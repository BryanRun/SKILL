---
name: gerrit-pipeline
description: >-
  Gerrit 一键提交评审流水线。串联 代码提交 → CR评审 → Checklist → 飞书通知 四步流程，严格按顺序依次调用各步骤。每步均支持独立操作。
  内置完整的 Gerrit 代码提交能力（commit message 规范、推送、amend、cherry-pick）。
  触发：gerrit pipeline / gp / 一键提交 / 提交并评审 / submit and review / 一键提交评审 /
  独立操作：pipeline submit / gerrit submit / gerrit push / gerrit amend / gerrit cherry-pick / 提交到gerrit / 推送代码 / 提交代码审查 / 推代码 / 提交CR /
  pipeline review / pipeline checklist / pipeline notify / 飞书通知
---

# Gerrit Pipeline — 一键提交评审流水线

将代码提交、自动评审、Checklist、飞书通知四步串联为一键流水线。每步均支持独立操作。

代码提交能力（Step 1）已内置，无需安装 gerrit-submit skill。

## 触发条件

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
| `gerrit cherry-pick` | Step 1: Cherry-pick 到其他分支 | 目标分支名 |
| `pipeline review <CR编号>` / `评审CR` | Step 2: 代码评审 | CR 编号 |
| `pipeline checklist <CR编号>` / `贴checklist` | Step 3: 贴 Checklist | CR 编号 |
| `pipeline notify` / `飞书通知` | Step 4: 飞书通知 | CR 编号、URL、评审结果 |

独立操作时，Claude 根据触发词识别目标步骤，仅执行该步骤。如缺少必要输入，通过 AskUserQuestion 向用户收集。

---

## 流水线总览

```
Step 1: gerrit-submit        → 生成 commit message + git push → 获得 CR 编号
          ↓
Step 2: enhanced_code_review → review CR <编号> → 六维评审 + 贴回 Gerrit
          ↓
Step 3: 贴 Checklist          → 将 AutoLink Code Review Checklist v2.0 贴到 Gerrit
          ↓
Step 4: 飞书通知              → 发送流水线结果卡片到飞书群
```

**四步严格顺序执行**，任一步骤失败则中止流水线并向用户报告。

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
| 【影响范围】 | — | 50 字 | 受影响的模块或功能范围，简明扼要 |
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
6. **体现版本格式**：【体现版本】由 Claude 自动填入当日日期，格式固定为 `After YYYY/M/D`（如 `After 2026/4/30`），不接受其他格式
7. **开发自测视频**（可选）：如用户选择添加，确认【开发自测视频】存在且内容为固定值
8. **严格符合模板**：commit message body 只能包含模板中定义的字段，不得有任何模板外的多余行（如 Co-Authored-By、Signed-off-by 等）

**校验脚本（供 Claude 内部调用）**：

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
check_field_length "【影响范围】" 0 50
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

### 1.4 推送工作流

#### 新建 Change（标准提交）

Reviewer 列表从配置文件 `~/.config/gerrit-pipeline/config.json` 的 `gerrit.reviewers` 字段读取，自动拼接为 `%r=reviewer1,r=reviewer2` 格式。

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
2. 读取配置文件中的 `gerrit.reviewers` 列表
3. 执行提交前检查（编译 + 单元测试）
4. `git add` 暂存变更文件
5. `git commit` 提交（使用规范化的 commit message）
6. 本地校验 commit message 格式
7. `git push autolink HEAD:refs/for/{目标分支}%r={reviewer1},r={reviewer2}`
8. 输出 Gerrit Change 链接

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

```bash
# 1. 切换到目标分支
git checkout {目标分支}
# 2. 拉取最新代码
git pull autolink {目标分支}
# 3. cherry-pick 指定 commit
git cherry-pick {commit-hash}
# 4. 如有冲突，解决后 git cherry-pick --continue
# 5. 推送到 Gerrit
git push autolink HEAD:refs/for/{目标分支}%r={reviewer1},r={reviewer2}
# 6. 切回原分支
git checkout {原分支}
```

**注意**：
- cherry-pick 会生成新的 commit（新 Change-Id），在 Gerrit 上是独立的 Change
- 如果 cherry-pick 多个 commit，逐个操作并分别推送
- 冲突解决后需确认 commit message 格式仍符合规范

### 1.6 交互式辅助流程

当用户触发提交流程时，Claude 按以下步骤辅助。根据是否为关联提交，分为两条路径。

#### 第一步：确认是否为多仓库关联提交（最先确认）

- 如果用户的触发指令中已包含 topic 相关关键词（如"关联提交"、"多仓库"、"topic"、明确给出了 topic 名称），则视为已确认，跳过此问
- 否则首先通过 AskUserQuestion 询问用户

---

#### 路径 A：非关联提交（单仓库）

流程不变，与原有行为一致：

**信息收集**（通过 AskUserQuestion）：
1. 提交类型：bug / change / feature
2. JIRA-ID
3. 概要描述
4. 目标分支（从当前分支推断或询问）
5. **开发自测视频**（可选）：通过 AskUserQuestion 询问用户是否需要添加【开发自测视频】字段；选"需要"→ commit message 末尾加入固定行 `【开发自测视频】申请豁免，原因：已自测通过，请实车验证`；选"不需要"→ 不添加此行

**自动生成 Commit Message**：
1. 分析 `git diff --staged` 的内容
2. 生成各必填字段内容（原因分析、解决方案等）
3. 估算代码修改量
4. 填充提交分支和体现版本
5. 展示给用户确认后提交

**推送确认**：
- 确认目标分支、Reviewer 列表（从配置文件 `gerrit.reviewers` 读取）
- 执行 git commit + git push
- 提取 CR 编号

---

#### 路径 B：多仓库关联提交

**信息收集**（通过 AskUserQuestion，一次性收集所有共享信息）：
1. **Topic 名称**（必填）：推荐格式 `模块名_功能_日期`，如 `D01_FWK_20250428`。校验不含空格、冒号等特殊字符
2. **自动扫描变更仓库**：在当前 repo（manifest 管理）根目录下，通过 `repo status` 或遍历子仓库执行 `git status --porcelain` 扫描所有有代码变动的仓库，列出待提交仓库的绝对路径和变更文件数
3. **用户确认关联仓库列表**：将扫描结果通过 AskUserQuestion（multiSelect）展示给用户。提示用户：**勾选需要关联提交的仓库，勾选完成后点击 Submit 确认**。确认后的仓库列表即为本次关联提交范围
4. **提交顺序**：根据确认的仓库数量自动编号（【1/y】→【y/y】）。如涉及 APK 的 sdk_release 仓库，自动将其排到最后。用户可调整顺序
5. **提交类型**：bug / change / feature（所有仓库共享）
6. **JIRA-ID**（所有仓库共享）
7. **概要描述**（所有仓库共享）
8. **目标分支**（所有仓库共享，或各仓库分别指定）
9. **开发自测视频**（可选）：通过 AskUserQuestion 询问用户是否需要添加【开发自测视频】字段；选"需要"→ 所有仓库 commit message 末尾均加入固定行 `【开发自测视频】申请豁免，原因：已自测通过，请实车验证`；选"不需要"→ 不添加此行

**扫描变更仓库的方法**：

```bash
# 方式一：使用 repo status（推荐，manifest 管理的仓库）
repo status

# 方式二：遍历子目录查找有变更的 git 仓库
repo forall -c 'if [ -n "$(git status --porcelain)" ]; then echo "$(pwd)"; fi'
```

**遍历检查各仓库变更**：
1. 按提交顺序，依次 `cd` 到每个仓库
2. 检查每个仓库是否有未暂存/未提交的变更（`git status`）
3. 获取每个仓库的 `git diff`

**统一生成 Commit Message**：
1. 所有仓库共享基础信息（类型、JIRA-ID、概要描述、body 各字段）
2. 每个仓库的标题末尾自动追加对应的 `【x/y】` 标识
3. 各仓库的 body 字段（原因分析、解决方案等）根据各自的 diff 内容分别生成

**统一展示并确认**：
1. 一次性展示所有仓库的 diff 摘要 + 生成的 commit message
2. 通过 AskUserQuestion 请求用户统一确认（"全部确认" / "需要修改"）
3. 用户确认后，按顺序依次执行

**按顺序依次提交推送**：
1. 按 `【1/y】→【2/y】→...→【y/y】` 的顺序，依次对每个仓库执行：
   - `cd` 到仓库目录
   - `git add` 暂存变更
   - `git commit`（使用对应的 commit message）
   - 本地校验 commit message 格式
   - `git push autolink HEAD:refs/for/{目标分支}%r={reviewer1},r={reviewer2},topic={topic名称}`
   - 提取 CR 编号
2. **最后一笔（【y/y】）最后 push**
3. 任一仓库 push 失败则中止后续仓库，向用户报告错误
4. 全部 push 成功后，汇总所有 CR 编号

**关联提交完成标志**：
- 所有仓库均 push 成功
- 所有 CR 共享同一 topic
- 汇总输出：各仓库的 CR 编号、URL、提交顺序

### 1.7 常用命令速查

| 操作 | 命令 |
|------|------|
| 推送新 Change | `git push autolink HEAD:refs/for/{branch}%r={r1},r={r2}` |
| 推送关联提交（带 topic） | `git push autolink HEAD:refs/for/{branch}%r={r1},r={r2},topic={topic}` |
| amend 后推送 | `git commit --amend && git push autolink HEAD:refs/for/{branch}%r={r1},r={r2}` |
| 查看 Gerrit Dashboard | 浏览器打开 `https://gerrit.auto-link.com.cn/dashboard/self` |
| 查看 Change-Id | `git log -1 --format="%B" \| grep Change-Id` |
| 检查 commit-msg hook | `ls -la .git/hooks/commit-msg` |
| 搜索 topic 是否唯一 | Gerrit 搜索 `topic:{topic名称}` |

### 1.8 注意事项

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

通过 Skill tool 调用 `enhanced_code_review`：

```
Skill({ skill: "enhanced_code_review", args: "review CR <CR编号>" })
```

其中 `<CR编号>` 替换为实际编号。

**多仓库关联提交场景**：对 Step 1 产出的每个 CR 依次执行评审，逐个调用上述命令。每个 CR 独立产出评审评分和问题列表。

### 本步骤完成标志

- 六维评审完成
- 评审结论已贴到 Gerrit（cover message + inline comments）
- 获取评审评分（+1 / 0 / -1）和发现的问题列表
- **关联提交场景**：所有 CR 均完成评审

### 关键输出（供后续步骤使用）

- **评审评分**：suggested_score（+1 / 0 / -1）
- **P0/P1/P2/P3 计数**：各级别问题数量
- **是否有阻塞性问题**：P0 > 0 或 P1 > 0
- **关联提交场景**：每个 CR 各自独立的评审结果

### 独立操作

触发 `pipeline review <CR编号>` 时，仅执行本步骤。如未提供 CR 编号，通过 AskUserQuestion 询问。

### 失败处理

- 如果评审脚本执行失败（如 Gerrit API 不可达），向用户报告错误
- 评审结果本身（如发现 P0 问题）不算失败，流水线继续执行后续步骤

---

## Step 3：贴 Checklist

### ⚠️ 用户确认声明

> **本步骤需要用户人工确认。** Claude 会根据评审结果预填 Checklist 并展示给用户，待用户确认后方可贴出。Checklist 一经贴出即视为提交人已逐项审阅并认可其内容，相关责任由提交人承担。

执行本步骤时，Claude **必须**：
1. 先将预填好的 Checklist 完整展示给用户
2. 通过 AskUserQuestion 请求用户确认，问题文案**必须**包含以下责任声明（不论单仓库还是多仓库关联提交，每次确认前都必须展示）：

   ```
   ⚠️ Checklist 一经贴出即视为提交人已逐项审阅并认可其内容，相关责任由提交人承担。
   
   请确认是否将上述 Checklist 贴到 Gerrit？
   ```

   选项：
   - "确认贴出" — 将上述 Checklist 贴到 Gerrit CR 评论中
   - "需要修改" — 需要调整 Checklist 内容后再贴出

3. 用户确认后才调用脚本贴到 Gerrit；用户要求修改则按修改意见调整后重新确认

### 前置条件

需要 CR 编号。完整流水线中由 Step 1 提供；独立操作时由用户提供。

**多仓库关联提交场景**：对 Step 1 产出的每个 CR 依次执行 Checklist 贴回。每个 CR 独立展示 Checklist 并请求用户确认。

### 执行方式

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

Claude 先将填好的 Checklist 写入临时文件，再调用脚本贴到 Gerrit。

### Checklist 标注规则

Claude 根据 Step 2 的评审结果和实际情况，自动标注每项：

| 标记 | 含义 | 使用场景 |
|------|------|---------|
| `✓` | 通过 | 该项检查通过或已确认 |
| `x` | 未通过 | 该项存在问题需要修改 |
| `o` | 不适用 | 该项在本次提交中不涉及（如"若有"、"可选"项） |

**标注依据**：

- **任务关联**：commit message 中有有效 JIRA-ID → ✓
- **分支关联**：单分支提交 → o；多分支需求 → 根据情况标注
- **提交关联**：无关联提交 → o；有关联 → 根据 topic 情况标注
- **功能测试 / 回归测试 / 集成测试**：根据 commit message 中【自测用例】【自测方法】字段标注
- **单元测试**：可选项，无单测 → o
- **接口定义 / 接口发布**：根据是否修改了对外接口判断
- **可配置化**：根据是否涉及配置参数判断
- **技术债**：根据评审结论判断，无技术债 → o
- **开源合规**：无新增开源组件 → ✓
- **评审结论建议**：P0=0 且 P1=0 → Approve；有 P1 → Need Info；有 P0 → Request Changes

### 独立操作

触发 `pipeline checklist <CR编号>` 时，仅执行本步骤。如缺少评审结果，Claude 先通过 `gerrit_show.py` 获取 CR 信息辅助标注。

### 本步骤完成标志

- Gerrit API 返回 200
- Checklist 已成功贴到 CR 评论中

---

## Step 3.5：发送飞书通知前确认

在完整流水线中，执行飞书通知（Step 4）之前，**必须**通过 AskUserQuestion 向用户确认该笔提交已具备可 Review / Merge 的条件。

**确认提示**：

> 即将发送飞书通知，请先确认以下事项：
> 1. Gerrit 门禁（prebuild / precheck）已通过或正在进行中
> 2. 所有关联 Change（若有）均已推送并具备合入条件
> 3. Reviewer 已准备好进行评审

**选项**（通过 AskUserQuestion 展示）：

| 选项 | 行为 |
|------|------|
| 确认，发送飞书通知 | 继续执行 Step 4 |
| 暂不发送，稍后手动触发 | 中止流水线，不发送飞书通知（已完成的提交、评审、Checklist 结果不受影响） |

**多仓库关联提交场景**：在确认提示中列出所有 CR 编号及其当前状态，统一确认后再发送。

**独立操作不受影响**：当用户直接触发 `pipeline notify` / `飞书通知` 时，视为用户已自行确认，跳过本步骤。

---

## Step 4：飞书通知

### 前置条件

1. 配置文件 `~/.config/gerrit-pipeline/config.json` 已初始化（含 chat_id 和 at_members）
2. 需要 CR 信息和评审结果。完整流水线中由前序步骤提供；独立操作时由用户提供或从 Gerrit 获取。

### 首次使用引导

如果配置文件不存在，Claude 引导用户完成初始化：

1. 提示用户运行 `python3 pipeline_config.py init`
2. 收集飞书群 chat_id
3. 收集 @mention 成员邮箱
4. 自动查询飞书 open_id 并保存到配置

也可通过 Claude 直接收集信息后调用脚本完成配置：

```bash
# 查询成员 open_id
cd <skill_dir>/scripts && python3 pipeline_config.py lookup-users \
  --emails "user1@auto-link.com.cn,user2@auto-link.com.cn" --save

# 查看当前配置
python3 pipeline_config.py show
```

### 执行方式

调用 `gerrit-pipeline/scripts/feishu_notify.py` 发送飞书群消息：

```bash
# 单仓库提交
cd <skill_dir>/scripts && python3 feishu_notify.py \
  --cr <CR编号> \
  --url "<Gerrit Change URL>" \
  --branch <目标分支> \
  --subject "<提交标题>" \
  --score <评审评分> \
  --p0 <P0数> --p1 <P1数> --p2 <P2数> --p3 <P3数> \
  --checklist <pass|warn|fail>

# 多仓库关联提交（增加 --topic 参数，一次性汇总所有 CR）
cd <skill_dir>/scripts && python3 feishu_notify.py \
  --topic <Topic名称> \
  --cr <CR编号1>,<CR编号2>,... \
  --url "<URL1>,<URL2>,..." \
  --branch <目标分支> \
  --subject "<共享概要描述>" \
  --score <最低评审评分> \
  --p0 <P0总数> --p1 <P1总数> --p2 <P2总数> --p3 <P3总数> \
  --checklist <pass|warn|fail>
```

其中 `<skill_dir>` 为本 skill 的安装路径（如 `~/.claude/skills/gerrit-pipeline`）。

脚本自动从 `~/.config/gerrit-pipeline/config.json` 读取 chat_id 和 at_members。

### 参数说明

| 参数 | 必填 | 说明 | 来源 |
|------|------|------|------|
| `--cr` | 是 | CR 编号 | Step 1 输出 |
| `--url` | 是 | Gerrit Change URL | Step 1 输出 |
| `--branch` | 否 | 目标分支（默认 al_dev） | Step 1 输出 |
| `--subject` | 是 | 提交标题（commit message 首行） | Step 1 输出 |
| `--score` | 否 | 评审评分 -1/0/1（默认 1） | Step 2 输出 |
| `--p0` ~ `--p3` | 否 | 各级别问题数（默认 0） | Step 2 输出 |
| `--checklist` | 否 | Checklist 状态 pass/warn/fail（默认 pass） | Step 3 输出 |
| `--topic` | 否 | Topic 名称（多仓库关联提交时必填） | Step 1 输出 |
| `--repos` | 否 | 各 CR 对应仓库名，逗号分隔（多仓库时必填，与 --cr 一一对应） | Step 1 输出 |
| `--chat-id` | 否 | 飞书群 ID（覆盖配置文件中的值） | — |
| `--dry` | 否 | 仅预览不发送 | — |

### 配置文件

位置：`~/.config/gerrit-pipeline/config.json`（用户私有，不随 skill 分发）

```json
{
  "feishu": {
    "chat_id": "oc_xxxxxxxx",
    "at_members": [
      {"name": "审核人A", "open_id": "ou_xxxxxxxx"},
      {"name": "审核人B", "open_id": "ou_xxxxxxxx"}
    ]
  }
}
```

### 飞书消息格式

发送 interactive card（卡片消息）。

#### 单仓库提交卡片

- **标题**：Gerrit Pipeline 通知（颜色随评审结果变化：绿/橙/红）
- **CR 编号**：可点击跳转到 Gerrit
- **分支** + **提交概要**
- **评审评分** + **问题统计**
- **Checklist 状态**
- **审核人**：@mention 配置的成员

#### 多仓库关联提交卡片

当传入 `--topic` 参数时，使用多仓库卡片格式：

- **标题**：Gerrit Pipeline 通知 — 关联提交（颜色随最低评审评分变化）
- **Topic**：显示 topic 名称，可点击跳转到 Gerrit topic 搜索页（`https://gerrit.auto-link.com.cn/q/topic:xxx`）
- **分支** + **提交概要**
- **关联 CR 列表**：每个 CR 一行，显示仓库名 + CR 编号（可点击跳转）
- **评审评分**：取所有 CR 中最低分
- **问题统计**：所有 CR 问题数汇总
- **Checklist 状态**
- **审核人**：@mention 配置的成员

### 飞书应用权限

脚本已内置公共飞书应用凭证，无需设置环境变量。

飞书应用需开通权限：
- `im:message:send_as_bot` — 发送群消息
- `contact:user.base:readonly` — 查询用户 open_id

机器人需已加入目标飞书群。

### 独立操作

触发 `pipeline notify` 或 `飞书通知` 时，仅执行本步骤。通过 AskUserQuestion 收集缺少的 CR 信息。

### 本步骤完成标志

- 飞书 API 返回成功（`code: 0`）
- 消息已送达目标群

### 失败处理

- 如飞书应用权限不足，提示用户联系管理员开通 `im:message:send_as_bot` 权限
- 飞书通知失败不影响前序步骤的结果（代码已提交、评审已贴出）

---

## Checklist 模板

以下为固化的 AutoLink Code Review Checklist v2.0 模板。**此模板不可变更**，Claude 必须严格按照以下模板输出，不得增删、修改任何检查项、分类、标题、说明文字或格式结构：

```markdown
### ✅ AutoLink Code Review Checklist v2.0
*适用于Gerrit评审 | AI已完成预审的精简版 | 推荐在每项前打 `✓` 或`x` 或添加评论说明，然后复制粘贴在Gerrit评论中*
> **说明**：此Checklist用于AI本地评审通过后的人工评审阶段。AI已自动检查编码风格、命名规范、
> 编译冲突、提交信息等8项，人工只需聚焦以下12项。若某项不适用（`若有`或`可选`），请标注 `o`。

---

#### 📎 流程合规
- [{任务关联}] **任务关联**：填写有效的JIRA任务或BUG编号，非关联任务不能反复用同一个JIRA单
- [{分支关联}] **分支关联**：需要提交的分支（如release分支）都已Cherry pick（若有）
- [{提交关联}] **提交关联**：拉齐有关联或依赖的相关方代码提交，并关联了同一个Topic（若有）

#### 🧪 测试验证
- [{功能测试}] **功能测试**：预期功能或问题缺陷的测试验证通过，测试报告已提交到Jira单
- [{回归测试}] **回归测试**：最小自测清单测试验证通过，测试报告已提交到Jira单
- [{集成测试}] **集成测试**：全量的接口集成测试验证通过，测试报告已提交到Jira单（可选）
- [{单元测试}] **单元测试**：覆盖率满足该模块测试等级要求且测试通过，测试报告已提交到Jira单（可选）

#### 🧱 平台化
- [{接口定义}] **接口定义**：对外接口定义简洁明了，且可跨项目、跨平台复用，文档更新匹配（若有）
- [{接口发布}] **接口发布**：对外接口更新时，重新生成接口文档和SDK包给到相关方（若有）
- [{可配置化}] **可配置化**：特定项目需求实现配置化，相关配置参数已在文档或清单中已更新
- [{技术债}] **技术债**：若暂时达不到平台化要求，需要登记到技术债务清单（若有）

#### 🔐 安全合规
- [{开源合规}] **开源合规**：所使用开源组件，符合其版权协议要求，不存在法律风险

---

### 📝 评审结论建议
- [{approve}] ✅ **Approve**（满足所有关键项，AI预审无高风险问题）
- [{need_info}] ⚠️ **Need Info**（需补充信息后决定）
- [{request_changes}] ❌ **Request Changes**（需修改后重新提交）
```

将模板中的 `{占位符}` 替换为 `✓`、`x` 或 `o`。评审结论三选一标 `✓`，其余标空格。

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

1. **顺序不可调换**：完整流水线必须按 Step 1 → 2 → 3 → 4 顺序执行
2. **CR 编号传递**：Step 1 的输出是后续所有步骤的输入，务必正确提取
3. **Self-review 限制**：Gerrit 禁止对自己的 CR 打分，评审评论会以不带 Code-Review label 的方式贴出
4. **Checklist 自动标注**：Claude 根据评审结果自动填写，人工 reviewer 可在 Gerrit 上修改
5. **失败中止**：Step 1 失败则整个流水线中止；Step 2/3 失败不影响后续步骤；Step 4 失败不影响已完成的提交和评审
6. **飞书通知**：Step 4 使用内置公共飞书应用，无需额外配置凭证
7. **独立操作**：每步可单独触发，Claude 会收集缺少的必要信息
8. **外部依赖**：Step 2（代码评审）依赖 enhanced_code_review skill，需同步安装；Step 1/3/4 为内置能力，无外部依赖

---

## 版本历史

### v1.6.0（2026/5/1）

1. **【体现版本】字段改为自动填当日日期**：格式固定为 `After YYYY/M/D`（如 `After 2026/5/1`），由 the assistant 自动填入，校验脚本同步更新正则匹配
2. **【提交项目/分支】字段简化**：内容仅需填写目标分支名，无需填写项目名
3. **Checklist 确认环节责任声明固化**：AskUserQuestion 问题文案中**必须**包含"Checklist 一经贴出即视为提交人已逐项审阅并认可其内容，相关责任由提交人承担"，单仓库与多仓库关联提交场景均强制展示
4. **Checklist 模板固化不可变更**：明确标注 AutoLink Code Review Checklist v2.0 模板不可变更，the assistant 必须严格按模板输出，不得增删、修改任何检查项、分类、标题、说明文字或格式结构

### v1.5.1

- 新增 `gp` 触发快捷方式

### v1.4.0

- 内置公共飞书应用凭证，无需额外配置

### v1.3.1

- 新增 Topic（多仓库关联提交）支持

### v1.2.0

- commit message body 字段新增 50 字最大长度约束
