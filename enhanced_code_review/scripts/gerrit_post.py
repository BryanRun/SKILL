"""post: 把评审草稿 (JSON) POST 到 Gerrit。

用法：
  # 从 audit 草稿发布，覆盖 score 和 cover
  python3 gerrit_post.py review.json

  # 命令行直接给 score 和 cover
  python3 gerrit_post.py review.json --score -1 --cover "cover.md"

  # dry run：打印不发
  python3 gerrit_post.py review.json --dry
"""
import sys, json, argparse
from gerrit_client import post_review


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("review_json")
    ap.add_argument("--score", type=int, default=None,
                    help="覆盖 suggested_score。-1/0/+1/+2。")
    ap.add_argument("--cover", default=None,
                    help="cover 文件路径（markdown）；或直接传字符串。")
    ap.add_argument("--dry", action="store_true", help="不真发，仅预览")
    a = ap.parse_args()

    r = json.loads(open(a.review_json, "r", encoding="utf-8").read())

    cr = r["cr"]
    rev = r.get("revision") or "current"
    score = a.score if a.score is not None else r["suggested_score"]
    if a.cover:
        if a.cover.endswith(".md") or a.cover.endswith(".txt"):
            try:
                cover = open(a.cover, "r", encoding="utf-8").read()
            except FileNotFoundError:
                cover = a.cover
        else:
            cover = a.cover
    else:
        cover = r.get("cover", "")

    comments = r.get("comments", {})
    # 清洗：跳过 /COMMIT_MSG（Gerrit 对 commit msg 的 comment 要走别的 path）
    clean = {}
    for path, items in comments.items():
        if path == "/COMMIT_MSG":
            # 把 commit msg 的问题挪到 cover 里
            extra = "\n\n[commit message]\n" + "\n".join(f"- {i['message']}" for i in items)
            cover = cover + extra
            continue
        clean[path] = items

    body_preview = {
        "cr": cr, "rev": rev, "score": score,
        "cover": cover,
        "comments_count": sum(len(v) for v in clean.values()),
        "paths": list(clean.keys()),
    }
    print("=== POST preview ===")
    print(json.dumps(body_preview, ensure_ascii=False, indent=2))

    if a.dry:
        print("\n[DRY RUN] skipped real POST")
        return

    s, resp = post_review(cr, rev, cover, score, clean)
    print(f"\nstatus: {s}")
    print(json.dumps(resp, ensure_ascii=False, indent=2) if isinstance(resp, dict) else resp[:500])


if __name__ == "__main__":
    main()
