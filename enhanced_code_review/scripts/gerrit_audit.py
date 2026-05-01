"""audit: 对单 CR 做结构化评审，输出评审草稿（JSON）供人工确认后再 post。

用法：
  python3 gerrit_audit.py <CR_NUMBER>                 # 输出评审草稿到 stdout
  python3 gerrit_audit.py <CR_NUMBER> -o review.json  # 保存到文件

说明：本脚本做**机械规则扫描**（降低遗漏风险），真正的高质量评审仍需要 LLM
对全量 diff 跑一遍 checklist。所以用法上是：
  1) 本脚本先扫出"硬规则"命中项（null check 缺失、e.printStackTrace、Jira 缺失等）
  2) 把 diff + 硬规则结果一起给 LLM，让 LLM 补 L1/L3 架构类问题
  3) 人工审核 → post
"""
import sys, re, json, argparse
from gerrit_client import (
    get_cr_detail, get_file_diff, iter_diff_lines,
    extract_jira, extract_jira_violations, find_related_crs, BASE
)
try:
    from consistency_scan import analyze_file as scan_consistency
except ImportError:
    scan_consistency = None

try:
    from privacy_compliance_scan import scan_diff_added as _privacy_scan_diff
except ImportError:
    _privacy_scan_diff = None

# 机械规则 ---------------------------------------------------------------
# 原则：只保留团队公认的硬规范。
# 团队约定 2026-04-19：e.printStackTrace() 不算规范问题，不纳入规则。
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
    ("R.TODO_NO_OWNER", re.compile(
        r"//\s*TODO(?!.*(?:@|\bJira\b|\bCHYT1V\b|\bBAIC\b|\bKP31\b|\bFL[123]\b|\bT1V\b|\bD01\b|\bCHYT12A\b|\bCHYMIFA\b))"
    ), "P3",
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
        # 隐私合规候选（门控 A + B 共现）；不直接计入 comments/summary，
        # 交由 LLM 在 Step 8 做门控 C 语义确认后再决定是否贴 P0 inline。
        "privacy_candidates": [],
    }

    # 关联 CR
    for j in result["jira"]:
        peers = find_related_crs(j)
        result["related_crs"].extend(
            [{"cr": r["_number"], "subject": r["subject"], "status": r["status"]}
             for r in peers if r["_number"] != int(cr_num)]
        )

    # Jira 合规性检测（三类不合规：缺失 / 占位号 / 纯数字）
    jira_text = subj + "\n" + commit_msg
    jira_violations = extract_jira_violations(jira_text)
    result["jira_violations"] = jira_violations

    if not result["jira"]:
        if jira_violations:
            # 有 Jira 号但全部不合规（占位号或纯数字）
            for v in jira_violations:
                result["comments"].setdefault("/COMMIT_MSG", []).append({
                    "line": 1, "level": "P0",
                    "message": (
                        f"Jira 号不合规（{v['type']}）：{v['raw']}。{v['detail']}\n\n"
                        "合规格式：CHYT1V-1234 / BAIC-567 / KP31-89 / FL1-12 / FL2-34 / FL3-56 / "
                        "T1V-78 / D01-90 / CHYT12A-11 / CHYMIFA-22 等（数字部分须为非零起始正整数）。"
                    ),
                    "rule": f"R.JIRA_{v['type'].upper()}",
                })
                result["summary"]["P0"] += 1
        else:
            # 完全没有任何 Jira 相关内容
            result["comments"].setdefault("/COMMIT_MSG", []).append({
                "line": 1, "level": "P0",
                "message": (
                    "缺 Jira 关联号。请在 subject 或 commit message 中补充合规格式的 Jira 号，便于追溯。\n\n"
                    "合规前缀：CHYT1V / BAIC / KP31 / FL1 / FL2 / FL3 / T1V / D01 / CHYT12A / CHYMIFA\n"
                    "合规格式：<前缀>-<非零起始正整数>，如 CHYT1V-1234。\n"
                    "不合规示例：纯数字（如 123456）、占位号（如 CHYT1V-000 / CHYT1V-0001）。"
                ),
                "rule": "R.JIRA_MISSING",
            })
            result["summary"]["P0"] += 1
    elif jira_violations:
        # 有合规 Jira 号，但同时存在不合规号 → P1 提醒
        for v in jira_violations:
            result["comments"].setdefault("/COMMIT_MSG", []).append({
                "line": 1, "level": "P1",
                "message": (
                    f"检测到不合规 Jira 引用（{v['type']}）：{v['raw']}。{v['detail']}\n"
                    "已识别到合规 Jira 号，此条仅作提醒。"
                ),
                "rule": f"R.JIRA_{v['type'].upper()}_WARN",
            })
            result["summary"]["P1"] += 1

    # 扫 diff（变量注解使用兼容 Python 3.6 的写法：不使用 PEP 585 下标注解）
    added_by_file = {}      # type: dict
    context_by_file = {}    # type: dict
    for fn, meta in files.items():
        if fn == "/COMMIT_MSG":
            continue
        dd = get_file_diff(cr_num, cur, fn)
        if not isinstance(dd, dict):
            continue
        added = []   # type: list
        full = []    # type: list
        for old_line, new_line, kind, text in iter_diff_lines(dd):
            if kind in ("add", "ctx") and new_line:
                if len(full) < new_line:
                    full.extend([""] * (new_line - len(full)))
                full[new_line - 1] = text
            if kind != "add":
                continue
            if new_line:
                added.append((new_line, text))
            hits = scan_line(text)
            for h in hits:
                result["comments"].setdefault(fn, []).append({
                    "line": new_line,
                    "level": h["level"],
                    "message": f"[{h['level']}] {h['title']}\n\n{h['detail']}",
                    "rule": h["rule"],
                })
                result["summary"][h["level"]] += 1
        if added:
            added_by_file[fn] = added
            context_by_file[fn] = full

    # 隐私合规候选扫描（门控 A + B 共现；门控 C 留给 LLM）
    if _privacy_scan_diff is not None and added_by_file:
        try:
            result["privacy_candidates"] = _privacy_scan_diff(
                added_by_file, context_by_file,
            )
        except Exception as e:
            result["privacy_candidates"] = [{"error": f"privacy_scan failed: {e}"}]

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
    privacy_cand_total = sum(
        len(pf.get("candidates", [])) for pf in result.get("privacy_candidates", [])
        if isinstance(pf, dict)
    )
    parts = [
        f"机械规则扫描结果（Jira: {', '.join(result['jira']) or '无'}）：",
        f"P0={s['P0']}, P1={s['P1']}, P2={s['P2']}, P3={s['P3']}",
        f"隐私合规候选（待 LLM 做门控 C 确认）：{privacy_cand_total}",
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
