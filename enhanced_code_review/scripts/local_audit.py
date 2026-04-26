"""本地文件/ diff 行级机械规则扫描（与 gerrit_audit.py 的 RULES 集合保持一致）。

不依赖 Gerrit；供 local_module_prepare.py 聚合到 LLM 上下文。
"""
from __future__ import annotations

import re
from typing import Any, Pattern

# 与 gerrit_audit.RULES 保持同步（2026-04-20 enhanced_code_review）
RULES: list[tuple[str, Pattern, str, str, str]] = [
    (
        "R.EMPTY_CATCH",
        re.compile(r"catch\s*\([^)]*\)\s*\{\s*\}"),
        "P1",
        "空 catch 块吞掉异常",
        "异常被吞掉会导致服务进入不一致状态，但外部无任何日志、无任何告警。",
    ),
    (
        "R.SYSTEM_OUT",
        re.compile(r"\bSystem\.(out|err)\.print"),
        "P2",
        "服务层出现 System.out/err",
        "服务层禁用 System.out/err（调试遗留？）。与项目统一 Log 规范不一致。",
    ),
    (
        "R.TODO_NO_OWNER",
        re.compile(r"//\s*TODO(?!.*(?:@|\bJira\b|\bCHYT1V\b|\bBAIC\b|\bKP31\b))"),
        "P3",
        "TODO 未关联 owner / Jira",
        "TODO 需附 owner 或 Jira 号。",
    ),
]


def scan_line(text: str) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for rid, pat, level, title, detail in RULES:
        if pat.search(text):
            hits.append(
                {
                    "rule": rid,
                    "level": level,
                    "title": title,
                    "detail": detail,
                }
            )
    return hits


def scan_text_lines(path: str, lines: list[str]) -> dict[str, Any]:
    """对完整文件逐行扫描，返回 { path, hits: [ {line_no, ...} ] }。"""
    out: list[dict[str, Any]] = []
    for i, line in enumerate(lines, start=1):
        for h in scan_line(line):
            out.append({"line": i, "text": line.rstrip()[:500], **h})
    return {"path": path, "hits": out}
