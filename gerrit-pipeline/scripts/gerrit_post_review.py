"""gerrit_post_review.py — 将代码评审结论贴到 Gerrit CR 评论（不带 Code-Review label）。

专门用于处理 self-review 场景：当评审人与 CR 提交人相同时，Gerrit 禁止打分，
但仍需将评审结论（评分建议、问题统计、问题列表）贴到 CR 评论中。

用法：
  python3 gerrit_post_review.py --cr 1003659 --review review.txt
  python3 gerrit_post_review.py --cr 1003659 --review-text "## 评审结论 ..."
  python3 gerrit_post_review.py --cr 1003659 --review review.txt --dry
"""
import os, sys, json, argparse
import urllib3
import requests
from requests.auth import HTTPBasicAuth

urllib3.disable_warnings()

CONFIG_PATH = os.path.expanduser("~/.config/gerrit-pipeline/config.json")
GERRIT_BASE = "https://gerrit.auto-link.com.cn"


def _load_gerrit_auth():
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    gerrit_cfg = cfg.get("gerrit", {})
    user = gerrit_cfg.get("user") or os.environ.get("GERRIT_USER")
    pwd = gerrit_cfg.get("http_password") or os.environ.get("GERRIT_HTTP_PASSWORD")
    if not user or not pwd:
        print("错误: Gerrit 用户名或��码未配置", file=sys.stderr)
        print("请运行 'python3 pipeline_config.py init' 或设置环境变量 GERRIT_USER / GERRIT_HTTP_PASSWORD", file=sys.stderr)
        sys.exit(1)
    return HTTPBasicAuth(user, pwd)


GERRIT_AUTH = _load_gerrit_auth()


def _strip(t):
    if t.startswith(")]}'"):
        t = t[4:]
    return t


def gerrit_get(path):
    r = requests.get(
        f"{GERRIT_BASE}{path}",
        auth=GERRIT_AUTH, verify=False, timeout=30,
    )
    t = _strip(r.text)
    try:
        return r.status_code, json.loads(t)
    except Exception:
        return r.status_code, t


def gerrit_post(path, body):
    r = requests.post(
        f"{GERRIT_BASE}{path}",
        auth=GERRIT_AUTH, verify=False, timeout=30,
        headers={"Content-Type": "application/json; charset=UTF-8"},
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
    )
    t = _strip(r.text)
    try:
        return r.status_code, json.loads(t)
    except Exception:
        return r.status_code, t


def check_review_posted(cr):
    """检查 CR 的评论中是否已包含评审结论（cover message）。

    通过查找评论中是否包含评审结论的特征字符串来判断。
    返回 True 表示已贴回，False 表示未贴回。
    """
    s, resp = gerrit_get(f"/a/changes/{cr}/detail")
    if s != 200:
        print(f"警告: 无法获取 CR {cr} 详情 (status={s})，假定未贴回", file=sys.stderr)
        return False

    messages = resp.get("messages", [])
    review_markers = ["Code-Review", "P0", "P1", "P2", "P3", "suggested_score"]
    for msg in reversed(messages):
        text = msg.get("message", "")
        matched = sum(1 for m in review_markers if m in text)
        if matched >= 3:
            return True
    return False


def main():
    ap = argparse.ArgumentParser(description="将评审结论贴到 Gerrit CR 评论（不带 Code-Review label）")
    ap.add_argument("--cr", required=True, help="CR 编号")
    ap.add_argument("--rev", default="current", help="revision hash（默认 current）")
    ap.add_argument("--review", help="评审结论文件路径")
    ap.add_argument("--review-text", help="评审结论文本内容（与 --review 二选一）")
    ap.add_argument("--check-only", action="store_true", help="仅检查评审结论是否已贴回，不发送")
    ap.add_argument("--dry", action="store_true", help="仅预览，不实际发送")
    args = ap.parse_args()

    if args.check_only:
        posted = check_review_posted(args.cr)
        if posted:
            print(f"CR {args.cr} 评审结论已贴回")
            sys.exit(0)
        else:
            print(f"CR {args.cr} 评审结论未贴回")
            sys.exit(1)

    if args.review:
        review_text = open(args.review, "r", encoding="utf-8").read()
    elif args.review_text:
        review_text = args.review_text
    else:
        print("错误: 需要 --review 或 --review-text", file=sys.stderr)
        sys.exit(1)

    body = {
        "message": review_text,
        "notify": "OWNER_REVIEWERS",
    }

    print(f"=== POST review (no label) ===")
    print(f"CR: {args.cr}, revision: {args.rev}")
    print(f"Review length: {len(review_text)} chars")

    if args.dry:
        print(f"\n{review_text}")
        print("\n[DRY RUN] 未实际发送")
        return

    s, resp = gerrit_post(f"/a/changes/{args.cr}/revisions/{args.rev}/review", body)
    print(f"\nstatus: {s}")
    if s == 200:
        print("评审结论已成功贴到 Gerrit")
    else:
        print(f"失败: {json.dumps(resp, ensure_ascii=False) if isinstance(resp, dict) else str(resp)[:500]}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
