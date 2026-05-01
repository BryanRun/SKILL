# enhanced_code_review · 增强版代码评审 v2.1.2

本目录为 **enhanced_code_review** 技能包：在 **gerrit-review** 全部能力（七维、脚本链、Gerrit 自动化）基础上增加 **本地模块评审**（无 CR 号）。原版仅 Gerrit 场景可继续使用 `~/.cursor/skills/gerrit-review` 或 `gerrit-review-v2.1.0.zip`。

## 运行时要求

- **最低支持 Python 3.6.9**（v2.1.2 起明示，已在 docker `python:3.6.15-slim` 与本机 Python 3.10.12 联合验证）。第三方依赖 `requests` / `urllib3` 由使用方自行安装。

## v2.1.2 新增

- **commit message 中【开发自测视频】链接段豁免**：`gerrit_client.extract_jira_violations` 不再把【开发自测视频】/【关联视频】/【关联链接】/【关联文档】/【下载链接】/【录屏】/【录像】/【录制视频】/【验收视频】/【评审视频】整段、以及任意行内 URL（http(s):// / ftp:// / file:// / www.）中的 5+ 位数字识别为「缺前缀的 Jira 号」（P1 回归）；占位号检测、正文 `bare_number` 检测保持原有强度。
- **回退至 Python 3.6.9 兼容**：删除所有 `from __future__ import annotations`、PEP 585/604 下标注解与 `@dataclass`，改用 `typing` 模块 + 普通类；`subprocess.run` 改回 `stdout=PIPE, stderr=PIPE, universal_newlines=True` 经典写法。功能 0 改变。

## v2.1.1 新增

- **本地模块评审适配车载多仓库 / git submodule / Android `repo` 工具**：`local_module_prepare.py` 新增 `--repo auto`，自动从模块路径回溯定位最近的 `.git`；区分 `dir / file / symlink` 三种 `.git` 形态；对 git submodule 回溯 superproject；对 `repo` 工具探测 `.repo/manifests` 根；子模块未初始化时输出复制即用的 `git -C <super> submodule update --init -- <path>`，**只描述、不自动执行**。
- **不再要求**「在仓库根执行」；旧用法（`cd <repo> && python3 ... <相对路径>` 或 `--repo <显式路径>`）保持兼容，新版仅追加 `topology` 字段。
- 详见 `references/09-local-module-review.md` 的「专章：子模块 / 多仓库 / repo 工具适配」。

## v2.1.0 既有能力（保留）

- **隐私合规维度（P0）**：基于《产品功能 信息安全要求-v1.2-20260210》+《附录-个人信息定义》。
- **高精确率触发**：三重门控（数据 A / 去向 B / 语义 C）全部命中才作为 P0 inline 评论，**宁可漏报不可误报**。
- `references/10-privacy-compliance.md` + `scripts/privacy_compliance_scan.py`；已挂接到 `gerrit_audit.py` 与 `local_module_prepare.py`。

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

## 7 大评审维度（**每次必全扫**）

1. **SOLID 原则** — SRP / OCP / LSP / ISP / DIP
2. **安全性** — AuthN/AuthZ / 注入 / 并发 / 资源 / IPC / 加密
3. **性能** — 算法 / 主线程阻塞 / 内存 / 缓存 / IO
4. **错误处理 + 边界** — 空 catch / RemoteException / null / 溢出 / off-by-one
5. **代码质量 + Google Style** — 缩进空格 / 命名 / imports / braces / Javadoc
6. **车载中间件专项** — 状态机 / 线程 / IPC / 电源 / 诊断 / OTA / 配置
7. **隐私合规（P0）** — 个人信息 / 敏感数据 × 传输 / 存储 / 日志 / 权限 / 跨端 / 撤回；**三重门控触发**

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
- **Java 缩进 4 空格，禁用 tab**（项目硬规范、2026-04-19 团队约定），P1
- **C++ 缩进 4 空格，禁用 tab**（项目硬规范、2026-04-19 团队约定），P1
- **C++ 风格不强制 Google Style**，**必须遵循项目原有代码风格**，P1
- **commit message 必带合规 Jira 号**（CHYT1V / BAIC / KP31 / FL1 / FL2 / FL3 / T1V / D01 / CHYT12A / CHYMIFA）— 缺失 P0 → -1；占位号（000/0001）P0 → -1；纯数字（如 123456）P0 → -1

### YAGNI
- **作为 P3 建议，不强制**（不阻断合入，仅作治理指引）

### Java Google Style 仅作参考
- 项目缩进覆盖为 4 spaces（非 Google 官方的 2 spaces）
- 其他 Google Style 项 仅作参考，项目明文规定优先

### 项目允许（非违规）
- `e.printStackTrace()` — 允许
- commit message 格式错别字 / 代码修改量 — 团队约定不纳入评审
- Log 封装类 / TAG / JavaDoc — 无明文规范时不强制

### 冲突处理
1. 项目明文规定 → 按项目
2. 项目未规定 → Google Style 仅作参考，仅 P3 建议
3. 项目习惯与 Google 不同 → 按项目

---

## 打分 + preflight

| 级别 | 场景 | Gerrit 分 |
|---|---|---|
| P0 Critical | 真崩溃 / 数据丢失 / 安全 / Jira 缺失或不合规 | **-1** |
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
  └─ 飞书简报给指定接收人（由团队配置）
```

---

## 环境（Gerrit 凭据须自行配置）

本技能**不包含**任何默认账号或 HTTP 密码。使用 Gerrit 脚本前请在 shell 中设置：

```bash
export GERRIT_BASE="https://gerrit.auto-link.com.cn"   # 或贵司 Gerrit 实例
export GERRIT_USER="<你的 Gerrit 用户名>"
export GERRIT_HTTP_PASSWORD="<Gerrit 个人设置中的 HTTP 密码>"
```

## 触发方式

用户发起即可，例如：
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
- 结果: skill 判 +1，人工已投 +2 在先，preflight 保护不覆盖
