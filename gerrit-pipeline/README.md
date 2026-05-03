# gerrit-pipeline — 使用说明

**版本：v1.7.0**

gerrit-pipeline 是一个 Claude Code Skill，为车联 AutoLink 团队提供 Gerrit 代码提交评审一站式自动化能力。只需一句指令，即可完成从代码提交、自动评审、Checklist 贴回到飞书群通知的完整流水线，也支持每个步骤独立执行。目标是减少重复操作、统一提交规范、加速 Code Review 闭环。

## 1. 功能概览

```
Step 1: 代码提交    → 生成规范 commit message + push 到 Gerrit
Step 2: 代码评审    → 七维自动评审 + 结果贴回 Gerrit
Step 3: Checklist  → AutoLink Code Review Checklist v2.0 贴到 Gerrit
Step 4: 飞书通知    → 发送评审结果卡片到飞书群，@审核人
```

## 2. 首次使用配置

### 2.1 前置条件

1. **安装 enhanced_code_review skill**：Step 2（代码评审）依赖此 skill 提供七维自动评审能力。请将其解压到 `~/.claude/skills/enhanced_code_review/` 目录下，否则评审步骤无法执行。
2. **飞书机器人入群**：在目标飞书群中添加名为 **WALL-E** 的机器人（群设置 → 群机器人 → 添加机器人 → 搜索「WALL-E」），否则无法发送通知。

### 2.2 方式一：Claude Code 快速配置（推荐）

在 Claude Code 中直接输入：

```
配置 gerrit-pipeline
```

Claude 会通过对话交互引导你完成全部配置，包括：

1. **Gerrit 凭据**：用户名、HTTP 密码、默认 Reviewer 列表
2. **飞书通知**：目标群 chat_id、需要 @mention 的审核人
3. **按项目配置**（可选）：为不同项目指定专属的飞书通知群、审核人和 Reviewer

整个过程无需手动编辑任何文件或运行脚本，Claude 会自动完成环境变量设置和配置文件生成。

> **提示**：如需修改已有配置，同样输入 `配置 gerrit-pipeline`，Claude 会读取现有配置并引导你更新。

### 2.3 方式二：手动配置

#### 2.3.1 初始化配置文件

```bash
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
> - **最具确定性的调用方式**：`/gerrit-pipeline`（斜杠命令，精确触发）
> - 以下自然语言触发词均依赖 AI 语义匹配，**无法保证 100% 命中**
> - 如遇触发失败，请使用 `/gerrit-pipeline` 斜杠命令

### 3.1 完整流水线

在 Claude Code 中输入以下任意触发词：

```
gerrit pipeline
gp
一键提交
提交并评审
```

Claude 会按 Step 1 → 2 → 3 → 4 顺序自动执行全部步骤。

### 3.2 独立操作

每步均可单独执行：

| 命令 | 说明 | 所需输入 |
|------|------|---------|
| `pipeline submit` / `gerrit submit` / `提交代码` | 仅提交代码 | 当前仓库有未提交变更 |
| `gerrit amend` | Amend 追加 patchset | 当前仓库有未提交变更 + 已有 Change |
| `gerrit cherry-pick` | Cherry-pick 到其他分支 | 目标分支名 |
| `pipeline review <CR编号>` | 仅评审 | CR 编号 |
| `pipeline checklist <CR编号>` | 仅贴 Checklist | CR 编号 |
| `pipeline notify` | 仅发飞书通知 | CR 编号 + 评审结果 |

### 3.3 用户交互步骤一览

完整流水线中，Claude 会在以下节点与用户交互。标注为「可选」的步骤在条件不满足时自动跳过。

#### Step 1：代码提交

| # | 交互步骤 | 必选/可选 | 说明 |
|---|---------|----------|------|
| 1 | 是否为多仓库关联提交 | 必选 | 触发指令中已包含 topic 关键词时自动跳过 |
| 2 | 选择所属项目 | 可选 | 仅在配置了 `projects` 时触发；只有一个项目时自动选中 |
| 3 | 提交类型（bug / change / feature） | 必选 | |
| 4 | JIRA-ID | 必选 | |
| 5 | 概要描述 | 必选 | |
| 6 | 目标分支 | 必选 | 可从当前分支推断 |
| 7 | 是否添加【开发自测视频】 | 可选 | 选"不需要"则不添加该字段 |
| 8 | 确认关联仓库列表 | 必选（仅关联提交） | 扫描后 multiSelect 展示，用户勾选确认 |
| 9 | Topic 名称 | 必选（仅关联提交） | |
| 10 | 确认 commit message | 必选 | 展示生成的 commit message，用户确认或修改 |

#### Step 2：代码评审

无用户交互，自动执行。

#### Step 3：贴 Checklist

| # | 交互步骤 | 必选/可选 | 说明 |
|---|---------|----------|------|
| 11 | 确认 Checklist 内容 | 必选 | 完整展示 12 项检查 + 评审结论建议，含责任声明，确认后才贴出 |

#### Step 3.5：发送飞书通知前确认

| # | 交互步骤 | 必选/可选 | 说明 |
|---|---------|----------|------|
| 12 | 确认是否发送飞书通知 | 必选 | 确认门禁通过、关联 Change 就绪；选"暂不发送"则中止通知，不影响前序结果 |

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

> **匹配规则**：Pipeline 在 Step 1 中通过 AskUserQuestion 让用户选择本次提交所属项目（从 `projects` 的 key 列出）。匹配到的字段覆盖顶层默认值，未配置的字段自动 fallback。同一仓库可属于多个项目，每次提交时由用户选择。只有一个项目时自动选中，无 `projects` 配置时跳过。

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

## 6. 依赖

1. Python 3.6+
2. `requests` 库（`pip install requests`）
3. Gerrit SSH 访问权限（用于 git push）
5. **enhanced_code_review skill**：Step 2（代码评审）依赖此 skill 提供七维自动评审能力，需同步安装到 `~/.claude/skills/` 目录下

> Step 1（代码提交）、Step 3（Checklist）、Step 4（飞书通知）为内置能力，无额外 skill 依赖。

## 7. 常见问题

**Q1: 飞书通知发送失败？**
1. 确认 **WALL-E** 机器人已加入目标群

**Q2: @mention 不生效？**
1. 确认配置中的 `open_id` 正确（可通过 `pipeline_config.py lookup-users` 重新查询）
2. 确认被 @的用户在目标群中

**Q3: 如何更换通知群？**
1. 运行 `python3 pipeline_config.py init` 重新配置 chat_id

## 8. 版本下载

最新版本及历史版本下载：[gerrit-pipeline 版本下载](https://t83dfrspj4.feishu.cn/wiki/Ja9BwNfKfi4ajAkwzSrcEFdznne)

## 9. 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
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

## 10. 反馈与建议

使用中如有问题、建议或新需求，欢迎在反馈表中填写：

[gerrit-pipeline 反馈表](https://t83dfrspj4.feishu.cn/wiki/WLYtwoeKWiIr2vk39GvcruyznNe)
