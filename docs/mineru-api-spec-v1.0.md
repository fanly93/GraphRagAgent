# MinerU API 规范文档 v1.0

> 官方文档：https://mineru.net/apiManage/docs
> 本文档基于官方文档 + **实际测试输出（2026-04-12，MinerU v2.7.6）** 综合整理。
> 当官方文档与实际输出存在冲突时，**以实际输出为准**。

---

## 零、快速启动（必读）

### 0.1 虚拟环境（强制要求）

MinerU 解析服务运行在独立虚拟环境中，**启动前必须激活**，禁止使用系统 Python 直接执行。

```bash
# 进入模块目录
cd /Users/tanglin/VibeCoding/GraphRagAgent/mineru_parser

# 激活虚拟环境
source .venv/bin/activate

# 验证（应显示 .venv 路径）
which python
# → .../mineru_parser/.venv/bin/python
```

| 项目 | 值 |
|---|---|
| 虚拟环境路径 | `mineru_parser/.venv/` |
| Python 版本 | 3.13.12 |
| 解释器 | `.venv/bin/python` |

**首次使用（.venv 不存在时）：**

```bash
cd /Users/tanglin/VibeCoding/GraphRagAgent/mineru_parser
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**配置 API Token（.env 文件）：**

```bash
# 编辑 .env，填入从 https://mineru.net/apiManage/openToken 获取的 Token
MINERU_API_TOKEN=eyJ...
```

---

### 0.2 Pipeline 启动步骤

```bash
# Step 1：进入目录并激活虚拟环境
cd /Users/tanglin/VibeCoding/GraphRagAgent/mineru_parser
source .venv/bin/activate

# Step 2：将待解析文件放入 input/ 目录
# 支持：PDF / Word(.docx) / PPT(.pptx) / Excel(.xlsx) / 图片(.png/.jpg 等)
cp /path/to/your/document.pdf input/

# Step 3：执行解析（解析完成后结果自动保存到 output/）
python run_parser.py

# Step 4（可选）：附带输出规范验证
python run_parser.py --verify
```

### 0.3 常用命令速查

```bash
# 预览文件路由，不实际调用 API
python run_parser.py --dry-run

# 解析指定文件（不扫描 input/）
python run_parser.py input/document.pdf input/data.xlsx

# 临时指定 Token（不改 .env）
python run_parser.py --token YOUR_TOKEN
```

### 0.4 解析结果位置

```
output/
└── {文件名}/
    ├── {uuid}_content_list.json   # RAG 分块核心文件
    ├── {uuid}_origin.pdf          # 原始文件副本
    ├── full.md                    # Markdown 全文
    ├── layout.json                # 版面布局分析
    └── images/                    # 提取的图片（SHA256.jpg）
```

> Excel 文件使用 Agent API，仅生成 `full.md`，无其他文件。

---

## 一、Pipeline 设计思路与完整执行流程

### 1.1 整体思路

MinerU 是云端文档解析服务，接收本地文件或公网 URL，输出结构化的 Markdown + JSON 内容块，供 RAG 系统分块入库。

```
本地文件
   │
   ▼
[格式路由]────────────────────────────────────────────────────────┐
   │  PDF / Word / PPT / HTML / 图片                              │  Excel
   ▼                                                              ▼
精准解析 API /api/v4/                                   Agent 轻量 API /api/v1/agent/
   │                                                              │
   ├─1. POST /api/v4/file-urls/batch                              ├─1. POST /api/v1/agent/parse/file
   │   （同时传解析参数 → 返回 batch_id + presigned_url）          │   （返回 task_id + file_url）
   │                                                              │
   ├─2. PUT presigned_url（上传文件，无需 Content-Type）            ├─2. PUT file_url（上传文件）
   │   （上传完成后 MinerU 自动开始解析，无需单独提交步骤）          │
   │                                                              ├─3. GET /api/v1/agent/parse/{task_id}
   ├─3. GET /api/v4/extract-results/batch/{batch_id}              │   （轮询直到 state=done）
   │   （轮询直到 state=done）                                     │
   │                                                              ▼
   ├─4. 下载 full_zip_url → 本地 ZIP                             下载 markdown_url → full.md
   │
   ├─5. 解压 ZIP → output/{文件名}/
   │
   └─6. 读取 {uuid}_content_list.json 进行 RAG 分块
```

### 1.2 关键设计决策

| 决策点 | 说明 |
|---|---|
| 格式路由 | Excel 只能用 Agent API；其余格式用精准 API |
| 解析参数时机 | **精准 API**：解析参数必须在申请上传链接时一并传入（步骤1），不能在后续单独传 |
| OSS 上传注意 | PUT 时**不能携带 Content-Type**（会导致 OSS 签名校验失败 403）；**必须携带 Content-Length** |
| RAG 主文件 | `{uuid}_content_list.json` 是 RAG 分块的核心文件；`full.md` 用于快速预览和全文检索 |
| Agent API 限制 | 仅输出 Markdown（无结构化 JSON、无图片），适合 Excel 等简单表格场景 |

---

## 二、运行脚本位置与执行步骤

### 2.1 项目目录结构

```
GraphRagAgent/
├── docs/
│   ├── mineru-api-spec.md          # 旧版规范
│   └── mineru-api-spec-v1.0.md     # 本文档
├── mineru_parser/                  # MinerU 解析模块
│   ├── input/                      # ← 待解析文件放这里
│   ├── output/                     # ← 解析结果自动保存到这里
│   │   └── {文件名}/
│   │       ├── {uuid}_content_list.json
│   │       ├── {uuid}_origin.pdf
│   │       ├── full.md
│   │       ├── layout.json
│   │       └── images/
│   ├── .env                        # ← 填写 MINERU_API_TOKEN
│   ├── .env.example
│   ├── requirements.txt
│   ├── run_parser.py               # 主入口脚本
│   ├── config.py                   # 配置加载
│   ├── models.py                   # 数据模型
│   ├── client.py                   # API 客户端
│   └── pipeline.py                 # Pipeline 编排
```

### 2.2 环境配置

> ⚠️ **必须在虚拟环境中运行**，详见 [零、快速启动](#零快速启动必读)。

```bash
cd GraphRagAgent/mineru_parser

# ── 首次初始化（.venv 不存在时）──────────────────────
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# ── 日常启动（每次新开终端后执行）────────────────────
source .venv/bin/activate          # macOS/Linux
# .venv\Scripts\activate.ps1       # Windows PowerShell

# ── 验证虚拟环境已激活 ────────────────────────────────
which python                       # 应显示 .venv/bin/python
python -c "import requests; print('OK')"

# ── 填写 API Token（只需配置一次）───────────────────
# 编辑 .env 文件：
# MINERU_API_TOKEN=eyJ...
# Token 获取地址：https://mineru.net/apiManage/openToken
```

### 2.3 运行命令

```bash
# 解析 input/ 目录中所有文件（主要用法）
python run_parser.py

# 解析后执行输出规范验证
python run_parser.py --verify

# 仅预览文件路由，不实际调用 API
python run_parser.py --dry-run

# 解析指定文件
python run_parser.py path/to/file.pdf path/to/data.xlsx

# 临时使用指定 token（覆盖 .env）
python run_parser.py --token YOUR_TOKEN
```

### 2.4 输出目录示例

解析完成后，每个文件在 `output/` 下生成独立子目录：

```
output/
├── 0.LangChain技术生态介绍/
│   ├── 5d48e83e-..._content_list.json   # 结构化块列表（87块）
│   ├── 5d48e83e-..._origin.pdf          # 原始文件副本
│   ├── full.md                          # Markdown 全文（164行）
│   ├── layout.json                      # 版面布局（8页）
│   └── images/                          # 提取图片（13张 SHA256.jpg）
├── 数组/                                # Word 文档
├── 图1/                                 # PNG 图片
├── 测试图片/                            # PNG 图片
└── 销售数据统计/                        # Excel（Agent API）
    └── full.md                          # 仅 Markdown，无其他文件
```

---

## 三、支持的输入格式与 API 路由

| 文档类型 | 精准解析 API `/api/v4/` | Agent 轻量 API `/api/v1/agent/` |
|---|---|---|
| PDF | ✅ | ✅ |
| Word (.doc/.docx) | ✅ | ✅（仅 .docx） |
| PowerPoint (.ppt/.pptx) | ✅ | ✅（仅 .pptx） |
| Excel (.xls/.xlsx) | ❌ | ✅ |
| HTML | ✅（需 `model_version: "MinerU-HTML"`） | ❌ |
| 图片（png/jpg/jpeg/jp2/webp/gif/bmp） | ✅ | ✅ |

**路由原则：**
- PDF / Word / PPT / HTML / 图片 → **精准解析 API**，推荐 `model_version: "vlm"`
- Excel → 只能用 **Agent 轻量 API**（限 ≤10MB / ≤20页）
- 扫描件 / 纯图片 → 精准 API + `is_ocr: true`（图片格式自动开启）
- Word / PPT 解析时 state 会经过 `converting` 阶段（Office 转换中）

---

## 四、API 认证

```http
Authorization: Bearer {api_token}
Content-Type: application/json
```

- Agent API 的 URL 解析（`POST /api/v1/agent/parse/url`）**无需 Token**
- Token 获取地址：https://mineru.net/apiManage/openToken

---

## 五、精准解析 API 接口规范（`/api/v4/`）

### 5.1 本地文件上传解析（推荐）

#### Step 1：申请上传链接 + 提交解析参数

```
POST https://mineru.net/api/v4/file-urls/batch
Authorization: Bearer {token}
Content-Type: application/json
```

**请求体（`files` 数组，单次 ≤ 200 个）：**

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `name` | string | **是** | — | 文件名（含扩展名） |
| `size` | int | **是** | — | 文件字节数 |
| `model_version` | string | 否 | `"pipeline"` | `pipeline` / `vlm`（推荐）/ `MinerU-HTML` |
| `is_ocr` | bool | 否 | `false` | 扫描件/图片必须开启 |
| `enable_formula` | bool | 否 | `true` | 公式识别（输出 LaTeX） |
| `enable_table` | bool | 否 | `true` | 表格结构识别 |
| `language` | string | 否 | `"ch"` | 见语言代码表 |
| `page_ranges` | string | 否 | 全文 | 如 `"1-10"` / `"2,4-6"` / `"2--2"` |
| `extra_formats` | [string] | 否 | — | 额外导出：`"docx"` / `"html"` / `"latex"` |
| `data_id` | string | 否 | — | 业务 ID，字母/数字/`_`/`-`/`.`，≤128字符 |
| `callback` | string | 否 | — | 解析完成回调 URL |
| `no_cache` | bool | 否 | `false` | 绕过缓存强制重新解析 |
| `seed` | string | 否 | — | 用于缓存命中控制，≤64字符 |
| `cache_tolerance` | int | 否 | `900` | 缓存容忍秒数 |

**⚠️ 重要：解析参数必须在此步传入，上传完成后无需再调用其他提交接口。**

**响应体：**

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "batch_id": "095ace06-30d0-4e44-b92c-de0346e12298",
    "file_urls": [
      "https://mineru.oss-cn-shanghai.aliyuncs.com/api-upload/extract/2026-04-12/{batch_id}/{uuid}.pdf?Expires=...&Signature=..."
    ]
  }
}
```

- `batch_id`：后续轮询使用（与上传 batch_id 相同，无需单独提交）
- `file_urls`：字符串数组，每个元素为一个文件的 OSS 预签名 PUT URL

#### Step 2：上传文件到 OSS

```
PUT {presigned_url}
Content-Length: {file_size_bytes}
（不携带 Content-Type！）

[文件字节流]
```

**⚠️ 注意：**
- **不能携带 `Content-Type` 头**：OSS 预签名签名不含该头，携带后签名不匹配返回 403
- **必须携带 `Content-Length` 头**：缺失时 OSS 接收截断内容，MinerU 报"文件损坏"

上传成功返回 HTTP 200，响应头含 `ETag`（文件 MD5）。

#### Step 3：轮询解析结果

上传完成后 MinerU 自动开始解析，用 Step 1 的 `batch_id` 轮询：

```
GET https://mineru.net/api/v4/extract-results/batch/{batch_id}
Authorization: Bearer {token}
```

**响应体：**

```json
{
  "code": 0,
  "data": {
    "batch_id": "095ace06-30d0-4e44-b92c-de0346e12298",
    "extract_result": [
      {
        "file_name": "0.LangChain技术生态介绍.pdf",
        "state": "done",
        "full_zip_url": "https://cdn-mineru.openxlab.org.cn/pdf/2026-04-12/{uuid}.zip",
        "err_msg": ""
      }
    ]
  }
}
```

**`state` 枚举（精准 API）：**

| state | 含义 |
|---|---|
| `waiting-file` | 等待文件上传（文件尚未 PUT） |
| `pending` | 已入队，等待解析 |
| `converting` | Office 文档转换中（Word/PPT 独有） |
| `running` | 解析进行中 |
| `done` | 解析完成，`full_zip_url` 可用 |
| `failed` | 解析失败，查看 `err_msg` |

**轮询建议：** 每 10 秒一次，超时 600 秒。

#### Step 4：下载并解压 ZIP

```python
# 下载 full_zip_url 到本地
# 解压后得到如下文件结构（见第六节）
```

---

### 5.2 公网 URL 单文件解析

```
POST https://mineru.net/api/v4/extract/task
Authorization: Bearer {token}
Content-Type: application/json
```

```json
{
  "url": "https://example.com/file.pdf",
  "model_version": "vlm",
  "enable_table": true,
  "enable_formula": true,
  "language": "ch"
}
```

响应：`{"data": {"task_id": "..."}}`

轮询：`GET /api/v4/extract/task/{task_id}`

```json
{
  "data": {
    "task_id": "...",
    "state": "done",
    "full_zip_url": "https://cdn-mineru.openxlab.org.cn/...",
    "err_msg": "",
    "extract_progress": {}
  }
}
```

---

## 六、精准解析 API 输出文件规范（实测）

### 6.1 ZIP 包内文件列表

```
{uuid}.zip
├── {uuid}_content_list.json    # 结构化内容块（RAG 核心文件）
├── {uuid}_origin.pdf           # 原始文件副本（上传文件的镜像）
├── full.md                     # Markdown 全文
├── layout.json                 # 版面布局分析（含坐标、结构层次）
└── images/
    └── {sha256_64hex}.jpg      # 提取的图片/表格截图/公式截图
```

**⚠️ 与旧规范的差异（以实测为准）：**

| 旧规范（错误） | 实际输出（正确） |
|---|---|
| `{filename}_content_list.json` | `{uuid}_content_list.json`（UUID 前缀） |
| `{filename}_middle.json` | **不存在**，对应内容在 `layout.json` 中 |
| `{filename}_model.json` | **不存在** |
| ——（未记录） | `{uuid}_origin.pdf`（原始文件副本） |
| ——（未记录） | `layout.json`（版面分析文件） |

---

### 6.2 `full.md` 格式（实测）

各元素 Markdown 表示：

| 元素 | 格式 | 实测示例 |
|---|---|---|
| 标题 | `# 标题` ~ `###### 标题` | `# LangChain快速入门与Agent开发实战-Part 1` |
| 正文段落 | 纯文本，段间空行 | — |
| 图片 | `![](images/{sha256}.jpg)` | alt 文本为空 |
| 表格 | 标准 GFM `\| \|` | — |
| 行内公式 | `$...$` | `$E = mc^2$` |
| 块级公式 | `$$\n...\n$$` | — |
| 列表 | `-` 无序 / `1.` 有序 | — |
| 代码块 | ` ``` ` 围栏 | — |

---

### 6.3 `{uuid}_content_list.json` 规范（实测）

`full.md` 的结构化版本，按**阅读顺序**平铺所有内容块，是 **RAG 分块入库的核心文件**。

#### 通用字段（所有 type 均有）

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | string | 内容块类型，见下表 |
| `page_idx` | int | 所在页码，从 **0** 开始 |
| `bbox` | [int,int,int,int] | `[x0,y0,x1,y1]`，**0–1000 归一化整数**（相对页面宽高） |

**坐标说明：** `bbox` 值域 0–1000，表示占页面宽/高的千分比。还原公式：
```python
x0_px = bbox[0] / 1000 * page_width_px
y0_px = bbox[1] / 1000 * page_height_px
```

#### `type` 枚举与专有字段（实测确认）

| type | 含义 | 专有字段 | 实测 |
|---|---|---|---|
| `text` | 正文 / 标题文本 | `text`（string），`text_level`（int，仅标题有，≥1） | ✅ |
| `image` | 图片 | `img_path`（`images/{sha256}.jpg`），`image_caption`（[]string），`image_footnote`（[]string） | ✅ |
| `table` | 表格 | `img_path`，`table_caption`（[]string），`table_footnote`（[]string），`table_body`（HTML string） | ✅ |
| `discarded` | 噪声/页眉页脚等丢弃内容 | `text` | ✅（新增） |
| `equation` | 独立公式 | `img_path`，`text`（LaTeX with `$$`），`text_format`（`"latex"`） | 未在测试文档触发 |
| `code` | 代码块 | `sub_type`（`"code"`/`"algorithm"`），`code_body`（string），`code_caption`（[]string） | 未在测试文档触发 |
| `list` | 列表 | `text` | 未在测试文档触发 |
| `chart` | 图表 | `img_path`，`image_caption`（[]string） | 未在测试文档触发 |
| `seal` | 印章 | `img_path` | 未在测试文档触发 |
| `header` | 页眉 | `text` | 未在测试文档触发 |
| `footer` | 页脚 | `text` | 未在测试文档触发 |
| `page_number` | 页码 | `text` | 未在测试文档触发 |
| `aside_text` | 旁注 | `text` | 未在测试文档触发 |
| `page_footnote` | 脚注 | `text` | 未在测试文档触发 |

**`text_level` 说明：**
- 标题块（heading）：`text_level` 为 1（一级）~ N（N级）
- 正文块：`text_level` 字段**缺失**（不是 0，而是字段不存在）
- 实测中 `text_level` 仅在部分 text 块中出现（标题才有）

**`table_body` HTML 格式（实测）：**
```html
<table>
  <tr><td rowspan=1 colspan=1>模块类别</td><td rowspan=1 colspan=1>示例功能</td></tr>
  ...
</table>
```
> ⚠️ 旧规范错误：实际**无** `<html><body>` 外层包装，直接是 `<table>` 标签

#### 实测完整示例

```json
// text（正文，无 text_level）
{
  "type": "text",
  "text": "本期公开课，我将为大家详细讲解元老级Agent开发工具——LangChain。",
  "bbox": [154, 159, 684, 175],
  "page_idx": 0
}

// text（标题，有 text_level）
{
  "type": "text",
  "text": "LangChain快速入门与Agent开发实战-Part 1",
  "text_level": 1,
  "bbox": [124, 45, 852, 104],
  "page_idx": 0
}

// image
{
  "type": "image",
  "img_path": "images/12eaa9f90274b5c93ff0f7f118c508105bc72c9c1710a11408106e2dc24cb812.jpg",
  "image_caption": [],
  "image_footnote": [],
  "bbox": [122, 478, 877, 744],
  "page_idx": 0
}

// table
{
  "type": "table",
  "img_path": "images/be83fdf1af676509deccabfe3d259fe99eebac741162b5c309431d2f8c37f382.jpg",
  "table_caption": [],
  "table_footnote": [],
  "table_body": "<table><tr><td rowspan=1 colspan=1>模块类别</td>...</table>",
  "bbox": [159, 456, 877, 729],
  "page_idx": 2
}

// discarded（噪声内容，实测新增）
{
  "type": "discarded",
  "text": "minimaxir.com +15",
  "bbox": [208, 918, 287, 927],
  "page_idx": 1
}
```

---

### 6.4 `layout.json` 规范（实测，对应旧规范的 `middle.json`）

包含每页完整版面分析结果，bbox 使用**原始坐标单位**（PDF 文档为 pt，图片为像素）。

#### 顶层结构

| 字段 | 类型 | 说明 |
|---|---|---|
| `pdf_info` | list | 每页为一个元素 |
| `_backend` | string | `"pipeline"`（注：即使请求 vlm 模型，此字段仍为 pipeline） |
| `_version_name` | string | MinerU 版本，实测为 `"2.7.6"` |

#### 单页（`pdf_info[n]`）字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `page_idx` | int | 页码，从 0 开始 |
| `page_size` | [float, float] | 页面 `[宽, 高]`，**PDF 为 pt，图片为像素** |
| `para_blocks` | list | 合并后段落块，阅读顺序排列（主要使用） |
| `preproc_blocks` | list | 预处理原始块（合并前） |
| `discarded_blocks` | list | 丢弃的噪声块 |

> ⚠️ 旧规范中的 `layout_bboxes`、`images`、`tables`、`interline_equations` 字段**实测不存在**

**`page_size` 参考值：**

| 文档类型 | 实测 page_size |
|---|---|
| PDF A4 | `[595, 842]` pt |
| Word US Letter | `[612, 792]` pt |
| PNG 图片 | 实际像素尺寸，如 `[1422, 776]` |

#### `para_blocks` 中 block 结构（两种变体）

**变体 1：文本类（text / title / list / discarded）**

```json
{
  "type": "text",
  "bbox": [74, 38, 507, 88],
  "index": 0.5,
  "lines": [
    {
      "bbox": [70, 39, 509, 66],
      "index": 0,
      "spans": [
        {
          "bbox": [70, 39, 509, 66],
          "score": 1.0,
          "content": "LangChain快速入门与Agent开发实战-Part",
          "type": "text"
        }
      ]
    }
  ]
}
```

**变体 2：复合类（image / table，含子块）**

```json
{
  "type": "image",
  "bbox": [73, 403, 522, 627],
  "blocks": [
    {
      "type": "image_body",
      "bbox": [73, 403, 522, 627],
      "group_id": 0,
      "index": 18,
      "lines": [
        {
          "bbox": [73, 403, 522, 627],
          "spans": [
            {
              "bbox": [73, 403, 522, 627],
              "score": 0.888,
              "type": "image",
              "image_path": "12eaa9f90274b5c93ff0f7f118c508105bc72c9c1710a11408106e2dc24cb812.jpg"
            }
          ]
        }
      ],
      "virtual_lines": []
    }
  ]
}
```

```json
{
  "type": "table",
  "bbox": [95, 384, 522, 614],
  "blocks": [
    {
      "type": "table_body",
      "bbox": [95, 384, 522, 614],
      "group_id": 0,
      "lines": [
        {
          "bbox": [95, 384, 522, 614],
          "spans": [
            {
              "bbox": [95, 384, 522, 614],
              "score": 0.983,
              "html": "<table><tr><td rowspan=1 colspan=1>...</td></tr></table>"
            }
          ]
        }
      ]
    }
  ]
}
```

**字段说明对照：**

| 字段 | 位置 | 说明 |
|---|---|---|
| `type` | block | 块类型：`text`/`title`/`list`/`image`/`table`/`discarded` |
| `bbox` | block/line/span | 坐标 `[x0,y0,x1,y1]`，单位同 `page_size`（PDF pt / 图片 px） |
| `index` | block/line | 阅读顺序序号（浮点） |
| `lines` | 文本类 block | 行列表（文本类直接有） |
| `blocks` | 复合类 block | 子块列表（image/table 有，内含 `image_body`/`table_body`） |
| `spans[].content` | 文本 span | 文本内容 |
| `spans[].type` | 文本 span | `"text"` / `"inline_equation"` / `"image"` |
| `spans[].image_path` | 图片 span | SHA256 文件名（**无 `images/` 前缀**，与 content_list 不同） |
| `spans[].html` | 表格 span | 表格 HTML 字符串 |
| `spans[].score` | span | 识别置信度 0–1 |
| `group_id` | sub-block | 同组内容 ID |
| `virtual_lines` | sub-block | 虚拟行（辅助定位用） |

**坐标系对照：**

| 文件 | bbox 单位 |
|---|---|
| `content_list.json` | **0–1000 归一化整数**（相对页面） |
| `layout.json`（PDF） | **PDF pt**（与 page_size 相同量纲） |
| `layout.json`（PNG） | **像素 px**（与 page_size 相同量纲） |

---

### 6.5 `images/` 目录

- 文件命名：`{sha256_64位十六进制}.jpg`（内容哈希，固定 `.jpg` 扩展名）
- 内容：图片区域截图、表格截图、公式截图
- content_list 引用路径：`images/{sha256}.jpg`
- layout.json 引用路径：仅 `{sha256}.jpg`（无目录前缀）

---

### 6.6 输出文件用途速查

| 文件 | 主要用途 | 坐标单位 |
|---|---|---|
| `full.md` | 全文预览、LLM 输入、文本检索 | 无 |
| `{uuid}_content_list.json` | **RAG 分块入库、多模态检索** | 0–1000 归一化 |
| `layout.json` | 精确版面分析、坐标提取、层次结构 | PDF pt / 像素 |
| `images/{sha256}.jpg` | 图片/表格/公式原始截图 | — |
| `{uuid}_origin.pdf` | 原始文件存档 | — |

---

## 七、Agent 轻量 API 接口规范（`/api/v1/agent/`）

### 7.1 本地文件上传解析

#### Step 1：申请上传链接

```
POST https://mineru.net/api/v1/agent/parse/file
Authorization: Bearer {token}
Content-Type: application/json
```

```json
{
  "file_name": "销售数据统计.xlsx",
  "file_size": 14336
}
```

> ⚠️ 字段名为 `file_name` / `file_size`（非 `name` / `size`，否则报 -10002）

**响应：**
```json
{
  "code": 0,
  "data": {
    "task_id": "6d7c5b4c-54f9-48da-...",
    "file_url": "https://mineru.oss-cn-shanghai.aliyuncs.com/..."
  }
}
```

> ⚠️ 响应字段为 `file_url`（非 `upload_url`）

#### Step 2：上传文件

```
PUT {file_url}
Content-Length: {file_size_bytes}
（不携带 Content-Type）
```

#### Step 3：轮询结果

```
GET https://mineru.net/api/v1/agent/parse/{task_id}
Authorization: Bearer {token}
```

**响应：**
```json
{
  "code": 0,
  "data": {
    "task_id": "...",
    "state": "done",
    "markdown_url": "https://cdn-mineru.openxlab.org.cn/...",
    "err_msg": ""
  }
}
```

**`state` 枚举（Agent API）：**

| state | 含义 |
|---|---|
| `waiting-file` | 等待文件上传 |
| `uploading` | 上传中 |
| `pending` | 已入队 |
| `running` | 解析中 |
| `done` | 完成，`markdown_url` 可用 |
| `failed` | 失败 |

### 7.2 Agent API 输出规范（实测）

Agent API **仅输出一个 Markdown 文件**，通过 `markdown_url` CDN 直链下载：

```markdown
## Sheet1
| 日期 | 销售人员ID | 销量 | 销售金额 |
| --- | --- | --- | --- |
| 10/20/2018 | 3 | 100 | 300 |
...
```

- 无 ZIP，无 content_list.json，无 layout.json，无 images/
- Excel 表格输出为 GFM Markdown 表格，Sheet 名作为 `##` 标题

---

## 八、请求参数完整参考

### 8.1 解析参数（精准 API，传入 `file-urls/batch` 的 files 数组）

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `model_version` | string | `"pipeline"` | `pipeline`（速度快）/ `vlm`（质量高，推荐）/ `MinerU-HTML`（HTML专用） |
| `is_ocr` | bool | `false` | 开启 OCR；扫描件/图片必须为 `true` |
| `enable_formula` | bool | `true` | 公式识别，输出 LaTeX |
| `enable_table` | bool | `true` | 表格识别，输出 HTML + 截图 |
| `language` | string | `"ch"` | 见语言代码表 |
| `page_ranges` | string | 全文 | 格式：`"1-10"`、`"2,4-6"`、`"2--2"`（负数表示倒数） |
| `extra_formats` | [string] | — | 额外输出格式：`"docx"`、`"html"`、`"latex"` |
| `data_id` | string | — | 业务追踪 ID，≤128字符 |
| `callback` | string | — | 完成回调 URL |
| `no_cache` | bool | `false` | 强制重新解析（跳过缓存） |
| `seed` | string | — | 缓存命中控制标识，≤64字符 |
| `cache_tolerance` | int | `900` | 缓存容忍秒数 |

### 8.2 语言代码（`language` 参数）

| 代码 | 语言 |
|---|---|
| `ch` | 中文（含英文，默认） |
| `en` | 英文 |
| `japan` | 日文 |
| `korean` | 韩文 |
| `latin` | 拉丁语系 |
| `arabic` | 阿拉伯文 |
| `cyrillic` | 西里尔文（俄文等） |
| `devanagari` | 天城文（印地语等） |

---

## 九、错误码

| 错误码 | 说明 | 处理建议 |
|---|---|---|
| `0` | 成功 | — |
| `A0202` | Token 错误 | 检查 `Authorization: Bearer {token}` 格式 |
| `A0211` | Token 过期 | 重新申请 Token |
| `-10001` | 服务内部异常 | 重试或联系支持 |
| `-10002` | 请求参数错误 | 检查必填字段和字段名 |
| `-60003` | 空文件 | 检查文件内容 |
| `-60004` | 文件超限（>200MB） | 分割文件 |
| `-60005` | 页数超限（>600页） | 使用 `page_ranges` 分批 |
| `-60006` | 不支持的文件格式 | 检查格式路由 |
| `-60018` | 每日任务数达上限 | 次日重试或升级配额 |
| `-30001` | Agent API：文件超限（>10MB） | 改用精准 API 或压缩文件 |
| `-30002` | Agent API：格式不支持 | 检查 Agent API 支持格式 |
| `-30003` | Agent API：页数超限（>20页） | 使用精准 API 或 `page_range` 分页 |

---

## 十、限制说明

| 项目 | 精准解析 API | Agent 轻量 API |
|---|---|---|
| 单文件大小 | ≤ 200 MB | ≤ 10 MB |
| 单文件页数 | ≤ 600 页 | ≤ 20 页 |
| 每日高优先级页数 | 2000页/账号（超出后降优先级） | — |
| 批量上传单次上限 | 200 个文件 | — |
| data_id 长度 | ≤ 128字符 | — |
| seed 长度 | ≤ 64字符 | — |

---

## 十一、关键参数配置建议

| 场景 | 推荐参数组合 |
|---|---|
| PDF 数字版（高质量） | `model_version: "vlm"`, `is_ocr: false` |
| PDF 扫描件 | `model_version: "vlm"`, `is_ocr: true` |
| Word / PPT | `model_version: "vlm"`, `is_ocr: false`（注意经过 `converting` 状态） |
| 图片文件 | `model_version: "vlm"`, `is_ocr: true`（图片格式自动开启） |
| Excel | Agent API，`file_name`/`file_size` 字段 |
| 仅需文本，不要公式图片 | `enable_formula: false`, `enable_table: false` |
| 多语言文档 | 根据主语言设置 `language` |
| 大文件分批处理 | `page_ranges: "1-100"` 分批提交 |

---

## 十二、MVP 验证清单

### 运行验证命令

```bash
cd GraphRagAgent/mineru_parser
python run_parser.py --verify
```

### 输出验证项

| 验证项 | 检查方式 | 预期 |
|---|---|---|
| 精准 API ZIP 下载成功 | `full_zip_url` 可访问 | HTTP 200 |
| `full.md` 非空 | `len(markdown) > 100` | ✅ |
| `full.md` 含标题 | `"#" in markdown` | ✅（图片文档可能为❌） |
| `content_list.json` 非空 | `len(content_list) > 0` | ✅ |
| bbox 值域正确 | `all(0 <= v <= 1000 for b in cl for v in b["bbox"])` | ✅ |
| image `img_path` SHA256 格式 | 文件名 64 位十六进制 + `.jpg` | ✅ |
| table `table_body` 无外层包装 | `table_body.startswith("<table>")` | ✅ |
| `layout.json` 存在 | 文件存在 | ✅ |
| `origin.pdf` 存在 | 文件存在 | ✅ |
| Agent API Markdown | Excel 解析为 GFM 表格 | ✅ |

### 实测结果（2026-04-12，v2.7.6）

| 文件 | API | 解析状态 | 输出文件数 | 图片数 |
|---|---|---|---|---|
| LangChain介绍.pdf（8页）| 精准 | ✅ done | 5个 + 13张图 | 13 |
| 数组.docx（12页） | 精准 | ✅ done | 5个 + 3张图 | 3 |
| 图1.png | 精准（OCR） | ✅ done | 5个 + 1张图 | 1 |
| 测试图片.png | 精准（OCR） | ✅ done | 5个 + 2张图 | 2 |
| 销售数据统计.xlsx | Agent | ✅ done | 1个（full.md） | 0 |
