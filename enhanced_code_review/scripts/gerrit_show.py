"""show: 拉 CR 完整 diff + commit message + Jira 关联 + 同组分片 CR。
Usage:
  python3 gerrit_show.py <CR_NUMBER>
"""
import sys, json
from gerrit_client import get_cr_detail, get_file_diff, iter_diff_lines, extract_jira, find_related_crs, BASE


def main(cr):
    d = get_cr_detail(cr)
    if not isinstance(d, dict):
        print("ERR:", d)
        return

    subj = d.get("subject", "")
    proj = d.get("project", "")
    br = d.get("branch", "")
    owner = d.get("owner", {})
    owner_name = owner.get("username") or owner.get("name", "?")
    cur = d.get("current_revision")
    commit_msg = d["revisions"][cur]["commit"]["message"]

    print("=" * 80)
    print(f"CR [{cr}] {subj}")
    print(f"owner: {owner_name} ({owner.get('email','')})")
    print(f"project: {proj}")
    print(f"branch: {br}, status: {d.get('status')}, WIP: {bool(d.get('work_in_progress'))}")
    print(f"URL: {BASE}/c/{proj}/+/{cr}")
    print("=" * 80)

    # Jira
    jiras = extract_jira(subj + "\n" + commit_msg)
    if jiras:
        print(f"\nJira: {', '.join(jiras)}")
        for j in jiras:
            related = find_related_crs(j)
            peers = [r for r in related if r.get("_number") != int(cr)]
            if peers:
                print(f"  关联 CR (Jira={j}):")
                for r in peers[:10]:
                    status = r.get("status")
                    r_subj = r.get("subject", "")[:70]
                    print(f"    [{r['_number']}] {status} · {r_subj}")
    else:
        print("\n⚠️ 未发现 Jira 号（将被 P0 标记）")

    # commit message
    print(f"\n--- Commit Message ---\n{commit_msg}")

    # files
    files = d["revisions"][cur].get("files") or {}
    print(f"\n--- Files ({len([f for f in files if f != '/COMMIT_MSG'])}) ---")
    for fn, m in files.items():
        if fn == "/COMMIT_MSG":
            continue
        print(f"  {fn}: +{m.get('lines_inserted',0)}/-{m.get('lines_deleted',0)} ({m.get('status','M')})")

    # diff
    print("\n--- Diff (new side 行号) ---")
    for fn in files:
        if fn == "/COMMIT_MSG":
            continue
        dd = get_file_diff(cr, cur, fn)
        if not isinstance(dd, dict):
            continue
        print(f"\n### {fn}")
        for old_line, new_line, kind, text in iter_diff_lines(dd):
            if kind == "add":
                print(f"  L{new_line:4d} + {text}")
            elif kind == "del":
                print(f"  L{old_line:4d} - {text}")
            # ctx 跳过，diff 太长


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 gerrit_show.py <CR_NUMBER>")
        sys.exit(1)
    main(sys.argv[1])
