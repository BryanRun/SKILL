#!/usr/bin/env python3
"""本地模块评审上下文生成（对齐 gerrit_review.py --prepare 的 JSON 形状，便于复用 references/08）。

用法（在 Git 仓库根目录执行）：
  python3 local_module_prepare.py <模块相对路径> [--base REF] [-o ctx.json]

示例：
  python3 local_module_prepare.py frameworks/cm/videoplayer
  python3 local_module_prepare.py frameworks/cm/videoplayer --base HEAD~1

说明：
  - 优先包含工作区相对 <模块> 的已跟踪文件的 git diff（含暂存）；若无 diff，则对 <模块> 下文本源文件做全量快照（仅元数据 + 可选截断预览）。
  - 机械规则见 local_audit.py（与 gerrit_audit 同源规则集）。
  - 六维深度评审仍由 Agent 按 SKILL + references/01-08 执行；本脚本只负责**结构化上下文**。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_THIS = os.path.dirname(os.path.abspath(__file__))
if _THIS not in sys.path:
    sys.path.insert(0, _THIS)

from local_audit import scan_line  # noqa: E402

TEXT_EXT = {
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".java",
    ".kt",
    ".kts",
    ".xml",
    ".bp",
    ".mk",
    ".cmake",
    ".py",
    ".aidl",
}


def _run_git(args: list[str], cwd: str) -> tuple[int, str]:
    p = subprocess.run(
        ["git", "-C", cwd, *args],
        capture_output=True,
        text=True,
        errors="replace",
    )
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out


def _collect_diff_paths(repo: str, module: str, base: str | None) -> tuple[str, list[str]]:
    """返回 (diff_source_description, [paths relative to repo])."""
    mod = module.strip().strip("/")
    root_path = Path(repo) / mod
    # 单文件路径：直接作为唯一评审目标
    if root_path.is_file():
        try:
            rel = str(root_path.relative_to(Path(repo))).replace("\\", "/")
        except ValueError:
            rel = mod
        return "single_file", [rel]
    # 工作区 + 暂存
    code, diff_cached = _run_git(["diff", "--name-only", "--relative", mod], repo)
    code2, diff_staged = _run_git(["diff", "--name-only", "--cached", "--relative", mod], repo)
    paths = sorted({p for p in (diff_cached + diff_staged).splitlines() if p.strip()})
    if paths:
        return "working_tree+index", paths
    # 与 base 比较
    if base:
        br, out = _run_git(["diff", "--name-only", f"{base}...HEAD", "--", mod], repo)
        if br == 0:
            paths = [p for p in out.splitlines() if p.strip()]
            if paths:
                return f"git_range {base}...HEAD", paths
    # 回退：列出模块下源文件
    root = Path(repo) / mod
    if not root.exists():
        return f"list_fallback missing:{mod}", []
    files: list[str] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() in TEXT_EXT or p.name in ("Android.bp", "Makefile"):
            try:
                rel = p.relative_to(Path(repo))
                files.append(str(rel).replace("\\", "/"))
            except ValueError:
                continue
    files.sort()
    return "full_tree_snapshot", files[:500]


def _read_diff_for_file(repo: str, path: str, base: str | None) -> str:
    code, a = _run_git(["diff", "--", path], repo)
    if a.strip():
        return a
    code2, b = _run_git(["diff", "--cached", "--", path], repo)
    if b.strip():
        return b
    if base:
        code3, c = _run_git(["diff", f"{base}...HEAD", "--", path], repo)
        return c
    return ""


def prepare(module: str, repo: str, base: str | None) -> dict:
    src, paths = _collect_diff_paths(repo, module, base)
    files_out: list[dict] = []
    audit_hits: dict[str, list] = {}

    for rel in paths:
        ext = Path(rel).suffix.lower()
        if ext not in TEXT_EXT and Path(rel).name not in ("Android.bp", "Makefile"):
            continue
        diff_text = _read_diff_for_file(repo, rel, base)
        # 对新增行做规则扫描（简化：若整文件 diff 为空则读全文件扫）
        lines_to_scan: list[tuple[int, str]] = []
        if diff_text.strip():
            for line in diff_text.splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    lines_to_scan.append((0, line[1:]))
        else:
            fp = Path(repo) / rel
            if fp.is_file():
                try:
                    content = fp.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    content = ""
                for i, ln in enumerate(content.splitlines(), start=1):
                    lines_to_scan.append((i, ln))

        path_hits: list[dict] = []
        for line_no, text in lines_to_scan:
            for h in scan_line(text):
                rec = {"line": line_no or None, **h, "text": text.strip()[:300]}
                path_hits.append(rec)
        if path_hits:
            audit_hits[rel] = path_hits

        files_out.append(
            {
                "path": rel,
                "diff_source": src,
                "diff_excerpt": diff_text[:120000] if diff_text else "",
                "audit_hits": path_hits,
            }
        )

    return {
        "mode": "local_module",
        "module": module,
        "repo_root": os.path.abspath(repo),
        "diff_collection": src,
        "git_base": base,
        "files": files_out,
        "audit_summary": {
            "paths_with_hits": list(audit_hits.keys()),
            "hit_counts": {k: len(v) for k, v in audit_hits.items()},
        },
        "note": "六维评审与 LLM 输出格式仍遵循 references/08-llm-review-prompt.md；此处为本地模块上下文。",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Prepare local module review JSON context")
    ap.add_argument("module", help="模块相对仓库根的路径，如 frameworks/cm/videoplayer")
    ap.add_argument("--base", default=None, help="git diff 基线，如 origin/main 或 HEAD~1")
    ap.add_argument(
        "-o",
        "--output",
        default=None,
        help="写入 JSON 文件；默认 stdout",
    )
    ap.add_argument(
        "--repo",
        default=os.getcwd(),
        help="Git 仓库根（默认当前目录）",
    )
    args = ap.parse_args()
    ctx = prepare(args.module, args.repo, args.base)
    js = json.dumps(ctx, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(js + "\n", encoding="utf-8")
    else:
        print(js)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
