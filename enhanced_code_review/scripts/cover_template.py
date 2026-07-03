"""cover_template.py — enhanced_code_review v2.5.3 统一 cover 模板生成器.

源自 enhanced_code_review v2.4.0；v2.7.0 在 gerrit-review 主线合并并扩到 8 维。

v2.5.2（模板强约束）：
  - LLM 的 cover 字段只允许写「纯结论散文」，模板抬头 / 顶部结论 H3 / 8 大维度矩阵 /
    Preflight / cherry-pick 复用块 / 落款等结构一律由本模块统一渲染，杜绝「模型自己写模板」。
  - `_sanitize_llm_summary` 在渲染 LLM 段前剥离任何误塞入的模板结构标记，保证散文纯净，
    不与模板自动生成的同名结构重复。
  - cherry-pick 复用档识别强化：`render_from_review_and_ctx` 同时认
    `review.cherry_pick_info.reuse` 与 `ctx.cherry_pick.reuse`，缺 base_info 时从
    ctx.cherry_pick 兜底合成，保证 cherry-pick 一定走 cherry-pick 模板。

四档 + Reply-Aware 增量评审叠加层：
  lite / standard / deep / cherry_pick_reuse （+ incremental 叠加）

模板硬要求（每档都必现）：
  - skill 名 + 版本号（header 第一行）
  - 顶部 H3「评审结论：<分数>（<一句话>）」（符合 references/13-cover-format-spec.md）
  - CR 基本信息（CR 号 + revision 短 sha + Jira + 分支）
  - 档位徽章（🟢 Lite / 🟡 Standard / 🔴 Deep / 🔁 Cherry-pick 复用 / 🔄 Incremental 叠加）
  - 7 大维度扫描表（✅/⚠️/❌/⚪ 图标）
  - 增量评审汇总（若 prior_review_context.has_prior_review=true 或 review.incremental_summary 非空）
  - 落款（自动生成 + 评级 + 信号来源）

档位差异：
  lite:              skill 标识 + Preflight 计数 + LLM 短文（不渲染 7+1 矩阵表）
  standard:          skill 标识 + Preflight + 7+1 矩阵 + 并发规则「hit≥1 才列」 + LLM 段
  deep:              standard 之上追加 adversarial_qa 统计 + 并发规则「全量 N 行表」
  cherry_pick_reuse: skill 标识 + 复用依据 + 基线结论 + LLM 段（说明"原样贴出"）
  incremental:       上述任一档位之上叠加「增量评审汇总」表（v2.4.0 新增）

Python 3.6.9 兼容：不使用 f-string `=` 调试语法、不使用 PEP 604 联合类型注解。
"""
import json
from typing import Dict, Optional


SKILL_NAME = "enhanced_code_review"
SKILL_VERSION = "2.5.5"

# v2.5.2：模板结构标记——LLM 的 cover 自由段若误塞整段模板，逐行剥离这些结构标记，
# 只保留纯结论散文，杜绝「模型自己写模板」导致 cover 双重渲染 / 结构漂移。
# 标记均为「emoji + 固定短语」，与正常评审散文碰撞概率极低。
_STRUCT_HEAD_MARKERS = (
    "## 🤖 ",            # header（skill 名 + 版本 + 徽章）
    "### 评审结论：",      # 顶部 H3 结论块
    "### 📊 Preflight",   # Preflight 计数表
    "### 8 大维度扫描",    # 维度矩阵标题
    "### 7 大维度扫描",    # 旧维度矩阵标题（向后兼容）
    "### 🔬 并发规则汇总",  # 并发规则明细
    "### 🔁 Cherry-pick",  # cherry-pick 复用块
    "### 📌 基线结论",      # cherry-pick 基线结论
    "### 增量评审汇总",     # Reply-Aware 增量汇总
    "### 📝 LLM 评审结论",  # LLM 段标题本身（模板会自动加）
)


def _sanitize_llm_summary(text):
    """v2.5.2：从 LLM 的 cover 自由段剥离模板结构标记，只保留纯结论散文。

    防御「模型自己写整段模板」：若 LLM 把 header / 顶部结论 H3 / 维度矩阵 /
    Preflight / cherry-pick 块 / 落款等模板结构塞进 cover 字段，渲染时会与
    cover_template 自动生成的同名结构重复。本函数：
      1) 若文本含「### 📝 LLM 评审结论」标记，优先抽取该标记之后的真实散文；
      2) 逐行丢弃以模板结构标记开头的行，以及落款「*🤖 由 ... 自动生成」行；
      3) 去掉首尾空行；若清洗后为空则回退原文（避免误伤极端短结论）。
    """
    if not text or not isinstance(text, str):
        return text
    marker = "### 📝 LLM 评审结论"
    if marker in text:
        text = text.split(marker)[-1]
    out = []
    for ln in text.split("\n"):
        s = ln.strip()
        if s.startswith("*🤖 由 "):
            continue
        if any(s.startswith(m) for m in _STRUCT_HEAD_MARKERS):
            continue
        out.append(ln)
    cleaned = "\n".join(out).strip()
    return cleaned or text.strip()

LEVEL_BADGE = {
    "lite": "🟢 Lite",
    "standard": "🟡 Standard",
    "deep": "🔴 Deep",
    "cherry_pick_reuse": "🔁 Cherry-pick 复用",
}
# v2.4.0 增量评审叠加徽章（与 level 徽章拼接）
INCREMENTAL_BADGE = "🔄 Incremental"

# 8 大维度固定显示顺序（id 对应 review JSON 的 dimensions_scanned key）
# v2.7.0：新增 platform_design 作为第 8 维度（软规则，P2/P3）
DIMENSIONS = [
    ("solid",                       "SOLID 原则"),
    ("security",                    "安全（OWASP/CWE/ISO 21434）"),
    ("performance",                 "性能"),
    ("error_handling",              "错误处理 + 边界"),
    ("code_quality_style",          "代码质量 + 风格（Google Style）"),
    ("automotive",                  "车载中间件（AUTOSAR/ISO 26262）"),
    ("privacy_compliance",          "隐私合规"),
    ("platform_design",             "平台化设计共识（P2/P3 软规则）"),
]

# 4.5 并发维度 id → 显示名 + 规则总数
# v2.5.5 新增 selinux_policy（上下文门控专项，仅 SELinux 改动 CR 显示为 4.6 行）
CONCURRENCY_DIMS = {
    "cpp_concurrency_stl":          ("C++ 并发 + STL", 12),
    "java_concurrency_collection":  ("Java/Kotlin 并发 + 集合", 12),
    "c_concurrency":                ("C 并发",             15),
    "selinux_policy":               ("SELinux 策略专项",   14),
}


def _safe(obj, key, default=None):
    """从 dict 安全取值。"""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def _score_one_liner(score, p0, p1, p2, p3):
    """顶部结论 H3 的分数 + 一句话（v2.4.0 新增，符合 13-cover-format-spec.md）。"""
    try:
        s = int(score) if score is not None else 0
    except (TypeError, ValueError):
        s = 0
    if s >= 1:
        sign = "+{0}".format(s)
        summary_tail = "可合入"
        issues = int(p1 or 0) + int(p2 or 0) + int(p3 or 0)
        if issues:
            summary_tail = "可合入，{0} 条改进建议".format(issues)
    elif s == 0:
        sign = "0"
        summary_tail = "持留"
    else:
        sign = str(s)
        p0_i = int(p0 or 0)
        p1_i = int(p1 or 0)
        if p0_i:
            summary_tail = "不可合入，{0} 条 P0".format(p0_i)
        elif p1_i:
            summary_tail = "不可合入，{0} 条 P1".format(p1_i)
        else:
            summary_tail = "不可合入"
    return sign, summary_tail


def _render_conclusion_top(meta, score, audit_summary, incremental_summary=None):
    """顶部 H3「评审结论：<分数>（<一句话>）」——按 references/13-cover-format-spec.md 硬要求。"""
    s = audit_summary or {}
    p0 = _safe(s, "P0", 0)
    p1 = _safe(s, "P1", 0)
    p2 = _safe(s, "P2", 0)
    p3 = _safe(s, "P3", 0)
    sign, tail = _score_one_liner(score, p0, p1, p2, p3)
    # 增量标注
    extra = ""
    if incremental_summary and isinstance(incremental_summary, dict):
        prior = incremental_summary.get("prior_total", 0)
        resolved = incremental_summary.get("resolved", 0)
        new_n = incremental_summary.get("new_findings", 0)
        extra = "，增量：前 {0} 条 → 已修 {1} / 新发现 {2}".format(prior, resolved, new_n)
    return [
        "### 评审结论：{0}（{1}{2}）".format(sign, tail, extra),
        "",
    ]


def _render_header(meta):
    """header：skill 名 + 版本 + 档位徽章（+ 增量叠加徽章） + CR 基本信息。"""
    level = meta.get("level", "standard")
    badge = LEVEL_BADGE.get(level, level)
    if meta.get("is_incremental"):
        badge = "{0} · {1}".format(badge, INCREMENTAL_BADGE)
    cr = meta.get("cr", "-")
    rev = (meta.get("revision") or "")[:8] or "-"
    jira = meta.get("jira") or "N/A"
    branch = meta.get("branch") or "-"
    url = meta.get("url") or ""

    cr_link = "[{0}]({1})".format(cr, url) if url else str(cr)

    return [
        "## 🤖 {0} v{1} · {2}".format(SKILL_NAME, SKILL_VERSION, badge),
        "",
        "> **CR** {0} · **revision** `{1}` · **Jira** `{2}` · **分支** `{3}`".format(
            cr_link, rev, jira, branch
        ),
        "",
    ]


def _render_cherry_pick_hint(cp_info):
    """对 standard/deep 档：若识别为 cherry-pick 但未复用（diff 不一致），加提示行。"""
    if not isinstance(cp_info, dict) or not cp_info.get("is_cherry_pick"):
        return []
    if cp_info.get("reuse"):
        return []  # 走 cherry_pick_reuse 档
    base_cr = cp_info.get("base_cr")
    diff_id = cp_info.get("diff_identical")
    base_url = cp_info.get("base_url") or ""
    base_link = "[CR {0}]({1})".format(base_cr, base_url) if base_url else "CR {0}".format(base_cr)
    if diff_id is False:
        reason = "diff 与基线不全等（KP31/T1V 分支差异或 rebase 调整），按独立 CR 评审"
    else:
        reason = "基线尚无评审或检测异常，按独立 CR 评审"
    return [
        "> ℹ️ **Cherry-pick 提示**：识别为 {0} 的 cherry-pick；{1}。".format(base_link, reason),
        "",
    ]


def _render_preflight(audit_summary):
    """Preflight 机械扫描计数表。"""
    s = audit_summary or {}
    p0 = _safe(s, "P0", 0)
    p1 = _safe(s, "P1", 0)
    p2 = _safe(s, "P2", 0)
    p3 = _safe(s, "P3", 0)
    pc = _safe(s, "privacy_candidates", 0)
    return [
        "### 📊 Preflight 机械扫描",
        "",
        "| 项 | 计数 |",
        "|---|---|",
        "| P0 | {0} |".format(p0),
        "| P1 | {0} |".format(p1),
        "| P2 | {0} |".format(p2),
        "| P3 | {0} |".format(p3),
        "| 隐私合规候选 | {0} |".format(pc),
        "",
    ]


def _status_cell(dim_info):
    """dimensions_scanned[k] → 状态单元格字符（v2.4.0 符合 13-cover-format-spec 图标）。

    图标约定：
      ✅ scanned 且无 finding
      ⚠️ scanned 且有 finding（即使 1 条也要预警色）
      ❌ 被明确标注 scanned=false 且有 finding（罕见：降级）
      ⚪ N/A 未扫描或信息缺失
    """
    if not isinstance(dim_info, dict):
        return "⚪ N/A"
    scanned = dim_info.get("scanned")
    findings = dim_info.get("findings")
    try:
        n = int(findings) if findings is not None else 0
    except (TypeError, ValueError):
        n = 0
    if scanned is True:
        return "⚠️ {0} findings".format(n) if n > 0 else "✅ 无"
    if scanned is False and n > 0:
        return "❌ 未扫描但有疑点 ({0})".format(n)
    return "⚪ N/A"


def _findings_cell(dim_info):
    """发现数单元格。"""
    if not isinstance(dim_info, dict):
        return "—"
    n = dim_info.get("findings")
    if n is None:
        return "—"
    return str(n)


def _render_dimension_matrix(dims, ctx_languages):
    """渲染 7+1 维 + 4.5 并发行（档位 standard/deep 用）。

    v2.4.0 改用 ### H3「7 大维度扫描」符合 references/13-cover-format-spec.md。

    ctx_languages: list[dict] 格式同 ctx['languages']，每个含 'lang' key。
    """
    lines = [
        "### 8 大维度扫描",
        "",
        "| # | 维度 | 结果 |",
        "|---|---|---|",
    ]
    dims = dims or {}
    for idx, (dim_id, disp) in enumerate(DIMENSIONS, 1):
        info = dims.get(dim_id, {})
        lines.append("| {0} | {1} | {2} |".format(idx, disp, _status_cell(info)))

    # 4.5 并发行 / 4.6 SELinux 专项行：按 ctx['languages'] 显示
    lang_rows = []      # 并发（C/C++/Java）
    selinux_rows = []   # v2.5.5 SELinux 策略专项（上下文门控）
    for lang_info in (ctx_languages or []):
        lang = lang_info.get("lang", "")
        dim_id = {
            "C++": "cpp_concurrency_stl",
            "Java/Kotlin": "java_concurrency_collection",
            "C": "c_concurrency",
            "SELinux": "selinux_policy",
        }.get(lang)
        if not dim_id:
            continue
        disp, rule_count = CONCURRENCY_DIMS[dim_id]
        info = dims.get(dim_id, {})
        if dim_id == "selinux_policy":
            selinux_rows.append("| 4.6 | {0}（{1} 条规则） | {2} |".format(
                disp, rule_count, _status_cell(info)
            ))
        else:
            lang_rows.append("| 4.5 | {0}（{1} 条规则） | {2} |".format(
                disp, rule_count, _status_cell(info)
            ))

    if not lang_rows:
        lines.append("| 4.5 | 并发专项 | ⚪ N/A（无 C/C++/Java 代码） |")
    else:
        lines.extend(lang_rows)
    # 仅在 SELinux 上下文命中时显示 4.6 行，避免对普通 CR 制造噪声
    if selinux_rows:
        lines.extend(selinux_rows)
    lines.append("")
    return lines


def _render_incremental_summary(incremental_summary, reply_disposition):
    """v2.4.0 新增：增量评审汇总块（符合 13-cover-format-spec.md §7）。"""
    if not incremental_summary or not isinstance(incremental_summary, dict):
        return []
    prior = incremental_summary.get("prior_total", 0)
    resolved = incremental_summary.get("resolved", 0)
    persist = incremental_summary.get("persist", 0)
    partial = incremental_summary.get("partial", 0)
    dropped = incremental_summary.get("dropped_by_reply", 0)
    downgraded = incremental_summary.get("downgraded_by_note", 0)
    code_gone = incremental_summary.get("code_no_longer_exists", 0)
    new_n = incremental_summary.get("new_findings", 0)
    lines = [
        "### 增量评审汇总（v2.4.0 Reply-Aware）",
        "",
        "| 指标 | 数量 |",
        "|---|---|",
        "| 前次评论总数 | {0} |".format(prior),
        "| 已修复 (resolved) | {0} |".format(resolved),
        "| 未修复 (persist) | {0} |".format(persist),
        "| 部分修复 (partial) | {0} |".format(partial),
        "| owner reply 采纳 (dropped_by_reply) | {0} |".format(dropped),
        "| 备注降级 (downgraded_by_note) | {0} |".format(downgraded),
        "| 代码不存在 (code_no_longer_exists) | {0} |".format(code_gone),
        "| 本次新发现 (new_findings) | {0} |".format(new_n),
        "",
    ]
    # 明细前 5 条 disposition（避免 cover 过长）
    if isinstance(reply_disposition, list) and reply_disposition:
        lines.append("<details><summary>Reply 处置明细（前 5 条）</summary>")
        lines.append("")
        lines.append("| # | 原等级 → 新 | 处置 | 原因 |")
        lines.append("|---|---|---|---|")
        for i, item in enumerate(reply_disposition[:5], 1):
            if not isinstance(item, dict):
                continue
            orig = item.get("original_level") or "?"
            new_l = item.get("new_level") or "—"
            disp = item.get("disposition") or "?"
            reason = (item.get("reason") or "")[:80].replace("|", "｜")
            lines.append("| {0} | {1} → {2} | `{3}` | {4} |".format(i, orig, new_l, disp, reason))
        lines.append("")
        lines.append("</details>")
        lines.append("")
    return lines


def _render_concurrency_details(level, rule_check_table, adversarial_qa=None):
    """4.5 并发规则明细（standard 档：hit≥1 才列；deep 档：全量表 + 对抗质询）。"""
    lines = ["### 🔬 并发规则汇总", ""]

    if level == "lite":
        lines.append("> Lite 档：不逐条扫描并发规则（短改动低风险）。")
        lines.append("")
        return lines

    table = rule_check_table or {}
    if not table:
        lines.append("> 本 CR 无 C/C++/Java 代码，无需并发规则扫描。")
        lines.append("")
        return lines

    if level == "standard":
        # 只列命中的规则
        hits = []
        for lang, rules in table.items():
            if not isinstance(rules, dict):
                continue
            for rid, entry in rules.items():
                n = _safe(entry, "findings", 0)
                if isinstance(n, int) and n > 0:
                    hits.append((lang, rid, n))
        if not hits:
            lines.append("> Standard 档：逐条扫描完毕，**0 条规则命中**。")
            lines.append("")
            return lines
        lines.append("> Standard 档：仅列出 hit ≥ 1 的规则。")
        lines.append("")
        lines.append("| 语言 | 规则 ID | 命中数 |")
        lines.append("|---|---|---|")
        for lang, rid, n in hits:
            lines.append("| {0} | `{1}` | {2} |".format(lang, rid, n))
        lines.append("")
        return lines

    # deep 档：全量 N 行表 + adversarial_qa 统计
    lines.append("> Deep 档：全量规则逐条结果（含 0 发现也列）。")
    lines.append("")
    lines.append("| 语言 | 规则 ID | scanned | 命中数 |")
    lines.append("|---|---|---|---|")
    for lang, rules in table.items():
        if not isinstance(rules, dict):
            continue
        for rid, entry in rules.items():
            scanned = "✅" if _safe(entry, "scanned") else "❌"
            n = _safe(entry, "findings", 0)
            lines.append("| {0} | `{1}` | {2} | {3} |".format(lang, rid, scanned, n))
    lines.append("")

    qa_count = len(adversarial_qa or [])
    if qa_count > 0:
        lines.append("**对抗式三问已附：{0} 条 P0/P1 各含反方/反例/证据**。".format(qa_count))
        lines.append("")
    return lines


def _render_cherry_pick(meta, base_info):
    """cherry_pick_reuse 档：复用块。"""
    base_cr = _safe(base_info, "base_cr", "?")
    base_score = _safe(base_info, "base_score", "?")
    base_summary = _safe(base_info, "base_summary", "(无摘要)")
    signals = _safe(base_info, "signals", {})

    return [
        "### 🔁 Cherry-pick 复用依据",
        "",
        "本 CR 识别为 **CR {0}** 的 cherry-pick，diff 与基线全等；直接复用基线评审结果，避免重复扫描。".format(base_cr),
        "",
        "| 信号 | 值 |",
        "|---|---|",
        "| `cherry_pick_of_change` API | {0} |".format(_safe(signals, "api", "—")),
        "| Change-Id 匹配 | {0} |".format(_safe(signals, "change_id_match", "—")),
        "| diff sha256 全等 | {0} |".format(_safe(signals, "diff_identical", "—")),
        "",
        "### 📌 基线结论",
        "",
        "- 基线 CR：[{0}]({1}) · 打分 **{2}**".format(
            base_cr, _safe(base_info, "base_url", ""), base_score
        ),
        "- 基线摘要：{0}".format(base_summary),
        "",
    ]


def _render_llm_summary(llm_summary):
    """LLM 自由段（放 cover 最后）。

    v2.5.2：先经 `_sanitize_llm_summary` 剥离模型误塞的模板结构，确保此处只渲染纯散文，
    标题「### 📝 LLM 评审结论」由模板统一加，不依赖 LLM 自带。
    """
    llm_summary = _sanitize_llm_summary(llm_summary)
    if not llm_summary:
        llm_summary = "_LLM 未提供结论段。_"
    return [
        "### 📝 LLM 评审结论",
        "",
        llm_summary.rstrip(),
        "",
    ]


def _render_footer(meta):
    """落款。"""
    level = meta.get("level", "standard")
    signals = meta.get("signals", "—")
    if isinstance(signals, (list, tuple)):
        signals = ", ".join(str(s) for s in signals) or "—"
    return [
        "---",
        "*🤖 由 {0} skill v{1} 自动生成 · 评级 `{2}` · 信号 `{3}`*".format(
            SKILL_NAME, SKILL_VERSION, level, signals
        ),
    ]


def render_cover(meta, audit_summary=None, dims=None, rule_check_table=None,
                 llm_summary="", adversarial_qa=None, base_info=None,
                 ctx_languages=None, cherry_pick_info=None, score=None,
                 incremental_summary=None, reply_disposition=None):
    """主入口：按 meta["level"] 渲染完整 cover markdown.

    v2.4.0 新增参数：
      score                review.score（用于顶部 H3 结论块的分数）
      incremental_summary  review.incremental_summary（Reply-Aware 汇总表）
      reply_disposition    review.reply_disposition（明细前 5 条）

    其它参数同 v2.3.1。

    返回：str，完整 cover markdown（含末尾换行）。
    """
    meta = dict(meta or {})
    meta.setdefault("skill_name", SKILL_NAME)
    meta.setdefault("skill_version", SKILL_VERSION)
    level = meta.get("level", "standard")
    is_incr = bool(meta.get("is_incremental")) or bool(incremental_summary)
    meta["is_incremental"] = is_incr

    out = []
    # v2.4.0 顶部 H3 结论块（所有档位都要）
    out.extend(_render_conclusion_top(meta, score, audit_summary, incremental_summary))
    out.extend(_render_header(meta))

    if level == "cherry_pick_reuse":
        out.extend(_render_cherry_pick(meta, base_info or {}))
        out.extend(_render_preflight(audit_summary or {}))
        if is_incr:
            out.extend(_render_incremental_summary(incremental_summary, reply_disposition))
        out.extend(_render_llm_summary(llm_summary))
        out.extend(_render_footer(meta))
        return "\n".join(out) + "\n"

    # standard/deep/lite 档：若识别为 cherry-pick 但未复用，加提示行
    out.extend(_render_cherry_pick_hint(cherry_pick_info))

    # Preflight 所有档位都有
    out.extend(_render_preflight(audit_summary or {}))

    if level == "lite":
        # Lite 不渲染 7+1 矩阵表，只给 LLM 自由段
        out.extend([
            "> Lite 档：短改动低风险，已由 Preflight 机械扫描全量覆盖；LLM 仅复核 Jira 合规 / 低级错误 / 疑似 P0 漏诊。",
            "",
        ])
    else:
        # Standard / Deep 渲染 7+1 矩阵 + 并发汇总
        out.extend(_render_dimension_matrix(dims, ctx_languages))
        out.extend(_render_concurrency_details(level, rule_check_table, adversarial_qa))

    # v2.4.0：任何档位（lite/standard/deep），有增量就渲染
    if is_incr:
        out.extend(_render_incremental_summary(incremental_summary, reply_disposition))

    out.extend(_render_llm_summary(llm_summary))
    out.extend(_render_footer(meta))
    return "\n".join(out) + "\n"


# 便于外部"按 review.json + ctx 一键生成 cover"
def render_from_review_and_ctx(review, ctx):
    """从 review.json + ctx 直接抽取字段并渲染 cover。

    review.json 约定字段：
      score / cover(LLM 自由段) / dimensions_scanned / rule_check_table /
      adversarial_qa / complexity_level / cherry_pick_info /
      reply_disposition / incremental_summary (v2.4.0)
    ctx 约定字段：
      cr / revision / project / branch / jira / url /
      audit.summary / complexity / languages /
      prior_review_context / review_decision (v2.4.0)
    """
    review = review or {}
    ctx = ctx or {}

    audit_summary = _safe(ctx.get("audit"), "summary", {})
    # privacy_candidates 可能是 list 或数
    pc = 0
    audit = ctx.get("audit") or {}
    raw_pc = audit.get("privacy_candidates") or ctx.get("privacy_candidates") or []
    if isinstance(raw_pc, list):
        for item in raw_pc:
            if isinstance(item, dict):
                pc += len(item.get("candidates") or [])
            else:
                pc += 1
    elif isinstance(raw_pc, int):
        pc = raw_pc
    audit_summary = dict(audit_summary)
    audit_summary.setdefault("privacy_candidates", pc)

    complexity = ctx.get("complexity") or {}
    level = (
        review.get("complexity_level")
        or complexity.get("level")
        or "standard"
    )
    # cherry-pick 档位优先（v2.5.2：同时认 review.cherry_pick_info 与 ctx.cherry_pick，
    # 缺哪个用另一个兜底，保证 cherry-pick 复用一定走 cherry-pick 模板）。
    review_cpi = review.get("cherry_pick_info") or {}
    ctx_cpi = ctx.get("cherry_pick") or {}
    cp_base_info = review_cpi if review_cpi.get("base_cr") else ctx_cpi
    if review_cpi.get("reuse") or ctx_cpi.get("reuse"):
        level = "cherry_pick_reuse"

    # v2.4.0: 识别是否为增量评审
    decision = ctx.get("review_decision") or {}
    prior = ctx.get("prior_review_context") or {}
    incr_summary = review.get("incremental_summary")
    reply_disp = review.get("reply_disposition")
    is_incr = bool(decision.get("is_incremental")) or bool(incr_summary) or bool(prior.get("has_prior_review"))

    meta = {
        "cr": ctx.get("cr", "-"),
        "revision": ctx.get("revision", ""),
        "project": ctx.get("project", "-"),
        "branch": ctx.get("branch", "-"),
        "jira": ", ".join(ctx.get("jira") or []) or "N/A",
        "url": ctx.get("url", ""),
        "level": level,
        "signals": complexity.get("signals") or complexity.get("reason") or "—",
        "is_incremental": is_incr,
    }

    return render_cover(
        meta,
        audit_summary=audit_summary,
        dims=review.get("dimensions_scanned"),
        rule_check_table=review.get("rule_check_table"),
        llm_summary=review.get("cover", ""),
        adversarial_qa=review.get("adversarial_qa"),
        base_info=cp_base_info,
        ctx_languages=ctx.get("languages"),
        cherry_pick_info=ctx.get("cherry_pick"),
        score=review.get("score"),
        incremental_summary=incr_summary,
        reply_disposition=reply_disp,
    )


if __name__ == "__main__":
    # 4 档 + incremental 叠加自测
    import sys
    cases = ["lite", "standard", "deep", "cherry_pick_reuse", "incremental"]
    want = sys.argv[1] if len(sys.argv) > 1 else "standard"
    if want not in cases:
        print("usage: cover_template.py [{0}]".format("|".join(cases)))
        sys.exit(1)

    is_incr = (want == "incremental")
    base_level = "standard" if is_incr else want

    meta = {
        "cr": "1015150", "revision": "a1b2c3d4e5f6",
        "project": "cluster/soc/scripts", "branch": "al_chery-t1v_dev",
        "jira": "CHYT1V-1381", "url": "https://example.com/c/scripts/+/1015150",
        "level": base_level, "signals": ["trivial-only"] if base_level == "lite" else ["mutex", "pthread"],
        "is_incremental": is_incr,
    }
    audit = {"P0": 0, "P1": 1, "P2": 2, "P3": 1, "privacy_candidates": 0}
    dims = {
        "solid": {"scanned": True, "findings": 0},
        "security": {"scanned": True, "findings": 0},
        "performance": {"scanned": True, "findings": 0},
        "error_handling": {"scanned": True, "findings": 2},
        "code_quality_style": {"scanned": True, "findings": 1},
        "automotive": {"scanned": False},
        "privacy_compliance": {"scanned": True, "findings": 0, "candidates_dropped": 0},
        "cpp_concurrency_stl": {"scanned": True, "findings": 0},
    }
    rct = {
        "C++": {
            "C-CONC-1": {"scanned": True, "findings": 0},
            "C-CONC-2": {"scanned": True, "findings": 1},
            "C-STD-1":  {"scanned": True, "findings": 0},
        },
    }
    base_info = {
        "base_cr": "1014999", "base_url": "https://example.com/c/scripts/+/1014999",
        "base_score": "+1", "base_summary": "原 review +1, 无 P0/P1",
        "signals": {"api": True, "change_id_match": True, "diff_identical": True},
    }
    ctx_langs = [{"lang": "C++", "rule_file": "09-cpp-concurrency-stl-traps.md", "rule_ids": ["C-CONC-1"]}]
    llm = "PS3 的关键 P2（CI_TIMESTAMP 前缀不一致）已修复；剩余 3 条后续优化建议不阻塞合入。"

    extra = {"adversarial_qa": [{"comment_index": 0}, {"comment_index": 1}]} if base_level == "deep" else {}

    incr = {
        "prior_total": 4, "resolved": 2, "persist": 1, "partial": 0,
        "dropped_by_reply": 1, "downgraded_by_note": 0,
        "code_no_longer_exists": 0, "new_findings": 1,
    } if is_incr else None
    reply_d = [
        {"original_level": "P1", "new_level": None, "disposition": "resolved", "reason": "PS4 已修复"},
        {"original_level": "P1", "new_level": None, "disposition": "dropped_by_reply",
         "reason": "owner 解释：该路径由调用方保证非空，已在 L120 验证"},
        {"original_level": "P2", "new_level": None, "disposition": "persist", "reason": "仍未修复"},
    ] if is_incr else None

    print(render_cover(
        meta, audit, dims, rct, llm_summary=llm,
        base_info=base_info, ctx_languages=ctx_langs,
        score=1 if base_level != "cherry_pick_reuse" else 1,
        incremental_summary=incr, reply_disposition=reply_d, **extra,
    ))
