#!/usr/bin/env python3
"""飞书开放平台 API 客户端工具

用法:
    python3 feishu_client.py token                                     # 获取 tenant_access_token
    python3 feishu_client.py doc-info <document_id>                    # 获取文档信息
    python3 feishu_client.py doc-text <document_id>                    # 获取文档纯文本
    python3 feishu_client.py doc-blocks <document_id>                  # 获取文档所有块
    python3 feishu_client.py doc-create --title "标题" [--folder TOKEN] [--collaborator EMAIL] # 创建文档
    python3 feishu_client.py doc-append <document_id> --text "内容"     # 追加文本块
    python3 feishu_client.py doc-export <document_id> --format markdown [--output file.md]
    python3 feishu_client.py doc-fit-tables <document_id>              # 自适应表格宽度（默认页宽）
    python3 feishu_client.py doc-fit-tables <document_id> --width 1033 # 指定目标宽度
    python3 feishu_client.py doc-beautify <document_id>               # 一键美化文档
    python3 feishu_client.py board-nodes <whiteboard_id>               # 获取画板节点
    python3 feishu_client.py board-create-node <whiteboard_id> --type text_shape --content '{...}'
    python3 feishu_client.py board-create-nodes <whiteboard_id> --nodes '[{...}, ...]'
    python3 feishu_client.py board-create-nodes <whiteboard_id> --file nodes.json
    python3 feishu_client.py board-create-mindmap <whiteboard_id> --file tree.json
    python3 feishu_client.py board-theme <whiteboard_id>               # 获取画板主题
    python3 feishu_client.py folder-list <folder_token>                # 列出文件夹内容
    python3 feishu_client.py wiki-node <wiki_token>                    # 获取知识库节点信息
    python3 feishu_client.py doc-permission <token> --link-share tenant_editable  # 设置链接分享权限
    python3 feishu_client.py doc-add-collaborator <token> --member-type email --member-id user@company.com  # 添加协作者
    python3 feishu_client.py doc-import <document_id> --file local.md  # 导入 Markdown（自动美化）
    python3 feishu_client.py doc-import <document_id> --file local.md --no-beautify  # 仅导入
    python3 feishu_client.py wiki-move-to <space_id> --obj-token TOKEN --obj-type docx [--parent WIKI_TOKEN]  # 移动文档到知识空间
    python3 feishu_client.py doc-delete <file_token> [--type docx]                     # 删除云空间文档（移入回收站）

环境变量:
    FEISHU_APP_ID       飞书应用 App ID
    FEISHU_APP_SECRET   飞书应用 App Secret
"""

import argparse
import json
import os
import sys
import time
import unicodedata
from pathlib import Path

import requests

BASE_URL = "https://open.feishu.cn/open-apis"

_token_cache = {"token": None, "expire_at": 0}


def get_env(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        print(f"错误: 环境变量 {key} 未设置", file=sys.stderr)
        sys.exit(1)
    return val


def get_tenant_token() -> str:
    now = time.time()
    if _token_cache["token"] and _token_cache["expire_at"] > now + 60:
        return _token_cache["token"]

    resp = requests.post(
        f"{BASE_URL}/auth/v3/tenant_access_token/internal",
        json={
            "app_id": get_env("FEISHU_APP_ID"),
            "app_secret": get_env("FEISHU_APP_SECRET"),
        },
    )
    data = resp.json()
    if data.get("code") != 0:
        print(f"获取 token 失败: {json.dumps(data, ensure_ascii=False)}", file=sys.stderr)
        sys.exit(1)

    _token_cache["token"] = data["tenant_access_token"]
    _token_cache["expire_at"] = now + data.get("expire", 7200)
    return _token_cache["token"]


_API_TIMEOUT = 60
_API_MAX_RETRIES = 5


def _request_with_retry(do_request):
    """Retry on transient network errors (long imports hit many API calls)."""
    last_exc: Exception | None = None
    for attempt in range(_API_MAX_RETRIES):
        try:
            return do_request()
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.ChunkedEncodingError,
        ) as e:
            last_exc = e
            time.sleep(1.5 * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def api_get(path: str, params: dict | None = None) -> dict:
    token = get_tenant_token()

    def do():
        return requests.get(
            f"{BASE_URL}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params or {},
            timeout=_API_TIMEOUT,
        )

    resp = _request_with_retry(do)
    return resp.json()


def api_post(path: str, body: dict | None = None) -> dict:
    token = get_tenant_token()

    def do():
        return requests.post(
            f"{BASE_URL}{path}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=body or {},
            timeout=_API_TIMEOUT,
        )

    resp = _request_with_retry(do)
    return resp.json()


def api_patch(path: str, body: dict | None = None, params: dict | None = None) -> dict:
    token = get_tenant_token()

    def do():
        return requests.patch(
            f"{BASE_URL}{path}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=body or {},
            params=params or {},
            timeout=_API_TIMEOUT,
        )

    resp = _request_with_retry(do)
    return resp.json()


def api_delete(path: str, body: dict | None = None) -> dict:
    token = get_tenant_token()

    def do():
        return requests.delete(
            f"{BASE_URL}{path}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=body or {},
            timeout=_API_TIMEOUT,
        )

    resp = _request_with_retry(do)
    return resp.json()


def api_put(path: str, body: dict | None = None, params: dict | None = None) -> dict:
    token = get_tenant_token()

    def do():
        return requests.put(
            f"{BASE_URL}{path}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=body or {},
            params=params or {},
            timeout=_API_TIMEOUT,
        )

    resp = _request_with_retry(do)
    return resp.json()


def pp(data: dict):
    print(json.dumps(data, ensure_ascii=False, indent=2))


# ── Document commands ──────────────────────────────────────────────

def cmd_token(_args):
    token = get_tenant_token()
    print(token)


def cmd_doc_info(args):
    pp(api_get(f"/docx/v1/documents/{args.document_id}"))


def cmd_doc_text(args):
    data = api_get(f"/docx/v1/documents/{args.document_id}/raw_content")
    if data.get("code") == 0:
        print(data.get("data", {}).get("content", ""))
    else:
        pp(data)


def cmd_doc_blocks(args):
    all_blocks = []
    page_token = None
    while True:
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        data = api_get(f"/docx/v1/documents/{args.document_id}/blocks", params)
        if data.get("code") != 0:
            pp(data)
            return
        items = data.get("data", {}).get("items", [])
        all_blocks.extend(items)
        page_token = data.get("data", {}).get("page_token")
        if not data.get("data", {}).get("has_more"):
            break
    pp({"blocks": all_blocks, "total": len(all_blocks)})


def _set_permission_public(token: str, doc_type: str = "docx",
                            link_share: str = "tenant_readable") -> dict:
    """Set document public sharing permissions via v2 API (incremental update)."""
    return api_patch(
        f"/drive/v2/permissions/{token}/public",
        body={"link_share_entity": link_share},
        params={"type": doc_type},
    )


def _add_collaborator(token: str, member_type: str, member_id: str,
                      perm: str = "full_access", doc_type: str = "docx") -> dict:
    """Add a collaborator to a cloud document."""
    return api_post(
        f"/drive/v1/permissions/{token}/members?type={doc_type}&need_notification=false",
        body={
            "member_type": member_type,
            "member_id": member_id,
            "perm": perm,
            "type": "user",
        },
    )


def _get_gitconfig_email() -> str | None:
    """Read user.email from ~/.gitconfig (INI format, [user] section)."""
    gitconfig = Path.home() / ".gitconfig"
    if not gitconfig.exists():
        return None
    try:
        import configparser
        cfg = configparser.ConfigParser()
        cfg.read(str(gitconfig), encoding="utf-8")
        return cfg.get("user", "email", fallback=None)
    except Exception:
        return None


def cmd_doc_create(args):
    body = {"title": args.title}
    if args.folder:
        body["folder_token"] = args.folder
    result = api_post("/docx/v1/documents", body)
    pp(result)

    if result.get("code") == 0 and not args.no_permission:
        doc_id = result["data"]["document"]["document_id"]
        perm_resp = _set_permission_public(doc_id, "docx", args.link_share)
        if perm_resp.get("code") == 0:
            print(f"\n权限已设置: link_share_entity={args.link_share}")
        else:
            print(f"\n权限设置失败: {json.dumps(perm_resp, ensure_ascii=False)}", file=sys.stderr)

        if not args.no_collaborator:
            email = args.collaborator or _get_gitconfig_email()
            if email:
                collab_resp = _add_collaborator(doc_id, "email", email, "full_access", "docx")
                if collab_resp.get("code") == 0:
                    print(f"协作者已添加: email={email}")
                else:
                    print(f"协作者添加失败: {json.dumps(collab_resp, ensure_ascii=False)}", file=sys.stderr)
            else:
                print("提示: 未找到协作者邮箱（~/.gitconfig 中无 user.email），跳过自动添加协作者。"
                      "可通过 --collaborator <email> 手动指定。", file=sys.stderr)


def cmd_doc_append(args):
    elements = []
    if args.text:
        elements.append({"text_run": {"content": args.text}})
    elif args.markdown:
        elements.append({"text_run": {"content": args.markdown}})
    else:
        print("错误: 需要 --text 或 --markdown 参数", file=sys.stderr)
        sys.exit(1)

    block_id = args.document_id
    body = {
        "children": [
            {
                "block_type": 2,
                "text": {"elements": elements},
            }
        ],
        "index": -1,
    }
    pp(api_post(f"/docx/v1/documents/{args.document_id}/blocks/{block_id}/children", body))


BLOCK_TYPE_MAP = {
    1: "page", 2: "text", 3: "h1", 4: "h2", 5: "h3",
    6: "h4", 7: "h5", 8: "h6", 9: "h7", 10: "h8", 11: "h9",
    12: "bullet", 13: "ordered", 14: "code", 15: "quote",
    17: "todo", 22: "divider", 27: "image",
    30: "callout", 31: "grid", 32: "grid_column", 43: "board",
}


def _block_to_markdown(block: dict) -> str:
    bt = block.get("block_type", 0)
    type_name = BLOCK_TYPE_MAP.get(bt, f"unknown({bt})")

    def extract_text(block_data: dict) -> str:
        elements = block_data.get("elements", [])
        parts = []
        for el in elements:
            tr = el.get("text_run", {})
            parts.append(tr.get("content", ""))
        return "".join(parts)

    if type_name == "text":
        return extract_text(block.get("text", {}))
    elif type_name.startswith("h"):
        level = int(type_name[1:])
        return "#" * level + " " + extract_text(block.get(f"heading{level}", block.get("text", {})))
    elif type_name == "bullet":
        return "- " + extract_text(block.get("bullet", block.get("text", {})))
    elif type_name == "ordered":
        return "1. " + extract_text(block.get("ordered", block.get("text", {})))
    elif type_name == "code":
        co = block.get("code", block.get("text", {}))
        text = extract_text(co)
        lang = co.get("language")
        if lang is None or lang == "":
            lang = co.get("style", {}).get("language", "")
        return f"```{lang}\n{text}\n```"
    elif type_name == "quote":
        return "> " + extract_text(block.get("quote", block.get("text", {})))
    elif type_name == "todo":
        done = block.get("todo", {}).get("done", False)
        check = "x" if done else " "
        return f"- [{check}] " + extract_text(block.get("todo", block.get("text", {})))
    elif type_name == "divider":
        return "---"
    elif type_name == "board":
        token = block.get("board", {}).get("token", block.get("block_id", ""))
        return f"[画板: {token}]"
    elif type_name == "image":
        token = block.get("image", {}).get("token", "")
        return f"![image]({token})"
    return ""


def cmd_doc_export(args):
    fmt = args.format
    if fmt == "text":
        data = api_get(f"/docx/v1/documents/{args.document_id}/raw_content")
        if data.get("code") != 0:
            pp(data)
            return
        content = data.get("data", {}).get("content", "")
    elif fmt == "markdown":
        all_blocks = []
        page_token = None
        while True:
            params = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            data = api_get(f"/docx/v1/documents/{args.document_id}/blocks", params)
            if data.get("code") != 0:
                pp(data)
                return
            items = data.get("data", {}).get("items", [])
            all_blocks.extend(items)
            page_token = data.get("data", {}).get("page_token")
            if not data.get("data", {}).get("has_more"):
                break

        doc_info = api_get(f"/docx/v1/documents/{args.document_id}")
        title = doc_info.get("data", {}).get("document", {}).get("title", "Untitled")
        lines = [f"# {title}", ""]
        for block in all_blocks:
            if block.get("block_type") == 1:
                continue
            line = _block_to_markdown(block)
            if line:
                lines.append(line)
                lines.append("")
        content = "\n".join(lines)
    else:
        print(f"不支持的格式: {fmt}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        Path(args.output).write_text(content, encoding="utf-8")
        print(f"已导出到 {args.output}")
    else:
        print(content)


# ── Table fitting ─────────────────────────────────────────────────

# Feishu page content area widths (px) derived from reverse-engineering the
# web editor's padding formula: https://juejin.cn/post/7438115774501797914
# For window width > 964px the content area is constant at ~833px (Default).
# "Wide" adds 200px (content ~1033px); "Full" fills the viewport.
FEISHU_PAGE_WIDTHS = {"default": 833, "wide": 1033}
_TABLE_CELL_PADDING = 18
_MIN_COL_WIDTH = 50


def _estimate_text_width(text: str) -> int:
    """Estimate rendered pixel width.  CJK chars ~14px, others ~8px."""
    w = 0
    for ch in text:
        if ch == "\n":
            continue
        w += 14 if unicodedata.east_asian_width(ch) in ("W", "F") else 8
    return w


def _get_block_text(block: dict) -> str:
    for key in ("text", "heading1", "heading2", "heading3", "heading4",
                "heading5", "heading6", "heading7", "heading8", "heading9",
                "bullet", "ordered", "todo", "code"):
        section = block.get(key)
        if section and "elements" in section:
            parts = []
            for elem in section["elements"]:
                parts.append(elem.get("text_run", {}).get("content", ""))
                parts.append(elem.get("mention_doc", {}).get("title", ""))
            return "".join(parts)
    return ""


def _cell_max_line_width(blocks_map: dict, cell_id: str) -> int:
    cell = blocks_map.get(cell_id)
    if not cell:
        return 0
    max_w = 0
    for child_id in cell.get("children", []):
        child = blocks_map.get(child_id)
        if not child:
            continue
        for line in _get_block_text(child).split("\n"):
            line = line.strip()
            if line:
                max_w = max(max_w, _estimate_text_width(line))
    return max_w


def _get_all_blocks(doc_id: str) -> list[dict]:
    all_blocks = []
    page_token = None
    while True:
        params: dict = {"page_size": 500, "document_revision_id": -1}
        if page_token:
            params["page_token"] = page_token
        data = api_get(f"/docx/v1/documents/{doc_id}/blocks", params)
        if data.get("code") != 0:
            print(f"ERROR: {json.dumps(data, ensure_ascii=False)}", file=sys.stderr)
            sys.exit(1)
        items = data.get("data", {}).get("items", [])
        all_blocks.extend(items)
        if not data.get("data", {}).get("has_more", False):
            break
        page_token = data.get("data", {}).get("page_token")
    return all_blocks


def cmd_doc_fit_tables(args):
    """Auto-fit all table column widths in a document to fill the page width.

    Two phases:
    1. Analyse cell text to compute optimal per-column proportions.
    2. Scale so the total equals target_width and PATCH each column.
    """
    target = args.width
    doc_id = args.document_id

    print(f"目标页面宽度: {target}px")
    blocks = _get_all_blocks(doc_id)
    blocks_map = {b["block_id"]: b for b in blocks}
    tables = [b for b in blocks if b.get("block_type") == 31]
    print(f"文档共 {len(blocks)} 个块，其中 {len(tables)} 个表格\n")

    for t_idx, table in enumerate(tables):
        table_id = table["block_id"]
        prop = table.get("table", {}).get("property", {})
        col_size = prop.get("column_size", 0)
        row_size = prop.get("row_size", 0)
        old_widths = prop.get("column_width", [])
        cells = table.get("table", {}).get("cells", [])
        merge_info = prop.get("merge_info", [])

        if col_size == 0:
            continue

        # Phase 1: measure content width per column
        col_max = [0] * col_size
        for row in range(row_size):
            for col in range(col_size):
                idx = row * col_size + col
                if idx >= len(cells):
                    continue
                mi = merge_info[idx] if idx < len(merge_info) else {}
                if mi.get("col_span", 1) > 1:
                    continue
                w = _cell_max_line_width(blocks_map, cells[idx]) + _TABLE_CELL_PADDING
                col_max[col] = max(col_max[col], w)

        for i in range(col_size):
            col_max[i] = max(col_max[i], _MIN_COL_WIDTH)

        total_needed = sum(col_max)
        if total_needed == 0:
            continue

        # Phase 2: scale to target
        if total_needed <= target:
            scale = target / total_needed
            new_widths = [int(w * scale) for w in col_max]
        else:
            new_widths = [max(_MIN_COL_WIDTH, int(w * target / total_needed)) for w in col_max]

        diff = target - sum(new_widths)
        if diff and new_widths:
            new_widths[new_widths.index(max(new_widths))] += diff

        changed = new_widths != old_widths[:col_size]
        if not changed:
            print(f"[{t_idx+1}] {table_id}: 无需变更")
            continue

        print(f"[{t_idx+1}] {table_id}: {old_widths} → {new_widths} (sum={sum(new_widths)})")
        for ci in range(col_size):
            if ci < len(old_widths) and old_widths[ci] == new_widths[ci]:
                continue
            resp = api_patch(
                f"/docx/v1/documents/{doc_id}/blocks/{table_id}",
                body={"update_table_property": {"column_width": new_widths[ci], "column_index": ci}},
                params={"document_revision_id": -1},
            )
            if resp.get("code") != 0:
                print(f"  col {ci} 失败: {resp}", file=sys.stderr)
            time.sleep(0.25)

    print(f"\n完成: {len(tables)} 个表格已调整至 {target}px 总宽度")


# ── Document beautify ─────────────────────────────────────────────

def _extract_code_text(block: dict) -> str:
    elements = block.get("code", {}).get("elements", [])
    return "".join(e.get("text_run", {}).get("content", "") for e in elements)


def _is_plantuml(block: dict) -> bool:
    if block.get("block_type") != 14:
        return False
    return _extract_code_text(block).strip().startswith("@start")


def _clean_plantuml(code: str) -> str:
    # 飞书 style_type=1 对 left to right direction 报 syntax error（约第 3 行），导致回退经典样式
    lines = [
        ln
        for ln in code.split("\n")
        if "skinparam componentStyle" not in ln
        and ln.strip().lower() != "left to right direction"
    ]
    result = "\n".join(lines)
    stripped = result.strip()
    if not any(stripped.endswith(tag) for tag in ("@enduml", "@endgantt", "@endmindmap")):
        start_tag = stripped.split("\n")[0].replace("@start", "@end")
        result = result.rstrip() + "\n" + start_tag + "\n"
    return result


def _delete_doc_root_child_by_block_id(doc_id: str, block_id: str) -> bool:
    """在文档根下按 block_id 删除一个子块（每次调用前会重新拉取 children 索引）。"""
    fresh_root = api_get(f"/docx/v1/documents/{doc_id}/blocks/{doc_id}")
    fresh_children = fresh_root.get("data", {}).get("block", {}).get("children", [])
    if block_id not in fresh_children:
        return False
    idx = fresh_children.index(block_id)
    resp = api_delete(
        f"/docx/v1/documents/{doc_id}/blocks/{doc_id}/children/batch_delete",
        {"start_index": idx, "end_index": idx + 1},
    )
    time.sleep(0.25)
    return resp.get("code") == 0


def _beautify_plantuml(doc_id: str, blocks: list[dict]) -> int:
    """Convert PlantUML code blocks → whiteboards, then delete originals. Returns count."""
    import re as _re

    puml_blocks = [(b["block_id"], _extract_code_text(b)) for b in blocks if _is_plantuml(b)]
    if not puml_blocks:
        return 0

    print(f"  发现 {len(puml_blocks)} 个 PlantUML 代码块")

    # Get root children order
    root = next((b for b in blocks if b["block_id"] == doc_id), None)
    children = root["children"] if root else []

    converted = 0
    code_ids_imported: list[str] = []
    board_ids_empty: list[str] = []
    for bid, code in puml_blocks:
        cleaned = _clean_plantuml(code)

        # Refresh children order (changes after each insertion)
        fresh_root = api_get(f"/docx/v1/documents/{doc_id}/blocks/{doc_id}")
        fresh_children = fresh_root.get("data", {}).get("block", {}).get("children", [])
        try:
            insert_idx = fresh_children.index(bid) + 1
        except ValueError:
            continue

        # Create whiteboard block after the code block
        resp = api_post(f"/docx/v1/documents/{doc_id}/blocks/{doc_id}/children", {
            "children": [{"block_type": 43, "board": {"align": 2, "width": 1200, "height": 800}}],
            "index": insert_idx,
        })
        if resp.get("code") != 0:
            print(f"    创建画板失败 ({bid}): {resp}", file=sys.stderr)
            continue
        child0 = resp["data"]["children"][0]
        board_block_id = child0.get("block_id")
        wb_id = child0["board"]["token"]

        # Import PlantUML：优先 style_type=1（画板原生节点）；失败时仅对活动图再试 diagram_type=3
        # （纯 rectangle/组件图误用 type=3 可能变成极少节点的异常结果）；最后回退 style_type=2。
        import_resp = api_post(f"/board/v1/whiteboards/{wb_id}/nodes/plantuml", {
            "plant_uml_code": cleaned,
            "syntax_type": 1, "style_type": 1, "diagram_type": 0,
        })
        looks_activity = (
            _re.search(r"(?m)^\s*start\s*$", cleaned)
            and (
                _re.search(r"\bif\s*\(", cleaned)
                or _re.search(r"(?m)^\s*:\s*[^;]+;", cleaned)
            )
        )
        if import_resp.get("code") != 0 and looks_activity:
            import_resp = api_post(f"/board/v1/whiteboards/{wb_id}/nodes/plantuml", {
                "plant_uml_code": cleaned,
                "syntax_type": 1, "style_type": 1, "diagram_type": 3,
            })
        if import_resp.get("code") != 0:
            # Fallback to classic style for gantt/complex diagrams
            import_resp = api_post(f"/board/v1/whiteboards/{wb_id}/nodes/plantuml", {
                "plant_uml_code": cleaned,
                "syntax_type": 1, "style_type": 2, "diagram_type": 0,
            })
        if import_resp.get("code") == 0:
            converted += 1
            code_ids_imported.append(bid)
            first_line = cleaned.strip().split("\n")[0]
            print(f"    导入成功: {first_line}")
        else:
            print(f"    导入失败 ({bid}): {import_resp}", file=sys.stderr)
            if board_block_id:
                board_ids_empty.append(board_block_id)
        time.sleep(0.3)

    # 导入失败时移除空画板，保留源码代码块；仅导入成功时删除源码块
    time.sleep(0.5)
    removed_boards = 0
    for bbid in board_ids_empty:
        if _delete_doc_root_child_by_block_id(doc_id, bbid):
            removed_boards += 1
    if removed_boards:
        print(f"  已移除 {removed_boards} 个导入失败的空画板（已保留对应 PlantUML 源码块）")

    deleted_codes = 0
    for cid in code_ids_imported:
        if _delete_doc_root_child_by_block_id(doc_id, cid):
            deleted_codes += 1
    print(f"  已删除 {deleted_codes} 个已成功转画板的原始代码块")
    return converted


def _compute_fit_widths(col_max: list[int], target_width: int) -> list[int]:
    """把每列原始内容宽度按比例缩放到 target_width，最小列宽 _MIN_COL_WIDTH。
    docx Table 与 Sheet 块共用此算法。"""
    col_count = len(col_max)
    col_max = [max(w, _MIN_COL_WIDTH) for w in col_max]
    total_needed = sum(col_max)
    if total_needed <= 0:
        return [max(_MIN_COL_WIDTH, target_width // max(1, col_count))] * col_count
    if total_needed <= target_width:
        scale = target_width / total_needed
        widths = [int(w * scale) for w in col_max]
    else:
        widths = [max(_MIN_COL_WIDTH, int(w * target_width / total_needed)) for w in col_max]
    diff = target_width - sum(widths)
    if diff and widths:
        widths[widths.index(max(widths))] += diff
    return widths


def _sheet_get_all_values(spreadsheet_token: str, sheet_id: str) -> list[list[str]]:
    """读取 Sheet 工作表全量数据。先用 v3 元数据拿 grid 行列数，再用 v2 GET values。"""
    meta = api_get(f"/sheets/v3/spreadsheets/{spreadsheet_token}/sheets/{sheet_id}")
    g = meta.get("data", {}).get("sheet", {}).get("grid_properties", {}) or {}
    rows_n = int(g.get("row_count") or 0)
    cols_n = int(g.get("column_count") or 0)
    if rows_n <= 0 or cols_n <= 0:
        return []
    rng = f"{sheet_id}!A1:{_col_index_to_letter(cols_n)}{rows_n}"
    r = api_get(f"/sheets/v2/spreadsheets/{spreadsheet_token}/values/{rng}")
    raw = r.get("data", {}).get("valueRange", {}).get("values", []) or []
    out: list[list[str]] = []
    for row in raw:
        out.append(["" if c is None else str(c) for c in row])
    return out


def _beautify_sheet_block(spreadsheet_token: str, sheet_id: str,
                          rows: list[list[str]], target_width: int) -> None:
    """Sheet 块美化：列宽自适应（按内容缩放到 target_width）+ 表头加粗。

    - 列宽：sheets 端用 `PUT dimension_range` 单段连续列设同一 fixedSize；
      合并相邻同宽列减少调用次数。
    - 加粗：`PUT styles_batch_update` 单次给整行设 font.bold=true。
    sheets API 限频 100 次/秒，无需大间隔。"""
    if not rows:
        return
    col_count = max((len(r) for r in rows), default=0)
    if col_count <= 0:
        return

    col_max = [0] * col_count
    for row in rows:
        for ci, cell in enumerate(row):
            if ci >= col_count:
                continue
            for line in (cell or "").split("\n"):
                w = _estimate_text_width(line.strip()) + _TABLE_CELL_PADDING
                if w > col_max[ci]:
                    col_max[ci] = w
    new_widths = _compute_fit_widths(col_max, target_width)

    i = 0
    while i < col_count:
        j = i
        while j + 1 < col_count and new_widths[j + 1] == new_widths[i]:
            j += 1
        api_put(
            f"/sheets/v2/spreadsheets/{spreadsheet_token}/dimension_range",
            body={
                "dimension": {
                    "sheetId": sheet_id, "majorDimension": "COLUMNS",
                    "startIndex": i + 1, "endIndex": j + 1,
                },
                "dimensionProperties": {"fixedSize": new_widths[i]},
            },
        )
        i = j + 1

    end_col = _col_index_to_letter(col_count)
    api_put(
        f"/sheets/v2/spreadsheets/{spreadsheet_token}/styles_batch_update",
        body={"data": [{
            "ranges": [f"{sheet_id}!A1:{end_col}1"],
            "style": {"font": {"bold": True}},
        }]},
    )


def _beautify_tables(doc_id: str, target_width: int):
    """Fit table widths + set header_row + bold header text.
    同步处理 docx Table（block_type=31）与 Sheet 块（block_type=30）。"""
    blocks = _get_all_blocks(doc_id)
    blocks_map = {b["block_id"]: b for b in blocks}
    tables = [b for b in blocks if b.get("block_type") == 31]
    sheet_blocks = [b for b in blocks if b.get("block_type") == 30]
    if not tables and not sheet_blocks:
        return

    if sheet_blocks:
        print(f"  发现 {len(tables)} 个文档表格 + {len(sheet_blocks)} 个 Sheet 表格")
    else:
        print(f"  发现 {len(tables)} 个表格")

    for t_idx, table in enumerate(tables):
        table_id = table["block_id"]
        prop = table.get("table", {}).get("property", {})
        col_size = prop.get("column_size", 0)
        row_size = prop.get("row_size", 0)
        old_widths = prop.get("column_width", [])
        cells = table.get("table", {}).get("cells", [])
        merge_info = prop.get("merge_info", [])

        if col_size == 0:
            continue

        # --- Column width fitting ---
        col_max = [0] * col_size
        for row in range(row_size):
            for col in range(col_size):
                idx = row * col_size + col
                if idx >= len(cells):
                    continue
                mi = merge_info[idx] if idx < len(merge_info) else {}
                if mi.get("col_span", 1) > 1:
                    continue
                w = _cell_max_line_width(blocks_map, cells[idx]) + _TABLE_CELL_PADDING
                col_max[col] = max(col_max[col], w)

        for i in range(col_size):
            col_max[i] = max(col_max[i], _MIN_COL_WIDTH)

        total_needed = sum(col_max)
        if total_needed > 0:
            if total_needed <= target_width:
                scale = target_width / total_needed
                new_widths = [int(w * scale) for w in col_max]
            else:
                new_widths = [max(_MIN_COL_WIDTH, int(w * target_width / total_needed)) for w in col_max]
            diff = target_width - sum(new_widths)
            if diff and new_widths:
                new_widths[new_widths.index(max(new_widths))] += diff

            if new_widths != old_widths[:col_size]:
                for ci in range(col_size):
                    if ci < len(old_widths) and old_widths[ci] == new_widths[ci]:
                        continue
                    api_patch(
                        f"/docx/v1/documents/{doc_id}/blocks/{table_id}",
                        body={"update_table_property": {"column_width": new_widths[ci], "column_index": ci}},
                        params={"document_revision_id": -1},
                    )
                    time.sleep(0.25)

        # --- Set header_row ---
        if not prop.get("header_row"):
            api_patch(
                f"/docx/v1/documents/{doc_id}/blocks/{table_id}",
                body={"update_table_property": {"header_row": True}},
                params={"document_revision_id": -1},
            )
            time.sleep(0.25)

        # --- Bold header cell text ---
        header_cells = cells[:col_size]
        for cell_id in header_cells:
            cell_block = blocks_map.get(cell_id)
            if not cell_block:
                continue
            for child_id in cell_block.get("children", []):
                child = blocks_map.get(child_id)
                if not child:
                    continue
                for key in ("text", "heading1", "heading2", "heading3", "heading4",
                            "heading5", "heading6", "heading7", "heading8", "heading9",
                            "bullet", "ordered"):
                    section = child.get(key)
                    if not section or "elements" not in section:
                        continue
                    new_elements = []
                    needs_update = False
                    for elem in section["elements"]:
                        tr = elem.get("text_run")
                        if tr:
                            style = dict(tr.get("text_element_style", {}))
                            if not style.get("bold"):
                                style["bold"] = True
                                needs_update = True
                            new_elements.append({"text_run": {"content": tr["content"], "text_element_style": style}})
                        else:
                            new_elements.append(elem)
                    if needs_update:
                        api_patch(
                            f"/docx/v1/documents/{doc_id}/blocks/{child_id}",
                            body={"update_text_elements": {"elements": new_elements}},
                            params={"document_revision_id": -1},
                        )
                        time.sleep(0.25)
                    break

    for sb in sheet_blocks:
        full_token = (sb.get("sheet") or {}).get("token", "")
        if "_" not in full_token:
            continue
        spreadsheet_token, sheet_id = full_token.split("_", 1)
        sheet_rows = _sheet_get_all_values(spreadsheet_token, sheet_id)
        if not sheet_rows:
            continue
        _beautify_sheet_block(spreadsheet_token, sheet_id, sheet_rows, target_width)

    print(f"  表格美化完成: 列宽自适应 + 表头高亮 + 文字加粗")


# ── Markdown import ────────────────────────────────────────────────

_MD_LANG_MAP = {
    "plaintext": 1, "text": 1, "": 1,
    "abap": 2, "ada": 3, "apache": 4, "apex": 5, "assembly": 6, "asm": 6,
    "bash": 7, "shell": 7, "sh": 7, "zsh": 7,
    "csharp": 8, "cs": 8,
    "cpp": 9, "c++": 9,
    "c": 10,
    "cobol": 11,
    "css": 12,
    "coffeescript": 13, "coffee": 13,
    "d": 14, "dart": 15, "delphi": 16, "django": 17,
    "dockerfile": 18, "docker": 18,
    "erlang": 19, "fortran": 20, "foxpro": 21,
    "go": 22, "golang": 22,
    "groovy": 23,
    "html": 24, "htmlbars": 25, "http": 26,
    "haskell": 27,
    "json": 28,
    "java": 29,
    "javascript": 30, "js": 30,
    "julia": 31, "kotlin": 32, "kt": 32,
    "latex": 33, "tex": 33,
    "lisp": 34, "logo": 35, "lua": 36,
    "matlab": 37,
    "makefile": 38, "make": 38,
    "markdown": 39, "md": 39,
    "nginx": 40, "objective-c": 41, "objc": 41,
    "openedgeabl": 42,
    "php": 43, "perl": 44,
    "postscript": 45, "powershell": 46, "ps1": 46,
    "prolog": 47, "protobuf": 48, "proto": 48,
    "python": 49, "py": 49,
    "r": 50, "rpg": 51,
    "ruby": 52, "rb": 52,
    "rust": 53, "rs": 53,
    "sas": 54, "scss": 55,
    "sql": 56,
    "scala": 57, "scheme": 58, "scratch": 59,
    "plantuml": 60,
    "swift": 61,
    "thrift": 62,
    "typescript": 63, "ts": 63,
    "vbscript": 64, "vb": 64,
    "visual basic": 65,
    "xml": 66, "svg": 66,
    "yaml": 67, "yml": 67,
    "cmake": 68, "diff": 69, "gherkin": 70,
    "graphql": 71, "gql": 71,
    "glsl": 72,
    "properties": 73, "ini": 73,
    "solidity": 74, "sol": 74,
    "toml": 75,
}


def _log(msg: str, *, err: bool = False):
    print(msg, file=sys.stderr if err else sys.stdout, flush=True)


def _mk_inline_only(text: str, *, parse_inline: bool = True) -> list[dict]:
    """仅处理 ``**bold**`` / `` `code` ``，不解析 Markdown 链接。"""
    if not text:
        return []
    if not parse_inline or ("**" not in text and "`" not in text):
        return [{"text_run": {"content": text}}]

    import re as _re

    elements: list[dict] = []
    for seg in _re.split(r"(\*\*.+?\*\*|`[^`]+`)", text):
        if not seg:
            continue
        if seg.startswith("**") and seg.endswith("**"):
            elements.append({
                "text_run": {
                    "content": seg[2:-2],
                    "text_element_style": {"bold": True},
                }
            })
        elif seg.startswith("`") and seg.endswith("`"):
            elements.append({
                "text_run": {
                    "content": seg[1:-1],
                    "text_element_style": {"inline_code": True},
                }
            })
        else:
            elements.append({"text_run": {"content": seg}})
    return elements or [{"text_run": {"content": text}}]


def _sanitize_text_elements(elements: list[dict]) -> list[dict]:
    """避免空 content 触发飞书 1770001。"""
    out: list[dict] = []
    for e in elements:
        tr = e.get("text_run")
        if tr and tr.get("content", "") == "":
            tr["content"] = " "
        out.append(e)
    return out if out else [{"text_run": {"content": " "}}]


def _mk_text_elements(text: str, *, parse_inline: bool = True) -> list[dict]:
    """Build text_run elements from a string.

    - Markdown ``[显示名](https://url)`` -> ``text_element_style.link.url``
    - ``**bold**`` / `` `code` `` 由 `_mk_inline_only` 处理
    """
    import re as _re

    if not text:
        return [{"text_run": {"content": " "}}]

    # 代码块等场景不解析 Markdown 链接；否则 C++ lambda [](...) 中的 ](
    # 可能被误识别为链接片段，进而触发飞书 1770006 schema mismatch。
    if not parse_inline:
        return _sanitize_text_elements(_mk_inline_only(text, parse_inline=False))

    if "[" not in text or "](" not in text:
        return _sanitize_text_elements(_mk_inline_only(text, parse_inline=parse_inline))

    elements: list[dict] = []
    pos = 0
    link_re = _re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
    for m in link_re.finditer(text):
        before = text[pos:m.start()]
        if before:
            elements.extend(_mk_inline_only(before, parse_inline=parse_inline))
        inner, url = m.group(1), m.group(2).strip()
        if not url:
            elements.extend(_mk_inline_only(m.group(0), parse_inline=parse_inline))
        elif not url.startswith(("http://", "https://")):
            # 飞书 text_element_style.link.url 仅接受合法 URL；#锚点/相对路径会返回 1770006
            elements.extend(_mk_inline_only(inner, parse_inline=parse_inline))
        else:
            inner_els = _mk_inline_only(inner, parse_inline=parse_inline)
            if not inner_els:
                inner_els = [{"text_run": {"content": " "}}]
            for el in inner_els:
                tr = el.get("text_run", {})
                style = dict(tr.get("text_element_style") or {})
                style["link"] = {"url": url}
                tr["text_element_style"] = style
            elements.extend(inner_els)
        pos = m.end()

    tail = text[pos:]
    if tail:
        elements.extend(_mk_inline_only(tail, parse_inline=parse_inline))

    return _sanitize_text_elements(elements if elements else [{"text_run": {"content": text}}])


def _parse_markdown(content: str) -> list[dict]:
    """Parse markdown into a list of action dicts for block creation."""
    import re as _re

    lines = content.split("\n")
    actions: list[dict] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Code block（首行语言：\S* 可匹配 c++ 等；language 须写入 code.style.language 见 _do_import_markdown）
        if line.strip().startswith("```"):
            lang_m = _re.match(r"^```\s*(\S*)", line.strip())
            lang = (lang_m.group(1) if lang_m else "").strip()
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1
            lang_key = lang.lower()
            actions.append({
                "type": "code",
                "text": "\n".join(code_lines),
                "lang": _MD_LANG_MAP.get(lang_key, 1),
            })
            continue

        # Heading
        m = _re.match(r"^(#{1,6})\s+(.+)$", line)
        if m:
            actions.append({"type": "heading", "level": len(m.group(1)), "text": m.group(2).strip()})
            i += 1
            continue

        # Divider
        if _re.match(r"^---+\s*$", line.strip()):
            actions.append({"type": "divider"})
            i += 1
            continue

        # Blockquote
        if line.startswith("> "):
            quote_lines: list[str] = []
            while i < len(lines) and lines[i].startswith("> "):
                quote_lines.append(lines[i][2:])
                i += 1
            actions.append({"type": "quote", "text": "\n".join(quote_lines)})
            continue

        # Table (require separator line after header)
        if "|" in line and i + 1 < len(lines) and _re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
            table_rows: list[list[str]] = []
            while i < len(lines) and "|" in lines[i]:
                stripped = lines[i].strip()
                if _re.match(r"^\|[\s:|-]+\|$", stripped):
                    i += 1
                    continue
                cells = [c.strip() for c in stripped.strip("|").split("|")]
                table_rows.append(cells)
                i += 1
            actions.append({"type": "table", "rows": table_rows})
            continue

        # Todo / Checkbox (must precede bullet to avoid `- [ ] x` matching as bullet)
        m = _re.match(r"^[-*+]\s+\[([ xX])\]\s+(.+)$", line)
        if m:
            done = m.group(1).lower() == "x"
            actions.append({"type": "todo", "text": m.group(2), "done": done})
            i += 1
            continue

        # Unordered list
        m = _re.match(r"^[-*+]\s+(.+)$", line)
        if m:
            actions.append({"type": "bullet", "text": m.group(1)})
            i += 1
            continue

        # Ordered list
        m = _re.match(r"^\d+[.)]\s+(.+)$", line)
        if m:
            actions.append({"type": "ordered", "text": m.group(1)})
            i += 1
            continue

        # Empty line
        if not line.strip():
            i += 1
            continue

        # Plain text
        actions.append({"type": "text", "text": line})
        i += 1

    return actions


def _import_append_blocks(doc_id: str, parent_id: str, children: list[dict], index: int = -1) -> dict:
    """创建子块；失败重试 3 次后抛错，避免静默丢块。"""
    last: dict | None = None
    for attempt in range(3):
        time.sleep(0.25 if attempt == 0 else 0.35 * (2 ** attempt))
        r = api_post(
            f"/docx/v1/documents/{doc_id}/blocks/{parent_id}/children",
            {"children": children, "index": index},
        )
        last = r
        if r.get("code") == 0:
            return r
        _log(
            f"  ⚠ 块创建失败 (第 {attempt + 1}/3 次): {r.get('msg', '')} (code={r.get('code')})",
            err=True,
        )
    raise RuntimeError(f"飞书块创建失败（已重试 3 次）: {last!r}")


_MAX_FEISHU_TABLE_ROWS = 9            # 文档 Table 块创建端硬上限：row_size>9 报 1770001 invalid param
_SHEET_TABLE_THRESHOLD = 50           # Markdown 表格行数 > 此值时改用 Sheet 块嵌入（亚秒级写入）


def _col_index_to_letter(n: int) -> str:
    """1->A, 26->Z, 27->AA。用于拼接 sheets 的 A1 表示法。"""
    s = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        s = chr(65 + rem) + s
    return s


def _fill_table_cells(doc_id: str, table_id: str, rows: list[list[str]]):
    """向已创建好的 Table 块逐 cell 写入内容；首行加粗作为表头。"""
    col_count = max(len(r) for r in rows) if rows else 1

    # Wait for the table's auto-created cell blocks to be indexed
    time.sleep(0.5)
    table_info = api_get(f"/docx/v1/documents/{doc_id}/blocks/{table_id}")
    cell_ids = table_info.get("data", {}).get("block", {}).get("table", {}).get("cells", [])

    # Batch-fetch all blocks to find existing text blocks inside cells
    all_blocks = _get_all_blocks(doc_id)
    blocks_map = {b["block_id"]: b for b in all_blocks}

    for row_idx, row_data in enumerate(rows):
        for col_idx, cell_text in enumerate(row_data):
            cell_index = row_idx * col_count + col_idx
            if cell_index >= len(cell_ids):
                break
            cell_id = cell_ids[cell_index]
            cell_block = blocks_map.get(cell_id, {})
            children_ids = cell_block.get("children", [])

            if row_idx == 0:
                elements = _mk_text_elements(cell_text)
                for e in elements:
                    tr = e.get("text_run", {})
                    style = dict(tr.get("text_element_style") or {})
                    style["bold"] = True
                    tr["text_element_style"] = style
            else:
                elements = _mk_text_elements(cell_text)

            if children_ids:
                child_id = children_ids[0]
                time.sleep(0.25)
                api_patch(
                    f"/docx/v1/documents/{doc_id}/blocks/{child_id}",
                    body={"update_text_elements": {"elements": elements}},
                    params={"document_revision_id": -1},
                )
            else:
                # Cell's child not in batch result; fetch individually
                time.sleep(0.25)
                cell_detail = api_get(f"/docx/v1/documents/{doc_id}/blocks/{cell_id}")
                detail_children = cell_detail.get("data", {}).get("block", {}).get("children", [])
                if detail_children:
                    time.sleep(0.25)
                    api_patch(
                        f"/docx/v1/documents/{doc_id}/blocks/{detail_children[0]}",
                        body={"update_text_elements": {"elements": elements}},
                        params={"document_revision_id": -1},
                    )
                else:
                    block = {"block_type": 2, "text": {"elements": elements}}
                    _import_append_blocks(doc_id, cell_id, [block])


def _import_create_table_once(doc_id: str, parent_id: str, rows: list[list[str]]):
    """创建单张表（行数 ≤ _MAX_FEISHU_TABLE_ROWS）并填充内容。"""
    row_count = len(rows)
    col_count = max(len(r) for r in rows) if rows else 1

    r = _import_append_blocks(doc_id, parent_id, [{
        "block_type": 31,
        "table": {"property": {"row_size": row_count, "column_size": col_count}},
    }])
    table_id = r["data"]["children"][0]["block_id"]
    _fill_table_cells(doc_id, table_id, rows)


def _import_create_table_full(doc_id: str, parent_id: str, rows: list[list[str]]):
    """创建一张完整的表（不拆分），行数任意。

    飞书创建端 row_size 硬上限 9（超出返回 1770001 invalid param），
    超出部分通过 PATCH `insert_table_row` 子请求在表末逐行扩容。
    文档级编辑限频 3 次/秒（见 docx-v1 patch 文档），保留 ~0.4s 间隔规避 429。
    """
    row_count = len(rows)
    col_count = max(len(r) for r in rows) if rows else 1
    initial = min(row_count, _MAX_FEISHU_TABLE_ROWS)

    r = _import_append_blocks(doc_id, parent_id, [{
        "block_type": 31,
        "table": {"property": {"row_size": initial, "column_size": col_count}},
    }])
    table_id = r["data"]["children"][0]["block_id"]

    extra = row_count - initial
    if extra > 0:
        _log(f"    扩容 {initial} → {row_count} 行 (insert_table_row × {extra})")
        for _ in range(extra):
            time.sleep(0.4)
            api_patch(
                f"/docx/v1/documents/{doc_id}/blocks/{table_id}",
                body={"insert_table_row": {"row_index": -1}},
                params={"document_revision_id": -1},
            )

    _fill_table_cells(doc_id, table_id, rows)


def _import_create_sheet_block(doc_id: str, parent_id: str, rows: list[list[str]]) -> None:
    """以 Sheet 块（电子表格嵌入）形式承载大表，单次批量写入数据。

    docx Table 受文档级 3 次/秒编辑限频，逐 cell PATCH 在大表场景下耗时随行数线性放大；
    Sheet 块走 sheets API（100 次/秒），且 values_batch_update 写入会自动扩 grid，
    单次请求即可完成 N×M 数据写入。"""
    col_count = max(len(r) for r in rows) if rows else 1
    row_count = len(rows)

    initial_rows = max(1, min(row_count, _MAX_FEISHU_TABLE_ROWS))
    initial_cols = max(1, min(col_count, _MAX_FEISHU_TABLE_ROWS))
    r = _import_append_blocks(doc_id, parent_id, [{
        "block_type": 30,
        "sheet": {"row_size": initial_rows, "column_size": initial_cols},
    }])
    full_token = r["data"]["children"][0]["sheet"]["token"]
    spreadsheet_token, sheet_id = full_token.split("_", 1)

    end_col = _col_index_to_letter(col_count)
    rng = f"{sheet_id}!A1:{end_col}{row_count}"
    api_post(
        f"/sheets/v2/spreadsheets/{spreadsheet_token}/values_batch_update",
        body={"valueRanges": [{"range": rng, "values": rows}]},
    )


def _import_create_table(doc_id: str, parent_id: str, rows: list[list[str]],
                         sheet_threshold: int = _SHEET_TABLE_THRESHOLD) -> None:
    """根据行数选择最优实现，整张表绝不拆分。

    - 行数 ≤ _MAX_FEISHU_TABLE_ROWS（9）：直接创建 row_size=N 的文档表格
    - 9 < 行数 ≤ sheet_threshold：单表 + insert_table_row 扩容到目标行数
    - 行数 > sheet_threshold（且 sheet_threshold > 0）：改用 Sheet 块电子表格嵌入

    sheet_threshold=0 表示禁用 Sheet 回退（无论多大都用文档 Table 扩容路径）。"""
    row_count = len(rows)
    if row_count <= _MAX_FEISHU_TABLE_ROWS:
        _import_create_table_once(doc_id, parent_id, rows)
        return
    if sheet_threshold > 0 and row_count > sheet_threshold:
        _log(f"    > {sheet_threshold} 行 → 改用 Sheet 块电子表格嵌入")
        _import_create_sheet_block(doc_id, parent_id, rows)
        return
    _import_create_table_full(doc_id, parent_id, rows)


def _do_import_markdown(doc_id: str, md_path: str, beautify: bool = True, width: int = 833,
                        append: bool = False, sheet_threshold: int = _SHEET_TABLE_THRESHOLD):
    """Core import logic: parse markdown, create blocks, optionally beautify."""
    # Safety: verify the document is empty before importing (skip check in append mode)
    page_blocks = _get_all_blocks(doc_id)
    page_block = next((b for b in page_blocks if b.get("block_type") == 1), None)
    if not append and page_block and len(page_block.get("children", [])) > 0:
        _log("⚠ 文档非空，跳过导入以防重复。如需重新导入请先创建新文档；如需追加内容请使用 --append。", err=True)
        return
    if append and page_block and len(page_block.get("children", [])) > 0:
        _log("ℹ 追加模式：将在现有内容末尾追加导入。")

    content = Path(md_path).read_text(encoding="utf-8")
    actions = _parse_markdown(content)
    total = len(actions)
    _log(f"解析得到 {total} 个内容块，开始导入...\n")

    for idx, action in enumerate(actions):
        atype = action["type"]
        tag = f"  [{idx + 1}/{total}]"

        if atype == "heading":
            level = action["level"]
            text = action["text"]
            if level == 1:
                _log(f"{tag} H1 作为文档标题，跳过（避免与页顶标题重复）")
                continue
            bt = 2 + level
            key = f"heading{level}"
            _import_append_blocks(doc_id, doc_id, [{"block_type": bt, key: {"elements": _mk_text_elements(text)}}])
            _log(f"{tag} H{level}: {text}")

        elif atype == "text":
            _import_append_blocks(doc_id, doc_id, [{"block_type": 2, "text": {"elements": _mk_text_elements(action["text"])}}])
            t = action["text"]
            _log(f'{tag} 文本: {t[:50]}{"..." if len(t) > 50 else ""}')

        elif atype == "bullet":
            _import_append_blocks(doc_id, doc_id, [{"block_type": 12, "bullet": {"elements": _mk_text_elements(action["text"])}}])
            t = action["text"]
            _log(f'{tag} 列表: {t[:50]}{"..." if len(t) > 50 else ""}')

        elif atype == "ordered":
            _import_append_blocks(doc_id, doc_id, [{"block_type": 13, "ordered": {"elements": _mk_text_elements(action["text"])}}])
            t = action["text"]
            _log(f'{tag} 有序: {t[:50]}{"..." if len(t) > 50 else ""}')

        elif atype == "todo":
            _import_append_blocks(doc_id, doc_id, [{
                "block_type": 17,
                "todo": {
                    "elements": _mk_text_elements(action["text"]),
                    "style": {"done": action["done"]},
                },
            }])
            t = action["text"]
            mark = "\u2611" if action["done"] else "\u2610"
            _log(f'{tag} \u5f85\u529e: {mark} {t[:50]}{"..." if len(t) > 50 else ""}')

        elif atype == "code":
            # 飞书要求语言写在 Text.style.language，写在 code.language 会被忽略 → 界面恒为 Plain Text
            _import_append_blocks(doc_id, doc_id, [{
                "block_type": 14,
                "code": {
                    "elements": _mk_text_elements(action["text"], parse_inline=False),
                    "style": {"language": action["lang"]},
                },
            }])
            _log(f"{tag} 代码块 ({len(action['text'])} 字符)")

        elif atype == "divider":
            _import_append_blocks(doc_id, doc_id, [{"block_type": 22, "divider": {}}])
            _log(f"{tag} 分割线")

        elif atype == "quote":
            _import_append_blocks(doc_id, doc_id, [{
                "block_type": 15,
                "quote": {"elements": _mk_text_elements(action["text"])},
            }])
            t = action["text"]
            _log(f'{tag} 引用: {t[:50]}{"..." if len(t) > 50 else ""}')

        elif atype == "table":
            rows = action["rows"]
            _log(f"{tag} 表格 ({len(rows)} 行 × {max(len(r) for r in rows)} 列)")
            _import_create_table(doc_id, doc_id, rows, sheet_threshold=sheet_threshold)

    _log(f"\n✅ 内容导入完成")

    if beautify:
        _log(f"\n--- 开始一键美化 (页宽 {width}px) ---\n")
        _log("[1/2] PlantUML 转画板...")
        blocks = _get_all_blocks(doc_id)
        converted = _beautify_plantuml(doc_id, blocks)
        if converted == 0:
            _log("  无 PlantUML 代码块")
        _log("")
        _log("[2/2] 表格美化...")
        _beautify_tables(doc_id, width)
        _log(f"\n--- 美化完成 ---")

    _log(f"\n📄 文档链接: https://autolink-ai.feishu.cn/docx/{doc_id}")


def cmd_doc_import(args):
    """Import a local Markdown file into a Feishu document, then auto-beautify."""
    doc_id = args.document_id
    md_path = args.file
    beautify = not args.no_beautify
    width = args.width
    append = args.append
    sheet_threshold = args.sheet_threshold

    if not Path(md_path).exists():
        print(f"错误: 文件不存在 - {md_path}", file=sys.stderr)
        sys.exit(1)

    if sheet_threshold > 0:
        table_strategy = f"≤9 直建 / ≤{sheet_threshold} 单表扩容 / >{sheet_threshold} 改 Sheet 块"
    else:
        table_strategy = "≤9 直建 / >9 单表扩容（已禁用 Sheet 回退）"

    _log(f"=== Markdown 导入飞书文档 ===")
    _log(f"文件: {md_path}")
    _log(f"文档: {doc_id}")
    _log(
        f"模式: {'追加' if append else '全新'}  "
        f"美化: {'是' if beautify else '否'}  "
        f"页宽: {width}px\n"
        f"表格策略: {table_strategy}\n"
    )

    _do_import_markdown(
        doc_id, md_path,
        beautify=beautify, width=width, append=append,
        sheet_threshold=sheet_threshold,
    )


def cmd_doc_beautify(args):
    """One-click document beautification: PlantUML→whiteboard, table fitting, header styling."""
    doc_id = args.document_id
    target_width = args.width

    print(f"=== 飞书文档一键美化 ===")
    print(f"文档: {doc_id}  页宽: {target_width}px\n")

    # Step 1: PlantUML → whiteboard + delete originals
    print("[1/2] PlantUML 转画板...")
    blocks = _get_all_blocks(doc_id)
    converted = _beautify_plantuml(doc_id, blocks)
    if converted == 0:
        print("  无 PlantUML 代码块")
    print()

    # Step 2: Table beautification (re-read blocks since step 1 may have changed them)
    print("[2/2] 表格美化...")
    _beautify_tables(doc_id, target_width)

    print(f"\n=== 美化完成 ===")


# ── Whiteboard commands ────────────────────────────────────────────

def cmd_board_nodes(args):
    pp(api_get(f"/board/v1/whiteboards/{args.whiteboard_id}/nodes"))


def cmd_board_create_node(args):
    """Create a single node. Wraps in the required ``nodes`` array."""
    node = {"type": args.type}
    if args.content:
        node.update(json.loads(args.content))
    if args.x is not None:
        node["x"] = args.x
    if args.y is not None:
        node["y"] = args.y
    if args.width is not None:
        node["width"] = args.width
    if args.height is not None:
        node["height"] = args.height
    pp(api_post(f"/board/v1/whiteboards/{args.whiteboard_id}/nodes", {"nodes": [node]}))


def cmd_board_create_nodes(args):
    """Batch-create nodes from JSON (inline or file)."""
    if args.file:
        nodes = json.loads(Path(args.file).read_text(encoding="utf-8"))
    else:
        nodes = json.loads(args.nodes)
    if not isinstance(nodes, list):
        nodes = [nodes]
    pp(api_post(f"/board/v1/whiteboards/{args.whiteboard_id}/nodes", {"nodes": nodes}))


# ── Mindmap builder ───────────────────────────────────────────────

_MINDMAP_PALETTE = [
    {"fill": "#E0F7FA", "border": "#00ACC1", "text": "#006064"},
    {"fill": "#E3F2FD", "border": "#1E88E5", "text": "#0D47A1"},
    {"fill": "#F3E5F5", "border": "#8E24AA", "text": "#4A148C"},
    {"fill": "#E8F5E9", "border": "#43A047", "text": "#1B5E20"},
    {"fill": "#FFEBEE", "border": "#E53935", "text": "#B71C1C"},
    {"fill": "#FFF3E0", "border": "#FB8C00", "text": "#E65100"},
    {"fill": "#FCE4EC", "border": "#D81B60", "text": "#880E4F"},
    {"fill": "#C8E6C9", "border": "#2E7D32", "text": "#1B5E20"},
    {"fill": "#FFF9C4", "border": "#F9A825", "text": "#795548"},
    {"fill": "#D1C4E9", "border": "#5E35B1", "text": "#311B92"},
    {"fill": "#FFE0B2", "border": "#EF6C00", "text": "#BF360C"},
    {"fill": "#B2EBF2", "border": "#00838F", "text": "#004D40"},
]


def _build_mindmap_nodes(tree: dict) -> list[dict]:
    """Convert a tree dict into flat whiteboard nodes (text_shape + connector).

    ``tree`` format::

        {
          "root": "根节点文本",
          "center_x": 1200,       // optional, default 1200
          "center_y": 800,        // optional, default 800
          "branches": [
            {
              "name": "一级分支",
              "side": "right",     // "right" or "left", auto-assigned if omitted
              "color": {"fill": "#E0F7FA", "border": "#00ACC1", "text": "#006064"},  // optional
              "children": ["叶子1", "叶子2"]
            },
            ...
          ]
        }
    """
    ROOT_W, ROOT_H = 320, 64
    BRANCH_W, BRANCH_H = 240, 40
    LEAF_W, LEAF_H = 280, 28
    H_GAP, V_GAP_BRANCH, V_GAP_LEAF = 80, 14, 6

    cx = tree.get("center_x", 1200)
    cy = tree.get("center_y", 800)
    branches = tree.get("branches", [])

    # Auto-assign sides if not specified: alternate right/left
    for i, b in enumerate(branches):
        if "side" not in b:
            b["side"] = "right" if i % 2 == 0 else "left"

    right_branches = [b for b in branches if b["side"] == "right"]
    left_branches = [b for b in branches if b["side"] == "left"]

    nodes: list[dict] = []
    nid = 0

    root_id = f"n:{nid}"
    nodes.append({
        "id": root_id,
        "type": "text_shape",
        "x": cx - ROOT_W / 2, "y": cy - ROOT_H / 2,
        "width": ROOT_W, "height": ROOT_H,
        "text": {
            "text": tree.get("root", "Mind Map"),
            "font_size": 16, "font_weight": "bold",
            "text_color": "#ffffff",
            "horizontal_align": "center", "vertical_align": "mid",
        },
        "style": {
            "fill_color": "#1456CB", "border_color": "#0D47A1",
            "border_style": "solid", "border_width": "medium",
            "fill_opacity": 100, "border_opacity": 100,
            "fill_color_type": 1, "border_color_type": 1,
        },
        "composite_shape": {"type": "round_rect2"},
    })
    nid += 1

    def _calc_total_h(branch_list):
        total_leaves = sum(len(b.get("children", [])) for b in branch_list)
        return (
            len(branch_list) * BRANCH_H
            + max(0, len(branch_list) - 1) * V_GAP_BRANCH
            + total_leaves * LEAF_H
            + total_leaves * V_GAP_LEAF
        )

    palette_idx = 0

    for side, branch_list in [("right", right_branches), ("left", left_branches)]:
        total_h = _calc_total_h(branch_list)
        cur_y = cy - total_h / 2

        for branch in branch_list:
            c = branch.get("color") or _MINDMAP_PALETTE[palette_idx % len(_MINDMAP_PALETTE)]
            palette_idx += 1

            branch_id = f"n:{nid}"
            bx = (cx + ROOT_W / 2 + H_GAP) if side == "right" else (cx - ROOT_W / 2 - H_GAP - BRANCH_W)

            nodes.append({
                "id": branch_id,
                "type": "text_shape",
                "x": bx, "y": cur_y,
                "width": BRANCH_W, "height": BRANCH_H,
                "text": {
                    "text": branch["name"],
                    "font_size": 13, "font_weight": "bold",
                    "text_color": c["text"],
                    "horizontal_align": "center", "vertical_align": "mid",
                },
                "style": {
                    "fill_color": c["fill"], "border_color": c["border"],
                    "border_style": "solid", "border_width": "narrow",
                    "fill_opacity": 100, "border_opacity": 100,
                    "fill_color_type": 1, "border_color_type": 1,
                },
                "composite_shape": {"type": "round_rect"},
            })
            nid += 1

            root_snap = "right" if side == "right" else "left"
            branch_snap = "left" if side == "right" else "right"
            nodes.append({
                "id": f"c:{nid}", "type": "connector",
                "connector": {
                    "start": {"attached_object": {"id": root_id, "snap_to": root_snap}},
                    "end": {"attached_object": {"id": branch_id, "snap_to": branch_snap}},
                    "shape": "curve",
                },
                "style": {
                    "border_color": c["border"], "border_style": "solid",
                    "border_width": "narrow", "border_opacity": 80,
                    "border_color_type": 1,
                },
            })
            nid += 1

            cur_y += BRANCH_H + V_GAP_LEAF

            for leaf_text in branch.get("children", []):
                leaf_id = f"n:{nid}"
                lx = (bx + BRANCH_W + H_GAP * 0.6) if side == "right" else (bx - H_GAP * 0.6 - LEAF_W)

                nodes.append({
                    "id": leaf_id,
                    "type": "text_shape",
                    "x": lx, "y": cur_y,
                    "width": LEAF_W, "height": LEAF_H,
                    "text": {
                        "text": leaf_text, "font_size": 11,
                        "text_color": c["text"],
                        "horizontal_align": "left", "vertical_align": "mid",
                    },
                    "style": {
                        "fill_color": c["fill"], "border_color": c["border"],
                        "border_style": "solid", "border_width": "extra_narrow",
                        "fill_opacity": 60, "border_opacity": 60,
                        "fill_color_type": 1, "border_color_type": 1,
                    },
                    "composite_shape": {"type": "round_rect"},
                })
                nid += 1

                leaf_snap_start = "right" if side == "right" else "left"
                leaf_snap_end = "left" if side == "right" else "right"
                nodes.append({
                    "id": f"c:{nid}", "type": "connector",
                    "connector": {
                        "start": {"attached_object": {"id": branch_id, "snap_to": leaf_snap_start}},
                        "end": {"attached_object": {"id": leaf_id, "snap_to": leaf_snap_end}},
                        "shape": "curve",
                    },
                    "style": {
                        "border_color": c["border"], "border_style": "solid",
                        "border_width": "extra_narrow", "border_opacity": 50,
                        "border_color_type": 1,
                    },
                })
                nid += 1
                cur_y += LEAF_H + V_GAP_LEAF

            cur_y += V_GAP_BRANCH

    return nodes


def cmd_board_create_mindmap(args):
    """Create a mind map on a whiteboard from a JSON tree definition."""
    tree = json.loads(Path(args.file).read_text(encoding="utf-8"))
    all_nodes = _build_mindmap_nodes(tree)

    shapes = [n for n in all_nodes if n["type"] != "connector"]
    conns = [n for n in all_nodes if n["type"] == "connector"]
    print(f"构建完成: {len(shapes)} 个形状 + {len(conns)} 条连线 = {len(all_nodes)} 个元素")

    resp = api_post(f"/board/v1/whiteboards/{args.whiteboard_id}/nodes", {"nodes": all_nodes})
    if resp.get("code") == 0:
        ids = resp.get("data", {}).get("ids", [])
        print(f"创建成功: {len(ids)} 个元素已添加到画板")
    else:
        print(f"创建失败: {json.dumps(resp, ensure_ascii=False)}", file=sys.stderr)
        sys.exit(1)


def cmd_board_theme(args):
    pp(api_get(f"/board/v1/whiteboards/{args.whiteboard_id}/theme"))


# ── Drive / Wiki commands ─────────────────────────────────────────

def cmd_folder_list(args):
    pp(api_get("/drive/v1/files", {"folder_token": args.folder_token, "page_size": 200}))


def cmd_wiki_node(args):
    pp(api_get("/wiki/v2/spaces/get_node", {"token": args.wiki_token}))


def cmd_wiki_move_to(args):
    """Move a cloud document into a Wiki space."""
    body: dict = {
        "obj_type": args.obj_type,
        "obj_token": args.obj_token,
    }
    if args.parent:
        body["parent_wiki_token"] = args.parent

    resp = api_post(f"/wiki/v2/spaces/{args.space_id}/nodes/move_docs_to_wiki", body)
    pp(resp)

    data = resp.get("data", {})
    if resp.get("code") == 0:
        if "wiki_token" in data:
            print(f"\n移动完成: wiki_token={data['wiki_token']}")
        elif "task_id" in data:
            print(f"\n移动任务已提交（异步）: task_id={data['task_id']}")
            print("使用 wiki-task 命令查询结果")
        elif data.get("applied"):
            print("\n无编辑权限，已发起申请")


def cmd_wiki_task(args):
    """Query the result of an async Wiki task (e.g. move)."""
    pp(api_get(f"/wiki/v2/tasks/{args.task_id}", {"task_type": args.task_type}))


def cmd_doc_move(args):
    """Move a cloud document to a different Drive folder."""
    body = {"type": args.type, "folder_token": args.folder}
    resp = api_post(f"/drive/v1/files/{args.file_token}/move", body)
    pp(resp)
    if resp.get("code") == 0:
        print(f"\n已移动到目标文件夹: folder_token={args.folder}")
    else:
        print(f"\n移动失败: code={resp.get('code')}, msg={resp.get('msg')}",
              file=sys.stderr)


def cmd_doc_delete(args):
    """Delete a cloud document (moves to trash, recoverable for 30 days)."""
    resp = api_delete(f"/drive/v1/files/{args.file_token}?type={args.type}")
    pp(resp)
    if resp.get("code") == 0:
        print(f"\n已删除（移入回收站）: {args.file_token} (type={args.type})")
    elif resp.get("code") == 1061004:
        print("\n删除失败: forbidden (1061004)。"
              "可能原因：Wiki 管理的文档无法通过 Drive API 删除，需在飞书 UI 手动操作。",
              file=sys.stderr)


def cmd_doc_permission(args):
    """Set document public sharing permissions."""
    resp = _set_permission_public(args.token, args.type, args.link_share)
    pp(resp)
    if resp.get("code") == 0:
        print(f"\n权限已设置: link_share_entity={args.link_share}")


def cmd_doc_add_collaborator(args):
    """Add a specific user as a collaborator."""
    resp = _add_collaborator(args.token, args.member_type, args.member_id,
                             args.perm, args.type)
    pp(resp)
    if resp.get("code") == 0:
        print(f"\n协作者已添加: {args.member_type}={args.member_id}, perm={args.perm}")


# ── Main ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="飞书文档与画板 CLI 工具")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("token", help="获取 tenant_access_token")

    p = sub.add_parser("doc-info", help="获取文档信息")
    p.add_argument("document_id")

    p = sub.add_parser("doc-text", help="获取文档纯文本")
    p.add_argument("document_id")

    p = sub.add_parser("doc-blocks", help="获取文档所有块")
    p.add_argument("document_id")

    p = sub.add_parser("doc-create", help="创建新文档")
    p.add_argument("--title", required=True)
    p.add_argument("--folder", default=None)
    p.add_argument("--no-permission", action="store_true",
                   help="跳过创建后自动设置权限（默认设置组织内可阅读）")
    p.add_argument("--link-share", default="tenant_readable",
                   choices=["tenant_readable", "tenant_editable", "anyone_readable",
                            "anyone_editable", "closed"],
                   help="链接分享权限（默认 tenant_readable）")
    p.add_argument("--collaborator", default=None,
                   help="创建后自动添加的协作者邮箱（默认读取 ~/.gitconfig user.email）")
    p.add_argument("--no-collaborator", action="store_true",
                   help="跳过自动添加协作者")

    p = sub.add_parser("doc-append", help="追加内容到文档")
    p.add_argument("document_id")
    p.add_argument("--text", default=None)
    p.add_argument("--markdown", default=None)

    p = sub.add_parser("doc-export", help="导出文档")
    p.add_argument("document_id")
    p.add_argument("--format", choices=["markdown", "text"], default="markdown")
    p.add_argument("--output", default=None)

    p = sub.add_parser("doc-fit-tables", help="自适应调整文档所有表格列宽对齐页面宽度")
    p.add_argument("document_id")
    p.add_argument("--width", type=int, default=FEISHU_PAGE_WIDTHS["default"],
                   help=f"目标总宽度 (px)。默认={FEISHU_PAGE_WIDTHS['default']} (Default 页宽)，"
                        f"较宽={FEISHU_PAGE_WIDTHS['wide']}")

    p = sub.add_parser("doc-beautify", help="一键美化文档 (PlantUML→画板 + 表格列宽 + 表头高亮加粗)")
    p.add_argument("document_id")
    p.add_argument("--width", type=int, default=FEISHU_PAGE_WIDTHS["default"],
                   help=f"目标表格总宽度 (px)。默认={FEISHU_PAGE_WIDTHS['default']}")

    p = sub.add_parser("board-nodes", help="获取画板所有节点")
    p.add_argument("whiteboard_id")

    p = sub.add_parser("board-create-node", help="创建单个画板节点")
    p.add_argument("whiteboard_id")
    p.add_argument("--type", required=True)
    p.add_argument("--content", default=None, help="节点属性 JSON（会与 type 合并）")
    p.add_argument("--x", type=float, default=None)
    p.add_argument("--y", type=float, default=None)
    p.add_argument("--width", type=float, default=None)
    p.add_argument("--height", type=float, default=None)

    p = sub.add_parser("board-create-nodes", help="批量创建画板节点")
    p.add_argument("whiteboard_id")
    p.add_argument("--nodes", default=None, help="节点数组 JSON 字符串")
    p.add_argument("--file", default=None, help="包含节点数组的 JSON 文件路径")

    p = sub.add_parser("board-create-mindmap", help="从 JSON 树定义在画板上创建思维导图")
    p.add_argument("whiteboard_id")
    p.add_argument("--file", required=True, help="思维导图树 JSON 文件路径")

    p = sub.add_parser("board-theme", help="获取画板主题")
    p.add_argument("whiteboard_id")

    p = sub.add_parser("folder-list", help="列出文件夹内容")
    p.add_argument("folder_token")

    p = sub.add_parser("wiki-node", help="获取知识库节点信息")
    p.add_argument("wiki_token")

    p = sub.add_parser("wiki-move-to", help="移动云文档到知识空间")
    p.add_argument("space_id", help="目标知识空间 ID")
    p.add_argument("--obj-token", required=True, help="文档 token (document_id)")
    p.add_argument("--obj-type", default="docx",
                   choices=["doc", "docx", "sheet", "bitable", "mindnote", "file"],
                   help="文档类型（默认 docx）")
    p.add_argument("--parent", default=None,
                   help="父节点 wiki_token（不填则作为一级节点）")

    p = sub.add_parser("wiki-task", help="查询 Wiki 异步任务结果")
    p.add_argument("task_id", help="任务 ID")
    p.add_argument("--task-type", default="move",
                   choices=["move"],
                   help="任务类型（默认 move）")

    p = sub.add_parser("doc-move", help="移动云空间文档到指定 Drive 文件夹")
    p.add_argument("file_token", help="文档 token (document_id)")
    p.add_argument("--folder", required=True, help="目标文件夹 folder_token")
    p.add_argument("--type", default="docx",
                   choices=["doc", "docx", "sheet", "bitable", "mindnote",
                            "file", "folder"],
                   help="文档类型（默认 docx）")

    p = sub.add_parser("doc-delete", help="删除云空间文档（移入回收站）")
    p.add_argument("file_token", help="文档 token (document_id)")
    p.add_argument("--type", default="docx",
                   choices=["doc", "docx", "sheet", "bitable", "mindnote",
                            "file", "folder"],
                   help="文档类型（默认 docx）")

    p = sub.add_parser("doc-permission", help="设置文档链接分享权限")
    p.add_argument("token", help="文档 token")
    p.add_argument("--type", default="docx",
                   choices=["doc", "docx", "sheet", "file", "wiki", "bitable",
                            "folder", "mindnote", "minutes", "slides"],
                   help="文档类型（默认 docx）")
    p.add_argument("--link-share", default="tenant_readable",
                   choices=["tenant_readable", "tenant_editable", "anyone_readable",
                            "anyone_editable", "closed"],
                   help="链接分享权限（默认 tenant_readable）")

    p = sub.add_parser("doc-add-collaborator", help="添加文档协作者")
    p.add_argument("token", help="文档 token")
    p.add_argument("--member-type", required=True,
                   choices=["email", "openid", "unionid", "userid", "openchat"],
                   help="协作者 ID 类型")
    p.add_argument("--member-id", required=True, help="协作者 ID")
    p.add_argument("--perm", default="full_access",
                   choices=["view", "edit", "full_access"],
                   help="权限角色（默认 full_access）")
    p.add_argument("--type", default="docx",
                   choices=["doc", "docx", "sheet", "file", "wiki", "bitable",
                            "folder", "mindnote", "minutes", "slides"],
                   help="文档类型（默认 docx）")

    p = sub.add_parser("doc-import", help="将本地 Markdown 导入飞书文档（自动美化）")
    p.add_argument("document_id")
    p.add_argument("--file", required=True, help="本地 Markdown 文件路径")
    p.add_argument("--no-beautify", action="store_true", help="跳过导入后自动美化")
    p.add_argument("--width", type=int, default=833, help="页宽 (默认 833, 较宽 1033)")
    p.add_argument("--append", action="store_true", help="追加模式：允许向非空文档末尾追加内容")
    p.add_argument("--sheet-threshold", type=int, default=50,
                   help="行数超过此阈值时改用 Sheet 块电子表格嵌入（默认 50；置 0 禁用 Sheet 回退）")

    args = parser.parse_args()

    commands = {
        "token": cmd_token,
        "doc-info": cmd_doc_info,
        "doc-text": cmd_doc_text,
        "doc-blocks": cmd_doc_blocks,
        "doc-create": cmd_doc_create,
        "doc-append": cmd_doc_append,
        "doc-export": cmd_doc_export,
        "doc-fit-tables": cmd_doc_fit_tables,
        "doc-beautify": cmd_doc_beautify,
        "board-nodes": cmd_board_nodes,
        "board-create-node": cmd_board_create_node,
        "board-create-nodes": cmd_board_create_nodes,
        "board-create-mindmap": cmd_board_create_mindmap,
        "board-theme": cmd_board_theme,
        "folder-list": cmd_folder_list,
        "wiki-node": cmd_wiki_node,
        "wiki-move-to": cmd_wiki_move_to,
        "wiki-task": cmd_wiki_task,
        "doc-move": cmd_doc_move,
        "doc-delete": cmd_doc_delete,
        "doc-permission": cmd_doc_permission,
        "doc-add-collaborator": cmd_doc_add_collaborator,
        "doc-import": cmd_doc_import,
    }

    fn = commands.get(args.command)
    if fn:
        fn(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    main()
