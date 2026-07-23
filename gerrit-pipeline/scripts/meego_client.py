#!/usr/bin/env python3
"""Resolve Meego work-item links and sync gerrit-pipeline results to Meego."""

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import uuid
from urllib.parse import quote, unquote, urlparse

import requests

CONFIG_PATH = os.path.expanduser("~/.config/gerrit-pipeline/config.json")
DEFAULT_BASE_URL = "https://project.feishu.cn"
BRANDING_PREFIX = "Powered by gerrit-pipeline"
_TOKEN_CACHE = {"token": None, "expire_at": 0}

# Administrators can bake Meego OpenAPI credentials into the distributed skill,
# just like the Feishu bot credentials used by feishu_notify.py.
MEEGO_PLUGIN_ID = "MII_6A602CE12ECD8BD6"
MEEGO_PLUGIN_SECRET = "76EA4EAEDBCA63020F593A35450D616D"
MEEGO_PLUGIN_TOKEN = ""
MEEGO_USER_KEY = "7643489164528307413"
MEEGO_ALLOWED_HOSTS = {"project.feishu.cn"}
MEEGO_PLUGIN_TOKEN_TYPE = 0
MEEGO_AUTH_HELP_URL = "https://project.feishu.cn/b/helpcenter/1p8d7djs/61dmhkek"
MEEGO_DEFAULT_WORK_ITEM_QUERY_PATH = "/open_api/{project_key}/work_item/filter"
MEEGO_DEFAULT_COMMENT_PATH = "/open_api/{project_key}/work_item/{work_item_type_key}/{work_item_id}/comment/create"


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def resolve_project_config(cfg, project_name=None):
    projects = cfg.get("projects", {}) if isinstance(cfg.get("projects", {}), dict) else {}
    if not project_name or project_name not in projects:
        return cfg
    merged = json.loads(json.dumps(cfg))
    project_cfg = projects[project_name]
    merged.pop("projects", None)
    for section in ("gerrit", "feishu"):
        if isinstance(project_cfg.get(section), dict):
            merged.setdefault(section, {}).update(project_cfg[section])
    return merged


def read_version():
    skill_json = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skill.json")
    try:
        with open(skill_json, "r", encoding="utf-8") as f:
            return str(json.load(f).get("version", "")).strip()
    except Exception:
        return "unknown"


def extract_work_item_id(subject):
    match = re.match(r"^【[^】\r\n]+】【([^】\r\n]+)】", str(subject or "").strip())
    return match.group(1).strip() if match else ""


def parse_work_item_url(work_item_url, strict=False):
    raw = str(work_item_url or "").strip()
    if not raw:
        return {}

    parsed = urlparse(raw)
    host = parsed.netloc.lower()
    if parsed.scheme != "https" or host not in MEEGO_ALLOWED_HOSTS:
        if strict:
            raise RuntimeError("invalid Meego work item URL: expected https://project.feishu.cn/...")
        return {}

    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if len(parts) < 4 or parts[2] != "detail" or not parts[0] or not parts[1] or not parts[3]:
        if strict:
            raise RuntimeError("invalid Meego work item URL path: expected /<project_key>/<work_item_type_key>/detail/<work_item_id>")
        return {}

    return {
        "url": raw,
        "base_url": "%s://%s" % (parsed.scheme, parsed.netloc),
        "project_key": parts[0],
        "work_item_type_key": parts[1],
        "work_item_id": parts[3],
    }


def meego_settings(_cfg=None):
    return {
        "base_url": DEFAULT_BASE_URL,
        "project_key": "",
        "work_item_type_key": "",
        "plugin_id": MEEGO_PLUGIN_ID,
        "plugin_secret": MEEGO_PLUGIN_SECRET,
        "plugin_token": MEEGO_PLUGIN_TOKEN,
        "user_key": MEEGO_USER_KEY,
        "work_item_url_template": "",
        "plugin_token_path": "/open_api/authen/plugin_token",
        "work_item_query_path": MEEGO_DEFAULT_WORK_ITEM_QUERY_PATH,
        "comment_path": MEEGO_DEFAULT_COMMENT_PATH,
        "comment_body_field": "content",
    }


def apply_work_item_context(settings, link):
    merged = dict(settings or {})
    if link.get("base_url"):
        merged["base_url"] = str(link["base_url"]).rstrip("/")
    if link.get("project_key"):
        merged["project_key"] = link["project_key"]
    if link.get("work_item_type_key"):
        merged["work_item_type_key"] = link["work_item_type_key"]
    return merged


def path_from_template(settings, template, work_item_id=""):
    return str(template or "").format(
        project_key=quote(settings.get("project_key", ""), safe=""),
        work_item_type_key=quote(settings.get("work_item_type_key", ""), safe=""),
        work_item_id=quote(str(work_item_id), safe=""),
    )


def endpoint_from_template(settings, template, work_item_id=""):
    endpoint = path_from_template(settings, template, work_item_id)
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        return endpoint
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    return settings["base_url"] + endpoint


def _json_post(url, headers=None, payload=None, timeout=30):
    resp = requests.post(url, headers=headers or {}, json=payload or {}, timeout=timeout)
    try:
        data = resp.json()
    except ValueError:
        data = {"raw": resp.text}
    if resp.status_code >= 400:
        raise RuntimeError("Meego API HTTP %s: %s" % (resp.status_code, json.dumps(data, ensure_ascii=False)[:500]))
    nested_error = data.get("error") if isinstance(data.get("error"), dict) else {}
    err_msg = data.get("err_msg") or data.get("msg") or data.get("message") or nested_error.get("msg") or nested_error.get("message") or ""
    code = data.get("err_code", data.get("code", nested_error.get("code", 0)))
    if code not in (0, "0", None, ""):
        raise RuntimeError("Meego API error %s: %s" % (code, err_msg or json.dumps(data, ensure_ascii=False)[:500]))
    return data


def get_plugin_token(settings):
    if settings.get("plugin_token"):
        return settings["plugin_token"]
    if _TOKEN_CACHE["token"] and _TOKEN_CACHE["expire_at"] > time.time() + 60:
        return _TOKEN_CACHE["token"]
    if not settings.get("plugin_id") or not settings.get("plugin_secret"):
        return ""
    data = _json_post(
        endpoint_from_template(settings, settings.get("plugin_token_path") or "/open_api/authen/plugin_token"),
        headers={"Content-Type": "application/json"},
        payload={"plugin_id": settings["plugin_id"], "plugin_secret": settings["plugin_secret"], "type": MEEGO_PLUGIN_TOKEN_TYPE},
    )
    token = (
        data.get("data", {}).get("token")
        or data.get("data", {}).get("plugin_token")
        or data.get("token")
        or ""
    )
    if token:
        _TOKEN_CACHE["token"] = token
        expire_after = data.get("data", {}).get("expire")
        if expire_after in (None, ""):
            expire_after = data.get("data", {}).get("expire_time", 7200)
        _TOKEN_CACHE["expire_at"] = time.time() + int(expire_after)
    return token


def missing_user_key_message():
    return (
        "missing Meego X-USER-KEY: plugin_id/plugin_secret are configured, "
        "but Meego OpenAPI requires a user_key for plugin-token requests. "
        "Ask the skill administrator to update the built-in MEEGO_USER_KEY in scripts/meego_client.py. "
        "Help: %s" % MEEGO_AUTH_HELP_URL
    )


def api_headers(settings, request_id=None, require_user_key=False):
    token = get_plugin_token(settings)
    if not token:
        return {}
    user_key = str(settings.get("user_key") or "").strip()
    if require_user_key and not user_key:
        raise RuntimeError(missing_user_key_message())
    headers = {
        "Content-Type": "application/json",
        "X-PLUGIN-TOKEN": token,
        "X-Plugin-Token": token,
    }
    if user_key:
        headers["X-USER-KEY"] = user_key
        headers["X-User-Key"] = user_key
    if request_id:
        headers["X-PLUGIN-REQUEST-ID"] = request_id
    return headers


def _coerce_work_item_id(value):
    text = str(value or "").strip()
    return int(text) if text.isdigit() else text


def query_work_item(settings, work_item_id, strict=False):
    if not settings.get("project_key") or not settings.get("work_item_type_key"):
        return {}
    if not str(settings.get("user_key") or "").strip():
        if strict:
            raise RuntimeError(missing_user_key_message())
        return {}
    headers = api_headers(settings, require_user_key=True)
    if not headers:
        return {}
    url = endpoint_from_template(settings, settings.get("work_item_query_path") or MEEGO_DEFAULT_WORK_ITEM_QUERY_PATH, work_item_id)
    data = _json_post(
        url,
        headers=headers,
        payload={
            "work_item_type_keys": [settings.get("work_item_type_key", "")],
            "work_item_ids": [_coerce_work_item_id(work_item_id)],
            "page_size": 200,
            "page_num": 1,
        },
    )
    payload = data.get("data", data)
    if isinstance(payload, list):
        return payload[0] if payload else {}
    if isinstance(payload, dict):
        for key in ("work_items", "items", "list", "data"):
            if isinstance(payload.get(key), list) and payload[key]:
                return payload[key][0]
        return payload
    return {}


def build_work_item_url(settings, work_item_id, detail=None):
    detail = detail or {}
    for key in ("url", "web_url", "detail_url", "work_item_url"):
        if detail.get(key):
            return str(detail[key])
    if settings.get("work_item_url_template"):
        return settings["work_item_url_template"].format(
            work_item_id=quote(str(work_item_id), safe=""),
            project_key=quote(settings.get("project_key", ""), safe=""),
            work_item_type_key=quote(settings.get("work_item_type_key", ""), safe=""),
        )
    project_key = str(detail.get("simple_name") or detail.get("project_key") or settings.get("project_key") or "").strip()
    item_type = str(detail.get("work_item_type_key") or settings.get("work_item_type_key") or "").strip()
    if project_key and item_type and work_item_id:
        return "%s/%s/%s/detail/%s" % (
            settings["base_url"],
            quote(project_key, safe=""),
            quote(item_type, safe=""),
            quote(str(work_item_id), safe=""),
        )
    return ""


def resolve_work_item_link(subject="", work_item_id="", work_item_url="", cfg=None, project_name=None, strict=False):
    cfg = resolve_project_config(cfg if cfg is not None else load_config(), project_name)
    settings = meego_settings(cfg)
    parsed_url = parse_work_item_url(work_item_url, strict=(strict or bool(str(work_item_url or "").strip())))
    if parsed_url:
        settings = apply_work_item_context(settings, parsed_url)

    item_id = str(parsed_url.get("work_item_id") or work_item_id or extract_work_item_id(subject)).strip()
    if not item_id:
        if strict:
            raise RuntimeError("missing Meego work item id")
        return {"id": "", "url": "", "source": "missing", "detail": {}, "project_key": "", "work_item_type_key": "", "base_url": ""}
    detail = {}
    try:
        detail = query_work_item(settings, item_id, strict=strict)
    except Exception:
        if strict:
            raise
    url = parsed_url.get("url") or build_work_item_url(settings, item_id, detail)
    source = "input_url" if parsed_url else ("api" if detail else "id")
    return {
        "id": item_id,
        "url": url,
        "source": source,
        "detail": detail,
        "project_key": settings.get("project_key", ""),
        "work_item_type_key": settings.get("work_item_type_key", ""),
        "base_url": settings.get("base_url", ""),
    }


def format_markdown_link(item_id, url):
    if not item_id:
        return ""
    text = str(item_id).replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
    return "[%s](%s)" % (text, url) if url else text


def format_cr_links(cr_value, url_value):
    cr_list = [item.strip() for item in str(cr_value or "").split(",") if item.strip()]
    url_list = [item.strip() for item in str(url_value or "").split(",") if item.strip()]
    if not cr_list:
        return ""
    if len(cr_list) == 1:
        return format_markdown_link(cr_list[0], url_list[0] if url_list else "")
    lines = []
    for index, cr in enumerate(cr_list):
        url = url_list[index] if index < len(url_list) else ""
        lines.append("  - %s" % format_markdown_link(cr, url))
    return "\n" + "\n".join(lines)


def checklist_text(status):
    return {"pass": "通过", "warn": "部分待确认", "fail": "未通过"}.get(str(status or ""), str(status or ""))


def build_sync_comment(args, link):
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cr_links = format_cr_links(args.cr, args.url)
    lines = [
        "### Gerrit Pipeline 同步",
        "",
        "- CR:%s" % ((" " + cr_links) if "\n" not in cr_links else cr_links),
        "- 提交标题: %s" % args.subject,
        "- 分支: %s" % args.branch,
        "- 评审评分: %s" % args.score,
        "- 问题统计: P0=%s P1=%s P2=%s P3=%s" % (args.p0, args.p1, args.p2, args.p3),
        "- Checklist: %s" % checklist_text(args.checklist),
    ]
    if args.topic:
        lines.append("- Topic: %s" % args.topic)
    if args.repos:
        lines.append("- Repos: %s" % args.repos)
    lines.append("- 同步时间: %s" % now)
    body = "\n".join(lines).rstrip()
    return f"{body}\n\n---\n\n{BRANDING_PREFIX} v{read_version()}\nSync ID: gerrit-pipeline:{link.get('id', '')}:{str(args.cr).replace(',', '_')}\n"


def post_comment(settings, work_item_id, comment, request_id=None):
    if not str(work_item_id or "").strip():
        raise RuntimeError("missing Meego work item id")
    if not settings.get("project_key") or not settings.get("work_item_type_key"):
        raise RuntimeError("missing meego.project_key or meego.work_item_type_key")
    headers = api_headers(settings, request_id=request_id, require_user_key=True)
    if not headers:
        raise RuntimeError("missing Meego plugin token or plugin credentials")
    url = endpoint_from_template(settings, settings.get("comment_path") or MEEGO_DEFAULT_COMMENT_PATH, work_item_id)
    body = {
        settings.get("comment_body_field") or "content": comment,
    }
    return _json_post(url, headers=headers, payload=body)


def cmd_resolve_link(args):
    link = resolve_work_item_link(
        args.subject,
        args.work_item_id,
        args.work_item_url,
        project_name=args.project,
        strict=args.strict,
    )
    print(json.dumps({
        "work_item_id": link["id"],
        "url": link["url"],
        "project_key": link.get("project_key", ""),
        "work_item_type_key": link.get("work_item_type_key", ""),
        "source": link["source"],
    }, ensure_ascii=False, indent=2))
    return 0 if link["id"] else 1


def cmd_sync(args):
    cfg = resolve_project_config(load_config(), args.project)
    link = resolve_work_item_link(args.subject, args.work_item_id, args.work_item_url, cfg=cfg, strict=args.strict)
    if not link.get("id"):
        print("错误: 缺少 Meego 工作项 URL 或兼容工作项 ID，无法执行 Step 5 同步", file=sys.stderr)
        return 1
    if args.comment_file:
        with open(args.comment_file, "r", encoding="utf-8") as f:
            comment = f.read()
    elif args.comment_text:
        comment = args.comment_text
    else:
        comment = build_sync_comment(args, link)
    if args.dry:
        print("=== Meego sync preview ===")
        print("Work Item: %s" % format_markdown_link(link.get("id"), link.get("url")))
        print(comment)
        return 0
    settings = apply_work_item_context(meego_settings(cfg), link)
    request_id = args.request_id or str(uuid.uuid5(uuid.NAMESPACE_URL, "gerrit-pipeline:%s:%s" % (link.get("id"), args.cr)))
    post_comment(settings, link["id"], comment, request_id=request_id)
    print("Meego 工作项已同步: %s" % format_markdown_link(link.get("id"), link.get("url")))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description="Meego helper for gerrit-pipeline")
    sub = parser.add_subparsers(dest="command")

    resolve = sub.add_parser("resolve-link", help="Resolve Meego work item link")
    resolve.add_argument("--subject", default="", help="commit subject containing Meego work item id")
    resolve.add_argument("--work-item-id", default="", help="Meego work item id, kept for compatibility")
    resolve.add_argument("--work-item-url", default="", help="Meego work item URL (preferred)")
    resolve.add_argument("--project", default=None, help="project config name")
    resolve.add_argument("--strict", action="store_true", help="fail on API/config errors")

    sync = sub.add_parser("sync", help="Step 5: sync pipeline result to Meego comment")
    sync.add_argument("--subject", required=True, help="commit subject")
    sync.add_argument("--work-item-id", default="", help="Meego work item id, kept for compatibility")
    sync.add_argument("--work-item-url", default="", help="Meego work item URL (preferred)")
    sync.add_argument("--project", default=None, help="project config name")
    sync.add_argument("--cr", required=True, help="CR number, comma separated for topic")
    sync.add_argument("--url", required=True, help="Gerrit URL, comma separated for topic")
    sync.add_argument("--branch", default="", help="target branch")
    sync.add_argument("--topic", default="", help="Gerrit topic")
    sync.add_argument("--repos", default="", help="repo list")
    sync.add_argument("--score", default="1", help="review score")
    sync.add_argument("--p0", default="0")
    sync.add_argument("--p1", default="0")
    sync.add_argument("--p2", default="0")
    sync.add_argument("--p3", default="0")
    sync.add_argument("--checklist", default="pass", choices=["pass", "warn", "fail"])
    sync.add_argument("--comment-file", default="", help="custom comment file")
    sync.add_argument("--comment-text", default="", help="custom comment text")
    sync.add_argument("--request-id", default="", help="idempotency request id")
    sync.add_argument("--strict", action="store_true", help="fail on resolve errors")
    sync.add_argument("--dry", action="store_true", help="preview only")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "resolve-link":
        return cmd_resolve_link(args)
    if args.command == "sync":
        return cmd_sync(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
