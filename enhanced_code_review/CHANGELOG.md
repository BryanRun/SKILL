# CHANGELOG

## enhanced_code_review v2.1.2 — 2026-04-30

### P1 修复：commit message 链接段不再被误标为「缺前缀的 Jira 号」

**背景**：奇瑞规范段中【开发自测视频】常带飞书云盘链接、本地录屏路径、备份 ID 等，含 10~14 位时间戳或 file token 数字尾段。旧版 `extract_jira_violations()` 用 `\b(\d{5,})\b` 全文扫，会把这些数字误判为 `bare_number`（缺前缀的 Jira 引用），从而在 `R.JIRA_BARE_NUMBER` 路径产出 P0/P1 评论刷屏。

**修复**：在 `scripts/gerrit_client.py` 中：

- 新增 `_VIDEO_LINK_HEADERS` 段标题白名单（开发自测视频 / 测试自测视频 / 验收视频 / 录屏 / 录像 / 录制视频 / 关联视频 / 关联链接 / 关联文档 / 下载链接 / 评审视频）；
- 新增 `_bare_number_exempt_ranges(text)`：识别**仅在行首附近**出现的【...】段标题，把白名单段（从段标题到下一个【...】段标题或文末）的字符范围加入豁免；同时把行内 URL（`https?://` / `ftp://` / `file://` / `www.`）的字符范围加入豁免；
- `extract_jira_violations()` 仅对**未被豁免**的位置触发 `bare_number`；占位号检测（`placeholder`，合法前缀 + 占位数字）保持不变。

**回归用例**（`docker python:3.6.15-slim` + 当前 Python 3.10.12 双跑通）：

1. 飞书 file token + 时间戳 + 12-13 位 ID 不应被误判 → `violations=[]`
2. 正文里 5+ 位裸数字（如 `123456`）仍触发 `bare_number`
3. 正文 bare_number + 视频段链接共存：仅前者触发
4. 占位号检测保持工作（不受 bare_number 改造影响）

### 兼容回退：最低支持 Python 3.6.9

**背景**：部分服务器仍在 Python 3.6.9（如 Ubuntu 18.04 LTS / 部分 SOC 主机）。v2.0.x ~ v2.1.1 引入了 `from __future__ import annotations`（PEP 563，3.7+）、`dict[..]` / `list[..]` / `X | None`（PEP 585/604，3.9+ / 3.10+）以及 `@dataclass`（标准库 3.7+），导致这些版本服务器**无法 import 即报错**。

**修复**（功能 0 改变；仅类型注解 / 经典 API 写法）：

- `scripts/local_audit.py` / `scripts/local_module_prepare.py` / `scripts/privacy_compliance_scan.py`：删除 `from __future__ import annotations`；
- 全部 PEP 585/604 注解改为 `typing` 形式：`dict[..]` → `Dict[..]`、`list[..]` → `List[..]`、`tuple[..]` → `Tuple[..]`、`X | None` → `Optional[X]`；变量注解改为 `# type:` 注释（避免 3.6/3.7/3.8 运行时对下标的 `TypeError`）；
- `scripts/privacy_compliance_scan.py` 中 `@dataclass class Candidate` 改为普通 `class Candidate(object)` + `__slots__` + 显式 `__init__`，`to_dict` / 字段访问语义不变；
- `scripts/local_module_prepare.py` `_run_git()` 中 `subprocess.run(..., capture_output=True, text=True)` 改为 `stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True`；
- `scripts/gerrit_audit.py` 中两行 `dict[str, list[tuple[int, str]]] = {}` 等运行时变量注解改为 `# type:` 注释。

**验证**：在 docker `python:3.6.15-slim` 中 `pip install requests<2.28` 后：`py_compile` 全脚本通过，`gerrit_audit / local_audit / local_module_prepare / privacy_compliance_scan` 全部可 import，JIRA 回归 4/4 PASS。

### 分发

- 发行包：`enhanced-code-review-v2.1.2.zip`（替换 `v2.1.1` 压缩包）。

---

## enhanced_code_review v2.1.1 — 2026-04-28

### 适配车载多仓库 / git submodule / Android `repo` 工具结构

**背景**：车载工程几乎都是子模块结构。原 `local_module_prepare.py` 要求「在仓库根执行」，对 AutoLink 这类 `repo` 工具管理（`vendor/autolink/` 一级目录自身没有 `.git`，业务模块下沉到 `frameworks/cm/`、`midware/hud/` 才有 `.git`）以及 git submodule（`.git` 是 file 含 `gitdir:` 指针）场景**直接不可用**。

### 改动

- **`scripts/local_module_prepare.py`**：
  - 新增 `--repo auto`：从模块路径（绝对或相对 cwd）向上回溯定位最近的 `.git`（dir / file / symlink 三态），并把 module 自动换算为相对仓库根的路径。
  - 新增 `_classify_dot_git()` / `_find_superproject()` / `_find_repo_tool_root()` / `_scan_uninitialized_submodules()` / `_describe_topology()` 等拓扑探测函数。
  - 输出 JSON 追加 `topology` 顶层字段，覆盖：`git_root`、`git_kind`、`is_submodule`、`superproject`、`repo_tool_managed`、`repo_tool_root`、`uninitialized_submodules[]`、`auto_resolve_target`、`module_relative_to_repo`。
  - **submodule 未初始化提示**：若 `.gitmodules` 声明的子模块路径下无 `.git`，输出 `init_hint = "git -C <super> submodule update --init -- <path>"`，可复制即用；脚本**只描述、不自动执行** `git submodule update`。
  - 目标路径完全不存在但落在某个声明 submodule 下时，顶层 `topology.uninitialized_submodule_hint` 提供同款 init_hint，并以退出码 2 提示用户。
  - 兼容旧用法：显式 `--repo <path>` 与 `cd <repo> && ... <相对路径>` 行为不变；新版仅追加 `topology` 字段，无破坏性变更。
- **`references/09-local-module-review.md`**：新增**专章 子模块 / 多仓库 / repo 工具适配（v2.1.1）**，覆盖三种 `.git` 形态、`--repo auto` 用法、未初始化 submodule 处理、Agent 行为指引、自检清单。
- **`SKILL.md`**：版本升至 2.1.1；本地模块工作流不再要求「在仓库根执行」；使用示例同步更新。

### 验证

在真实 AutoLink `repo` 工具管理工作树下覆盖以下拓扑全部通过：

1. **autolink 一级目录无 `.git`，业务子目录有**：`--repo auto` 自动定位到 `frameworks/cm`，`repo_tool_managed=true`、`repo_tool_root=/home/y/t1v_8775`。
2. **已初始化 git submodule**：`git_kind=file`、`is_submodule=true`、`superproject` 指向上层工作树。
3. **superproject 下子模块未初始化**：`topology.uninitialized_submodules[]` 列出 path + 复制即用的 `git -C ... submodule update --init -- <path>`。
4. **目标路径不存在但属已声明 submodule**：退出码 2，顶层 `uninitialized_submodule_hint.init_hint` 可复制即用。
5. **显式 `--repo <path>`**：旧行为不变，同时输出 `topology` 字段（无副作用）。

### Jira 号合规性检测增强

**背景**：commit message 中 Jira 号存在两类不合规情况被旧版遗漏：(1) 纯数字（如 `123456`，无项目前缀）；(2) 占位号（如 `CHYT1V-000`、`CHYT1V-0001`，数字部分全 0 或 0 开头）。此外旧版前缀列表缺少 `FL2`、`CHYT12A`、`CHYMIFA` 三个项目。

- **`scripts/gerrit_client.py`**：
  - `JIRA_RE` 补全为 10 个合法前缀（CHYT1V / BAIC / KP31 / FL1 / FL2 / FL3 / T1V / D01 / CHYT12A / CHYMIFA）+ CL / N80（历史保留）。
  - 新增 `_PLACEHOLDER_RE`（匹配全 0 或 0 开头数字）。
  - `extract_jira()` 改造为二次过滤：正则匹配后排除占位号，只返回合规 Jira 号。
  - **新增** `extract_jira_violations()`：返回不合规 Jira 引用列表（含 `type=placeholder` 和 `type=bare_number`），供 audit 消费。
- **`scripts/gerrit_audit.py`**：
  - Jira 检测从简单"有/无"升级为**三档不合规**：(1) 完全缺失 → P0；(2) 全部为占位号/纯数字（无合规号）→ 逐条 P0；(3) 有合规号但同时存在不合规引用 → 逐条 P1 提醒。
  - 错误消息列出完整合规前缀列表与合规格式说明。
  - TODO 无主正则 (`R.TODO_NO_OWNER`) 补全项目前缀。
- **`scripts/local_audit.py`**：TODO 无主正则同步补全前缀。
- **`SKILL.md`**：硬性规范段补全前缀列表 + 不合规说明；打分 P0 行同步。
- **`references/05-code-quality-style.md`**：§4.1 Jira 号表格新增占位号和纯数字两行。
- **`references/06-automotive-middleware.md`**：项目规范表同步。
- **`references/07-review-methodology.md`**：P0 三级裁决表 Jira 条更新。
- **`references/08-llm-review-prompt.md`**：项目规范段更新前缀列表与不合规说明。
- **`README.md`**：硬性规范和打分表同步。

### 分发

- 发行包：`enhanced-code-review-v2.1.1.zip`（替换 `v2.1.0` 压缩包）。

---

## enhanced_code_review v2.1.0 — 2026-04-21

### 新增：隐私合规评审维度（P0，高精确率触发）

- **新增** `references/10-privacy-compliance.md`：基于《产品功能 信息安全要求-v1.2-20260210》只纳入**隐私合规**类条目（CS-PO-014 / 016-001~003 / 017 / 020-003 / 022-001~006 / 023~028），配套《附录-个人信息定义》的敏感个人信息清单。
- **评审方法论升级**：`references/07-review-methodology.md` 追加 **Step 8 · 隐私合规**；三级裁决表将"隐私合规双命中"列入 P0。
- **LLM Prompt 升级**：`references/08-llm-review-prompt.md` 扩展为 **7 大维度 × 8 步骤**；每条 `dimension=privacy_compliance` 的评论 `privacy_evidence` 字段（`gate_a_line` / `gate_b_line` / `cs_po_id`）**必填**。
- **新增机械扫描** `scripts/privacy_compliance_scan.py`：仅在同窗口（默认 ±8 行）内**同时**命中"敏感数据（门控 A）"和"高风险 sink（门控 B）"时产出**候选**；测试/mock/注释路径一律 drop；LLM 在 Step 8 做**门控 C 语义确认**后方可作为 P0 贴回。
- **挂接** `scripts/gerrit_audit.py` 与 `scripts/local_module_prepare.py`：输出 `privacy_candidates` 供 LLM 消费，不直接计入 P0 summary。
- **触发门槛强约束**：团队明示隐私合规 P0 「触发条件必须确认无误，不能随意触发」，扫描器与 Prompt 均以**高精确率**为第一目标，**宁可漏报，不可误报**。

### 分发

- 发行包：`enhanced-code-review-v2.1.0.zip`（替换 `v2.0.1` 压缩包）。

---

## enhanced_code_review v2.0.1 — 2026-04-20

### 安全与隐私

- **`scripts/gerrit_client.py`**：删除 `GERRIT_USER` / `GERRIT_HTTP_PASSWORD` 的**默认值**（此前含 HTTP 密码硬编码，属严重泄露风险）。未设置环境变量时调用 API 会抛出明确错误，提示由使用方自行配置 Gerrit HTTP 凭证。
- **文档与 references**：去除个人姓名与「某某明确」等表述，改为团队/项目约定用语；**不**在技能包内预设任何账号或密钥。

### 分发

- 发行包：`enhanced-code-review-v2.0.1.zip`（替换 `v2.0.0` 压缩包）。

---

## enhanced_code_review v2.0.0 — 2026-04-20

- **技能名称**：`enhanced_code_review`（与 `gerrit-review` 同源 references + scripts，质量门禁不变）。
- **新增**：本地模块评审 — `scripts/local_module_prepare.py`、`scripts/local_audit.py`、`references/09-local-module-review.md`。
- **分发**：`enhanced-code-review-v2.0.0.zip`；原版单独包 `gerrit-review-v2.0.0.zip`。

## gerrit-review / 融合版 v2.0.0 — 2026-04-19

**里程碑版本：完整融合 code-review-expert + superpowers + Google Style**

### 重大改动

- **完整 6 大评审维度**（每次必全扫，不再砍维度）：
  1. SOLID 原则
  2. 安全性（OWASP + CWE + Android CDD + ISO 21434）
  3. 性能（Effective Java Item 67 + Android Performance）
  4. 错误处理 + 边界（Effective Java 70-77 + Clean Code Ch.7）
  5. 代码质量 + 风格
  6. 车载中间件专项（L1~L10）

- **项目硬规范**：
  - Java 缩进必须 **4 空格**，禁用 tab（P1）
  - C++ 缩进必须 **4 空格**，禁用 tab（P1）
  - C++ 风格不强制 Google Style，必须遵循项目原有风格（P1）
  - commit message 必带 Jira 号（P0 → -1）

- **YAGNI 定位**：作为 P3 建议，不强制，不阻断合入

- **评审方法论**：
  - 对抗式评审（verify-before-comment）
  - 三问 filter（每条必过）
  - 每条评论必有权威依据（不是 AI 常识）
  - 评论 5 要素（问题+依据+原理+建议+Before/After）

- **新增 preflight 保护**：不覆盖人工分数（self 已 +2 时不贴回）

### 新增文件

- `references/01-solid-principles.md`
- `references/02-security.md`
- `references/03-performance.md`
- `references/04-error-handling-boundaries.md`
- `references/05-code-quality-style.md`
- `references/06-automotive-middleware.md`
- `references/07-review-methodology.md`
- `references/08-llm-review-prompt.md`
- `VERSION` / `CHANGELOG.md`

### 已删除

- `references/solid-architecture.md` → 合并到 01
- `references/security-reliability.md` → 合并到 02
- `references/code-quality.md` → 拆分到 03/04/05
- `references/adversarial-review.md` → 合并到 07
- `references/llm-review-prompt.md` → 合并到 08
- `references/automotive-middleware-checklist.md` → 重写为 06
- `references/false-positives.md` → 合并到 07 反例表

---

## v1.0.0 — 2026-04-19（早期版本）

- 初始版本，包含 7 脚本 + 6 references
- code-review-expert + superpowers 初步融合
- CR 993636 首次实战（-1，发现 DisplayController NPE）
- CR 995945 实战（+1，preflight 保护未覆盖人工 +2）
