# enhanced_code_review · 增强版代码评审 v2.5.3

本目录为 **enhanced_code_review** 技能包：在 **gerrit-review v2.7.0** 全部能力（**7+1** 维度评审 + 闭环增强 CL-1~CL-6 + BUILD-FAIL-1 红线 + Reply-Aware 增量评审 + 平台化设计共识软规则 P2/P3 + 多语言并发专项 + scan_hints 内嵌 + rule_check_table 强制）基础上保留 **本地模块评审**（无 CR 号）+ **复杂度自适应**（Lite/Standard/Deep 三档）+ **Topic 解耦**（v2.3.1 起，不回退）+ **Cover 模板化**（v2.3.1 起）+ **Cherry-pick 智能复用**（v2.3.1 起）。原版仅 Gerrit 场景可继续使用 `~/.cursor/skills/gerrit-review`。

## 运行时要求

- **最低支持 Python 3.6.9**（v2.1.2 起明示，已在 docker `python:3.6.15-slim` 与本机 Python 3.10.12 联合验证）。第三方依赖 `requests` / `urllib3` 由使用方自行安装。

## v2.5.3 新增（2026-06-10）

- **本地超集发布**：在官方 v2.5.2 基础上合并回本地独有的 **严重度↔分数一致性硬门禁** `gerrit_review.py::check_score_severity_gate`（与 gerrit-review 同源，官方 v2.5.2 zip 不含）：G1 P0 → score ≤ -1；G2 合并冲突/编译失败 → score == -2；G3 P1 → score ≤ -1；接入 lite/standard/deep 三档校验。
- **完整保留 v2.5.2 全部能力**（回帖模板强约束 / AUDI Jira 前缀 / codex 兼容）。

## v2.5.2 新增（2026-06-06）

- **回帖模板强约束（杜绝「模型自己写模板」）**：回帖 cover **必须**经 skill 模板（`cover_template`）渲染，禁止模型自由写整段模板。
- **`scripts/gerrit_post.py`**：缺 ctx / `--no-auto-cover` / `--cover` 等绕过模板的路径不再静默退回裸 cover，统一改为**硬失败 `exit 4`**；新增 `--allow-raw-cover` 显式放行裸 cover（并打 stderr 告警）。
- **`scripts/gerrit_review.py --post`**（`post_from_review_json`）：贴回前统一调用 `cover_template.render_from_review_and_ctx`（此前**从不**走模板、直接 POST 裸 cover），缺 `--ctx` / `--no-auto-cover` 同样需 `--allow-raw-cover`；新增 CLI `--no-auto-cover` / `--allow-raw-cover`。
- **`scripts/gerrit_review.py::validate_review_json`**：新增 v2.5.2 守卫，`cover` 字段命中 skill 模板抬头 / 顶部结论 H3 / 维度矩阵 / Preflight / 落款等结构标记即拒绝 POST，强制 LLM 只写「### 📝 LLM 评审结论」之下的纯散文。
- **`scripts/cover_template.py`**：新增 `_sanitize_llm_summary` 消毒 LLM 段（剥离误塞的模板结构）；cherry-pick 复用同时认 `review.cherry_pick_info.reuse` 与 `ctx.cherry_pick.reuse`，缺 base_info 时从 `ctx.cherry_pick` 兜底合成，保证 cherry-pick 一定走 cherry-pick 模板；`SKILL_VERSION` → `2.5.2`。
- **能力无回退**：`references/01~16` 全部不动；7+1 维 / 隐私合规三重门控 / 闭环增强 CL-1~CL-6 / BUILD-FAIL-1 红线 / Reply-Aware / 复杂度自适应 / Topic 解耦 / 本地模块评审 / Cherry-pick 三级识别全部继承；review.json schema 向后兼容；Python 3.6.9 兼容。

## v2.5.1 新增（2026-05-21）

- **codex 兼容修复**：`scripts/gerrit_audit.py` 与 `scripts/privacy_compliance_scan.py` 移除 PEP 585（`list[..]` / `dict[..]` / `tuple[..]`）、PEP 604（`X | None`）、PEP 563（`from __future__ import annotations`）以及 `dataclasses` 依赖；所有运行时类型注解统一切回 `typing` 模块（`List` / `Dict` / `Tuple` / `Optional` 等）。
- **Candidate 数据类改写**：`privacy_compliance_scan.py` 中 `@dataclass class Candidate` → 普通 `class Candidate(object)` + 显式 `__init__`，语义保持一致。
- **运行时承诺**：继续保持「最低 Python 3.6.9」承诺，docker `python:3.6.15-slim` 全量 import 验证通过（`py36 import OK`）。
- **能力无回退**：v2.5.0 闭环增强 CL-1~CL-6 / BUILD-FAIL-1 红线 / contract scan LRU cache / cover 自动徽章 / review.json schema 新可选字段全部保留；`skill.json` `platform` 字段新增 `codex`。

## v2.5.0 新增（合并自 gerrit-review v2.7.0，2026-05-15）

- **闭环增强机制 CL-1~CL-6**（`references/15-closeloop-enhancement.md`）：临时策略 reply 硬约束 / 未闭环清单 unresolved_issues / 契约变更跨 CR 上下文感知 / cover 带病合入说明段强制 / 真修复识别 fix_mismatch / 契约硬扫候选层
- **BUILD-FAIL-1 预编译失败质量红线 P0**（`references/16-build-fail-redline.md`）：Verified / Prebuild-Check label -1/-2 → 直接 -2 跳过 LLM 评审
- **contract scan LRU cache**：兄弟 CR 查询进程级缓存
- **兄弟 CR 拉取改 `o=CURRENT_FILES`-only**：节省 ~30% 流量
- **cover 自动徽章升级**：顶部硬约束 `🤖 enhanced_code_review v2.5.0 · 🟡 Standard`
- `validate_review_json` 新增 CL-1 / CL-2 / CL-4 / BUILD-FAIL-1 强制校验
- review.json schema 新增可选字段：`unresolved_issues` / `fix_mismatch_flag` / `contract_change_scan_results` / `reply_classification`，向后兼容

## v2.4.1 新增（同步 gerrit-review v2.5.1）

### 平台化设计共识第 8 维度（软规则 P2/P3）

- 新增 `references/14-platform-design-principles.md`：8 条规则 PLAT-1~PLAT-8 + 平台化总目标 G1~G5 + 需求三分类（🟢通用/🟡可选/🔴定制）+ 配置化三层（静态/动态/客户）+ 平台-项目-客户三层分离 + ISO 25010 八大质量属性 + 底座能力复用清单（通信/持久化/健康/启动/配置/时间/日志）+ 评论输出格式 + 豁免清单 + 复盘机制。
- **定级硬约束**：所有 `dimension == "platform_design"` 的 inline 评论 `level` 必须为 `P2` 或 `P3`。`gerrit_review.py::validate_review_json` 在 v2.4.1 强制守卫，拒绝任何 P0/P1（应改归类到对应硬维度）。
- **不影响打分决策**：仅命中 PLAT-* 的 CR 仍可 +1，平台化共识只是叠加 inline 提示，不阻断合入。
- `dimensions_scanned` 新增 `platform_design` key（与 `cpp_concurrency_stl` 同列「允许 scanned=false 但 key 必填」清单 `DIMS_ALLOW_NOT_SCANNED`）。

### Cover 排版规范同步

- `references/13-cover-format-spec.md` 抬头版本标记升至「v2.4.1 同步自 gerrit-review v2.5.1」。
- cover 骨架表格新增「平台化设计共识 (P2/P3)」一行。
- 综合评估段统一表达为「7+1 维度评审 + 平台化共识扫描」+「PLAT-* 命中 N 条，仅作改进提示，不影响打分」。

## v2.4.0 能力（保留，2026-05-12）

- **Reply-Aware 增量评审 + 6 分支决策矩阵**：`build_prior_review_context` 读 inline comments + cover messages + score 历史，识别 owner 任何 reply；`compute_review_decision` 按 owner reply / 他人 -1 实质性 / 代码是否有变动 自动选 proceed / skip / incremental。
- **P0 豁免铁律**：P0 仅 owner reply 合理性可豁免，不能通过特殊备注降级；特殊备注影响 P1 及以下。
- **reply_disposition / incremental_summary** 字段：review.json 新 schema，Standard/Deep 档硬校验，Lite 档必填字段但内容可空。
- ECR **保留 Topic 解耦**（`gerrit_client.find_related_crs` 不回退；Reply-Aware 评审链路只依赖本 CR 自身历史，不按 Jira/topic 反查兄弟 CR）。

## v2.3.x 能力（保留）

- 复杂度自适应（Lite/Standard/Deep 三档）+ Topic 解耦 + Cover 模板化（`scripts/cover_template.py`，v2.4.0 升级支持 Reply-Aware 增量汇总块）+ Cherry-pick 智能复用（`scripts/cherry_pick_detect.py`）。

## v2.2.1 能力（保留）

- scan_hints 内嵌 User Prompt（每个 `lang_info` 内填充 `scan_hints`，LLM 按表逐条扫描）。
- rule_check_table 强制（Output JSON 必须含 `rule_check_table`，按语言分组逐条规则填 `{scanned, findings}`）。
- 多语言并发与容器/集合专项（rule_ids 校准与 09/11/12 文件实际一致）。

## 文件结构

```
enhanced_code_review/
├── SKILL.md                          ← 触发 / 维度 / 工作流
├── VERSION                           ← 2.4.1
├── CHANGELOG.md
├── README.md                         ← 本文件
├── references/
│   ├── 01-solid-principles.md
│   ├── 02-security.md
│   ├── 03-performance.md
│   ├── 04-error-handling-boundaries.md
│   ├── 05-code-quality-style.md
│   ├── 06-automotive-middleware.md
│   ├── 07-review-methodology.md
│   ├── 08-llm-review-prompt.md       ← v2.4.1: 第 8 维度 platform_design + Step 9 + level 守卫自检
│   ├── 08-llm-review-prompt-lite.md
│   ├── 08-llm-review-prompt-deep.md
│   ├── 09-cpp-concurrency-stl-traps.md
│   ├── 09-local-module-review.md     ← 本地模块（独有）
│   ├── 10-privacy-compliance.md
│   ├── 11-java-concurrency-collection-traps.md
│   ├── 12-c-concurrency-traps.md
│   ├── 13-cover-format-spec.md       ← v2.4.1: 7+1 维度表 + 平台化共识行
│   └── 14-platform-design-principles.md ← v2.4.1 新增：平台化设计共识 P2/P3
└── scripts/
    ├── gerrit_client.py
    ├── gerrit_inbox.py
    ├── gerrit_show.py
    ├── gerrit_audit.py
    ├── consistency_scan.py
    ├── privacy_compliance_scan.py
    ├── gerrit_review.py              ← v2.4.1: REQUIRED_DIMS + DIMS_ALLOW_NOT_SCANNED + platform_design level 守卫
    ├── gerrit_post.py
    ├── cherry_pick_detect.py         ← v2.3.1 独有
    ├── complexity_assess.py          ← v2.3.0 独有
    ├── cover_template.py             ← v2.4.0 升级独有
    ├── local_audit.py                ← 本地模块（独有）
    └── local_module_prepare.py       ← 本地模块（独有）
```

## 与 gerrit-review 的关系

| | gerrit-review v2.5.1 | enhanced_code_review v2.4.1 |
|---|---|---|
| Gerrit 自动化 | Yes | Yes |
| 本地模块评审 | No | Yes |
| 隐私合规 P0 | Yes | Yes |
| 多语言并发专项 | Yes | Yes |
| 自动语言分派 | Yes | Yes |
| scan_hints 内嵌 | Yes | Yes |
| rule_check_table 强制 | Yes | Yes |
| Reply-Aware 增量评审 + 6 分支决策 | Yes | Yes |
| Cover 排版规范（references/13） | Yes | Yes |
| **平台化设计共识第 8 维度（P2/P3 软规则）** | Yes | Yes |
| Topic 解耦 (`find_related_crs` 删除) | 否（仍保留同组关联） | **Yes**（v2.3.1 起不回退） |
| 复杂度自适应（Lite/Standard/Deep） | No | Yes |
| Cover 模板化 (`cover_template.py`) | No | Yes |
| Cherry-pick 智能复用 (`cherry_pick_detect.py`) | No | Yes |

## 配置

```bash
export GERRIT_BASE="https://your-gerrit.example.com"
export GERRIT_USER="your-gerrit-username"
export GERRIT_HTTP_PASSWORD="your-gerrit-http-password"
```

## 使用

```bash
# Gerrit 评审
python3 scripts/gerrit_review.py 993636 --prepare -o /tmp/ctx.json
python3 scripts/gerrit_review.py 993636 --post /tmp/review.json --ctx /tmp/ctx.json

# 本地模块评审
python3 scripts/local_module_prepare.py <模块路径> --repo auto -o /tmp/local_ctx.json

# 独立隐私合规扫描
python3 scripts/privacy_compliance_scan.py <file.java> [--window 8]
```

## 版本变更

详见 `CHANGELOG.md`。
