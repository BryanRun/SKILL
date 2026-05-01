# 本地模块评审（Local Module Review）

本文件定义 **enhanced_code_review** 相对原生 gerrit-review 的增量能力：**不依赖 Gerrit Change Number**，在本地 Git 仓库内对指定目录做与 `--prepare` 类似的结构化上下文输出，供 LLM 按 `08-llm-review-prompt.md` 产出评审结论。

## 触发语义（与 SKILL 一致）

- 用户说 **`review <模块路径>`**（例如 `review frameworks/cm/videoplayer`）→ Agent 应优先识别为**本地模块评审**（当前仓库为真源时）。
- 用户说 **`enhanced_code_review review <模块路径>`** → 显式指定本技能。
- 若 `<模块路径>` 无法解析为目录，再回退到 gerrit 语义（`review CR <数字>` / `review <姓名>`）。

## 工作流（v2.1.1 起）

1. **不再要求**「在仓库根执行」。脚本内置 git 拓扑探测，自适应 git submodule、Android `repo` 工具、子目录散布的多仓库结构。
2. 推荐用 `--repo auto` 让脚本从模块路径向上回溯定位最近的 `.git`：
   ```bash
   python3 scripts/local_module_prepare.py <模块绝对/相对路径> --repo auto -o /tmp/local_ctx.json
   ```
3. 显式指定仓库根（向后兼容旧行为）也仍然支持：
   ```bash
   cd <git 工作树根>
   python3 scripts/local_module_prepare.py <模块相对路径> [--base origin/main] -o /tmp/local_ctx.json
   ```
4. Agent 读取 `local_ctx.json`，合并 **references/01～08, 10** 的七维 checklist，输出与 Gerrit 评审同构的 **review JSON**（或等价结构正文）。
5. **不执行** `gerrit_post.py`（无 CR 可贴）；结论留在仓库内 Markdown / 会话 / 如需可再手动建 CR。

## 与 Gerrit 流程的对齐

| 环节 | Gerrit | 本地模块 |
|------|--------|----------|
| 上下文 | `gerrit_review.py --prepare` | `local_module_prepare.py` |
| 机械规则 | `gerrit_audit.py` | `local_audit.py`（规则集同源） |
| 一致性扫描 | `consistency_scan.py`（需 CR/Revision） | 可选：仅对 Java/Kotlin 未来扩展；当前以 diff + LLM 为主 |
| 隐私合规扫描 | `privacy_compliance_scan.py` | 由 `local_module_prepare.py` 内联调用（同源逻辑） |
| 贴回 | `gerrit_post.py` | 不适用 |

## 质量门禁

- 七维必扫、三问 filter、YAGNI、项目明文规范（与 `SKILL.md` 完全一致）**不得因本地模式而删减**。
- 隐私合规 P0 仍走**三重门控**（数据 A + 去向 B + 语义 C），与 Gerrit 路径完全一致。

---

# 专章：子模块 / 多仓库 / repo 工具适配（v2.1.1）

## 1. 背景

车载工程几乎都是子模块结构。常见三种拓扑，**都不能假设「仓库根 = 当前目录」**：

| 拓扑 | `<repo>/.git` 形态 | 典型场景 |
|------|------------------|---------|
| 普通仓库 | **目录** | 单仓库、CI 临时 clone |
| Git submodule | **文件**（含 `gitdir: ...` 指针） | superproject 引用第三方/平台模块 |
| Android `repo` 工具 | **symlink** → `<workspace>/.repo/projects/<...>.git` | AOSP / 车载平台多仓库（如 AutoLink T1V：`t1v_8775/.repo/manifests` + 各业务子目录独立 git） |

**关键事实**：车载平台仓库（含 AutoLink）里，`vendor/autolink/` 一级目录**自身没有** `.git`，必须下沉到 `frameworks/cm/`、`midware/hud/` 等业务子目录才能找到 git 工作树根。直接在 `vendor/autolink/` 调用 `git rev-parse --show-toplevel` 会失败。

## 2. 脚本能力

`local_module_prepare.py` 在 v2.1.1 起内置以下能力：

### 2.1 自动定位最近的 git 工作树（`--repo auto`）

从用户给定的**模块路径**（绝对或相对 cwd）所在位置开始，逐级向上查找包含 `.git`（dir / file / symlink 三态均可）的目录，作为本次评审的真实仓库根。

```bash
# 在任意 cwd 直接给绝对路径
python3 local_module_prepare.py /home/y/t1v_8775/qnx/vendor/autolink/midware/hud --repo auto

# 给子目录也行，会一并把模块相对路径算回 git 根
python3 local_module_prepare.py /home/y/t1v_8775/qnx/vendor/autolink/frameworks/cm/videoplayer/impl --repo auto
# → repo_root=/home/y/t1v_8775/qnx/vendor/autolink/frameworks/cm
# → module=videoplayer/impl
```

输出 JSON 中追加 `topology` 字段，描述本次解析过程：

```json
"topology": {
  "git_root": "/.../frameworks/cm",
  "git_kind": "dir | file | symlink | none",
  "is_submodule": false,
  "superproject": null,
  "repo_tool_managed": true,
  "repo_tool_root": "/.../t1v_8775",
  "uninitialized_submodules": [],
  "auto_resolve_target": "/.../frameworks/cm/videoplayer/impl",
  "module_relative_to_repo": "videoplayer/impl"
}
```

### 2.2 区分三种 `.git` 形态并探测 superproject

| `git_kind` | `is_submodule` | 含义 | 处理 |
|---|---|---|---|
| `dir` | false | 普通仓库 | 直接评审 |
| `symlink` | false | repo 工具或手动 symlink | 直接评审；并尝试探测 `repo_tool_root`（`.repo/manifests` 上溯 16 层内命中） |
| `file` | **true** | git submodule | 解析 `gitdir: ...` 指针，回溯到 superproject 工作树并写入 `superproject` 字段 |
| `none` | — | 未找到 `.git` | 退出码 2，输出 `topology` + `uninitialized_submodule_hint`（若可推断） |

### 2.3 子模块未初始化时给出复制即用命令

两类来源：

1. **superproject 内 `.gitmodules` 声明 → 子目录无 `.git`**：脚本扫 `.gitmodules`，对每个声明路径检查是否已落盘并初始化，未初始化的写入 `topology.uninitialized_submodules[]`，每条带 `init_hint`：
   ```json
   {
     "path": "libs/child2",
     "init_hint": "git -C /path/to/super submodule update --init -- libs/child2"
   }
   ```
2. **目标路径整体不存在 / 未拉取**：脚本沿祖先寻找最近的 `.gitmodules`，若目标路径恰好落在某个声明的 submodule 路径下，输出顶层 `topology.uninitialized_submodule_hint`，给出能让用户复制粘贴的 `git -C <super> submodule update --init -- <path>`。

> 设计原则：**只描述、不自动执行**。`init_hint` 只打印不运行，避免在评审脚本里隐式改动用户工作树（破坏性操作必须由用户显式触发）。

## 3. Agent 行为指引

调用 `local_module_prepare.py` 后：

1. 优先读取 `topology.git_root` 与 `module_relative_to_repo`，确认评审范围与用户意图一致。
2. 若 `topology.git_kind == "none"`：
   - 检查 `topology.uninitialized_submodule_hint`，若存在 → **复读** `init_hint` 让用户初始化后重跑，**不要**自己执行 `git submodule update`。
   - 若无 hint，提示用户检查路径或显式传 `--repo <git_root>`。
3. 若 `topology.is_submodule == true`：
   - 评审上下文是 submodule 工作树自身的 diff；
   - 在 cover comment 里注明「本次评审仅覆盖子模块 `<name>`，superproject `<superproject>` 的 gitlink 引用变更需另行评审」，避免漏掉 superproject 侧的指针更新。
4. 若 `topology.repo_tool_managed == true`：
   - 评审前可在 cover comment 注明「repo 工具管理，工作树根为 `<git_root>`，与 manifest 行为相关的跨仓库改动需结合 `repo status` 综合判断」。
5. 若 `uninitialized_submodules` 非空，但当前评审目标不在其内：仅作为 cover comment 中的提示信息提及，不影响主评审结论。

## 4. 兼容性

| 旧用法 | v2.1.1 行为 |
|--------|-------------|
| `cd <repo> && python3 ... <相对路径>` | 完全保持原行为；并在输出中追加 `topology` 字段（无副作用） |
| `--repo <显式路径>` | 与旧版语义一致；同样输出 `topology` |
| `--repo auto` | **新增**；推荐用于车载多仓库 / submodule 场景 |

## 5. 自检清单（评审脚本一定要打勾）

- [ ] 输出 JSON 含 `topology` 字段。
- [ ] 当目标在已初始化子模块内：`git_kind=file && is_submodule=true && superproject != null`。
- [ ] 当目标在 repo 工具管理工作树内：`git_kind=symlink && repo_tool_managed=true && repo_tool_root != null`。
- [ ] 当目标路径不存在但属已声明 submodule：`git_kind=none && uninitialized_submodule_hint.init_hint` 是可直接复制粘贴的 `git -C ... submodule update --init -- <path>`。
- [ ] 当目标在 superproject 内但相邻 submodule 未初始化：`uninitialized_submodules[]` 列出 `path` 与 `init_hint`，且目标本身评审不受影响。
