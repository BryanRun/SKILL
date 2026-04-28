"""pipeline_config.py — gerrit-pipeline 配置管理。

用法：
  python3 pipeline_config.py init                          # 交互式初始化配置
  python3 pipeline_config.py show                          # 展示当前配置
  python3 pipeline_config.py lookup-users --emails a@x.com,b@x.com  # 查询飞书 open_id

配置文件位置：~/.config/gerrit-pipeline/config.json
"""
import os, sys, json, time, argparse
import requests

CONFIG_DIR = os.path.expanduser("~/.config/gerrit-pipeline")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"

_token_cache = {"token": None, "expire_at": 0}


def _get_env(key):
    val = os.environ.get(key)
    if not val:
        print(f"错误: 环境变量 {key} 未设置", file=sys.stderr)
        sys.exit(1)
    return val


def _get_tenant_token():
    now = time.time()
    if _token_cache["token"] and _token_cache["expire_at"] > now + 60:
        return _token_cache["token"]

    resp = requests.post(
        f"{FEISHU_BASE_URL}/auth/v3/tenant_access_token/internal",
        json={
            "app_id": _get_env("FEISHU_APP_ID"),
            "app_secret": _get_env("FEISHU_APP_SECRET"),
        },
        timeout=30,
    )
    data = resp.json()
    if data.get("code") != 0:
        print(f"获取 token 失败: {json.dumps(data, ensure_ascii=False)}", file=sys.stderr)
        sys.exit(1)

    _token_cache["token"] = data["tenant_access_token"]
    _token_cache["expire_at"] = now + data.get("expire", 7200)
    return _token_cache["token"]


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return None
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f"配置已保存到 {CONFIG_PATH}")


def lookup_users_by_email(emails):
    token = _get_tenant_token()
    resp = requests.post(
        f"{FEISHU_BASE_URL}/contact/v3/users/batch_get_id?user_id_type=open_id",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"emails": emails},
        timeout=30,
    )
    data = resp.json()
    if data.get("code") != 0:
        print(f"查询失败: {json.dumps(data, ensure_ascii=False)}", file=sys.stderr)
        return []

    results = []
    for item in data.get("data", {}).get("user_list", []):
        email = item.get("email", "")
        open_id = item.get("user_id", "")
        name = email.split("@")[0] if email else ""
        results.append({"email": email, "open_id": open_id, "name": name})
        print(f"  {email} → {open_id}")

    not_found = data.get("data", {}).get("not_found_list", [])
    if not_found:
        print(f"  未找到: {', '.join(not_found)}")

    return results


def cmd_init(args):
    print("=== gerrit-pipeline 配置初始化 ===\n")

    cfg = load_config() or {}

    # --- Gerrit 配置 ---
    print("【Gerrit 配置】")
    gerrit = cfg.get("gerrit", {})

    user = input(f"Gerrit 用户名 [{gerrit.get('user', '')}]: ").strip()
    if user:
        gerrit["user"] = user
    elif not gerrit.get("user"):
        print("错误: Gerrit 用户名不能为空", file=sys.stderr)
        sys.exit(1)

    pwd = input(f"Gerrit HTTP 密码 [{'*' * 8 if gerrit.get('http_password') else ''}]: ").strip()
    if pwd:
        gerrit["http_password"] = pwd
    elif not gerrit.get("http_password"):
        print("错误: Gerrit HTTP 密码不能为空", file=sys.stderr)
        sys.exit(1)

    reviewers_default = ",".join(gerrit.get("reviewers", []))
    reviewers_input = input(f"Gerrit Reviewers (逗号分隔, 如 reviewer1,reviewer2) [{reviewers_default}]: ").strip()
    if reviewers_input:
        gerrit["reviewers"] = [r.strip() for r in reviewers_input.split(",") if r.strip()]

    cfg["gerrit"] = gerrit

    # --- 飞书配置 ---
    print("\n【飞书配置】")
    feishu = cfg.get("feishu", {})

    chat_id = input(f"飞书群 chat_id [{feishu.get('chat_id', '')}]: ").strip()
    if chat_id:
        feishu["chat_id"] = chat_id
    elif not feishu.get("chat_id"):
        print("错误: chat_id 不能为空", file=sys.stderr)
        sys.exit(1)

    print("\n配置 @mention 成员（输入邮箱，逗号分隔，回车跳过）")
    existing = feishu.get("at_members", [])
    if existing:
        print(f"当前成员: {', '.join(m['name'] for m in existing)}")

    emails_input = input("成员邮箱 (如 user1@company.com,user2@company.com): ").strip()
    if emails_input:
        emails = [e.strip() for e in emails_input.split(",") if e.strip()]
        print("\n正在查询飞书 open_id ...")
        users = lookup_users_by_email(emails)
        if users:
            feishu["at_members"] = [
                {"name": u["name"], "open_id": u["open_id"]}
                for u in users if u["open_id"]
            ]

    cfg["feishu"] = feishu
    save_config(cfg)
    print("\n初始化完成！")


def cmd_show(args):
    cfg = load_config()
    if not cfg:
        print(f"配置文件不存在: {CONFIG_PATH}")
        print("请运行 'python3 pipeline_config.py init' 初始化配置")
        sys.exit(1)

    print(f"配置文件: {CONFIG_PATH}\n")
    print(json.dumps(cfg, ensure_ascii=False, indent=2))


def cmd_lookup(args):
    emails = [e.strip() for e in args.emails.split(",") if e.strip()]
    if not emails:
        print("错误: 请提供至少一个邮箱", file=sys.stderr)
        sys.exit(1)

    print(f"正在查询 {len(emails)} 个用户的 open_id ...\n")
    results = lookup_users_by_email(emails)

    if results and args.save:
        cfg = load_config() or {}
        feishu = cfg.get("feishu", {})
        feishu["at_members"] = [
            {"name": u["name"], "open_id": u["open_id"]}
            for u in results if u["open_id"]
        ]
        cfg["feishu"] = feishu
        save_config(cfg)


def main():
    ap = argparse.ArgumentParser(description="gerrit-pipeline 配置管理")
    sub = ap.add_subparsers(dest="command")

    sub.add_parser("init", help="交互式初始化配置")
    sub.add_parser("show", help="展示当前配置")

    lk = sub.add_parser("lookup-users", help="通过邮箱查询飞书 open_id")
    lk.add_argument("--emails", required=True, help="邮箱列表，逗号分隔")
    lk.add_argument("--save", action="store_true", help="查询结果保存到配置文件")

    args = ap.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "show":
        cmd_show(args)
    elif args.command == "lookup-users":
        cmd_lookup(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
