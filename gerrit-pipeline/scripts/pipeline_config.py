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

FEISHU_APP_ID = "cli_a97aeb96793a9bc1"
FEISHU_APP_SECRET = "01ArKkBCEZsBDks8v227YeSpVGoIpax4"


def _get_tenant_token():
    now = time.time()
    if _token_cache["token"] and _token_cache["expire_at"] > now + 60:
        return _token_cache["token"]

    resp = requests.post(
        f"{FEISHU_BASE_URL}/auth/v3/tenant_access_token/internal",
        json={
            "app_id": FEISHU_APP_ID,
            "app_secret": FEISHU_APP_SECRET,
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


def resolve_config(project_name=None):
    """根据项目名称返回合并后的配置。

    在 projects 中精确匹配 project_name，用其值覆盖顶层配置。
    未匹配或无 projects 时返回顶层配置（向后兼容）。
    返回 (merged_cfg, matched_project_name)。
    """
    cfg = load_config() or {}
    projects = cfg.get("projects", {})

    if not project_name or project_name not in projects:
        return cfg, None

    proj = projects[project_name]
    merged = json.loads(json.dumps(cfg))
    merged.pop("projects", None)

    if "gerrit" in proj:
        for k, v in proj["gerrit"].items():
            merged.setdefault("gerrit", {})[k] = v
    if "feishu" in proj:
        for k, v in proj["feishu"].items():
            merged.setdefault("feishu", {})[k] = v
    return merged, project_name


def list_project_names():
    """返回所有已配置的项目名称列表。"""
    cfg = load_config() or {}
    return list(cfg.get("projects", {}).keys())


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


def cmd_add_project(args):
    cfg = load_config() or {}
    projects = cfg.setdefault("projects", {})
    proj = projects.setdefault(args.name, {})

    if args.reviewers:
        proj.setdefault("gerrit", {})["reviewers"] = [
            r.strip() for r in args.reviewers.split(",") if r.strip()
        ]

    if args.chat_id:
        proj.setdefault("feishu", {})["chat_id"] = args.chat_id

    if args.at_emails:
        emails = [e.strip() for e in args.at_emails.split(",") if e.strip()]
        print(f"\n正在查询 {len(emails)} 个用户的 open_id ...")
        users = lookup_users_by_email(emails)
        if users:
            proj.setdefault("feishu", {})["at_members"] = [
                {"name": u["name"], "open_id": u["open_id"]}
                for u in users if u["open_id"]
            ]

    cfg["projects"] = projects
    save_config(cfg)
    print(f"\n项目 '{args.name}' 配置已保存")


def cmd_list_projects(args):
    cfg = load_config() or {}
    projects = cfg.get("projects", {})
    if not projects:
        print("未配置任何项目。使用 'add-project' 添加项目配置。")
        return

    print(f"共 {len(projects)} 个项目配置：\n")
    for name, proj in projects.items():
        print(f"  📁 {name}")
        g = proj.get("gerrit", {})
        f = proj.get("feishu", {})
        if g.get("reviewers"):
            print(f"     Reviewers: {', '.join(g['reviewers'])}")
        if f.get("chat_id"):
            print(f"     chat_id:   {f['chat_id']}")
        if f.get("at_members"):
            names = [m.get("name", "?") for m in f["at_members"]]
            print(f"     @members:  {', '.join(names)}")
        print()


def cmd_remove_project(args):
    cfg = load_config() or {}
    projects = cfg.get("projects", {})
    if args.name not in projects:
        print(f"项目 '{args.name}' 不存在", file=sys.stderr)
        sys.exit(1)
    del projects[args.name]
    cfg["projects"] = projects
    save_config(cfg)
    print(f"项目 '{args.name}' 已删除")


def main():
    ap = argparse.ArgumentParser(description="gerrit-pipeline 配置管理")
    sub = ap.add_subparsers(dest="command")

    sub.add_parser("init", help="交互式初始化配置")
    sub.add_parser("show", help="展示当前配置")

    lk = sub.add_parser("lookup-users", help="通过邮箱查询飞书 open_id")
    lk.add_argument("--emails", required=True, help="邮箱列表，逗号分隔")
    lk.add_argument("--save", action="store_true", help="查询结果保存到配置文件")

    ap_add = sub.add_parser("add-project", help="添加或更新项目配置")
    ap_add.add_argument("--name", required=True, help="项目名称（如 D01、BAIC）")
    ap_add.add_argument("--chat-id", default=None, help="飞书群 chat_id")
    ap_add.add_argument("--reviewers", default=None, help="Gerrit Reviewers，逗号分隔")
    ap_add.add_argument("--at-emails", default=None, help="@mention 成员邮箱，逗号分隔")

    sub.add_parser("list-projects", help="列出所有项目配置")

    ap_rm = sub.add_parser("remove-project", help="删除项目配置")
    ap_rm.add_argument("--name", required=True, help="项目名称")

    args = ap.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "show":
        cmd_show(args)
    elif args.command == "lookup-users":
        cmd_lookup(args)
    elif args.command == "add-project":
        cmd_add_project(args)
    elif args.command == "list-projects":
        cmd_list_projects(args)
    elif args.command == "remove-project":
        cmd_remove_project(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
