"""feishu_notify.py — 发送 Gerrit Pipeline 通知到飞书群。

用法：
  # 单仓库提交
  python3 feishu_notify.py --cr 1003659 --url "https://..." --branch al_dev \
      --subject "【feature】..." --score 1 --p0 0 --p1 0 --p2 0 --p3 1 \
      --checklist pass

  # 多仓库关联提交
  python3 feishu_notify.py --topic D01_FWK_20250428 \
      --cr 1003659,1003660,1003661 \
      --url "https://url1,https://url2,https://url3" \
      --repos "frameworks/base,packages/apps/Settings,vendor/autolink/sdk_release" \
      --branch al_dev --subject "【feature】..." \
      --score 1 --p0 0 --p1 0 --p2 0 --p3 1 --checklist pass

  python3 feishu_notify.py --dry ...   # 仅预览，不实际发送

配置文件：~/.config/gerrit-pipeline/config.json（由 pipeline_config.py init 生成）
"""
import os, sys, json, time, argparse, datetime, re
import requests
from pipeline_config import resolve_config

BASE_URL = "https://open.feishu.cn/open-apis"
CONFIG_PATH = os.path.expanduser("~/.config/gerrit-pipeline/config.json")


def _read_version():
    readme = os.path.join(os.path.dirname(__file__), "..", "README.md")
    try:
        with open(readme, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"\*\*版本：v([\d.]+)\*\*", line.strip())
                if m:
                    return m.group(1)
    except OSError:
        pass
    return "unknown"


__version__ = _read_version()

_token_cache = {"token": None, "expire_at": 0}

FEISHU_APP_ID = "cli_a97aeb96793a9bc1"
FEISHU_APP_SECRET = "01ArKkBCEZsBDks8v227YeSpVGoIpax4"


def get_tenant_token():
    now = time.time()
    if _token_cache["token"] and _token_cache["expire_at"] > now + 60:
        return _token_cache["token"]

    resp = requests.post(
        f"{BASE_URL}/auth/v3/tenant_access_token/internal",
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


def send_message(chat_id, msg_type, content):
    token = get_tenant_token()
    resp = requests.post(
        f"{BASE_URL}/im/v1/messages?receive_id_type=chat_id",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        json={
            "receive_id": chat_id,
            "msg_type": msg_type,
            "content": content,
        },
        timeout=30,
    )
    data = resp.json()
    if data.get("code") != 0:
        print(f"发送失败: {json.dumps(data, ensure_ascii=False)}", file=sys.stderr)
        return False, data
    return True, data


def _score_text(score):
    if score >= 1:
        return "✅ +1 (LGTM)"
    elif score == 0:
        return "⚠️ 0 (有风险项)"
    else:
        return "❌ -1 (需修改)"


def _checklist_text(status):
    m = {"pass": "✅ 通过", "warn": "⚠️ 部分待确认", "fail": "❌ 未通过"}
    return m.get(status, status)


def _build_at_text(at_members):
    if not at_members:
        return ""
    parts = []
    for m in at_members:
        open_id = m.get("open_id", "")
        name = m.get("name", "")
        if open_id:
            parts.append(f"<at id={open_id}></at>")
        elif name:
            parts.append(f"@{name}")
    return " ".join(parts)


def _escape_link_text(text):
    """Escape Markdown link label syntax while keeping rendered text unchanged."""
    return str(text).replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _md_link(text, url):
    return f"[{_escape_link_text(text)}]({url})"


def build_card(args, at_members=None, submitter=None):
    if args.topic:
        return build_topic_card(args, at_members=at_members, submitter=submitter)
    return build_single_card(args, at_members=at_members, submitter=submitter)


def build_single_card(args, at_members=None, submitter=None):
    score_display = _score_text(args.score)
    checklist_display = _checklist_text(args.checklist)
    issues = f"P0={args.p0}  P1={args.p1}  P2={args.p2}  P3={args.p3}"
    submit_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    header_color = "green"
    if args.score < 0 or args.p0 > 0:
        header_color = "red"
    elif args.score == 0 or args.p1 > 0:
        header_color = "orange"

    submitter_text = ""
    if submitter:
        open_id = submitter.get("open_id", "")
        name = submitter.get("name", "")
        if open_id:
            submitter_text = f"<at id={open_id}></at>"
        elif name:
            submitter_text = name

    elements = [
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**提交概要**\n{_md_link(args.subject, args.url)}"},
        },
        {
            "tag": "div",
            "fields": [
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**CR 编号**\n[{args.cr}]({args.url})"}},
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**分支**\n{args.branch}"}},
            ],
        },
        {
            "tag": "div",
            "fields": [
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**提交人**\n{submitter_text}" if submitter_text else "**提交人**\n-"}},
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**提交日期**\n{submit_time}"}},
            ],
        },
        {
            "tag": "div",
            "fields": [
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**评审评分**\n{score_display}"}},
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**问题统计**\n{issues}"}},
            ],
        },
        {
            "tag": "div",
            "fields": [
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**Checklist**\n{checklist_display}"}},
            ],
        },
    ]

    at_text = _build_at_text(at_members)
    if at_text:
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**审核人**\n{at_text}"},
        })
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": "⏰ 请审核人于当日 24:00 前完成 Code Review 及 Merge，谢谢！"},
        })

    elements.append({"tag": "hr"})
    elements.append({
        "tag": "note",
        "elements": [
            {"tag": "plain_text", "content": f"由 Gerrit Pipeline v{__version__} 自动发送"},
        ],
    })

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "Gerrit Pipeline 通知"},
            "template": header_color,
        },
        "elements": elements,
    }
    return json.dumps(card, ensure_ascii=False)


def build_topic_card(args, at_members=None, submitter=None):
    score_display = _score_text(args.score)
    checklist_display = _checklist_text(args.checklist)
    issues = f"P0={args.p0}  P1={args.p1}  P2={args.p2}  P3={args.p3}"
    submit_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    header_color = "green"
    if args.score < 0 or args.p0 > 0:
        header_color = "red"
    elif args.score == 0 or args.p1 > 0:
        header_color = "orange"

    submitter_text = ""
    if submitter:
        open_id = submitter.get("open_id", "")
        name = submitter.get("name", "")
        if open_id:
            submitter_text = f"<at id={open_id}></at>"
        elif name:
            submitter_text = name

    cr_list = [c.strip() for c in args.cr.split(",")]
    url_list = [u.strip() for u in args.url.split(",")]
    repo_list = [r.strip() for r in args.repos.split(",")] if args.repos else [f"repo{i+1}" for i in range(len(cr_list))]

    cr_lines = []
    for i in range(len(cr_list)):
        cr = cr_list[i]
        url = url_list[i] if i < len(url_list) else ""
        repo = repo_list[i] if i < len(repo_list) else ""
        cr_lines.append(f"- **{repo}**: [{cr}]({url})")
    cr_text = "\n".join(cr_lines)

    topic_url = f"https://gerrit.auto-link.com.cn/q/topic:{args.topic}"

    elements = [
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**提交概要**\n{_md_link(args.subject, topic_url)}"},
        },
        {
            "tag": "div",
            "fields": [
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**Topic**\n[{args.topic}]({topic_url})"}},
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**分支**\n{args.branch}"}},
            ],
        },
        {
            "tag": "div",
            "fields": [
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**提交人**\n{submitter_text}" if submitter_text else "**提交人**\n-"}},
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**提交日期**\n{submit_time}"}},
            ],
        },
        {
            "tag": "div",
            "fields": [
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**评审评分**\n{score_display}"}},
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**问题统计**\n{issues}"}},
            ],
        },
        {
            "tag": "div",
            "fields": [
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**Checklist**\n{checklist_display}"}},
            ],
        },
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**关联 CR 列表**\n{cr_text}"},
        },
    ]

    at_text = _build_at_text(at_members)
    if at_text:
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**审核人**\n{at_text}"},
        })
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": "⏰ 请审核人于当日 24:00 前完成 Code Review 及 Merge，谢谢！"},
        })

    elements.append({"tag": "hr"})
    elements.append({
        "tag": "note",
        "elements": [
            {"tag": "plain_text", "content": f"由 Gerrit Pipeline v{__version__} 自动发送"},
        ],
    })

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "Gerrit Pipeline 通知 — 关联提交"},
            "template": header_color,
        },
        "elements": elements,
    }
    return json.dumps(card, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser(description="发送 Gerrit Pipeline 通知到飞书群")
    ap.add_argument("--cr", required=True, help="CR 编号（多仓库时逗号分隔）")
    ap.add_argument("--url", required=True, help="Gerrit Change URL（多仓库时逗号分隔）")
    ap.add_argument("--branch", default="al_dev", help="目标分支")
    ap.add_argument("--subject", required=True, help="提交标题，必须与 commit message 第一行完全一致")
    ap.add_argument("--topic", default=None, help="Topic 名称（多仓库关联提交时必填）")
    ap.add_argument("--repos", default=None, help="各 CR 对应仓库名，逗号分隔（多仓库时必填，与 --cr 一一对应）")
    ap.add_argument("--score", type=int, default=1, help="评审评分 (-1/0/1)")
    ap.add_argument("--p0", type=int, default=0, help="P0 问题数")
    ap.add_argument("--p1", type=int, default=0, help="P1 问题数")
    ap.add_argument("--p2", type=int, default=0, help="P2 问题数")
    ap.add_argument("--p3", type=int, default=0, help="P3 问题数")
    ap.add_argument("--checklist", default="pass", choices=["pass", "warn", "fail"], help="Checklist 状态")
    ap.add_argument("--project", default=None, help="项目名称（如 D01、BAIC），用于匹配项目专属配置")
    ap.add_argument("--chat-id", default=None, help="飞书群 chat_id（覆盖配置文件）")
    ap.add_argument("--dry", action="store_true", help="仅预览，不实际发送")
    args = ap.parse_args()

    cfg, matched_project = resolve_config(args.project)
    if not cfg:
        print(f"错误: 配置文件不存在: {CONFIG_PATH}", file=sys.stderr)
        print("请先运行: python3 pipeline_config.py init", file=sys.stderr)
        sys.exit(1)

    if matched_project:
        print(f"匹配项目配置: {matched_project}")

    feishu_cfg = cfg.get("feishu", {})
    chat_id = args.chat_id or feishu_cfg.get("chat_id")
    if not chat_id:
        print("错误: 未配置飞书群 chat_id", file=sys.stderr)
        sys.exit(1)

    at_members = feishu_cfg.get("at_members", [])
    submitter = feishu_cfg.get("submitter")

    card_content = build_card(args, at_members=at_members, submitter=submitter)

    print("=== 消息预览 ===")
    print(json.dumps(json.loads(card_content), ensure_ascii=False, indent=2))

    if args.dry:
        print("\n[DRY RUN] 未实际发送")
        return

    ok, data = send_message(chat_id, "interactive", card_content)
    if ok:
        print(f"\n发送成功: message_id={data.get('data', {}).get('message_id', 'N/A')}")
    else:
        print(f"\n发送失败", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
