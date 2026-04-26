"""gerrit_review.py — 主入口，全自动化评审 + 贴回

用法：
  python3 gerrit_review.py <CR_NUMBER>              # 全自动（拉取→扫描→让 LLM 评 → 贴回）
  python3 gerrit_review.py <CR_NUMBER> --dry        # 只拉数据 + 机械扫描，不贴
  python3 gerrit_review.py <CR_NUMBER> --prepare    # 准备好 LLM 输入（stdout），LLM 产出 review.json 后可用 --post
  python3 gerrit_review.py <CR_NUMBER> --post review.json [--score N]

本脚本不包含 LLM 调用。LLM 侧由 her 本体在对话里完成：
  1. her 跑 prepare，拿到上下文
  2. her 按 references/llm-review-prompt.md 的 system+user prompt 产出 review.json
  3. her 跑 --post review.json 贴回
"""
import sys, os, json, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gerrit_client import (
    get_cr_detail, get_file_diff, iter_diff_lines,
    extract_jira, find_related_crs, post_review, BASE
)

try:
    from consistency_scan import analyze_file as scan_consistency
except ImportError:
    scan_consistency = None

from gerrit_audit import analyse_cr


def prepare_context(cr_num):
    """拉齐 LLM 评审需要的所有上下文，一个 JSON 返回。"""
    d = get_cr_detail(cr_num)
    if not isinstance(d, dict):
        return {"error": str(d)}

    cur = d["current_revision"]
    subj = d.get("subject", "")
    commit_msg = d["revisions"][cur]["commit"]["message"]
    owner = d.get("owner", {})
    files = d["revisions"][cur].get("files") or {}
    project = d.get("project", "")
    branch = d.get("branch", "")

    ctx = {
        "cr": cr_num,
        "revision": cur,
        "subject": subj,
        "owner": owner.get("username") or owner.get("name"),
        "owner_email": owner.get("email"),
        "project": project,
        "branch": branch,
        "url": f"{BASE}/c/{project}/+/{cr_num}",
        "status": d.get("status"),
        "wip": bool(d.get("work_in_progress")),
        "insertions": d.get("insertions"),
        "deletions": d.get("deletions"),
        "jira": extract_jira(subj + "\n" + commit_msg),
        "commit_message": commit_msg,
        "files": [],
        "related_crs": [],
        "audit": {},
        "consistency": {},
    }

    # Jira 关联 CR
    for j in ctx["jira"]:
        peers = find_related_crs(j)
        for r in peers:
            if r.get("_number") == int(cr_num):
                continue
            ctx["related_crs"].append({
                "cr": r.get("_number"),
                "subject": r.get("subject"),
                "status": r.get("status"),
            })

    # files + diff
    for fn, meta in files.items():
        if fn == "/COMMIT_MSG":
            continue
        item = {
            "path": fn,
            "status": meta.get("status", "M"),
            "inserted": meta.get("lines_inserted", 0),
            "deleted": meta.get("lines_deleted", 0),
            "diff_lines": [],
        }
        dd = get_file_diff(cr_num, cur, fn)
        if isinstance(dd, dict):
            for old_l, new_l, kind, text in iter_diff_lines(dd):
                if kind == "ctx":
                    continue
                item["diff_lines"].append({
                    "old": old_l, "new": new_l, "kind": kind, "text": text,
                })
        ctx["files"].append(item)

    # audit: 机械规则
    audit = analyse_cr(cr_num)
    ctx["audit"] = {
        "summary": audit.get("summary", {}),
        "comments": audit.get("comments", {}),
        "suggested_score": audit.get("suggested_score"),
    }

    # consistency scan
    if scan_consistency:
        for fn in files:
            if fn == "/COMMIT_MSG" or not fn.endswith((".java", ".kt")):
                continue
            try:
                findings = scan_consistency(cr_num, cur, fn)
                if findings:
                    ctx["consistency"][fn] = findings
            except Exception as e:
                ctx["consistency"][f"{fn}_error"] = str(e)

    return ctx


def post_from_review_json(cr_num, review_json_path, score_override=None, dry=False):
    """把 LLM 产出的 review.json POST 回 Gerrit。"""
    review = json.load(open(review_json_path, "r", encoding="utf-8"))

    cr = str(review.get("cr") or cr_num)
    rev = review.get("revision") or "current"
    score = score_override if score_override is not None else review.get("score", 0)
    cover = review.get("cover", "")

    # comments：transform LLM 输出到 Gerrit 格式
    comments = {}
    for c in review.get("comments", []):
        path = c["path"]
        if path == "/COMMIT_MSG":
            # 挪到 cover 里
            cover += f"\n\n[commit message] {c.get('message', '')}"
            continue
        comments.setdefault(path, []).append({
            "line": c["line"],
            "message": c.get("message", c.get("title", "")),
            "unresolved": c.get("unresolved", True),
            "level": c.get("level"),
        })

    count = sum(len(v) for v in comments.values())
    preview = {
        "cr": cr, "rev": rev, "score": score,
        "inline_count": count, "cover_len": len(cover),
        "paths": list(comments.keys()),
    }
    print("=== POST preview ===")
    print(json.dumps(preview, ensure_ascii=False, indent=2))

    if dry:
        print("\n[DRY] skipped real POST")
        return preview

    s, resp = post_review(cr, rev, cover, score, comments)
    print(f"\nstatus: {s}")
    print(json.dumps(resp, ensure_ascii=False, indent=2) if isinstance(resp, dict) else resp[:500])
    return {"status": s, "resp": resp}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cr", help="CR number")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--prepare", action="store_true", help="只输出 LLM 评审所需上下文（JSON 到 stdout）")
    g.add_argument("--post", metavar="REVIEW_JSON", help="从 LLM 产出的 review.json POST 回 Gerrit")
    ap.add_argument("--dry", action="store_true", help="不真发，仅预览")
    ap.add_argument("--score", type=int, default=None, help="覆盖 review.json 中的 score")
    ap.add_argument("-o", "--output", help="prepare 模式输出到文件")
    a = ap.parse_args()

    if a.post:
        post_from_review_json(a.cr, a.post, a.score, a.dry)
    else:
        ctx = prepare_context(a.cr)
        out = json.dumps(ctx, ensure_ascii=False, indent=2)
        if a.output:
            open(a.output, "w", encoding="utf-8").write(out)
            print(f"prepared -> {a.output}")
            print(f"  P0={ctx['audit']['summary'].get('P0',0)} "
                  f"P1={ctx['audit']['summary'].get('P1',0)} "
                  f"P2={ctx['audit']['summary'].get('P2',0)} "
                  f"P3={ctx['audit']['summary'].get('P3',0)}")
            print(f"  consistency findings: {sum(len(v) for v in ctx['consistency'].values() if isinstance(v, list))}")
        else:
            print(out)


if __name__ == "__main__":
    main()
