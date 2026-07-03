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
from typing import Dict, List, Tuple
from gerrit_client import (
    get_cr_detail, get_file_diff, iter_diff_lines,
    extract_jira, find_related_crs, BASE
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

    # TODO 无主（2026-04-30 更新：CHY* 通配 + FL2；2026-06-06 新增 AUDI；2026-06-16 v2.5.5 新增 CHER）
    ("R.TODO_NO_OWNER", re.compile(r"//\s*TODO(?!.*(?:@|\bJira\b|\bCHER[A-Z0-9]*\b|\bCHY[A-Z0-9]+\b|\bBAIC\b|\bKP[A-Z0-9]+\b|\bAUDI\b|\bFL[1-3]\b|\bD01\b))"), "P3",
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

    # Jira 缺失硬规则（2026-04-30 更新：CHY*/KP*/FL2 通配 + “项目正式”软判断豁免）
    if not result["jira"]:
        # 软判断：看 branch / commit message / project 是否是项目正式开发
        branch = (d.get("branch") or "").lower()
        project_path = (d.get("project") or "").lower()
        cmsg_lower = commit_msg.lower()
        # 项目关键词（车联内部项目标识）
        project_keywords = [
            "t1l", "t1v", "n80", "kp31", "kp", "fl1", "fl2", "fl3",
            "d01", "baic", "chery", "cher", "jtr", "chyt", "audi",
        ]
        # 临时/实验性标识（出现则不豁免）
        temp_markers = ["test_only", "demo", "tmp", "temporary", "experiment", "playground", "poc"]
        is_project_branch = any(k in branch or k in project_path for k in project_keywords)
        is_temp = any(m in cmsg_lower for m in temp_markers)
        # 判断是否豁免
        if is_project_branch and not is_temp:
            # 豁免为 P2（警告）
            result["comments"].setdefault("/COMMIT_MSG", []).append({
                "line": 1, "level": "P2",
                "message": (
                    "⚠️ 缺 Jira 关联号，但根据 branch (`%s`) / project (`%s`) 判断为项目正式开发，已豁免硬阅 P0。\n\n"
                    "建议补充 CHERxxx-nnn / CHYxxx-nnn / BAIC-nnn / KPxxx-nnn / AUDI-nnn / FL[1-3]-nnn / D01-nnn 等格式的 Jira 号，便于追溯。"
                ) % (d.get("branch") or "-", d.get("project") or "-")
            })
            result["summary"]["P2"] += 1
            result["jira_exempted"] = True
        else:
            # 未豁免→ P0 原规则
            result["comments"].setdefault("/COMMIT_MSG", []).append({
                "line": 1, "level": "P0",
                "message": "缺 Jira 关联号。请在 subject 或 commit message 中补充 CHERxxx-nnn / CHYxxx-nnn / BAIC-nnn / KPxxx-nnn / AUDI-nnn / FL[1-3]-nnn / D01-nnn 等格式的 Jira 号，便于追溯。"
            })
            result["summary"]["P0"] += 1

    # 扫 diff
    added_by_file: Dict[str, List[Tuple[int, str]]] = {}
    context_by_file: Dict[str, List[str]] = {}
    for fn, meta in files.items():
        if fn == "/COMMIT_MSG":
            continue
        dd = get_file_diff(cr_num, cur, fn)
        if not isinstance(dd, dict):
            continue
        added: List[Tuple[int, str]] = []
        full: List[str] = []
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


# ============================================================
# v2.6.0 闭环增强：契约变更扫 + 跨 CR 一致性扫
# v2.6.0 内部修订 (2026-05-15)：
#   - LRU cache 兜底跨 CR sibling 扫描（同 Jira 多 CR 复用一次查询）
#   - sibling CR 拉取改 o=CURRENT_FILES（最小集，省 30% 流量）
# ============================================================

import re as _re
import functools as _functools

# 同 Jira 多 CR 之间共享一次 sibling 查询（LRU cache，避免同一 Jira 重复打 Gerrit）
# key 仅取 (jira, current_owner_id)，gerrit_get_func 不可哈希故包裹一层闭包
_SIBLING_CACHE = {}

def _sibling_lookup_cached(jira, current_owner_id, gerrit_get_func, cr_number):
    """v2.6.0 修订 A+B：LRU cache + 最小 o= 参数。

    - 命中 cache（同 Jira + 同 owner）→ 复用，不重新发 HTTP
    - 未命中 → 用 o=CURRENT_FILES 拿最小数据（只要 files 路径）
    """
    cache_key = (jira, current_owner_id)
    if cache_key in _SIBLING_CACHE:
        cached = _SIBLING_CACHE[cache_key]
        # 排除当前 CR 自身
        return [s for s in cached if s.get('_number') != int(cr_number)]

    from urllib.parse import quote
    q = f'message:{jira}'
    # v2.6.0 规则 B：只拿 CURRENT_FILES（隐含 current_revision SHA + files map），
    # 不解析 detail meta（labels / accounts），省 30% 流量
    path = f'/a/changes/?q={quote(q)}&o=CURRENT_FILES'
    code, sibling_list = gerrit_get_func(path)
    if code != 200 or not isinstance(sibling_list, list):
        return []
    _SIBLING_CACHE[cache_key] = sibling_list
    return [s for s in sibling_list if s.get('_number') != int(cr_number)]


def _sibling_cache_clear():
    """测试 / 长跑场景手工清缓存"""
    _SIBLING_CACHE.clear()

def contract_change_scan(diff_text, files):
    """CL-6: 扫描 diff 中的契约变更候选（默认 P2，待上下文判定升级）

    Args:
        diff_text: full diff text
        files: list of {path, new_content, old_content} dicts (or similar from prepare_context)

    Returns:
        list of contract change candidates
    """
    candidates = []

    # 1. current.txt 中的 IntDef 数值变更
    # 形如: -    field public static final int SUCCESS = 1;
    #       +    field public static final int SUCCESS = 0;
    intdef_old = {}
    intdef_new = {}
    for line in diff_text.split('\n'):
        m = _re.match(r'^([-+])\s*field public static final int (\w+) = (-?\d+);', line)
        if not m: continue
        sign, name, val = m.group(1), m.group(2), int(m.group(3))
        (intdef_old if sign == '-' else intdef_new)[name] = val

    for name in set(intdef_old) & set(intdef_new):
        if intdef_old[name] != intdef_new[name]:
            candidates.append({
                'type': 'intdef_value',
                'symbol': name,
                'old_value': intdef_old[name],
                'new_value': intdef_new[name],
                'context_aware_severity': 'P2',
                'note': '默认 P2 提醒；如确认仅单端改动需 P2；如两端不一致 LLM 应升 P0'
            })

    # 2. proto field tag 变更
    proto_old = {}
    proto_new = {}
    for line in diff_text.split('\n'):
        # 简单匹配 enum / field：  KEY = 1;  或  required int32 foo = 5;
        m = _re.match(r'^([-+])\s*(?:repeated\s+|optional\s+|required\s+)?(?:\w[\w<>.\s]*\s+)?(\w+)\s*=\s*(\d+)\s*;', line)
        if not m: continue
        sign, name, tag = m.group(1), m.group(2), int(m.group(3))
        # 排除非 proto 文件（看上下文中是否提到 .proto）
        (proto_old if sign == '-' else proto_new)[name] = tag

    # 检测 .proto 上下文：通过 diff_text 是否包含 .proto 段
    if '.proto' in diff_text or 'syntax = "proto' in diff_text:
        for name in set(proto_old) & set(proto_new):
            if proto_old[name] != proto_new[name]:
                candidates.append({
                    'type': 'proto_tag',
                    'symbol': name,
                    'old_value': proto_old[name],
                    'new_value': proto_new[name],
                    'context_aware_severity': 'P2',
                    'note': 'proto field tag 一经使用永不复用；如 LLM 确认是新增字段从未用过的 tag 起编则无问题'
                })

    # 3. Bundle / Parcel key 字符串字面值变化
    key_old = {}
    key_new = {}
    for line in diff_text.split('\n'):
        m = _re.match(r'^([-+]).*?(\w+KEY\w*|KEY_\w+)\s*=\s*"([^"]+)"', line)
        if not m: continue
        sign, name, val = m.group(1), m.group(2), m.group(3)
        (key_old if sign == '-' else key_new)[name] = val

    for name in set(key_old) & set(key_new):
        if key_old[name] != key_new[name]:
            candidates.append({
                'type': 'bundle_key',
                'symbol': name,
                'old_value': key_old[name],
                'new_value': key_new[name],
                'context_aware_severity': 'P2',
                'note': 'Bundle key 字符串变更默认 P2；如两端不一致 LLM 应升 P0'
            })

    return candidates


def contract_consistency_scan(cr_number, jira, contract_changes, gerrit_get_func, current_owner=None):
    """CL-3 (v2.6.0 修订)：上下文感知的跨 CR 一致性扫描

    志强 2026-05-15 修订关键约束：
      - 单人单 CR 内闭环（两端都改）且契约值不一致 → P0
      - 单人单 CR 内闭环 + 契约值一致 → 不发评论
      - 多人多 CR 协作 + 检测到完整配套 → 不发评论 / 至多 P2
      - 多人协作但仅检测到单端 → P2 提醒（不阻断）
      - 单人单 CR 仅改单端 → P2 提醒（需补另一端）

    Returns:
        dict: assessment ∈ {
            'context_aware_ok_multi_owner',
            'single_owner_closed_loop_need_value_check',
            'single_side_only_single_owner_p2',
            'single_side_multi_owner_p2',
            'no_jira_cannot_verify',
            'scan_failed_use_p2',
            'unknown_use_p2'
        }
    """
    if not contract_changes:
        return None

    result = {
        'changed_contracts': [c.get('symbol') for c in contract_changes],
        'sibling_crs': [],
        'client_side_found_in_sibling': False,
        'server_side_found_in_sibling': False,
        'sibling_other_owner': False,
        'sibling_count': 0,
        'assessment': 'context_aware_ok',
        'note': '',
    }

    if not jira:
        result['assessment'] = 'no_jira_cannot_verify'
        result['note'] = '无 Jira 号，无法跨 CR 比对契约一致性；LLM 应给 P2 提醒 owner 确认上下游配套情况'
        return result

    # 查同 Jira 下其他 CR——v2.6.0 修订：LRU cache 复用 + 最小参数 o=CURRENT_FILES
    try:
        sibling_list = _sibling_lookup_cached(jira, current_owner, gerrit_get_func, cr_number)
        # 只需文件路径判别侧别；owner 从 sibling object 直接读。
        for s in sibling_list:
            cur_rev = s.get('current_revision', '')
            files = list((s.get('revisions', {}).get(cur_rev, {}).get('files', {}) or {}).keys())
            side = _classify_side(files)
            owner_info = s.get('owner', {}) or {}
            sibling_owner = owner_info.get('username') or owner_info.get('name', '')
            result['sibling_crs'].append({
                'cr': s.get('_number'),
                'status': s.get('status'),
                'subject': (s.get('subject') or '')[:80],
                'side': side,
                'owner': sibling_owner,
                'files': files[:5],
            })
            if sibling_owner and current_owner and sibling_owner != current_owner:
                result['sibling_other_owner'] = True
            if side == 'server':
                result['server_side_found_in_sibling'] = True
            if side == 'client_sdk':
                result['client_side_found_in_sibling'] = True
        result['sibling_count'] = len(sibling_list)
    except Exception as e:
        result['error'] = f'sibling scan failed: {e}'
        result['assessment'] = 'scan_failed_use_p2'
        result['note'] = '跨 CR 扫描失败，LLM 默认走 P2 提醒'
        return result

    has_client = result['client_side_found_in_sibling']
    has_server = result['server_side_found_in_sibling']
    is_single_owner_scope = not result['sibling_other_owner']

    # 综合评定（关键修订：单人 CR 内能闭环的，不一致按 P0；多人协作不阻断仅 P2 提醒）
    if has_client and has_server:
        # 两端都有 sibling CR 覆盖
        if is_single_owner_scope:
            result['assessment'] = 'single_owner_closed_loop_need_value_check'
            result['note'] = ('检测到当前 owner 在单 CR 或多 CR 范围内已闭环覆盖两端；'
                              'LLM 必须语义比对两端契约值是否一致——不一致则 P0；一致则不发评论')
        else:
            result['assessment'] = 'context_aware_ok_multi_owner'
            result['note'] = ('检测到多人多 CR 协作覆盖两端；信任协作流程，最多 P2 提醒，'
                              '不阻断合入（人工最终会对齐）')
    elif has_client or has_server:
        # 单端有 sibling
        if is_single_owner_scope:
            result['assessment'] = 'single_side_only_single_owner_p2'
            result['note'] = ('当前 owner 单 CR 仅改了一端契约，未见另一端配套 CR；'
                              '判 P2 提醒 owner 补另一端，不阻断合入')
        else:
            result['assessment'] = 'single_side_multi_owner_p2'
            result['note'] = ('多人协作场景下仅检测到单端配套；判 P2 提醒 owner 与协作方确认另一端，'
                              '不阻断合入')
    else:
        # 完全无 sibling
        if is_single_owner_scope:
            # 单 CR 单 owner 只改契约本身，但未发现任何配套 CR
            result['assessment'] = 'single_side_only_single_owner_p2'
            result['note'] = ('未发现同 Jira 兄弟 CR；如本 CR 仅改单端契约则需补另一端，判 P2 提醒，'
                              '不阻断合入')
        else:
            result['assessment'] = 'unknown_use_p2'
            result['note'] = '协作场景但无配套 CR，LLM 走 P2 提醒'

    return result


def _classify_side(files):
    """粗略根据文件路径判断 CR 是 server 还是 client SDK 侧"""
    for f in files:
        fl = f.lower()
        if 'manager/api' in fl or '/sdk/' in fl or '/connector/' in fl or 'adapter' in fl:
            return 'client_sdk'
        if 'service.java' in fl or 'packages/services' in fl or '/qnx/' in fl or '/hal/' in fl:
            return 'server'
    return 'unknown'
