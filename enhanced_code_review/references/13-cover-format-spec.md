# Gerrit Cover 排版规范（v2.7.0，2026-05-15；enhanced_code_review v2.5.2 强约束，2026-06-06）

## 概要

v2.7.0 从 enhanced_code_review v2.4.1 合并 cover 模板化能力。所有 Gerrit cover 由 `scripts/cover_template.py` 生成，顶部必含 skill 名 + 版本号 + 档位徽章。`gerrit_post.py` 默认 auto-cover（走 `render_from_review_and_ctx`）。

> **enhanced_code_review v2.5.2 模板强约束（杜绝「模型自己写模板」）**：回帖 cover **必须**经 `cover_template` 渲染，模型只能在 review.json 的 `cover` 字段写「### 📝 LLM 评审结论」之下的**纯结论散文**，不得自带抬头/徽章/顶部结论 H3/8 大维度矩阵/Preflight/cherry-pick 块/落款等模板结构。
> - 两条贴回路径（`gerrit_post.py`、`gerrit_review.py --post`）统一走模板；缺 ctx / `--no-auto-cover` / `--cover` 等绕过模板的路径必须显式 `--allow-raw-cover` 才放行，否则 `exit 4`。
> - `validate_review_json` 检测到 `cover` 自带模板结构标记即拒绝 POST；`cover_template._sanitize_llm_summary` 在渲染前再次剥离误塞结构作为防御纵深。
> - cherry-pick 复用同时认 `review.cherry_pick_info.reuse` 与 `ctx.cherry_pick.reuse`，保证 cherry-pick CR 一定走 cherry-pick 模板。

---

## 顶部抬头（领型硬要求）

首评 + Standard：
```markdown
## 🤖 gerrit-review v2.7.0 · 🟡 Standard
```
增量评审叠加 `· 🔄 Incremental`：
```markdown
## 🤖 gerrit-review v2.7.0 · 🟡 Standard · 🔄 Incremental
```
Cherry-pick 复用：
```markdown
## 🤖 gerrit-review v2.7.0 · 🔁 Cherry-pick 复用
```

---

## 首评 cover 骨架（Standard，按用户截图风格）

```markdown
## 🤖 gerrit-review v2.7.0 · 🟡 Standard

**评审结论：<+1/+2/-1/-2>（<一句话>）**

---

### 1. CR 元信息（直读 ctx，未生成）

| 项 | 值 |
|---|---|
| CR | [<num>](<gerrit URL>) |
| Branch | <branch> |
| Owner | <owner_username> |
| Jira | <jira-num>（白名单 ✅）|
| Change-Id | <change_id> |
| 改动 | +X / -Y（N 文件）|
| 主要内容 | <subject> |

---

### 2. Reply-Aware 评审决策

| 项 | 值 |
|---|---|
| self_prior_comments | N 条（首评/有历史）|
| owner_replies | N 条 |
| 他人 -1 | 是/否 |
| 撤回记录 | 是/否 |
| review_decision | **proceed / incremental / skip** |

---

### 3. 8 大维度扫描

| 维度 | 结果 | 关键证据 |
|---|---|---|
| 1. SOLID | ✅/⚠️/❌ | ... |
| 2. 安全 | ... | ... |
| 3. 性能 | ... | ... |
| 4. 错误处理 + 边界 | ... | ... |
| 5. 代码质量 | ... | ... |
| 6. 车载中间件 | ... | ... |
| 7. 隐私合规 | ... | ... |
| 8. 平台化设计共识 (P2/P3 软规则) | ... | ... |

---

### 4. <语言专项> 并发与集合扫描（J-CONC/J-STD/J-LIFE 12 条 / C-CONC/C-STD/C-LIFE 12 条 / C-MUTEX/C-RACE 15 条）

| 规则 | 命中 | 证据 |
|---|---|---|

---

### 5. audit 候选 X P0 上下文判定（CL-3/CL-5/历史代码豁免）

<逐条 audit 候选项的 confirm/drop 决策>

---

**综合：P0=X / P1=X / P2=X / P3=X**（PLAT-* 命中 N 条，仅作改进提示，不影响打分），建议 <+1/+2/-1/-2>。
```

---

## 增量评审 cover（在首评骨架上叠加）

```markdown
## 🤖 gerrit-review v2.7.0 · 🟡 Standard · 🔄 Incremental

<其他保持>

### 6. 增量评审汇总

| 维度 | 前次 | 本次 | 增减 |
|---|---|---|---|
...

<details>
<summary>Reply 处置明细（前 5 条）</summary>

| # | 原条目 | reply | disposition |
|---|---|---|---|
...
</details>
```

---

## Lite 档 cover（简化版）

Lite 档不渲染 8 维矩阵表，仅：
- 顶部抬头 + 评审结论 H3
- CR 元信息
- Preflight 机械扫描计数表
- LLM 短文（复核 Jira 合规 / 低级错误 / 疑似 P0 漏诊）
- cover ≥ 80 字符

## Deep 档 cover（增强版）

Deep 档除 Standard 全部字段外追加：
- 4.5 并发规则全量 N 行表（含 0 发现也列）
- adversarial_qa 三问：每 P0/P1 含反方 / 反例 / 证据
- cover ≥ 400 字符

## Cherry-pick 复用 cover

```markdown
## 🤖 gerrit-review v2.7.0 · 🔁 Cherry-pick 复用

### 🔁 Cherry-pick 复用依据
本 CR 识别为 **CR <base>** 的 cherry-pick，diff 与基线全等；直接复用基线评审结果。

### 📌 基线结论
- 基线 CR：[<base>](<base url>) · 打分 **+1**
- 基线摘要：原 review +1, 无 P0/P1
```

---

## 以下是 v2.4.3 原始规范（保留，供历史参考）

# Gerrit Cover 排版规范（v2.4.3 新增，2026-05-06）


## 缘起（首次：2026-05-06 早 / 再次强调：2026-05-06 16:37 北京）

2026-05-06 志强先后两次给出两张截图对照：
- **丑格式**：整段纯散文混在一起，P0/P1/P2/P3 命中数藏在"综合："结尾一句里，读者必须通读全文才能找到结论
- **好格式**：顶部 H3 结论 → CR 元信息（一行概要）→ 分点"核心修复方向"→ H3「7 大维度扫描」表格

**16:37 复盘**：v2.4.3 上午已经定过这条规则，但下午又出现散文版（CR 不详，志强截图标注 "这个太丑了"）。说明 LLM 在 cron 长链路里偶尔偷懒不读 13 文件 → **必须把这条作为最高优先级硬约束**，cron prompt + 08-llm-review-prompt.md + gerrit_post.py 校验三处都要硬化。

**规则**：以后所有 Gerrit cover 按"好格式"输出，**绝对禁止**整段散文版。任何散文版应在 gerrit_post.py 质量校验中被拒绝（exit=3）。

---

## 好格式硬要求（必须全部满足）

### 1. 顶部 H3 结论块（第一眼可读）
```markdown
### 评审结论：+1（可合入）
```
或：
```markdown
### 评审结论：+1（可合入，2 条改进建议）
```
或：
```markdown
### 评审结论：-1（不可合入，3 条 P0）
```

- 分数必须 **斜线前置**（+1 / +2 / -1 / -2，不写 0）
- 括号里用一句话标注：`可合入` / `可合入，N 条改进建议` / `不可合入，N 条 P0` / `Cherry-pick 与原 CR 一致`

### 2. CR 元信息一行（仅 cherry-pick 场景）
```markdown
Cherry-pick from CR 1011185（分支 al_chery-d01_dev2 → 本分支 al_chery-t1j-f12_8255_release）

- 与原 CR 文件签名完全一致：+387/-14，2 个文件（taskmanager.cpp / test.cpp）
- 改动内容、风险评估、UT 设计均与原 CR 相同
```

### 3. 主 CR 场景：CR 号 + Jira + 一句话摘要
```markdown
CR 1011185 [D01-46510](url) / [CHYT1V-1171](url) TaskManager IO 长生命周期保活修复：+387/-14，2 个文件。核心修复方向**正确**：在 ProcessSubmitedTask 中将 IOEventNotifyTask 与 TimerTask 一并按"长生命周期"任务处理，避免因 cycle 背压或单次超时被从 active_tasks/task_index 摘除，彻底堵上 custom.mcu.* PPS 订阅链 ~61s 后永久失效的根因。

UT 增补质量非常高，**直接回归本 bug 场景**：`Pipe_LongCallback_DoesNotKillNotifier` 用 1800ms 超限回调验证 IO 任务不被误杀，第二次事件仍能触发。
```

要点：
- **Jira 号必须超链接**，格式 `[D01-46510](https://.../browse/D01-46510)`
- **加粗关键判断词**：`**正确**` / `**直接回归本 bug 场景**` / `**必改**` / `**阻断点**`
- **code 格式强调标识符**：`` `Pipe_LongCallback_DoesNotKillNotifier` `` / `` `ProcessSubmitedTask` `` / `` `custom.mcu.*` ``
- 不用整段连写，一句一换行或一段一换行

### 4. 「7 大维度扫描」表格块（必须）

```markdown
### 7 大维度扫描

| 维度 | 结果 |
|---|---|
| SOLID | ⚠️ 1 P2 — CleanupCompletedTasks 保活判定未同步 IOEventNotifyTask（语义不对称） |
| 安全 | ✅ 无发现 |
| 性能 | ✅ 无发现（热路径新增 2 次 dynamic_cast 顺承现有模式） |
| C++ 并发与 STL 专项 | ✅ 12 条规则扫描完成，0 命中 |
| 错误处理 | ✅ 无发现 |
| 代码质量 / Google Style | ⚠️ 1 P3 — 第 565 行注释未同步更新（"TimerTask" 应改为 "TimerTask / IOEventNotifyTask"） |
| 车载中间件专项 | ✅ 无发现（修复直接解车机量产 P0 — PPS 通道 61s 断流） |
| 隐私合规 | ✅ 无发现 |
```

**视觉元素约定**：
- ✅ = 无发现 / 通过
- ⚠️ = 有非阻断级发现（P2/P3）
- ❌ = 有阻断级发现（P0/P1）
- 🔒 = 隐私合规专项独立图标（可选）

**每行格式**：`| <维度名> | <图标> <数量><级别> — <一句话摘要> |`
- 有发现：`⚠️ 1 P2 — <内容>`
- 无发现：`✅ 无发现` 或 `✅ 无发现（<补充说明>）`
- **不要**在表格里写长段文字，超过 50 字移到下方章节

### 5. 综合评估段（结尾，一段概述）

```markdown
已完成 7+1 维度评审：
(1) SOLID — cmake 是构建配置，目标拆分（update_hal/update_service/update_service_tester）边界清晰，符合单一职责；
(2) 安全 — ENABLE_UPDATE_SERVICE_TEST 默认 ON 在量产场景激进（建议 release 关），AL_MCU_DRY_RUN/AL_MCU_DRY_RUN 与 compile_definitions，不会污染 release 路径，OK；
...
综合：P0=0 / P1=0 / P2=1 / P3=2，整体属于 OTA 重构系列的第一步基础设施搭建，单独看风险低，建议 +1 通过；建议 2/3、3/3 合入时补做 C++ 并发与升级回滚专项评审。
```

要点：
- 用 `(1)` `(2)` `(3)` 编号逐维度总结（每条 20-50 字）
- 结尾必带「**综合：P0=X / P1=X / P2=X / P3=X**」硬统计
- 结尾给**明确可执行建议**（+1 通过 / 补 C++ 专项 / 等后续 CR 一起评审）

---

## 丑格式（禁止）

对比丑格式的表现：

```
【gerrit-review skill v2.4.2 自动评审 -1】

本 CR 是 xxx 的修改，主要完成了 xxx 功能。经过评审发现以下问题：首先，在 xxx 文件中 xxx 方法没有处理 xxx 异常；其次，xxx 接口的签名变更会影响下游依赖；再次，xxx 等等。综合来看问题较多，建议回滚重做。P0=2, P1=3, P2=1, P3=0。
```

丑在哪：
1. **结论藏尾**：分数 -1 藏在标题里，具体问题数量在最后一句
2. **无表格**：维度扫描结果全挤在一段散文里
3. **无图标**：读者无法 3 秒扫视判断严重程度
4. **无加粗**：关键词"必改"/"阻断"/"正确"无视觉权重
5. **无 code 标识符**：类名、方法名、Jira 号全是裸文本，复制定位难
6. **无段落分层**：H3 标题缺失，整篇一块大头

---

## Markdown 强制元素清单

| 元素 | 用法 | 示例 |
|---|---|---|
| `### H3 标题` | 每个大块（结论 / 维度扫描 / 综合评估）之前 | `### 评审结论：+1（可合入）` |
| `**bold**` | 判断词、关键修复方向、P0 警示 | `**正确**` / `**必改**` |
| `` `code` `` | 类名/方法名/常量/路径 | `` `ProcessSubmitedTask` `` / `` `custom.mcu.*` `` |
| `[text](url)` | Jira 号、CR 号、文档号 | `[D01-46510](https://.../browse/D01-46510)` |
| `\| 表格 \|` | 7 大维度扫描 | 见 §4 |
| `- 列表` | 同层并列要点 | cherry-pick 一致性证据 |
| emoji（✅⚠️❌） | 表格里的状态列（不在正文滥用） | 见 §4 视觉元素 |

---

## 对 gerrit_post.py / review JSON 的影响

- `cover` 字段值**必须是合法 markdown**（不是纯文本），Gerrit Web UI 默认渲染 markdown
- 换行用真实 `\n`，不要用连续空格 / br
- 表格前后必须有空行（markdown 规范）
- H3 用 `###`（不用 H1 `#`，Gerrit cover 空间有限，H3 大小正合适）

## v2.4.3 之后的 review 产出流程

LLM 在产出 cover 时按以下骨架填：

```markdown
### 评审结论：<分数>（<一句话>）

<CR 元信息 + 一句话摘要，1-3 段，带 **bold** + `code` + [link]>

### 7 大维度扫描

| 维度 | 结果 |
|---|---|
| SOLID | ... |
| 安全 | ... |
| 性能 | ... |
| <C++/Java/C> 并发与 STL 专项 | ... |
| 错误处理 | ... |
| 代码质量 / Google Style | ... |
| 车载中间件专项 | ... |
| 隐私合规 | ... |
| 平台化设计共识 (P2/P3) | ... |

<可选：「核心修复方向」「关键风险」「必改清单」等附加块>

### 增量评审汇总（v2.5.0，有历史评审时必填）

| 指标 | 数量 |
|---|---|
| 前次评论总数 | N |
| 已修复 (resolved) | X |
| 未修复 (persist) | Y |
| 部分修复 (partial) | P |
| owner 回复采纳 (dropped_by_reply) | D |
| 备注降级 (downgraded_by_note) | G |
| 本次新发现 | Z |

### 综合评估

已完成 7+1 维度评审 + 平台化共识扫描：(1) ... (2) ... ... 综合：P0=X / P1=X / P2=X / P3=X（其中 PLAT-* 命中 N 条，仅作改进提示，不影响打分），<结论建议>。
```


---

## v2.6.0 新增 — 「带病合入说明」段（CL-4）

### 强制规则

`unresolved_issues.length > 0` 的 CR，cover **必须**含「带病合入说明」段。

### 模板（含未闭环）

```markdown
## ⚠️ 带病合入说明

本 CR 已识别 **N 项未闭环问题**，全部已挂跟踪。FO 需在量产前确认全部恢复。

| 编号 | 等级 | 问题 | 接受原因 | 跟踪 Jira | 量产闸口 |
|---|---|---|---|---|---|
| U1 | P1 | activateSystem 缺 setActiveBootSlot | owner 临时策略 | [CHYKP31-1740](https://jira.../CHYKP31-1740) | 2026-06 量产前 |
| U2 | P1 | getUpgradeResultAfterReboot 缺 isSlotMarkedSuccessful | owner 临时策略 | [CHYKP31-1741](...) | 2026-06 量产前 |
```

### 模板（无未闭环，推荐显式声明）

```markdown
## ✅ 闭环状态

本 CR 无未闭环问题。
```

### 校验

`validate_review_json` 强制：
- `unresolved_issues.length > 0` AND cover 不含「带病合入说明」 → POST 拒绝
- 每个 unresolved_issues 条目必须含 `level / path / title / rationale_accepted / tracking_jira / risk_summary` 字段

### 与其他段的位置

建议放在 cover 末尾「综合评估」之前：

```
1. H3 评审结论
2. CR 元信息
3. 8 大维度扫描表
4. 维度命中详情（如有）
5. ⚠️ 带病合入说明（如有未闭环）
6. ✅ 闭环状态（如无未闭环，可选）
7. 综合评估
```

---

## v2.6.0 新增 — 契约变更上下文感知段（CL-3）

当 `contract_change_candidates` 非空时，cover 必须显式呈现 `contract_consistency.assessment`：

| assessment | cover 应包含的话术 |
|---|---|
| `context_aware_ok` | "检测到契约变更，已配套兄弟 CR（[CR x] 覆盖另一端），视为正常协作" |
| `single_side_p2` | "⚠️ 检测到契约变更仅单端修改，已提 P2 提醒；建议 owner 与协作方确认另一端是否同步" |
| `mismatch_p0` | "❌ 检测到契约变更两端不一致，已判 P0；详见 inline 评论" |
| `no_jira_cannot_verify` | "⚠️ 检测到契约变更但当前 CR 无 Jira 号，无法跨 CR 比对；已提 P2 提醒 owner" |

绝对禁止：契约变更不查 contract_consistency 就一刀切判 P0。
