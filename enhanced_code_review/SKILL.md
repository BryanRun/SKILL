---
name: enhanced_code_review
description: "增强版代码评审（v2.0.0）。完整继承 gerrit-review 全部能力（6 维 + P0-P3 + 脚本链 + Google/Java/C++ 规范与车联明文）并新增本地模块评审：无需 CR 号即可对仓库子目录做与 prepare 同构的评审上下文。触发：review <模块路径>、enhanced_code_review review <模块路径>、以及原 gerrit-review 全部触发语（review CR / review 姓名 / gerrit inbox 等）。"
version: "2.0.0"
---

# enhanced_code_review — 增强版代码评审（v2.0.0）

> **本技能 = gerrit-review 能力全集 + 本地模块评审增量**。质量门禁、六维清单、方法论、评分与评论格式与 `gerrit-review` **完全一致**，不得删减。详见 `references/09-local-module-review.md`。

## 版本

- **2.0.0**：首次以 `enhanced_code_review` 名称发布；与 `gerrit-review` 同源 `references/` 与 `scripts/`（含 `gerrit_*.py`），新增 `local_module_prepare.py` / `local_audit.py`。

## 触发（本地增强）

- `review <模块路径>` — 例：`review frameworks/cm/videoplayer`、`review midware/startupanimation`
- `enhanced_code_review review <模块路径>` — 显式调用本技能

**本地模块工作流**：在仓库根执行：

```bash
python3 scripts/local_module_prepare.py <模块相对路径> [--base origin/main] -o /tmp/local_ctx.json
```

Agent 读取 JSON 后，按 `references/08-llm-review-prompt.md` 产出评审结论（六维 + 三问 + YAGNI）。

## 触发（原 Gerrit 全能力，保留）

- `review CR <编号>` — 单 CR 全自动评审
- `review <姓名>` — 按 owner 列 open CR 清单
- `gerrit inbox` / `今天待审` — 待审概览

---

## 完整 6 大维度（必全扫）

| # | 维度 | 权威依据 | 参考 |
|---|---|---|---|
| 1 | **SOLID 原则** | Bob Martin APPP (2002) + Effective Java | `references/01-solid-principles.md` |
| 2 | **安全性** | OWASP Top 10 + CWE/SANS Top 25 + Android CDD + ISO 21434 | `references/02-security.md` |
| 3 | **性能** | Effective Java Item 67 + Android Performance Patterns | `references/03-performance.md` |
| 4 | **错误处理 + 边界** | Effective Java Item 70-77 + Clean Code Ch.7 | `references/04-error-handling-boundaries.md` |
| 5 | **代码质量 + 风格** | **Google Java/C++ Style Guide** | `references/05-code-quality-style.md` |
| 6 | **车载中间件专项** | Android Automotive + QNX + AUTOSAR + ISO 26262 | `references/06-automotive-middleware.md` |

**每次评审必扫 6 个维度**，即使某维度无发现也在 cover 里声明"已扫，无发现"。

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

System + user prompt 模板。按该模板执行评审，输出 review JSON。

---

## 项目明文规范（车联 AutoLink）

（与 gerrit-review 一致，此处不重复删减；以 `gerrit-review` 原版 `SKILL.md` 与下列章节为真源。）

### 硬性

- **Java 缩进必须 4 空格，禁止 tab** — P1
- **C++ 缩进必须 4 空格，禁止 tab** — P1
- **C++ 风格**：遵循项目原有代码整体风格 — P1
- **commit message 必带 Jira 号**（CHYT1V/BAIC/KP31/CL/T1V/D01）— 缺失 P0 → -1（**仅 Gerrit 路径**；本地模块评审可注明 N/A）

### YAGNI 原则

- **作为 P3 建议，不强制**

### 冲突处理

1. 项目明文规定 → 按项目
2. 项目未规定 → 可参考 Google Style，**仅作 P3 建议**
3. 项目习惯与 Google Style 冲突 → 按项目

---

## 打分规则

（与 gerrit-review 完全一致）

| 级别 | 特征 | Gerrit 分 |
|---|---|---|
| P0 Critical | 真崩溃 / 数据丢失 / 安全 / 契约破坏 / 缺 Jira | **-1** |
| P1 Important | 真 risk / 架构混淆 / 线程安全 / IPC 挂死 | **0** |
| P2 Medium | code smell / 维护性 / Google Style 违反 | **+1** |
| P3 Low | 可选改进 / 风格建议 | **+1** |
| 无问题 | — | **+1** |

---

## 自动化工作流

### A) Gerrit（7 步，与原版相同）

```
触发 "review CR <n>"
  ↓
Step 1 · Preflight（gerrit_show / gerrit_audit / consistency_scan）
  ↓
Step 2～7 · 六维 + LLM + 三问 + YAGNI + 分数决策
  ↓
gerrit_post.py 贴回（或简报）
```

### B) 本地模块（无 CR）

```
触发 "review <模块路径>"
  ↓
local_module_prepare.py → JSON 上下文
  ↓
Step 2～7 · 六维 + LLM + 三问 + YAGNI（不贴 Gerrit）
```

---

## 评论 5 要素（每条必含）

（与 gerrit-review 相同）

```
[P<级别>] <file>:<line> — <一句话标题>

**依据**：<权威来源>
**现象**：<具体代码 + 场景>
**原理**：<为什么这是问题>
**建议**：<具体修法>
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
| `scripts/gerrit_review.py` | Gerrit 主入口 prepare/post |
| `scripts/gerrit_post.py` | 贴回 Gerrit |
| **`scripts/local_module_prepare.py`** | **本地模块 prepare JSON** |
| **`scripts/local_audit.py`** | **本地行级规则（与 audit 同源）** |

---

## 参考文件

| 文件 | 作用 |
|---|---|
| `references/01-solid-principles.md` ~ `08-llm-review-prompt.md` | 与 gerrit-review 相同 |
| **`references/09-local-module-review.md`** | **本地模块评审** |

---

## 使用示例

### Gerrit（不变）

```bash
export GERRIT_BASE="https://gerrit.auto-link.com.cn"
export GERRIT_USER="..."
export GERRIT_HTTP_PASSWORD="..."

python3 scripts/gerrit_review.py 993636 --prepare -o /tmp/ctx.json
python3 scripts/gerrit_review.py 993636 --post /tmp/review.json
```

### 本地模块

```bash
cd /path/to/repo
python3 scripts/local_module_prepare.py frameworks/cm/videoplayer -o /tmp/local_ctx.json
```

---

## 与 gerrit-review 的关系

- **gerrit-review**：仅 Gerrit 自动化；**本技能**在其基础上增加 **本地模块** 能力，**不降低**任一维度或规则质量。
- 分发包：`enhanced-code-review-v2.0.0.zip`（本技能）；`gerrit-review-v2.0.0.zip`（原版技能单独打包归档，供只需 Gerrit 的场景）。
