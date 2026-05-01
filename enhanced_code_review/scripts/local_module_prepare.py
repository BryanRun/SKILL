#!/usr/bin/env python3
"""本地模块评审上下文生成（对齐 gerrit_review.py --prepare 的 JSON 形状，便于复用 references/08）。

用法：
  python3 local_module_prepare.py <模块路径> [--base REF] [--repo REPO|auto] [-o ctx.json]

示例：
  # 显式 repo（当前目录就是 git 工作树根；模块为相对路径）
  python3 local_module_prepare.py frameworks/cm/videoplayer

  # 自动定位最近的 git 工作树（推荐：车载多仓库 / git submodule 场景）
  cd <任意位置>
  python3 local_module_prepare.py /path/to/qnx/vendor/autolink/midware/hud --repo auto

  # 与基线比较
  python3 local_module_prepare.py frameworks/cm/videoplayer --base HEAD~1

适配场景：
  - 普通仓库：`<repo>/.git` 是目录
  - git submodule：`<repo>/.git` 是文件（含 `gitdir:` 行），脚本会回溯 superproject 工作树
  - repo 工具管理：`<repo>/.git` 是 symlink；存在 `.repo/manifests/` 时标注 repo_tool_managed
  - 未初始化 submodule：若 `.gitmodules` 声明但目录无 `.git`，输出复制即用的 `git submodule update --init <path>`

说明：
  - 优先包含工作区相对 <模块> 的已跟踪文件的 git diff（含暂存）；若无 diff，则对 <模块> 下文本源文件做全量快照（仅元数据 + 可选截断预览）。
  - 机械规则见 local_audit.py（与 gerrit_audit 同源规则集）。
  - 七维深度评审仍由 Agent 按 SKILL + references/01-08 执行；本脚本只负责**结构化上下文**与**git 拓扑探测**。
"""
"""兼容性：本模块不使用 PEP 563/585/604（无 ``from __future__ import annotations``、
无 ``dict[..]`` / ``X | None`` 等运行时下标注解），可在 Python 3.6.9+ 直接运行。
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_THIS = os.path.dirname(os.path.abspath(__file__))
if _THIS not in sys.path:
    sys.path.insert(0, _THIS)

from local_audit import scan_line  # noqa: E402
try:
    from local_audit import scan_privacy as _scan_privacy  # noqa: E402
except ImportError:
    _scan_privacy = None

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


# ---------------------------------------------------------------------------
# Git 拓扑探测（v2.1.1 新增）
# ---------------------------------------------------------------------------


def _classify_dot_git(repo_root):
    # type: (Path) -> str
    """识别 <repo_root>/.git 的形态：dir / file / symlink / none。"""
    p = repo_root / ".git"
    # symlink 优先于 dir/file（symlink 指向 dir 时 is_dir 也为 True）
    if p.is_symlink():
        return "symlink"
    if p.is_file():
        return "file"
    if p.is_dir():
        return "dir"
    return "none"


def _read_gitdir_pointer(p):
    # type: (Path) -> Optional[str]
    """从 .git 文件读取 `gitdir: ...` 指针（git submodule / linked worktree 形态）。"""
    if not p.is_file():
        return None
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("gitdir:"):
            return line.split(":", 1)[1].strip()
    return None


def _find_nearest_git_root(start):
    # type: (Path) -> Optional[Path]
    """从 start 向上回溯，返回最近的含 .git（dir / file / symlink）的目录。

    `git rev-parse --show-toplevel` 在 submodule 内会回到 submodule 的工作树根，
    本函数行为一致；用于 `--repo auto` 解析。
    """
    cur = start
    if cur.exists():
        try:
            cur = cur.resolve()
        except OSError:
            cur = cur.absolute()
    else:
        cur = cur.absolute()
    while True:
        dot = cur / ".git"
        if dot.exists() or dot.is_symlink():
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent


def _find_superproject(repo_root):
    # type: (Path) -> Optional[Path]
    """若 <repo_root>/.git 是 file（gitlink），向上找到拥有 `.git/modules/<name>` 的 superproject 工作树。"""
    p = repo_root / ".git"
    pointer = _read_gitdir_pointer(p)
    if not pointer:
        return None
    pointer_path = Path(pointer)
    abs_gitdir = pointer_path if pointer_path.is_absolute() else (repo_root / pointer_path)
    try:
        abs_gitdir = abs_gitdir.resolve()
    except OSError:
        return None
    # 形如 <super>/.git/modules/<name> → superproject 为 <super>
    cur = abs_gitdir
    while cur.parent != cur:
        cur = cur.parent
        if cur.name == ".git" and cur.parent.exists():
            return cur.parent
    return None


def _find_repo_tool_root(start):
    # type: (Path) -> Optional[Path]
    """向上 ≤16 层查找 `.repo/manifests/`，命中即视为 Android `repo` 工具管理。"""
    cur = start
    for _ in range(16):
        if (cur / ".repo" / "manifests").exists():
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent
    return None


def _scan_uninitialized_submodules(repo_root, limit=20):
    # type: (Path, int) -> List[dict]
    """读取 <repo_root>/.gitmodules，列出已声明但未初始化的子模块路径。

    每条返回包含 `path` 与 `init_hint`（可直接复制粘贴的 git 命令）。
    """
    gm = repo_root / ".gitmodules"
    if not gm.is_file():
        return []
    try:
        text = gm.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out = []  # type: List[dict]
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("path"):
            continue
        if "=" not in s:
            continue
        rel = s.split("=", 1)[1].strip()
        if not rel:
            continue
        sub_dir = repo_root / rel
        sub_dot_git = sub_dir / ".git"
        if (not sub_dir.exists()) or (sub_dir.is_dir() and not (sub_dot_git.exists() or sub_dot_git.is_symlink())):
            out.append(
                {
                    "path": rel,
                    "init_hint": f"git -C {repo_root} submodule update --init -- {rel}",
                }
            )
        if len(out) >= limit:
            break
    return out


def _describe_topology(repo_root):
    # type: (Path) -> dict
    """生成对该 repo_root 的拓扑描述（含 superproject、repo 工具、未初始化子模块）。"""
    kind = _classify_dot_git(repo_root)
    super_proj = _find_superproject(repo_root) if kind == "file" else None
    repo_tool = _find_repo_tool_root(repo_root)
    uninit = _scan_uninitialized_submodules(repo_root)
    desc = {
        "git_root": str(repo_root),
        "git_kind": kind,
        "is_submodule": kind == "file",
        "superproject": str(super_proj) if super_proj else None,
        "repo_tool_managed": bool(repo_tool),
        "repo_tool_root": str(repo_tool) if repo_tool else None,
        "uninitialized_submodules": uninit,
    }
    return desc


def _build_init_hint_for_missing(target_abs):
    # type: (Path) -> Optional[dict]
    """target 路径不存在或所在目录无 .git 时，尝试在 target 的祖先里找 .gitmodules 提供 init 命令。"""
    cur = target_abs
    if not cur.exists():
        # 找最近存在的祖先
        while not cur.exists() and cur.parent != cur:
            cur = cur.parent
    for _ in range(16):
        gm = cur / ".gitmodules"
        if gm.is_file():
            try:
                text = gm.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            for line in text.splitlines():
                s = line.strip()
                if not s.startswith("path") or "=" not in s:
                    continue
                rel = s.split("=", 1)[1].strip()
                if not rel:
                    continue
                cand = (cur / rel).resolve() if (cur / rel).exists() or True else None
                # 如果 target_abs 落在该 submodule 路径里，给出该路径
                try:
                    target_abs.relative_to(cur / rel)
                except ValueError:
                    continue
                return {
                    "superproject_root": str(cur),
                    "submodule_path": rel,
                    "init_hint": f"git -C {cur} submodule update --init -- {rel}",
                }
        if cur.parent == cur:
            return None
        cur = cur.parent
    return None


# ---------------------------------------------------------------------------
# Git diff / 文件枚举
# ---------------------------------------------------------------------------


def _run_git(args, cwd):
    # type: (List[str], str) -> Tuple[int, str]
    # 兼容 Python 3.6.9：subprocess.run 不使用 capture_output / text（3.7+），改用经典写法。
    p = subprocess.run(
        ["git", "-C", cwd] + list(args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        errors="replace",
    )
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out


def _collect_diff_paths(repo, module, base):
    # type: (str, str, Optional[str]) -> Tuple[str, List[str]]
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
    files = []  # type: List[str]
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


def _read_diff_for_file(repo, path, base):
    # type: (str, str, Optional[str]) -> str
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


# ---------------------------------------------------------------------------
# 上下文聚合
# ---------------------------------------------------------------------------


def prepare(module, repo, base):
    # type: (str, str, Optional[str]) -> dict
    src, paths = _collect_diff_paths(repo, module, base)
    files_out = []           # type: List[dict]
    audit_hits = {}          # type: Dict[str, list]
    privacy_candidates = []  # type: List[dict]

    for rel in paths:
        ext = Path(rel).suffix.lower()
        if ext not in TEXT_EXT and Path(rel).name not in ("Android.bp", "Makefile"):
            continue
        diff_text = _read_diff_for_file(repo, rel, base)
        # 对新增行做规则扫描（简化：若整文件 diff 为空则读全文件扫）
        lines_to_scan = []  # type: List[Tuple[int, str]]
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

        path_hits = []  # type: List[dict]
        for line_no, text in lines_to_scan:
            for h in scan_line(text):
                rec = {"line": line_no or None, "text": text.strip()[:300]}
                rec.update(h)
                path_hits.append(rec)
        if path_hits:
            audit_hits[rel] = path_hits

        # 隐私合规候选扫描（对新侧完整文件做门控 A + B 共现）
        priv_cands = []  # type: List[dict]
        if _scan_privacy is not None:
            fp = Path(repo) / rel
            if fp.is_file():
                try:
                    full_lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
                except OSError:
                    full_lines = []
                if full_lines:
                    res = _scan_privacy(rel, full_lines) or {}
                    priv_cands = res.get("candidates", [])
                    if priv_cands:
                        privacy_candidates.append({"path": rel, "candidates": priv_cands})

        files_out.append(
            {
                "path": rel,
                "diff_source": src,
                "diff_excerpt": diff_text[:120000] if diff_text else "",
                "audit_hits": path_hits,
                "privacy_candidates": priv_cands,
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
        "privacy_candidates": privacy_candidates,
        "privacy_summary": {
            "paths_with_candidates": [pc["path"] for pc in privacy_candidates],
            "candidate_counts": {pc["path"]: len(pc["candidates"]) for pc in privacy_candidates},
            "note": "候选仅为门控 A + B 共现提示；P0 裁决须由 LLM 按 10-privacy-compliance.md 做门控 C 确认。",
        },
        "note": "七维评审（含隐私合规 P0）与 LLM 输出格式遵循 references/08-llm-review-prompt.md；此处为本地模块上下文。",
    }


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def _resolve_repo_and_module(repo_arg, module_arg):
    # type: (str, str) -> Tuple[Optional[Path], str, dict]
    """根据 --repo / module 解析出 (repo_root, module_relative_to_repo, topology)。

    repo_arg == 'auto'：从 module_arg 所在位置向上找最近的 .git。
    其它：repo_arg 即仓库根，module_arg 视作相对路径（保留旧行为）。
    """
    if repo_arg == "auto":
        target = Path(module_arg)
        if not target.is_absolute():
            target = (Path.cwd() / target).resolve()
        # 起点：target 自身或最近存在的祖先
        start = target if target.exists() else target.parent
        while not start.exists() and start.parent != start:
            start = start.parent
        repo_root = _find_nearest_git_root(start)
        if repo_root is None:
            init_hint = _build_init_hint_for_missing(target)
            return None, "", {
                "git_root": None,
                "git_kind": "none",
                "auto_resolve_target": str(target),
                "uninitialized_submodule_hint": init_hint,
                "error": (
                    "无法在 {} 及其祖先中找到 .git；"
                    "若该路径属于 git submodule，请按 uninitialized_submodule_hint 初始化后重试。"
                ).format(target),
            }
        try:
            module_rel = str(target.relative_to(repo_root)).replace("\\", "/") or "."
        except ValueError:
            module_rel = module_arg
        topo = _describe_topology(repo_root)
        topo["auto_resolve_target"] = str(target)
        topo["module_relative_to_repo"] = module_rel
        return repo_root, module_rel, topo

    # 显式 repo
    repo_root = Path(repo_arg).resolve()
    topo = _describe_topology(repo_root) if repo_root.exists() else {
        "git_root": str(repo_root),
        "git_kind": "none",
        "error": f"--repo {repo_arg} 不存在",
    }
    return repo_root, module_arg, topo


def main():
    # type: () -> int
    ap = argparse.ArgumentParser(
        description="Prepare local module review JSON context",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python3 local_module_prepare.py frameworks/cm/videoplayer\n"
            "  python3 local_module_prepare.py /abs/path/to/midware/hud --repo auto\n"
            "  python3 local_module_prepare.py mod --base origin/main --repo /path/to/repo\n"
        ),
    )
    ap.add_argument(
        "module",
        help="模块路径：可为相对仓库根（与 --repo 配合）或绝对路径（与 --repo auto 配合）",
    )
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
        help="Git 仓库根（默认当前目录）。可用 'auto' 从 module 路径向上回溯定位最近 .git，自适应 git submodule / repo 工具管理的多仓库结构",
    )
    args = ap.parse_args()

    repo_root, module_rel, topology = _resolve_repo_and_module(args.repo, args.module)

    if repo_root is None or not Path(repo_root).exists():
        # 给出友好的退出信息：错误信息进 stderr，topology JSON 进 stdout 便于上层捕获
        err_payload = {
            "mode": "local_module",
            "module": args.module,
            "repo_root": None,
            "topology": topology,
            "files": [],
            "note": (
                "未能解析 git 仓库根。若 module 属于未初始化的 git submodule，可执行："
                f"{(topology.get('uninitialized_submodule_hint') or {}).get('init_hint', '<see topology>')}"
            ),
        }
        js = json.dumps(err_payload, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(js + "\n", encoding="utf-8")
        else:
            print(js)
        print(
            "[local_module_prepare] 未找到 .git；详见 topology / uninitialized_submodule_hint",
            file=sys.stderr,
        )
        return 2

    ctx = prepare(module_rel, str(repo_root), args.base)
    ctx["topology"] = topology

    js = json.dumps(ctx, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(js + "\n", encoding="utf-8")
    else:
        print(js)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
