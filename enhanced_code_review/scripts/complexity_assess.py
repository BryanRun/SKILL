"""complexity_assess.py — 复杂度评级器（v2.3.0 新增）

目标：根据 CR / 本地模块 diff 的客观指标把评审工作量路由到三档，
      让「少量修改」快走 Lite prompt、「大量或高风险修改」走 Deep prompt，
      不遗漏问题的前提下提升性价比。

输入：prepare_context() 产出的 ctx dict
输出：dict，形如
  {
    "level": "lite" | "standard" | "deep",
    "score": int,                    # 数值得分（调试用）
    "signals": [str, ...],           # 触发了哪些信号
    "reason": str,                   # 人类可读的选档原因
    "metrics": {                     # 关键指标快照
        "changed_lines": int,
        "file_count": int,
        "keyword_hits": [str, ...],
        "audit_p0": int,
        "privacy_candidate_files": int,
    },
  }

兼容：Python 3.6.9+（不使用 dataclasses / PEP 604 / PEP 585 注解）。
"""
from __future__ import absolute_import
import re
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# 阈值（保守值；v2.3.0 用户确认）
# ---------------------------------------------------------------------------
LITE_MAX_LINES = 10        # 改动行总数（insertions + deletions）不超过此值可能走 Lite
LITE_MAX_FILES = 1         # 改动文件数
DEEP_MIN_LINES = 200       # 改动行总数超过此值直接 Deep
DEEP_AUDIT_P0 = 2          # audit P0 数量达到此值直接 Deep
DEEP_PRIVACY_FILES = 3     # 含 privacy_candidates 的文件数达到此值直接 Deep

# 高风险关键词（出现在 diff text、文件路径、commit message 任意一处即命中）
# 命中一个即立刻 Deep；即便 diff 很短也不降级
DEEP_KEYWORDS = [
    # 并发同步
    r"\bmutex\b", r"\bthread\b", r"\basync\b", r"\bsemaphore\b",
    r"\bstd::atomic\b", r"\bvolatile\b", r"\bpthread_\w+", r"\bcondition_variable\b",
    r"\bshared_lock\b", r"\bunique_lock\b", r"\bReadWriteLock\b", r"\bStampedLock\b",
    r"\bsynchronized\b", r"\bsynchronized\s*\(",
    # JNI / 跨边界
    r"\bJNI\b", r"\bJNIEnv\b", r"\bjni\b",
    # 内存 / 密码学
    r"\bmemcpy\b", r"\bmemmove\b", r"\bstrcpy\b", r"\balloca\b",
    r"\bAES\b", r"\bRSA\b", r"\bSHA-?\d+\b",
    # 敏感字段
    r"\bpasswd\b", r"\bpassword\b", r"\btoken\b", r"\bsecret\b",
    r"\bcert\b", r"\bcertificate\b", r"\bprivate_key\b",
    r"\bPII\b", r"\bprivacy\b", r"\bimei\b", r"\bvin\b", r"\biccid\b",
    r"\bphone_number\b", r"\blat(itude)?\b", r"\blng\b|\blon(gitude)?\b",
    # 构建 / 清单（影响面广）
    r"\bCMakeLists\b", r"\bAndroidManifest\b", r"\bManifest\.xml\b",
    r"\bpermission\b", r"\bSELinux\b", r"\bsepolicy\b",
]

# 安全编译关键词正则（忽略大小写）
_KW_RE = re.compile("|".join(DEEP_KEYWORDS), re.IGNORECASE)

# "琐碎改动"识别启发式：命中任一即视为 "only-comment-or-format"
# 仅当 diff 的新增行全部落入下列模式，才允许 Lite
_TRIVIAL_LINE_RE = re.compile(
    r"^\s*(//|/\*|\*|\*/|#)"    # 单行/块注释
    r"|^\s*$"                    # 纯空行
    r"|^\s*#\s*include\s+[<\"]"  # 单 include
    r"|^\s*import\s+\S+\s*;?$"   # import 语句
    r"|^\s*(LOG|ALOG|DLOG|SLOG|TLOG|QLOG|MLOG)\w*\s*\("  # 日志函数调用
)

# commit message 关键字提示琐碎变更
_TRIVIAL_MSG_RE = re.compile(
    r"\b(typo|comment|format|rename|cleanup|lint|whitespace|indent|log\s*text|log\s*level)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# 核心评估函数
# ---------------------------------------------------------------------------
def assess(ctx):
    # type: (Dict[str, Any]) -> Dict[str, Any]
    """根据 ctx 评估复杂度档位。

    兼容两种 ctx 形态：
      1. Gerrit ctx（来自 gerrit_review.prepare_context）：
         含 insertions / deletions / files / audit / commit_message ...
      2. Local fallback ctx（兼容历史 ECR 数据格式，本身 v2.7.0 不再分发本地模块工具）：
         含 files[].diff_excerpt / audit_summary ...
    """
    signals = []  # type: List[str]
    metrics = {
        "changed_lines": 0,
        "file_count": 0,
        "keyword_hits": [],
        "audit_p0": 0,
        "privacy_candidate_files": 0,
    }  # type: Dict[str, Any]

    # -- 1) 改动行数 & 文件数 -----------------------------------------------
    ins = ctx.get("insertions")
    dels = ctx.get("deletions")
    if isinstance(ins, int) and isinstance(dels, int):
        metrics["changed_lines"] = ins + dels
    files = ctx.get("files") or []
    metrics["file_count"] = len([f for f in files if (f.get("path") or "").lower() != "/commit_msg"])

    # local fallback 场景没有 insertions/deletions，用 diff_excerpt 估算
    if metrics["changed_lines"] == 0 and files:
        changed = 0
        for f in files:
            diff = f.get("diff_excerpt") or ""
            for ln in diff.splitlines():
                if (ln.startswith("+") and not ln.startswith("+++")) or \
                   (ln.startswith("-") and not ln.startswith("---")):
                    changed += 1
            # 若 file 仅有 diff_lines（gerrit 格式）
            for dl in f.get("diff_lines") or []:
                if dl.get("kind") in ("+", "-"):
                    changed += 1
        metrics["changed_lines"] = changed

    # -- 2) 高风险关键词扫描 ------------------------------------------------
    commit_msg = ctx.get("commit_message") or ""
    hay_list = [commit_msg]  # type: List[str]
    for f in files:
        path = f.get("path") or ""
        hay_list.append(path)
        # gerrit 格式
        for dl in f.get("diff_lines") or []:
            text = dl.get("text") or ""
            hay_list.append(text)
        # local 格式
        diff_ex = f.get("diff_excerpt") or ""
        if diff_ex:
            hay_list.append(diff_ex)

    kw_hits = set()
    for hay in hay_list:
        if not hay:
            continue
        for m in _KW_RE.finditer(hay):
            kw_hits.add(m.group(0).lower())
    metrics["keyword_hits"] = sorted(kw_hits)

    # -- 3) Preflight audit P0 计数 -----------------------------------------
    # gerrit: ctx['audit']['summary']['P0']
    audit = ctx.get("audit") or {}
    summ = audit.get("summary") or {}
    if isinstance(summ.get("P0"), int):
        metrics["audit_p0"] = summ["P0"]

    # local: audit_summary.hit_counts（未分级，保守视为 0）
    # Preflight 级别的 P0 主要来自 gerrit_audit；此处 local 分支兼容历史数据格式

    # -- 4) privacy 候选文件数 ----------------------------------------------
    priv = ctx.get("privacy_candidates")
    if isinstance(priv, list):
        metrics["privacy_candidate_files"] = len(priv)
    else:
        # gerrit 场景：privacy scan 结果落在 audit.comments 里，按 key 计数
        pc_keys = [k for k in (audit.get("comments") or {}).keys()
                   if "privacy" in (k or "").lower()]
        metrics["privacy_candidate_files"] = len(pc_keys)

    # -- 5) 档位决策（从强到弱）--------------------------------------------
    # 5a) Deep 强触发
    if metrics["changed_lines"] > DEEP_MIN_LINES:
        signals.append("changed_lines>%d" % DEEP_MIN_LINES)
    if metrics["keyword_hits"]:
        signals.append("high_risk_keyword:%s" % ",".join(metrics["keyword_hits"][:5]))
    if metrics["audit_p0"] >= DEEP_AUDIT_P0:
        signals.append("audit_p0>=%d" % DEEP_AUDIT_P0)
    if metrics["privacy_candidate_files"] >= DEEP_PRIVACY_FILES:
        signals.append("privacy_candidate_files>=%d" % DEEP_PRIVACY_FILES)

    if signals:
        level = "deep"
        reason = "触发 Deep 档信号：" + "; ".join(signals)
        return {
            "level": level, "score": 10, "signals": signals,
            "reason": reason, "metrics": metrics,
        }

    # 5b) Lite 条件（全部满足）
    lite_blocked = []  # type: List[str]

    # 改动行数
    if metrics["changed_lines"] > LITE_MAX_LINES:
        lite_blocked.append("changed_lines=%d>%d" % (metrics["changed_lines"], LITE_MAX_LINES))
    # 文件数
    if metrics["file_count"] > LITE_MAX_FILES:
        lite_blocked.append("file_count=%d>%d" % (metrics["file_count"], LITE_MAX_FILES))
    # Preflight 有任何 P0 / P1 → 不允许 Lite（保守）
    p0 = metrics["audit_p0"]
    p1 = summ.get("P1", 0) if isinstance(summ, dict) else 0
    if p0 > 0 or (isinstance(p1, int) and p1 > 0):
        lite_blocked.append("audit_has_P0/P1(%d/%d)" % (p0, p1))
    # 隐私候选 → 不允许 Lite
    if metrics["privacy_candidate_files"] > 0:
        lite_blocked.append("privacy_candidates>0")
    # diff 非 "trivial-only"
    if metrics["changed_lines"] > 0:
        trivial_ok = _diff_is_trivial_only(files)
        if not trivial_ok:
            lite_blocked.append("diff_has_non_trivial_lines")

    if not lite_blocked:
        # 命中 commit message typo/format 关键字更保险一些
        extra = []
        if _TRIVIAL_MSG_RE.search(commit_msg):
            extra.append("commit_msg_hint:trivial")
        return {
            "level": "lite", "score": 1,
            "signals": extra or ["all_lite_conditions_met"],
            "reason": "改动小且全为注释/格式/日志文本/include/import，无 Preflight 阻塞",
            "metrics": metrics,
        }

    # 5c) 默认 Standard
    return {
        "level": "standard", "score": 5,
        "signals": lite_blocked,
        "reason": "未达 Lite 条件，也未触发 Deep 信号；走标准 7 维评审",
        "metrics": metrics,
    }


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------
def _diff_is_trivial_only(files):
    # type: (List[Dict[str, Any]]) -> bool
    """返回 True iff 所有新增行都匹配 _TRIVIAL_LINE_RE。"""
    any_line = False
    for f in files:
        path = (f.get("path") or "").lower()
        if path in ("/commit_msg", "commit_msg"):
            continue
        # gerrit 格式
        for dl in f.get("diff_lines") or []:
            if dl.get("kind") == "+":
                any_line = True
                text = (dl.get("text") or "").rstrip()
                if text and not _TRIVIAL_LINE_RE.match(text):
                    return False
        # local 格式
        diff = f.get("diff_excerpt") or ""
        for ln in diff.splitlines():
            if ln.startswith("+") and not ln.startswith("+++"):
                any_line = True
                body = ln[1:]
                if body.strip() and not _TRIVIAL_LINE_RE.match(body):
                    return False
    return any_line  # 至少要有一行改动才视为 trivial；全无改动保持默认 standard


# ---------------------------------------------------------------------------
# CLI（自测用）
# ---------------------------------------------------------------------------
def _cli():
    import argparse, json, sys
    ap = argparse.ArgumentParser(description="Complexity assessor (v2.3.0)")
    ap.add_argument("ctx_json", nargs="?", help="prepared ctx JSON file; omit to read stdin")
    ap.add_argument("--pretty", action="store_true")
    a = ap.parse_args()
    if a.ctx_json:
        with open(a.ctx_json, "r", encoding="utf-8") as fh:
            ctx = json.load(fh)
    else:
        ctx = json.load(sys.stdin)
    res = assess(ctx)
    print(json.dumps(res, ensure_ascii=False,
                     indent=2 if a.pretty else None))


if __name__ == "__main__":
    _cli()
