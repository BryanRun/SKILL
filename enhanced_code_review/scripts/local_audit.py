"""本地文件/ diff 行级机械规则扫描（与 gerrit_audit.py 的 RULES 集合保持一致）。

不依赖 Gerrit；供 local_module_prepare.py 聚合到 LLM 上下文。

兼容性：本模块不使用 PEP 563 / PEP 585 / PEP 604 等 Python 3.7+ 才允许的注解写法，
       且不引入 dataclasses，可在 Python 3.6.9+ 直接运行（见 SKILL.md「运行时要求」）。
"""

import re
from typing import Any, Dict, List, Pattern, Tuple

# 与 gerrit_audit.RULES 保持同步（2026-04-20 enhanced_code_review）
RULES = [
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
        re.compile(
            r"//\s*TODO(?!.*(?:@|\bJira\b|\bCHER[A-Z0-9]*\b|\bCHYT1V\b|\bBAIC\b|\bKP31\b|\bAUDI\b|\bFL[123]\b|\bT1V\b|\bD01\b|\bCHYT12A\b|\bCHYMIFA\b))"
        ),
        "P3",
        "TODO 未关联 owner / Jira",
        "TODO 需附 owner 或 Jira 号。",
    ),
]  # type: List[Tuple[str, Pattern, str, str, str]]


def scan_line(text):
    # type: (str) -> List[Dict[str, Any]]
    hits = []  # type: List[Dict[str, Any]]
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


def scan_text_lines(path, lines):
    # type: (str, List[str]) -> Dict[str, Any]
    """对完整文件逐行扫描，返回 { path, hits: [ {line_no, ...} ] }。"""
    out = []  # type: List[Dict[str, Any]]
    for i, line in enumerate(lines, start=1):
        for h in scan_line(line):
            entry = {"line": i, "text": line.rstrip()[:500]}
            entry.update(h)
            out.append(entry)
    return {"path": path, "hits": out}


def scan_privacy(path, lines):
    # type: (str, List[str]) -> Dict[str, Any]
    """隐私合规候选扫描（门控 A + B 共现）。

    返回 { path, candidates: [...], dropped_reason? }。
    门控 C（语义 / 上下文）由 LLM 在 08 的 Step 8 做最终裁决。
    """
    try:
        from privacy_compliance_scan import scan_file as _scan
    except ImportError:
        return {"path": path, "candidates": [], "dropped_reason": "privacy_scan unavailable"}
    return _scan(path, lines)
