# MinerU API 规范文档

> 官方文档：https://mineru.net/apiManage/docs | 输出字段参考：https://opendatalab.github.io/MinerU/reference/output_files/

---

## 1. 支持的输入文档格式

| 文档类型 | 精准解析 API `/api/v4/` | Agent 轻量 API `/api/v1/agent/` |
|---|---|---|
| PDF | ✅ | ✅ |
| Word (.doc/.docx) | ✅ | ✅（仅 .docx） |
| PowerPoint (.ppt/.pptx) | ✅ | ✅（仅 .pptx） |
| Excel (.xls/.xlsx) | ❌ | ✅ |
| HTML | ✅（需指定 `model_version: "MinerU-HTML"`） | ❌ |
| 图片（png/jpg/jpeg/jp2/webp/gif/bmp） | ✅ | ✅ |

**选型原则：**
- PDF / Word / PPT → 精准解析 API，`model_version: "vlm"`
- Excel → 只能用 Agent 轻量 API（限 ≤10MB / ≤20页）
- 扫描件 → 精准解析 API，`is_ocr: true`

---

## 2. API 接口速查

### 认证

```http
Authorization: Bearer {api_token}
Content-Type: application/json
```

Agent API 的 URL 解析接口（`POST /api/v1/agent/parse/url`）**无需 Token**。

### 精准解析 API（`/api/v4/`）

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/v4/extract/task` | POST | 单文件公网 URL 提交 |
| `/api/v4/extract/task/{task_id}` | GET | 查询单任务状态与结果 |
| `/api/v4/file-urls/batch` | POST | 本地文件上传：申请上传链接（⚠️ 同时传解析参数，上传完自动解析） |
| `/api/v4/extract-results/batch/{batch_id}` | GET | 查询批量结果（本地上传用此接口轮询） |

**本地文件上传正确流程（实测）：**
```
1. POST /api/v4/file-urls/batch
   Body: {"files": [{"name": "x.pdf", "size": N, "model_version": "vlm", "is_ocr": false, ...}]}
   ← 解析参数必须在此步传入 ←
   Response: {"data": {"batch_id": "...", "file_urls": ["presigned_put_url"]}}

2. PUT presigned_put_url（不带 Content-Type，带 Content-Length）
   ← 上传完成后 MinerU 自动开始解析，无需单独提交 ←

3. GET /api/v4/extract-results/batch/{batch_id}  # 用步骤1返回的 batch_id
   Response: {"data": {"extract_result": [{"file_name": "...", "state": "done", "full_zip_url": "..."}]}}
```

### Agent 轻量 API（`/api/v1/agent/`）

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/v1/agent/parse/url` | POST | URL 模式提交（免 Token） |
| `/api/v1/agent/parse/file` | POST | 本地文件上传：申请上传链接（需 `file_name`/`file_size` 字段，返回 `file_url`） |
| `/api/v1/agent/parse/{task_id}` | GET | 查询任务结果 |

---

## 3. 请求参数

### 3.1 精准解析 API 提交参数（`POST /api/v4/extract/task`）

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `url` | string | **是** | — | 文件公网 URL |
| `model_version` | string | 否 | `"pipeline"` | `pipeline` / `vlm`（推荐）/ `MinerU-HTML` |
| `is_ocr` | bool | 否 | `false` | 扫描件必须开启 |
| `enable_formula` | bool | 否 | `true` | 公式识别（输出 LaTeX） |
| `enable_table` | bool | 否 | `true` | 表格结构识别 |
| `language` | string | 否 | `"ch"` | `ch` / `en` / `japan` / `korean` |
| `page_ranges` | string | 否 | 全文 | 如 `"1-10"` / `"2,4-6"` / `"2--2"` |
| `extra_formats` | [string] | 否 | — | 额外导出：`"docx"` / `"html"` / `"latex"` |
| `data_id` | string | 否 | — | 业务数据 ID，字母/数字/`_`/`-`/`.`，≤128字符 |
| `callback` | string | 否 | — | 解析完成回调 URL |
| `no_cache` | bool | 否 | `false` | 绕过缓存强制重新解析 |

### 3.2 Agent 轻量 API 提交参数（`POST /api/v1/agent/parse/url`）

| 参数名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `url` | string | **是** | 文件公网 URL |
| `language` | string | 否 | 同上 |
| `enable_table` | bool | 否 | 默认 true |
| `is_ocr` | bool | 否 | 默认 false |
| `enable_formula` | bool | 否 | 默认 true |
| `page_range` | string | 否 | **注意：参数名与精准 API 不同，无 `s`** |

### 3.3 任务状态枚举

**精准解析 API：** `pending` → `converting`（Office文档）→ `running` → `done` / `failed`

**Agent API：** `waiting-file` → `uploading` → `pending` → `running` → `done` / `failed`

完成后精准 API 返回 `full_zip_url`，Agent API 返回 `markdown_url`。

---

## 4. 输出文件规范

### 4.1 精准解析 API 输出（ZIP 包）

```
{task_id}.zip
├── full.md                        # Markdown 全文
├── {filename}_content_list.json   # 结构化内容块列表（RAG 分块主要使用）
├── {filename}_middle.json         # 版面布局详细信息
├── {filename}_model.json          # 模型检测原始结果
├── images/                        # 提取的图片/表格截图/公式截图
│   └── {sha256}.jpg               # 文件名为内容 SHA256 哈希值
├── {filename}.docx                # extra_formats 包含 "docx" 时存在
├── {filename}.html                # extra_formats 包含 "html" 时存在
└── {filename}.tex                 # extra_formats 包含 "latex" 时存在
```

**Agent 轻量 API 输出：** 仅一个 `markdown_url` CDN 直链，无 JSON 结构文件，无图片文件。

---

### 4.2 `full.md` 格式规范

各元素的 Markdown 表示：

| 元素 | 格式 | 示例 |
|---|---|---|
| 标题 | ATX 标题 `#` ~ `######` | `# 一级标题` |
| 正文段落 | 纯文本，段间空行 | — |
| 行内公式 | `$...$` | `质能方程 $E = mc^2$` |
| 块级公式 | `$$...$$` 独占一行 | `$$\int e^x dx$$` |
| 表格 | 标准 GFM 表格 | `\| A \| B \|` / 复杂合并单元格用 HTML `<table>` |
| 图片 | `![caption](images/{sha256}.jpg)` | — |
| 列表 | `-` 无序 / `1.` 有序 | — |
| 代码块 | 标准代码围栏 ` ``` ` | — |

---

### 4.3 `{filename}_content_list.json` 字段规范

`full.md` 的结构化版本，按**阅读顺序**平铺所有内容块，是 RAG 分块入库的核心文件。

#### 通用字段（所有 type 均有）

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | string | 内容块类型，见下表 |
| `page_idx` | int | 所在页码（从 **0** 开始） |
| `bbox` | [int,int,int,int] | `[x0,y0,x1,y1]`，值域 **0–1000**（已归一化，左上角为原点） |

#### `type` 枚举值与专有字段

| type | 含义 | 专有字段 |
|---|---|---|
| `text` | 正文段落 | `text`（string），`text_level`（0=正文，1=一级标题） |
| `title` | 标题 | `text`，`text_level`（1~N） |
| `image` | 图片 | `img_path`，`image_caption`（[]string），`image_footnote`（[]string） |
| `table` | 表格 | `img_path`，`table_caption`（[]string），`table_footnote`（[]string），`table_body`（HTML string） |
| `chart` | 图表 | `img_path`，`image_caption`（[]string） |
| `equation` | 独立公式 | `img_path`，`text`（LaTeX with `$$`），`text_format`（固定 `"latex"`） |
| `code` | 代码块 | `sub_type`（`"code"` / `"algorithm"`），`code_body`（string），`code_caption`（[]string） |
| `list` | 列表 | `text` |
| `seal` | 印章 | `img_path` |
| `header` | 页眉 | `text` |
| `footer` | 页脚 | `text` |
| `page_number` | 页码 | `text` |
| `aside_text` | 旁注 | `text` |
| `page_footnote` | 脚注 | `text` |

#### 各类型完整示例

```json
// text / title
{"type": "text", "text": "正文段落内容", "text_level": 0, "bbox": [62,480,946,904], "page_idx": 0}
{"type": "title", "text": "第一章 引言", "text_level": 1, "bbox": [62,100,500,140], "page_idx": 0}

// image
{
  "type": "image",
  "img_path": "images/a8ecda1c69b27e4f79fce1589175a9d721cbdc1cf78b4cc06a015f3746f6b9d8.jpg",
  "image_caption": ["Fig. 1. Annual flow duration curves."],
  "image_footnote": [],
  "bbox": [62,480,946,904],
  "page_idx": 1
}

// table
{
  "type": "table",
  "img_path": "images/e3cb413394a475e555807ffdad913435940ec637873d673ee1b039e3bc3496d0.jpg",
  "table_caption": ["Table 2 Significance of the rainfall and time terms"],
  "table_footnote": ["* indicates significance at the 5% level"],
  "table_body": "<html><body><table><tr><td rowspan=\"2\">Site</td><td colspan=\"10\">Percentile</td></tr>...</table></body></html>",
  "bbox": [62,480,946,904],
  "page_idx": 5
}

// equation
{
  "type": "equation",
  "img_path": "images/181ea56ef185060d04bf4e274685f3e072e922e7b839f093d482c29bf89b71e8.jpg",
  "text": "$$\nQ _ { \\% } = f ( P ) + g ( T )\n$$",
  "text_format": "latex",
  "bbox": [62,480,946,904],
  "page_idx": 2
}
```

#### bbox 坐标还原

```python
# content_list 的 bbox 值域为 0-1000，还原为页面实际像素坐标：
x0_px = bbox[0] / 1000 * page_width_px
y0_px = bbox[1] / 1000 * page_height_px
x1_px = bbox[2] / 1000 * page_width_px
y1_px = bbox[3] / 1000 * page_height_px
```

---

### 4.4 `{filename}_middle.json` 字段规范（版面布局信息）

包含每页的完整版面分析结果，是精确坐标提取和版面结构理解的核心文件。

#### 顶层结构

| 字段 | 类型 | 说明 |
|---|---|---|
| `pdf_info` | list | 每页为一个元素 |
| `_backend` | string | `"pipeline"` / `"vlm"` / `"office"` |
| `_version_name` | string | MinerU 版本号 |

#### 单页（`pdf_info[n]`）字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `page_idx` | int | 页码，从 0 开始 |
| `page_size` | [float, float] | 页面宽高，**单位 PDF 点（pt）**，标准 A4 = [595.0, 842.0] |
| `para_blocks` | list | **主要使用**：合并后段落块，按阅读顺序排列 |
| `preproc_blocks` | list | 预处理原始块（未合并） |
| `layout_bboxes` | list | 版面区域划分（栏、列信息） |
| `images` | list | 本页图片块 |
| `tables` | list | 本页表格块 |
| `interline_equations` | list | 本页行间公式块 |
| `discarded_blocks` | list | 丢弃的噪声块 |

#### `para_blocks` 中 block 结构（三级嵌套）

```
block（段落块）
  ├── type: string          # 见下方枚举
  ├── bbox: [x0,y0,x1,y1]  # Pipeline=PDF pt；VLM=归一化[0,1]
  └── lines: []
        ├── bbox
        └── spans: []
              ├── bbox
              ├── content: string   # 文本内容（文本类 span）
              ├── img_path: string  # 图片路径（图片类 span）
              ├── type: string      # text / inline_equation / image / table
              └── score: float      # 识别置信度
```

**block `type` 枚举（11 种）：**

| type | 含义 |
|---|---|
| `text` | 普通文本段落 |
| `title` | 标题 |
| `list` | 列表 |
| `index` | 目录/索引 |
| `image_body` | 图片主体 |
| `image_caption` | 图片标题 |
| `image_footnote` | 图片脚注 |
| `table_body` | 表格主体 |
| `table_caption` | 表格标题 |
| `table_footnote` | 表格脚注 |
| `interline_equation` | 行间独立公式 |

#### `layout_bboxes` 版面区域

```json
{"layout_bbox": [52, 61, 294, 731], "layout_label": "V", "sub_layout": []}
```

`layout_label`: `"V"` 单栏垂直布局，`"H"` 水平分栏，多栏时 `sub_layout` 有值。

#### 坐标系对照

| 文件 | 后端 | bbox 单位 |
|---|---|---|
| `content_list.json` | 全部 | 0–1000 归一化整数 |
| `middle.json` | pipeline | PDF 点（pt） |
| `middle.json` | vlm | 0–1 归一化浮点 |
| `model.json` | pipeline | 像素（px） |
| `model.json` | vlm | 0–1 归一化浮点 |

---

### 4.5 `{filename}_model.json` 字段规范（模型检测原始结果）

#### Pipeline 后端（平面数组）

```json
[
  {"cls_id": 6,  "label": "doc_title", "score": 0.9751, "bbox": [275,181,1512,292], "index": 3},
  {"cls_id": 22, "label": "text",      "score": 0.9217, "bbox": [275,330,524,370],  "index": 4}
]
```

| 字段 | 说明 |
|---|---|
| `cls_id` | 模型类别 ID |
| `label` | 检测框标签（见下表） |
| `score` | 置信度 0–1 |
| `bbox` | 像素坐标 `[x0,y0,x1,y1]` |
| `index` | 阅读顺序 |

**`label` 枚举：** `text` / `title` / `doc_title` / `list` / `table` / `image` / `equation` / `figure_caption` / `table_caption` / `header` / `footer` / `page_number` / `aside_text` / `code`

#### VLM 后端（二维数组：页面列表 → 块列表）

```json
[
  [
    {"type": "header", "bbox": [0.077,0.095,0.18,0.181], "angle": 0, "score": null, "content": "ELSEVIER"},
    {"type": "title",  "bbox": [0.157,0.228,0.833,0.253], "angle": 0, "score": null, "content": "论文标题"}
  ]
]
```

| 字段 | 说明 |
|---|---|
| `type` | 内容类型（同 content_list type） |
| `bbox` | 0–1 归一化坐标 |
| `angle` | 文本旋转角度（0/90/180/270） |
| `score` | VLM 模式通常为 null |
| `content` | 识别文本 |

---

### 4.6 输出文件用途速查

| 文件 | 主要用途 | 坐标单位 |
|---|---|---|
| `full.md` | 文本检索、LLM 输入、快速预览 | 无 |
| `*_content_list.json` | **RAG 分块入库、多模态检索** | 0–1000 |
| `*_middle.json` | 精确版面分析、坐标提取、跨块关系 | pt（pipeline）/ 0-1（vlm） |
| `*_model.json` | 调试、重新后处理 | px（pipeline）/ 0-1（vlm） |
| `images/*.jpg` | 图片/表格/公式的原始截图 | — |

---

## 5. 错误码

| 错误码 | 说明 |
|---|---|
| `0` | 成功 |
| `A0202` | Token 错误 |
| `A0211` | Token 过期 |
| `-10001` | 服务内部异常 |
| `-10002` | 请求参数错误 |
| `-60003` | 空文件 |
| `-60004` | 文件超限（>200MB） |
| `-60005` | 页数超限（>600页） |
| `-60006` | 不支持的文件格式 |
| `-60018` | 每日任务数已达上限 |
| `-30001` | Agent API：文件超限（>10MB） |
| `-30002` | Agent API：格式不支持 |
| `-30003` | Agent API：页数超限（>20页） |

---

## 6. 限制说明

| 项目 | 精准解析 API | Agent 轻量 API |
|---|---|---|
| 单文件大小 | ≤ 200 MB | ≤ 10 MB |
| 单文件页数 | ≤ 600 页 | ≤ 20 页 |
| 每日高优先级页数 | 2000页/账号（超出后降优先级） | — |
| 批量上传单次上限 | 200 个文件 | — |
| 上传链接有效期 | 24 小时 | — |

---

## 7. MVP 测试要点

### 最小配置

```
MINERU_API_KEY=your_token   # 精准 API 必须；Agent URL 模式免 token
pip install requests
```

### 推荐测试请求

```json
POST /api/v4/extract/task
{
  "url": "https://cdn-mineru.openxlab.org.cn/demo/example.pdf",
  "model_version": "vlm",
  "enable_table": true,
  "enable_formula": true,
  "language": "ch"
}
```

### 输出验证清单

| 验证项 | 检查方式 |
|---|---|
| `full.md` 非空，含标题 `#` | `len(markdown) > 100` |
| `content_list.json` 有内容块 | `len(content_list) > 0` |
| bbox 坐标在 0–1000 | `all(0 <= v <= 1000 for v in bbox)` |
| image 的 `img_path` 为 SHA256 格式 | 文件名长度 64 位十六进制 + `.jpg` |
| table 有 `table_body` HTML | `"<table>"` 在 `table_body` 中 |
| equation 有 LaTeX 文本 | `text_format == "latex"` |
| `middle.json` 有 `para_blocks` | `len(para_blocks) > 0` |
| images/ 目录有 jpg 文件 | ZIP 内 `images/` 前缀文件非空 |

### 文档类型测试矩阵

| 文档类型 | API | 关键参数 |
|---|---|---|
| PDF 数字版 | 精准 | `is_ocr: false` |
| PDF 扫描件 | 精准 | `is_ocr: true` |
| Word / PPT | 精准 | `is_ocr: false`（state 会经过 `converting`） |
| Excel | Agent | `page_range` 注意无 `s` |
| 图片 | 精准 | `is_ocr: true` |
