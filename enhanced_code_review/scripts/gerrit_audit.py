"""audit: 对单 CR 做结构化评审，输出评审草稿（JSON）供人工确认后再 post。

用法：
  python3 gerrit_audit.py <CR_NUMBER>                 # 输出评审草稿到 stdout
  python3 gerrit_audit.py <CR_NUMBER> -o review.json  # 保存到文件

说明：本脚本做**机械规则扫描**（降低志强的遗漏风险），真正的高质量评审仍需要 LLM
对全量 diff 跑一遍 checklist。所以用法上是：
  1) 本脚本先扫出"硬规则"命中项（null check 缺失、e.printStackTrace、Jira 缺失等）
  2) 把 diff + 硬规则结果一起给 LLM，让 LLM 补 L1/L3 架构类问题
  3) 人工（志强）审核 → post
"""
import sys, re, json, argparse
from gerrit_client import (
    get_cr_detail, get_file_diff, iter_diff_lines,
    extract_jira, find_related_crs, BASE
)
try:
    from consistency_scan import analyze_file as scan_consistency
except ImportError:
    scan_consistency = None

# 机械规则 ---------------------------------------------------------------
# 原则：只保留团队公认的硬规范。
# 志强 2026-04-19 明确：e.printStackTrace() 不算规范问题，不纳入规则。
# 只保留：空 catch 吞异常（必中 P1）、TODO 无主（P3）、System.out 服务禁用（P2）
#
# 注意：以下规则都是"低级模式识别"，真正的评审价值在 LLM 按 checklist 推理。
RULES = [
    # (id, pattern, level, title, detail)

    # 空 catch：异常被静默吞掉，服务进入不一致状态且无日志
    ("R.EMPTY_CATCH", re.compile(r"catch\s*\([^)]*\)\s*\{\s*\}"), "P1",
     "空 catch 块吞掉异常",
     "异常被吞掉会导致服务进入不一致状态，但外部无任何日志、无任何告警，"
     "现场无法排查。应至少 Log.w/e 记录，或明确 rethrow / 降级。"),

    # System.out 服务禁用
    ("R.SYSTEM_OUT", re.compile(r"\bSystem\.(out|err)\.print"), "P2",
     "服务层出现 System.out/err",
     "服务层禁用 System.out/err（调试遗留？）。与项目统一 Log 规范不一致。"),

    # TODO 无主
    ("R.TODO_NO_OWNER", re.compile(r"//\s*TODO(?!.*(?:@|\bJira\b|\bCHYT1V\b|\bBAIC\b|\bKP31\b))"), "P3",
     "TODO 未关联 owner / Jira",
     "TODO 需附 owner 或 Jira 号，否则随时间推移会变成无主债。"),
]


def scan_line(text):
    """对单行新增代码做规则扫描，返回命中列表。"""
    hits = []
    for rid, pat, level, title, detail in RULES:
        if pat.search(text):
            hits.append({"rule": rid, "level": level, "title": title, "detail": detail})
    return hits


def analyse_cr(cr_num):
    d = get_cr_detail(cr_num)
    if not isinstance(d, dict):
        return {"error": str(d)}

    subj = d.get("subject", "")
    cur = d.get("current_revision")
    commit_msg = d["revisions"][cur]["commit"]["message"]
    owner = d.get("owner", {})
    files = d["revisions"][cur].get("files") or {}

    result = {
        "cr": cr_num,
        "subject": subj,
        "owner": owner.get("username") or owner.get("name"),
        "project": d.get("project"),
        "branch": d.get("branch"),
        "url": f"{BASE}/c/{d.get('project')}/+/{cr_num}",
        "revision": cur,
        "jira": extract_jira(subj + "\n" + commit_msg),
        "related_crs": [],
        "comments": {},   # path -> [ {line, level, message} ]
        "summary": {"P0": 0, "P1": 0, "P2": 0, "P3": 0},
        "suggested_score": 0,
        "cover": "",
    }

    # 关联 CR
    for j in result["jira"]:
        peers = find_related_crs(j)
        result["related_crs"].extend(
            [{"cr": r["_number"], "subject": r["subject"], "status": r["status"]}
             for r in peers if r["_number"] != int(cr_num)]
        )

    # Jira 缺失硬规则
    if not result["jira"]:
        result["comments"].setdefault("/COMMIT_MSG", []).append({
            "line": 1, "level": "P0",
            "message": "缺 Jira 关联号。请在 subject 或 commit message 中补充 CHYT1V-xxx / BAIC-xxx / KP31-xxx 等格式的 Jira 号，便于追溯。"
        })
        result["summary"]["P0"] += 1

    # 扫 diff
    for fn, meta in files.items():
        if fn == "/COMMIT_MSG":
            continue
        dd = get_file_diff(cr_num, cur, fn)
        if not isinstance(dd, dict):
            continue
        for old_line, new_line, kind, text in iter_diff_lines(dd):
            if kind != "add":
                continue
            hits = scan_line(text)
            for h in hits:
                result["comments"].setdefault(fn, []).append({
                    "line": new_line,
                    "level": h["level"],
                    "message": f"[{h['level']}] {h['title']}\n\n{h['detail']}",
                    "rule": h["rule"],
                })
                result["summary"][h["level"]] += 1

    # 同文件内一致性扫描（车载中间件最高发的硬不一致）
    if scan_consistency:
        for fn in files:
            if fn == "/COMMIT_MSG" or not fn.endswith(".java"):
                continue
            try:
                findings = scan_consistency(cr_num, cur, fn)
            except Exception as e:
                continue
            for f in findings:
                # 为每个 unchecked method 分别挑一条，定位到函数 header
                for mname in f["unchecked_methods"]:
                    result["comments"].setdefault(fn, []).append({
                        "line": 1,  # LLM 会根据 method 名再校正行号
                        "level": f["severity"],
                        "message": (
                            f"[{f['severity']}] {f['title']} — {mname}() 未判空\n\n"
                            f"{f['detail']}\n\n"
                            f"该类内已判空的方法：{f['checked_methods']}\n"
                            f"该类内未判空的方法：{f['unchecked_methods']}"
                        ),
                        "rule": "R.NULL_CHECK_INCONSISTENT",
                        "method": mname,
                        "field": f["field"],
                    })
                    result["summary"][f["severity"]] += 1

    # 决分
    s = result["summary"]
    if s["P0"] > 0:
        result["suggested_score"] = -1
    elif s["P1"] > 0:
        result["suggested_score"] = 0
    else:
        result["suggested_score"] = 1

    # 默认 cover（LLM 应覆盖）
    parts = [
        f"机械规则扫描结果（Jira: {', '.join(result['jira']) or '无'}）：",
        f"P0={s['P0']}, P1={s['P1']}, P2={s['P2']}, P3={s['P3']}",
        "（以上仅为硬规则命中项；架构/功能/时序类问题需 LLM 补充）",
    ]
    result["cover"] = "\n".join(parts)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cr")
    ap.add_argument("-o", "--output", default=None)
    a = ap.parse_args()

    r = analyse_cr(a.cr)
    out = json.dumps(r, ensure_ascii=False, indent=2)
    if a.output:
        open(a.output, "w", encoding="utf-8").write(out)
        print(f"saved -> {a.output}")
    else:
        print(out)


if __name__ == "__main__":
    main()
