---
name: feishu-docs
description: >-
  Read, create, edit, and export Feishu (Lark) documents and whiteboards via
  Open Platform API. Use when the user mentions Feishu documents, Lark docs,
  飞书文档, 飞书画板, whiteboard, or needs to interact with Feishu cloud
  documents programmatically.
---

# 飞书文档与画板操作

通过飞书开放平台 API 对飞书文档和画板进行读取、创建、编辑和导出操作。

## 前置条件

### 环境变量

操作前确认以下环境变量已设置：

```bash
export FEISHU_APP_ID="your_app_id"
export FEISHU_APP_SECRET="your_app_secret"
```

### Python 依赖

需要 **Python 3.10+**，请确保使用 `python3` 命令。部分主机上 `python` 指向 Python 2，脚本和文档中统一使用 `python3`。

```bash
pip3 install lark-oapi requests
```

### Windows 环境

Windows 控制台默认使用 GBK 编码，脚本日志中的 Unicode 字符（如 ✅ ⚠）可能导致 `UnicodeEncodeError`。脚本入口已做 `reconfigure(encoding="utf-8")` 处理，但若仍遇编码问题，可设置环境变量兜底：

```powershell
$env:PYTHONIOENCODING = "utf-8"
```

### HTTP 客户端行为

`feishu_client.py` 对 Open Platform 的 `GET` / `POST` / `PATCH` / `DELETE` 默认使用 **60s 超时**，并对 `ConnectionError` / `Timeout` / `ChunkedEncodingError` **最多重试 5 次**，降低长文档导入时的偶发网络失败。

### 权限要求

| 功能 | 所需权限 |
|------|---------|
| 读取文档 | docx:document:readonly |
| 编辑文档 | docx:document |
| 读取画板节点 | board:whiteboard:node:read |
| 创建画板节点 | board:whiteboard:node:create |
| 导入 PlantUML/Mermaid | board:whiteboard:node:create |
| 自适应表格列宽 | docx:document |
| 一键美化文档 | docx:document, board:whiteboard:node:create |
| 导入 Markdown | docx:document |
| 导出文档 | docx:document:readonly |
| 设置文档权限/链接分享 | docs:permission.setting:write_only |
| 添加文档协作者 | docs:permission.member:create |
| 移动文档到知识空间 | wiki:wiki:readonly, wiki:wiki |
| 移动文档到 Drive 文件夹 | drive:file |
| 删除云空间文档 | drive:file |
| 大表 Sheet 块嵌入与美化 | sheets:spreadsheet |

## 核心工作流

### 0. 一键美化文档

当用户提供一个飞书文档链接并要求"美化"时，使用 `doc-beautify` 命令一键完成以下操作：

1. **PlantUML → 飞书画板**：将文档中所有 PlantUML 代码块（`@startuml` / `@startgantt` / `@startmindmap` 等）导入为飞书画板，并删除原代码块
2. **自适应表格列宽**：按内容比例重新分配列宽，使表格总宽度对齐页面宽度（**同时覆盖 docx Table 和大表 Sheet 块**）
3. **表头高亮加粗**：docx Table 设置首行为标题行（`header_row`）+ 文字加粗；Sheet 块通过 `styles_batch_update` 把首行字体加粗

```bash
# 从文档 URL 提取 document_id 后执行
python3 scripts/feishu_client.py doc-beautify <document_id>

# 指定较宽页宽 (1033px)
python3 scripts/feishu_client.py doc-beautify <document_id> --width 1033
```

**触发条件：** 用户说"美化飞书文档"、"优化文档排版"、"格式化文档"等类似指令时，自动调用此命令。

### 0.5 Markdown 导入飞书文档

将本地 Markdown 文件导入为飞书文档，**导入完成后自动执行一键美化**（等同于 `doc-beautify`）。

```bash
# 1. 先创建空文档
python3 scripts/feishu_client.py doc-create --title "文档标题"
# → 返回 document_id

# 2. 导入 Markdown（自动美化）
python3 scripts/feishu_client.py doc-import <document_id> --file ./local.md

# 指定较宽页宽
python3 scripts/feishu_client.py doc-import <document_id> --file ./local.md --width 1033

# 仅导入不美化
python3 scripts/feishu_client.py doc-import <document_id> --file ./local.md --no-beautify

# 追加模式：向已有内容的文档末尾追加
python3 scripts/feishu_client.py doc-import <document_id> --file ./local.md --append

# 大表策略：表格行数 > 阈值（默认 50）时改用 Sheet 块电子表格嵌入
python3 scripts/feishu_client.py doc-import <document_id> --file ./local.md --sheet-threshold 50

# 强制全程走文档 Table 路径（任何行数都用 docx Table，禁用 Sheet 回退）
python3 scripts/feishu_client.py doc-import <document_id> --file ./local.md --sheet-threshold 0
```

**表格策略（`doc-import` 内部根据行数自动选择，整张表绝不拆分）：**

| 行数 | 实现路径 | 说明 |
|------|---------|------|
| ≤ 9 | 单次创建 `row_size=N` 的 docx Table | 飞书创建端硬上限 9（`row_size>9` 报 `1770001 invalid param`） |
| 9 < 行数 ≤ `sheet_threshold` | 先建 9 行 docx Table，再用 `insert_table_row` 子请求增量扩容 | 文档级编辑限频 3 次/秒，扩容耗时随行数线性增长 |
| 行数 > `sheet_threshold`（默认 50） | 改用 Sheet 块电子表格嵌入（`block_type=30`），`values_batch_update` 一次写入全表 | sheets API 限频 100 次/秒，60 行 × 6 列实测端到端 5s 内完成（含美化）；docx Table 路径同等数据需 200s+ |
| `--sheet-threshold 0` | 禁用 Sheet 回退，任何行数都走 docx Table 扩容路径 | 用于强制保留为 docx Table 形态（如导出对齐、跨文档复制等场景） |

支持的 Markdown 元素：标题（H1-H6）、引用（`>`）、代码块（带语言识别，含 PlantUML）、分割线（`---`）、表格、无序列表（`- `）、有序列表（`1. `）、待办列表（`- [ ]` / `- [x]`）、普通文本，以及行内链接 `[显示文字](https://...)`。H1 自动跳过（作为文档标题，避免与飞书页顶标题重复）。导入后美化阶段会自动将 PlantUML/Mermaid 代码块转为飞书画板；块创建失败时会自动重试，仍失败则中断并报错，避免静默丢块。

**Markdown 预处理规则（导入前自动检查并修正）：**

在导入 Markdown 之前，需要检查源文件中是否存在以下已知会导致飞书渲染异常的写法，并**在导入前自动修正源文件**：

| 问题 | 原因 | 修正方式 |
|------|------|---------|
| 嵌套代码块（如 `````markdown` 包裹 ````plantuml`） | 解析器不支持多层反引号嵌套，内层代码块会被拆散为纯文本 | 去掉外层包裹，直接使用内层代码块；如需展示代码块语法，改用文字描述（如"将代码放入 \`\`\`plantuml 代码块中"） |
| 表格单元格中包含管道符 `\|` | 管道符被解析为列分隔符，导致表格列数错乱、内容溢出 | 将管道符替换为文字描述或使用 HTML 实体 `&#124;`，避免裸 `\|` 出现在单元格中 |
| Markdown 表格超过 **9 行**（表头+数据） | 飞书创建单表时 `row_size > 9` 会返回 `1770001` | **不再拆表**：脚本按行数自动选「9 行内直建 / 9-50 行单表 `insert_table_row` 扩容 / 超过 50 行改用 Sheet 块」，一律保持单一表对象。无需手动改源文件；如需强制 docx Table 路径，加 `--sheet-threshold 0` |
| 导入时指定的 `--width` 与飞书页宽设置不匹配 | 表格列宽总和超过/不足实际页面宽度 | 不传 `--width` 时默认 833px（对应飞书默认页宽），仅在确认用户使用"较宽"页宽时才传 `--width 1033` |

#### 代码块语言（避免默认为纯文本）

`feishu_client.py` 将 Markdown 围栏语言映射为飞书 **CodeLanguage** 枚举值，并写入 **`code.style.language`**（`TextStyle`，见[飞书块数据结构](https://open.feishu.cn/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/document-docx/docx-v1/data-structure/block)）。**禁止**把语言写在 `code.language` 顶层 —— 服务端会忽略，界面会始终显示为 **Plain Text**。

围栏首行解析使用 `^\`\`\`\s*(\S*)`，可正确识别 ` ```cpp`、` ```c++` 等（旧版仅用 `\w*` 会把 `c++` 截成 `c`）。

**若围栏无语言、空字符串、或仅写 `text` / `plaintext`，会映射为 PlainText（枚举 1）**。需要高亮时**必须**写语言标签，例如：

| 内容类型 | 推荐围栏首行 | 说明 |
|---------|-------------|------|
| C/C++ | ` ```cpp` 或 ` ```c` | 勿留空 |
| Shell / CI | ` ```bash` 或 ` ```sh` | |
| Python | ` ```python` | |
| JSON / YAML | ` ```json` / ` ```yaml` | |
| PlantUML（待转画板前仍为代码块） | ` ```plantuml` | 与 `_is_plantuml` 识别、`plantuml` 导入 API 一致 |
| 纯展示、无需高亮 | ` ```text` 或 ` ```plaintext` | 仅当确实不需要高亮时使用 |

**执行要求：** 在调用 `doc-import` / 生成飞书文档之前，检查并修正 Markdown 中所有 ` ``` ` 代码块：补全语言标签；禁止无故使用无语言围栏或 `txt`（若仓库习惯写 `txt`，应改为与 `feishu_client` 映射表一致的别名，如 `text`/`plaintext` 或实际语言）。

#### PlantUML：飞书画板不兼容时的处理顺序（先改源码，再导入）

飞书 PlantUML 导入接口（见下文 §5）**不支持全部 PlantUML 语法**。若不经处理直接 `doc-import` / `doc-beautify`，可能 `parse error` 或画板空白。**必须按下述顺序操作，再生成飞书文档**：

1. **对照 §5「注意事项与已知问题」**：删除或改写不支持的指令（如 `skinparam componentStyle rectangle`、`diagram_type=8` 组件图问题等）。
2. **思维导图 `@startmindmap`**：必须先按 §6「PlantUML 预处理」清洗（`left side` / `<style>` / 图标 / 颜色注解等），再导入。
3. **`doc-beautify` 内置 `_clean_plantuml`** 仅做有限删除（如去掉含 `skinparam componentStyle` 的行）；**复杂类图/时序图若仍失败，应在源 Markdown 中手工简化**（减少 skinparam、拆分多图、`diagram_type` 用 `0` 自动识别）。
4. **验证**：可在本地用同一套清洗后的源码心理预期「能过飞书解析」；若 API 仍报错，继续改 PlantUML 直至成功，**最后再执行** `doc-import` / `doc-beautify`。
5. **禁止**：在 PlantUML 仍含已知不兼容语法时反复调用导入接口刷配额。

**导入失败恢复：** 若 `doc-import` 中途崩溃或超时，内容可能已部分或全部导入到飞书文档中，但自动美化步骤未执行。此时**不要重新导入**（会导致内容重复），而是单独运行美化命令补完：

```bash
# 对已导入内容的文档单独执行美化（PlantUML 转画板 + 表格列宽 + 表头加粗）
python3 scripts/feishu_client.py doc-beautify <document_id>
```

**触发条件：** 用户说"导入 Markdown 到飞书"、"将 md 写入飞书文档"、"导入飞书文档"等类似指令时，自动创建文档并调用此命令；**同时**应执行上述代码块语言检查与 PlantUML 预检（若文档含图表）。

### 1. 获取 Access Token

所有 API 调用都需要 `tenant_access_token`。使用工具脚本自动获取：

```bash
python3 scripts/feishu_client.py token
```

或手动获取：

```bash
curl -X POST 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal' \
  -H 'Content-Type: application/json' \
  -d '{"app_id": "'$FEISHU_APP_ID'", "app_secret": "'$FEISHU_APP_SECRET'"}'
```

### 2. 读取文档

**获取文档基本信息：**

```bash
python3 scripts/feishu_client.py doc-info <document_id>
```

**获取文档纯文本内容：**

```bash
python3 scripts/feishu_client.py doc-text <document_id>
```

**获取文档所有块（结构化内容）：**

```bash
python3 scripts/feishu_client.py doc-blocks <document_id>
```

### 3. 创建/编辑文档

**创建新文档：**

创建成功后**自动设置链接分享权限为组织内可阅读**（`tenant_readable`），并**尝试将当前用户添加为协作者**（默认读取 `~/.gitconfig` 的 `user.email`，也可通过 `--collaborator <email>` 显式指定）。若未读取到邮箱、或飞书应用无 `docs:permission.member:create` 权限 / 被企业策略限制，则会打印提示并跳过协作者添加，不影响文档创建。如需编辑权限，可通过 `--link-share tenant_editable` 指定。

```bash
# 创建文档（默认组织内可阅读 + 尝试自动添加协作者）
python3 scripts/feishu_client.py doc-create --title "文档标题" [--folder <folder_token>]

# 创建文档（组织内可编辑）
python3 scripts/feishu_client.py doc-create --title "文档标题" --link-share tenant_editable

# 指定协作者邮箱（不使用 ~/.gitconfig）
python3 scripts/feishu_client.py doc-create --title "文档标题" --collaborator someone@company.com

# 跳过自动添加协作者
python3 scripts/feishu_client.py doc-create --title "文档标题" --no-collaborator

# 跳过权限设置（同时也不会走协作者逻辑）
python3 scripts/feishu_client.py doc-create --title "文档标题" --no-permission
```

**在文档中追加内容块：**

```bash
python3 scripts/feishu_client.py doc-append <document_id> --text "要追加的文本内容"
```

**在文档中追加 Markdown 格式块：**

```bash
python3 scripts/feishu_client.py doc-append <document_id> --markdown "## 标题\n正文内容"
```

### 4. 画板（Whiteboard）操作

飞书画板以 `whiteboard_id` 标识。在文档中 `block_type=43` 的块即为画板，其 `block.token` 就是 `whiteboard_id`。

**获取画板所有节点：**

```bash
python3 scripts/feishu_client.py board-nodes <whiteboard_id>
```

**创建单个节点：**

```bash
python3 scripts/feishu_client.py board-create-node <whiteboard_id> --type text_shape \
  --content '{"text":{"text":"Hello"}}' --x 100 --y 100 --width 200 --height 60
```

**批量创建节点（从 JSON）：**

```bash
python3 scripts/feishu_client.py board-create-nodes <whiteboard_id> --file nodes.json
# 或内联 JSON
python3 scripts/feishu_client.py board-create-nodes <whiteboard_id> --nodes '[{"type":"text_shape","x":0,"y":0,"width":100,"height":40,"text":{"text":"A"}}]'
```

**获取画板主题：**

```bash
python3 scripts/feishu_client.py board-theme <whiteboard_id>
```

### 5. 导入 PlantUML / Mermaid 图表到画板

当原始文档中包含 PlantUML 或 Mermaid 格式的设计图（架构图、时序图、流程图等）时，**优先使用飞书画板原生 PlantUML 导入接口**，直接将源码渲染为画板原生节点，而非手动拼搭 `text_shape` + `connector`。

**前置条件（与 §0.5 一致）：** 若飞书解析报错，**先在 Markdown / `.puml` 中修改语法**（见本节「注意事项与已知问题」及 §6），再执行导入或一键美化；不要假设「标准 PlantUML」一定能被飞书画板原样接受。

**API 接口：**

```
POST /board/v1/whiteboards/{whiteboard_id}/nodes/plantuml
```

**请求体：**

```json
{
  "plant_uml_code": "@startuml\nAlice -> Bob: hello\n@enduml",
  "syntax_type": 1,
  "style_type": 1,
  "diagram_type": 0
}
```

**参数说明：**

| 参数 | 必填 | 说明 |
|------|------|------|
| `plant_uml_code` | 是 | PlantUML / Mermaid 源码（1–1,000,000 字符） |
| `syntax_type` | 是 | `1` = PlantUML，`2` = Mermaid |
| `style_type` | 否 | `1` = 画板样式（生成多个原生节点），`2` = 经典样式（生成图片，支持二次编辑源码）。默认 `2` |
| `diagram_type` | 否 | `0` = 自动识别（推荐），`1` = 思维导图，`2` = 时序图，`3` = 活动图，`4` = 类图，`5` = ER，`6` = 流程图，`7` = 用例图，`8` = 组件图 |

**频率限制：** 5 次/秒

**使用示例（Python）：**

```python
import os, requests

BASE = "https://open.feishu.cn/open-apis"
TK = requests.post(f"{BASE}/auth/v3/tenant_access_token/internal", json={
    "app_id": os.environ["FEISHU_APP_ID"],
    "app_secret": os.environ["FEISHU_APP_SECRET"]
}).json()["tenant_access_token"]
H = {"Authorization": f"Bearer {TK}", "Content-Type": "application/json"}

# 1. 在文档中创建画板块
r = requests.post(f"{BASE}/docx/v1/documents/{doc_id}/blocks/{doc_id}/children",
    headers=H, json={
        "children": [{"block_type": 43, "board": {"align": 2, "width": 1200, "height": 800}}],
        "index": -1
    }).json()
wb_id = r["data"]["children"][0]["board"]["token"]

# 2. 导入 PlantUML
r = requests.post(f"{BASE}/board/v1/whiteboards/{wb_id}/nodes/plantuml",
    headers=H, json={
        "plant_uml_code": puml_code,
        "syntax_type": 1,
        "style_type": 1,
        "diagram_type": 0
    }).json()
# r["data"]["node_id"] 为创建的节点 ID
```

**注意事项与已知问题：**

| 问题 | 解决方案 |
|------|---------|
| `diagram_type=8`（组件图）可能返回 `parse error` | 改用 `diagram_type=0`（自动识别） |
| `skinparam componentStyle rectangle` 导致语法错误 | 删除该行，飞书解析器不支持此指令 |
| `style_type=1` 生成原生节点不可编辑源码 | 如需保留源码编辑能力，改用 `style_type=2` |
| Mermaid 语法仅支持 `style_type=1` | `style_type=2`（经典样式）仅限 PlantUML |

**决策规则：** 当用户要求将设计图转为飞书画板时，如果源文档中已有 PlantUML / Mermaid 代码块，直接使用此接口导入；仅在源文档没有结构化图表语法、需要从零设计布局时，才退化到手动方式（`text_shape` + `connector` 自由绘制）。

### 6. 导入思维导图到飞书画板（可编辑原生节点）

将 PlantUML `@startmindmap` 思维导图导入为飞书画板**可编辑的原生节点**（非图片），用户可以在画板上直接拖拽、编辑文字、增删节点。

**关键参数组合：**

```python
{
    "plant_uml_code": puml_code,
    "syntax_type": 1,      # PlantUML
    "style_type": 1,        # 画板样式（可编辑原生节点）
    "diagram_type": 1       # 思维导图（必须指定为 1，不要用 0 自动识别）
}
```

**飞书 `style_type=1` 对 PlantUML mindmap 语法的兼容性：**

| 语法特性 | 是否支持 | 说明 |
|---------|---------|------|
| `* / ** / *** / ****` 层级节点 | 支持 | 最多支持约 5 层 |
| 中文文本 | 支持 | |
| `\n` 节点内换行 | 支持 | |
| `left side` / `right side` | **不支持** | 返回 `parse error`，必须删除 |
| `<style>...</style>` 样式块 | **不支持** | 返回 `parse error`，必须删除 |
| `<&icon>` Creole 图标 | **不支持** | 返回 `parse error`，必须删除 |
| `***[#color]` 颜色注解 | **不支持** | 返回 `parse error`，必须删除 |
| `title` 标题行 | 忽略 | 不报错但不渲染，可保留 |

**PlantUML 预处理（导入前必须清洗）：**

在调用导入 API 之前，必须对 `.puml` 源码执行以下清洗：

1. **删除 `<style>...</style>` 块**（含 `<style>` 和 `</style>` 及中间内容）
2. **删除所有 `left side` 和 `right side` 行**
3. **删除 `<&xxx>` 图标引用**（如 `<&flag>`, `<&check>`, `<&target>` 等）
4. **删除 `[#color]` 颜色注解**（如 `***[#FFCDD2]` → `***`）
5. **删除空行**（飞书解析器对空行敏感）

清洗示例（Python）：

```python
import re

def clean_puml_for_feishu(puml_code: str) -> str:
    """清洗 PlantUML mindmap 源码，使其兼容飞书 style_type=1"""
    # 删除 <style>...</style> 块
    puml_code = re.sub(r'<style>.*?</style>', '', puml_code, flags=re.DOTALL)
    # 删除 left side / right side
    puml_code = re.sub(r'^(left|right)\s+side\s*$', '', puml_code, flags=re.MULTILINE)
    # 删除 <&xxx> 图标
    puml_code = re.sub(r'<&\w+>\s*', '', puml_code)
    # 删除 [#color] 颜色注解（保留 * 层级标记）
    puml_code = re.sub(r'\[#[A-Fa-f0-9]{6}\]\s*', '', puml_code)
    # 删除空行
    puml_code = '\n'.join(line for line in puml_code.split('\n') if line.strip())
    return puml_code
```

**完整工作流（从 .puml 文件导入飞书文档画板）：**

```python
import os, re, requests, time

BASE = "https://open.feishu.cn/open-apis"
TK = requests.post(f"{BASE}/auth/v3/tenant_access_token/internal", json={
    "app_id": os.environ["FEISHU_APP_ID"],
    "app_secret": os.environ["FEISHU_APP_SECRET"]
}).json()["tenant_access_token"]
H = {"Authorization": f"Bearer {TK}", "Content-Type": "application/json"}

# 1. 读取并清洗 PlantUML
with open("mindmap.puml") as f:
    puml_raw = f.read()
puml_clean = clean_puml_for_feishu(puml_raw)

# 2. 在文档中创建画板块
r = requests.post(f"{BASE}/docx/v1/documents/{doc_id}/blocks/{doc_id}/children",
    headers=H, json={
        "children": [{"block_type": 43, "board": {"align": 2, "width": 1200, "height": 800}}],
        "index": -1
    }).json()
wb_id = r["data"]["children"][0]["board"]["token"]
time.sleep(0.5)

# 3. 导入为可编辑原生节点
r = requests.post(f"{BASE}/board/v1/whiteboards/{wb_id}/nodes/plantuml",
    headers=H, json={
        "plant_uml_code": puml_clean,
        "syntax_type": 1,
        "style_type": 1,        # 画板样式 = 可编辑原生节点
        "diagram_type": 1        # 思维导图
    }).json()

if r.get("code") == 0:
    print(f"导入成功，节点 ID: {r['data']['node_id']}")
else:
    print(f"导入失败: {r}")
```

**注意：** 因为 `left side` / `right side` 被删除，所有分支默认展开在右侧。如需左右分布，用户可在飞书画板中手动拖拽调整节点位置。

**触发条件：** 用户说"导入思维导图到飞书"、"PlantUML 导入飞书画板"、"导入 puml 到飞书"、"要可编辑的飞书画板"等类似指令时，使用本节工作流。

### 7. 自适应表格列宽（对齐页面宽度）

飞书文档中通过 API 创建或默认生成的表格，其列宽总和（约 730px）通常**小于页面内容区域宽度**，导致表格右侧留白。此命令自动分析每列文本内容，按内容比例重新分配列宽，使表格总宽度对齐页面宽度。

**飞书页面宽度参考值：**

飞书文档编辑器内容区宽度取决于用户的"页宽设置"（右上角 ··· → 页宽），不同模式对应的内容区宽度：

| 页宽模式 | 内容区宽度 (px) | 说明 |
|---------|---------------|------|
| 默认 (Default) | **833** | 窗口 > 964px 时恒定 |
| 较宽 (Wide) | **1033** | 默认 + 200px |
| 全宽 (Full) | 窗口宽 − 132 | 随窗口变化 |

> 参考来源：[飞书页宽行为逆向分析](https://juejin.cn/post/7438115774501797914)

**基本用法（默认页宽 833px）：**

```bash
python3 scripts/feishu_client.py doc-fit-tables <document_id>
```

**指定"较宽"页宽（1033px）：**

```bash
python3 scripts/feishu_client.py doc-fit-tables <document_id> --width 1033
```

**工作原理：**

1. 遍历文档所有表格块（`block_type=31`）
2. 读取每个单元格内容，按字符宽度（CJK ~14px，ASCII ~8px）估算每列所需最小宽度
3. 按内容比例将列宽缩放至目标总宽度（默认 833px）
4. 通过 `PATCH /docx/v1/documents/{doc_id}/blocks/{table_id}` 的 `update_table_property` 逐列更新

**API 限制：**

- 单列最小宽度 50px
- 文档 CRUD 频率限制 5 次/秒（脚本已内置 0.25s 间隔）
- 每次只能更新一列宽度，N 列表格需 N 次 API 调用

**与 Sheet 块的关系：** `doc-fit-tables` **仅作用于 docx Table（`block_type=31`）**。若文档中含 Sheet 块（大表场景，`block_type=30`），其列宽与表头加粗由 `doc-beautify` 一并处理（走 sheets v2 `dimension_range` + `styles_batch_update` 端点，限频 100 次/秒，相邻同宽列合并调用）。需要单独美化 Sheet 块时直接跑 `doc-beautify <document_id>` 即可。

### 8. 权限管理

机器人应用创建的文档默认所有者是机器人本身，其他用户无法编辑。通过以下方式授予编辑权限：

**方式一：设置链接分享权限（推荐，自动执行）**

`doc-create` 命令创建文档后会自动调用此 API，将链接分享设为组织内可阅读。手动调用：

```bash
# 设置组织内可阅读（默认）
python3 scripts/feishu_client.py doc-permission <document_id> --link-share tenant_readable

# 设置组织内可编辑
python3 scripts/feishu_client.py doc-permission <document_id> --link-share tenant_editable

# 关闭链接分享
python3 scripts/feishu_client.py doc-permission <document_id> --link-share closed
```

**方式二：添加指定用户为协作者**

```bash
# 通过邮箱添加（可管理权限）
python3 scripts/feishu_client.py doc-add-collaborator <document_id> --member-type email --member-id user@company.com

# 通过邮箱添加（仅编辑权限）
python3 scripts/feishu_client.py doc-add-collaborator <document_id> --member-type email --member-id user@company.com --perm edit

# 通过 userid 添加
python3 scripts/feishu_client.py doc-add-collaborator <document_id> --member-type userid --member-id "12345"

# 通过 openid 添加
python3 scripts/feishu_client.py doc-add-collaborator <document_id> --member-type openid --member-id "ou_xxxxx"
```

**链接分享权限可选值：**

| 值 | 说明 |
|---|------|
| `tenant_readable` | 组织内获得链接的人可阅读（默认） |
| `tenant_editable` | 组织内获得链接的人可编辑 |
| `anyone_editable` | 互联网上获得链接的人可编辑（需 external_access=open） |
| `anyone_readable` | 互联网上获得链接的人可阅读（需 external_access=open） |
| `closed` | 关闭链接分享 |

**前置权限要求：** 飞书应用需要开启 `docs:permission.setting:write_only`（修改云文档权限设置）和/或 `docs:permission.member:create`（添加云文档协作者）权限。

### 9. 导出文档

**导出为 Markdown：**

```bash
python3 scripts/feishu_client.py doc-export <document_id> --format markdown [--output ./output.md]
```

**导出为纯文本：**

```bash
python3 scripts/feishu_client.py doc-export <document_id> --format text [--output ./output.txt]
```

### 10. 移动文档到知识空间（Wiki）

将云空间文档（我的空间 / 共享空间）移动至指定知识空间，挂载在指定父节点下或作为一级页面。移动后文档从"我的空间"/"共享空间"消失，转入知识库目录树，权限默认继承父页面。

**基本用法：**

```bash
# 移动文档到知识空间，挂载在指定父节点下
python3 scripts/feishu_client.py wiki-move-to <space_id> --obj-token <document_id> --parent <parent_wiki_token>

# 移动为一级页面（不指定 --parent）
python3 scripts/feishu_client.py wiki-move-to <space_id> --obj-token <document_id>

# 移动非 docx 类型（如 sheet）
python3 scripts/feishu_client.py wiki-move-to <space_id> --obj-token <token> --obj-type sheet --parent <parent_wiki_token>
```

**参数说明：**

| 参数 | 必填 | 说明 |
|------|------|------|
| `space_id` | 是 | 目标知识空间 ID（通过 `wiki-node` 查询已有节点可获取） |
| `--obj-token` | 是 | 要移动的文档 token（即 `document_id`） |
| `--obj-type` | 否 | 文档类型，默认 `docx`。可选：`doc`, `docx`, `sheet`, `bitable`, `mindnote`, `file` |
| `--parent` | 否 | 目标父节点的 `wiki_token`。不填则作为知识空间一级页面 |

**异步任务：** 接口可能返回 `task_id`（操作尚未完成），需通过 `wiki-task` 查询最终结果：

```bash
python3 scripts/feishu_client.py wiki-task <task_id>
```

**从 Wiki URL 提取 space_id 和 parent_wiki_token：**

对于 `https://xxx.feishu.cn/wiki/<wiki_token>` 格式的目标位置：

```bash
# 查询节点信息，获取 space_id 和 node_token（即 parent_wiki_token）
python3 scripts/feishu_client.py wiki-node <wiki_token>
```

返回中的 `space_id` 即知识空间 ID，`node_token` 可作为 `--parent` 参数。

**典型场景（创建文档 → 导入 → 移入 Wiki）：**

```bash
# 1. 创建空文档
python3 scripts/feishu_client.py doc-create --title "方案文档"
# → 返回 document_id

# 2. 导入 Markdown
python3 scripts/feishu_client.py doc-import <document_id> --file ./plan.md

# 3. 查询目标 Wiki 节点
python3 scripts/feishu_client.py wiki-node <target_wiki_token>
# → 返回 space_id, node_token

# 4. 移动到 Wiki
python3 scripts/feishu_client.py wiki-move-to <space_id> --obj-token <document_id> --parent <target_wiki_token>
# → 返回 wiki_token，文档即在知识库中
```

**触发条件：** 用户说"移动到 Wiki"、"移到知识库"、"放到 wiki 下面"、提供 Wiki URL 并要求移动文档时，自动调用此命令。需先通过 `wiki-node` 解析目标 URL 获取 `space_id` 和父节点 token。

### 11. 删除文档

将云空间文档移入回收站（可恢复 30 天）。

```bash
# 删除 docx 文档
python3 scripts/feishu_client.py doc-delete <document_id>

# 删除其他类型
python3 scripts/feishu_client.py doc-delete <file_token> --type sheet
```

**限制：** 仅支持删除**云空间**（我的空间 / 共享空间 / 指定文件夹）中的文档。**Wiki 管理的文档无法通过此 API 删除**（返回 `1061004 forbidden`），需在飞书知识库 UI 中手动「移至回收站」。

**触发条件：** 用户说"删除文档"、"删掉这篇"、提供 docx URL 并要求删除时调用。若目标是 Wiki 文档（URL 含 `/wiki/`），应提前告知用户需手动操作。

### 12. 移动文档到 Drive 文件夹

将云空间文档移动到指定的 Drive 文件夹。适用于文档创建后需要归档到特定目录的场景。

**基本用法：**

```bash
# 移动 docx 文档到目标文件夹
python3 scripts/feishu_client.py doc-move <document_id> --folder <folder_token>

# 移动其他类型
python3 scripts/feishu_client.py doc-move <file_token> --folder <folder_token> --type sheet
```

**参数说明：**

| 参数 | 必填 | 说明 |
|------|------|------|
| `file_token` | 是 | 文档 token（即 `document_id`） |
| `--folder` | 是 | 目标文件夹的 `folder_token` |
| `--type` | 否 | 文档类型，默认 `docx`。可选：`doc`, `docx`, `sheet`, `bitable`, `mindnote`, `file`, `folder` |

**从 URL 提取 folder_token：**

对于 `https://xxx.feishu.cn/drive/folder/<folder_token>` 格式的链接，直接取路径末段作为 `folder_token`。

**限制：**
- 仅支持移动**云空间**（我的空间 / 共享空间）中的文档。**Wiki 管理的文档无法通过此 API 移动到 Drive 文件夹**（见「已知限制与规避方案」）
- 需要对源位置和目标文件夹均具有编辑权限
- 飞书应用需开启 `drive:file` 权限

**触发条件：** 用户说"移动到文件夹"、"移到目录"、提供 `drive/folder/` URL 并要求移动文档时，自动调用此命令。

## 已知限制与规避方案

以下为实践中验证的平台限制，操作前**必须先判断**以避免无效 API 调用。

| 限制 | 影响 | 规避方案 |
|------|------|---------|
| **Wiki → Drive 不可逆** | 文档一旦移入知识空间（`wiki-move-to`），无法通过 API 移回 Drive 文件夹 | 若用户后续要求转到 Drive 文件夹：在目标文件夹 `doc-create --folder` 新建文档 → `doc-import` 重新导入，而非尝试移动 |
| **Wiki 文档不可 API 删除** | `DELETE /drive/v1/files` 对 Wiki 管理的文档返回 `1061004 forbidden`；飞书开放平台**无 Wiki 节点删除端点** | 告知用户在飞书知识库 UI 手动删除 |
| **Wiki 节点删除无公开 API** | Wiki v2 仅暴露 create / move / get_node，无 delete 端点 | 同上 |
| **Drive 文件夹移动需权限** | `POST /drive/v1/files/:token/move` 需要源位置和目标位置的编辑权限 | 确保飞书应用已开启 `drive:file` 权限 |

**决策流程（用户要求"移动文档到 XXX"时）：**

1. **解析目标 URL**：
   - `https://xxx.feishu.cn/wiki/<token>` → Wiki 目标，用 `wiki-move-to`
   - `https://xxx.feishu.cn/drive/folder/<token>` → Drive 文件夹目标，用 `doc-move`（已有文档）或 `doc-create --folder`（新建文档直接放入）
2. **若文档当前在 Wiki 中**且目标是 Drive 文件夹 → 无法直接移动，必须走"新建+重新导入"路径
3. **若文档当前在云空间**且目标是 Drive 文件夹 → 用 `doc-move <document_id> --folder <folder_token>`

## 文档 API 限制与注意事项

| 限制 | 说明 |
|------|------|
| 表格创建 `row_size` | **创建端硬上限 9 行**（未写入官方文档，超过返回 `invalid param` code=1770001）。脚本不再拆表：9 行内单次创建；9-50 行先建 9 行表再用 `PATCH insert_table_row` 子请求逐批扩容；超过 50 行自动改用 Sheet 块（电子表格嵌入）以规避文档级 3 次/秒编辑限频。可用 `--sheet-threshold` 调整阈值或置 0 强制走 docx Table |
| 文档级编辑频率 | **3 次/秒**（`PATCH /docx/v1/documents/:id/blocks/:id`）。同一文档下大量 cell 写入 / `insert_table_row` 扩容时会成为瓶颈，单元测试已观测 60 行 docx Table 全程耗时 ~270s。Sheet 块改走 sheets API（100 次/秒），同等数据 5s 内完成 |
| 分割线 `block_type` | 分割线为 **22**（非 27，27 是图片）。需传 `{"block_type": 22, "divider": {}}` |
| `children` 数组长度 | 单次创建子块请求最多 50 个 |

## 画板 API 限制与注意事项

| 限制 | 说明 |
|------|------|
| 节点创建格式 | 请求体必须使用 `{"nodes": [...]}` 数组包裹，不能直接放顶层字段 |
| mind_map 类型 | 仅支持创建根节点，子节点通过 API 添加会返回 `invalid arg` |
| 图片节点 | `image` 类型需要先通过 `drive/v1/medias/upload_all` 上传获取 token；`docx_image` 类型的 token 在画板上可能返回 `server internal error` |
| 删除节点 | 画板 API **不提供**删除节点的接口 |
| 批量上限 | 单次请求最多创建 3000 个节点 |
| connector 引用 | connector 的 `attached_object.id` 必须引用**同一批次**中创建的节点自定义 ID，跨批次引用需使用服务端返回的实际 ID |
| 自定义 ID | 创建时可指定 `id` 字段用于同批次内跨节点引用（如 connector → text_shape），服务端会分配实际 ID |

## API 速率限制

| 接口类别 | 限制 |
|---------|------|
| 文档 CRUD（含表格列宽更新） | 5 次/秒 |
| 画板节点操作 | 50 次/秒 |
| PlantUML/Mermaid 导入 | 5 次/秒 |
| Token 获取 | 按应用 20 次/分钟 |

## 常见场景

### 从 wiki URL 获取文档 ID 并定位画板

对于 `https://xxx.feishu.cn/wiki/<wiki_token>` 格式的链接：

```bash
# 1. 获取 document_id
python3 scripts/feishu_client.py wiki-node <wiki_token>
# 返回中 obj_token 即为 document_id

# 2. 获取文档块，找到画板
python3 scripts/feishu_client.py doc-blocks <document_id>
# block_type=43 的块为画板，其 board.token 就是 whiteboard_id

# 3. 在画板上操作
python3 scripts/feishu_client.py board-create-mindmap <whiteboard_id> --file tree.json
```

### 从飞书 URL 提取 ID

| URL 格式 | 提取方式 |
|----------|---------|
| `https://xxx.feishu.cn/docx/<document_id>` | 直接取 `document_id` |
| `https://xxx.feishu.cn/wiki/<wiki_token>` | `wiki-node <wiki_token>` → `obj_token` 即 `document_id`，`space_id` 用于移动 |
| `https://xxx.feishu.cn/drive/folder/<folder_token>` | 直接取 `folder_token`，用于 `doc-create --folder` 或 `folder-list` |

### 批量读取文档目录

```bash
python3 scripts/feishu_client.py folder-list <folder_token>
```

### 将本地 Markdown 导入飞书文档（导入 + 自动美化）

将本地 Markdown 文件解析为飞书文档块（标题、引用、代码块、分割线、表格等），逐块写入目标文档，完成后自动执行一键美化（PlantUML 转画板 + 表格列宽自适应 + 表头高亮加粗）。

**基本用法（导入 + 自动美化）：**

```bash
# 1. 创建空文档
python3 scripts/feishu_client.py doc-create --title "文档标题"
# 记录返回的 document_id

# 2. 导入 Markdown 并自动美化
python3 scripts/feishu_client.py doc-import <document_id> --file ./local.md
```

**指定较宽页宽（1033px）：**

```bash
python3 scripts/feishu_client.py doc-import <document_id> --file ./local.md --width 1033
```

**仅导入不美化：**

```bash
python3 scripts/feishu_client.py doc-import <document_id> --file ./local.md --no-beautify
```

**支持的 Markdown 元素：**

| 元素 | 对应飞书块类型 |
|------|--------------|
| `# ~ ######` 标题 | Heading 1-6 (block_type 3-8)，H1 自动跳过（已作为文档标题） |
| `> ` 引用 | Quote (block_type 15) |
| ` ``` ` 代码块 | Code (block_type 14)，自动识别 20+ 种语言（含 PlantUML） |
| `---` 分割线 | Divider (block_type 22) |
| `- ` 无序列表 | Bullet (block_type 12) |
| `1. ` 有序列表 | Ordered (block_type 13) |
| `- [ ]` / `- [x]` 待办列表 | Todo (block_type 17)，保留勾选状态 |
| 表格（竖线分隔） | ≤ 50 行：Table (`block_type=31`)，单表 `insert_table_row` 扩容；> 50 行：Sheet 块电子表格嵌入 (`block_type=30`)，`values_batch_update` 一次写入。两类表头都会在美化阶段加粗，列宽都会自适应 |
| 普通文本 | Text (block_type 2) |
| `[别名](https://url)` 行内链接 | Text 内 `text_run`，`text_element_style.link.url` |

**美化阶段自动执行：**

| 操作 | 说明 |
|------|------|
| PlantUML → 画板 | 将 PlantUML/Mermaid 代码块转为飞书画板原生节点，删除原代码块 |
| 表格列宽自适应 | 按内容比例分配列宽，对齐页面宽度（同时覆盖 docx Table 与 Sheet 块） |
| 表头高亮加粗 | docx Table 设 `header_row` + 文字加粗；Sheet 块通过 `styles_batch_update` 给首行 `font.bold=true` |

**触发条件：** 用户说"导入 Markdown 到飞书"、"将 md 文件写入飞书文档"等类似指令时，自动创建文档并调用此命令。

### 导入 Markdown 到指定 Drive 文件夹

用户提供 `https://xxx.feishu.cn/drive/folder/<folder_token>` 时：

**方式一：创建时直接指定文件夹（推荐）**

```bash
# 1. 在目标文件夹中创建文档
python3 scripts/feishu_client.py doc-create --title "文档标题" --folder <folder_token>

# 2. 导入 Markdown
python3 scripts/feishu_client.py doc-import <document_id> --file ./local.md
```

**方式二：先创建再移动（文档已存在时）**

```bash
# 1. 创建文档（默认在我的空间）
python3 scripts/feishu_client.py doc-create --title "文档标题"

# 2. 导入 Markdown
python3 scripts/feishu_client.py doc-import <document_id> --file ./local.md

# 3. 移动到目标文件夹
python3 scripts/feishu_client.py doc-move <document_id> --folder <folder_token>
```

### 导入 Markdown 并放入 Wiki 知识库

用户提供 `https://xxx.feishu.cn/wiki/<wiki_token>` 时：

```bash
# 1. 创建文档（云空间）
python3 scripts/feishu_client.py doc-create --title "文档标题"

# 2. 导入 Markdown
python3 scripts/feishu_client.py doc-import <document_id> --file ./local.md

# 3. 查询 Wiki 目标节点获取 space_id
python3 scripts/feishu_client.py wiki-node <wiki_token>

# 4. 移入知识空间
python3 scripts/feishu_client.py wiki-move-to <space_id> --obj-token <document_id> --parent <wiki_token>
```

**注意：** 移入 Wiki 后文档不可逆回 Drive（见「已知限制与规避方案」），请确认用户意图后再执行第 4 步。

## 详细参考

- 完整 API 参考见 [api-reference.md](api-reference.md)
- 工具脚本源码见 [scripts/feishu_client.py](scripts/feishu_client.py)
- 飞书开放平台文档：https://open.feishu.cn/document
