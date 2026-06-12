# gerrit-pipeline — 使用说明

**版本：v2.0.0**

gerrit-pipeline 是一个 Claude Code 优先、Agent Neutral 兼容的 Skill，为车联 AutoLink 团队提供 Gerrit 代码提交评审一站式自动化能力。Claude Code 中可获得最佳体验：斜杠命令、结构化确认、多选、Skill 调用都能直接串联；其他 Agent 只要支持读取 skill 文档、执行脚本、与用户确认/选择，也可以按同一流程执行。v1.9.0 起，原 Step 3（Checklist 确认）与原 Step 3.5（飞书通知前确认）合并为单一确认屏，在不降低安全红线的前提下减少交互弹窗。目标是减少重复操作、统一提交规范、加速 Code Review 闭环。

## 1. 功能概览

```text
Step 1: 代码提交    → 生成规范 commit message + push 到 Gerrit
Step 2: 代码评审    → 七维自动评审 + 结果贴回 Gerrit
Step 3: 合并确认    → 同屏展示 Checklist 预览 + 飞书通知预览，一次确认后贴 Checklist
Step 4: 飞书通知    → Checklist 全部成功后发送评审结果卡片到飞书群，@审核人
```

## 2. 首次使用配置

### 2.0 Agent 兼容说明

- **推荐运行时：Claude Code**。直接使用 `/gerrit-pipeline`、`配置 gerrit-pipeline` 和结构化交互，步骤最少
- **兼容运行时：其他 Agent**。需具备 shell/Python 执行能力、用户确认/选择能力，并能调用或复用 `enhanced_code_review`
- **交互等价原则**：文档中的 `AskUserQuestion` 表示结构化确认/选择/输入；非 Claude Agent 可用等价表单、多选控件或清晰的对话提问实现，但不能省略 JIRA 确认、commit message 确认、Checklist 责任声明等红线

### 2.1 前置条件

1. **安装 enhanced_code_review skill**：Step 2（代码评审）依赖此 skill 提供七维自动评审能力。请从 [enhanced_code_review 版本下载页](https://t83dfrspj4.feishu.cn/wiki/Ja9BwNfKfi4ajAkwzSrcEFdznne) 下载最新版本，并使用AI agent完成部署/更新，否则评审步骤无法执行。
2. **飞书机器人入群**：在目标飞书群中添加名为 **WALL-E** 的机器人（群设置 → 群机器人 → 添加机器人 → 搜索「WALL-E」），否则无法发送通知。

### 2.2 方式一：Claude Code 快速配置（推荐）

在 Claude Code 中直接输入：

```text
配置 gerrit-pipeline
```

Claude 会通过结构化对话交互引导你完成全部配置，包括：

1. **Gerrit 凭据**：用户名、HTTP 密码、默认 Reviewer 列表
2. **飞书通知**：目标群 chat_id、需要 @mention 的审核人
3. **按项目配置**（可选）：为不同项目指定专属的飞书通知群、审核人和 Reviewer

整个过程无需手动编辑任何文件或运行脚本，Claude 会自动完成环境变量设置和配置文件生成。这是当前体验最完整的路径。

> **提示**：如需修改已有配置，同样输入 `配置 gerrit-pipeline`，Claude 会读取现有配置并引导你更新。

### 2.3 方式二：手动配置

#### 2.3.1 初始化配置文件

```bash
# Claude Code 默认安装路径示例；其他 Agent 请替换为自己的 skill 安装目录
cd ~/.claude/skills/gerrit-pipeline/scripts
python3 pipeline_config.py init
```

按提示输入：
1. **Gerrit 用户名** 和 **HTTP 密码**
2. **默认 Reviewer**（逗号分隔）
3. **飞书群 chat_id**：目标通知群的 ID（在飞书群设置中查看）
4. **@mention 成员邮箱**：需要 @提醒 的审核人邮箱，逗号分隔

脚本会自动查询成员的飞书 open_id 并保存到配置文件。

配置文件位置：`~/.config/gerrit-pipeline/config.json`（用户私有，不随 skill 分发）

#### 2.3.2 按项目配置（可选）

当你负责多个项目，不同项目需要通知不同飞书群、@不同审核人或指定不同 Reviewer 时，可在基础配置之上添加项目专属配置：

```bash
# Claude Code 默认安装路径示例；其他 Agent 请替换为自己的 skill 安装目录
cd ~/.claude/skills/gerrit-pipeline/scripts

# 添加项目配置（自动查询 at_members 的飞书 open_id）
python3 pipeline_config.py add-project \
  --name "D01" \
  --chat-id "oc_xxx" \
  --reviewers "reviewer1,reviewer2" \
  --at-emails "user1@auto-link.com.cn,user2@auto-link.com.cn"
```

参数说明：

| 参数 | 必填 | 说明 |
|------|------|------|
| `--name` | 是 | 项目名称（如 `D01`、`BAIC`） |
| `--chat-id` | 否 | 项目专属飞书群 ID，不填则继承顶层默认 |
| `--reviewers` | 否 | 项目专属 Reviewer，逗号分隔，不填则继承顶层默认 |
| `--at-emails` | 否 | 项目专属 @mention 审核人邮箱，逗号分隔，脚本自动查询 open_id |

配置后，Pipeline 在 Step 1 中会让你选择本次提交所属项目，自动使用对应的项目配置。未配置 `projects` 时行为与之前完全一致。

### 2.4 查看/管理配置

```bash
# 查看当前配置
python3 pipeline_config.py show

# 查询用户 open_id
python3 pipeline_config.py lookup-users --emails "user1@company.com,user2@company.com"

# 查询并保存到配置
python3 pipeline_config.py lookup-users --emails "user1@company.com" --save
```

## 3. 使用方式

> **⚠️ 关于触发方式的说明**：
> - **Claude Code 中最具确定性的调用方式**：`/gerrit-pipeline`（斜杠命令，精确触发）
> - 以下自然语言触发词均依赖 AI 语义匹配，**无法保证 100% 命中**
> - 其他 Agent 如不支持斜杠命令，应使用明确自然语言：`gerrit pipeline` / `pipeline submit` / `pipeline notify`
> - Claude Code 中如遇触发失败，请使用 `/gerrit-pipeline` 斜杠命令

### 3.1 完整流水线

在 Claude Code 或其他兼容 Agent 中输入以下任意触发词：

```text
gerrit pipeline
gp
一键提交
提交并评审
```

执行 Agent 会按 Step 1 → 2 → 3 → 4 顺序自动执行全部步骤。

### 3.2 独立操作

每步均可单独执行：

| 命令 | 说明 | 所需输入 |
|------|------|---------|
| `pipeline submit` / `gerrit submit` / `提交代码` | 仅提交代码 | 当前仓库有未提交变更 |
| `gerrit amend` | Amend 追加 patchset | 当前仓库有未提交变更 + 已有 Change |
| `gerrit cherry-pick` | Cherry-pick 到其他分支 | 目标分支名 + JIRA-ID 确认 |
| `pipeline review <CR编号>` | 仅评审 | CR 编号 |
| `pipeline checklist <CR编号>` | 仅贴 Checklist | CR 编号 |
| `pipeline notify` | 仅发飞书通知 | CR 编号 + 评审结果 |

### 3.3 用户交互步骤一览

完整流水线中，执行 Agent 会在以下节点与用户交互。Claude Code 可用结构化弹窗合并交互；其他 Agent 可分步询问。标注为「可选」的步骤在条件不满足时自动跳过。

#### Step 1：代码提交

| # | 交互步骤 | 必选/可选 | 说明 |
|---|---------|----------|------|
| 1 | 确认提交模式（新建 / Amend / Cherry-pick） | 必选 | 触发指令中已包含模式关键词时自动跳过 |
| 2 | 判定提交范围 | 自动（仅新建提交） | 显式多仓关键词直接进入多仓；用户提供仓库路径时按路径数量判定且不扫描；显式单仓关键词直接进入单仓；无显式意图时，普通 Git 仓库只查当前仓库，repo workspace 先询问是否全局扫描（20 秒超时） |
| 3 | 选择所属项目 | 可选 | 仅在配置了 `projects` 时触发；只有一个项目时自动选中 |
| 4 | JIRA-ID | 必选 | 不可跳过，必须通过交互确认 |
| 5 | 新建提交信息批量确认 | 必选（仅新建提交） | 同屏收集提交类型、概要描述、目标分支、是否添加【开发自测视频】 |
| 6 | 确认关联仓库列表 | 必选（仅关联提交） | 自动扫描结果作为 multiSelect 候选项呈现，用户明确勾选本次需要关联提交的仓库 |
| 7 | Topic 名称 | 必选（仅关联提交） | |
| 8 | 确认 commit message | 必选 | 展示生成的 commit message，用户确认或修改 |

#### Step 2：代码评审

无用户交互，自动执行。

#### Step 3：合并确认

| # | 交互步骤 | 必选/可选 | 说明 |
|---|---------|----------|------|
| 9 | 合并确认屏 | 必选 | 同屏展示 1 份固定 Checklist 预览、飞书通知卡片预览与责任声明；可选全部确认 / 仅贴 Checklist 暂不发飞书 |

#### Step 4：飞书通知

无用户交互，自动执行。

## 4. 配置文件结构

`~/.config/gerrit-pipeline/config.json`：

```json
{
  "gerrit": {
    "user": "your_gerrit_username",
    "http_password": "your_gerrit_http_password",
    "reviewers": ["reviewer1", "reviewer2"]
  },
  "feishu": {
    "chat_id": "oc_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "submitter": {"name": "你的姓名", "open_id": "ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
    "at_members": [
      {"name": "张三", "open_id": "ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
      {"name": "李四", "open_id": "ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}
    ]
  },
  "projects": {
    "D01": {
      "gerrit": { "reviewers": ["专属reviewer1", "专属reviewer2"] },
      "feishu": { "chat_id": "oc_D01群ID", "at_members": [{"name": "王五", "open_id": "ou_xxx"}] }
    },
    "BAIC": {
      "feishu": { "chat_id": "oc_BAIC群ID" }
    }
  }
}
```

| 配置项 | 说明 |
|--------|------|
| `gerrit.user` | Gerrit 用户名 |
| `gerrit.http_password` | Gerrit HTTP 密码（在 Gerrit Settings → HTTP Credentials 中生成） |
| `gerrit.reviewers` | 默认 Reviewer 列表（push 时自动添加） |
| `feishu.chat_id` | 默认飞书通知群 ID |
| `feishu.submitter` | 提交人信息（name + open_id），通知卡片中 @提交人 |
| `feishu.at_members` | 默认飞书 @mention 审核人列表（name + open_id） |
| `projects` | 按项目差异化配置（可选，不配置时使用顶层默认值） |
| `projects.<项目名>.gerrit.reviewers` | 项目专属 Reviewer 列表，覆盖顶层 |
| `projects.<项目名>.feishu.chat_id` | 项目专属飞书群 ID，覆盖顶层 |
| `projects.<项目名>.feishu.at_members` | 项目专属 @mention 审核人，覆盖顶层 |

> **匹配规则**：Pipeline 在 Step 1 中通过 `AskUserQuestion` 或等价交互能力让用户选择本次提交所属项目（从 `projects` 的 key 列出）。匹配到的字段覆盖顶层默认值，未配置的字段自动 fallback。同一仓库可属于多个项目，每次提交时由用户选择。只有一个项目时自动选中，无 `projects` 配置时跳过。

### 4.1 按项目配置管理

```bash
# 添加或更新项目配置
python3 pipeline_config.py add-project \
  --name "D01" \
  --chat-id "oc_xxx" \
  --reviewers "reviewer1,reviewer2" \
  --at-emails "user1@auto-link.com.cn,user2@auto-link.com.cn"

# 列出所有项目配置
python3 pipeline_config.py list-projects

# 删除项目配置
python3 pipeline_config.py remove-project --name "D01"

```

## 5. 脚本说明

| 脚本 | 用途 |
|------|------|
| `pipeline_config.py` | 配置管理（init / show / lookup-users / add-project / list-projects / remove-project） |
| `feishu_notify.py` | 发送飞书群通知（读取配置，支持 @mention） |
| `gerrit_post_checklist.py` | 贴 Checklist 到 Gerrit CR 评论 |
| `gerrit_post_review.py` | 贴评审结论到 Gerrit CR 评论 |
| `telemetry_client.py` | 内部运行指标后台上报 |
| `telemetry_defaults.json` | 内置运行指标默认配置 |

## 6. 内部运行指标

v2.0.0 起，gerrit-pipeline 默认启用内部运行指标上报。配置随 skill 内部分发，用户无需感知或配置 URL、版本 key、签名密钥、开关等参数。

上报在后台执行，请求使用 HMAC-SHA256、时间戳和 nonce 签名，不影响代码提交、评审、Checklist 或飞书通知主流程。网络不可达时，事件会暂存在本地队列，并在后续 pipeline 运行且网络可用时补发。

## 7. 依赖

1. Python 3.6+
2. `requests` 库（`pip install requests`）
3. Gerrit SSH 访问权限（用于 git push）
4. **enhanced_code_review skill**：Step 2（代码评审）依赖此 skill 提供七维自动评审能力。Claude Code 默认同步安装到 `~/.claude/skills/`；其他 Agent 安装到各自的 skill/插件目录，并确保 gerrit-pipeline 能调用其等价流程

> Step 1（代码提交）、Step 3（Checklist）、Step 4（飞书通知）为内置能力，无额外 skill 依赖。

## 8. 常见问题

**Q1: 飞书通知发送失败？**
1. 确认 **WALL-E** 机器人已加入目标群

**Q2: @mention 不生效？**
1. 确认配置中的 `open_id` 正确（可通过 `pipeline_config.py lookup-users` 重新查询）
2. 确认被 @的用户在目标群中

**Q3: 如何更换通知群？**
1. 运行 `python3 pipeline_config.py init` 重新配置 chat_id

## 9. 版本下载

线上版本及历史版本下载：[gerrit-pipeline 版本下载](https://t83dfrspj4.feishu.cn/wiki/Ja9BwNfKfi4ajAkwzSrcEFdznne)

### 9.1 本地打包发版流程

对应飞书使用手册：https://t83dfrspj4.feishu.cn/wiki/Tzq1wRg5biiaCLkcx2gcgcb6nO1

流程 A 用于飞书 zip 手动分发：本地清空 `release/` 后生成当前版本 zip，不通过飞书 API 上传，文件由维护者手动替换。
流程 B 用于 SkillPack 发布：以 `skill.json` 为版本与元数据 SOT，通过 SkillPack 客户端完成 lint、打包与发布，当前 SkillPack 发布通道为 `claude-code`；`her`、`cursor`、`codex` 和通用 `agent` 兼容性写入描述与标签，后续如需对应端上架需从对应客户端单独发布。

## 10. 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| v2.0.0 | 2026-06-12 | 1. 默认启用内部运行指标上报，配置随 skill 分发，用户无需额外配置<br>2. 新增本地 spool 队列，网络不可达或后台进程拉起失败时保留事件，下次运行批量补发<br>3. 新增 Telemetry Gateway，接收端先异步入库再由后台 flush 到飞书多维表格，并按 `event_id` 做幂等保护 |
| v1.9.7 | 2026-06-03 | 1. 补齐发布包中的 `references/full-spec.md`，避免用户更新后完整规范文档缺失<br>2. 流程 A 增加 zip 内容校验，流程 B 增加 SkillPack tarball 内容校验，避免后续发版再次遗漏完整规范<br>3. 不改变用户配置、主流程行为和既有升级路径 |
| v1.9.6 | 2026-06-01 | 1. 放开 Gerrit Pipeline JIRA-ID 前缀白名单，不再枚举固定项目 Key<br>2. JIRA-ID 校验改为通用 Jira Key 形态：项目 Key 以大写字母开头，可包含大写字母和数字，后接 `-` 与数字编号<br>3. 保留 JIRA-ID 用户确认、中文方括号包裹和真实工单要求，提升新增项目兼容性 |
| v1.9.5 | 2026-05-29 | 1. AutoLink Code Review Checklist 升级为 `v2.1`，固定模板从 12 项扩展为 13 项<br>2. 流程合规新增“代码影响”检查项，要求共享代码、公共模块、平台化组件变更说明影响项目和验证范围<br>3. 同步更新 Step 3 Checklist 展示、贴回和评审结论区分说明 |
| v1.9.4 | 2026-05-25 | 1. 将 SkillPack 发布平台切换为 `claude-code`，重新发布 Claude Code 通道版本<br>2. 保留 `her`、`cursor`、`codex` 和通用 `agent` 兼容性说明，避免误将兼容范围写入 SkillPack 单平台字段 |
| v1.9.3 | 2026-05-25 | 1. 适配 SkillPack 发布规范：新增 `skill.json` 作为版本与元数据 SOT，新增 `.skillpackignore` 控制发布包内容<br>2. 当前 SkillPack 发布通道声明为 `her`；同时在描述与标签中说明 `cursor`、`claude-code`、`codex` 和通用 `agent` 兼容性<br>3. 新增发版流程 B：通过 SkillPack 客户端执行 lint、打包与发布；README 与飞书文档仅保留流程 A/B 的简要说明 |
| v1.9.2 | 2026-05-25 | 1. 提交范围判定改为显式意图优先：多仓关键词直接进入关联提交，显式仓库路径按数量判定，单仓关键词只提交当前仓库<br>2. 无显式意图时避免默认全局扫描：普通 Git 仓库只检查当前仓库，repo workspace 先询问范围，并为全局扫描增加 20 秒超时处理<br>3. 飞书通知提交概要严格使用 commit message 第一行，并转义 Markdown 链接文本，避免标题中的 `[`、`]`、`\` 破坏卡片链接<br>4. 固化本地发版流程：发版只生成本地 zip，不包含飞书 API 上传；生成产物前必须清空 `release/` 目录；流程最后提交并推送当前仓库全部改动<br>5. 固化飞书使用手册链接，避免后续发版遗漏文档块级更新 |
| v1.9.1 | 2026-05-21 | Agent Neutral 通用性说明：保留 Claude Code 作为最佳体验路径，同时明确其他 Agent 的等价交互、脚本调用和 enhanced_code_review 复用要求 |
| v1.9.0 | 2026-05-21 | 1. 原 Step 3 与 Step 3.5 合并为单一确认屏：Checklist 预览、飞书通知预览、责任声明同屏展示<br>2. 提交流程交互压缩：新建提交不再单问"是否多仓库"，改为预扫描自动判路；批量收集提交信息，减少弹窗次数<br>3. 多仓库 Checklist 只展示 1 份固定模板预览并统一确认，但执行级仍逐 CR 串行贴回<br>4. 故障边界明确：任一 Checklist 贴回失败则中止飞书发送，并向用户报告部分成功状态 |
| v1.8.3 | 2026-05-14 | 飞书通知卡片底部 footer 新增显示 skill 版本号（如 `由 Gerrit Pipeline v1.8.3 自动发送`），版本号从 README 动态解析，发版时只需改 README |
| v1.8.2 | 2026-05-14 | 1. Checklist 模板预填状态：9 项 `[✓]` + 3 项可选 `[o]` + 结论预选 Approve，Claude 直接复制输出避免空白和勾选丢失<br>2. 规则措辞同步：从"禁止标注状态"改为"按模板原样输出（含预填状态）"<br>3. Step 3 性能优化：明确直接复制不做推理 |
| v1.8.1 | 2026-05-06 | 【影响范围】字段最低字数从无要求改为 8 字，与模板规范对齐 |
| v1.8.0 | 2026-05-05 | 1. JIRA-ID 确认强制化：所有提交场景必须通过 AskUserQuestion 确认 JIRA-ID<br>2. 完整流水线支持 Amend / Cherry-pick 模式，新增路径 C / D<br>3. Gerrit 凭据上下文传递：Step 1 读取后续步骤直接复用，禁止重复查找<br>4. Checklist 完全固化：不再标注状态，完全按模板原样输出<br>5. 飞书通知卡片新增"提交日期"字段<br>6. 流水线步骤编号修正，补全 Step 3.5 |
| v1.7.0 | 2026-05-03 | 1. 按项目差异化配置：新增 `projects` 字段，不同项目可指定专属飞书通知群、审核人和 Reviewer<br>2. 评审结论贴回兜底：Step 2 新增校验，enhanced_code_review 未贴回时由 pipeline 兜底执行<br>3. 飞书通知卡片调整：提交概要移至最上方，以可点击链接形式展示<br>4. 配置交互优化：`配置 gerrit-pipeline` 时自动引导按项目配置 |
| v1.6.4 | 2026-05-02 | 1. Commit Message 强制校验：commit 后 push 前新增校验-修正-重试闭环，最多 3 次自动修正<br>2. 触发词说明：推荐 `/gerrit-pipeline` 斜杠命令精确触发 |
| v1.6.3 | 2026-05-01 | 1. Step 2 评审范围限制：仅评审修改代码及强相关代码，排除无关历史代码<br>2. 六维评审升级为七维评审，新增隐私合规维度 |
| v1.6.2 | 2026-05-01 | 1. Step 2 评审结论为必需项：必须完整展示给用户并贴回 Gerrit，不可跳过 |
| v1.6.1 | 2026-05-01 | 1. 严格区分 Step 2 评审结论与 Step 3 Checklist，严禁混淆或合并<br>2. Checklist 内容完全固化，只能标注状态（✓/x/o），禁止修改检查项文字<br>3. Checklist 必须完整展示，禁止省略或截断 |
| v1.6.0 | 2026-05-01 | 1. 【体现版本】字段自动填当日日期，格式固定为 `After YYYY/M/D`<br>2. 【提交项目/分支】字段简化为仅填分支名<br>3. Checklist 确认环节责任声明固化<br>4. Checklist 模板固化不可变更 |
| v1.5.1 | 2026-04-29 | 1. 新增触发词 `gp`（gerrit pipeline 缩写），简化调用 |
| v1.5.0 | 2026-04-29 | 1. 【开发自测视频】字段改为可选，由用户交互选择是否添加<br>2. Commit message 严格符合模板，禁止 Co-Authored-By 等模板外多余行<br>3. Step 3 与 Step 4 之间新增确认步骤，确保 Gerrit 门禁通过后再发送飞书通知 |
| v1.4.0 | 2026-04-28 | 1. 内置公共飞书应用凭证，用户无需再配置 `FEISHU_APP_ID` / `FEISHU_APP_SECRET` 环境变量 |
| v1.3.1 | 2026-04-28 | 1. 飞书通知卡片中 Topic 改为可点击的 Gerrit 链接，跳转到 topic 搜索页 |
| v1.3.0 | 2026-04-27 | 1. 新增 Topic（多仓库关联提交）完整规范<br>2. 支持命名规则、【x/y】关联标识、提交顺序约束、合入纪律<br>3. 新增 Topic 名称格式校验脚本<br>4. 交互流程每次询问是否为关联提交<br>5. 自动扫描有变更的仓库，支持 multiSelect 确认<br>6. 多仓库场景下 Step 2/3 逐 CR 执行，Step 4 汇总通知 |
| v1.2.0 | 2026-04-27 | 1. Commit message body 各字段新增 50 字上限约束<br>2. 校验脚本同步增加最大字数检查 |
| v1.1.0 | 2026-04-26 | 1. 融合 gerrit-submit 为内置能力，Step 1 不再依赖外部 skill<br>2. 通知卡片新增提交人字段并 @mention<br>3. 新增 `feishu.submitter` 配置项 |
| v1.0.0 | 2026-04-25 | 1. 首次发布<br>2. 四步流水线（代码提交 → 评审 → Checklist → 飞书通知）<br>3. 每步支持独立操作<br>4. 配置化（用户私有 config.json）<br>5. 飞书通知 @mention 审核人 |

## 11. 反馈与建议

使用中如有问题、建议或新需求，欢迎在反馈表中填写：

[gerrit-pipeline 反馈表](https://t83dfrspj4.feishu.cn/wiki/WLYtwoeKWiIr2vk39GvcruyznNe)
