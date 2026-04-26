"""inbox: 列出你作为 reviewer 且 open 的 CR。
Usage:
  python3 gerrit_inbox.py              # 所有待审
  python3 gerrit_inbox.py --unvoted    # 只看没打过 +2 的
  python3 gerrit_inbox.py --owner <username>  # 谁提的 CR
"""
import sys, urllib.parse, argparse
from gerrit_client import gget, BASE, USER, extract_jira


def run(mode, owner):
    if owner:
        q = f"owner:{owner} AND status:open"
    elif mode == "unvoted":
        q = f"reviewer:self AND status:open AND NOT label:Code-Review=+2,{USER}"
    else:
        q = "reviewer:self AND status:open"

    query = urllib.parse.quote(q)
    s, data = gget(f"/a/changes/?q={query}&n=30"
                   "&o=DETAILED_ACCOUNTS&o=LABELS&o=CURRENT_REVISION&o=CURRENT_COMMIT")

    if not isinstance(data, list):
        print("ERR:", data)
        return

    print(f"query: {q}")
    print(f"count: {len(data)}\n")

    for c in data:
        num = c.get("_number")
        subj = c.get("subject", "")
        proj = c.get("project", "")
        br = c.get("branch", "")
        owner_name = c.get("owner", {}).get("username") or c.get("owner", {}).get("name", "?")
        upd = c.get("updated", "")[:16]
        ins = c.get("insertions", 0)
        dele = c.get("deletions", 0)
        wip = "[WIP] " if c.get("work_in_progress") else ""

        # CI
        ver = c.get("labels", {}).get("Verified", {})
        ci = "✅" if ver.get("approved") else ("❌" if ver.get("rejected") else "⏳")

        # 我是否已投 Code-Review
        cr = c.get("labels", {}).get("Code-Review", {})
        my_vote = ""
        for v in cr.get("all", []) or []:
            if v.get("username") == USER:
                val = v.get("value")
                if val:
                    my_vote = f" 已投 self={val:+d}"
                break

        jiras = extract_jira(subj)
        jira_s = f" [{'/'.join(jiras)}]" if jiras else " [⚠️ 无 Jira]"

        print(f"[{num}] {wip}{ci} +{ins}/-{dele}{jira_s}{my_vote}")
        print(f"  {subj}")
        print(f"  owner={owner_name} proj={proj.split('/')[-1]} branch={br} upd={upd}")
        print(f"  {BASE}/c/{proj}/+/{num}")
        print()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--unvoted", action="store_true")
    ap.add_argument("--owner", default=None, help="按提交人用户名过滤")
    a = ap.parse_args()
    mode = "unvoted" if a.unvoted else "all"
    run(mode, a.owner)
