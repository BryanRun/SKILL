---
name: gerrit-pipeline
package: skillpack
description: >-
  Gerrit 一键提交评审流水线。串联代码提交、自动评审、Checklist 贴回与飞书通知，支持新建提交、amend、cherry-pick、多仓 topic 关联提交和项目差异化配置。
  SkillPack platform 字段按服务端已注册平台发布到 her / cursor / claude-code；流程本身保持 Agent Neutral，Codex 和其他具备 shell/Python 执行能力的 agent 也可按本文执行。
---

# Gerrit Pipeline

将代码提交、自动评审、Checklist 与飞书通知串联为一键流水线：

```text
Step 1: 代码提交    -> 生成规范 commit message + push 到 Gerrit
Step 2: 代码评审    -> 调用 enhanced_code_review + 结果贴回 Gerrit
Step 3: 合并确认    -> Checklist 预览 + 飞书通知预览 + 责任声明
Step 4: 飞书通知    -> Checklist 全部成功后发送飞书卡片
```

完整规范保存在 `references/full-spec.md`。执行任何复杂流程、边界处理或发版操作时，必须先读取该文件对应章节。

## When to use

- 用户需要将本地代码提交到 Gerrit，并希望串联自动评审、Checklist 和飞书通知。
- 用户明确提到 `gerrit pipeline`、`gp`、`pipeline submit`、`pipeline notify`、提交 CR、关联提交、多仓 topic、Checklist 或飞书评审通知。
- 当前任务涉及 AutoLink Gerrit 工作流，且需要遵守固定 commit message、JIRA-ID 确认、Reviewer、Checklist 和通知规则。

## Prerequisites

- 当前环境可执行 shell、Python 3、git，并具备目标 Gerrit 仓库访问权限。
- `~/.config/gerrit-pipeline/config.json` 已配置，或用户要求配置 gerrit-pipeline。
- 完整流水线的 Step 2 需要可用的 `enhanced_code_review` skill 或等价代码评审能力。
- 执行多仓关联提交前，用户需要确认参与仓库、提交顺序和 topic。

## When NOT to use

- 用户只是询问 Git、Gerrit 或飞书的一般知识，不需要执行提交/评审/通知流程。
- 当前目录不是目标代码仓库，且用户没有提供仓库路径。
- 用户要求绕过 JIRA-ID、commit message 确认、Checklist 责任声明或 Gerrit 审核纪律。
- 用户只需要普通文件打包、SkillPack 发布或飞书文档编辑；这些应使用对应发版流程或 feishu-docs 能力。

## 触发方式

- 完整流水线：`gerrit pipeline` / `gp` / `一键提交` / `提交并评审` / `submit and review`
- 仅提交：`pipeline submit` / `gerrit submit` / `gerrit push` / `提交到gerrit` / `提交CR`
- Amend：`gerrit amend`
- Cherry-pick：`gerrit cherry-pick`
- 仅评审：`pipeline review <CR编号>`
- 仅 Checklist：`pipeline checklist <CR编号>`
- 仅通知：`pipeline notify` / `飞书通知`

Claude Code 中优先使用 `/gerrit-pipeline`。Codex、Cursor、Her 或其他 Agent 使用明确自然语言触发词即可。

## 运行依赖

- Python 3.6+
- Python 包：`requests`、`urllib3`
- Git / Gerrit SSH 访问权限
- `~/.config/gerrit-pipeline/config.json`
- Step 2 依赖 `enhanced_code_review` skill

配置文件由 `scripts/pipeline_config.py init` 生成，包含 Gerrit 凭据、Reviewer、飞书群 `chat_id`、提交人和 @mention 成员。

## 执行红线

1. 完整流水线必须按 Step 1 -> Step 2 -> Step 3 -> Step 4 执行。
2. 提交模式必须显式确认：新建提交 / Amend / Cherry-pick，不得仅凭 git 状态推断。
3. JIRA-ID 必须通过用户确认，不可跳过。
4. commit message 必须最终展示给用户确认或修改。
5. Checklist 模板必须按完整模板原样输出，不能依据评审结果自动改写检查项。
6. 任一 Checklist 贴回失败时，不得发送飞书通知。
7. 飞书通知 `--subject` 必须与 commit message 第一行完全一致。
8. 多仓关联提交必须使用统一 topic，参与仓库由用户明确确认。

## Step 1 提交范围判定

新建提交按以下优先级判定路径：

1. 显式多仓触发词：`多仓`、`多仓库`、`多仓提交`、`关联提交`、`topic` -> 路径 B。
2. 用户显式提供仓库路径：1 个路径 -> 路径 A；2 个及以上路径 -> 路径 B。
3. 显式单仓触发词：`单仓`、`仅提交当前仓库`、`只提交当前仓库` -> 路径 A。
4. 无显式意图：
   - 普通 Git 仓库：只检查当前仓库。
   - repo / manifest workspace：先询问仅当前仓库、扫描整个 workspace 或手动指定路径。

全局扫描初次超时为 20 秒；超时后必须让用户选择继续等待、仅当前仓库或手动指定路径。

## 路径 A：单仓库提交

必须收集或确认：

- 项目（配置了 `projects` 时）
- JIRA-ID
- 提交类型：`bug` / `change` / `feature`
- 目标分支
- 概要描述
- 是否添加【开发自测视频】

执行顺序：

```bash
git add <files>
git commit
git push autolink HEAD:refs/for/<branch>%r=<reviewer1>,r=<reviewer2>
```

commit 后、push 前必须执行 commit message 校验；失败时最多修正并 amend 3 次。

## 路径 B：多仓库关联提交

必须确认参与仓库、顺序、topic 和共享字段。涉及 APK / `sdk_release` 时，该仓库排最后。

每个仓库按顺序提交，并使用同一个 topic：

```bash
git push autolink HEAD:refs/for/<branch>%r=<reviewer1>,r=<reviewer2>,topic=<topic>
```

扫描结果只能作为候选项，不得静默纳入全部脏仓库。

## Amend / Cherry-pick

Amend 流程用于已有 Change 追加 patchset，必须保留原 Change-Id。不得用普通 `git commit` 创建新 Change。

Cherry-pick 流程必须确认目标分支和 JIRA-ID；如冲突，解决后继续 cherry-pick，再按规范 push 到 Gerrit。

## Step 2 代码评审

调用或复用 `enhanced_code_review`，评审范围仅限本次修改及强相关代码。评审结论必须完整展示并贴回 Gerrit。

Gerrit 禁止 self-review 打分，因此评审评论以不带 Code-Review label 的方式贴出；如 enhanced_code_review 未贴回，使用 `scripts/gerrit_post_review.py` 兜底。

## Step 3 Checklist

Checklist 固定模板在完整规范 `references/full-spec.md` 中维护。执行时必须完整展示模板与责任声明，由用户确认后贴回 Gerrit。

多仓场景只展示一份固定模板预览，但执行级仍逐 CR 串行贴回。

## Step 4 飞书通知

所有 Checklist 贴回成功后，调用 `scripts/feishu_notify.py`。

单仓示例：

```bash
python3 scripts/feishu_notify.py \
  --cr <CR编号> \
  --url "<Gerrit Change URL>" \
  --branch <目标分支> \
  --subject "<commit message 第一行>" \
  --project "<项目名称>" \
  --score <评审评分> \
  --p0 <P0数> --p1 <P1数> --p2 <P2数> --p3 <P3数> \
  --checklist <pass|warn|fail>
```

多仓增加 `--topic` 和 `--repos`，一次汇总所有 CR。

## 配置脚本

- `scripts/pipeline_config.py`：配置管理、项目配置、用户 open_id 查询
- `scripts/gerrit_post_review.py`：评审结论贴回
- `scripts/gerrit_post_checklist.py`：Checklist 贴回
- `scripts/feishu_notify.py`：飞书通知卡片
- `scripts/telemetry_client.py`：非阻塞执行遥测上报
- `scripts/telemetry_defaults.json`：内部 telemetry 默认配置

## 发版流程

发版流程分两类：

- 流程 A：飞书 zip 手动分发。本地清空 `release/` 后生成用户侧 skill zip；如维护 Gateway，同步生成管理员侧 gateway zip；不通过飞书 API 上传。
- 流程 B：SkillPack 发布。以 `skill.json` 为版本与元数据 SOT，通过 SkillPack 客户端执行 lint、打包与 publish。

详细命令和版本历史见 `references/full-spec.md`。



## 执行遥测

Telemetry 默认启用，固定上报到内网 Telemetry Gateway，版本 key 和 HMAC 签名密钥随 skill 内部分发，请求带时间戳与 nonce 防重放。完整流水线执行开始时必须创建 run context；每个 step 结束时记录耗时；最终报告输出前先后台触发
`scripts/telemetry_client.py` 发送一次 `pipeline_done` 事件，然后立即输出最终报告。Telemetry 发送失败不得影响主流程结论；失败事件会暂存在本地队列，下次 pipeline 启动且网络可用时批量补发。

```bash
RUN_ID="$(python3 scripts/telemetry_client.py \
  --run-start \
  --mode full_pipeline \
  --entry-mode submit \
  --agent codex)"

python3 scripts/telemetry_client.py --run-id "$RUN_ID" --step-start submit
# 执行 Step 1
python3 scripts/telemetry_client.py --run-id "$RUN_ID" --step-finish submit

python3 scripts/telemetry_client.py --run-id "$RUN_ID" --step-start review
# 执行 Step 2
python3 scripts/telemetry_client.py --run-id "$RUN_ID" --step-finish review

python3 scripts/telemetry_client.py \
  --background \
  --run-id "$RUN_ID" \
  --event-type pipeline_done \
  --mode full_pipeline \
  --entry-mode submit \
  --steps submit,review,checklist,notify \
  --is-full-pipeline true \
  --agent codex \
  --success true \
  --repo-count 1
```

失败场景将 `--success false`，并传入稳定的 `--error-code`，如
`step1_submit_failed`、`step3_checklist_failed` 或 `step4_notify_failed`；
同时传入 `--failure-stage`，如 `submit`、`review`、`checklist` 或 `notify`。
`--agent` 必须由执行 Agent 显式传入，如 `claude-code`、`codex`、`cursor`、`deepseek`、`qwen`；无法判断时传 `unknown`。独立操作使用 `--mode single_step`，并用 `--entry-mode` 与 `--steps` 记录真实入口和执行步骤。
