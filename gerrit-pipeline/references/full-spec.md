---
name: gerrit-pipeline
description: >-
  Gerrit 一键提交评审流水线。串联 代码提交 → CR评审 → Checklist+飞书通知合并确认 流程，严格按 Step 1 → 2 → 3 → 4 顺序依次调用（v1.9.0 起 Step 3 合并原 Step 3.5 通知前确认）。每步均支持独立操作。
  内置完整的 Gerrit 代码提交能力（commit message 规范、推送、amend、cherry-pick）。
  触发：gerrit pipeline / gp / 一键提交 / 提交并评审 / submit and review / 一键提交评审 /
  独立操作：pipeline submit / gerrit submit / gerrit push / gerrit amend / gerrit cherry-pick / 提交到gerrit / 推送代码 / 提交代码审查 / 推代码 / 提交CR /
  pipeline review / pipeline checklist / pipeline notify / 飞书通知
---

# Gerrit Pipeline — 一键提交评审流水线

将代码提交、自动评审、Checklist + 飞书通知前确认串联为一键流水线（Step 1 → 2 → 3 → 4，v1.9.0 起 Step 3 合并原 Step 3.5 的确认职责）。每步均支持独立操作。

代码提交能力（Step 1）已内置，无需安装 gerrit-submit skill。

## Agent 运行时兼容模型

本 skill 采用 **Claude Code 优先、Agent Neutral 兼容** 的设计：

- **Claude Code 是推荐运行时**：可直接使用斜杠命令、`AskUserQuestion`、multiSelect、Skill tool 调用等原生能力，交互步骤最少，体验最佳
- **其他 Agent 是兼容运行时**：只要能读取本文件、执行 shell/Python 脚本、与用户进行确认/选择交互，并调用等价的代码评审能力，即可按同一流程执行
- **交互能力抽象**：文中的 `AskUserQuestion` 表示“向用户发起结构化确认/选择/输入”的能力；Claude Code 可使用原生 `AskUserQuestion`，其他 Agent 可用等价表单、多选控件或明确的对话提问实现
- **Skill 调用抽象**：文中的 `Skill(...)` 表示“调用另一个已安装能力/子流程”；Claude Code 可使用 Skill tool，其他 Agent 可直接加载对应 skill 文档或调用其脚本/流程

除明确标注为“Claude Code 优化路径”的内容外，流程规则、故障边界、确认红线和脚本调用均不依赖特定 Agent。

## 触发条件

> **⚠️ 关于触发方式的说明**：
> - **Claude Code 中最具确定性的调用方式**：`/gerrit-pipeline`（斜杠命令，精确触发）
> - **自然语言触发词**（如下所列）均依赖 AI 语义匹配，**无法保证 100% 命中**
> - 其他 Agent 如不支持斜杠命令，应使用明确自然语言：`gerrit pipeline` / `pipeline submit` / `pipeline notify`
> - Claude Code 中如遇触发失败，请使用 `/gerrit-pipeline` 斜杠命令

### 完整流水线

以下任一表述触发完整四步流水线：

- `gerrit pipeline` / `gp` — 执行完整流水线
- `一键提交` / `一键提交评审` — 提交 + 评审 + Checklist + 飞书通知
- `提交并评审` / `submit and review` — 同上
- `pipeline` — 简写触发

### 独立操作

每步均可单独触发，独立执行时需用户提供必要的上下文信息：

| 触发词 | 步骤 | 所需输入 |
|--------|------|---------|
| `pipeline submit` / `gerrit submit` / `gerrit push` / `提交到gerrit` / `推送代码` / `提交代码审查` / `推代码` / `提交CR` | Step 1: 代码提交 | 当前仓库有未提交的变更 |
| `gerrit amend` | Step 1: Amend 追加 patchset | 当前仓库有未提交的变更 + 已有 Change |
| `gerrit cherry-pick` | Step 1: Cherry-pick 到其他分支 | 目标分支名 + JIRA-ID 确认 |
| `pipeline review <CR编号>` / `评审CR` | Step 2: 代码评审 | CR 编号 |
| `pipeline checklist <CR编号>` / `贴checklist` | Step 3: 贴 Checklist | CR 编号 |
| `pipeline notify` / `飞书通知` | Step 4: 飞书通知 | CR 编号、URL、评审结果 |

独立操作时，执行 Agent 根据触发词识别目标步骤，仅执行该步骤。如缺少必要输入，通过 `AskUserQuestion` 或等价交互能力向用户收集。

---

## 流水线总览

```
Step 1: gerrit-submit        → 生成 commit message + git push → 获得 CR 编号
          ↓
Step 2: enhanced_code_review → review CR <编号> → 七维评审 + 贴回 Gerrit
          ↓
Step 3: 合并确认              → 同屏展示 Checklist 预览 + 飞书通知卡片预览 + 责任声明
                              → 用户一次确认后：串行贴 Checklist 到所有 CR
          ↓
Step 4: 飞书通知              → Checklist 全部成功后发送飞书通知
```

> **v1.9.0 合并说明**：原 Step 3（Checklist 确认贴出）与原 Step 3.5（飞书通知前确认）合并为单一确认屏。执行级仍保持顺序与故障边界：所有 Checklist 贴回成功后才发送飞书；任一 Checklist 贴失败则中止飞书发送并报告部分成功状态。

**四步严格顺序执行**，任一步骤失败则中止流水线并向用户报告。

### 流水线上下文传递

完整流水线在同一会话中顺序执行，Step 1 读取的配置信息在后续步骤中直接复用，**禁止重复查找**。

#### 凭据上下文（Step 1 读取，后续步骤复用）

Step 1 执行时从 `~/.config/gerrit-pipeline/config.json` 读取以下信息，后续步骤直接使用，不再重复读取配置文件：

| 信息项 | 来源 | 复用步骤 |
|--------|------|---------|
| `gerrit.user` | config.json | Step 2 兜底、Step 3 |
| `gerrit.http_password` | config.json | Step 2 兜底、Step 3 |
| CR 编号 | Step 1 push 输出 | Step 2、3、4 |
| 项目名称 | Step 1 用户选择 | Step 2、3、4（reviewer/通知匹配） |

#### 环境变量设置

Step 1 完成后，后续步骤调用脚本前，直接用 Step 1 已读取的值设置环境变量，不再重新查找：

```bash
export GERRIT_USER="{Step 1 已读取的 gerrit.user}"
export GERRIT_HTTP_PASSWORD="{Step 1 已读取的 gerrit.http_password}"
```

#### 独立操作例外

当某步骤以独立操作方式触发（非完整流水线）时，无 Step 1 上下文，此时按原有方式从配置文件读取凭据。

---

## Step 1：代码提交

### 1.1 Gerrit 服务器配置

| 项目 | 值 |
|------|---|
| 服务器 | `https://gerrit.auto-link.com.cn` |
| SSH | `ssh://gerrit.auto-link.com.cn:29418` |
| 认证方式 | SSH |
| 远程仓库名 | `autolink` |
| Dashboard | `https://gerrit.auto-link.com.cn/dashboard/self` |

### 1.2 Commit Message 规范

#### 标题格式

```
【类型】【JIRA-ID】概要描述【x/y】
```

- **类型**（必选其一）：`bug` / `change` / `feature`
  - `bug`：缺陷修复
  - `change`：需求变更
  - `feature`：新功能开发
- **JIRA-ID**：JIRA ticket 编号，用 `【】` 包裹，必须在 JIRA 上真实存在。已知前缀：`CHYT1V` / `BAIC` / `KP31` / `CL` / `T1V` / `D01` / `XINCHI` 等
- **概要描述**：简明扼要说明改动内容
- **【x/y】**（多仓库关联提交时必填）：关联提交序号标识，x 为当前提交序号，y 为总笔数，均为正整数。`【】` 为中文方括号。非关联提交时省略

**示例**：
```
# 单笔提交（无关联）
【bug】【CHYT1V-1058】仪表双闪报警灯无提示音
【feature】【CHYT1V-961】Carproperty 新增车辆属性支持

# 多仓库关联提交（3 笔）
【change】【CHYT1V-200】登录流程调整为异步模式【1/3】
【change】【CHYT1V-200】SDK 接口同步更新【2/3】
【change】【CHYT1V-200】sdk_release 版本更新【3/3】
```

#### Body 必填字段

所有字段均为**必填**，Gerrit 门禁会检查前 4 项的最低字数要求。

| 字段 | 最低字数 | 最高字数 | 说明 |
|------|---------|---------|------|
| 【原因分析】 | 8 字 | 50 字 | 概述故障原因或新需求/变更背景，简明扼要 |
| 【解决方案】 | 8 字 | 50 字 | 概述改动方案，简明扼要 |
| 【自测用例】 | 20 字 | 50 字 | 场景 + 操作步骤 + 期望结果 + 实际结果，简明扼要 |
| 【自测方法】 | 4 字 | 50 字 | 验证方式及次数，简明扼要 |
| 【影响范围】 | 8 字 | 50 字 | 受影响的模块或功能范围，简明扼要 |
| 【代码修改量】 | — | 50 字 | 修改的代码行数（估算即可） |
| 【提交项目/分支】 | — | 50 字 | 提交的目标分支名 |
| 【体现版本】 | 自动填当日日期 | 固定格式 | 自动获取当日日期，格式固定为 `After YYYY/M/D`（如 `After 2026/4/30`） |
| 【开发自测视频】（可选） | — | — | 用户选择添加时，内容固定为：`申请豁免，原因：已自测通过，请实车验证` |

#### Change-Id

- 由 `.git/hooks/commit-msg` 钩子**自动生成**，无需手动填写
- commit 时 hook 会自动在 message 末尾追加 `Change-Id: Ixxxxxxx`
- amend 操作时保留原有 Change-Id 即可关联同一 Change

#### 完整 Commit Message 模板

```
【{类型}】【{JIRA-ID}】{概要描述}

【原因分析】{至少8字，描述故障原因或需求背景}
【解决方案】{至少8字，描述改动方案}
【自测用例】{至少20字，场景+操作步骤+期望结果+实际结果}
【自测方法】{至少4字，验证方式及次数}
【影响范围】{受影响的模块/功能}
【代码修改量】{修改行数}
【提交项目/分支】{目标分支}
【体现版本】After {当日日期，格式如 2026/4/30}
（可选，用户选择添加时包含下行）
【开发自测视频】申请豁免，原因：已自测通过，请实车验证
```

> Change-Id 由 hook 自动追加，不要手动写入。

### 1.3 Topic（多仓库关联提交）

当多个仓库的 Change 互相依赖、需要一起合入时，必须使用 Topic 关联。

#### 使用场景

- 多个仓库的代码修改互相依赖，需原子性合入
- 典型场景：APK + SDK、FWK + SOC 等跨仓库联动

#### 命名规则

| 规则 | 说明 |
|------|------|
| 不能包含空格、冒号等特殊字符 | 仅允许字母、数字、下划线 `_`、连字符 `-` |
| 多词连接 | 用下划线或驼峰格式 |
| 必须唯一 | 在 Gerrit 搜索 `topic:xxx` 确认不重复 |

**推荐命名格式**：`模块名_功能_日期`

```
D01_FWK_20250428
D01_SOC_20250428
BAIC_FWK_20250428
Add-collect-log-function_20250428
```

#### 提交顺序要求

1. 按 `【1/y】→【2/y】→...→【y/y】` 的顺序提交
2. **最后一笔（【y/y】）必须最后 push**
3. APK 场景下，`sdk_release` 的提交必须排在最后（如 3 笔关联提交，sdk_release 带【3/3】）
4. commit message 和 topic 必须在本地编辑好再推送

#### 合入规则

- 多笔预编译通过后，**不要再推新的 patchset**
- 必须**全部合入或全部不合**，不能只合一部分

#### 补救措施

如果 push 后发现漏加 topic 或【x/y】标识：
- 可手动将最后一笔提交（如【3/3】）在 Gerrit 上 **Abandon → Restore**
- 重新编辑 commit message 后 amend 推送

#### Topic 名称校验

```bash
# 校验 topic 名称格式（仅允许字母、数字、下划线、连字符）
topic_name="$1"
echo "$topic_name" | grep -qE '^[A-Za-z0-9_-]+$' || echo "ERROR: Topic 名称包含非法字符（仅允许字母、数字、下划线、连字符）"
```

### 1.4 提交前检查（本地预检）

在推送到 Gerrit 之前，按顺序执行以下检查：

#### 编译检查

确认代码能够编译通过。根据项目情况执行对应的构建命令。

#### 单元测试

确认相关模块的单元测试通过。如项目有 `mk_unit_tests_linux.sh` 等脚本，优先使用。

#### Commit Message 格式校验

在 commit 之前或之后，检查 commit message 是否符合规范：

1. **标题**：以 `【bug】`、`【change】` 或 `【feature】` 开头
2. **JIRA-ID**：标题中包含有效的 JIRA ticket 编号
3. **【x/y】标识**（如存在）：x、y 为正整数，x ≤ y，`【】` 为中文方括号
4. **Body 字段完整性**：确认 4 个门禁必检字段均存在且满足最低字数
   - 【原因分析】≥ 8 字
   - 【解决方案】≥ 8 字
   - 【自测用例】≥ 20 字
   - 【自测方法】≥ 4 字
5. **其他必填字段**：确认【影响范围】【代码修改量】【提交项目/分支】【体现版本】存在
6. **体现版本格式**：【体现版本】由执行 Agent 自动填入当日日期，格式固定为 `After YYYY/M/D`（如 `After 2026/4/30`），不接受其他格式
7. **开发自测视频**（可选）：如用户选择添加，确认【开发自测视频】存在且内容为固定值
8. **严格符合模板**：commit message body 只能包含模板中定义的字段，不得有任何模板外的多余行（如 Co-Authored-By、Signed-off-by 等）

**校验脚本（供执行 Agent 内部调用）**：

```bash
# 获取最新 commit message
msg=$(git log -1 --format="%B")

# 检查标题格式（【类型】【JIRA-ID】概要描述）
echo "$msg" | head -1 | grep -qE '^【(bug|change|feature)】【' || echo "ERROR: 标题格式不符"

# 检查 JIRA-ID（已知前缀，需被【】包裹）
echo "$msg" | head -1 | grep -qE '【(CHYT1V|BAIC|KP31|CL|T1V|D01|XINCHI)-[0-9]+】' || echo "ERROR: 缺少 JIRA-ID 或未用【】包裹"

# 检查【x/y】标识格式（如存在）
title=$(echo "$msg" | head -1)
if echo "$title" | grep -qE '【[0-9]+/[0-9]+】'; then
  x=$(echo "$title" | grep -oE '【[0-9]+/[0-9]+】' | grep -oE '[0-9]+' | head -1)
  y=$(echo "$title" | grep -oE '【[0-9]+/[0-9]+】' | grep -oE '[0-9]+' | tail -1)
  [ "$x" -gt 0 ] && [ "$y" -gt 0 ] || echo "ERROR: 【x/y】中 x 和 y 必须为正整数"
  [ "$x" -le "$y" ] || echo "ERROR: 【x/y】中 x($x) 不能大于 y($y)"
fi

# 检查必填字段存在性
for field in "【原因分析】" "【解决方案】" "【自测用例】" "【自测方法】" "【影响范围】" "【代码修改量】" "【提交项目/分支】" "【体现版本】"; do
  echo "$msg" | grep -q "$field" || echo "ERROR: 缺少 $field"
done

# 检查字段字数（最低 + 最高）
check_field_length() {
  local field="$1" min_len="$2" max_len="$3"
  local content=$(echo "$msg" | grep "$field" | sed "s/$field//")
  local len=${#content}
  if [ "$min_len" -gt 0 ] && [ "$len" -lt "$min_len" ]; then
    echo "ERROR: $field 内容不足 ${min_len} 字（当前 ${len} 字）"
  fi
  if [ "$len" -gt "$max_len" ]; then
    echo "ERROR: $field 内容超过 ${max_len} 字（当前 ${len} 字），请简明扼要"
  fi
}
check_field_length "【原因分析】" 8 50
check_field_length "【解决方案】" 8 50
check_field_length "【自测用例】" 20 50
check_field_length "【自测方法】" 4 50
check_field_length "【影响范围】" 8 50
check_field_length "【代码修改量】" 0 50
check_field_length "【提交项目/分支】" 0 50

# 检查【体现版本】格式（必须为 After YYYY/M/D 格式，如 After 2026/4/30）
version_date=$(echo "$msg" | grep "^【体现版本】" | sed 's/^【体现版本】//')
if [ -n "$version_date" ]; then
  echo "$version_date" | grep -qE '^After [0-9]{4}/[0-9]{1,2}/[0-9]{1,2}$' || echo "ERROR: 【体现版本】格式错误，必须为 After YYYY/M/D 格式（如 After 2026/4/30）"
fi

# 检查 body 中是否存在模板外的多余行（标题、空行、已知字段、Change-Id 行除外）
allowed_fields="【原因分析】|【解决方案】|【自测用例】|【自测方法】|【影响范围】|【代码修改量】|【提交项目/分支】|【体现版本】|【开发自测视频】|Change-Id:"
echo "$msg" | tail -n +2 | while IFS= read -r line; do
  [ -z "$line" ] && continue
  echo "$line" | grep -qE "^($allowed_fields)" && continue
  echo "ERROR: commit message 中存在模板外的多余行: $line"
done
```

### 1.5 推送工作流

#### 新建 Change（标准提交）

Reviewer 列表从配置文件 `~/.config/gerrit-pipeline/config.json` 读取。如配置了 `projects`，则根据用户选择的项目名匹配项目专属的 `gerrit.reviewers`，未匹配时 fallback 到顶层 `gerrit.reviewers`。自动拼接为 `%r=reviewer1,r=reviewer2` 格式。

```bash
# 推送到目标分支的 review 队列，自动添加配置中的 reviewer
git push autolink HEAD:refs/for/{目标分支}%r={reviewer1},r={reviewer2}
```

**携带 topic**（多仓库关联提交时必须）：

```bash
# 关联提交必须带 topic
git push autolink HEAD:refs/for/{目标分支}%r={reviewer1},r={reviewer2},topic={topic名称}

# 示例：关联提交 push 到 al_chery-d01_dev2 分支
git push autolink HEAD:refs/for/al_chery-d01_dev2%r=reviewer1,r=reviewer2,topic=D01_FWK_20250428
```

**完整流程**：

1. 确认当前分支和目标分支
2. 如配置了 `projects`，通过 `AskUserQuestion` 或等价交互能力让用户选择本次提交所属项目（只有一个项目时自动选中，无 `projects` 配置时跳过）
3. 读取配置文件中的 `gerrit.reviewers` 列表（根据所选项目匹配专属配置，未选择时使用顶层默认值）
4. 执行提交前检查（编译 + 单元测试）
5. `git add` 暂存变更文件
6. `git commit` 提交（使用规范化的 commit message）
7. **强制校验 commit message**（详见 1.6 节），校验���通过则自动修正并重试，最多 3 次，3 次仍不通过则中止流水线
8. `git push autolink HEAD:refs/for/{目标分支}%r={reviewer1},r={reviewer2}`
9. 输出 Gerrit Change 链接

#### Amend 追加 Patchset

当需要在已有 Change 上追加修改时：

```bash
# 1. 修改代码
# 2. 暂存变更
git add <files>
# 3. amend 提交（保留原 Change-Id）
git commit --amend
# 4. 推送（Change-Id 不变，Gerrit 自动关联为新 patchset）
git push autolink HEAD:refs/for/{目标分支}%r={reviewer1},r={reviewer2}
```

**注意**：
- amend 会保留原 commit message 中的 `Change-Id`，Gerrit 据此识别为同一 Change 的新 patchset
- 如需修改 commit message，amend 时编辑即可
- 推送前确认 `Change-Id` 未被改变

#### Cherry-pick 到其他分支

当需要将当前提交 cherry-pick 到其他分支时：

##### JIRA-ID 确认（必需步骤，不可跳过）

> **Cherry-pick 前必须通过 `AskUserQuestion` 或等价交互能力向用户确认 JIRA-ID，即使原 commit 中已包含 JIRA-ID 也必须确认。此步骤为强制项，不可跳过。**

执行流程：
1. 读取原 commit message 中的 JIRA-ID
2. 通过 `AskUserQuestion` 或等价交互能力向用户展示当前 JIRA-ID 并确认：
   - 选项 1：沿用原 JIRA-ID `【{原JIRA-ID}】`
   - 选项 2：使用新的 JIRA-ID（用户输入新 ID）
3. 用户确认后，将最终确定的 JIRA-ID 用于 cherry-pick 后的 commit message

##### 操作步骤

```bash
# 1. 切换到目标分支
git checkout {目标分支}
# 2. 拉取最新代码
git pull autolink {目标分支}
# 3. cherry-pick 指定 commit
git cherry-pick {commit-hash}
# 4. 如有冲突，解决后 git cherry-pick --continue
# 5. 如用户选择了新 JIRA-ID，amend commit message 替换 JIRA-ID
git commit --amend  # 仅在 JIRA-ID 变更时执行
# 6. 推送到 Gerrit
git push autolink HEAD:refs/for/{目标分支}%r={reviewer1},r={reviewer2}
# 7. 切回原分支
git checkout {原分支}
```

**注意**：
- cherry-pick 会生成新的 commit（新 Change-Id），在 Gerrit 上是独立的 Change
- 如果 cherry-pick 多个 commit，逐个操作并分别推送
- 冲突解决后需确认 commit message 格式仍符合规范
- JIRA-ID 确认必须在 cherry-pick 操作之前完成，确保 push 前 commit message 中的 JIRA-ID 正确

### 1.6 Commit Message 强制校验（校验-修正-重试闭环）

> **本节定义的校验流程为强制步骤，commit 后、push 前必须执行，不可跳过。**

#### 执行时机

在以下所有场景中，**git commit 成功之后、git push 之前**，必须执行本校验流程：

- 标准提交（新建 Change）
- Amend 追加 Patchset
- Cherry-pick 到其他分支
- 多仓库关联提交（每个仓库 commit 后均需校验）

#### 校验流程

```
git commit 完成
      ↓
运行校验脚本（1.4 节中的全部校验项）
      ↓
  校验通过？ ──是──→ 继续 git push
      ↓ 否
展示校验错误给用户
      ↓
执行 Agent 自动修正 commit message
      ↓
git commit --amend（仅修正 message，不改变代码）
      ↓
重新运行校验脚本
      ↓
（循环，最多 3 次）
      ↓
3 次仍不通过 → 中止流水线，向用户报告所有校验错误
```

#### 校验项清单

每次校验必须**逐项检查**以下所有规则（对应 1.4 节校验脚本）：

| # | 校验项 | 判定规则 | 失败严重性 |
|---|--------|---------|-----------|
| 1 | 标题格式 | 以 `【bug】`、`【change】` 或 `【feature】` 开头 | 阻塞 |
| 2 | JIRA-ID | 标题中包含有效 JIRA ticket 编号，用 `【】` 包裹 | 阻塞 |
| 3 | 【x/y】标识 | 如存在，x、y 为正整数，x ≤ y，`【】` 为中文方括号 | 阻塞 |
| 4 | 标题与 body 之间空行 | 标题之后必须有一个空行再接 body | 阻塞 |
| 5 | 【原因分析】 | 存在且 8~50 字 | 阻塞 |
| 6 | 【解决方案】 | 存在且 8~50 字 | 阻塞 |
| 7 | 【自测用例】 | 存在且 20~50 字 | 阻塞 |
| 8 | 【自测方法】 | 存在且 4~50 字 | 阻塞 |
| 9 | 【影响范围】 | 存在且 8~50 字 | 阻塞 |
| 10 | 【代码修改量】 | 存在且 ≤50 字 | 阻塞 |
| 11 | 【提交项目/分支】 | 存在且 ≤50 字 | 阻塞 |
| 12 | 【体现版本】 | 存在且格式为 `After YYYY/M/D`（如 `After 2026/5/2`） | 阻塞 |
| 13 | 【开发自测视频】 | 如存在，内容必须为固定值 | 阻塞 |
| 14 | 无模板外多余行 | body 中不得有 Co-Authored-By、Signed-off-by 等模板外行（Change-Id 行除外） | 阻塞 |
| 15 | 字段顺序 | body 各字段必须按模板定义的顺序排列 | 阻塞 |

#### 自动修正规则

当校验失败时，执行 Agent 按以下规则自动修正，**无需再次询问用户**：

| 错误类型 | 自动修正方式 |
|---------|------------|
| 字段内容不足最低字数 | 根据 `git diff --staged` 重新生成该字段内容，确保达到最低字数 |
| 字段内容超过 50 字上限 | 精简该字段内容至 50 字以内 |
| 缺少必填字段 | 根据 diff 和上下文补充缺失字段 |
| 【体现版本】格式错误 | 替换为当日日期 `After YYYY/M/D` |
| 存在模板外多余行 | 删除多余行（如 Co-Authored-By、Signed-off-by 等） |
| 字段顺序错误 | 按模板定义的顺序重新排列 |
| 标题与 body 之间缺少空行 | 插入空行 |

修正完成后使用 `git commit --amend` 更新 commit message（仅修正 message 内容，不改变已暂存的代码变更），然后重新执行校验。

#### 重试限制

- **最多重试 3 次**（含首次校验共 4 次校验机会）
- 3 次自动修正后仍不通过，**中止流水线**
- 向用户报告：
  1. 当前 commit message 全文
  2. 仍然存在的所有校验错误
  3. 建议用户手动修正后重新触发流水线

#### 校验通过标志

校验脚本输出无任何 `ERROR` 行，即视为校验通过。校验通过后方可执行 `git push`。

### 1.7 交互式辅助流程

> **v1.9.0 交互精简**：本节按"推断优先 + 批量弹窗 + 合并确认"重排。在 Claude Code 中可用 `AskUserQuestion` 将原 9 次以上弹窗压缩到 3-4 屏；其他 Agent 可分多轮提问实现，但不得省略安全红线（JIRA-ID 强制确认 / commit message 最终确认 / Checklist 模板固化 / 责任声明）。

当用户触发提交流程时，执行 Agent 按以下步骤辅助。先确认提交模式，再根据模式进入对应路径。

#### 第一步：确认提交模式（Screen 0）

- 如果用户的触发指令中已明确提交模式（如包含 "amend"、"追加"、"cherry-pick" 等关键词），则视为已确认，**跳过此屏**
- 否则通过 `AskUserQuestion` 或等价交互能力单题询问用户：

  | 选项 | 说明 |
  |------|------|
  | 新建提交 | 创建新 commit，生成新 Change |
  | Amend 追加 | 在已有 Change 上追加 patchset（git commit --amend） |
  | Cherry-pick | 将已有 commit cherry-pick 到其他分支 |

> **不可基于 git 状态自动推断提交模式**：Amend / Cherry-pick / 新建提交的后续字段差异大（如 Amend 不需要"提交类型/概要"），误判代价高，必须由用户显式选择。

确认提交模式后，根据模式进入对应流程：
- **新建提交**：继续第二步（提交范围判定），然后走路径 A / B
- **Amend**：跳过预扫描，直接走路径 C（Amend 流程）
- **Cherry-pick**：跳过预扫描，直接走路径 D（Cherry-pick 流程）

#### 第二步：提交范围判定（显式优先，扫描兜底）

仅在新建提交模式下执行。执行 Agent 必须按以下优先级判定本次进入路径 A / B：

##### 2.1 显式多仓触发词

如果用户触发词中明确包含以下任一关键词，直接进入路径 B（多仓库关联提交）：

- `多仓`
- `多仓库`
- `多仓提交`
- `多仓库提交`
- `关联提交`
- `topic`

此时不进入单仓路径。若用户同时提供了仓库路径，以用户提供的路径作为候选列表；若未提供路径，则进入多仓候选收集流程。

##### 2.2 用户显式提供仓库路径

如果用户在触发 skill 时直接提供了仓库路径地址，**不执行全局扫描**，按路径数量决定路径：

| 用户提供的仓库路径数量 | 自动进入 | 备注 |
|------------------------|----------|------|
| 1 个仓库路径 | 路径 A（单仓库） | 仅在该仓库内提交 |
| ≥2 个仓库路径 | 路径 B（多仓库关联提交） | 这些路径作为多仓候选列表，后续仍需用户确认参与范围和顺序 |

执行 Agent 必须先将相对路径规范化为绝对路径，并校验每个路径是 Git 仓库或位于 Git 仓库内；无法识别的路径必须提示用户修正，不得静默忽略。

##### 2.3 显式单仓触发词

如果用户触发词中明确包含以下任一关键词，直接进入路径 A（单仓库提交），以当前仓库或用户提供的单个仓库路径为提交目标：

- `单仓`
- `单仓库`
- `单仓提交`
- `单仓库提交`
- `只提交当前仓库`
- `仅提交当前仓库`
- `当前仓库提交`

这些关键词必须按字面匹配，不得把普通的 `提交`、`推送`、`代码提交`、`提交代码` 模糊理解为单仓意图。

##### 2.4 意图冲突处理

如果用户同时表达互相冲突的意图（例如同时包含 `单仓` 和 `多仓`，或声明单仓但提供两个及以上仓库路径），执行 Agent 必须暂停并向用户确认提交范围，不得自行选择路径。

##### 2.5 无显式意图、无仓库路径时的兜底策略

仅当用户既未提供仓库路径，也未包含明确单仓 / 多仓触发词时，执行 Agent 按当前目录上下文决定是否扫描。

**当前目录不是 Git 仓库，也不在 Git 仓库内**：

- 不执行全局扫描
- 提示用户提供仓库路径，或切换到目标仓库目录后重新触发

**当前目录是普通单 Git 仓库，且不属于 repo / manifest workspace**：

- 只执行当前仓库 `git status --porcelain`
- 当前仓库无变更：中止并提示无可提交变更
- 当前仓库有变更：进入路径 A（单仓库）

**当前目录位于 repo / manifest workspace 内**：

1. 先定位 workspace 根目录
2. 先检测当前仓库是否有变更
3. 通过 `AskUserQuestion` 或等价交互能力询问提交范围：

   | 选项 | 行为 |
   |------|------|
   | 仅提交当前仓库 | 直接进入路径 A，不扫描整个 workspace |
   | 扫描整个 workspace | 从 workspace 根目录扫描所有脏仓库，再按扫描结果进入路径 A / B |
   | 手动指定仓库路径 | 让用户输入仓库路径，按路径数量进入路径 A / B |

> 默认推荐选项为「仅提交当前仓库」，避免普通提交流程被全局扫描拖慢；当用户确实需要多仓库关联提交时，再选择「扫描整个 workspace」或手动提供路径。

**全局扫描命令**：

```bash
# manifest 管理的工作区
repo forall -c 'if [ -n "$(git status --porcelain)" ]; then echo "$(pwd)"; fi'

# 普通单仓库
git status --porcelain
```

**全局扫描超时策略**：

- 初次扫描超时时间为 **20 秒**
- 20 秒内未完成时，不继续阻塞流程，必须提示用户选择：

  | 选项 | 行为 |
  |------|------|
  | 仅提交当前仓库 | 中止扫描，进入路径 A |
  | 手动指定仓库路径 | 中止扫描，按用户提供路径数量进入路径 A / B |
  | 继续等待 / 重试扫描 | 继续或重新执行全局扫描 |

**扫描结果处理规则**：

| 扫描结果 | 自动进入 | 备注 |
|---------|---------|------|
| 1 个脏仓库 | 路径 A（单仓库） | 不询问"是否多仓库" |
| ≥2 个脏仓库 | 路径 B（多仓库关联提交） | 扫描结果作为 multiSelect 候选项呈现给用户，由用户明确选择参与仓库；不得静默纳入全部脏仓库 |
| 0 个脏仓库 | 报错中止 | 提示用户先暂存或修改文件 |

---

#### 路径 A：非关联提交（单仓库）

**Screen 1（批量收集核心字段）**：Claude Code 优先通过单次 `AskUserQuestion`（最多 4 问/屏）一次性收集；其他 Agent 可用等价结构化表单或连续提问收集：

| 字段 | 来源 / 默认值 | 备注 |
|------|--------------|------|
| **项目**（多项目时） | 配置 `projects` 列表 | 只配置 1 个项目时**自动选中**，本字段不再询问，把名额留给其他 |
| **JIRA-ID**（必需，不可跳过） | 用户输入（可从当前分支名 / 上一笔 commit 推断为推荐项） | v1.8.0 红线 |
| **提交类型** | bug / change / feature | 三选一 |
| **目标分支** | 默认从当前分支推断为推荐项 | 用户可改 |

> Claude Code 中因 `AskUserQuestion` 单屏最多 4 题，超出时（如多项目场景）按"项目 + JIRA + 类型 + 分支"优先级取前 4 项；【开发自测视频】合并到 Screen 2 选项中。其他 Agent 即使可一次收集更多字段，也应保持相同字段优先级和最终确认语义。

**自动生成 Commit Message**（无用户交互）：
1. 分析 `git diff --staged` 的内容
2. 生成各必填字段内容（原因分析、解决方案等）
3. 估算代码修改量
4. 填充提交分支和体现版本

**Screen 2（commit message 预览 + 自测视频开关 + 最终确认）**：Claude Code 使用单次 `AskUserQuestion` 展示 3 选项；其他 Agent 使用等价确认交互：

| 选项 | 行为 |
|------|------|
| 确认推送（含【开发自测视频】） | 末尾追加固定行 `【开发自测视频】申请豁免，原因：已自测通过，请实车验证`，然后进入校验-修正-重试（§1.6.4） → push |
| 确认推送（不含【开发自测视频】） | 不追加自测视频行，进入校验-修正-重试（§1.6.4） → push |
| 需要修改 commit message | 接收用户修改意见 → 重新生成 → 重新展示同屏。**最多 3 轮**，超出后 hand off 给用户手动编辑（参照 §1.6.4 重试上限精神） |

> **§1.6.4 commit-msg 校验-修正-重试闭环在用户"确认推送"之后、`git push` 之前照常执行，不可省略。**

**推送**：
- 使用所选项目对应的 reviewer 列表执行 git push
- 提取 CR 编号

---

#### 路径 B：多仓库关联提交

**Screen 1（关联仓库列表 multiSelect）**：将第二步扫描结果通过 `AskUserQuestion` multiSelect（Claude Code 优化路径）或等价多选交互展示为候选列表，用户必须明确勾选本次需要关联提交的仓库。

提示文案：**请选择本次需要关联提交的仓库；未勾选的仓库不会参与本次提交。点击 Submit 确认**。

> 若用户未选择任何仓库，或只选择 1 个仓库，则中止路径 B 并提示用户重新选择；单仓库提交应走路径 A。

**Screen 2（批量收集核心字段，所有仓库共享）**：Claude Code 优先通过单次 `AskUserQuestion`（最多 4 问/屏）收集；其他 Agent 可用等价连续提问：

| 字段 | 来源 / 默认值 | 备注 |
|------|--------------|------|
| **项目**（多项目时） | 配置 `projects` | 只 1 个项目时自动选中 |
| **JIRA-ID**（必需，不可跳过） | 用户输入 | v1.8.0 红线 |
| **提交类型** | bug / change / feature | 所有仓库共享 |
| **目标分支** | 默认从当前分支推断为推荐项 | 所有仓库共享 |

> Topic 名称采用**自动建议**（格式 `{模块名/项目名}_{JIRA-ID}_{YYYYMMDD}`），不再单独询问，挪到 Screen 3 中可修改。

**自动生成所有仓库 Commit Message**（无用户交互）：
1. 所有仓库共享基础信息（类型、JIRA-ID、概要描述、body 各字段）
2. 每个仓库标题末尾自动追加对应 `【x/y】` 标识
3. 各仓库 body 字段根据各自的 diff 内容分别生成
4. 自动计算提交顺序（涉及 APK 的 sdk_release 仓库自动排到最后）

**Screen 3（合并预览 + 自测视频 + Topic + 顺序确认）**：在同一屏展示：
- 所有仓库的 diff 摘要 + 生成的 commit message
- 自动建议的 Topic 名称（可改）
- 自动计算的提交顺序（可调整）

通过 `AskUserQuestion` 或等价确认交互提供 3 选项：

| 选项 | 行为 |
|------|------|
| 全部确认（含【开发自测视频】） | 所有仓库 commit message 末尾追加自测视频行 → 按顺序逐仓 commit / 校验 / push |
| 全部确认（不含【开发自测视频】） | 不追加自测视频行 → 按顺序逐仓 commit / 校验 / push |
| 需要修改 | 接收用户修改意见（commit message / Topic / 顺序均可改） → 重新生成预览 → 重新展示同屏，最多 3 轮 |

**扫描变更仓库的方法**：

```bash
# 方式一：使用 repo status（推荐，manifest 管理的仓库）
repo status

# 方式二：遍历子目录查找有变更的 git 仓库
repo forall -c 'if [ -n "$(git status --porcelain)" ]; then echo "$(pwd)"; fi'
```

**按顺序依次提交推送**：
1. 按 `【1/y】→【2/y】→...→【y/y】` 的顺序，依次对每个仓库执行：
   - `cd` 到仓库目录
   - `git add` 暂存变更
   - `git commit`（使用对应的 commit message）
   - 本地校验 commit message 格式（§1.6.4 校验-修正-重试闭环照常执行）
   - `git push autolink HEAD:refs/for/{目标分支}%r={reviewer1},r={reviewer2},topic={topic名称}`
   - 提取 CR 编号
2. **最后一笔（【y/y】）最后 push**
3. 任一仓库 push 失败则中止后续仓库，向用户报告**部分成功状态**（哪些 CR 已 push 成功，哪些未执行），不静默重试
4. 全部 push 成功后，汇总所有 CR 编号

**关联提交完成标志**：
- 所有仓库均 push 成功
- 所有 CR 共享同一 topic
- 汇总输出：各仓库的 CR 编号、URL、提交顺序

---

#### 路径 C：Amend 追加 Patchset

> 在已有 Change 上追加修改，保留原 Change-Id，Gerrit 自动关联为新 patchset。完整流水线中 amend 完成后继续执行 Step 2 → 3 → 4。

**信息收集**（通过 `AskUserQuestion` 或等价交互能力）：
1. **JIRA-ID**（必需步骤，不可跳过）：读取当前 HEAD commit message 中的 JIRA-ID，通过结构化确认向用户确认沿用或更换
2. 目标分支（从当前分支推断或询问）

**执行流程**：
1. `git add` 暂存变更文件
2. `git commit --amend`（保留原 Change-Id；如 JIRA-ID 变更则同步修改 commit message）
3. 强制校验 commit message（1.6 节）
4. `git push autolink HEAD:refs/for/{目标分支}%r={reviewer1},r={reviewer2}`
5. 提取 CR 编号（从 push 输出中获取）

**注意**：
- amend 必须保留原 commit message 中的 `Change-Id`，推送前确认未被改变
- 不要使用 `git commit`（无 `--amend`），否则会创建新 Change 而非追加 patchset

---

#### 路径 D：Cherry-pick 到其他分支

> 将已有 commit cherry-pick 到其他分支。完整流水线中 cherry-pick 完成后继续执行 Step 2 → 3 → 4。

**信息收集**（通过 `AskUserQuestion` 或等价交互能力）：
1. **JIRA-ID 确认**（必需步骤，不可跳过）：读取原 commit 的 JIRA-ID，询问沿用或更换
2. 目标分支

**执行流程**：按 1.5 节 Cherry-pick 操作步骤执行。

### 1.8 常用命令速查

| 操作 | 命令 |
|------|------|
| 推送新 Change | `git push autolink HEAD:refs/for/{branch}%r={r1},r={r2}` |
| 推送关联提交（带 topic） | `git push autolink HEAD:refs/for/{branch}%r={r1},r={r2},topic={topic}` |
| amend 后推送 | `git commit --amend && git push autolink HEAD:refs/for/{branch}%r={r1},r={r2}` |
| 查看 Gerrit Dashboard | 浏览器打开 `https://gerrit.auto-link.com.cn/dashboard/self` |
| 查看 Change-Id | `git log -1 --format="%B" \| grep Change-Id` |
| 检查 commit-msg hook | `ls -la .git/hooks/commit-msg` |
| 搜索 topic 是否唯一 | Gerrit 搜索 `topic:{topic名称}` |

### 1.9 注意事项

1. **永远不要 `--no-verify`**：commit-msg hook 负责生成 Change-Id，跳过会导致推送失败
2. **amend vs 新 commit**：修改已推送的 Change 用 amend；新的独立改动用新 commit
3. **force push 禁止**：不要对已推送到 Gerrit 的分支做 force push
4. **敏感文件排除**：不要提交 `.env`、密钥文件、凭证等敏感内容
5. **分批提交**：大改动建议分批提交（在标题末尾标注如 `【1/3】`），每批独立可编译可测试
6. **编译和测试**：推送前必须确保编译通过和单元测试通过
7. **关联提交纪律**：多笔关联提交预编译通过后，不要再推新 patchset；必须全部合入或全部不合

### 本步骤完成标志

- git push 成功，输出中包含 Gerrit Change URL
- 从 push 输出中提取以下关键信息，供后续步骤使用：
  - **CR 编号**：从 URL 中提取（如 `+/1003659` → `1003659`）
  - **Change URL**：完整的 Gerrit Change 链接
  - **提交标题**：commit message 的第一行
  - **目标分支**：push 的目标分支名
  - **项目名称**：用户选择的项目名（如 `D01`），供 Step 4 飞书通知匹配项目配置
- **关联提交场景**：所有仓库均 push 成功，汇总所有 CR 编号。后续步骤（评审、Checklist、飞书通知）对每个 CR 分别执行

### 提取 CR 编号的方法

从 `git push` 输出中匹配：

```
remote:   https://gerrit.auto-link.com.cn/c/.../+/<CR编号> ...
```

使用正则：`\+/(\d+)` 提取 CR 编号。

### 独立操作

触发 `pipeline submit` 时，仅执行本步骤。完成后输出 CR 编号和 URL，不继续后续步骤。

### 失败处理

- 如果 commit 或 push 失败，中止流水线，向用户报告错误
- 不继续执行后续步骤

---

## Step 2：代码评审（调用 enhanced_code_review）

### 前置条件

需要 CR 编号。完整流水线中由 Step 1 提供；独立操作时由用户提供。

### 执行方式

Claude Code 优先通过 Skill tool 调用 `enhanced_code_review`：

```
Skill({ skill: "enhanced_code_review", args: "review CR <CR编号>" })
```

其中 `<CR编号>` 替换为实际编号。其他 Agent 如不支持 Skill tool，应加载 `enhanced_code_review/SKILL.md` 并按其 `review CR <CR编号>` 流程执行，或调用等价的评审脚本链；输出必须与 enhanced_code_review 的评审结论结构等价。

**多仓库关联提交场景**：对 Step 1 产出的每个 CR 依次执行评审，逐个调用上述命令。每个 CR 独立产出评审评分和问题列表。

### 评审范围限制

**仅针对本次修改的代码及与修改点强相关的代码进行评审**，与修改无关的历史代码不在评审范围内：

- ✅ 本次 diff 中新增、修改、删除的代码
- ✅ 与修改点存在直接调用、依赖或逻辑关联的上下文代码
- ❌ diff 上下文中展示但与本次修改无关的历史代码
- ❌ 未修改文件中的既有问题

### 评审结论贴回校验（Pipeline 兜底）

> **本子步骤为强制步骤，不可跳过。** enhanced_code_review 可能因 Gerrit self-review 限制或其他原因未能将评审结论贴回 Gerrit。Pipeline 必须校验并确保评审结论已贴回。

#### 触发条件

enhanced_code_review skill 执行完成后，无论其是否报告贴回成功，Pipeline 均需执行本校验。

#### 校验流程

```
enhanced_code_review 执行完成
      ↓
调用 gerrit_post_review.py --check-only 检查评审结论是否已贴回
      ↓
  已贴回？ ──是──→ 继续 Step 3
      ↓ 否
执行 Agent 将评审结论（cover message）写入临时文件
      ↓
调用 gerrit_post_review.py 贴回评审结论（不带 Code-Review label）
      ↓
  贴回成功？ ──是──→ 继续 Step 3
      ↓ 否
重试（最多 2 次）
      ↓
仍失败 → 中止流水线，向用户报告错误
```

#### 执行方式

**Step 1：检查评审结论是否已贴回**

```bash
cd <skill_dir>/scripts && python3 gerrit_post_review.py \
  --cr <CR编号> \
  --check-only
```

- 退出码 `0`：评审结论已贴回，跳过后续操作
- 退出码 `1`：评审结论未贴回，执行 Step 2

**Step 2：贴回评审结论（不带 Code-Review label）**

执行 Agent 将 enhanced_code_review 产出的评审结论（包含评审评分建议、P0-P3 问题统计、具体问题列表）写入临时文件，然后调用脚本贴回：

```bash
# 方式一：从文件读取评审结论
cd <skill_dir>/scripts && python3 gerrit_post_review.py \
  --cr <CR编号> \
  --review /tmp/review_result.txt

# 方式二：直接传入文本
cd <skill_dir>/scripts && python3 gerrit_post_review.py \
  --cr <CR编号> \
  --review-text "<评审结论文本>"
```

其中 `<skill_dir>` 为本 skill 的安装路径。

#### 评审结论内容要求

由 Pipeline 贴回的评审结论必须包含以下完整信息（与 enhanced_code_review 原始输出一致）：

- 评审评分建议（suggested_score: +1 / 0 / -1）
- P0/P1/P2/P3 问题统计
- 具体问题列表（如有）
- 各维度评审摘要

**禁止**：简化、截断或仅贴部分评审结论。

#### 多仓库关联提交场景

对 Step 1 产出的每个 CR，均需独立执行本校验。任一 CR 的评审结论未能贴回，视为该 CR 的 Step 2 未完成。

### 本步骤完成标志

- 七维评审完成
- **评审结论必须完整展示给用户**（评审评分、P0-P3 问题统计、具体问题列表）
- **评审结论必须贴回到 Gerrit**（cover message + inline comments），这是必需项，不可跳过
- 获取评审评分（+1 / 0 / -1）和发现的问题列表
- **关联提交场景**：所有 CR 均完成评审，每个 CR 的评审结论均需展示并贴回 Gerrit

### 关键输出（供后续步骤使用）

- **评审评分**：suggested_score（+1 / 0 / -1）
- **P0/P1/P2/P3 计数**：各级别问题数量
- **是否有阻塞性问题**：P0 > 0 或 P1 > 0
- **关联提交场景**：每个 CR 各自独立的评审结果

### 独立操作

触发 `pipeline review <CR编号>` 时，仅执行本步骤。如未提供 CR 编号，通过 `AskUserQuestion` 或等价交互能力询问。

### 失败处理

- 如果评审脚本执行失败（如 Gerrit API 不可达），向用户报告错误
- 评审结果本身（如发现 P0 问题）不算失败，流水线继续执行后续步骤

---

## Step 3：合并确认（Checklist + 飞书通知前确认）

> **v1.9.0 合并**：原 Step 3（Checklist 确认贴出）与原 Step 3.5（飞书通知前确认）合并为**单一确认屏**。多仓库场景下，Checklist 固定模板只展示一次，用户统一确认后串行贴回所有 CR。**确认 UI 合并，但执行级故障边界保留**：Checklist 串行贴回 → 全部成功后才发飞书 → 任一失败则中止飞书并报告部分状态。

### ⚠️ 用户确认声明

> **本步骤需要用户人工确认。** 执行 Agent 将 Checklist 模板原样展示给用户、飞书通知卡片预览同屏展示，待用户确认后方可继续执行（贴 Checklist，并在全部成功后进入 Step 4 发飞书）。Checklist 一经贴出即视为提交人已逐项审阅并认可其内容，相关责任由提交人承担。

执行本步骤时，执行 Agent **必须**：

1. **直接输出固定模板**（不经 LLM 生成）：将本文件末尾「Checklist 模板」章节的内容**逐字复制**输出，不做任何推理、改写或重新生成
   - **禁止省略、截断或简化 Checklist 内容**
   - **禁止修改任何检查项的文字描述**
   - **状态标记按模板原样输出**：模板已预填 `✓` / `o` / 空格，执行 Agent 不得清空、修改或重新判定
   - 必须包含模板中的所有 12 项检查项（流程合规 3 项 + 测试验证 4 项 + 平台化 4 项 + 安全合规 1 项）
   - 必须包含评审结论建议的 3 个选项（Approve / Need Info / Request Changes）

2. **多仓库场景**：Checklist 是固定模板，**只展示 1 份 Checklist 预览**；用户确认后，将同一份 Checklist 模板分别贴到 Step 1 产出的每个 CR 中

3. **同屏展示飞书通知预览**：展示即将发送的卡片内容（含目标群、@提交人、@审核人、CR 列表、提交概要等），便于用户判断"门禁是否就绪"

4. **通过 `AskUserQuestion` 或等价交互能力请求用户确认**，问题文案**必须**包含以下责任声明 + 飞书通知就绪 checklist（不论单仓库还是多仓库关联提交，每次确认前都必须展示）：

   ```
   ⚠️ Checklist 一经贴出即视为提交人已逐项审阅并认可其内容，相关责任由提交人承担。
   
   即将执行：
   1. 将上述 Checklist 贴到 Gerrit（{N} 个 CR）
   2. 发送上述飞书通知卡片
   
   请先确认：
   - Gerrit 门禁（prebuild / precheck）已通过或正在进行中
   - 所有关联 Change（若有）均已推送并具备合入条件
   - Reviewer 已准备好进行评审
   ```

   选项：

   | 选项 | 行为 |
   |------|------|
   | 全部确认（贴 Checklist + 发飞书） | 串行贴所有 CR 的 Checklist → 全部成功后发送飞书通知 |
   | 暂不发送飞书（仅贴 Checklist） | 串行贴所有 CR 的 Checklist，**不发送飞书**；用户可稍后用 `pipeline notify` 手动补发 |

5. 用户确认后才调用脚本贴到 Gerrit。Checklist 模板固定不可修改，因此本步骤不提供"修改 Checklist"选项

> **性能说明**：Checklist 模板是固定文本，执行 Agent 应直接复制输出，不需要逐项"分析"或"生成"。Claude Code 中这能显著减少 LLM 推理耗时，其他 Agent 也应保持同样策略。

### 执行级故障边界（关键）

合并的是**确认 UI**，不是执行流程。执行时**仍保持顺序与故障边界**：

```
用户选择"全部确认"
      ↓
按顺序串行贴 N 个 CR 的 Checklist
  （每个 CR 调用 gerrit_post_checklist.py，失败立即中止后续）
      ↓
  全部 N 个成功？ ──否──→ 中止飞书发送
      ↓ 是                  报告："M/N 个 Checklist 已成功贴回，
   调用 feishu_notify.py        飞书未发送。可用 `pipeline notify`
      ↓                          手动补发飞书通知。"
   飞书发送成功 / 失败 →
   按 Step 4 失败处理策略
```

**关键原则**：
- Checklist 贴失败 → **绝不**发送飞书（保护 v1.5.0 设立的"门禁通过后才发通知"语义）
- 飞书发送失败 → 不回滚 Checklist（已贴的 Checklist 不需要回滚）
- 任何阶段失败 → 显式向用户报告**已完成的步骤** + **未完成的步骤** + **手动补救命令**

### 前置条件

需要 CR 编号。完整流水线中由 Step 1 提供；独立操作时由用户提供。

**多仓库关联提交场景**：对 Step 1 产出的全部 CR **共一次确认**，但 Checklist 固定模板只预览一次；执行级仍逐 CR 串行贴回。

### 执行方式

#### 1. 贴 Checklist（逐 CR 串行）

使用 `gerrit-pipeline/scripts/gerrit_post_checklist.py` 将 Checklist 贴到 Gerrit：

```bash
# 方式一：从文件读取 Checklist
cd <skill_dir>/scripts && python3 gerrit_post_checklist.py \
  --cr <CR编号> \
  --rev <revision_hash> \
  --checklist /tmp/checklist.txt

# 方式二：直接传入 Checklist 文本
cd <skill_dir>/scripts && python3 gerrit_post_checklist.py \
  --cr <CR编号> \
  --checklist-text "<Checklist 内容>"
```

执行 Agent 先将填好的 Checklist 写入临时文件，再调用脚本贴到 Gerrit。

#### 2. 发送飞书通知

Checklist 全部成功贴回后，调用 `feishu_notify.py`（详见 Step 4 章节）。

### ⚠️ 评审结论 vs Checklist — 概念区分

**评审结论**和 **Checklist** 是两个完全独立的概念，**严禁混淆或合并**：

| | 评审结论（Step 2 产出） | Checklist（Step 3 产出） |
|---|---|---|
| **来源** | Step 2 代码评审的输出 | Step 3 独立的检查清单 |
| **内容** | 代码评审的评分（+1/0/-1）和问题统计（P0-P3） | 12 项合规检查 + 评审结论建议 |
| **作用** | 评价代码质量 | 确认流程合规、测试验证、平台化、安全合规 |
| **贴到 Gerrit** | **必需**，以评审评论形式贴出 | **必需**，以 Checklist 评论形式贴出 |
| **展示给用户** | **必需**，完整展示评审结论 | **必需**，完整展示全部 12 项 |
| **是否可修改** | 根据代码评审结果生成 | **完全固化，不可修改（包括状态标注）** |

**关键原则**：
1. **评审结论和 Checklist 都是必需项**，两者都必须展示给用户并贴回 Gerrit，缺一不可
2. **Step 2 的评审结论不能替代 Step 3 的 Checklist**
3. **Step 3 的 Checklist 不能省略或简化为评审结论**
4. **Checklist 完全按模板原样输出**，执行 Agent 不可修改任何内容，包括检查项文字、状态标注、评审结论建议选项

Checklist 模板中的"评审结论建议"（Approve / Need Info / Request Changes）是 Checklist 自身的一部分，不等同于 Step 2 的评审结论。

### Checklist 完全固化规则

**Checklist 的全部内容完全固化，执行 Agent 必须严格按模板原样输出，不可做任何修改**：

- ❌ **禁止做**：
  - 修改、清空或重新判定模板中的预填状态（`✓` / `o` / 空格）— 状态标记按模板原样输出
  - 修改检查项的标题或描述文字
  - 修改评审结论建议的选项文字
  - 增加或删除检查项
  - 根据评审结果调整任何内容
  - 将评审结论的内容插入到 Checklist 中
  - 用评审结论替代 Checklist

Checklist 的状态标注（`✓` / `o`）和评审结论建议的预选已在模板中固化，执行 Agent 直接原样输出，不参与判定。如人工 reviewer 在 Gerrit 上需要调整某项状态，由 reviewer 自行修改。

### 独立操作

- 触发 `pipeline checklist <CR编号>` 时，仅执行 Checklist 贴出（不发飞书）。执行 Agent 将 Checklist 模板原样贴出，不做任何标注或修改
- 触发 `pipeline notify` / `飞书通知` 时，仅发送飞书通知（不贴 Checklist），视为用户已自行确认门禁，跳过合并确认屏

### 本步骤完成标志

- **Checklist 部分**：所有 CR 的 Gerrit API 均返回 200，Checklist 已成功贴到 CR 评论中
- **飞书通知部分**：飞书 API 返回成功（卡片已送达目标群）
- **部分成功**：明确向用户报告哪些子步骤已完成 / 未完成 / 如何补救

---

## Step 4：飞书通知

### 前置条件

1. 配置文件 `~/.config/gerrit-pipeline/config.json` 已初始化（含 chat_id 和 at_members）
2. 需要 CR 信息和评审结果。完整流水线中由前序步骤提供；独立操作时由用户提供或从 Gerrit 获取。

### 首次使用引导

当用户输入 `配置 gerrit-pipeline` 或配置文件不存在时，执行 Agent 按以下流程引导用户完成全部配置。Claude Code 中推荐使用结构化问答一次完成；其他 Agent 可分步询问，但最终配置文件结构必须一致。

#### 第一阶段：基础配置

通过 `AskUserQuestion` 或等价交互能力逐步收集以下信息：

1. **Gerrit 用户名**
2. **Gerrit HTTP 密码**（在 Gerrit Settings → HTTP Credentials 中生成）
3. **默认 Reviewer 列表**（逗号分隔）
4. **飞书群 chat_id**（目标通知群的 ID）
5. **提交人邮箱**（用于查询提交人的飞书 open_id，通知卡片中 @提交人）
6. **@mention 审核人邮箱**（逗号分隔）

收集完成后，执行 Agent 调用脚本自动查询飞书 open_id 并保存配置：

```bash
cd <skill_dir>/scripts

# 初始化基础配置
python3 pipeline_config.py init

# 查询提交人 open_id
python3 pipeline_config.py lookup-users --emails "submitter@auto-link.com.cn"

# 查询审核人 open_id 并保存
python3 pipeline_config.py lookup-users \
  --emails "user1@auto-link.com.cn,user2@auto-link.com.cn" --save
```

#### 第二阶段：按项目配置（可选）

基础配置完成后，执行 Agent 主动询问用户：

> 你是否负责多个项目，需要按项目区分飞书通知群、审核人或 Reviewer？

**选项**（通过 `AskUserQuestion` 或等价交互能力展示）：

| 选项 | 行为 |
|------|------|
| 需要，配置项目 | 进入项目配置流程 |
| 不需要，使用默认配置即可 | 跳过，配置完成 |

如果用户选择「需要」，执行 Agent 循环收集每个项目的配置：

1. **项目名称**（如 `D01`、`BAIC`）
2. **项目专属飞书群 chat_id**（不填则继承顶层默认）
3. **项目专属 Reviewer 列表**（不填则继承顶层默认）
4. **项目专属 @mention 审核人邮箱**（不填则继承顶层默认）

每个项目收集完成后调用：

```bash
python3 pipeline_config.py add-project \
  --name "D01" \
  --chat-id "oc_xxx" \
  --reviewers "reviewer1,reviewer2" \
  --at-emails "user1@auto-link.com.cn,user2@auto-link.com.cn"
```

然后询问「是否继续添加其他项目」，用户选择「否」时结束配置流程。

#### 查看与管理配置

```bash
# 查看当前完整配置
python3 pipeline_config.py show

# 查看所有项目配置
python3 pipeline_config.py list-projects

# 删除项目配置
python3 pipeline_config.py remove-project --name "D01"
```

配置 `projects` 后，Pipeline 在 Step 1 中会通过 `AskUserQuestion` 或等价交互能力让用户选择本次提交所属项目，匹配的项目配置自动覆盖顶层默认值。未配置 `projects` 时使用顶层默认配置，行为与单项目场景完全一致。

### 执行方式

调用 `gerrit-pipeline/scripts/feishu_notify.py` 发送飞书群消息：

```bash
# 单仓库提交
cd <skill_dir>/scripts && python3 feishu_notify.py \
  --cr <CR编号> \
  --url "<Gerrit Change URL>" \
  --branch <���标分支> \
  --subject "<提交标题>" \
  --project "<项目名称>" \
  --score <评审评分> \
  --p0 <P0数> --p1 <P1数> --p2 <P2数> --p3 <P3数> \
  --checklist <pass|warn|fail>

# 多仓库关联提交（增加 --topic 参数，一次性汇总所有 CR）
cd <skill_dir>/scripts && python3 feishu_notify.py \
  --topic <Topic名称> \
  --cr <CR编号1>,<CR编号2>,... \
  --url "<URL1>,<URL2>,..." \
  --branch <目标分支> \
  --subject "<提交标题>" \
  --project "<项目名称>" \
  --score <最低评审评分> \
  --p0 <P0总数> --p1 <P1总数> --p2 <P2总数> --p3 <P3总数> \
  --checklist <pass|warn|fail>
```

其中 `<skill_dir>` 为本 skill 的安装路径；Claude Code 默认通常为 `~/.claude/skills/gerrit-pipeline`，其他 Agent 使用各自的 skill/插件安装目录。`<项目名称>` 为 Step 1 中用户选择的项目名（如 `D01`）。

脚本根据 `--project` 参数精确匹配 `~/.config/gerrit-pipeline/config.json` 中 `projects` 的 key，使用对应的项目专属配置（chat_id、at_members），未匹配或未传 `--project` 时使用顶层默认配置。

### 参数说明

| 参数 | 必填 | 说明 | 来源 |
|------|------|------|------|
| `--cr` | 是 | CR 编号 | Step 1 输出 |
| `--url` | 是 | Gerrit Change URL | Step 1 输出 |
| `--branch` | 否 | 目标分支（默认 al_dev） | Step 1 输出 |
| `--subject` | 是 | 提交标题，必须与 commit message 第一行完全一致，不得改写、压缩或替换为概要描述 | Step 1 输出 |
| `--score` | 否 | 评审评分 -1/0/1（默认 1） | Step 2 输出 |
| `--p0` ~ `--p3` | 否 | 各级别问题数（默认 0） | Step 2 输出 |
| `--checklist` | 否 | Checklist 状态 pass/warn/fail（默认 pass） | Step 3 输出 |
| `--project` | 否 | 项目名称（如 `D01`），匹配项目专属的 chat_id 和 at_members | Step 1 输出 |
| `--topic` | 否 | Topic 名称（多仓库关联提交时必填） | Step 1 输出 |
| `--repos` | 否 | 各 CR 对应仓库名，逗号分隔（多仓库时必填，与 --cr 一一对应） | Step 1 输出 |
| `--chat-id` | 否 | 飞书群 ID（覆盖配置文件中的值） | — |
| `--dry` | 否 | 仅预览不发送 | — |

### 配置文件

位置：`~/.config/gerrit-pipeline/config.json`（用户私有，不随 skill 分发）

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
      {"name": "审核人A", "open_id": "ou_xxxxxxxx"},
      {"name": "审核人B", "open_id": "ou_xxxxxxxx"}
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

**配置项说明**：

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

**projects 匹配规则**：
- `projects` 为可选字段，不配置时所有项目使用顶层默认配置（向后兼容）
- key 为项目名称（如 `D01`、`BAIC`），由用户在 Step 1 交互时选择
- value 中的 `gerrit` 和 `feishu` 字段**覆盖**顶层对应字段，未配置的字段 fallback 到顶层
- 同一仓库可属于多个项目，每次提交时由用户选择当前所属项目
- 只有一个项目时自动选中，无 `projects` 配置时跳过选择

**项目配置管理命令**：

```bash
# 添加或更新项目配置
cd <skill_dir>/scripts && python3 pipeline_config.py add-project \
  --name "D01" \
  --chat-id "oc_xxx" \
  --reviewers "reviewer1,reviewer2" \
  --at-emails "user1@auto-link.com.cn,user2@auto-link.com.cn"

# 列出所有项目配置
python3 pipeline_config.py list-projects

# 删除项目配置
python3 pipeline_config.py remove-project --name "D01"
```

### 飞书消息格式

发送 interactive card（卡片消息）。

#### 单仓库提交卡片

- **标题**：Gerrit Pipeline 通知（颜色随评审结果变化：绿/橙/红）
- **提交概要**：以链接形式展示，点击跳转到 Gerrit Change URL；显示文本必须与 commit message 第一行完全一致
- **CR 编号** + **分支**
- **提交人** + **提交日期**
- **评审评分** + **问题统计**
- **Checklist**
- **审核人**：@mention 配置的成员（根据项目配置匹配）

#### 多仓库关联提交卡片

当传入 `--topic` 参数时，使用多仓库卡片格式：

- **标题**：Gerrit Pipeline 通知 — 关联提交（颜色随最低评审评分变化）
- **提交概要**：以链接形式展示，点击跳转到 Gerrit Topic 搜索页；显示文本必须来自 Step 1 传入的 commit message 标题，不得改写为概要描述
- **Topic** + **分支**
- **提交人** + **提交日期**
- **评审评分** + **问题统计**
- **Checklist**
- **关联 CR 列表**：每个 CR 一行，显示仓库名 + CR 编号（可点击跳转）
- **审核人**：@mention 配置的成员（根据项目配置匹配）

### 飞书应用权限

脚本已内置公共飞书应用凭证，无需设置环境变量。

飞书应用需开通权限：
- `im:message:send_as_bot` — 发送群消息
- `contact:user.base:readonly` — 查询用户 open_id

机器人需已加入目标飞书群。

### 独立操作

触发 `pipeline notify` 或 `飞书通知` 时，仅执行本步骤。通过 `AskUserQuestion` 或等价交互能力收集缺少的 CR 信息。

### 本步骤完成标志

- 飞书 API 返回成功（`code: 0`）
- 消息已送达目标群

### 失败处理

- 如飞书应用权限不足，提示用户联系管理员开通 `im:message:send_as_bot` 权限
- 飞书通知失败不影响前序步骤的结果（代码已提交、评审已贴出）

---

## Checklist 模板

以下为固化的 AutoLink Code Review Checklist v2.0 模板。**此模板不可变更**，执行 Agent 必须严格按照以下模板输出，不得增删、修改任何检查项、分类、标题、说明文字或格式结构：

```markdown
### ✅ AutoLink Code Review Checklist v2.0
*适用于Gerrit评审 | AI已完成预审的精简版 | 推荐在每项前打 `✓` 或`x` 或添加评论说明，然后复制粘贴在Gerrit评论中*
> **说明**：此Checklist用于AI本地评审通过后的人工评审阶段。AI已自动检查编码风格、命名规范、
> 编译冲突、提交信息等8项，人工只需聚焦以下12项。若某项不适用（`若有`或`可选`），请标注 `o`。

---

#### 📎 流程合规
- [✓] **任务关联**：填写有效的JIRA任务或BUG编号，非关联任务不能反复用同一个JIRA单
- [✓] **分支关联**：需要提交的分支（如release分支）都已Cherry pick（若有）
- [o] **提交关联**：拉齐有关联或依赖的相关方代码提交，并关联了同一个Topic（若有）

#### 🧪 测试验证
- [✓] **功能测试**：预期功能或问题缺陷的测试验证通过，测试报告已提交到Jira单
- [✓] **回归测试**：最小自测清单测试验证通过，测试报告已提交到Jira单
- [✓] **集成测试**：全量的接口集成测试验证通过，测试报告已提交到Jira单（可选）
- [o] **单元测试**：覆盖率满足该模块测试等级要求且测试通过，测试报告已提交到Jira单（可选）

#### 🧱 平台化
- [✓] **接口定义**：对外接口定义简洁明了，且可跨项目、跨平台复用，文档更新匹配（若有）
- [✓] **接口发布**：对外接口更新时，重新生成接口文档和SDK包给到相关方（若有）
- [✓] **可配置化**：特定项目需求实现配置化，相关配置参数已在文档或清单中已更新
- [o] **技术债**：若暂时达不到平台化要求，需要登记到技术债务清单（若有）

#### 🔐 安全合规
- [✓] **开源合规**：所使用开源组件，符合其版权协议要求，不存在法律风险

---

### 📝 评审结论建议
- [✓] ✅ **Approve**（满足所有关键项，AI预审无高风险问题）
- [ ] ⚠️ **Need Info**（需补充信息后决定）
- [ ] ❌ **Request Changes**（需修改后重新提交）
```

> **执行 Agent 必须严格按上述模板原样输出（含预填的 `✓` / `o` 状态标记），不得修改任何文字或重新判定状态。** 如人工 reviewer 在 Gerrit 上需要调整某项状态，由 reviewer 自行修改。

---

## 流水线完成报告

四步全部完成后，向用户输出简报。

### 单仓库提交

```
## Gerrit Pipeline 完成

| 步骤 | 状态 | 详情 |
|------|------|------|
| Step 1: 代码提交 | ✅ | CR <编号>，分支: <分支名> |
| Step 2: 代码评审 | ✅ | 评分: +1，P0=0 P1=0 P2=0 P3=1 |
| Step 3: Checklist | ✅ | 已贴到 Gerrit |
| Step 4: 飞书通知 | ✅ | 已发送到群 |

🔗 Gerrit Change: <URL>
```

### 多仓库关联提交

```
## Gerrit Pipeline 完成（关联提交）

**Topic**: <Topic名称>

| 仓库 | CR | 评审评分 | 问题统计 | Checklist |
|------|-----|---------|---------|-----------|
| <仓库1> | [<CR1>](<URL1>) | +1 | P0=0 P1=0 P2=0 P3=0 | ✅ |
| <仓库2> | [<CR2>](<URL2>) | +1 | P0=0 P1=0 P2=1 P3=0 | ✅ |
| <仓库3> | [<CR3>](<URL3>) | +1 | P0=0 P1=0 P2=0 P3=1 | ✅ |

| 步骤 | 状态 |
|------|------|
| Step 1: 代码提交 | ✅ 共 <n> 个仓库 |
| Step 2: 代码评审 | ✅ 最低评分: +1 |
| Step 3: Checklist | ✅ 已贴到 Gerrit |
| Step 4: 飞书通知 | ✅ 已发送到群 |
```

---

## 注意事项

1. **顺序不可调换**：完整流水线必须按 Step 1 → 2 → 3 → 4 顺序执行；v1.9.0 起 Step 3 吞并的是原 Step 3.5 的确认 UI，不是 Step 4 的执行职责
2. **CR 编号传递**：Step 1 的输出是后续所有步骤的输入，务必正确提取
3. **Self-review 限制**：Gerrit 禁止对自己的 CR 打分，评审评论会以不带 Code-Review label 的方式贴出
4. **Checklist 模板固化**：执行 Agent 按模板原样输出预填状态，不得依据评审结果自动改写；人工 reviewer 如需调整，可在 Gerrit 上修改
5. **失败中止**：Step 1 失败则整个流水线中止；Step 2 失败不影响进入 Step 3；Step 3 任一 Checklist 贴回失败则中止 Step 4；Step 4 失败不回滚已完成的 Checklist
6. **飞书通知**：Step 4 使用内置公共飞书应用，无需额外配置凭证
7. **独立操作**：每步可单独触发，执行 Agent 会收集缺少的必要信息
8. **外部依赖**：Step 2（代码评审）依赖 enhanced_code_review skill，需同步安装；Step 1/3/4 为内置能力，无外部依赖

---

## 打包发版流程

### 流程 A：飞书 zip 手动分发

完整发版流程只包含本地校验与 zip 产物生成，**不包含飞书 API 上传**。如需更新飞书文档或上传 zip 文件，由维护者在本地产物生成后手动完成。

对应飞书使用手册：https://t83dfrspj4.feishu.cn/wiki/Tzq1wRg5biiaCLkcx2gcgcb6nO1

执行打包前必须先清空仓库根目录下的 `release/` 目录，再生成当前版本 zip 包，确保 `release/` 中只保留本次发布产物：

```bash
python3 -m py_compile \
  gerrit-pipeline/scripts/feishu_notify.py \
  gerrit-pipeline/scripts/gerrit_post_checklist.py \
  gerrit-pipeline/scripts/gerrit_post_review.py \
  gerrit-pipeline/scripts/pipeline_config.py

mkdir -p release
find release -mindepth 1 -maxdepth 1 -type f -delete
zip -q release/gerrit-pipeline-v1.9.4.zip \
  gerrit-pipeline/README.md \
  gerrit-pipeline/SKILL.md \
  gerrit-pipeline/skill.json \
  gerrit-pipeline/.skillpackignore \
  gerrit-pipeline/scripts/pipeline_config.py \
  gerrit-pipeline/scripts/feishu_notify.py \
  gerrit-pipeline/scripts/gerrit_post_review.py \
  gerrit-pipeline/scripts/gerrit_post_checklist.py

unzip -l release/gerrit-pipeline-v1.9.4.zip
sha256sum release/gerrit-pipeline-v1.9.4.zip

git status --short
git add -A
git commit -m "release: gerrit-pipeline v1.9.4"
git push origin "$(git branch --show-current)"
```

其中 `git commit` / `git push` 是完整发版流程的最后一步，必须在本地文档、飞书文档和 zip 产物都确认完成后执行。

### 流程 B：SkillPack 发布

SkillPack 发布使用 `skill.json` 作为版本与元数据 SOT。当前发布的 `platform` 为 `claude-code`；Her、Cursor、Codex 和通用 agent 兼容性写入 `description` 与 `tags`，后续如需对应端上架需从对应客户端单独发布。发布包必须由 SkillPack 客户端生成 tar.gz，包根目录直接包含 `SKILL.md`、`skill.json`、`README.md` 和 `scripts/`，不得带 `gerrit-pipeline/` 目录前缀。

```bash
python3 -m py_compile \
  gerrit-pipeline/scripts/feishu_notify.py \
  gerrit-pipeline/scripts/gerrit_post_checklist.py \
  gerrit-pipeline/scripts/gerrit_post_review.py \
  gerrit-pipeline/scripts/pipeline_config.py

export SKILLPACK_SKILLS_ROOT="$(pwd)"

# 预检打包结构：tarball 根目录必须直接包含 SKILL.md 与 skill.json
bash ~/.openclaw/workspace/skills/skillpack-client/scripts/pack-skill.sh \
  gerrit-pipeline \
  --skills-root "$SKILLPACK_SKILLS_ROOT"

# 正式发布：wrapper 会依次执行 telemetry pre、SkillPack lint、publish、telemetry post
bash ~/.openclaw/workspace/skills/skillpack-client/scripts/publish-with-telemetry.sh \
  gerrit-pipeline \
  --changelog "gerrit-pipeline v1.9.4"

git status --short
git add -A
git commit -m "release: gerrit-pipeline v1.9.4"
git push origin "$(git branch --show-current)"
```

流程 B 不生成飞书 zip，也不通过飞书 API 上传文件；它只负责通过 SkillPack 发布 skill 版本。`git commit` / `git push` 仍是流程 B 的最后一步，必须在 SkillPack lint / publish 成功后执行。

---

## 版本历史

### v1.9.4（2026/5/25）

1. **Claude Code 通道发布**：将 `skill.json.platform` 切换为 `claude-code`，通过 SkillPack 重新发布 Claude Code 通道版本
2. **兼容声明收敛**：Her、Cursor、Codex 和通用 agent 兼容性保留在 `description` 与 `tags` 中，不再写入 SkillPack 单平台字段

### v1.9.3（2026/5/25）

1. **SkillPack 兼容适配**：新增 `skill.json` 作为版本与元数据 SOT，补齐 `trigger_keywords`、`requires`、`eval_cases`、`changelog` 等发布字段
2. **发布包控制**：新增 `.skillpackignore`，避免 `release/`、`__pycache__`、`.source.json` 等非分发内容进入 SkillPack 包
3. **多 Agent 兼容声明**：当前发布的 `platform` 为 `claude-code`；Her、Cursor、Codex 和通用 agent 兼容性写入 `description` 与 `tags`，后续如需对应端上架需从对应客户端单独发布
4. **发版流程拆分**：保留流程 A（飞书 zip 手动分发），新增流程 B（SkillPack lint / 打包 / 发布）；README 与飞书文档仅保留简要说明，具体执行命令保留在本文件

### v1.9.2（2026/5/25）

1. **提交范围判定重构**：新建提交从“预扫描自动判路”调整为“显式意图优先，扫描兜底”；`多仓`、`关联提交`、`topic` 等关键词直接进入路径 B，显式仓库路径按数量判定单仓 / 多仓，`单仓`、`仅提交当前仓库` 等关键词直接进入路径 A
2. **全局扫描收敛**：无显式意图时，普通 Git 仓库只检查当前仓库；repo / manifest workspace 先让用户选择仅当前仓库、扫描整个 workspace 或手动指定仓库路径，并为全局扫描增加 20 秒超时后的范围选择
3. **飞书通知标题保真**：`--subject` 必须与 commit message 第一行完全一致，单仓与多仓通知卡片的提交概要显示文本不得改写为概要描述
4. **Markdown 链接安全**：飞书卡片构造链接时转义提交标题中的 `\`、`[`、`]`，避免特殊字符破坏 `lark_md` 链接格式
5. **发版流程固化**：完整发版流程只生成本地 zip 产物，不包含飞书 API 上传；生成新产物前必须先清空 `release/` 目录；流程最后提交并推送当前仓库全部改动
6. **飞书文档链接固化**：在发版流程中固定记录 gerrit-pipeline 使用手册链接，避免后续遗漏块级更新

### v1.9.1（2026/5/21）

1. **Agent Neutral 通用性**：新增运行时兼容模型，明确 Claude Code 是推荐运行时，其他 Agent 可通过等价交互能力和脚本调用兼容执行
2. **保留 Claude Code 优势**：斜杠命令、`AskUserQuestion`、multiSelect、Skill tool 调用作为 Claude Code 优化路径保留，不削弱现有使用体验
3. **交互抽象统一**：将 JIRA 确认、项目选择、Checklist 责任声明等步骤从 Claude 专属表述调整为 `AskUserQuestion` 或等价交互能力，安全红线不变

### v1.9.0（2026/5/21）

1. **确认 UI 合并**：原 Step 3（Checklist 确认贴出）与原 Step 3.5（飞书通知前确认）合并为单一确认屏；同屏展示 Checklist 预览、飞书通知卡片预览和责任声明
2. **交互压缩**：新建提交流程不再单独询问"是否多仓库关联提交"，改为预扫描脏仓库后自动判定 Path A / B；提交类型、概要描述、目标分支、开发自测视频改为批量收集
3. **多仓库确认策略调整**：多仓库关联提交只展示一次固定 Checklist 预览并统一确认，但执行级仍保持逐 CR 串行贴回
4. **故障边界明确**：任一 Checklist 贴回失败则中止飞书发送；飞书发送失败不回滚已贴出的 Checklist，并要求向用户报告已完成 / 未完成 / 补救命令

### v1.8.3（2026/5/14）

1. **飞书通知卡片 footer 显示版本号**：单仓库与多仓库关联提交两种卡片底部 note 由「由 Gerrit Pipeline 自动发送」改为「由 Gerrit Pipeline v{版本号} 自动发送」
2. **版本号动态解析**：`feishu_notify.py` 启动时从同目录上层 `README.md` 头部版本行解析，发版时只需改 README 一处，footer 自动同步；找不到 README 时 fallback 为 `unknown`，不影响通知发送

### v1.8.2（2026/5/14）

1. **Checklist 模板预填状态**：12 项检查项中 9 项预填 `[✓]`、3 项可选项预填 `[o]`；评审结论建议预选 `[✓] Approve`。Step 3 由 Claude 直接复制模板输出（含预填状态），不再贴空白模板，避免 LLM 重新判定造成的耗时和勾选丢失
2. **规则措辞同步调整**：原"禁止标注状态（✓/x/o），保持空格"改为"按模板原样输出（含预填状态），不得清空或重新判定"；状态调整由人工 reviewer 在 Gerrit 上进行
3. **Step 3 性能优化提示**：明确 Checklist 是固定文本，应直接复制输出而非"分析/生成"，显著减少本步骤推理耗时

### v1.8.1（2026/5/6）

1. **【影响范围】字段最低字数修正**：从无要求改为 8 字，与 commit message 模板规范对齐（字段规格表、校验脚本、Checklist 校验表三处同步修正）

### v1.8.0（2026/5/5）

1. **JIRA-ID 确认强制化**：所有提交场景（单仓库、多仓库关联、Cherry-pick）中 JIRA-ID 确认为必需步骤，必须通过 AskUserQuestion 向用户确认，不可自行推断或省略
2. **完整流水线支持 Amend / Cherry-pick 模式**：1.7 节交互式辅助流程新增"第一步：确认提交模式"（新建 / Amend / Cherry-pick），新增路径 C（Amend 追加 Patchset）和路径 D（Cherry-pick），完整流水线不再只走新建 commit 路径
3. **Gerrit 凭据上下文传递**：Step 1 读取的 `gerrit.user` / `gerrit.http_password` / CR 编号 / 项目名称在后续步骤直接复用，禁止重复查找配置文件；独立操作时按原有方式读取
4. **Checklist 完全固化（不可标注）**：Claude 不再标注状态（✓/x/o），不再修改任何检查项文字或评审结论建议选项，完全按模板原样输出；所有状态标注由人工 reviewer 在 Gerrit 上完成
5. **飞书通知卡片新增"提交日期"字段**：单仓库和多仓库卡片均新增提交日期（`YYYY-MM-DD HH:MM`），自动取脚本执行时的本地时间
6. **流水线步骤编号修正**：补全 Step 3.5（通知前确认），流水线顺序描述改为 `Step 1 → 2 → 3 → 3.5 → 4`

### v1.7.0（2026/5/3）

1. **按项目差异化配置**：新增 `projects` 配置字段，不同项目可指定专属飞书通知群、@mention 审核人和 Gerrit Reviewer；Pipeline Step 1 中通过 AskUserQuestion 让用户选择当前所属项目，自动匹配项目配置覆盖顶层默认值，向后兼容
2. **评审结论贴回兜底**：Step 2 完成后自动校验评审结论是否已贴回 Gerrit，未贴回时由 pipeline 调用 `gerrit_post_review.py` 兜底执行（处理 self-review 场景）
3. **飞书通知卡片调整**：提交概要移至卡片最上方，以可点击链接形式展示（单仓库跳转 Change URL，多仓库跳转 Topic 搜索页）
4. **配置交互优化**：`配置 gerrit-pipeline` 时，基础配置完成后自动询问是否需要按项目配置，引导用户循环添加项目专属配置
5. **新增脚本 `gerrit_post_review.py`**：将评审结论贴到 Gerrit CR 评论（不带 Code-Review label），支持 `--check-only` 检查模式

### v1.6.4（2026/5/2）

1. **Commit Message 强制校验（校验-修正-重试闭环）**：git commit 后、git push 前新增强制校验步骤，运行完整校验脚本逐项检查 15 项规则；校验失败时 Claude 自动修正并 amend，最多重试 3 次，仍不通过则中止流水线
2. **触发词说明**：明确自然语言触发词依赖 AI 语义匹配、无法保证 100% 命中，推荐使用 `/gerrit-pipeline` 斜杠命令精确触发

### v1.6.3（2026/5/1）

1. **Step 2 评审范围限制**：仅针对本次修改的代码及与修改点强相关的代码进行评审，排除无关历史代码
2. **六维评审升级为七维评审**：匹配 enhanced_code_review v2.1.2，新增第 7 维「隐私合规」

### v1.6.2（2026/5/1）

1. **Step 2 评审结论为必需项**：评审结论必须完整展示给用户（评分+P0-P3+问题列表），且必须贴回 Gerrit，不可跳过

### v1.6.1（2026/5/1）

1. **严格区分 Step 2 评审结论与 Step 3 Checklist**：新增对比表格和 4 条关键原则，严禁混淆或合并
2. **Checklist 内容完全固化**：只能标注状态（✓/x/o），禁止修改检查项的标题或描述文字，新增正确/错误示例
3. **Checklist 必须完整展示**：禁止省略、截断或简化，必须包含全部 12 项检查项 + 评审结论建议 3 选项

### v1.6.0（2026/5/1）

1. **【体现版本】字段改为自动填当日日期**：格式固定为 `After YYYY/M/D`（如 `After 2026/5/1`），由 Claude 自动填入，校验脚本同步更新正则匹配
2. **【提交项目/分支】字段简化**：内容仅需填写目标分支名，无需填写项目名
3. **Checklist 确认环节责任声明固化**：AskUserQuestion 问题文案中**必须**包含"Checklist 一经贴出即视为提交人已逐项审阅并认可其内容，相关责任由提交人承担"，单仓库与多仓库关联提交场景均强制展示
4. **Checklist 模板固化不可变更**：明确标注 AutoLink Code Review Checklist v2.0 模板不可变更，Claude 必须严格按模板输出，不得增删、修改任何检查项、分类、标题、说明文字或格式结构

### v1.5.1

- 新增 `gp` 触发快捷方式

### v1.5.0

1. **【开发自测视频】字段改为可选**：由用户交互选择是否添加
2. **Commit message 严格符合模板**：禁止 Co-Authored-By 等模板外多余行
3. **Step 3 与 Step 4 之间新增确认步骤**：确保 Gerrit 门禁通过后再发送飞书通知

### v1.4.0

- 内置公共飞书应用凭证，无需额外配置

### v1.3.1

- 飞书通知卡片中 Topic 改为可点击的 Gerrit 链接，跳转到 topic 搜索页

### v1.3.0

1. **新增 Topic（多仓库关联提交）完整规范**：支持命名规则、【x/y】关联标识、提交顺序约束、合入纪律
2. **新增 Topic 名称格式校验脚本**
3. **交互流程每次询问是否为关联提交**：自动扫描有变更的仓库，支持 multiSelect 确认
4. **多仓库场景下 Step 2/3 逐 CR 执行，Step 4 汇总通知**

### v1.2.0

1. **Commit message body 各字段新增 50 字上限约束**
2. **校验脚本同步增加最大字数检查**

### v1.1.0

1. **融合 gerrit-submit 为内置能力**：Step 1 不再依赖外部 skill
2. **通知卡片新增提交人字段并 @mention**
3. **新增 `feishu.submitter` 配置项**

### v1.0.0

1. **首次发布**
2. **四步流水线**：代码提交 → 评审 → Checklist → 飞书通知
3. **每步支持独立操作**
4. **配置化**：用户私有 config.json
5. **飞书通知 @mention 审核人**



## 执行遥测（SkillPack 2026-04-30 起强制）

**脚本式 skill（有入口脚本）**：脚本开头添加 2 行 trap 模板：
```bash
_T_START=$(date +%s%3N); _T_SKILL="gerrit-pipeline"
trap '_T_RC=$?; bash ~/.openclaw/workspace/skills/skillpack-client/scripts/record-run.sh "$_T_SKILL" $(($(date +%s%3N) - _T_START)) $([ $_T_RC -eq 0 ] && echo true || echo false) &' EXIT
```

**流程式 skill（纯 SKILL.md）**：在 SKILL.md 流程末尾手动调：
```bash
bash ~/.openclaw/workspace/skills/skillpack-client/scripts/record-run.sh "gerrit-pipeline" <duration-ms> <success>
```
