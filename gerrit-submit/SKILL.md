---
name: gerrit-submit
description: >-
  Gerrit 代码提交助手。辅助生成符合公司规范的 commit message、推送 Change 到 Gerrit、amend 追加 patchset、cherry-pick 到其他分支。
  触发：gerrit submit / gerrit push / gerrit amend / gerrit cherry-pick / 提交到gerrit / 推送代码 / 提交代码审查 等。
---

# Gerrit 代码提交助手

辅助开发者完成从 commit message 编写到 Gerrit 推送的完整流程。

## 触发条件

以下任一表述触发本技能：

- `gerrit submit` / `gerrit push` — 新建 Change 并推送
- `gerrit amend` — 在已有 Change 上追加 patchset
- `gerrit cherry-pick` — cherry-pick 当前提交到其他分支
- 中文：`提交到 gerrit`、`推送代码`、`提交代码审查`、`推代码`、`提交CR`

---

## 1. Gerrit 服务器配置

| 项目 | 值 |
|------|---|
| 服务器 | `https://gerrit.auto-link.com.cn` |
| SSH | `ssh://gerrit.auto-link.com.cn:29418` |
| 认证方式 | SSH |
| 远程仓库名 | `autolink` |
| Dashboard | `https://gerrit.auto-link.com.cn/dashboard/self` |

---

## 2. Commit Message 规范

### 2.1 标题格式

```
【类型】【JIRA-ID】概要描述
```

- **类型**（必选其一）：`bug` / `change` / `feature`
  - `bug`：缺陷修复
  - `change`：需求变更
  - `feature`：新功能开发
- **JIRA-ID**：JIRA ticket 编号，用 `【】` 包裹，必须在 JIRA 上真实存在。已知前缀：`CHYT1V` / `BAIC` / `KP31` / `CL` / `T1V` / `D01` / `XINCHI` 等
- **概要描述**：简明扼要说明改动内容

**示例**：
```
【bug】【CHYT1V-1058】仪表双闪报警灯无提示音
【feature】【CHYT1V-961】Carproperty 新增车辆属性支持
【change】【CHYT1V-200】登录流程调整为异步模式
```

### 2.2 Body 必填字段

所有字段均为**必填**，Gerrit 门禁会检查前 4 项的最低字数要求。

| 字段 | 最低字数 | 最高字数 | 说明 |
|------|---------|---------|------|
| 【原因分析】 | 8 字 | 50 字 | 概述故障原因或新需求/变更背景，简明扼要 |
| 【解决方案】 | 8 字 | 50 字 | 概述改动方案，简明扼要 |
| 【自测用例】 | 20 字 | 50 字 | 场景 + 操作步骤 + 期望结果 + 实际结果，简明扼要 |
| 【自测方法】 | 4 字 | 50 字 | 验证方式及次数，简明扼要 |
| 【影响范围】 | — | 50 字 | 受影响的模块或功能范围，简明扼要 |
| 【代码修改量】 | — | 50 字 | 修改的代码行数（估算即可） |
| 【提交项目/分支】 | — | 50 字 | 提交的目标项目和分支名 |
| 【体现版本】 | — | 50 字 | 改动将体现在哪个版本中 |

### 2.3 Change-Id

- 由 `.git/hooks/commit-msg` 钩子**自动生成**，无需手动填写
- commit 时 hook 会自动在 message 末尾追加 `Change-Id: Ixxxxxxx`
- amend 操作时保留原有 Change-Id 即可关联同一 Change

### 2.4 完整 Commit Message 模板

```
【{类型}】【{JIRA-ID}】{概要描述}

【原因分析】{至少8字，描述故障原因或需求背景}
【解决方案】{至少8字，描述改动方案}
【自测用例】{至少20字，场景+操作步骤+期望结果+实际结果}
【自测方法】{至少4字，验证方式及次数}
【影响范围】{受影响的模块/功能}
【代码修改量】{修改行数}
【提交项目/分支】{目标分支}
【体现版本】{体现版本日期或版本号}
```

> Change-Id 由 hook 自动追加，不要手动写入。

---

## 3. 提交前检查（本地预检）

在推送到 Gerrit 之前，按顺序执行以下检查：

### 3.1 编译检查

确认代码能够编译通过。根据项目情况执行对应的构建命令。

### 3.2 单元测试

确认相关模块的单元测试通过。如项目有 `mk_unit_tests_linux.sh` 等脚本，优先使用。

### 3.3 Commit Message 格式校验

在 commit 之前或之后，检查 commit message 是否符合规范：

1. **标题**：以 `【bug】`、`【change】` 或 `【feature】` 开头
2. **JIRA-ID**：标题中包含有效的 JIRA ticket 编号
3. **Body 字段完整性**：确认 4 个门禁必检字段均存在且满足最低字数
   - 【原因分析】≥ 8 字
   - 【解决方案】≥ 8 字
   - 【自测用例】≥ 20 字
   - 【自测方法】≥ 4 字
4. **其他必填字段**：确认【影响范围】【代码修改量】【提交项目/分支】【体现版本】存在

**校验脚本（供 Claude 内部调用）**：

```bash
# 获取最新 commit message
msg=$(git log -1 --format="%B")

# 检查标题格式（【类型】【JIRA-ID】概要描述）
echo "$msg" | head -1 | grep -qE '^【(bug|change|feature)】【' || echo "ERROR: 标题格式不符"

# 检查 JIRA-ID（已知前缀，需被【】包裹）
echo "$msg" | head -1 | grep -qE '【(CHYT1V|BAIC|KP31|CL|T1V|D01|XINCHI)-[0-9]+】' || echo "ERROR: 缺少 JIRA-ID 或未用【】包裹"

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
check_field_length "【体现版本】" 0 50
```

---

## 4. 推送工作流

### 4.1 新建 Change（标准提交）

```bash
# 推送到目标分支的 review 队列，自动添加 reviewer
git push autolink HEAD:refs/for/{目标分支}%r=xiejie,r=lixinguo
```

**携带 topic**（可选）：

```bash
git push autolink HEAD:refs/for/{目标分支}%r=xiejie,r=lixinguo,topic={topic名称}
```

**完整流程**：

1. 确认当前分支和目标分支
2. 执行提交前检查（编译 + 单元测试）
3. `git add` 暂存变更文件
4. `git commit` 提交（使用规范化的 commit message）
5. 本地校验 commit message 格式
6. `git push autolink HEAD:refs/for/{目标分支}%r=xiejie,r=lixinguo`
7. 输出 Gerrit Change 链接

### 4.2 Amend 追加 Patchset

当需要在已有 Change 上追加修改时：

```bash
# 1. 修改代码
# 2. 暂存变更
git add <files>
# 3. amend 提交（保留原 Change-Id）
git commit --amend
# 4. 推送（Change-Id 不变，Gerrit 自动关联为新 patchset）
git push autolink HEAD:refs/for/{目标分支}%r=xiejie,r=lixinguo
```

**注意**：
- amend 会保留原 commit message 中的 `Change-Id`，Gerrit 据此识别为同一 Change 的新 patchset
- 如需修改 commit message，amend 时编辑即可
- 推送前确认 `Change-Id` 未被改变

### 4.3 Cherry-pick 到其他分支

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
git push autolink HEAD:refs/for/{目标分支}%r=xiejie,r=lixinguo
# 6. 切回原分支
git checkout {原分支}
```

**注意**：
- cherry-pick 会生成新的 commit（新 Change-Id），在 Gerrit 上是独立的 Change
- 如果 cherry-pick 多个 commit，逐个操作并分别推送
- 冲突解决后需确认 commit message 格式仍符合规范

---

## 5. 交互式辅助流程

当用户触发提交流程时，Claude 按以下步骤辅助：

### 5.1 信息收集

通过 AskUserQuestion 收集以下信息（如未从上下文中获取）：

1. **提交类型**：bug / change / feature
2. **JIRA-ID**：如 CHYT1V-1234
3. **概要描述**：一句话说明改动
4. **目标分支**：从当前分支推断或询问用户
5. **是否需要 topic**：可选

### 5.2 自动生成 Commit Message

根据收集的信息和 `git diff --staged` 的内容，自动生成完整的 commit message：

1. 分析暂存的代码变更
2. 生成各必填字段内容（原因分析、解决方案等）
3. 估算代码修改量
4. 填充提交项目/分支和体现版本
5. 展示给用户确认后提交

### 5.3 推送确认

推送前向用户确认：
- 目标分支是否正确
- Reviewer 列表是否需要调整（默认：xiejie, lixinguo）
- 是否需要添加 topic

---

## 6. 常用命令速查

| 操作 | 命令 |
|------|------|
| 推送新 Change | `git push autolink HEAD:refs/for/{branch}%r=xiejie,r=lixinguo` |
| 推送带 topic | `git push autolink HEAD:refs/for/{branch}%r=xiejie,r=lixinguo,topic={topic}` |
| amend 后推送 | `git commit --amend && git push autolink HEAD:refs/for/{branch}%r=xiejie,r=lixinguo` |
| 查看 Gerrit Dashboard | 浏览器打开 `https://gerrit.auto-link.com.cn/dashboard/self` |
| 查看 Change-Id | `git log -1 --format="%B" \| grep Change-Id` |
| 检查 commit-msg hook | `ls -la .git/hooks/commit-msg` |

---

## 7. 注意事项

1. **永远不要 `--no-verify`**：commit-msg hook 负责生成 Change-Id，跳过会导致推送失败
2. **amend vs 新 commit**：修改已推送的 Change 用 amend；新的独立改动用新 commit
3. **force push 禁止**：不要对已推送到 Gerrit 的分支做 force push
4. **敏感文件排除**：不要提交 `.env`、密钥文件、凭证等敏感内容
5. **分批提交**：大改动建议分批提交（在标题末尾标注如 `【1/3】`），每批独立可编译可测试
6. **编译和测试**：推送前必须确保编译通过和单元测试通过
