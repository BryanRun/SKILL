# CHANGELOG

## enhanced_code_review v2.5.5 — 2026-06-16

### 新增第 9 维「SELinux 策略专项」（上下文门控）+ JIRA CHER 前缀

**背景**：
1. 团队 Android 侧 sepolicy（`*.te` / `*.cil` / `*_contexts` / `te_macros`）改动此前无专项评审，permissive 域、通配符过度授权、W^X、削弱 neverallow、危险 capability 等高危安全问题缺乏机械化兜底。依据《Android SELinux策略平台化配置指导文档》（vendor/autolink，@李根 v1.0）+ AOSP *Security-Enhanced Linux in Android* + Android CDD §9.7 沉淀专项规则。
2. 奇瑞 Chery 项目 Jira 号前缀 `CHER`（如 `CHER-1234` / `CHERY-5678`）此前不被 `JIRA_RE` 识别，导致缺 Jira 号误报。

#### 变动

**SELinux 专项（仅 SELinux 上下文开启）**
- 新增 `references/18-selinux-policy.md`：14 条规则（4 P0 / 6 P1 / 3 P2 / 1 P3），含权威依据、反例、评论模板、评审方法论。安全红线不设 P2/P3 上限。
- `scripts/gerrit_review.py`：
  - 新增 `detect_selinux_context()` / `_is_selinux_path()` / `_selinux_lang_entry()`；命中 sepolicy 文件时向 `ctx['languages']` 追加 `lang="SELinux"`（14 `rule_ids` + `scan_hints`）。
  - `REQUIRED_DIMS` 追加 `selinux_policy`；`DIMS_ALLOW_NOT_SCANNED` 追加 `selinux_policy`（非 SELinux CR 允许 scanned=false）。
  - lang 分派新增 `elif lang=='SELinux'` → 强制 `selinux_policy.scanned=true` + `rule_check_table["SELinux"]`。
- `scripts/cover_template.py`：`SKILL_VERSION=2.5.5`；`CONCURRENCY_DIMS` 加 `selinux_policy`（14）；维度矩阵新增 **4.6 SELinux 策略专项**行，仅命中上下文时渲染。
- `scripts/local_module_prepare.py`：`TEXT_EXT` 加 `.te` / `.cil` / `.conf`；新增 `_SELINUX_BASENAMES` 放行无后缀上下文文件（`file_contexts` / `service_contexts` / `te_macros` 等）。
- `references/08-llm-review-prompt.md`：评审维度第 9 项 + Step 10 + `dimensions_scanned.selinux_policy` + `rule_check_table["SELinux"]` 14 条 + `comments[].dimension` 枚举 + 输出自检两条。
- `references/02-security.md`：顶部加 SELinux 专项交叉引用。

**JIRA CHER 前缀**
- `scripts/gerrit_client.py::JIRA_RE` 新增 `CHER[A-Z0-9]*-\d+`（兼容 CHER / CHERY / CHERxxx，`CHEESE-1` 不误命中）。
- `scripts/gerrit_audit.py`：`R.TODO_NO_OWNER` 负向断言加 `CHER`；`project_keywords` 加 `cher`；两处缺 Jira 建议文案加 `CHERxxx-nnn`。
- `scripts/local_audit.py`：TODO 负向断言加 `CHER`。

#### 验证
- 6 个改动脚本 `ast.parse` 全通过；`detect_selinux_context` 7 用例、`JIRA_RE` 6 用例、`validate_review_json` 门控（SELinux 上下文 scanned=false 拒绝 / scanned=true 通过 / 非 SELinux 允许 false）、cover 4.6 行渲染全部断言通过。

#### 不变项
`references/01 / 03~17` 不动；7+1 维评审 / 闭环增强 CL-1~CL-6 / BUILD-FAIL-1 / Reply-Aware / 复杂度自适应 / Cherry-pick / 本地模块评审 / stale-revision 修复 / 严重度↔分数门禁全部继承；review.json schema 仅新增可选维度，向后兼容；Python 3.6.9 兼容。

---

## enhanced_code_review v2.5.4 — 2026-06-10

### 修复 stale-revision bug（贴回前强制对齐 Gerrit 实时 current_revision）

**背景**：CR 1049671（CHYT1V-3692【5/6】）PS2 上，自动评审错误地投了 -1——其 cover 的 revision 标的是 PS1 的 sha `8c7acd04`，实际是基于 PS1 陈旧 diff base 误判（说「al_pa target 创建前 include(idiag_ut.cmake) 导致 IDiag UT 走 skip」），而 PS2 已把 include 移到 add_library 之后修复。志强反馈「代码已变更」时，工具仍按旧 patchset 代码出结论 + cover 标错 PS。

**根因**：`post_from_review_json` / `gerrit_post.py` 贴回时 `rev` 取自 `review.json::revision`，cover 元信息取自 `ctx.json::revision`。当这两个文件残留旧 PS sha（评审过程中 owner 又推了新 patchset），review 会被 POST 到陈旧 patchset 且 cover 显示旧 PS sha。

#### 变动

- **`scripts/gerrit_client.py` 新增 `get_current_revision(cr)`**：实时查 Gerrit `current_revision` sha + patch_set 号，返回 `(sha, ps)`。
- **`scripts/gerrit_review.py::post_from_review_json`**：POST 前调用 `get_current_revision`，若 `review.json::revision` ≠ 实时 current → 自动改写 `rev` / `review.revision` / `ctx.revision` 到最新 PS，并打 stderr `[warn] stale-revision` 告警；`rev` 已对齐但 ctx 残留旧 sha 时也同步 ctx。
- **`scripts/gerrit_post.py`**：同源守卫，两条贴回路径行为一致。
- **元数据**：`VERSION` / `skill.json` / `cover_template.SKILL_VERSION` 同步 2.5.4。

#### 验证

- 本机 Python 3.13 全量 import（13 scripts）+ py_compile 全通过。
- `get_current_revision('1049671')` 实查返回当前 PS（验证时 CR 已推进到 PS3 `9da6839e`）。
- dry-run 自测：review.json 写 PS2 旧 sha `857ff5a8` → 守卫检测到 ≠ 实时 PS3 `9da6839e`，自动改写 `rev` 与 ctx.revision 到 PS3，并打两条 stderr 告警。

#### 不变项

- 完整保留 v2.5.3 全部能力（score-severity 门禁 + 回帖模板强约束 + AUDI 前缀 + codex 兼容 + 闭环增强 CL-1~CL-6 + BUILD-FAIL-1 红线 + 平台化共识 + Reply-Aware + 复杂度自适应 + Cherry-pick + 本地模块评审 + 隐私合规三重门控）。
- `references/01~16` 全部参考文档不动；review.json schema 向后兼容。
- Python 3.6.9 兼容：新增代码全用 `.format()` + `typing`，无 f-string `=` / PEP 585/604。

---

## enhanced_code_review v2.5.3 — 2026-06-10

### 本地超集发布：在官方 v2.5.2 基础上合并回 score-severity 门禁

**背景**：官方 v2.5.2 zip（回帖模板强约束 + AUDI Jira 前缀 + codex 兼容）**不含**本地独有的严重度↔分数一致性硬门禁。本地原 2.5.0 的该门禁与 gerrit-review 同源，属质量红线能力不能丢。为避免「同名 v2.5.2 不同内容」冲突，升为 v2.5.3 发布。

#### 变动

- **合并策略**：以官方 v2.5.2 为新基线全量更新，**未接受整包覆盖**，增量移植本地独有门禁。
- **`scripts/gerrit_review.py::check_score_severity_gate`**（本地独有，与 gerrit-review 同源）：严重度↔分数一致性硬门禁
  - G1：comments / unresolved_issues 含 P0 → score 必须 ≤ -1
  - G2：命中合并冲突标记 / 编译失败等阻断关键词 → score 必须 == -2
  - G3：comments / unresolved_issues 含 P1 → score 必须 ≤ -1
  - 接入 lite / standard / deep 三档 validate_review_json 校验
- **完整保留**官方 v2.5.2 全部能力：回帖模板强约束（gerrit_post.py / gerrit_review.py --post 统一走 cover_template，绕模板需 --allow-raw-cover 否则 exit 4；validate 硬拒 cover 自带模板结构；_sanitize_llm_summary 消毒）、AUDI Jira 前缀、codex 兼容。

#### 验证

- 本机 Python 3.13 全量 import（13 scripts）通过；py_compile 全通过
- 门禁自测：P0+score=1 → 报错；P0+score=-2 → 放行
- AUDI-12345 命中 Jira、AUDIO-1 不误命中
- SKILL_VERSION / VERSION / skill.json 同步 2.5.3

---

## enhanced_code_review v2.5.2 — 2026-06-06

### 回帖模板强约束（杜绝「模型自己写模板」）

**原则**：完整保留 v2.5.1 / v2.5.0 全部能力（闭环增强 CL-1~CL-6 / BUILD-FAIL-1 红线 / 平台化共识 / Reply-Aware / 复杂度自适应 / Cherry-pick 智能复用 / 隐私合规三重门控 / 本地模块评审）；本次仅收口「回帖 cover 绕过 skill 模板」的两个 loophole，强制所有贴回 cover 经 `cover_template` 统一渲染。

#### 问题背景

- `scripts/gerrit_post.py`：缺 ctx 时**静默退回** `review.json` 原始 cover（模型自由文本），绕过模板。
- `scripts/gerrit_review.py --post`（`post_from_review_json`）：**从不**调用 `cover_template`，一直直接 POST 模型自由 cover。
- 二者都可能让模型即兴写整段非标准模板贴到 Gerrit，跨 CR 风格不一致、结构漂移。

#### 改动

| 改动点 | 落地文件 | 说明 |
|---|---|---|
| 缺 ctx / 绕模板路径硬失败 | `scripts/gerrit_post.py` | 缺 ctx / `--no-auto-cover` / `--cover` 不再静默退回裸 cover，改 `exit 4`；新增 `--allow-raw-cover` 显式放行（stderr 告警） |
| `--post` 统一走模板 | `scripts/gerrit_review.py::post_from_review_json` | 贴回前调用 `cover_template.render_from_review_and_ctx`；缺 `--ctx` / `--no-auto-cover` 需 `--allow-raw-cover`；新增 CLI `--no-auto-cover` / `--allow-raw-cover`；新增 `cover_template` 导入 |
| validate 硬拒模型自带模板 | `scripts/gerrit_review.py::validate_review_json` | `cover` 命中 `## 🤖 enhanced_code_review` / `### 评审结论：` / `### 8 大维度扫描` / `### 📊 Preflight` / `*🤖 由 ...` 等结构标记即 `raise ReviewQualityError` 拒绝 POST |
| LLM 段消毒 + cherry-pick 强化 | `scripts/cover_template.py` | 新增 `_sanitize_llm_summary`（剥离误塞模板结构、抽取真实散文）；`render_from_review_and_ctx` cherry-pick 复用同时认 `review.cherry_pick_info` 与 `ctx.cherry_pick`，缺 base_info 从 ctx 兜底；`SKILL_VERSION` → `2.5.2` |
| **Jira 前缀补 AUDI**（2026-06-06 修订） | `scripts/gerrit_client.py::JIRA_RE` / `scripts/gerrit_audit.py` / `scripts/local_audit.py` / `references/05,06,08,08-lite` | 新增 `AUDI-\d+`（奥迪项目正式 Jira 号），同步进 `JIRA_RE`、`R.TODO_NO_OWNER` 负向断言、缺 Jira 软判断 `project_keywords`、两处缺号建议文案，及 4 篇参考文档前缀枚举；`AUDIO-1` 等不误命中 |
| 元数据 | `VERSION` / `skill.json` / `SKILL.md` / `README.md` / `CHANGELOG.md` / `references/13-cover-format-spec.md` | 同步至 v2.5.2，新增 v2.5.2 段 |

#### 验证

- `py_compile` + import：`cover_template` / `gerrit_post` / `gerrit_review` 全通过，`cover_template.SKILL_VERSION == 2.5.2`。
- `cover_template.py` 四档 + incremental 自测全 OK。
- `_sanitize_llm_summary`：模型误塞整段模板 → 只留纯散文（抬头/矩阵/落款被剥离）。
- cherry-pick：仅 `ctx.cherry_pick.reuse=true` 也能触发 cherry-pick 模板。
- `JIRA_RE`：`AUDI-12345` / `AUDI-1` 命中，`AUDIO-1` 不误命中。
- `validate_review_json`：cover 自带模板抬头 → 拒绝 POST。
- `gerrit_post.py` dry：缺 ctx `exit 4`、`--no-auto-cover` `exit 4`、`--ctx` 正常渲染 v2.5.2 模板。

#### 不变项

- `references/01~16` 全部参考文档不动（仅 `13-cover-format-spec.md` 抬头追加 v2.5.2 强约束说明）。
- review.json schema 向后兼容：标准/Deep 档 cover 本就只写散文的历史 review.json 仍可 POST。
- Python 3.6.9 兼容：新增代码全用 `.format()` + `typing`，无 f-string `=` / PEP 585/604。

---

## enhanced_code_review v2.5.1 — 2026-05-21

### codex 兼容修复（完整保留 v2.5.0 全部能力）

**原则**：完整保留 v2.5.0 全部能力（闭环增强 CL-1~CL-6 / BUILD-FAIL-1 红线 / contract scan LRU cache / contract_change_scan / cover 自动徽章升级）+ v2.4.1 全部能力（平台化设计共识 / Reply-Aware 增量评审 / 6 分支决策矩阵 / 复杂度自适应 / Cherry-pick 智能复用 / 隐私合规三重门控 / 本地模块评审）。本次**仅修复 codex 运行时兼容**，不涉及任何评审规则、维度或流程变更。

#### 修复（codex 兼容）

1. **`scripts/gerrit_audit.py`** — 移除运行时 PEP 585 类型注解
   - 新增 `from typing import Dict, List, Tuple` 导入
   - 替换 `added_by_file: dict[str, list[tuple[int, str]]]` → `Dict[str, List[Tuple[int, str]]]`
   - 替换 `context_by_file: dict[str, list[str]]` → `Dict[str, List[str]]`
   - 替换函数内局部变量 `added: list[tuple[int, str]]` / `full: list[str]` 同步切回 typing

2. **`scripts/privacy_compliance_scan.py`** — 移除 PEP 563 / PEP 585 / dataclasses 依赖
   - 移除 `from __future__ import annotations`（PEP 563，3.7+）
   - 移除 `from dataclasses import dataclass, field`（3.7+ 标准库）
   - 扩展 `typing` 导入：`Iterable, List, Optional, Pattern, Tuple, Dict`
   - `GATE_A` / `GATE_B` 注解 `list[tuple[...]]` → `List[Tuple[...]]`
   - `@dataclass class Candidate` 改写为普通 `class Candidate(object)` + 显式 `__init__`(13 个字段)，语义保持一致
   - `_pair` / `scan_file` / `scan_diff_added` / `__main__` 内所有 `list[Candidate]` / `list[str]` / `dict[..]` 同步切回 typing

#### 元数据更新

- `VERSION` `2.5.0` → `2.5.1`
- `skill.json::version` `2.5.0` → `2.5.1`；`description` 同步说明本次修复点
- **`skill.json::platform` 新增 `codex`**（原为 `["claude-code"]` → `["claude-code", "codex"]`）
- `SKILL.md` frontmatter `version` + H1 + 抬头 blockquote 同步至 v2.5.1，新增 v2.5.1 版本段
- `README.md` 抬头同步 v2.5.1 + 新增 v2.5.1 段
- **`scripts/cover_template.py::SKILL_VERSION` `"2.5.0"` → `"2.5.1"`**(运行时 cover 顶部硬约束徽章随版本号一并升级:`🤖 enhanced_code_review v2.5.1 · 🟡 Standard`)

#### 验证

- docker `python:3.6.15-slim` 全量 import：`py36 import OK`（最严格场景，PEP 585/604/dataclasses 全部不可用）
- 本机 Python 3.10.12 import：正常
- codex CLI 典型 Python 3.8+ 场景：通过（无 PEP 585/604 运行时报错）

#### 不变项（完整保留）

- references/01~16 全部参考文档不变
- 7 维评审 + 平台化共识第 8 维（P2/P3）+ 隐私合规三重门控 + 闭环增强 CL-1~CL-6 + BUILD-FAIL-1 红线**全部保留**
- review.json schema 不变（向后兼容 v2.5.0 / v2.4.1）
- 本地模块评审栈（`local_module_prepare.py` / `local_audit.py`）不变
- 其他 scripts（`gerrit_client.py` / `gerrit_review.py` / `gerrit_show.py` / `gerrit_post.py` / `gerrit_inbox.py` / `consistency_scan.py` / `cherry_pick_detect.py` / `complexity_assess.py` / `cover_template.py`）不变

---

## enhanced_code_review v2.5.0 — 2026-05-15

### 从 gerrit-review v2.7.0 合并主线 4 大新能力（完整保留 v2.4.1 全部能力）

**原则**：完整保留 ECR v2.4.1 全部能力（平台化共识 / Reply-Aware / 6 分支决策 / 复杂度自适应 / Cherry-pick 智能复用 / Topic 解耦 / 本地模块评审 / 隐私合规三重门控）+ 本地模块评审独有栈，**仅基于** gerrit-review v2.7.0 做增量合并。

#### 新增（合并自 gerrit-review v2.7.0）

1. **闭环增强机制 CL-1~CL-6**（`references/15-closeloop-enhancement.md`）
   - **CL-1 临时策略 reply 硬约束**：reply_classification 5 类（rational / temporary_with_jira / temporary_no_jira / tradeoff_no_data / no_reply）；后两类禁止豁免；含临时性关键词集（临时策略/上线前/后续 CR/这版先/TODO/简化复杂度 等）+ 4 行处置矩阵
   - **CL-2 未闭环清单 unresolved_issues 强制**：temporary_with_jira 类降级必须挂关联 Jira（CHYT1V/CHYKP31/D01/FL[1-3]/T1V/N80）并写入 review JSON 顶层 `unresolved_issues` 数组
   - **CL-3 契约变更跨 CR 上下文感知**：识别同 Jira / 同 topic 兄弟 CR，区分 context_aware_ok / single_side_p2 / mismatch_p0 三种判定；**绝对禁止仅凭契约变更就一刀切 P0**
   - **CL-4 cover 带病合入说明段强制**：`unresolved_issues` 非空时 cover 必含「⚠️ 带病合入说明」段
   - **CL-5 真修复识别 fix_mismatch**：比对 owner reply 声称的修复与代码实际变化；fix_mismatch 时维持原 P0/P1
   - **CL-6 契约硬扫候选层**：`gerrit_audit.py` 新增 `contract_change_scan` 扫 IntDef 数值 / proto field tag / Bundle key 字符串变更，默认 P2 候选

2. **BUILD-FAIL-1 预编译失败质量红线 P0**（`references/16-build-fail-redline.md`）
   - 触发：CR 当前 patchset 任一 `Verified` / `Prebuild-Check` label 被打 -1/-2
   - 处置：直接 `-2` 跳过 LLM 评审（不浪费 token，不发起 7+1 维度扫描）
   - `compute_review_decision` 新增优先级 0.5 的 mode `skip_build_failed`
   - CLI 新增 `gerrit_review.py <CR> --build-fail-fast` 快通道
   - 不识别 `CommitMsg-Check` / `StaticCode-Check`（由其他维度兜底）

3. **contract scan LRU cache（性能优化）**：兄弟 CR 查询进程级缓存 `_SIBLING_CACHE`，节省 ~30% 流量

4. **兄弟 CR 拉取改 `o=CURRENT_FILES`-only**：去掉 `o=CURRENT_REVISION` / `o=DETAILED_ACCOUNTS`

5. **cover 自动徽章升级**：`scripts/cover_template.py` 顶部硬约束 `🤖 enhanced_code_review v2.5.0 · 🟡 Standard`，增量评审叠加 `🔄 Incremental`

#### 校验规则增强

`validate_review_json` 增加 CL-1 / CL-2 / CL-4 / BUILD-FAIL-1 强制校验（在 v2.4.1 平台化共识守卫 + DIMS_ALLOW_NOT_SCANNED 之上叠加）。

#### 兼容性

- review.json schema 仅新增可选字段：`unresolved_issues` / `fix_mismatch_flag` / `contract_change_scan_results` / `reply_classification`
- 旧 review.json（v2.4.1 / v2.4.0 / v2.3.x）仍可 POST，向后兼容
- Python 3.6.9（无 PEP 585/604、无 dataclasses 依赖）

#### 未改动

- 保留：`scripts/local_audit.py` / `scripts/local_module_prepare.py` / `scripts/consistency_scan.py` / `scripts/gerrit_inbox.py`
- 保留：`references/01~07`、`references/09-cpp-concurrency-stl-traps.md`、`references/09-local-module-review.md`、`references/10-privacy-compliance.md`、`references/11/12`、`references/14-platform-design-principles.md`

---

## enhanced_code_review v2.4.1 — 2026-05-14

### 平台化设计共识第 8 维度（软规则 P2/P3）+ dimension/level 守卫（同步 gerrit-review v2.5.1）

**背景**：gerrit-review v2.5.1 在 2026-05-14 落定第 8 个评审维度 `platform_design`——来源于团队两份内部权威输出《中间件平台化策略与落地框架》+《中间件平台能力规划》。本次升级 ECR 同步增量采纳该维度，**完全不动** v2.4.0 已有的 Reply-Aware 增量评审 + 6 分支决策矩阵 + Cover 排版规范 + cover_template + cherry_pick + 复杂度自适应 + Topic 解耦 + 本地模块评审 + 隐私合规三重门控等能力。

#### 新增文件

- **`references/14-platform-design-principles.md`**（8.6KB）——平台化设计共识规则集
  - §一 平台化总目标 G1~G5（评审价值轴）
  - §二 需求三分类：🟢 通用 / 🟡 可选 / 🔴 定制
  - §三 配置化三层模型：静态（编译期）/ 动态（运行期）/ 客户（部署期）
  - §四 平台/项目/客户三层分离：下层不感知上层 / 上层不修改下层 / 跨层调用单向
  - §五 ISO 25010 八大质量属性（评审标尺）
  - §六 底座能力复用清单（通信 / 持久化 / 健康 / 启动 / 配置 / 时间 / 日志）
  - §七 8 条 PLAT 规则表（PLAT-1~PLAT-8，全 P2/P3）
    - PLAT-1 P2 硬编码项目差异
    - PLAT-2 P2 平台层引入项目/客户特化
    - PLAT-3 P2 公共接口违反治理规范
    - PLAT-4 P2 重复造底座能力
    - PLAT-5 P2 配置项无层级声明
    - PLAT-6 P3 可选需求未走配置化
    - PLAT-7 P3 缺质量属性设计说明
    - PLAT-8 P3 增量功能未对齐平台基线
  - §八 评论输出格式（依据/现象/原理/建议 + Before/After）
  - §九 与其他维度的边界（平台化是叠加不是替代）
  - §十 豁免清单（hotfix / 项目分支 / 测试 / < 30 行小 bug）
  - §十一 复盘与演进机制（每季度一次）

#### 修改文件

- **`scripts/gerrit_review.py::validate_review_json`** 升级：
  - `REQUIRED_DIMS` 末尾追加 `'platform_design'`
  - 新增 `DIMS_ALLOW_NOT_SCANNED = {'cpp_concurrency_stl', 'platform_design'}` 常量
  - 把分支 `elif d != 'cpp_concurrency_stl':` 改为 `elif d not in DIMS_ALLOW_NOT_SCANNED:`
  - 新增 **platform_design 定级守卫**：遍历 `review['comments']`，若 `dimension == 'platform_design'` 且 `level in ('P0','P1')` → 报错拒贴，提示「软规则仅 P2/P3，如确属 P0/P1 请归类到其他维度」
  - **不影响** Lite / Standard / Deep / cherry_pick_reuse 四档已有校验逻辑
- **`references/13-cover-format-spec.md`**：
  - 抬头版本标记升级为「v2.4.1 同步自 gerrit-review v2.5.1」
  - cover 骨架表格新增「平台化设计共识 (P2/P3)」一行
  - 综合评估段示例改为「7+1 维度评审 + 平台化共识扫描」+「PLAT-* 命中 N 条，仅作改进提示，不影响打分」
- **`references/08-llm-review-prompt.md`**：
  - 「评审维度」标题：`7 类完整覆盖` → `7 类完整覆盖 + 1 类软规则`
  - 新增第 8 项 `platform_design` 维度描述（含定级硬约束 + `validate_review_json` 行为）
  - User Prompt 增加 **Step 9 · 平台化设计共识** 扫描步骤（覆盖 §一~§十 + PLAT-* 前缀要求 + 豁免）
  - JSON schema `dimensions_scanned` 新增 `platform_design` 字段
  - JSON schema `comments[].dimension` 枚举末尾追加 `platform_design`，`rule_id` 注释扩展到 `PLAT-1` 起
  - 输出前自检清单追加 v2.4.1 四项（dimensions_scanned key 必填 / level 守卫 / PLAT-* 前缀 + 章节引用 / 打分独立性）
- **`SKILL.md`**：
  - description 升级为 v2.4.1，提及平台化设计共识第 8 维度
  - 顶部版本记录新增 v2.4.1 条目
  - 「完整评审维度」表格升级为「7 大必全扫 + 1 类软规则（v2.4.1 起）」，新增第 8 行 platform_design + 定级硬约束 callout
  - 自动化工作流新增 Step 9；本地模块 workflow 范围更新为 Step 2~9
  - 参考文件表格新增 `references/14-platform-design-principles.md` 一行
  - 强制最低保证清单：维度清单加 `平台化设计共识`，并追加 v2.4.1 平台化软规则 PLAT-* 约束条目
  - 与 gerrit-review 关系小节同步至 v2.5.1，分发包名升至 `enhanced_code_review-v2.4.1.zip`
- **`README.md`**：版本号 + 平台化设计共识能力简介
- **`VERSION`**：`2.4.0` → `2.4.1`

#### 未改动（继承 v2.4.0 状态）

- `scripts/gerrit_client.py`（仍保留 ECR v2.3.1 `find_related_crs` 移除状态，**不回退**到 gerrit-review v2.5.1 的 Topic 关联实现，规避 Jira 拆分多笔时误关联兄弟 CR）
- `scripts/gerrit_audit.py` / `gerrit_show.py` / `gerrit_post.py` / `gerrit_inbox.py` / `consistency_scan.py` / `privacy_compliance_scan.py` / `cherry_pick_detect.py` / `complexity_assess.py` / `cover_template.py` / `local_audit.py` / `local_module_prepare.py`
- `references/01-solid-principles.md` ~ `references/12-c-concurrency-traps.md`
- `references/08-llm-review-prompt-lite.md` / `08-llm-review-prompt-deep.md`
- `references/09-local-module-review.md` / `references/10-privacy-compliance.md`

#### 设计原则

1. **只提取共性、不提取个体**：上游文档中的业务组名、人名、项目名、项目时间节点全部不录入。只提取「需求三分类」「配置化三层模型」「三层架构分离」「ISO 25010」「底座能力清单」等可复用设计共识。
2. **低定级、不阻断合入**：平台化是「应该怎么做」的设计趋势，不是「不这么做会出 bug」的硬错误。全部规则限定 P2/P3，仅作 inline 提示，不影响 Code-Review 分数。
3. **叠加而不替代**：与现有 7 大维度并行扫描；P0/P1 依然走原有维度，平台化只加一层设计角度的 inline。
4. **完全保留 v2.4.0 所有能力**：Reply-Aware / 决策矩阵 / 增量评审 / cover 排版规范 / 复杂度自适应 / Topic 解耦 / Cover 模板化 / Cherry-pick 智能复用全部不变。

#### 上游需求来源

- 中间件平台能力规划（飞书 Wiki: `Hc3QwjkZeiaDjhkJG5pcetmGnrf`）
- 中间件平台化策略与落地框架（飞书 Wiki: `AvUyw2DNMirGk9kBC2DcK113n1f`）

---

## enhanced_code_review v2.4.0 — 2026-05-12

### Reply-Aware 增量评审 + 6 分支决策矩阵 + cover 排版规范（同步 gerrit-review v2.5.0 修正二，ECR 保留 Topic 解耦）

**背景**：gerrit-review v2.5.0 在 2026-05-12 经历上午初版 → 下午 bug fix 两轮迭代后定稿，最大升级点：
1. **Reply-Aware 增量评审**：`build_prior_review_context` 读 owner 的 inline + cover reply + score 历史 + patch_set 号变化；`compute_review_decision` 用 **6 分支决策矩阵** 替代旧的"他人已 -1 就 skip"粗粒度逻辑；
2. **P0 豁免铁律**：P0 仅可通过 owner reply 的合理性豁免，不能通过特殊备注降级；
3. **cover 排版规范**（references/13-cover-format-spec.md）：禁止散文 cover，必须顶部 H3 结论 + 7 大维度表格 + 增量评审汇总；
4. CR 1018054（PS5→PS12 代码有变动误判 skip）下午修复后定稿。

ECR v2.4.0 全面吸收以上升级，**同时保留**自身 v2.3.1 的 Topic 解耦（不回退 `find_related_crs`）、Cover 模板化（`cover_template.py` 升级到 v2.4.0）与 Cherry-pick 智能复用。

**新增脚本 API（在 `gerrit_client.py`）**：

- `is_placeholder_jira(jira_num_str)` — Jira 占位号判定（T1V-0 / T1V-001 / T1V-0099 视为占位；T1V-10 / T1V-12345 视为合规）。
- `get_change_comments(cr)` — 获取 inline comments + reply 链全量。
- `get_change_messages(cr)` — 获取 cover messages + 分数历史。
- `is_substantive_review_message(msg_text)` — 实质 / 非实质 AI 评审判定（`自动预审未通过` 等关键字 → 非实质；`评审结论 / 维度扫描 / [P0]` 等 → 实质；净文本 > 300 字符 → 实质）。
- `build_prior_review_context(cr, self_username)` — 构建完整 prior review 上下文（含 `prior_review_patch_set` / `current_patch_set` / `code_changed_since_prior_review` / `has_owner_reply` / `has_substantive_other_minus_one` 等字段）。
- `compute_review_decision(prior, current_revision=None, force=False)` — 6 分支决策函数：`incremental / proceed / skip`。

**变更**：

- `gerrit_review.py::prepare_context`：末尾注入 `ctx["prior_review_context"]` + `ctx["review_decision"]`；异常时 fallback 到 `mode=proceed`。complexity 评级 / cherry_pick 检测 / Reply-Aware 三个层次并存，互不干扰。
- `gerrit_review.py::validate_review_json`：
  - **Standard / Deep 档**：若 `prior_review_context.has_prior_review=true`，硬要求 `reply_disposition`（list）+ `incremental_summary`（dict），每条 disposition 含 `disposition` 字段。
  - **Lite 档**：`reply_disposition` / `incremental_summary` 字段必填但内容可为空 `[] / {}`。
  - **Cherry-pick_reuse 档**：不受影响。
- `gerrit_review.py::main()`：`--prepare` 模式的 stderr banner 新增 Reply-Aware 决策块（`🆕 proceed / 🔄 incremental / ⏭️ skip` + prior_review / owner_reply / other_minus_one 计数）。
- `cover_template.py`（升级至 v2.4.0）：
  - 顶部新增 `_render_conclusion_top`：`### 评审结论：<分数>（<一句话>）`（`+1` / `-1` / `+2` / `-2`，不写 0）；有增量时追加「增量：前 N → 已修 X / 新发现 Z」。
  - 维度矩阵图标统一为 `✅ 无 / ⚠️ N findings / ❌ 未扫但有疑点 / ⚪ N/A`（符合 references/13-cover-format-spec.md）。
  - 新增 `_render_incremental_summary`：渲染增量评审汇总表 + Reply 处置明细前 5 条（`<details>` 折叠）。
  - `render_from_review_and_ctx` 自动从 `ctx.review_decision.is_incremental` / `review.incremental_summary` / `prior_review_context.has_prior_review` 任一判定为增量；meta 叠加 `🔄 Incremental` 徽章。
  - `render_cover` 新增 `score / incremental_summary / reply_disposition` 参数。
  - `__main__` 自测新增 `incremental` 档位。
- `references/13-cover-format-spec.md`：同步自 gerrit-review v2.4.3，顶部加技能语境说明（「ECR cover 由 cover_template 按本文骨架自动渲染」）。
- `references/08-llm-review-prompt.md`：新增「历史评审上下文（v2.4.0 — Reply-Aware + 增量评审）」章节，含规则 A（Reply 采纳）/ B（特殊备注）/ C（增量）/ D（他人 -1 跳过）/ E（owner reply 必增量）/ F（Patch Set 变动）；输出 JSON schema 新增 `reply_disposition` + `incremental_summary` 字段；`skill_meta.version` 升至 2.4.0；自检清单追加 4 条 Reply-Aware 项。
- `references/08-llm-review-prompt-lite.md`：User Prompt 注入 prior_review_context 占位 + 增量字段必填提示。
- `references/08-llm-review-prompt-deep.md`：新增强化 6「Reply-Aware 增量评审深度要求」（P0 豁免严审 / Persist 论证三问 / 新发现走 adversarial_qa / incremental_summary 正交等式）。
- `VERSION`：`2.3.1` → `2.4.0`。

**刻意保留（不随 v2.5.0 回退）**：

- `gerrit_client.find_related_crs`：**不恢复**。v2.3.1 的 Topic 解耦依旧生效，Reply-Aware 只依赖本 CR 自身 inline / cover / score 历史。
- `gerrit_audit.py` / `gerrit_show.py` / `gerrit_post.py` / `gerrit_inbox.py`：保持 v2.3.1 版本（gerrit-review v2.5.0 在这几个文件上的变动是回退 Topic 解耦 + 丢失 auto-cover，与 ECR 目标相反）。
- `cherry_pick_detect.py` / `complexity_assess.py` / `local_module_prepare.py` / `local_audit.py`：完全保留，不受影响。
- references 01-07、09、10、11、12：与 gerrit-review v2.5.0 完全一致，无需变更。

**用户可感知效果**：

- 以后每次 Gerrit cover 都以 `### 评审结论：<分数>（<一句话>）` 开头，顶部 3 秒可读；7 大维度表格用 ✅/⚠️/❌/⚪ 图标区分状态。
- 有历史评审的 CR（increment 模式）自动在 cover 追加「增量评审汇总」表，`reply_disposition` 明细前 5 条用 `<details>` 折叠，可读性显著提升。
- `laibin 自动预审未通过` 这类纯标记 -1 不再阻止 ECR 发起完整评审（规则 2）；owner 推 patchset 本身就被视为响应（规则 6），不会漏评。
- `P0 + owner reply` 时仍要求 reply 必须有技术依据 + 可在代码中验证才允许 drop，防止 owner 口头解释绕过 P0 评判。

**兼容性**：

- 所有新字段对旧 review.json 保持向后兼容（Lite 档必填但可空 `[]/{}`；Cherry-pick_reuse 档不校验）。
- Python 3.6.9 兼容：所有新函数使用 `typing` 模块与经典 `"{0}".format()` 写法，无 f-string `=` 调试语法、无 PEP 585/604。
- 旧 CR（无 prior review）评审路径完全不变。

---

## enhanced_code_review v2.3.1 — 2026-05-08

### Topic 解耦 + Cover 模板化 + Cherry-pick 智能复用

**背景**：v2.3.0 在 CR 1015078 PS3/PS4 使用中暴露两类硬伤：
1. **Topic 误评** — `find_related_crs(jira)` 通过 Jira 号反查同组 CR，把兄弟 CR 列入"同组"让 LLM 当阻塞证据误判 -1。用户明确："review 时严禁 Jira 和 topic 关联"。
2. **Cover 风格不专业** — 完全由 LLM 即兴写，无统一骨架；不显示 skill 名/版本号；7+1 维结果靠 LLM 重述（易遗漏）；每个 PS 风格都不一样，可读性差。

**新增**：

- `scripts/cover_template.py`（~340 行，Python 3.6.9 兼容）：统一 cover 模板渲染器。四档（lite / standard / deep / cherry_pick_reuse）全覆盖。每档 cover 必含：①skill 名 + 版本号（header 首行）、②档位徽章（🟢/🟡/🔴/🔁）、③CR 基本信息（CR/revision/Jira/分支）、④Preflight 计数表、⑤自动落款（评级 + 信号来源）。Standard 档额外渲染 7+1 维矩阵表 + 并发规则汇总（hit≥1 才列）；Deep 档追加全量并发表 + adversarial_qa 统计；Cherry-pick 档加"复用依据"块。提供 `render_from_review_and_ctx(review, ctx)` 一键调用接口；可命令行 `python3 cover_template.py {lite|standard|deep|cherry_pick_reuse}` 自测 4 档样式。
- `scripts/cherry_pick_detect.py`（~180 行）：cherry-pick 三级识别器。①Gerrit 原生 `cherry_pick_of_change` 字段；②同 Change-Id 在更早 CR；③diff new-side sha256 指纹全等。三级信号全命中且基线已有评分才走复用；任一失败降级为独立 review。
- `scripts/gerrit_review.py::prepare_context`：评级后自动跑 `cherry_pick_detect`，若 `reuse=True` 把 `complexity.level` 覆盖为 `cherry_pick_reuse`，Agent 可跳过 LLM 扫描。
- `scripts/gerrit_post.py`：默认启用 auto-cover，自动加载同名 `.ctx.json` 并通过 `render_from_review_and_ctx` 包装 LLM 自由结论段；`--no-auto-cover` 可退回 v2.3.0 行为；`--ctx` 可显式指定 ctx 路径。

**移除（Topic 解耦）**：

- `gerrit_client.py::find_related_crs()` 函数体整体删除（5 行函数 + 不再需要的 docstring）。`gerrit_inbox.py` 经 grep 确认不依赖。
- `gerrit_audit.py::analyse_cr`：移除 `import find_related_crs`、`related_crs` 字段、Jira 关联 CR 循环（L94-100 原逻辑）。
- `gerrit_review.py::prepare_context`：移除 `import find_related_crs`、`ctx["related_crs"]` 字段、Jira 关联 CR 循环（L247-257 原逻辑）。
- `gerrit_show.py`：移除 `import find_related_crs` 与关联 CR 打印段（L35-43 原逻辑）。Jira 号提取保留。
- `references/08-llm-review-prompt.md`：删除 L213 `- 同组 CR：{related_crs}` 行。

**变更**：

- `validate_review_json`（`gerrit_review.py`）：
  - 新增 `cherry_pick_reuse` 档最宽松校验（仅要求 `cherry_pick_info.reuse=true + base_cr` 非空）。
  - Standard/Deep 档 cover 字段不再按 7 个维度关键词硬校验（`COVER_REQUIRED_KEYWORDS` 保留变量但停用），改由 `cover_template` 模板保证 7+1 维必现；仍要求 cover 非空。
  - 新增 `skill_meta = {name: "enhanced_code_review", version}` 字段硬要求（Lite / Standard / Deep 三档），防 LLM 漏写。
- `references/08-llm-review-prompt.md` / `-lite.md` / `-deep.md`：输出 JSON schema 新增 `skill_meta` + `cherry_pick_info` 字段说明；`cover` 字段语义改为"LLM 自由结论段（模板骨架由 gerrit_post.py 自动注入）"。

**用户可感知效果**：

- 以后每次 Gerrit cover 都会以 `🤖 enhanced_code_review v2.3.1 · 🟡 Standard` 开头，revision 短 sha + Jira + 分支一目了然，7+1 维矩阵表 + Preflight 计数表固定位置，对比跨 PS 时 diff 能精准定位"哪一维新增/修复了问题"。
- 不会再因 topic 不一致被误判 -1；Jira 号拆多笔提交 / rebase 分叉都不再影响评分。
- 同一系列 cherry-pick 只需对最早的 CR 做一次完整 review，后续分支 cherry-pick 自动复用，cover 显式标注"复用自 CR {base_cr}"+ 三级信号证据。

**兼容性**：

- review JSON schema 新增 `skill_meta` 必填、`cherry_pick_info` 可选；LLM 必须在每次输出中带上 `skill_meta` 否则 validate 拒绝 POST。
- `gerrit_post.py` 默认 auto-cover；若当前工程流程尚未把 `ctx.json` 与 `review.json` 一起落盘，首次会打印 `[warn] 未找到 ctx.json，auto-cover 退回 review.json 原 cover 字段`，不阻塞 POST。推荐 `gerrit_review.py --prepare -o /tmp/ctx_<cr>.json` + `gerrit_post.py /tmp/review_<cr>.json --ctx /tmp/ctx_<cr>.json` 流程串联。
- `--no-auto-cover` flag 留给需要完全自定义 cover 的场景。

**回滚**：所有改动局限在 `~/.cursor/skills/enhanced_code_review/`，`git revert` 一条命令。已发布 zip：`enhanced_code_review-v2.3.1.zip` + `.sha256`。

---

## enhanced_code_review v2.3.0 — 2026-05-07

### 复杂度自适应三档（Lite / Standard / Deep）— 少量修改快走、高风险修改严查

**背景**：用户反馈 v2.2.1 评审流程对任何 CR 都跑完整 7+1 维 + 39 条并发规则 + rule_check_table 硬校验，导致 typo / 注释 / 日志文案等琐碎改动也要花大量 LLM token 走全流程，性价比低。需要按客观指标自动分档，让少量修改走轻量 prompt，高风险修改走强化 prompt。

**新增**：

- `scripts/complexity_assess.py`：评级器单文件实现（~200 行，Python 3.6.9 兼容）。输入 ctx，输出 `{level, score, signals, reason, metrics}`。兼容 Gerrit 与本地模块两种 ctx 形态。
- `references/08-llm-review-prompt-lite.md`：Lite 档精简 prompt。LLM 只问 3 件事：Jira 合规 / 低级错误 / 疑似 P0 漏诊。不逐条扫 39 条并发规则、不填 rule_check_table。
- `references/08-llm-review-prompt-deep.md`：Deep 档增强 prompt。在 Standard 之上追加对抗式三问（每 P0/P1 必附反方/反例/证据）+ 关键词热点强扫 + 隐私三重门控全流程 + 分文件评审（changed_lines>200 时）。
- `scripts/gerrit_review.py`：`prepare_context` 末尾注入 `ctx["complexity"]`；CLI 加 `--force-level lite|standard|deep` 手工覆盖；启动时 stderr 打印评级 banner。
- `scripts/local_module_prepare.py`：`prepare` 后 `_attach_complexity`，本地模块路径同样支持评级；CLI 同样加 `--force-level`。
- `scripts/gerrit_review.py::validate_review_json`：按档位分叉硬校验 —— Lite 放宽（dimensions_scanned/rule_check_table 可为空，cover ≥ 80 字），Standard 保持 v2.2.1 原硬校验，Deep 追加每 P0/P1 三问 + cover ≥ 400 字。三档都强制 `complexity_level` 字段匹配。

**分档阈值**（保守）：

| 档位 | 条件 |
|------|------|
| 🟢 Lite | `changed_lines ≤ 10` **且** `file_count ≤ 1` **且** diff 全为注释/格式/日志/include/import **且** 无高风险关键词 **且** Preflight 无 P0/P1 **且** 无 privacy_candidate |
| 🔴 Deep | `changed_lines > 200` **或** 命中高风险关键词（mutex/thread/async/JNI/memcpy/AES/password/token/cert/privacy/PII/pthread_*/CMakeLists/AndroidManifest/permission/SELinux 等 30+ 项正则） **或** `audit_P0 ≥ 2` **或** `privacy_candidate_files ≥ 3` |
| 🟡 Standard | 其余（默认档，v2.2.1 原流程不变） |

**Preflight 机械扫描在所有档位都全跑**（gerrit_audit + consistency_scan + privacy_compliance_scan），不因档位下降而省略。这是质量门禁的最后防线。

**漏诊安全网**：

1. Preflight 任何 P0/P1 或 privacy_candidate 命中 → 评级器自动禁入 Lite
2. Lite 档若 LLM 产出 `score=-2` → `validate_review_json` 在 stderr 打印明显警告，提示人工 `--force-level standard` rerun，但不阻塞 POST（尊重 LLM 判断 + 留痕）
3. Deep 档每 P0/P1 必附三问自检（反方/反例/证据），答不全直接 drop 该评论
4. 评级器任何异常 → 回退 Standard，不阻断评审流程

**性价比估算**（保守假设）：

- Lite 覆盖 ~60% 流量（注释/日志/typo 类改动），LLM token 降到原 ~20%
- Standard 覆盖 ~30% 流量，token 持平
- Deep 覆盖 ~10% 流量，token 加重 ~20% 换取漏诊率下降
- **整体预期 token 消耗减少 ~45%**，质量在高风险场景不降反升

**保留**：v2.2.1 全部能力 —— 7+1 维 / 39 条并发规则集 / scan_hints 内嵌 / rule_check_table 强制 / 隐私合规三重门控 / 本地模块评审 / Python 3.6.9 兼容。

**Why 不做的事**：

- 不做 Jira-Topic 跨 CR 校验（用户明示评审不绑定 Jira ↔ topic）
- Lite 档不完全跳过 LLM（用户明示 Lite 阶段也走完整 LLM 评审，只是减少 prompt 长度）
- 评级器不做 commit message 格式校验（CR-6 职责边界，那是 `autolink-chery-commit-msg` 的事）

---

## enhanced_code_review v2.2.1 — 2026-05-03

### 同步 gerrit-review v2.4.2：scan_hints 内嵌 + rule_check_table 强制 + 飞书规则集对齐

**背景**：gerrit-review 从 v2.4.1 升级到 v2.4.2，对 Step 4.5 多语言并发专项扫描做了三项 P0 改进 — ① 把每条规则的 grep 关键词从「LLM 自行解析规则文件」下沉到 `prepare_context` 脚本层；② Output JSON 强制 `rule_check_table`，逐条规则填扫描结果；③ 校准规则 ID 与飞书三份规则集文档保持一致。enhanced_code_review 同步这些能力，并保留本地模块评审与 Python 3.6.9 兼容性。

**新增**：

- `scripts/gerrit_review.py::prepare_context`：在 `ctx['languages']` 每个 lang_info 内加 `scan_hints` 字段，包含每条规则的 `{rule, level, title, grep, check}`，LLM 按表逐条扫描。
- `references/08-llm-review-prompt.md` User Prompt：在「语言分派」段后新增「Step 4.5 扫描提示」表格，直接展示 `{scan_hints_table}`，LLM 无需自行解析规则文件。
- `references/08-llm-review-prompt.md` Output JSON Schema：新增 `rule_check_table` 字段，按语言分组（`C++` / `Java/Kotlin` / `C`），逐条规则必须填 `{scanned: true/false, findings: N}`。
- `scripts/gerrit_review.py::validate_review_json`：新增 `rule_check_table` 强制检查，按 `ctx['languages']` 动态校验每条规则是否在表中；缺失或字段不全直接拒绝 POST。

**更新**：

- `scripts/gerrit_review.py::prepare_context`：修正 C++ / Java rule_ids 与 09/11 文件实际一致 — C++ 改为 `C-CONC-1~7 / C-STD-1~2 / C-LIFE-1~3`；Java 改为 `J-CONC-1~7 / J-STD-1~2 / J-LIFE-1~3`。
- `SKILL.md`：版本 v2.2.1，description 强调「scan_hints 内嵌 + rule_check_table 强制」，多语言规则集 ID 列表与文件实际一致。
- 共享 references（01~08, 10）与 scripts（gerrit_audit / gerrit_client / gerrit_review / gerrit_post 等）同步 gerrit-review v2.4.2。

**保留**：

- 本地模块评审全部能力（`references/09-local-module-review.md`、`scripts/local_module_prepare.py`、`scripts/local_audit.py`）。
- 隐私合规三重门控（P0），逻辑与 v2.2.0 完全一致。
- Python 3.6.9 兼容（沿用 v2.1.2 的 typing 注解策略与 subprocess 经典写法）。

**Why**：

- v2.4.1 已有语言分派，但 LLM 仍需自行解析规则文件的 grep 关键词，长上下文下漏扫风险高；v2.4.2 把 grep hints 下沉到脚本层，直接填充进 User Prompt，LLM 按表逐条扫描。
- 新增 `rule_check_table` 强制要求 LLM 逐条填写扫描结果，消除「整段跳过」风险。
- 飞书三份规则集文档与本地完全对齐（C 规则 ID 统一为 C-MUTEX/C-RACE/C-INIT/C-COND/C-ATOMIC/C-GLOBAL/C-ERRNO/C-SIGNAL/C-LIFE）。

**Compat**：

- 向后兼容：旧版 review.json 缺 `rule_check_table` 会被 `validate_review_json` 拒绝，但不影响已合入 CR；下一次评审需补齐字段。
- 旧版 dimensions_scanned / cover 关键词约束不变。

**重要**：

- 所有并发规则**不适用「历史代码 P0 降级 P2」豁免**。
- 混合语言 CR 分别扫描对应规则集；`.c + .cpp` 优先 C++。

---

## enhanced_code_review v2.2.0 — 2026-05-02

### 同步 gerrit-review v2.4.1：多语言并发与容器/集合专项 + 自动语言分派

**背景**：gerrit-review 从 v2.1.0 升级到 v2.4.1，新增了 Step 4.5 多语言并发专项扫描（C++ 12条 / Java 12条 / C 15条）和脚本层自动语言分派。enhanced_code_review 同步这些能力。

**新增**：

- `references/09-cpp-concurrency-stl-traps.md`：C++ 并发与 STL 容器陷阱 12 条规则（C-CONC-1~5 / C-STD-1~2 / C-LIFE-1~2 / C-SMART-1 / C-SYNC-1~2）
- `references/11-java-concurrency-collection-traps.md`：Java/Kotlin 并发与集合陷阱 12 条规则（J-SYNC-1~3 / J-COLL-1~3 / J-LIFE-1~2 / J-ATOMIC-1 / J-VOLATILE-1 / J-LEAK-1~2）
- `references/12-c-concurrency-traps.md`：C 并发陷阱 15 条规则（C-MUTEX-1~2 / C-RACE-1~2 / C-LIFE-1~2 / C-INIT-1~2 / C-COND-1~2 / C-ATOMIC-1~2 / C-GLOBAL-1 / C-ERRNO-1 / C-SIGNAL-1）
- `gerrit_review.py::prepare_context`：自动语言分派，按文件扩展名检测 C++/Java/C，输出 `ctx['languages']` 字段
- `gerrit_review.py::validate_review_json(ctx)`：按语言动态校验必扫维度

**更新**：

- 共享 scripts（gerrit_audit.py / gerrit_client.py / gerrit_review.py 等）同步 gerrit-review v2.4.1
- 共享 references（01~08, 10）同步 gerrit-review v2.4.1
- SKILL.md 维度表新增 Step 4.5 多语言并发专项
- LLM prompt（08）接入语言分派 + 多语言并发规则

**保留**：

- 本地模块评审全部能力（`09-local-module-review.md`、`local_module_prepare.py`、`local_audit.py`）
- Python 3.6.9 兼容
- 隐私合规三重门控（P0）

**重要**：

- 所有并发规则**不适用「历史代码 P0 降级 P2」豁免**
- 混合语言 CR 分别扫描对应规则集

---

## enhanced_code_review v2.1.2 — 2026-04-30

### P1 修复：commit message 链接段不再被误标为「缺前缀的 Jira 号」

**背景**：奇瑞规范段中【开发自测视频】常带飞书云盘链接、本地录屏路径、备份 ID 等，含 10~14 位时间戳或 file token 数字尾段。旧版 `extract_jira_violations()` 用 `\b(\d{5,})\b` 全文扫，会把这些数字误判为 `bare_number`（缺前缀的 Jira 引用），从而在 `R.JIRA_BARE_NUMBER` 路径产出 P0/P1 评论刷屏。

**修复**：在 `scripts/gerrit_client.py` 中：

- 新增 `_VIDEO_LINK_HEADERS` 段标题白名单
- 新增 `_bare_number_exempt_ranges(text)`：识别白名单段和行内 URL 的字符范围加入豁免
- `extract_jira_violations()` 仅对未被豁免的位置触发 `bare_number`

### 兼容回退：最低支持 Python 3.6.9

- 删除所有 `from __future__ import annotations`、PEP 585/604 下标注解与 `@dataclass`
- 改用 `typing` 模块 + 普通类
- `subprocess.run` 改回 `stdout=PIPE` 经典写法
- 功能 0 改变

---

## enhanced_code_review v2.1.1 — 2026-04-28

### 本地模块评审适配子模块 / 多仓库

- `local_module_prepare.py` 新增 `--repo auto` 自动从模块路径回溯定位最近 `.git`
- 区分 `dir / file / symlink` 三种 `.git` 形态
- 对 git submodule 回溯出 superproject 工作树
- 对 Android `repo` 工具管理探测 `.repo/manifests` 根
- 子模块未初始化时输出复制即用的 `git -C <super> submodule update --init -- <path>`
- **不再要求**「在仓库根执行」

---

## enhanced_code_review v2.1.0 — 2026-04-21

### 新增隐私合规评审维度（P0）

- 新增 `references/10-privacy-compliance.md` + `scripts/privacy_compliance_scan.py`
- 基于《产品功能 信息安全要求-v1.2-20260210》+《附录-个人信息定义》
- 三重门控（数据 A + 去向 B + 语义 C），宁可漏报不可误报
- 已挂接到 `gerrit_audit.py`，输出 `privacy_candidates` 供 LLM 门控 C 确认

---

## enhanced_code_review v2.0.1 — 2026-04-19

- 移除 `gerrit_client.py` 中任何默认账号与 HTTP 密码
- 清理技能与 references 中的个人化表述
- Gerrit 凭据必须由使用方通过环境变量配置

---

## enhanced_code_review v2.0.0 — 2026-04-18

- 首次以 `enhanced_code_review` 名称发布
- 与 `gerrit-review` 同源 `references/` 与 `scripts/`（含 `gerrit_*.py`）
- 新增 `local_module_prepare.py` / `local_audit.py` / `09-local-module-review.md`
