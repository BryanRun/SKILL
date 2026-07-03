---
name: enhanced_code_review
# full-description: "增强版代码评审（v2.5.2，2026-06-06 回帖模板强约束 + 完整保留 v2.5.1/v2.5.0 全部能力）。**v2.5.2 回帖模板强约束**：回帖 cover 必须经 skill 模板（cover_template）渲染，禁止模型自由写整段模板——gerrit_post.py 与 gerrit_review.py --post 两条贴回路径统一走模板，缺 ctx / --no-auto-cover / --cover 必须显式 --allow-raw-cover 才放行（否则 exit 4）；validate_review_json 硬拒 cover 自带模板抬头/徽章/维度矩阵/Preflight/落款；cover_template 新增 _sanitize_llm_summary 消毒 LLM 段，cherry-pick 复用同时认 review.cherry_pick_info 与 ctx.cherry_pick 保证一定走 cherry-pick 模板。完整保留 v2.5.0 全部能力（合并自 gerrit-review v2.7.0 主线新能力：闭环增强 CL-1~CL-6 / BUILD-FAIL-1 预编译失败红线 P0 / contract scan LRU cache / contract_change_scan / cover 自动徽章升级）+ v2.4.1 全部能力（平台化设计共识 P2/P3 软规则 / Reply-Aware 增量评审 / 6 分支决策矩阵 / P0 豁免铁律 / 复杂度自适应 Lite/Standard/Deep / Topic 解耦 / Cover 模板化 / Cherry-pick 智能复用 / 本地模块评审 / 隐私合规三重门控）+ 本地模块评审独有栈（`local_module_prepare.py` / `local_audit.py` / `references/09-local-module-review.md`）。**v2.5.1 codex 兼容修复**：`scripts/gerrit_audit.py` 与 `scripts/privacy_compliance_scan.py` 移除 PEP 585（`list[..]` / `dict[..]` / `tuple[..]`）、PEP 604（`X | None`）、PEP 563（`from __future__ import annotations`）以及 `dataclasses` 依赖；所有运行时类型注解统一切回 `typing` 模块（`List` / `Dict` / `Tuple` / `Optional`）；`@dataclass class Candidate` 改写为普通 `class Candidate(object)` + 显式 `__init__`；docker `python:3.6.15-slim` 全量 import 验证通过；`skill.json::platform` 新增 `codex`。**v2.5.0 增量能力（合并自 gerrit-review v2.7.0，v2.5.1 全部继承）**：① **闭环增强机制 CL-1~CL-6**（`references/15-closeloop-enhancement.md`）：临时策略 reply 硬约束识别 / 未闭环清单 unresolved_issues 强制产出 / 契约变更跨 CR 上下文感知（context_aware_ok / single_side_p2 / mismatch_p0 三种判定）/ cover 带病合入说明段强制 / 真修复识别 fix_mismatch / 契约硬扫候选层；② **BUILD-FAIL-1 预编译失败红线 P0**（`references/16-build-fail-redline.md`）：CR 当前 patchset 任一 Verified / Prebuild-Check label 被打 -1/-2 时直接 -2 跳过 LLM 评审；③ **contract scan LRU cache**：兄弟 CR 查询进程级缓存；④ **gerrit_audit 新增 contract_change_scan**：扫 IntDef 数值 / proto field tag / Bundle key 字符串变更；⑤ **cover 自动徽章升级**：顶部硬约束 `🤖 enhanced_code_review v2.5.1 · 🟡 Standard`，增量评审叠加 `🔄 Incremental`。validate_review_json 含 CL-1 / CL-2 / CL-4 / BUILD-FAIL-1 强制校验。review.json schema 仅新增可选字段（unresolved_issues / fix_mismatch_flag / contract_change_scan_results），向后兼容 v2.4.1 / v2.5.0 历史 review.json。Python 3.6.9 兼容（无 PEP 585/604、无 dataclasses 依赖）。触发：review <模块路径>、enhanced_code_review review <模块路径>、以及原 gerrit-review 全部触发语。"
description: "增强版代码评审 v2.5.5（v2.5.4 超集 + 第 9 维 SELinux 策略专项上下文门控 + JIRA CHER 前缀）。仅当 CR 命中 *.te/*.cil/*_contexts/te_macros/sepolicy 路径时开启 SELinux 检测（references/18，14 条规则 P0~P3，安全红线不设上限）。完整能力说明保留在正文和上方 full-description 注释；触发：review <模块路径>、enhanced_code_review review <模块路径>、以及原 gerrit-review 全部触发语。"
version: "2.5.5"
---

# enhanced_code_review — 增强版代码评审（v2.5.5）

> **本技能 = gerrit-review v2.7.0 能力全集 + 本地模块评审增量 + 隐私合规维度 + 复杂度自适应 + Topic 解耦 + Cover 模板化 + Cherry-pick 智能复用 + 平台化设计共识软规则 + 闭环增强 CL-1~CL-6 + BUILD-FAIL-1 红线**。质量门禁、八维清单、方法论、评分与评论格式与 `gerrit-review` **完全一致**,不得删减。详见 `references/09-local-module-review.md`、`references/10-privacy-compliance.md`、`references/13-cover-format-spec.md`、`references/14-platform-design-principles.md`、`references/15-closeloop-enhancement.md`、`references/16-build-fail-redline.md`、`references/18-selinux-policy.md`（v2.5.5 SELinux 策略专项，上下文门控）。**v2.5.2 回帖模板强约束**：回帖 cover **必须**经 skill 模板（`cover_template`）渲染，禁止模型自由写整段模板；`gerrit_post.py` 与 `gerrit_review.py --post` 两条贴回路径统一走模板，缺 ctx / `--no-auto-cover` / `--cover` 等绕过路径必须显式 `--allow-raw-cover` 才放行（否则 `exit 4`）；`validate_review_json` 硬拒 cover 自带模板抬头/徽章/维度矩阵/Preflight/落款；`cover_template` 新增 `_sanitize_llm_summary` 消毒 LLM 段，cherry-pick 复用同时认 `review.cherry_pick_info` 与 `ctx.cherry_pick`，保证一定走 cherry-pick 模板（见「§版本」v2.5.2 段）。v2.5.1 codex 兼容 + v2.5.0 闭环增强 CL-1~CL-6 / BUILD-FAIL-1 红线全部继承。

## 运行时要求（v2.1.2 起明示）

- **最低支持 Python 3.6.9**；已在 Python 3.6.15（docker `python:3.6.15-slim`）与 Python 3.10.12 上联合验证。
- 不再使用 `from __future__ import annotations`（PEP 563，3.7+）、`dict[..]` / `list[..]` / `X | None`（PEP 585/604，3.9+ / 3.10+）等运行时新语法，**也不依赖** 标准库 `dataclasses`（3.7+）。所有类型注解统一使用 `typing` 模块（`typing` 3.5+ 即支持）。
- `subprocess.run` 改用 `stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True` 经典写法（不使用 `capture_output=True` / `text=True`，3.7+ 才有）。
- 第三方依赖 `requests` / `urllib3` 由使用方按服务器实际版本选择安装（与 Python 兼容性无关）。

## 版本

- **2.5.5**（本版本，2026-06-16）：**新增第 9 维「SELinux 策略专项」（上下文门控）+ JIRA CHER 前缀**。
  - **新增 `references/18-selinux-policy.md`**：14 条规则（SEL-PERM-1 / SEL-WILD-1 / SEL-WX-1 / SEL-NEVERALLOW-1 = **P0**；SEL-CAP-1 / SEL-VIOLATOR-1 / SEL-DONTAUDIT-1 / SEL-LABEL-1 / SEL-VER-1 / SEL-CTX-1 = **P1**；SEL-MIN-1 / SEL-MACRO-1 / SEL-COMMENT-1 = **P2**；SEL-NAME-1 = **P3**）。依据 AOSP *Security-Enhanced Linux in Android* + Android CDD §9.7（禁 permissive 域）+ CIL/te 语言规范 + 工程《Android SELinux策略平台化配置指导文档》。安全红线（permissive 域 / 通配符过度授权 / W^X / 削弱 neverallow / 授予 untrusted 域高危 capability）**不设 P2/P3 上限**，可直接决定 -1/-2。
  - **上下文门控（核心约束）**：SELinux 维度**只在 SELinux 相关代码上下文开启**。`gerrit_review.py::build_context` 新增 `detect_selinux_context`，当 diff 命中 `*.te` / `*.cil`（含 `*.compat.cil` / `*.ignore.cil`）/ `file_contexts` / `property_contexts` / `service_contexts` / `seapp_contexts` / `hwservice_contexts` / `vndservice_contexts` / `genfs_contexts` / `te_macros` / `mac_permissions.xml` / `keys.conf`，或路径含 `/sepolicy/` | `/selinux/` 时，向 `ctx['languages']` 追加伪语言条目 `lang="SELinux"`（14 条 `rule_ids` + `scan_hints`），强制 `selinux_policy` 维度 `scanned=true` + `rule_check_table["SELinux"]` 逐条填写；**非 SELinux CR** 该维度允许 `scanned=false`（并入 `DIMS_ALLOW_NOT_SCANNED`），**不对普通业务代码套用、不产生噪声**。
  - **脚本改动**：`scripts/gerrit_review.py`（`detect_selinux_context` / `_selinux_lang_entry` / `REQUIRED_DIMS` 追加 `selinux_policy` / `DIMS_ALLOW_NOT_SCANNED` 追加 / lang 分派新增 `elif lang=='SELinux'`）；`scripts/cover_template.py`（`SKILL_VERSION=2.5.5`，`CONCURRENCY_DIMS` 加 `selinux_policy`，维度矩阵新增 **4.6 SELinux 策略专项**行，仅命中上下文时渲染）；`scripts/local_module_prepare.py`（`TEXT_EXT` 加 `.te`/`.cil`/`.conf` + `_SELINUX_BASENAMES` 放行无后缀上下文文件）。
  - **JIRA CHER 前缀（奇瑞 Chery 项目匹配性修复）**：`scripts/gerrit_client.py::JIRA_RE` 新增 `CHER[A-Z0-9]*-\d+`（兼容 `CHER-1234` / `CHERY-5678` / `CHERxxx-nnn`，置于 CHY 分支前无歧义）；同步进 `gerrit_audit.py`（`R.TODO_NO_OWNER` 负向断言 + `project_keywords` 追加 `cher` + 两处缺 Jira 建议文案）与 `local_audit.py`（TODO 负向断言）。`CHEESE-1` 等不误命中。
  - **prompt / 维度同步**：`references/08-llm-review-prompt.md` 评审维度新增第 9 项 SELinux + Step 10 扫描步骤 + `dimensions_scanned.selinux_policy` + `rule_check_table["SELinux"]` 14 条 + `comments[].dimension` 枚举追加 `selinux_policy` + 输出自检两条；`references/02-security.md` 顶部加 SELinux 专项交叉引用。
  - **不变项**：`references/01 / 03~17` 全部不动；7+1 维评审 / 隐私合规三重门控 / 闭环增强 CL-1~CL-6 / BUILD-FAIL-1 红线 / Reply-Aware / 复杂度自适应 / Cherry-pick 复用 / 本地模块评审 / stale-revision 修复 / 严重度↔分数硬门禁 **全部继承不退化**；review.json schema 仅新增可选维度 `selinux_policy`，向后兼容历史 review.json（非 SELinux CR scanned=false 即可）；Python 3.6.9 兼容（新增代码全用 `.format()` + `typing`，无 f-string / PEP 585/604）。
- **2.5.4**（2026-06-06）：**stale-revision 修复**。POST 贴回前以 Gerrit 实时 `current_revision` 为准，自动改写 `review.json` / `ctx.json` 残留旧 PS sha，杜绝基于旧 patchset 误判 + cover revision 标错（如 CR 1049671 PS2 被按 PS1 旧代码错评 -1）。新增 `gerrit_client.get_current_revision`，`gerrit_review.py --post` 与 `gerrit_post.py` 两条路径同步守卫。
- **2.5.2**（2026-06-06）：**回帖模板强约束（杜绝「模型自己写模板」）**。问题背景：回帖 cover 存在两个绕过 skill 模板的 loophole——`gerrit_post.py` 在缺 ctx 时静默退回 `review.json` 原始 cover，`gerrit_review.py --post`（`post_from_review_json`）则**从不**走 `cover_template`、直接 POST 模型自由 cover；二者都可能让模型即兴写整段非标准模板贴回 Gerrit。本版四处收口：**(1) `scripts/gerrit_post.py`**：缺 ctx / `--no-auto-cover` / `--cover` 等绕过模板的路径不再静默退回裸 cover，统一改为**硬失败 `exit 4`** 并提示用 `--ctx`；只有显式叠加新参数 `--allow-raw-cover` 才放行裸 cover 并打 stderr 醒目告警。**(2) `scripts/gerrit_review.py::post_from_review_json`**：贴回前统一调用 `cover_template.render_from_review_and_ctx`（与 `gerrit_post.py` 同源），缺 `--ctx` / `--no-auto-cover` 同样需 `--allow-raw-cover` 才裸贴；新增 CLI `--no-auto-cover` / `--allow-raw-cover`。**(3) `scripts/gerrit_review.py::validate_review_json`**：新增 v2.5.2 守卫，`cover` 字段命中 skill 模板抬头（`## 🤖 enhanced_code_review`）/ 顶部结论 H3（`### 评审结论：`）/ 维度矩阵（`### 8 大维度扫描`）/ Preflight / 落款等结构标记即 `raise ReviewQualityError` 拒绝 POST——强制 LLM 的 `cover` 只写「### 📝 LLM 评审结论」之下的纯散文。**(4) `scripts/cover_template.py`**：新增 `_sanitize_llm_summary`，渲染 LLM 段前剥离模型误塞的模板结构（抬头/H3/矩阵/Preflight/cherry-pick 块/落款），优先抽取 `### 📝 LLM 评审结论` 之后的真实散文；cherry-pick 复用识别强化为同时认 `review.cherry_pick_info.reuse` 与 `ctx.cherry_pick.reuse`，缺 base_info 时从 `ctx.cherry_pick` 兜底合成，保证 cherry-pick CR 一定走 cherry-pick 模板；`SKILL_VERSION` 升至 `2.5.2`（cover 顶部徽章随之 `🤖 enhanced_code_review v2.5.2`）。**不变项**：`references/01~16` 全部参考文档不动；7+1 维评审 / 隐私合规三重门控 / 闭环增强 CL-1~CL-6 / BUILD-FAIL-1 红线 / Reply-Aware / 复杂度自适应 / Topic 解耦 / 本地模块评审 / Cherry-pick 三级识别 **全部继承,不退化**；review.json schema 向后兼容（标准/Deep 档 cover 本就只写散文的历史 review.json 仍可 POST）；Python 3.6.9 兼容（新增代码全用 `.format()` + `typing`，无 f-string / PEP 585/604）。**(5) Jira 前缀补 AUDI（2026-06-06 修订）**：`scripts/gerrit_client.py::JIRA_RE` 新增 `AUDI-\d+`（奥迪项目正式 Jira 号），并同步进 `gerrit_audit.py` 的 `R.TODO_NO_OWNER` 负向断言 + 缺 Jira 软判断 `project_keywords`（新增 `audi`）+ 两处缺号建议文案、`local_audit.py` 的 TODO 负向断言、`references/05/06/08/08-lite` 四篇前缀枚举；`AUDIO-1` 等不误命中。
- **2.5.1**（2026-05-21）：**codex CLI 兼容修复（纯运行时兼容性,无功能变化）**。`scripts/privacy_compliance_scan.py` 移除 `from __future__ import annotations`,移除 `from dataclasses import dataclass, field` 依赖(dataclasses 是 3.7+ 标准库),`@dataclass class Candidate` 改为普通 `class Candidate(object)` + 显式 `__init__`,所有 `list[..]` / `dict[..]` / `tuple[..]` / `X | None` 运行时类型注解改用 `typing.List` / `Dict` / `Tuple` / `Optional`(PEP 585/604 仅在 3.9+ / 3.10+ 可用)。`scripts/gerrit_audit.py` 同步替换 `dict[..]` / `list[..]` / `tuple[..]` 注解为 `typing.Dict` / `List` / `Tuple`。docker `python:3.6.15-slim` 验证通过:13 个脚本全量 import 无 `SyntaxError` / `TypeError` / `ModuleNotFoundError`,SKILL.md 的「Python 3.6.9+ 兼容」承诺由文档升级为代码保证。`skill.json::platform` 显式追加 `"codex"`,与 `"claude-code"` 并列声明 dual-platform 支持。所有 `references/` 文档不动,其余 scripts 全部保留 v2.5.0 状态(仅 docstring 内字面字符串含 PEP 585 字样,无运行时效应)。闭环增强 CL-1~CL-6 / BUILD-FAIL-1 红线 / contract scan LRU cache / 平台化共识 P2/P3 / Reply-Aware / 复杂度自适应 / Cover 模板化 / Cherry-pick 复用 / Topic 解耦 / 本地模块评审 / 隐私合规三重门控 **全部继承,不退化**。

- **2.5.0**（2026-05-15）：**从 gerrit-review v2.7.0 合并 4 大主线新能力**。完整保留 v2.4.1 平台化共识 + v2.4.0 Reply-Aware + v2.3.x 复杂度自适应 / Cover 模板化 / Cherry-pick 智能复用 / Topic 解耦 + 本地模块评审独有栈（`local_module_prepare.py` / `local_audit.py` / `references/09-local-module-review.md`）。
  - **闭环增强机制 CL-1~CL-6**（`references/15-closeloop-enhancement.md`，11.7KB）：
    - **CL-1 临时策略 reply 硬约束**：reply_classification 5 类（rational / temporary_with_jira / temporary_no_jira / tradeoff_no_data / no_reply）；后两类禁止豁免；临时性关键词集（临时策略 / 上线前 / 后续 CR / 这版先 / TODO / 简化复杂度 等 20+ 项）+ 4 行处置矩阵
    - **CL-2 未闭环清单 unresolved_issues 强制**：temporary_with_jira 类降级必须挂关联 Jira（CHYT1V/CHYKP31/D01/FL[1-3]/T1V/N80）并写入 review JSON 顶层 `unresolved_issues` 数组
    - **CL-3 契约变更跨 CR 上下文感知**：识别同 Jira / 同 topic 兄弟 CR，区分 context_aware_ok / single_side_p2 / mismatch_p0 三种判定；**绝对禁止仅凭契约变更就一刀切 P0**
    - **CL-4 cover 带病合入说明段强制**：`unresolved_issues` 非空时 cover 必含「⚠️ 带病合入说明」段
    - **CL-5 真修复识别 fix_mismatch**：比对 owner reply 声称的修复与代码实际变化；fix_mismatch 时维持原 P0/P1，禁止豁免
    - **CL-6 契约硬扫候选层**：`gerrit_audit.py` 新增 `contract_change_scan` 扫 IntDef 数值 / proto field tag / Bundle key 字符串变更，默认 P2 候选待 CL-3 上下文升级
  - **BUILD-FAIL-1 预编译失败质量红线 P0**（`references/16-build-fail-redline.md`，3.7KB）：
    - 触发：CR 当前 patchset 任一 `Verified` / `Prebuild-Check` label 被打 -1/-2
    - 处置：直接 `-2` 跳过 LLM 评审（不浪费 token，不发起 7+1 维度扫描）
    - `compute_review_decision` 新增优先级 0.5 的 mode `skip_build_failed`；CLI 提供 `gerrit_review.py <CR> --build-fail-fast` 快通道
    - 不识别 `CommitMsg-Check` / `StaticCode-Check`（由其他维度兜底）
  - **contract scan LRU cache（性能优化）**：同 Jira 多 CR sibling 查询复用进程级缓存（`_SIBLING_CACHE`），cron / 批量评审场景同同查询的冗余被干掉
  - **兄弟 CR 拉取改 `o=CURRENT_FILES`-only**：去掉 `o=CURRENT_REVISION` / `o=DETAILED_ACCOUNTS`，仅拉 file path，节省 ~30% 流量
  - **cover 自动徽章升级**：顶部硬约束 `🤖 enhanced_code_review v2.5.0 · 🟡 Standard`（参 `scripts/cover_template.py::SKILL_NAME/SKILL_VERSION`），增量评审叠加 `🔄 Incremental`
  - `validate_review_json` 增加 CL-1 / CL-2 / CL-4 / BUILD-FAIL-1 强制校验
  - **review.json schema 仅新增可选字段**：`unresolved_issues` / `fix_mismatch_flag` / `contract_change_scan_results` / `reply_classification`；旧 review.json 仍可 POST（向后兼容 v2.4.1 / v2.4.0 / v2.3.x）
  - **未改动**：`scripts/local_audit.py` / `scripts/local_module_prepare.py` / `scripts/consistency_scan.py` / `scripts/gerrit_inbox.py` / `references/09-local-module-review.md` / `references/01~07` / `references/09-cpp-concurrency-stl-traps.md` / `references/10-privacy-compliance.md` / `references/11/12` / `references/14-platform-design-principles.md`。复杂度自适应 + Cover 模板化 + Cherry-pick 智能复用 + 隐私合规三重门控 + Reply-Aware 6 分支决策 + 平台化共识 P2/P3 全部继承。

- **2.4.1**（2026-05-14）：**平台化设计共识第 8 维度（软规则 P2/P3）+ dimension/level 守卫**。同步自 gerrit-review v2.5.1，保留 ECR 自有能力栈不动。
  - 新增 `references/14-platform-design-principles.md`（8.6KB）：8 条规则 PLAT-1~PLAT-8 + 平台化总目标 G1~G5 + 需求三分类（🟢通用/🟡可选/🔴定制）+ 配置化三层（静态/动态/客户）+ 平台-项目-客户三层分离 + ISO 25010 八大质量属性 + 底座能力复用清单（通信/持久化/健康/启动/配置/时间/日志）+ 评论输出格式 + 豁免清单 + 复盘机制。
  - 来源依据：《中间件平台化策略与落地框架》+《中间件平台能力规划》（只提取共性方法论，不引入人名/项目时间/具体业务组）。
  - `scripts/gerrit_review.py::validate_review_json` 升级：
    - `REQUIRED_DIMS` 末尾追加 `'platform_design'`；同时新增常量 `DIMS_ALLOW_NOT_SCANNED = {'cpp_concurrency_stl', 'platform_design'}` 将 cpp_concurrency_stl 与 platform_design 一并归入「允许 scanned=false 但 key 必填」清单。
    - 把旧分支判断 `elif d != 'cpp_concurrency_stl':` 改为 `elif d not in DIMS_ALLOW_NOT_SCANNED:`。
    - 新增 **platform_design 定级守卫**：遍历 `review['comments']`，若 `dimension == 'platform_design'` 且 `level in ('P0','P1')` → 拒绝 POST，提示「软规则仅 P2/P3」（如确属 P0/P1 请改归类）。
    - 上述守卫对 Lite / Standard / Deep / Cherry_pick_reuse 四档同时生效，**不影响**已有 reply_disposition / rule_check_table / complexity_level 等校验。
  - `references/13-cover-format-spec.md` 同步：
    - 抬头标记升级为「v2.4.1 同步自 gerrit-review v2.5.1」。
    - cover 骨架表格新增「平台化设计共识 (P2/P3)」一行。
    - 综合评估段统一描述为「已完成 7+1 维度评审 + 平台化共识扫描」+「PLAT-* 命中 N 条，仅作改进提示，不影响打分」。
  - `references/08-llm-review-prompt.md` 同步：
    - System Prompt「评审维度」标题从「7 类完整覆盖」改为「7 类完整覆盖 + 1 类软规则」，新增第 8 项 platform_design 维度描述（含定级硬约束 + 依据参考）。
    - User Prompt 增加 **Step 9 · 平台化设计共识** 扫描步骤（覆盖 §一 ~ §十 章节 + PLAT-* 前缀要求 + 豁免清单）。
    - JSON schema `dimensions_scanned` 新增 `platform_design` 字段，`comments[].dimension` 枚举末尾追加 `platform_design`，`rule_id` 注释扩展到 `PLAT-1` 起。
    - 输出前自检清单追加 v2.4.1 四项（dimensions_scanned key 必填 / level 守卫 / PLAT-* 前缀 + 章节引用 / 打分独立性）。
  - **未改动**：`scripts/gerrit_client.py` / `gerrit_audit.py` / `gerrit_show.py` / `gerrit_post.py` / `gerrit_inbox.py` / `consistency_scan.py` / `privacy_compliance_scan.py` / `cherry_pick_detect.py` / `complexity_assess.py` / `cover_template.py` / `local_audit.py` / `local_module_prepare.py`；`references/01~12` / `08-llm-review-prompt-deep.md` / `-lite.md` / `09-local-module-review.md` / `10-privacy-compliance.md` 全部保留 v2.4.0 状态。Topic 解耦（不回退 `find_related_crs`）+ 复杂度自适应 + Cover 模板化 + Cherry-pick 智能复用 + 隐私合规三重门控 + Reply-Aware 增量评审 6 分支决策全部继承。

- **2.4.0**（2026-05-12）：**Reply-Aware 增量评审 + 6 分支决策矩阵 + cover 排版规范 + ECR 保留 Topic 解耦**。同步自 gerrit-review v2.5.0 修正二，但**不回退** v2.3.1 的 Topic 解耦（find_related_crs 保持删除）。
  - `gerrit_client.py` 新增 6 个 API：`get_change_comments` / `get_change_messages` / `is_substantive_review_message` / `build_prior_review_context` / `compute_review_decision` / `is_placeholder_jira`（JIRA_RE 注释补齐 2026-05-03 名单扩展说明）。
  - `gerrit_review.py::prepare_context` 末尾注入 `ctx["prior_review_context"]` + `ctx["review_decision"]`；complexity 评级 / cherry_pick 检测 / Reply-Aware 三层上下文并存；`--prepare` 输出 banner 叠加「🆕 proceed / 🔄 incremental / ⏭️ skip」决策信息。
  - `validate_review_json` 对 Standard/Deep/Lite 三档叠加 Reply-Aware 硬校验：`prior_review_context.has_prior_review=true` 时必须有 `reply_disposition`（list）+ `incremental_summary`（dict）；cherry_pick_reuse 档不受影响。
  - `cover_template.py`（升级至 v2.4.0）：顶部新增 `### 评审结论：<分数>（<一句话>）` 硬块；维度矩阵图标切到 ✅/⚠️/❌/⚪（符合 references/13-cover-format-spec.md）；新增 `_render_incremental_summary` 渲染「增量评审汇总」表 + Reply 处置明细前 5 条；`render_from_review_and_ctx` 自动探测 `review_decision.is_incremental` 加挂 🔄 Incremental 叠加徽章。
  - 新增 `references/13-cover-format-spec.md`（同步自 gerrit-review v2.4.3，ECR 顶部加技能语境说明）。
  - `references/08-llm-review-prompt.md` 新增「历史评审上下文（v2.4.0 — Reply-Aware + 增量评审）」章节（规则 A/B/C/D/E/F）+ `reply_disposition` / `incremental_summary` schema + cover 排版硬约束 + 4 条自检清单。
  - `references/08-llm-review-prompt-lite.md` 注入 prior_review_context 占位 + 增量字段必填说明；`references/08-llm-review-prompt-deep.md` 追加 Reply-Aware 强化 6（P0 豁免严审 / Persist 论证三问 / incremental_summary 正交等式）。
  - **仍保留 Topic 解耦**：`gerrit_client.find_related_crs` 不回退、`gerrit_audit.py` / `gerrit_show.py` 保持 v2.3.1 版本；Reply-Aware 评审链路只依赖本 CR 自身历史,不按 Jira/topic 反查兄弟 CR。
- **2.3.1**：**Topic 解耦 + Cover 模板化 + Cherry-pick 智能复用**。① 删除 `gerrit_client.find_related_crs` 与 5 处调用点 + prompt 同组 CR 行；review 不再按 Jira 反查兄弟 CR,杜绝 topic/Jira 拆分误评 -1。② 新增 `scripts/cover_template.py`(4 档统一渲染：lite/standard/deep/cherry_pick_reuse),`gerrit_post.py` 默认 auto-cover,cover 必含 skill 名 + 版本 + 档位徽章 + 7+1 维矩阵 + 并发汇总。③ 新增 `scripts/cherry_pick_detect.py` 三级识别,prepare_context 末尾自动跑。④ review JSON schema 新增 `skill_meta` + `cherry_pick_info` 字段,validate 按档位分叉。
- **2.3.0**：**新增复杂度自适应三档（Lite / Standard / Deep）**。新增 `scripts/complexity_assess.py` 评级器，`gerrit_review.py::prepare_context` 与 `local_module_prepare.py::prepare` 末尾注入 `ctx["complexity"]`。新增 `references/08-llm-review-prompt-lite.md` 与 `references/08-llm-review-prompt-deep.md`。`validate_review_json` 按档位分叉。CLI 新增 `--force-level lite|standard|deep`。
- **2.2.1**：同步 gerrit-review v2.4.2 — scan_hints 内嵌 + rule_check_table 强制 + rule_ids 校准。
- **2.2.0**：多语言并发与容器/集合专项（C++ 12 / Java 12 / C 15）+ 自动语言分派。
- **2.1.2**：commit message 中【开发自测视频】链接段豁免；Python 3.6.9 兼容。
- **2.1.1**：本地模块评审适配子模块 / 多仓库结构 — `local_module_prepare.py` 新增 `--repo auto`。
- **2.1.0**：新增隐私合规评审维度（P0 级；三重门控）。
- **2.0.1**：移除默认凭据；references 去个人化表述。
- **2.0.0**：首次以 `enhanced_code_review` 名称发布。

## 触发（本地增强）

- `review <模块路径>` — 例：`review frameworks/cm/videoplayer`、`review midware/startupanimation`
- `enhanced_code_review review <模块路径>` — 显式调用本技能

**本地模块工作流**（v2.1.1 起不再要求在仓库根执行）：

```bash
# 推荐：自动从模块路径回溯最近 .git，自适应车载多仓库 / git submodule / repo 工具结构
python3 scripts/local_module_prepare.py <模块绝对/相对路径> --repo auto -o /tmp/local_ctx.json

# 兼容：显式仓库根（在 git 工作树内执行）
cd <git 工作树根>
python3 scripts/local_module_prepare.py <模块相对路径> [--base origin/main] -o /tmp/local_ctx.json
```

Agent 读取 JSON 后，按 `references/08-llm-review-prompt.md` 产出评审结论（八维 + 三问 + YAGNI + 隐私合规门控 C）。
若输出 `topology.git_kind == "none"` 且带 `uninitialized_submodule_hint.init_hint`，**复读** init_hint 让用户初始化后重跑，**不要**自动执行 `git submodule update`。

## 触发（原 Gerrit 全能力，保留）

- `review CR <编号>` — 单 CR 全自动评审
- `review <姓名>` — 按 owner 列 open CR 清单
- `gerrit inbox` / `今天待审` — 待审概览

---

## 完整评审维度（7 大必全扫 + 1 类软规则，v2.4.1 起）

| # | 维度 | 权威依据 | 参考 |
|---|---|---|---|
| 1 | **SOLID 原则** | Bob Martin APPP (2002) + Effective Java | `references/01-solid-principles.md` |
| 2 | **安全性** | OWASP Top 10 + CWE/SANS Top 25 + Android CDD + ISO 21434 | `references/02-security.md` |
| 3 | **性能** | Effective Java Item 67 + Android Performance Patterns | `references/03-performance.md` |
| 4 | **错误处理 + 边界** | Effective Java Item 70-77 + Clean Code Ch.7 | `references/04-error-handling-boundaries.md` |
| 4.5 | **多语言并发与容器/集合专项（v2.2.0 新增，按语言自动分派）** | ISO C++ Standard / JLS / C Standard + 团队真实缺陷复盘 | `references/09-cpp-concurrency-stl-traps.md`、`references/11-java-concurrency-collection-traps.md`、`references/12-c-concurrency-traps.md` |
| 5 | **代码质量 + 风格** | **Google Java/C++ Style Guide** + 项目硬规范 | `references/05-code-quality-style.md` |
| 6 | **车载中间件专项** | Android Automotive + QNX + AUTOSAR + ISO 26262 | `references/06-automotive-middleware.md` |
| 7 | **隐私合规（P0）** | 《产品功能 信息安全要求-v1.2-20260210》+《附录-个人信息定义》 | `references/10-privacy-compliance.md` |
| **8** | **平台化设计共识（软规则 P2/P3，v2.4.1 新增）** | 中间件平台化策略与落地框架 + 中间件平台能力规划（团队权威输出） | `references/14-platform-design-principles.md` |

即使某维度无发现，也要在 cover 声明"已扫，无发现"。

> **第 8 维度定级硬约束**（v2.4.1）：`platform_design` 维度下所有 inline 评论 `level` 必须为 `P2` 或 `P3`。仅命中本维度（无其他维度 P0/P1）**不影响** +1 决策。`gerrit_review.py::validate_review_json` 强制拒绝 `dimension=='platform_design'` 且 `level in {'P0','P1'}` 的 comment。

### Step 4.5 多语言并发规则集（v2.2.1，rule_ids 与 09/11/12 文件实际一致）

| 语言 | 参考文件 | 规则数 | 规则 ID |
|---|---|---|---|
| **C++** | `references/09-cpp-concurrency-stl-traps.md` | 12 条 | C-CONC-1~7 / C-STD-1~2 / C-LIFE-1~3 |
| **Java/Kotlin** | `references/11-java-concurrency-collection-traps.md` | 12 条 | J-CONC-1~7 / J-STD-1~2 / J-LIFE-1~3 |
| **C** | `references/12-c-concurrency-traps.md` | 15 条 | C-MUTEX-1~2 / C-RACE-1~2 / C-LIFE-1~2 / C-INIT-1~2 / C-COND-1~2 / C-ATOMIC-1~2 / C-GLOBAL-1 / C-ERRNO-1 / C-SIGNAL-1 |

**自动语言分派**：`gerrit_review.py::prepare_context` 根据文件扩展名自动检测语言，输出 `ctx['languages']` 字段：
- `.cpp/.cc/.cxx/.hpp/.h` → C++ → `references/09-cpp-concurrency-stl-traps.md`
- `.java/.kt` → Java/Kotlin → `references/11-java-concurrency-collection-traps.md`
- `.c` → C → `references/12-c-concurrency-traps.md`
- 混合语言 CR 分别扫描；`.c + .cpp` 优先 C++

**v2.2.1 新增 scan_hints 内嵌**：每个 `lang_info` 内含 `scan_hints` 列表，逐条规则附带 `grep` 正则与人工确认点（`check`），LLM 直接读取 User Prompt 中的 `{scan_hints_table}`，按表逐条扫描，无需自行解析规则文件。

**v2.2.1 新增 rule_check_table 强制**：Output JSON 必须含 `rule_check_table` 字段，按语言分组逐条规则填 `{scanned: true/false, findings: N}`；`validate_review_json` 按 `ctx['languages']` 动态校验缺失即拒绝 POST，杜绝「整段跳过」风险。

所有并发规则**不适用「历史代码 P0 降级 P2」豁免**，仍以 P0/P1 上报。每条 inline 必带 `[P<级>][<规则ID>]` 前缀。

---

## 隐私合规特殊触发约束（v2.1.0 硬规则）

隐私合规按 **P0** 计分 → 对分数影响极大，须**高精确率**触发：

- **只有**同时命中 `10-privacy-compliance.md` §4 规则表中的 **数据信号（门控 A）+ 去向信号（门控 B）+ 语义确认（门控 C）** 才可作为 P0 评论。
- 只命中门控 A 或只命中门控 B → 降级**疑似**，**不落 inline**，只在 cover 的"建议人工复核"列一行。
- 命中但位于以下上下文时 **必须 drop**：测试目录、纯注释/文档/字符串字面量 TAG、接口声明/字段定义但无赋值、同变量名但与用户上下文无关。
- 每条 P0 隐私合规评论 **必须**在 `message` 中同时列出 **门控 A 证据行号** 和 **门控 B 证据行号**。

---

## 方法论 · `references/07-review-methodology.md`

- **对抗式评审**：verify-before-comment
- **YAGNI 过滤**：抽象建议前 grep 真实 caller 数，≥ 2 才建议抽象
- **三问 filter**（每条必过）：
  1. 不提会真的出问题吗？
  2. 有权威依据支撑吗？
  3. 项目里其他代码是否也这么写？（都这样 → drop 或降 P3）

---

## LLM 评审 · `references/08-llm-review-prompt.md`

System + user prompt 模板。Agent 按该模板执行评审，输出 review JSON（含隐私合规门控 C 确认逻辑 + 语言分派扫描）。

---

## 项目明文规范（车联 AutoLink）

### 硬性
- **Java 缩进必须 4 空格，禁止 tab** — P1
- **C++ 缩进必须 4 空格，禁止 tab** — P1
- **C++ 风格**：遵循项目原有代码整体风格 — P1
- **commit message 必带合规 Jira 号**（缺失 P0 → -1；占位号 P0 → -1；纯数字 P0 → -1；仅 Gerrit 路径，本地模块可注明 N/A）

### YAGNI 原则
- **作为 P3 建议，不强制**

### 冲突处理
1. 项目明文规定 → 按项目
2. 项目未规定 → 可参考 Google Style，**仅作 P3 建议**
3. 项目习惯与 Google Style 冲突 → 按项目

---

## 打分规则

| 级别 | 特征 | Gerrit 分 |
|---|---|---|
| P0 Critical | 真崩溃 / 数据丢失 / 安全 / **隐私合规三重门控命中** / 契约破坏 / Jira 缺失或不合规 | **-1** |
| P1 Important | 真 risk / 架构混淆 / 线程安全 / IPC 挂死 / **4 空格缩进违反** | **0** 或 -1 |
| P2 Medium | code smell / 维护性 / Google Style 违反 | **+1** |
| P3 Low | 可选改进 / 风格建议 | **+1** |
| 无问题 | — | **+1** |

---

## 自动化工作流

### A) Gerrit（8 步）

```
触发 "review CR <n>"
  ↓
Step 1 · Preflight
  - gerrit_show.py                拉 detail / commit / full diff / 同组 CR
  - gerrit_audit.py               机械扫描（Jira / 空 catch / System.out / TODO）
  - consistency_scan.py           同文件 null check 一致性
  - privacy_compliance_scan.py    隐私合规双门控候选（A + B 共现，供 Step 8 消费）
  ↓
Step 2 · SOLID + 架构               ← 01-solid-principles.md
Step 3 · 安全                        ← 02-security.md
Step 4 · 性能                        ← 03-performance.md
Step 4.5 · 多语言并发与容器专项       ← 09/11/12（按语言自动分派）
Step 5 · 错误处理 + 边界             ← 04-error-handling-boundaries.md
Step 6 · 代码质量 + Google Style     ← 05-code-quality-style.md
Step 7 · 车载专项                    ← 06-automotive-middleware.md
Step 8 · 隐私合规（门控 C 语义确认）  ← 10-privacy-compliance.md
Step 9 · 平台化设计共识（软规则，仅 P2/P3）  ← 14-platform-design-principles.md
  ↓
LLM 整合 → 三问 filter + YAGNI + 权威依据 → 分数决策
  ↓
preflight 检查 self 分数（不抢人工）
  ↓
gerrit_post.py 贴回 Gerrit（或只输出本地简报）
```

### B) 本地模块（无 CR）

```
触发 "review <模块路径>"
  ↓
local_module_prepare.py → JSON 上下文（含 privacy_candidates）
  ↓
Step 2～9 · 7+1 维 + LLM + 三问 + YAGNI + 隐私合规门控 C + 平台化软规则（不贴 Gerrit）
```

---

## 评论 5 要素（每条必含）

```
[P<级别>] <file>:<line> — <一句话标题>

**依据**：<权威来源>
**现象**：<具体代码 + 场景>
**原理**：<为什么这是问题>
**建议**：<具体修法>
```

### 隐私合规评论额外要素（P0 必含）
```
**门控 A 证据**：<行号> — <命中的数据信号>
**门控 B 证据**：<行号> — <命中的 sink 模式>
**门控 C 语义确认**：<LLM 上下文判断依据>
```

---

## 核心脚本

| 脚本 | 作用 |
|---|---|
| `scripts/gerrit_client.py` | Gerrit HTTP 客户端 |
| `scripts/gerrit_inbox.py` | 待审清单 |
| `scripts/gerrit_show.py` | 单 CR detail + diff |
| `scripts/gerrit_audit.py` | 机械规则扫描（CR） |
| `scripts/consistency_scan.py` | 同文件一致性（CR + Java） |
| `scripts/gerrit_review.py` | Gerrit 主入口 prepare/post（v2.2.1: scan_hints 内嵌 + rule_check_table 强制 + 自动语言分派 + 动态校验） |
| `scripts/gerrit_post.py` | 贴回 Gerrit |
| **`scripts/local_module_prepare.py`** | **本地模块 prepare JSON** |
| **`scripts/local_audit.py`** | **本地行级规则（与 audit 同源）** |
| **`scripts/privacy_compliance_scan.py`** | **隐私合规候选扫描（门控 A + B 共现；P0 走三重门控）** |

---

## 参考文件

| 文件 | 作用 |
|---|---|
| `references/01-solid-principles.md` | SOLID（Martin APPP + Effective Java） |
| `references/02-security.md` | 安全（OWASP/CWE/ISO） |
| `references/03-performance.md` | 性能（Effective Java + Android） |
| `references/04-error-handling-boundaries.md` | 错误处理 + 边界 |
| `references/05-code-quality-style.md` | Google Java/C++ Style Guide + 项目硬规范 |
| `references/06-automotive-middleware.md` | 车载中间件 L1~L10 |
| `references/07-review-methodology.md` | 对抗式 + YAGNI + 三问 + Step 8 隐私合规 |
| `references/08-llm-review-prompt.md` | LLM system + user prompt（八维度 + 语言分派） |
| **`references/09-cpp-concurrency-stl-traps.md`** | C++ 并发与 STL 容器陷阱 12 条（C-CONC-1~7 / C-STD-1~2 / C-LIFE-1~3） |
| **`references/09-local-module-review.md`** | **本地模块评审（enhanced_code_review 独有）** |
| **`references/10-privacy-compliance.md`** | **隐私合规 P0 + 三重门控** |
| **`references/11-java-concurrency-collection-traps.md`** | Java/Kotlin 并发与集合陷阱 12 条（J-CONC-1~7 / J-STD-1~2 / J-LIFE-1~3） |
| **`references/12-c-concurrency-traps.md`** | C 并发陷阱 15 条（C-MUTEX/C-RACE/C-INIT/C-COND/C-ATOMIC/C-GLOBAL/C-ERRNO/C-SIGNAL/C-LIFE） |
| **`references/13-cover-format-spec.md`** | Cover 排版规范（v2.4.1 同步：7+1 维度表格新增「平台化设计共识 (P2/P3)」行） |
| **`references/14-platform-design-principles.md`** | **v2.4.1 新增** 平台化设计共识软规则 P2/P3（8 条 PLAT-1~PLAT-8）— 需求三分类 / 配置化三层 / 平台-项目-客户三层分离 / ISO 25010 八大属性 / 底座能力复用 |

---

## 使用示例

### Gerrit

```bash
export GERRIT_BASE="https://gerrit.auto-link.com.cn"
export GERRIT_USER="..."
export GERRIT_HTTP_PASSWORD="..."

python3 scripts/gerrit_review.py 993636 --prepare -o /tmp/ctx.json
python3 scripts/gerrit_review.py 993636 --post /tmp/review.json
```

### 本地模块

```bash
python3 scripts/local_module_prepare.py \
    /home/y/t1v_8775/qnx/vendor/autolink/frameworks/cm/videoplayer \
    --repo auto -o /tmp/local_ctx.json
```

### 独立跑隐私合规扫描

```bash
python3 privacy_compliance_scan.py <file.java> [--window 8]
```

---

## 强制最低保证

- 每次评审必出现（即使 cover 只一句）：`SOLID / 安全 / 性能 / 错误处理 / 代码质量 / 车载专项 / 隐私合规 / 平台化设计共识`
- **C++ 改动**额外必出现：C++ 并发与 STL 专项扫描表格（12 行），每条 inline 必带 `[P<级>][<规则ID>]` 前缀
- **Java/Kotlin 改动**额外必出现：Java 并发与集合专项扫描表格（12 行）
- **C 改动**额外必出现：C 并发专项扫描表格（15 行）
- 并发规则**不适用「历史代码 P0 降级 P2」豁免**
- 隐私合规若有候选但门控 C 不通过 → cover 必须写"已扫隐私合规，N 处候选经语义确认均 drop"
- **v2.4.1 平台化软规则**：`dimensions_scanned.platform_design` key 必填（无平台化代码 → `{"scanned": false, "findings": 0}`）；每条 `dimension == 'platform_design'` 的 inline 评论必含 `[P2|P3][PLAT-<n>]` 前缀；**不允许** 出现 P0/P1（如属 P0/P1 请改归类到对应硬维度）；豁免（hotfix / 项目分支专属 / 测试代码 / <30 行小 bug）不评

---

## 与 gerrit-review 的关系

- **gerrit-review v2.5.1**：仅 Gerrit 自动化；**本技能 v2.4.1** 在其基础上增加 **本地模块** 能力 + **复杂度自适应** + **Topic 解耦** + **Cover 模板化** + **Cherry-pick 智能复用**，**不降低**任一维度或规则质量。
- 共享 `references/`（01~08, 09-cpp, 10, 11, 12, **14-platform**）与 `scripts/gerrit_*.py`（其中 `gerrit_client.find_related_crs` 在 v2.3.1 已移除，本技能保留删除状态；`gerrit_review.py::validate_review_json` 在 v2.4.1 同步加入 platform_design 维度守卫）。
- 本技能独有：`references/09-local-module-review.md`、`references/08-llm-review-prompt-lite.md`、`references/08-llm-review-prompt-deep.md`、`scripts/local_module_prepare.py`、`scripts/local_audit.py`、`scripts/complexity_assess.py`、**`scripts/cover_template.py`**（v2.3.1 新增）、**`scripts/cherry_pick_detect.py`**（v2.3.1 新增）。
- 分发包：`enhanced_code_review-v2.4.1.zip`（本技能，替换 v2.4.0）。

---

## §v2.4.0 新增能力（Reply-Aware 增量评审）

### 1) 6 分支评审决策矩阵（`compute_review_decision`）

**问题**：历史上 ECR/gerrit-review 看到他人已 -1 就 skip，没识别他人 -1 是 AI 实质评审还是「自动预审未通过」纯标记；也没识别 owner 已 reply 或代码已推新 patchset。结果：① 有人 -1 但是预审拒绝 → ECR 跳过 → 该 CR 永远不被 AI 评审；② owner reply 了但被忽略 → 继续维持原 -1；③ owner 推了新 patchset 但 ECR 看到 self 已评 → skip，漏掉新问题。

**v2.4.0 做法**（同步 gerrit-review v2.5.0 修正二）：

| # | 场景 | 决策 | 优先级 |
|---|---|---|---|
| 1 | owner 有任何 reply（cover-level / inline，不论对象） | **incremental** | 最高 |
| 2 | self 已评审 + 代码有变动（new patch set） | **incremental** | — |
| 3 | 他人 -1 + 代码有变动 | **proceed** | — |
| 4 | 他人 -1 仅为纯标记（非实质 AI 评审） | **proceed** | — |
| 5 | 他人含实质 AI 评审 -1 + owner 无 reply + 代码未变 | **skip** | — |
| 6 | self 已评审 + owner 无 reply + 代码未变 | **skip** | — |
| 默认 | 首评 / `--force` | **proceed** | 默认 |

「实质 vs 非实质 AI 评审」由 `is_substantive_review_message()` 按关键字判定：含「评审结论 / 维度扫描 / `[P0]` / `[P1]` / 依据：」等骨架词或净文本 > 300 字符为实质；含「自动预审未通过 / 未找到 AI 本地预审结果」或纯 CI 标记为非实质。

### 2) Reply 采纳与 P0 豁免铁律

- **P0 豁免唯一途径 = owner reply 的合理性**；reply 必须有技术依据 + 可在当前代码中验证。
- **特殊备注（cover-level 非 reply）仅对 P1 及以下有效**；P0 不受影响。
- `reply_disposition` 输出每条 self 历史评论的处置结果：`resolved / persist / partial / dropped_by_reply / downgraded_by_note / code_no_longer_exists`。
- `incremental_summary` 输出汇总：`prior_total / resolved / persist / partial / dropped_by_reply / downgraded_by_note / code_no_longer_exists / new_findings`。

### 3) cover 排版规范（`references/13-cover-format-spec.md`）

- **禁止整段散文 cover**。
- 顶部 **H3「评审结论：<分数>（<一句话>）」**（`+1` / `-1` / `+2` / `-2`，不写 0）。
- CR 元信息一行带 **bold** / `code` / `[Jira 超链接]` / `[CR 链接]`。
- **H3「7 大维度扫描」表格**：每行一个维度 + 图标 `✅ 无` / `⚠️ N findings` / `❌ 未扫但有疑点` / `⚪ N/A`。
- **增量评审汇总表**（`has_prior_review=true` 时必现）。
- 综合评估段带 `P0=X / P1=X / P2=X / P3=X` 硬统计。
- `cover_template.py` v2.4.0 自动按本骨架渲染；`gerrit_post.py --no-auto-cover` 可退回 v2.3.0 行为。

### 4) Prior Review Context 注入

`prepare_context` 末尾调用 `build_prior_review_context(cr, self_username)` 返回：

- `has_prior_review / prior_score / prior_review_patch_set / current_patch_set / code_changed_since_prior_review`
- `self_prior_comments[] / owner_replies[] / owner_cover_replies[] / owner_inline_replies_to_others[]`
- `other_reviewer_comments[] / special_notes[] / score_history[]`
- `has_withdrawn / other_minus_one / has_substantive_other_minus_one / other_minus_one_details[] / has_owner_reply`
- `owner_username`

Agent 读 `ctx.prior_review_context` + `ctx.review_decision` 后按 `references/08-llm-review-prompt.md` 新增的「规则 A/B/C/D/E/F」处理。

### 5) Validate JSON 新增 Reply-Aware 硬校验

- Lite 档：若 `has_prior_review=true`，`reply_disposition` / `incremental_summary` 字段必须存在（可空）。
- Standard 档：`reply_disposition` 必须是 list 且每条含 `disposition`；`incremental_summary` 必须是 dict。
- Deep 档：叠加每条 `disposition` 的 `reason` 质量要求（引用 owner 原文或 diff 行号）；Persist 旧 P0/P1 必须在 inline 附 Q1-Q3 三问；新发现 P0/P1 仍走 adversarial_qa。
- Cherry-pick_reuse 档：不受 Reply-Aware 校验影响（复用档不跑 LLM 扫描）。

### 6) 与 Topic 解耦 / Cherry-pick / 复杂度自适应的协同

- `prepare_context` 流水线：`audit → files/diff → consistency_scan → complexity_assess → cherry_pick_detect → prior_review_context → review_decision`。
- cherry_pick 命中 → `complexity.level = cherry_pick_reuse`，Reply-Aware 校验跳过（复用基线结论）。
- 复杂度 lite / standard / deep 正交于 Reply-Aware：有历史评审就进增量模式，档位决定深度。
- **依旧保持 Topic 解耦**：`find_related_crs` 不回退，`gerrit_audit` / `gerrit_show` 不拉同 Jira 兄弟 CR；Reply-Aware 评审链路只用本 CR 自身历史。

---

## §v2.3.1 新增能力

### 1) Topic / Jira 关联解耦（硬约束）

**问题**：v2.3.0 与更早版本通过 `find_related_crs(jira)` 拉取同 Jira 号下所有 CR 注入 prompt，让 LLM 看到"同组 CR"列表。当 Jira 号被拆为多笔提交（同一 Jira 下有 N 个 CR）或 cherry-pick 到不同分支时，LLM 把"同组 CR"差异当作阻塞证据，**误评 -1**。

**v2.3.1 做法**：

- 删除 `gerrit_client.find_related_crs()` 函数体；删除 `gerrit_audit.py` / `gerrit_review.py` / `gerrit_show.py` 的 `import` 与全部 5 处调用循环；删除 `references/08-llm-review-prompt.md` 中 `- 同组 CR：{related_crs}` 提示行。
- review JSON / ctx 不再存在 `related_crs` 字段。
- Jira 号本身仍提取并合规检查（缺失硬规则不变），但**不再用 Jira 反查 peer CR**。
- Cherry-pick 关系改用 §3 的原生信号识别。

### 2) Cover 模板化（统一外观）

**问题**：v2.3.0 cover 完全由 LLM 即兴写，不显示 skill 名 / 版本号，7+1 维结果靠 LLM 自行重述（易遗漏），并发规则汇总也靠 LLM，跨 PS 风格不一致。

**v2.3.1 做法**：

- 新增 `scripts/cover_template.py`（Python 3.6.9 兼容）。提供 `render_cover(meta, audit_summary, dims, rule_check_table, llm_summary, ...)` 与 `render_from_review_and_ctx(review, ctx)` 两个入口。
- 四档骨架：

  | 档位 | 徽章 | 7+1 维矩阵 | 并发规则汇总 |
  |---|---|---|---|
  | `lite` | 🟢 Lite | 不渲染（短改动低风险） | 不渲染 |
  | `standard` | 🟡 Standard | ✅ 全 7+1 行 | 仅列 hit ≥ 1 的规则 |
  | `deep` | 🔴 Deep | ✅ 全 7+1 行 | 全量 N 行 + adversarial_qa 数量 |
  | `cherry_pick_reuse` | 🔁 Cherry-pick 复用 | 不渲染（复用基线） | 不渲染 |

- 每档 cover 必含：① skill 名 + 版本号（首行）、② 档位徽章、③ CR 基本信息（CR/revision/Jira/分支）、④ Preflight 计数表（P0/P1/P2/P3/隐私候选）、⑤ LLM 自由结论段、⑥ 落款（评级 + 信号来源）。

- `gerrit_post.py` 默认启用 auto-cover：从 `--ctx` 或 `<review>.ctx.json` 读 ctx，自动用 `render_from_review_and_ctx` 包装 LLM 的 `cover` 字段（自由段落）。
- `--no-auto-cover` flag 可退回 v2.3.0 行为，让 cover 完全由 LLM 控制。
- LLM 输出 JSON 必含 `skill_meta = {name: "enhanced_code_review", version: "2.3.1"}`，`validate_review_json` 在 lite / standard / deep 三档都硬校验。

### 3) Cherry-pick 智能复用

**用户意图**：「关于同一个 topic 的不同提交需要每一笔提交都 review，但是不需要关联 topic，对于 cherry-pick 的提交可以按照最早提交的 CR 进行 review，然后其他的 cherry-pick 提交直接贴结果」。

**三级识别**（任一失败降级独立 review）：

1. **Gerrit 原生** — `cherry_pick_of_change` 字段（最可靠）
2. **同 Change-Id** — `change:<Change-Id>` 查询，取 `_number` 最小者为基线
3. **diff 指纹** — 所有文件 new-side 行 sha256 哈希全等

**流程**：

```
prepare_context
  ↓
complexity_assess → ctx.complexity.level (lite|standard|deep)
  ↓
cherry_pick_detect(cr) → ctx.cherry_pick = {is_cherry_pick, base_cr, base_review_exists, base_score, diff_identical, signals, reuse}
  ↓
if reuse:
    ctx.complexity.level = "cherry_pick_reuse"  # 覆盖
    Agent 跳过 LLM 扫描，直接走基线复用模板
else:
    Agent 按对应档位 prompt 评审
```

**复用产出**：cover 显式声明"复用自 CR {base_cr}"+ 三级信号证据；inline 评论按基线 CR 的 review JSON 原样贴出（保留行号与 path）。

**保底**：
- `diff_identical=False`（被 revert/rebase 改过）→ 降级独立 review，cover 声明"疑似 cherry-pick 但 diff 有差异"
- `base_review_exists=False`（基线 CR 还没人贴过 Code-Review）→ 不复用

### 4) review JSON schema 变更

```json
{
  "score": -1 | 0 | 1,
  "complexity_level": "lite|standard|deep|cherry_pick_reuse",
  "skill_meta": {"name": "enhanced_code_review", "version": "2.3.1"},
  "cherry_pick_info": {
    "reuse": false,
    "base_cr": null, "base_score": null, "base_summary": null, "base_url": null,
    "signals": {"api": null, "change_id_match": null, "diff_identical": null}
  },
  "dimensions_scanned": { ... 7+1 维, lite 档可空 dict ... },
  "rule_check_table": { ... 多语言并发规则, lite 档可空 dict ... },
  "cover": "<LLM 自由结论段，模板由 gerrit_post.py auto-cover 自动注入>",
  "comments": [ ... inline 评论, 见 references/08-llm-review-prompt.md ... ],
  "adversarial_qa": [ ... Deep 档每 P0/P1 一条 ... ]
}
```

### 5) CLI 串联推荐

```bash
source ~/.gerrit_env

# 1) prepare：拉数据 + 评级 + cherry_pick_detect，落 ctx.json
python3 scripts/gerrit_review.py 1015150 --prepare -o /tmp/ctx_1015150.json

# 2) Agent 读 ctx 后产 review JSON（含 skill_meta + cherry_pick_info），落 review.json

# 3) post：默认 auto-cover，读同名 ctx.json，渲染统一模板贴回
python3 scripts/gerrit_post.py /tmp/review_1015150.json --ctx /tmp/ctx_1015150.json
```

---

## §复杂度自适应（v2.3.0）

### 设计目标

**少量修改不要过度 review，高风险修改不能漏诊**。评级器按客观指标把评审工作量路由到三档：Lite / Standard / Deep。**Preflight 机械扫描（`gerrit_audit` + `consistency_scan` + `privacy_compliance_scan`）在所有档位都全跑**——这部分不吃 LLM token，是质量门禁的最后防线。LLM prompt 侧才按档位分叉。

### 三档分类

| 档位 | 触发条件（均满足为 Lite；任一满足为 Deep；否则 Standard） | LLM 工作量 | 产出要求 |
|------|--------------------------------------------------------|-----------|---------|
| 🟢 **Lite** | `changed_lines ≤ 10` **且** `file_count ≤ 1` **且** 全为注释/格式/日志文案/单 include/import **且** 无高风险关键词 **且** Preflight 无 P0/P1 **且** 无 privacy_candidate | 只问 3 件事：Jira 合规 / 低级错误 / 疑似 P0 漏诊 | cover ≥ 80 字；`dimensions_scanned` / `rule_check_table` 可为空 dict；必有 `complexity_level="lite"` |
| 🟡 **Standard** | 介于两档之间（默认档） | 完整 7+1 维 + rule_check_table + 三问 filter | v2.2.1 原硬校验 |
| 🔴 **Deep** | `changed_lines > 200` **或** 命中高风险关键词（mutex/thread/async/JNI/memcpy/AES/passwd/token/cert/privacy/PII/pthread_*/CMakeLists/AndroidManifest/permission/SELinux 等 30+ 个） **或** `audit_P0 ≥ 2` **或** `privacy_candidate_files ≥ 3` | Standard 之上追加：对抗式三问（每 P0/P1 必含） + 关键词热点强扫 + 隐私三重门控全流程 | cover ≥ 400 字；`adversarial_qa` 数量 ≥ P0/P1 数；`complexity_level="deep"` |

### 评级器实现

- 脚本：`scripts/complexity_assess.py`
- 入口：`assess(ctx) → {level, score, signals, reason, metrics}`
- 兼容两种 ctx：`gerrit_review.prepare_context()` 的 Gerrit 格式 和 `local_module_prepare.prepare()` 的本地模块格式
- 关键词表：`DEEP_KEYWORDS`（含并发/JNI/密码学/敏感字段/构建清单 5 大类 30+ 项正则）
- 琐碎改动识别：`_TRIVIAL_LINE_RE` 匹配注释/空行/单 include/import/日志函数调用

### CLI 使用

```bash
# 自动评级
python3 gerrit_review.py <CR>          # 评级后走对应 prompt
python3 gerrit_review.py <CR> -o ctx.json  # ctx.json 含 complexity 字段

# 手工覆盖
python3 gerrit_review.py <CR> --force-level deep      # 强制走 Deep
python3 gerrit_review.py <CR> --force-level standard  # 强制走标准
python3 gerrit_review.py <CR> --force-level lite      # 强制走 Lite（少用，慎防漏诊）

# 本地模块同样支持
python3 local_module_prepare.py frameworks/cm/videoplayer --force-level deep
```

### Preflight 与评级的关系（不可颠倒）

```
用户触发 → prepare_context 拉取 Gerrit 数据
       ↓
    [Preflight 机械扫描] ← 三档都全跑，不省略
       ├─ gerrit_audit (Jira / 空 catch / System.out / TODO)
       ├─ consistency_scan (Java/Kotlin 一致性)
       └─ privacy_compliance_scan (候选 A+B 门控)
       ↓
    [complexity_assess] ← 拿 Preflight 结果 + diff 指标计算档位
       ↓
    ctx.complexity.level ∈ {lite, standard, deep}
       ↓
    LLM 按档位加载对应 prompt 模板
       ↓
    validate_review_json 按档位放宽/收紧硬校验
       ↓
    gerrit_post.py 贴回
```

### 漏诊安全网

1. **Preflight 刚性前置**：不论档位，机械扫描先跑；若出 P0/P1 → 评级器自动禁入 Lite
2. **Lite 档 `score=-2` 警示**：若 LLM 在 Lite 档发现重大问题，产出 score=-2 时 `validate_review_json` 会在 stderr 打印明显警告，提示人工用 `--force-level standard` rerun
3. **Deep 档硬校验加码**：每 P0/P1 必附三问自检（反方 / 反例 / 证据），答不全直接 drop 该评论，不裸贴
4. **评级器异常回退**：`complexity_assess` 任何异常 → 回退 Standard，不阻断评审

### 性价比估算（保守假设）

| 档位占比（估） | Lite 60% | Standard 30% | Deep 10% |
|----------------|----------|--------------|----------|
| 典型 diff 行数 | 1-10 | 10-200 | > 200 或关键词 |
| LLM prompt token | ~3k | ~15k-30k | ~30k-60k |
| 相对 v2.2.1 节省 | ~80% | 0% | -20%（加重） |
| 质量目标 | 快速过筛 | 7 维全扫 | 7 维 + 对抗质询 |

**结论**：Lite 把 60% 流量的 token 成本降到原来的 ~20%，整体预期 token 消耗减少 ~45%，Deep 档在 10% 高风险场景加码确保不漏诊。

### 常见触发示例

| 改动 | 评级 | 原因 |
|------|------|------|
| 修注释错别字（3 行） | 🟢 Lite | all_lite_conditions_met |
| 日志文案改格式（2 行） | 🟢 Lite | trivial-only |
| 新增一个函数（30 行业务逻辑） | 🟡 Standard | diff_has_non_trivial_lines |
| 改 `std::lock_guard` 实现（5 行） | 🔴 Deep | high_risk_keyword:mutex |
| 重构一个文件（250 行） | 🔴 Deep | changed_lines>200 |
| 新增权限到 AndroidManifest.xml | 🔴 Deep | high_risk_keyword:AndroidManifest,permission |
| 改动含 `private_key` 字段 | 🔴 Deep | high_risk_keyword:private_key |

### 与团队硬规则的一致性

- **Jira 号合规检查**：Preflight `gerrit_audit.py` 全档位跑，Lite 档 LLM 也会复核 —— 不因档位下降而放行
- **隐私合规三重门控**：Lite 档若触发 `privacy_candidate_files ≥ 1` 会自动升档到 Standard；Deep 档强制走全三门（A+B+C）
- **CR-6 职责边界**：评级器与 LLM prompt 都不做 commit message 格式校验（那是 `autolink-chery-commit-msg` 的职责），评级器只把 commit message 文本作为关键词扫描的一个输入源


## Invoke Reporting

> 每次执行此 skill 时**必须**双段上报：开始前调 `report-invoke.sh`(pre) + 结束后调 `report-usage.sh`(post)，用同一个 `$KEY` 配对，服务端自动算 duration。

```bash
KEY="$(date +%s%3N)-$RANDOM"

bash <SKILLS_ROOT>/skillpack-client/scripts/report-invoke.sh \
  --skill-name "enhanced_code_review" --key "$KEY"

# ... 此 skill 的实际执行内容 ...

bash <SKILLS_ROOT>/skillpack-client/scripts/report-usage.sh \
  --skill-id "enhanced_code_review" --success true --key "$KEY"
```

失败时把 post 那行的 `--success true` 改成 `--success false --error "<msg>"`。

**`<SKILLS_ROOT>` 说明**：你本地 `skills/` 目录的绝对路径（skillpack-client 从 `$(dirname "$0")/../..` 即可得到）。跨 Mac/Linux/容器环境都自动兼容，不需要手动配置。
