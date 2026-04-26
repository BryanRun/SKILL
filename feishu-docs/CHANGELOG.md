# 变更记录（速读）

供使用本 Skill 时快速了解「各版本多做了什么、和你操作相关的是什么」。细节与命令仍以 `SKILL.md` 为准。版本从新到旧；编号曾跳过 v1.5 / v1.6；外部分发包 v2.1 的部分能力已并入 v2.2。

## v2.8（2026-04-25）

- **大表导入彻底告别拆表**：废弃旧的「>9 行拆成多张表、续表重复表头」逻辑，统一保持单一表对象。`doc-import` 内部按行数自动选路径：
  - **≤ 9 行**：单次创建 `row_size=N` 的 docx Table（飞书创建端硬上限 9，超过返回 `1770001 invalid param`）
  - **9 < 行数 ≤ 50**：先建 9 行 docx Table，再用 `PATCH insert_table_row` 子请求逐批扩容（受文档级编辑 3 次/秒限频，60 行约 270s）
  - **> 50 行**：改用 Sheet 块电子表格嵌入（`block_type=30`），`values_batch_update` 一次写入全表（sheets API 100 次/秒，60 行 × 6 列实测端到端 5s 内完成含美化）
- **新增 `doc-import --sheet-threshold N` 选项**：调整切换 Sheet 块的行数阈值；置 `0` 时禁用 Sheet 回退，任何行数都强制走 docx Table 扩容路径（用于跨文档复制 / 导出对齐场景）
- **Sheet 块同样支持美化**：`doc-beautify` / `doc-import` 美化阶段同步识别 `block_type=30`（Sheet）：
  - **列宽自适应**：与 docx Table 共用同一缩放算法（CJK 14px / ASCII 8px + cell padding，按内容比例缩放到页宽），通过 `PUT /sheets/v2/spreadsheets/:token/dimension_range` 设置；相邻同宽列合并成一段调用，6 列通常 1-3 次请求
  - **表头加粗**：`PUT /sheets/v2/spreadsheets/:token/styles_batch_update` 给首行 `font.bold=true`
- **新增基础设施**：`api_put` HTTP 客户端（沿用现有 429 重试逻辑）；`_compute_fit_widths` 抽出列宽缩放算法供 docx 与 sheet 共用；`_sheet_get_all_values` 用 v3 sheet 元数据 + v2 `GET values` 拉全量数据
- **权限要求新增 `sheets:spreadsheet`**：用于 Sheet 块创建、`values_batch_update` 写数据、列宽与样式更新；未开启时大表 (>50 行) 会失败
- **SKILL.md / CHANGELOG.md 同步更新**：新增表格策略矩阵、与 `doc-fit-tables`（仍仅作用于 docx Table）的边界说明、文档级 3 次/秒限频说明，以及预处理表中关于「9 行限制」的修订

## v2.7（2026-04-14）

- **修复锚点链接导入崩溃**：Markdown 目录中的 `[章节](#anchor)` 因非 http(s) URL 触发飞书 `1770006 schema mismatch`，导致整个导入中断；现自动降级为纯文本，仅保留显示文字
- **PlantUML 画板样式提升**：`_clean_plantuml` 自动剥除 `left to right direction`（飞书 `style_type=1` 对此报 `syntax error`，会静默回退为不可编辑的经典图片样式）；剥除后可正常走画板原生节点，节点数从 0-2 提升至 7-35
- **活动图导入兜底**：`diagram_type=0` 失败时，对含 `start` + `if()` 特征的活动图额外尝试 `diagram_type=3`，提高画板样式成功率
- **修复导入失败时源码丢失**：旧逻辑无论 PlantUML 导入成功与否均删除源码代码块；现改为仅成功时删源码，失败时删空画板、保留源码代码块
- **新增 `_delete_doc_root_child_by_block_id` 工具函数**：按 block_id 精确删除文档根子块，每次操作前重新拉取 children 索引，避免插入/删除操作导致的索引偏移误删

## v2.6（2026-04-13）

- **新增 Checkbox / 待办列表导入**：Markdown `- [ ]` / `- [x]` 自动转换为飞书 Todo 块（`block_type=17`），保留勾选状态；支持 `- * +` 三种列表前缀及大写 `X`
- SKILL.md 支持元素列表及描述补充待办列表

## v2.5（2026-04-13）

- **新增 `doc-move`**：移动云空间文档到指定 Drive 文件夹（封装 `POST /drive/v1/files/:token/move`）
- SKILL.md 新增 §12「移动文档到 Drive 文件夹」；决策流程更新为引用 `doc-move` 命令（替代原先的 curl 直调建议）
- 常见场景「导入到指定 Drive 文件夹」补充"先创建再移动"的替代方式

## v2.4（2026-04-13）

- **新增 `doc-delete`**：删除云空间文档（移入回收站，30 天可恢复）；Wiki 管理的文档返回 `1061004`，脚本会给出明确提示
- **新增「已知限制与规避方案」**：Wiki → Drive 不可逆、Wiki 文档不可 API 删除、Drive 移动权限要求
- **新增「决策流程」**：根据目标 URL 类型（Wiki / Drive 文件夹）自动选择正确的操作路径
- **常见场景补充**：「导入到指定 Drive 文件夹」「导入并放入 Wiki」完整步骤；URL 解析表格覆盖 docx / wiki / drive/folder 三种格式
- api-reference.md 补充 `DELETE /drive/v1/files`、`POST /drive/v1/files/move`、错误码 `1061004`

## v2.3（2026-04-13）

- **新增 `wiki-move-to`**：移动云空间文档（docx/sheet/bitable 等）至知识空间，支持指定父节点或作为一级页面；异步任务通过 `wiki-task` 查询结果
- SKILL.md §10、api-reference.md Wiki 节补充对应文档

## v2.2（2026-04-13）

- **导入**：行内 `[文字](url)` → 飞书超链；表格 >9 行自动拆表；子块失败重试 3 次后报错；空文本兜底，减少 `1770001` 类错误
- **约定**：示例与脚本侧统一 `python3`；`doc-create` 仍可按 `~/.gitconfig` 的 `user.email` 自动加协作者；**非空文档不重复导入正文**（行为与 v2.1 外发包不同处以此为准）

## v1.9（2026-04-09）

- 文档与示例中的 `python` 一律改为 `python3`
- `doc-create` 创建后可按 git 邮箱自动添加协作者（可 `--collaborator` / `--no-collaborator`）

## v1.8（2026-04-09）

- 导入侧：请求超时重试、表格行数与大表策略、非空文档防重复写入
- `SKILL.md`：Windows 编码、失败恢复、API 限制等使用说明

## v1.7（2026-04-06）

- 代码块语言字段与围栏标签解析修正，导入/导出高亮与语言显示恢复正常

## v1.4（2026-04-01）

- 新增 `doc-permission`、`doc-add-collaborator`；`doc-create` 后默认可设组织内可读链接分享（可关、可改级别）

## v1.3（2026-03-31）

- 思维导图：改为 PlantUML 方案导入，画板内为可编辑原生节点

## v1.2（2026-03-31）

- 代码块语言枚举与常用别名补全，修复多种语言高亮不对的问题

## v1.1（2026-03-31）

- 行内 `**粗体**`、`` `代码` `` 导入为飞书原生样式（代码块内不误解析）

## v1.0（2026-03-31）

- 首版：`SKILL.md`、`api-reference.md`、`scripts/feishu_client.py`
