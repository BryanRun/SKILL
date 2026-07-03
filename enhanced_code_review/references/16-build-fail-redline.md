# 16. BUILD-FAIL-1 · 预编译失败质量红线（P0）

> 版本：v2.6.0 内部修订（2026-05-15）
> 适用：所有走 her gerrit-review 流水线的 CR
> 优先级：**P0 质量红线**，仅次于手动 `--force`

---

## 一、规则

**规则编号：BUILD-FAIL-1**
**等级：P0（质量红线）**
**触发：CR 当前 patchset 任一构建/预编译 label 被打 -1 / -2**

具体识别的 Gerrit label：

| Label | 含义 | 触发 |
|---|---|---|
| `Verified` | 自测 / 构建验证 | `Verified-1` 或 `all[].value < 0` |
| `Prebuild-Check` | 预编译检查（scm_verify Jenkins） | `Prebuild-Check-1` 或 `all[].value < 0` |

> 不识别 `CommitMsg-Check` / `StaticCode-Check`：这两个属于元数据/静态分析问题，由其他维度兜底。

---

## 二、处置：直接 -2 跳过 LLM 评审

**触发后立即**：

1. **跳过任何 LLM 评审流程**（不浪费 token，不发起 7+1 维度扫描）
2. POST cover：
   - `Code-Review` 投票 **-2**
   - cover 文案使用 `BUILD_FAIL_COVER_TEMPLATE`（专业措辞）：

```text
### 评审结论：-2（质量红线 · 预编译失败）

当前 patchset 已被构建系统标记为 {evidence}（预编译失败）。按 gerrit-review v2.6.0 质量红线 BUILD-FAIL-1，预编译未通过的 CR 不进入代码评审流程，请 owner 自查代码并完成本地预编译验证（make / gradle / m clean install 等）后重新提交 patch。

> 本次未触发 7+1 维度 LLM 评审（节省 token）；预编译通过后再提交即可重新走完整评审。
```

3. 不写 inline comments（构建失败定位由 Jenkins console 给出，AI 无需重复）

---

## 三、决策矩阵中的位置

`compute_review_decision(prior, force, build_failure)` 优先级：

```
0. force=True                                → proceed (手动覆盖)
0.5. build_failure                           → skip_build_failed (-2 fast-track) ← v2.6.0 新增
1. owner has reply                           → incremental
2. self prior review + owner reply           → incremental
3. other -1 (non-substantive)                → proceed
4. other -1 (substantive) + no owner reply   → skip
5. self prior + no owner reply + no code chg → skip
6. default                                   → proceed
```

新增 mode：`skip_build_failed`，对应字段 `should_review=False, is_incremental=False`。

---

## 四、使用方式

### CLI 快通道
```bash
python3 gerrit_review.py <CR> --build-fail-fast
# 或加 --dry 仅预览
```

### prepare_context 自动注入
正常 `prepare_context` 调用时，`ctx.build_failure` 字段会被填充；`ctx.review_decision.mode == 'skip_build_failed'` 即可直接走 fast-track。

### 在 cron / 自动评审中
推荐流程：
1. `prepare_context` 后判断 `ctx.review_decision.mode`
2. 如果是 `skip_build_failed` → 直接调用 `post_build_failed()`，**不调用 LLM**
3. 否则继续 LLM 评审流程

---

## 五、与其他维度的关系

| 维度 | 关系 |
|---|---|
| Reply-Aware (v2.5.0) | BUILD-FAIL-1 优先级高于 reply 处置；预编译失败时不读 reply |
| CL-1 ~ CL-6 闭环增强 | BUILD-FAIL-1 优先于所有 CL 规则；预编译失败时 unresolved_issues 不强制 |
| force 手动覆盖 | force 优先；如确需评审无法编译的 CR，加 `--force` |

---

## 六、不豁免清单

以下情形**仍然**触发 BUILD-FAIL-1：
- WIP CR 已上 reviewer
- hotfix CR
- cherry-pick follower
- 仅改文档 / 测试代码（如果 CI 仍报构建失败）

**唯一豁免**：手动 `--force` 标记（owner / lead 明确要求评审）。

---

## 七、版本演进

| 版本 | 日期 | 变更 |
|---|---|---|
| 1.0 | 2026-05-15 | 首版发布，作为 v2.6.0 内部修订的第 3 条规则 |
