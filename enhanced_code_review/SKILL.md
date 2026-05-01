---
name: enhanced_code_review
description: "增强版代码评审（v2.1.2）。完整继承 gerrit-review 全部能力（7 维 + P0-P3 + 脚本链 + Google/Java/C++ 规范与车联明文）并新增本地模块评审：无需 CR 号即可对仓库子目录做与 prepare 同构的评审上下文。v2.1.2 修复 commit message 中【开发自测视频】链接里的时间戳/文件 ID 被误判为「缺前缀的 Jira 号」（P1），并对全部脚本回退到 typing 风格类型注解，**最低支持 Python 3.6.9**（可在 3.6 / 3.7 / 3.8 / 3.9 / 3.10+ 直接运行）。隐私合规维度（P0，高精确率三重门控）与 v2.1.1 行为不变。Gerrit 须自行配置 GERRIT_USER / GERRIT_HTTP_PASSWORD。触发：review <模块路径>、enhanced_code_review review <模块路径>、以及原 gerrit-review 全部触发语（review CR / review 姓名 / gerrit inbox 等）。"
version: "2.1.2"
---

# enhanced_code_review — 增强版代码评审（v2.1.2）

> **本技能 = gerrit-review 能力全集 + 本地模块评审增量 + 隐私合规维度**。质量门禁、七维清单、方法论、评分与评论格式与 `gerrit-review` **完全一致**，不得删减。详见 `references/09-local-module-review.md` 与 `references/10-privacy-compliance.md`。

## 运行时要求（v2.1.2 起明示）

- **最低支持 Python 3.6.9**；已在 Python 3.6.15（docker `python:3.6.15-slim`）与 Python 3.10.12 上联合验证：`py_compile` 全脚本通过，`gerrit_audit` / `local_audit` / `local_module_prepare` / `privacy_compliance_scan` 均可 import，JIRA 误报回归用例 4/4 PASS。
- 不再使用 `from __future__ import annotations`（PEP 563，3.7+）、`dict[..]` / `list[..]` / `X | None`（PEP 585/604，3.9+ / 3.10+）等运行时新语法，**也不依赖** 标准库 `dataclasses`（3.7+）。所有类型注解统一使用 `typing` 模块（`typing` 3.5+ 即支持）。
- `subprocess.run` 改用 `stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True` 经典写法（不使用 `capture_output=True` / `text=True`，3.7+ 才有）。
- 第三方依赖 `requests` / `urllib3` 由使用方按服务器实际版本选择安装（与 Python 兼容性无关）。

## 版本

- **2.1.2**：① **commit message 中【开发自测视频】链接段豁免**：`gerrit_client.extract_jira_violations` 不再把链接段（含【开发自测视频】/【关联视频】/【关联链接】/【关联文档】/【下载链接】/【录屏】/【录像】/【录制视频】/【验收视频】/【评审视频】）整段、以及任意行内 URL（http(s):// / ftp:// / file:// / www.）中的 5+ 位数字识别为「缺前缀的 Jira 号」，根因是这些段常带 10~14 位时间戳 / 飞书 file token 数字尾段；占位号检测、正文 bare_number 检测保持原有强度。② **回退至 Python 3.6.9 兼容**：删除所有 `from __future__ import annotations`、PEP 585/604 下标注解与 `@dataclass`，改用 `typing` 模块 + 普通类；`subprocess.run` 改回 `stdout=PIPE` 经典写法。功能 0 改变。
- **2.1.1**：本地模块评审**适配子模块 / 多仓库**结构 — `local_module_prepare.py` 新增 `--repo auto` 自动从模块路径回溯定位最近 `.git`；区分 `dir / file / symlink` 三种 `.git` 形态；对 git submodule 回溯出 superproject 工作树；对 Android `repo` 工具管理探测 `.repo/manifests` 根；子模块未初始化时输出复制即用的 `git -C <super> submodule update --init -- <path>`。**不再要求**「在仓库根执行」。
- **2.1.0**：新增**隐私合规**评审维度（P0 级；`references/10-privacy-compliance.md` + `scripts/privacy_compliance_scan.py`）。基于《产品功能 信息安全要求-v1.2-20260210》+《附录-个人信息定义》，只纳入隐私合规类条目；触发采用**三重门控**（数据 A + 去向 B + 语义 C），宁可漏报不可误报。
- **2.0.1**：移除 `gerrit_client.py` 中任何默认账号与 HTTP 密码；清理技能与 references 中的个人化表述；Gerrit 凭据必须由使用方通过环境变量配置。
- **2.0.0**：首次以 `enhanced_code_review` 名称发布；与 `gerrit-review` 同源 `references/` 与 `scripts/`（含 `gerrit_*.py`），新增 `local_module_prepare.py` / `local_audit.py`。

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

Agent 读取 JSON 后，按 `references/08-llm-review-prompt.md` 产出评审结论（七维 + 三问 + YAGNI + 隐私合规门控 C）。
若输出 `topology.git_kind == "none"` 且带 `uninitialized_submodule_hint.init_hint`，**复读** init_hint 让用户初始化后重跑，**不要**自动执行 `git submodule update`。

## 触发（原 Gerrit 全能力，保留）

- `review CR <编号>` — 单 CR 全自动评审
- `review <姓名>` — 按 owner 列 open CR 清单
- `gerrit inbox` / `今天待审` — 待审概览

---

## 完整 7 大维度（必全扫）

| # | 维度 | 权威依据 | 参考 |
|---|---|---|---|
| 1 | **SOLID 原则** | Bob Martin APPP (2002) + Effective Java | `references/01-solid-principles.md` |
| 2 | **安全性** | OWASP Top 10 + CWE/SANS Top 25 + Android CDD + ISO 21434 | `references/02-security.md` |
| 3 | **性能** | Effective Java Item 67 + Android Performance Patterns | `references/03-performance.md` |
| 4 | **错误处理 + 边界** | Effective Java Item 70-77 + Clean Code Ch.7 | `references/04-error-handling-boundaries.md` |
| 5 | **代码质量 + 风格** | **Google Java/C++ Style Guide** | `references/05-code-quality-style.md` |
| 6 | **车载中间件专项** | Android Automotive + QNX + AUTOSAR + ISO 26262 | `references/06-automotive-middleware.md` |
| 7 | **隐私合规（P0）** | 《产品功能 信息安全要求-v1.2-20260210》+《附录-个人信息定义》 | `references/10-privacy-compliance.md` |

**每次评审必扫 7 个维度**，即使某维度无发现也在 cover 里声明"已扫，无发现"。

> **隐私合规特殊触发约束**（团队 2026-04-21 明确）：
> - 隐私合规问题按 **P0** 计分 → 对分数影响极大。
> - **三重门控**（数据 A + 去向 B + 语义 C）全部命中才允许作为 P0 inline 评论。
> - 触发条件必须"确认无误"，**宁可漏报，不可误报**；不能随意触发。
> - 机械扫描只产出候选（`privacy_candidates`），LLM 在 Step 8 做语义 C 确认后再贴。

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
- **commit message 必带合规 Jira 号**（前缀：CHYT1V / BAIC / KP31 / FL1 / FL2 / FL3 / T1V / D01 / CHYT12A / CHYMIFA）— **缺失** P0 → -1；**占位号**（如 CHYT1V-000 / CHYT1V-0001，数字部分全 0 或 0 开头）P0 → -1；**纯数字**（如 123456，无项目前缀）P0 → -1（**仅 Gerrit 路径**；本地模块评审可注明 N/A）

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
| P0 Critical | 真崩溃 / 数据丢失 / 安全 / **隐私合规三重门控命中** / 契约破坏 / Jira 缺失或不合规（占位号 / 纯数字） | **-1** |
| P1 Important | 真 risk / 架构混淆 / 线程安全 / IPC 挂死 | **0** |
| P2 Medium | code smell / 维护性 / Google Style 违反 | **+1** |
| P3 Low | 可选改进 / 风格建议 | **+1** |
| 无问题 | — | **+1** |

---

## 自动化工作流

### A) Gerrit（8 步）

```
触发 "review CR <n>"
  ↓
Step 1 · Preflight（gerrit_show / gerrit_audit / consistency_scan / privacy_compliance_scan）
  ↓
Step 2～7 · 六维 + LLM + 三问 + YAGNI + 分数决策
  ↓
Step 8 · 隐私合规门控 C 语义确认（LLM）
  ↓
gerrit_post.py 贴回（或简报）
```

### B) 本地模块（无 CR）

```
触发 "review <模块路径>"
  ↓
local_module_prepare.py → JSON 上下文（含 privacy_candidates）
  ↓
Step 2～8 · 七维 + LLM + 三问 + YAGNI + 隐私合规门控 C（不贴 Gerrit）
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
| **`scripts/privacy_compliance_scan.py`** | **隐私合规候选扫描（门控 A + B 共现；P0 走三重门控）** |

---

## 参考文件

| 文件 | 作用 |
|---|---|
| `references/01-solid-principles.md` ~ `08-llm-review-prompt.md` | 与 gerrit-review 相同 |
| **`references/09-local-module-review.md`** | **本地模块评审** |
| **`references/10-privacy-compliance.md`** | **隐私合规（P0，三重门控；只采用《v1.2-20260210》隐私合规类条目 + 附录-个人信息定义）** |

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
# 推荐：在任意 cwd 直接给绝对路径 + --repo auto
python3 scripts/local_module_prepare.py \
    /home/y/t1v_8775/qnx/vendor/autolink/frameworks/cm/videoplayer \
    --repo auto -o /tmp/local_ctx.json

# 兼容旧用法：在 git 工作树根执行
cd /path/to/repo
python3 scripts/local_module_prepare.py frameworks/cm/videoplayer -o /tmp/local_ctx.json
```

---

## 与 gerrit-review 的关系

- **gerrit-review**：仅 Gerrit 自动化；**本技能**在其基础上增加 **本地模块** 能力，**不降低**任一维度或规则质量。v2.1.0 起两者**同步**纳入隐私合规维度；v2.1.1 仅增强本地模块路径，gerrit 路径行为不变；v2.1.2 仅修复 JIRA 误报点 + 回退 Python 3.6.9 兼容，规则集与维度不变。
- 分发包：`enhanced-code-review-v2.1.2.zip`（本技能）；`gerrit-review-v2.1.0.zip`（仅 Gerrit 场景，与 `gerrit-review/` 目录对应，无变更）。
