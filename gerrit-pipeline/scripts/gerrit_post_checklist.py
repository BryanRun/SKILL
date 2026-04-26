"""gerrit_post_checklist.py — 将 Checklist 贴到 Gerrit CR 评论。

用法：
  python3 gerrit_post_checklist.py --cr 1003659 --checklist checklist.txt
  python3 gerrit_post_checklist.py --cr 1003659 --checklist-text "### Checklist ..."
  python3 gerrit_post_checklist.py --cr 1003659 --checklist checklist.txt --dry
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
        print("错误: Gerrit 用户名或密码未配置", file=sys.stderr)
        print("请运行 'python3 pipeline_config.py init' 或设置环境变量 GERRIT_USER / GERRIT_HTTP_PASSWORD", file=sys.stderr)
        sys.exit(1)
    return HTTPBasicAuth(user, pwd)


GERRIT_AUTH = _load_gerrit_auth()


def _strip(t):
    if t.startswith(")]}'"):
        t = t[4:]
    return t


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


def main():
    ap = argparse.ArgumentParser(description="将 Checklist 贴到 Gerrit CR 评论")
    ap.add_argument("--cr", required=True, help="CR 编号")
    ap.add_argument("--rev", default="current", help="revision hash（默认 current）")
    ap.add_argument("--checklist", help="Checklist 文件路径")
    ap.add_argument("--checklist-text", help="Checklist 文本内容（与 --checklist 二选一）")
    ap.add_argument("--dry", action="store_true", help="仅预览，不实际发送")
    args = ap.parse_args()

    if args.checklist:
        checklist = open(args.checklist, "r", encoding="utf-8").read()
    elif args.checklist_text:
        checklist = args.checklist_text
    else:
        print("错误: 需要 --checklist 或 --checklist-text", file=sys.stderr)
        sys.exit(1)

    body = {
        "message": checklist,
        "notify": "OWNER_REVIEWERS",
    }

    print(f"=== POST preview ===")
    print(f"CR: {args.cr}, revision: {args.rev}")
    print(f"Checklist length: {len(checklist)} chars")

    if args.dry:
        print(f"\n{checklist}")
        print("\n[DRY RUN] 未实际发送")
        return

    s, resp = gerrit_post(f"/a/changes/{args.cr}/revisions/{args.rev}/review", body)
    print(f"\nstatus: {s}")
    if s == 200:
        print("Checklist 已成功贴到 Gerrit")
    else:
        print(f"失败: {json.dumps(resp, ensure_ascii=False) if isinstance(resp, dict) else str(resp)[:500]}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
