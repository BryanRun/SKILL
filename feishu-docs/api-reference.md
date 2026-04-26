# 飞书开放平台 API 参考

Base URL: `https://open.feishu.cn/open-apis`

所有请求需携带 Header: `Authorization: Bearer <tenant_access_token>`

---

## 认证

### 获取 tenant_access_token

```
POST /auth/v3/tenant_access_token/internal
Content-Type: application/json

{
  "app_id": "<APP_ID>",
  "app_secret": "<APP_SECRET>"
}
```

**响应：**
```json
{
  "code": 0,
  "tenant_access_token": "t-xxx",
  "expire": 7200
}
```

---

## 文档 (DocX) API

### 获取文档信息

```
GET /docx/v1/documents/{document_id}
```

响应含 `title`、`revision_id`、`create_time`、`update_time`。

### 获取纯文本内容

```
GET /docx/v1/documents/{document_id}/raw_content
```

返回文档全文纯文本。

### 获取文档所有块

```
GET /docx/v1/documents/{document_id}/blocks?page_size=500
```

分页返回文档中的所有块，每个块包含 `block_id`、`block_type`、`parent_id`、`children`、具体内容等。

**常用 block_type 值：**

| block_type | 说明 |
|-----------|------|
| 1 | Page（页面，即根块） |
| 2 | Text（文本段落） |
| 3 | Heading1 |
| 4 | Heading2 |
| 5 | Heading3 |
| 6 | Heading4 |
| 7 | Heading5 |
| 8 | Heading6 |
| 9 | Heading7 |
| 10 | Heading8 |
| 11 | Heading9 |
| 12 | Bullet（无序列表） |
| 13 | Ordered（有序列表） |
| 14 | Code（代码块） |
| 15 | Quote（引用） |
| 17 | TodoList（任务列表） |
| 22 | Image（图片） |
| 23 | Table（表格） |
| 27 | Divider（分割线） |
| 30 | Callout（高亮块） |
| 31 | Grid（分栏布局） |
| 32 | GridColumn（分栏列） |
| 43 | Board（画板/白板） |

### 创建文档

```
POST /docx/v1/documents
Content-Type: application/json

{
  "title": "文档标题",
  "folder_token": "<可选，目标文件夹token>"
}
```

### 创建子块（追加内容）

```
POST /docx/v1/documents/{document_id}/blocks/{block_id}/children
Content-Type: application/json

{
  "children": [
    {
      "block_type": 2,
      "text": {
        "elements": [
          {
            "text_run": {
              "content": "段落文本内容"
            }
          }
        ]
      }
    }
  ],
  "index": -1
}
```

`block_id` 通常使用 `document_id`（即页面根块）来在文档末尾追加。`index: -1` 表示追加到末尾。

### 更新块内容

```
PATCH /docx/v1/documents/{document_id}/blocks/{block_id}
Content-Type: application/json

{
  "update_text_elements": {
    "elements": [
      {
        "text_run": {
          "content": "更新后的文本"
        }
      }
    ]
  }
}
```

### 删除块

```
DELETE /docx/v1/documents/{document_id}/blocks/{block_id}/children/batch_delete
Content-Type: application/json

{
  "start_index": 0,
  "end_index": 1
}
```

---

## 画板 (Whiteboard/Board) API

### 获取画板所有节点

```
GET /board/v1/whiteboards/{whiteboard_id}/nodes
```

返回画板中的所有节点。每个节点包含 `id`、`type`、`x`、`y`、`width`、`height`、`text`、`style`、`parent_id`、`children` 等字段。

### 批量创建画板节点

**重要：** 请求体必须使用 `nodes` 数组包裹，单次最多 3000 个节点。

```
POST /board/v1/whiteboards/{whiteboard_id}/nodes
Content-Type: application/json

{
  "nodes": [
    {
      "id": "n1",
      "type": "text_shape",
      "x": 100,
      "y": 100,
      "width": 200,
      "height": 60,
      "text": {
        "text": "节点文本",
        "font_size": 14,
        "font_weight": "bold",
        "text_color": "#000000",
        "horizontal_align": "center",
        "vertical_align": "mid"
      },
      "style": {
        "fill_color": "#E0F7FA",
        "border_color": "#00ACC1",
        "border_style": "solid",
        "border_width": "narrow",
        "fill_opacity": 100,
        "border_opacity": 100,
        "fill_color_type": 1,
        "border_color_type": 1
      },
      "composite_shape": {"type": "round_rect"}
    }
  ]
}
```

**响应：**
```json
{
  "code": 0,
  "data": {"ids": ["a1:1"]},
  "msg": ""
}
```

`id` 字段为自定义标识，仅在**同一批次**内用于节点间引用（如 connector 引用 text_shape）。服务端会分配实际 ID 并在 `data.ids` 中返回。

### connector（连接线）节点

在同一批次中创建，通过自定义 `id` 引用源/目标节点：

```json
{
  "id": "c1",
  "type": "connector",
  "connector": {
    "start": {
      "attached_object": {"id": "n1", "snap_to": "right"}
    },
    "end": {
      "attached_object": {"id": "n2", "snap_to": "left"}
    },
    "shape": "curve"
  },
  "style": {
    "border_color": "#00ACC1",
    "border_style": "solid",
    "border_width": "narrow",
    "border_opacity": 80,
    "border_color_type": 1
  }
}
```

`snap_to` 可选值：`auto`、`top`、`right`、`bottom`、`left`。
`shape` 可选值：`straight`（直线）、`polyline`（折线）、`curve`（曲线）、`right_angled_polyline`（直角折线）。

### composite_shape 常用子类型

| type 值 | 说明 |
|---------|------|
| round_rect | 圆角矩形 |
| round_rect2 | 全圆角矩形（胶囊形） |
| rect | 基础矩形 |
| ellipse | 圆形 |
| diamond | 菱形 |
| hexagon | 六边形 |
| triangle | 三角形 |
| cylinder | 圆柱体 |
| cloud | 云朵 |
| star | 五角星 |
| bubble | 气泡 |

### style 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| fill_color | string | 填充颜色（`#RRGGBB`） |
| fill_color_type | int | 0=系统颜色，1=自定义颜色 |
| fill_opacity | float | 填充透明度（0-100） |
| border_color | string | 边框颜色（`#RRGGBB`） |
| border_color_type | int | 0=系统颜色，1=自定义颜色 |
| border_style | string | `solid`/`none`/`dash`/`dot` |
| border_width | string | `extra_narrow`/`narrow`/`medium`/`bold` |
| border_opacity | float | 边框透明度（0-100） |

### 支持的节点类型

| 类型 | 说明 | API 限制 |
|------|------|---------|
| text_shape | 文本形状 | 完整支持 |
| connector | 连接线 | 完整支持，需同批次引用节点 |
| composite_shape | 组合形状 | 完整支持 |
| image | 图片 | 需 `drive/v1/medias/upload_all` 先上传获取 token |
| section | 分区 | 完整支持 |
| sticky_note | 便签 | 完整支持 |
| mind_map | 思维导图 | **仅支持创建根节点**，子节点 API 不可用 |
| group | 组 | 完整支持 |
| table | 表格 | 完整支持 |
| svg | SVG 图形 | 需特定格式 |
| paint | 画笔 | 完整支持 |

### 导入 PlantUML / Mermaid 图表

```
POST /board/v1/whiteboards/{whiteboard_id}/nodes/plantuml
Content-Type: application/json

{
  "plant_uml_code": "@startuml\nAlice -> Bob: hello\n@enduml",
  "syntax_type": 1,
  "style_type": 1,
  "diagram_type": 0
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| plant_uml_code | string | 是 | PlantUML / Mermaid 源码（1–1,000,000 字符） |
| syntax_type | int | 是 | `1` = PlantUML，`2` = Mermaid |
| style_type | int | 否 | `1` = 画板样式（多个原生节点），`2` = 经典样式（图片，可编辑源码，仅 PlantUML）。默认 `2` |
| diagram_type | int | 否 | `0` = 自动识别（推荐），`2` = 时序图，`3` = 活动图，`4` = 类图，`5` = ER，`6` = 流程图，`8` = 组件图 |

**响应：**
```json
{
  "code": 0,
  "msg": "success",
  "data": { "node_id": "t1:1" }
}
```

频率限制：5 次/秒。已知限制：`diagram_type=8` 可能返回 `parse error`，建议用 `0`（自动识别）；`skinparam componentStyle rectangle` 不被支持，需删除。

### 获取画板主题

```
GET /board/v1/whiteboards/{whiteboard_id}/theme
```

---

## 云空间 (Drive) API

### 列出文件夹内容

```
GET /drive/v1/files?folder_token={folder_token}&page_size=200
```

### 删除文件

```
DELETE /drive/v1/files/{file_token}?type=docx
```

将文件移入回收站（30 天内可恢复）。`type` 可选：`doc`, `docx`, `sheet`, `bitable`, `mindnote`, `file`, `folder`。

**限制：** Wiki 管理的文档返回 `1061004 forbidden`，需在飞书 UI 删除。

**所需权限：** `drive:file`

### 移动文件

```
POST /drive/v1/files/{file_token}/move
Content-Type: application/json

{
  "type": "docx",
  "folder_token": "<目标文件夹 token>"
}
```

将云空间文件移动到另一个文件夹。频率限制 5 QPS / 10000 次/天。

**限制：** 仅适用于云空间文件；Wiki 管理的文档不可通过此接口移动。

### 获取文件元信息

```
GET /drive/v1/metas/batch_query
Content-Type: application/json

{
  "request_docs": [
    {
      "doc_token": "<token>",
      "doc_type": "docx"
    }
  ]
}
```

---

## Wiki (知识库) API

### 通过 wiki_token 获取文档信息

```
GET /wiki/v2/spaces/get_node?token={wiki_token}
```

返回含 `obj_token`（即 `document_id`）和 `obj_type`。

### 移动云文档至知识空间

```
POST /wiki/v2/spaces/{space_id}/nodes/move_docs_to_wiki
Content-Type: application/json

{
  "parent_wiki_token": "<可选，父节点 wiki_token>",
  "obj_type": "docx",
  "obj_token": "<document_id>"
}
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `parent_wiki_token` | 否 | 父节点 token，不填则作为一级节点 |
| `obj_type` | 是 | `doc`, `docx`, `sheet`, `bitable`, `mindnote`, `file` |
| `obj_token` | 是 | 文档 token |

**响应（操作已完成）：**
```json
{
  "code": 0,
  "data": { "wiki_token": "wikbcLZuhp4r9QuJumHzVabcdef" },
  "msg": "success"
}
```

**响应（异步未完成）：**
```json
{
  "code": 0,
  "data": { "task_id": "7037044037068177428-xxx" },
  "msg": "success"
}
```

异步任务通过 `GET /wiki/v2/tasks/{task_id}?task_type=move` 查询结果。

移动后文档权限默认继承父页面，从云空间主页/我的空间/共享空间中消失。

### 查询 Wiki 异步任务结果

```
GET /wiki/v2/tasks/{task_id}?task_type=move
```

仅任务创建者可查询。返回移动完成的节点详情（`space_id`、`node_token`、`obj_token` 等）。

---

## 错误码

| code | 说明 |
|------|------|
| 0 | 成功 |
| 99991400 | 请求参数错误 |
| 99991401 | 认证失败 |
| 99991403 | 无权限 |
| 99991404 | 资源不存在 |
| 99991429 | 请求频率超限 |
| 2890002 | 画板参数无效（常见于 mind_map 子节点创建、格式不正确） |
| 2891001 | 画板服务端内部错误（常见于跨类型 image token 引用） |
| 1061002 | 素材上传参数错误（parent_type 值不合法），或 Drive move/delete 参数不合法 |
| 1061004 | forbidden — 无权限删除/移动文件（常见于 Wiki 管理的文档通过 Drive API 操作） |
| 1061044 | 素材上传父节点不存在 |
| 1770001 | 文档块参数无效 |
