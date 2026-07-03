# 15 · 评审闭环增强机制（v2.6.0 新增）

> **设立背景**：v2.5.x 在「发现 P0/P1 → 接受 owner reply → 降级 / drop」链路上过于宽松，存在「带病合入」失效路径。本文件定义评审的协商层（L3）+ 跟踪层（L4）精华规则，把 skill 拦截能力从「发现」升级到「闭环」。
> **来源依据**：业务四组 2026 年 5 月双周代码评审复盘 + 中间件平台化体系文档。
> **本文件规则与既有维度正交叠加，不替代任何 P0/P1 规则。**

---

## 一、临时策略 reply 硬约束识别（CL-1）

### 规则定义

owner reply 中含下列「临时性 / 取舍式 / 拖延式」信号词时，**禁止**自动豁免原 P0/P1：

**临时性关键词集**：
- 临时策略 / 临时方案 / 临时实现
- 上线前 / 后续 CR / 后续修 / 后续优化 / 这版先 / 这次先 / 暂时 / 先这样 / 等到 / 等XX再
- TODO / FIXME / XXX 注释式声明
- 简化 / 简化复杂度 / 降低代码复杂度（取舍式说辞）

### 处置矩阵

| reply 模式 | 原 P0 处置 | 原 P1 处置 | 允许 +1 合入 |
|---|---|---|---|
| 真合理解释（**有技术依据且可在代码中验证**） | drop | drop / 降级 | ✅ |
| **临时策略 + 明确关联 Jira（如 `CHYKP31-1740`）** | **降为 P2 + 写入 unresolved_issues** | **降为 P2 + 写入 unresolved_issues** | ✅ |
| **临时策略 无关联 Jira** | **维持 P0** | **维持 P1** | ❌ |
| **简化复杂度 / 取舍式** 且无量化依据 | **维持 P0** | **维持 P1** | ❌ |
| 无 reply / owner 未回应 | 维持 P0 | 维持 P1 | 视情况 |

### LLM 落地要求

LLM 在 `reply_disposition[]` 中对每条 owner reply 必须填 `reply_classification` 字段：

```
- "rational"            ：真合理（有技术依据且代码可验证）
- "temporary_with_jira" ：临时策略 + 关联 Jira（带病合入但可控）
- "temporary_no_jira"   ：临时策略但无 Jira（不可豁免）
- "tradeoff_no_data"    ：取舍式说辞无量化依据（不可豁免）
- "no_reply"            ：owner 未回应
```

---

## 二、未闭环清单（unresolved_issues）强制产出（CL-2）

### 规则

任何 `reply_classification = "temporary_with_jira"` 的降级条目，必须在 review.json 产出对应的 `unresolved_issues[]` 条目，缺失则 validate 拒绝 POST。

### Schema

```json
"unresolved_issues": [
  {
    "level": "P1",
    "path": "src/com/autolink/ota/updater/AndroidUpdater.java",
    "line": 168,
    "title": "activateSystem 未调 setActiveBootSlot",
    "rationale_accepted": "owner 标注「临时策略，上线前必改」",
    "tracking_jira": "CHYKP31-1740",
    "deadline": "2026-06-30",
    "risk_summary": "Android A/B 升级 bootloader 不切分区，重启回滚"
  }
]
```

### 处置流程

```
P0/P1 命中 + owner reply 含临时性关键词
  ↓
是否有 tracking_jira？
  ↓
有 → 走 temporary_with_jira：
      reply_disposition 标 "downgraded_by_temporary"
      原 level 写入 unresolved_issues[]
      cover 必含「带病合入说明」段
      允许 +1
  ↓
无 → 走 temporary_no_jira：
      reply_disposition 标 "persist_no_jira"
      维持原 P0/P1
      score 决策按原级别处理（P0 → -1）
```

---

## 三、跨 CR 一致性检查（上下文感知）（CL-3）

### 核心约束（v2.6.0 志强 2026-05-15 明确）

**评审契约变更必须区分单人闭环 vs 多人协作两种现实场景**：

| 场景 | assessment | 评审定级 | 是否阻断 |
|---|---|---|---|
| **同一 owner 在单 CR / 多 CR 内闭环改了两端，且两端契约值不一致** | `single_owner_closed_loop_need_value_check` | **P0** | ❌ 阻断 |
| 同一 owner 单 CR 内闭环改了两端 + 契约值一致 | `single_owner_closed_loop_need_value_check` | 不发评论 | ✅ |
| 多人多 CR 协作覆盖两端 | `context_aware_ok_multi_owner` | 最多 P2 提醒 | ✅ 不阻断 |
| 当前 owner 仅改单端（无另一端配套 CR） | `single_side_only_single_owner_p2` | **P2 提醒** | ✅ 不阻断 |
| 多人协作但仅检测到单端配套 | `single_side_multi_owner_p2` | **P2 提醒** | ✅ 不阻断 |
| 无 Jira 号 / 扫描失败 | `no_jira_cannot_verify` / `scan_failed_use_p2` | **P2 提醒** | ✅ 不阻断 |

**核心原则**：
1. **单人 CR 自闭环场景**——一个人在自己提交的范围内能改完两端，是 owner 的责任，必须自己保证一致；不一致按 P0 处理（不阻断会被 +1 但 P0 触发 -1）
2. **多人协作场景**——跨进程契约变更最终人工会对齐（cover 评审 / 跨组协调），不需要 AI 阻断；最多 P2 提醒
3. **绝对禁止**仅凭契约变更本身就判 P0/P1，必须先看 `contract_consistency.assessment`

### LLM 必须接收的上下文

LLM prompt 中必须充分提示：

> 契约变更评审前请充分考虑：
> - 这是单人单 CR 改动，还是多人多 CR 协作？
> - 是否有同 Jira / 同 topic 下的兄弟 CR？兄弟 CR 是否覆盖了 server / client 任一端？
> - 是否有最近 30 天内已合入主干的相关 CR 实现了配套修改？
> - 上下游协作场景下，单端 CR 修改契约**不等于** ABI BREAKING；仅当上下游契约真实不一致才是 P0。

### 实施

`gerrit_audit.py` 加 `contract_consistency_scan`：
1. 检测当前 CR 是否修改了 `current.txt` / `*.aidl` / `*.proto` / Bundle key 字符串
2. 如是，查 Gerrit：
   - 同 topic 下所有 CR
   - 同 Jira 下最近 60 天的 CR（含已合入）
   - 兄弟仓库的相关变更
3. 输出到 ctx：

```json
"contract_consistency": {
  "changed_contracts": ["UPDATE_STATUS.SUCCESS", "OTA_TYPE.ANDROID"],
  "sibling_crs": [
    {"cr": 1011499, "status": "MERGED", "side": "service", "synced": true},
    {"cr": 1015800, "status": "NEW", "side": "client_sdk", "synced": false}
  ],
  "client_side_found": true,
  "server_side_found": true,
  "both_sides_consistent": true,
  "assessment": "context_aware_ok / single_side_p2 / mismatch_p0"
}
```

LLM 据此判定等级，避免一刀切。

---

## 四、cover「带病合入说明」段强制（CL-4）

### 强制规则

任何 `unresolved_issues.length > 0` 的 CR，cover 必须含「带病合入说明」段。

### 模板

```markdown
## ⚠️ 带病合入说明

本 CR 已识别 **N 项未闭环问题**，全部已挂跟踪。FO 需在量产前确认全部恢复。

| 编号 | 等级 | 问题 | 接受原因 | 跟踪 Jira | 量产闸口 |
|---|---|---|---|---|---|
| U1 | P1 | activateSystem 缺 setActiveBootSlot | owner 临时策略 | [CHYKP31-1740](...) | 2026-06 量产前 |
```

或（无未闭环时显式声明）：

```markdown
## ✅ 闭环状态

本 CR 无未闭环问题。
```

### 实施

`validate_review_json` 中加：
- `unresolved_issues.length > 0` → cover 必须含 `带病合入说明` 关键词
- `unresolved_issues.length == 0` → cover 含 `闭环状态` 关键词（推荐但不强制）

---

## 五、真修复识别（CL-5）

### 规则

owner reply 中声称"已修复 / fixed / 已改 / 已处理 / 已完成"，**必须**比对该 line 在新 PS 中的代码是否真实变更。

### 实施

`gerrit_client.py::build_prior_review_context` 增强，对每条 self 历史 inline comment 输出：

```json
{
  "comment_id": "...",
  "path": "AndroidUpdater.java",
  "line": 168,
  "code_at_orig_ps": "return OTA_SUCCESS;",
  "code_at_curr_ps": "return OTA_SUCCESS;",
  "actually_changed": false,
  "owner_reply": "已修复",
  "claims_fixed": true,
  "fix_mismatch": true   // ❌ 声称修复但代码未变
}
```

### LLM 处置

`fix_mismatch == true` 时：
- 维持原 P0/P1
- 在 cover 中显式标注：「⚠️ owner 声称已修复但代码未实质变更（行 X：`<code>`），不接受豁免」
- inline 评论中引用 owner reply 原文 + 实际代码对比

---

## 六、契约硬扫层（CL-6，上下文感知）

### 规则

`gerrit_audit.py` 新增 `contract_change_scan`：

1. **current.txt 数值变更扫**：检测 `field public static final int \w+ = \d+` 数值变化
2. **proto field tag 扫**：检测 `.proto` diff 中 enum / field tag number 变化
3. **Bundle key 字符串扫**：检测 `KEY_\w+\s*=\s*".+?"` 字符串字面值变化

### 输出（必须结合 CL-3 上下文）

```json
"contract_change_candidates": [
  {
    "type": "intdef_value",      // intdef_value / proto_tag / bundle_key
    "symbol": "UPDATE_STATUS.SUCCESS",
    "old_value": 1,
    "new_value": 0,
    "file": "manager/api/current.txt",
    "line": 698,
    "context_aware_severity": "P2"  // 默认 P2，待 CL-3 上下文判定后升级
  }
]
```

### LLM 决策（关键）

LLM 看到 `contract_change_candidates` 后，**必须**结合 `contract_consistency.assessment` 综合判定（详见 §三定级矩阵）：

| assessment | 是否发评论 | 等级 |
|---|---|---|
| `single_owner_closed_loop_need_value_check` + 两端值一致（LLM 语义比对后确认）| 不发 | — |
| `single_owner_closed_loop_need_value_check` + 两端值不一致 | 发 | **P0** |
| `context_aware_ok_multi_owner` | 最多 P2 提醒（非必发）| P2 |
| `single_side_only_single_owner_p2` / `single_side_multi_owner_p2` | 发 | **P2 提醒** |
| `no_jira_cannot_verify` / `scan_failed_use_p2` / `unknown_use_p2` | 发 | **P2 提醒** |

**绝对禁止**：仅凭契约变更本身就判 P0，不看 contract_consistency 上下文。

---

## 七、与既有维度的关系

本文件规则**正交叠加**于既有 7+1 维度，不替代：

| 既有维度 | 与 CL-x 的关系 |
|---|---|
| 04 错误处理 + 边界（P0/P1） | CL-3 / CL-6 触发的契约破坏走 04 维度的"契约破坏 P0"，但严格按 CL-3 上下文判定 |
| 14 平台化设计共识（P2/P3） | CL-3 的"单端 P2 提醒"可挂在 PLAT-3 标签下输出 |
| Reply-Aware（v2.5.0 规则 A/B/C/D/E）| CL-1 强化 reply 分类；reply_classification 是 reply_disposition 的子字段 |

### 不评 / 豁免

以下场景**不**触发 CL-x 规则：
1. CR 仅修改测试代码 / 文档 / 示例
2. CR 修改 `current.txt` 但仅新增字段（非数值变更 / 非删除）
3. proto 文件**新增**消息 / 字段（tag 从未用过的值起编）
4. CR 是 cherry-pick follower（评审复用主干结论）

---

## 八、版本演进

| 版本 | 日期 | 主要变更 |
|---|---|---|
| 1.0 | 2026-05-15 | 首版发布；CL-1 ~ CL-6 六条闭环增强规则 |
| 1.1 | 2026-05-15 | v2.6.0 内部修订：LRU cache + sibling 拉取改 CURRENT_FILES-only |

---

## 九、进一步压缩空间（v2.6.0 内部修订，2026-05-15）

### 优化 1：LRU Cache 跨 CR sibling 查询复用

**问题**：同一 Jira 下多个 CR 走 cron / 批量评审时，`contract_consistency_scan` 每个 CR 会独立调一次 `gerrit_get_func`拉 sibling 列表，重复 HTTP。

**优化**：`gerrit_audit.py` 引入 `_SIBLING_CACHE` (进程级) 缓存 + `_sibling_lookup_cached(jira, owner, fn, cr)` 包裹。
- key = `(jira, current_owner)`
- 同一 Jira 同一 owner 多次调用 → 仅打一次 Gerrit。
- 允许手动 `_sibling_cache_clear()` 重置。

### 优化 2：sibling CR 拉取改 `o=CURRENT_FILES`-only

**问题**：原拉取参数 `o=CURRENT_REVISION&o=CURRENT_FILES&o=DETAILED_ACCOUNTS` 返回的 JSON 含大量冗余（account labels / detail meta）。实际只需 file 路径。

**优化**：改为 `o=CURRENT_FILES`。返回体仅含 `current_revision` SHA 与 files map，owner 从顶层 `s.owner` 读（含在默认 fields 中，无需额外 `o`）。

**收益：~30% 流量（依赖 sibling 数量）**。

### 优化 3（独立规则）：BUILD-FAIL-1 预编译失败红线

详见 [`16-build-fail-redline.md`](./16-build-fail-redline.md)。

- `prepare_context` 中调用 `detect_build_failure(detail)` 填充 `ctx.build_failure`
- `compute_review_decision(prior, build_failure=...)` 多一个优先级 0.5 的 mode `skip_build_failed`
- CLI: `--build-fail-fast` 直接 -2 快通道，不走 LLM
