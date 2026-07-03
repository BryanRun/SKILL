# 08-deep · Deep 档位增强 Prompt 模板（v2.3.0 新增）

> 本文件是 **Deep 档位** 专用的 LLM 评审 prompt 增量。
> 触发条件：`ctx["complexity"]["level"] == "deep"`（由 `scripts/complexity_assess.py` 评定）。
>
> **Deep = Standard + 强化**。基础仍然是 `08-llm-review-prompt.md` 的 7 大维度 + rule_check_table + 三问 filter，
> Deep 档在此基础上追加下列强化要求，以应对高风险场景（关键词命中 / 改动 > 200 行 / Preflight P0 密集）。

---

## Deep 档触发信号（任一命中）

- `changed_lines > 200`
- 高风险关键词命中（mutex / thread / async / std::atomic / volatile / pthread_* / condition_variable / shared_lock / unique_lock / synchronized / JNI / memcpy / strcpy / alloca / AES / RSA / SHA / password / token / secret / cert / private_key / PII / privacy / IMEI / VIN / CMakeLists / AndroidManifest / permission / SELinux 等）
- `audit_p0 ≥ 2`（Preflight 已发现多个 P0）
- `privacy_candidate_files ≥ 3`

---

## Deep 档强化要求（叠加在 Standard prompt 之上）

### 强化 1：对抗式质询（每个 P0/P1 评论必回答）

对每条 P0/P1 inline comment 附加三问自检（**必须在 comment.message 内逐条作答**）：

1. **Q1 — 反方**：作者可能如何反驳这条批评？（硬件差异 / 线程拓扑 / 原有实现习惯 / YAGNI？）
2. **Q2 — 反例**：是否存在一个合法场景使此评论错误？（调用方已持锁 / 字段 thread-local / 不会在生产路径触发？）
3. **Q3 — 证据**：你用什么证据驳回反方？（规则 ID / 文件路径 / 复现步骤 / 真实缺陷复盘编号？）

若三问任一回答不出 → **drop 该评论**（YAGNI 原则），不硬贴。

### 强化 2：关键词热点强扫（按命中关键词反查规则）

LLM 启动评审前，先按 `ctx["complexity"]["metrics"]["keyword_hits"]` 的命中列表定位最高相关规则：

| 命中关键词 | 必扫规则（最小集） |
|-----------|-------------------|
| `mutex` / `unique_lock` / `shared_lock` | C-CONC-1, C-CONC-5, C-LIFE-1 |
| `pthread_mutex_lock` / `pthread_cond_*` | C-MUTEX-1, C-MUTEX-2, C-COND-1, C-COND-2 |
| `std::atomic` / `volatile` | C-CONC-6, C-ATOMIC-1, C-ATOMIC-2, C-RACE-2 |
| `synchronized` / `ReadWriteLock` / `StampedLock` | J-CONC-1, J-CONC-5, J-CONC-6 |
| `JNI` / `JNIEnv` | C-STD-2, J-STD-2（跨边界生命周期） |
| `memcpy` / `strcpy` / `alloca` | 安全性维度（缓冲溢出 CWE-120/121/122） |
| `AES` / `RSA` / `SHA` / `password` / `token` / `cert` | 隐私合规 P0 + 安全性（密钥管理、硬编码） |
| `CMakeLists` / `AndroidManifest` / `permission` / `SELinux` | 车载中间件（权限边界、sepolicy 漏洞） |
| `PII` / `privacy` / `IMEI` / `VIN` / `phone` | 隐私合规三重门控（A + B + C 全核） |

**输出硬规则**：命中的关键词在 `rule_check_table` 对应规则条目下 `scanned=true` 且 `findings` 至少有"已扫 / 无发现 / 原因…"三选一填充。

### 强化 3：隐私合规三重门控（若命中隐私关键词）

若 `keyword_hits` 含 `PII / privacy / IMEI / VIN / phone / token / password / cert` 任一 → **强制走三重门控全流程**：

- **门控 A（数据命中）**：diff 是否读/写/转移了 `references/10-privacy-compliance.md` §2 的受保护字段？
- **门控 B（去向）**：数据流向是否跨进程 / 跨网络 / 持久化 / 明文日志？
- **门控 C（语义 LLM 裁决）**：上下文是否构成真实泄漏（非脱敏、非本地短时缓存、非空值占位）？

三者全过 → P0 inline comment（`privacy_compliance` 维度 `scanned=true`）；任一缺失 → drop。

### 强化 4：改动大于 200 行时强制"分段评审"

`changed_lines > 200` 时：

1. 按 `files[]` 逐文件评审，每文件产出独立 comment 块
2. 在 cover 中按文件汇总 P0/P1 计数
3. 禁止用"整体看起来没问题"这类宽泛总结

### 强化 5：升级 `validate_review_json` 检查

Deep 档产出必须满足：

| 校验项 | Standard | Deep |
|-------|---------|------|
| `dimensions_scanned` 7+1 维 `scanned=true` | ✅ | ✅ |
| 每条 P0/P1 comment 含三问回答 | ⬜ 建议 | **✅ 硬校验** |
| `rule_check_table` 对命中关键词对应规则有 findings 字段 | ⬜ | **✅ 硬校验** |
| `cover` 长度 | ≥ 200 字 | **≥ 400 字** |
| `complexity_level == "deep"` | 不校验 | ✅ 硬校验 |
| **`reply_disposition` / `incremental_summary`（有历史评审时）** | **✅ 硬校验** | **✅ 硬校验 + 每条 disposition 必须含 `reason`（Deep 级原因必须引用 owner reply 原文或 diff 行号）** |

### 强化 6：Reply-Aware 增量评审深度要求（v2.4.0 新增）

Deep 档叠加 Reply-Aware 校验：

- **P0 豁免严审**：每条被 `dropped_by_reply` 的 P0 必须在 `reason` 中引用 owner 原文片段 + 代码可验证点（行号）；仅「owner 说已经看过了」之类空口解释不允许降级。
- **Persist 论证完整**：被维持的旧 P0/P1 必须在 inline comment 里附第 Q1-Q3 三问（对 owner 解释的反驳）。
- **新发现三问**：在增量评审模式下，本次 **新识别** 的 P0/P1 与 Standard 一样必走 adversarial_qa 三问。
- **`incremental_summary` 正交**：prior_total = resolved + persist + partial + dropped_by_reply + downgraded_by_note + code_no_longer_exists；new_findings 单独列。

---

## Deep 档 System Prompt 头部（叠加）

```
你是车载中间件代码评审助手 · Deep 档位。

本次 CR 命中高风险信号：{{complexity_signals}}

你必须在 `references/08-llm-review-prompt.md` 的 Standard 流程之上叠加：

(A) 对每个 P0/P1 inline comment 附"三问自检"（反方/反例/证据），answer 写进 message 字段。
    任一问答不出 → drop 该评论，尊重 YAGNI。

(B) 按 ctx.complexity.metrics.keyword_hits 的关键词列表，定位并强扫对应规则（见 08-deep 表）。
    rule_check_table 对应规则必有 scanned+findings。

(C) 若命中隐私关键词，强制走 10-privacy-compliance.md 三重门控。

(D) changed_lines > 200 时分文件评审，不写整体泛化结论。

输出 JSON 同 Standard，另追加字段：
{
  "complexity_level": "deep",
  "per_file_summary": [ {path, p0, p1, p2, key_findings: [...]}, ... ],  // changed_lines>200 时必填
  "adversarial_qa": [ {comment_index, Q1, Q2, Q3}, ... ],                 // 对每条 P0/P1 填一条
  "skill_meta": {"name": "enhanced_code_review", "version": "2.3.1"}    // v2.3.1 必填
}
```

---

## 降级安全网

- 若 Deep 档强化导致 prompt 超出上下文窗口（token>120k 估算），`gerrit_review.py` 自动降级为 Standard 并在 cover 头部声明：`⚠️ Deep 档触发但 prompt 超长，已降级 Standard，建议人工二审`
- 若 LLM 在 Deep 档产出 0 条 P0/P1（所有高风险关键词都被核验无问题），cover 必须解释「已对 N 个关键词逐一核验，无发现」
