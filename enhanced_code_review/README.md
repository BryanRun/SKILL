# enhanced_code_review · 增强版代码评审 v2.0.0

本目录为 **enhanced_code_review** 技能包：在 **gerrit-review** 全部能力（六维、脚本链、Gerrit 自动化）基础上增加 **本地模块评审**（无 CR 号）。原版仅 Gerrit 场景可继续使用 `~/.cursor/skills/gerrit-review` 或 `gerrit-review-v2.0.0.zip`。

---

## 能力来源（三套方法论融合，不砍维度）

| 来源 | 贡献 |
|---|---|
| **code-review-expert**（sanyuan-skills） | **6 大完整维度**：SOLID / 安全 / 性能 / 错误处理 / 代码质量 / 车载专项；P0-P3 分级 |
| **superpowers**（obra/superpowers） | **评审方法论**：对抗式 / YAGNI / verify-before-comment / 每条必带依据 |
| **Google Java & C++ Style Guide** | **权威规范**：Java/C++ 统一风格（缩进/命名/imports/braces） |
| **Effective Java / Clean Code / OWASP / CWE / ISO 26262 / AUTOSAR** | 权威文献依据 |
| **gerrit-review 本地** | 车载中间件 L1~L10 专项 / 同文件一致性扫描 / Jira 硬性 / Gerrit REST API |

---

## 6 大评审维度（**每次必全扫**）

1. **SOLID 原则** — SRP / OCP / LSP / ISP / DIP
2. **安全性** — AuthN/AuthZ / 注入 / 并发 / 资源 / IPC / 加密
3. **性能** — 算法 / 主线程阻塞 / 内存 / 缓存 / IO
4. **错误处理 + 边界** — 空 catch / RemoteException / null / 溢出 / off-by-one
5. **代码质量 + Google Style** — 缩进空格 / 命名 / imports / braces / Javadoc
6. **车载中间件专项** — 状态机 / 线程 / IPC / 电源 / 诊断 / OTA / 配置

即使某维度无发现，也在 cover 声明"已扫 X 维度，无发现"。

---

## 核心差异：不砍维度，提高信号/噪声比

过去 v1 版本错误地以"对开发友好"为由砍了 SOLID/命名/风格维度。
**v2 修正**：

| 方向 | v1 错误 | v2 正确 |
|---|---|---|
| 维度覆盖 | 砍掉"应加抽象"类建议 | **全扫 6 维度**，发现真问题就提 |
| 风格 | `e.printStackTrace()` 黑名单扩到所有风格 | 只黑名单项目**明文允许**项；Google Style **全执行** |
| 依据 | 靠 AI 常识 | 每条必引 Google Style / OWASP / Effective Java / Clean Code |
| 过滤 | 过滤掉整类 | **三问 filter + YAGNI** 个案处理 |

---

## 项目规范（车联 AutoLink）

### 硬性
- **Java 缩进 4 空格，禁用 tab**（项目硬规范、2026-04-19 志强明确），P1
- **C++ 缩进 4 空格，禁用 tab**（项目硬规范、2026-04-19 志强明确），P1
- **C++ 风格不强制 Google Style**，**必须遵循项目原有代码风格**，P1
- **commit message 必带 Jira 号**（CHYT1V/BAIC/KP31/CL/T1V/D01）— 缺失 P0 → -1

### YAGNI
- **作为 P3 建议，不强制**（不阻断合入，仅作治理指引）

### Java Google Style 仅作参考
- 项目缩进覆盖为 4 spaces（非 Google 官方的 2 spaces）
- 其他 Google Style 项 仅作参考，项目明文规定优先

### 项目允许（非违规）
- `e.printStackTrace()` — 允许
- commit message 格式错别字 / 代码修改量 — 志强不管
- Log 封装类 / TAG / JavaDoc — 无明文规范时不强制

### 冲突处理
1. 项目明文规定 → 按项目
2. 项目未规定 → Google Style 仅作参考，仅 P3 建议
3. 项目习惯与 Google 不同 → 按项目

---

## 打分 + preflight

| 级别 | 场景 | Gerrit 分 |
|---|---|---|
| P0 Critical | 真崩溃 / 数据丢失 / 安全 / 缺 Jira | **-1** |
| P1 Important | 线程安全 / 架构混淆 / IPC 挂死 | **0** |
| P2 Medium | Google Style 违反 / code smell | **+1** |
| P3 Low | 可选改进 | **+1** |
| 纯净 | — | **+1**（+2 保留给人工） |

### preflight（不抢人工分数）

贴回前检查 self 当前分数：
- self 已 **+2** → 不贴（避免降级） → 只给简报
- self 已 **+1** → 可贴（可能纠正）
- self 未投 → 按决策

---

## 自动化流程（7 步 + LLM）

```
触发 "review CR <n>"
  ├─ Step 1 Preflight: show + audit + consistency
  ├─ Step 2-7 6 大维度扫描
  ├─ LLM 按 08-llm-review-prompt.md 产出 review JSON
  │   ├─ 三问 filter（每条必过）
  │   ├─ YAGNI（抽象建议必 grep）
  │   ├─ 权威依据标注（Google Style §N / OWASP / ...）
  │   └─ 5 要素完整（问题+依据+原理+建议+Before/After）
  ├─ preflight check self 分数
  ├─ gerrit_post 贴回（或跳过）
  └─ 飞书简报给志强
```

---

## 环境

```bash
export GERRIT_BASE="https://gerrit.auto-link.com.cn"
export GERRIT_USER="hualei"
export GERRIT_HTTP_PASSWORD="..."
```

## 触发方式

志强只要说：
- `review CR 993636` → 全自动评审 + 贴回（preflight 不抢分数）
- `review 林明的代码` → 列 open CR 清单
- `gerrit inbox` / `今天待审` → 待审概览

---

## 手动诊断命令

```bash
cd /data/.openclaw/workspace/skills/gerrit-review/scripts

python3 gerrit_inbox.py
python3 gerrit_inbox.py --unvoted
python3 gerrit_inbox.py --owner linming

python3 gerrit_show.py 993636
python3 gerrit_audit.py 993636
python3 consistency_scan.py 993636

# 全自动化主入口
python3 gerrit_review.py 993636 --prepare -o /tmp/ctx.json
python3 gerrit_review.py 993636 --post /tmp/review.json [--dry] [--score N]
```

---

## 脚本 + 参考清单

```
gerrit-review/
├── SKILL.md                                         (5.9K)
├── README.md                                        (本文件)
├── scripts/
│   ├── gerrit_client.py                 共享 HTTP
│   ├── gerrit_inbox.py                  待审清单
│   ├── gerrit_show.py                   单 CR detail
│   ├── gerrit_audit.py                  机械扫描
│   ├── consistency_scan.py              一致性扫描（core）
│   ├── gerrit_review.py                 主入口
│   └── gerrit_post.py                   贴回 Gerrit
└── references/
    ├── 01-solid-principles.md          SOLID + 架构
    ├── 02-security.md                  安全 + 可靠性
    ├── 03-performance.md               性能
    ├── 04-error-handling-boundaries.md 错误 + 边界
    ├── 05-code-quality-style.md        Google Style Guide
    ├── 06-automotive-middleware.md     车载 L1~L10
    ├── 07-review-methodology.md        对抗式 + YAGNI
    └── 08-llm-review-prompt.md         LLM prompt 模板
```

---

## 历史实战

### 993636 · 林明 · CHYT1V-855 Power 2/2
- ✅ 真 P0: DisplayController NPE（同类已防）
- ✅ 真 P1: PowerImpl 广播 try-catch 外置
- ✅ 真 P1: DisplayController SRP 违反
- ❌ 伪阳性（已纠正）: `e.printStackTrace()` / commit msg
- 结果: Code-Review = -1

### 995945 · ouqijiang · BAIC-61277 Power
- ✅ 修复主路径正确（MSG 通道改对）
- ✅ 顺带重构合理（5 分支合并 / SRP / dead code 清理）
- 结果: skill 判 +1，志强已投 +2 在先，preflight 保护不覆盖
