# MinerU + LangExtract Pipeline 规范文档 v1.0

> 基于实际执行结果编写（2026-04-13）  
> 测试文档：`0.LangChain技术生态介绍`（PDF，10,671 字符）  
> 模型：`qwen3.6-plus`（DashScope OpenAI-compatible 接口）

---

## 目录

1. [系统定位](#1-系统定位)
2. [完整执行流程](#2-完整执行流程)
3. [运行环境与脚本位置](#3-运行环境与脚本位置)
4. [阶段一：MinerU 文档解析](#4-阶段一mineru-文档解析)
5. [阶段间对接规范（mineru_reader.py）](#5-阶段间对接规范mineru_readerpy)
6. [阶段二：LangExtract 知识图谱抽取](#6-阶段二langextract-知识图谱抽取)
7. [Pipeline 最终输出规范（实际）](#7-pipeline-最终输出规范实际)
8. [当前文档状态总览](#8-当前文档状态总览)
9. [性能与质量参考](#9-性能与质量参考)

---

## 1. 系统定位

本 Pipeline 是 GraphRAG 索引阶段的核心流程，负责将原始文档转换为知识图谱三元组：

```
原始文档（PDF / Word / 图片 / Excel）
        │
        ▼ 阶段一：MinerU 解析
mineru_parser/output/{文档名}/
  └── full.md + *_content_list.json + layout.json + images/
        │
        ▼ 对接层：mineru_reader.py
langextract_pipeline/
  └── list[lx.data.Document]（text + document_id）
        │
        ▼ 阶段二：LangExtract 抽取
langextract_pipeline/output/
  └── kg_extraction_{ts}.jsonl（知识图谱三元组）
      kg_extraction_{ts}.html（可视化）
        │
        ▼ 后续阶段（待建设）
知识存储层（图数据库 / 向量库）
```

**各阶段职责：**

| 阶段 | 工具 | 职责 |
|------|------|------|
| 文档解析 | MinerU（云 API） | PDF/Word/图片 → Markdown 文本 + 结构化 JSON |
| 对接层 | mineru_reader.py | MinerU 输出 → lx.data.Document 列表 |
| 知识抽取 | LangExtract + LLM | 文本 → 实体/关系三元组（带原文坐标） |

---

## 2. 完整执行流程

### 2.1 数据流

```
[MinerU 云端解析]
  上传文档 → 选择 Precise/Agent API → 下载解析结果到
  mineru_parser/output/{文档名}/
        │
        ├── full.md                    ← 主文本（所有 pipeline 必有）
        ├── {uuid}_content_list.json   ← 结构化块（精准 API 特有）
        ├── layout.json                ← 版面坐标（精准 API 特有）
        └── images/                    ← 提取图片（精准 API 特有）

[mineru_reader.py 对接]
  scan_mineru_outputs(MINERU_OUTPUT_DIR)
    → 读取 full.md 作为主文本
    → 若 full.md 无 Markdown 表格，追加 content_list 中的 HTML 表格（带 caption）
    → 构建 lx.data.Document(text=..., document_id=目录名)

[lx.extract() 抽取]
  文本分块（ChunkIterator，按 MAX_CHAR_BUFFER 切分）
    → Prompt 构建（few-shot + KG_PROMPT_DESCRIPTION）
    → 并行 LLM 推理（ThreadPoolExecutor，MAX_WORKERS）
    → 输出解析（代码围栏 JSON 解析）
    → 文本对齐（extraction_text → char_interval 坐标）

[结果保存]
  lx.io.save_annotated_documents() → output/kg_extraction_{ts}.jsonl
  lx.visualize()                   → output/kg_extraction_{ts}.html
```

### 2.2 运行命令

```bash
cd /Users/tanglin/VibeCoding/GraphRagAgent/langextract_pipeline
source .venv/bin/activate

# 处理全部文档
python run_pipeline.py

# 只处理指定文档（可多个）
python run_pipeline.py "0.LangChain技术生态介绍" "数组"

# dry-run：只读取文档，不调用 API
python run_pipeline.py --dry-run
```

---

## 3. 运行环境与脚本位置

### 3.1 目录结构

```
GraphRagAgent/
├── mineru_parser/              # 阶段一：MinerU 解析
│   ├── mineru_client.py        # MinerU API 调用入口
│   ├── .env                    # MINERU_API_TOKEN
│   └── output/                 # 解析结果（每个文档一个子目录）
│
├── langextract_pipeline/       # 阶段二：LangExtract 抽取（含对接层）
│   ├── .venv/                  # Python 3.13.12 虚拟环境（独立，必须激活）
│   ├── .env                    # LLM API Keys + 抽取参数
│   ├── run_pipeline.py         # 主入口
│   ├── mineru_reader.py        # 对接层：MinerU → lx.data.Document
│   ├── config.py               # 配置加载（读取 .env）
│   ├── providers.py            # DashScope / DeepSeek 模型实例化
│   ├── kg_prompts.py           # KG 抽取 Prompt + Few-shot
│   └── output/                 # 抽取结果（.jsonl + .html）
│
└── reference_projects/
    └── langextract/            # LangExtract 源码（editable 安装到 pipeline venv）
        └── .venv/              # 独立 venv，仅用于 langextract 库开发/测试
```

### 3.2 虚拟环境

**阶段一（MinerU）：** 使用 `mineru_parser/.venv`，Python 3.12

**阶段二（LangExtract）：** 使用 `langextract_pipeline/.venv`，Python 3.13.12

```bash
# 阶段二 venv 初始化（首次）
cd langextract_pipeline
python3 -m venv .venv
.venv/bin/pip install -e "../reference_projects/langextract[test]" openai python-dotenv tqdm

# 每次运行前激活
source .venv/bin/activate
```

> ⚠️ 两个阶段使用**独立虚拟环境**，不得混用，避免依赖冲突。

### 3.3 配置文件

**`langextract_pipeline/.env` 关键配置：**

| 参数 | 默认值 | 必填 | 说明 |
|------|--------|------|------|
| `KG_MODEL_PROVIDER` | `dashscope` | 是 | `dashscope` 或 `deepseek` |
| `KG_MODEL_ID` | `qwen-plus` | 是 | 模型 ID（如 `qwen3.6-plus`） |
| `DASHSCOPE_API_KEY` | — | Provider=dashscope 时 | 阿里云 API Key |
| `DEEPSEEK_API_KEY` | — | Provider=deepseek 时 | DeepSeek API Key |
| `MAX_CHAR_BUFFER` | `3000` | 否 | 每 Chunk 最大字符数 |
| `MAX_WORKERS` | `3` | 否 | 并行 Worker（免费额度建议 ≤ 3） |
| `BATCH_LENGTH` | `5` | 否 | 每批 Chunk 数 |
| `EXTRACTION_PASSES` | `1` | 否 | 多轮抽取次数 |
| `MINERU_OUTPUT_DIR` | `../mineru_parser/output` | 否 | MinerU 输出路径 |

---

## 4. 阶段一：MinerU 文档解析

### 4.1 API 类型选择

| 文档类型 | 推荐 API | 产物 |
|---------|----------|------|
| PDF / Word / PPT | **Precise API** | full.md + content_list.json + layout.json + images/ |
| 图片（JPG/PNG） | Precise API | full.md + content_list.json（仅图块，文本极少） |
| Excel | **Agent API** | full.md（仅此一个文件） |

### 4.2 输出目录结构（实际）

```
mineru_parser/output/{文档名}/
├── full.md                            # 完整 Markdown 文本（必有）
├── {uuid}_content_list.json           # 结构化块列表（精准 API）
├── {uuid}_origin.pdf                  # 原始文件副本
├── layout.json                        # 版面坐标信息
└── images/                            # 提取图片（SHA256 命名）
```

### 4.3 content_list.json 关键字段

**顶层：** 平铺 JSON 数组，每个元素为一个内容块

**通用字段（所有 block）：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | 块类型：`text` / `table` / `image` / `discarded` 等 |
| `page_idx` | int | 页码（0-based） |
| `bbox` | int[4] | 归一化坐标 `[x0, y0, x1, y1]`（0-1000 比例） |

**text 块特有：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `text` | string | 纯文本内容 |
| `text_level` | int\|null | 标题层级（1=一级标题，null=正文） |

**table 块特有：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `table_body` | string | 完整 HTML `<table>` 结构 |
| `table_caption` | list[str] | 表格标题（实测多为空列表 `[]`） |
| `table_footnote` | list[str] | 表格脚注 |
| `img_path` | string | 表格截图路径（`images/{sha256}.jpg`） |

**image 块特有：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `img_path` | string | 图片路径 |
| `image_caption` | list[str] | 图片说明文字 |

### 4.4 实际文档解析结果

| 文档 | API 类型 | full.md 字符数 | content_list 块分布 | 图片数 |
|------|---------|---------------|---------------------|--------|
| 0.LangChain技术生态介绍 | Precise | 8,941 | text:70, image:11, discarded:4, table:2 | 13 |
| 数组 | Precise | 7,924 | text:127, image:3 | 3 |
| 图1 | Precise | 943 | table:1 | 1 |
| 测试图片 | Precise | 162 | image:2 | 2 |
| 销售数据统计 | Agent | 2,906 | 无（Agent API 不产生） | 0 |

---

## 5. 阶段间对接规范（mineru_reader.py）

**脚本位置：** `langextract_pipeline/mineru_reader.py`

### 5.1 对接逻辑

```python
# 核心函数调用链
scan_mineru_outputs(MINERU_OUTPUT_DIR, doc_filter=None, include_tables=True)
  └── read_mineru_document(output_dir, include_tables=True)
        ├── 读取 full.md → text（主文本）
        ├── 若 full.md 无 Markdown 表格（_has_markdown_tables 检测）：
        │     读取 *_content_list.json → _extract_table_texts()
        │     → 追加 [表格 N：caption]\n{table_body}
        ├── 文本 < 200 字符时打印警告
        └── 返回 lx.data.Document(text=text, document_id=目录名,
                                  additional_context="来源文档：{目录名}")
```

### 5.2 输出的 lx.data.Document 字段

| 字段 | 值来源 | 说明 |
|------|--------|------|
| `text` | full.md + HTML 表格（条件追加） | LangExtract 分块和对齐的基准文本 |
| `document_id` | MinerU 输出目录名 | 原始文件名 stem |
| `additional_context` | `"来源文档：{doc_id}"` | 注入所有 Chunk 的背景信息 |

### 5.3 表格处理规则

| full.md 是否含 MD 表格（`|` 开头行） | 处理方式 |
|--------------------------------------|----------|
| 否（PDF/Word 大多数情况） | 从 content_list.json 追加 HTML 表格，防止遗漏结构化数据 |
| 是（Excel Agent API 产物） | 跳过追加，避免重复 |

### 5.4 实际文本字符数（对接后）

| 文档 | full.md | 追加表格 | 最终 text 字符数 |
|------|---------|---------|----------------|
| 0.LangChain技术生态介绍 | 8,941 | +1,728（2 张 HTML 表） | **10,669** |
| 数组 | 7,924 | 无表格 | **7,924** |
| 图1 | 943 | +952（1 张 HTML 表） | **1,895** |
| 测试图片 | 162 | 无表格 | **162** ⚠️ 过短 |
| 销售数据统计 | 2,906 | 跳过（已含 MD 表格） | **2,906** |

### 5.5 注意事项

- **纯图片文档**（`测试图片`，162 字符）：LangExtract 无法处理图片内容，抽取结果极少，建议通过 `doc_filter` 排除
- **discarded 块**（页眉页脚噪声）：仅在 content_list.json 中存在，full.md 中已过滤，不会污染文本

---

## 6. 阶段二：LangExtract 知识图谱抽取

### 6.1 模型接入

LangExtract 内置路由会将 `qwen*`、`deepseek*` 误路由到 OllamaLanguageModel。

**规避方案：** 直接实例化 `OpenAILanguageModel` 并通过 `model=` 参数传入，绕过路由。

```python
from langextract.providers.openai import OpenAILanguageModel

# DashScope（阿里云 Qwen）
model = OpenAILanguageModel(
    model_id="qwen3.6-plus",
    api_key=DASHSCOPE_API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    max_workers=3,
)

# DeepSeek
model = OpenAILanguageModel(
    model_id="deepseek-chat",
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1",
    max_workers=5,
)
```

### 6.2 lx.extract() 调用参数

```python
result = lx.extract(
    text_or_documents=documents,        # list[lx.data.Document]
    model=model,                         # 预构建实例（绕过路由）
    max_char_buffer=3000,                # 每 Chunk 最大字符数
    batch_length=5,                      # 每批 Chunk 数
    max_workers=3,                       # 并行 Worker 数
    extraction_passes=1,                 # 抽取轮数
    context_window_chars=None,           # 跨 Chunk 上下文（None=不启用）
    prompt_description=KG_PROMPT_DESCRIPTION,
    examples=KG_EXAMPLES,               # Few-shot 示例
    use_schema_constraints=False,        # 必须 False（非 Gemini 模型）
    fence_output=True,                   # 要求代码围栏包裹 JSON（更稳定）
    show_progress=True,
)
```

**关键参数说明：**

| 参数 | 值 | 必要性 | 说明 |
|------|-----|-------|------|
| `use_schema_constraints` | `False` | **必须** | OpenAI-compat 模型不支持 Gemini 结构化 Schema |
| `fence_output` | `True` | **推荐** | 要求模型用 ` ```json ` 包裹输出，解析更稳定 |
| `model` | 预构建实例 | **必须** | 直接传实例绕过路由，避免 qwen/deepseek 被路由到 Ollama |
| `max_char_buffer` | 3000 | 可调 | 越小越精确，API 调用次数越多 |
| `max_workers` | 3 | 可调 | DashScope 免费额度建议 ≤ 3 |

### 6.3 Prompt 与 Few-shot 规范

**实体类型（extraction_class）：**

| 类型 | 说明 | 示例 |
|------|------|------|
| `product` | 产品/工具/框架 | LangChain, GPT-4, LlamaIndex |
| `organization` | 公司/机构/社区 | OpenAI, Google, Anthropic |
| `technology` | 技术/概念/算法 | RAG, Function Calling, Transformer |
| `event` | 事件/发布/行为 | 2022年10月开源, GPT-4发布 |
| `person` | 人物 | Harrison Chase |
| `location` | 地点 | （较少出现） |

**关系通过 attributes 表达：**

```python
# 示例：product 的关系 attributes
{
    "created_by": "Harrison Chase",      # → person/organization
    "use_case": "RAG应用, Agent系统",    # 用途描述
    "language": "Python, TypeScript",    # 技术栈
}

# 示例：event 的关系 attributes
{
    "actor": "LangChain",               # → 执行主体
    "type": "开源发布",
    "year": "2022",
}
```

---

## 7. Pipeline 最终输出规范（实际）

### 7.1 输出文件

每次 `run_pipeline.py` 运行产生 2 个文件：

| 文件 | 格式 | 说明 |
|------|------|------|
| `output/kg_extraction_{YYYYMMDD_HHMMSS}.jsonl` | **JSONL** | 每行一个 AnnotatedDocument |
| `output/kg_extraction_{YYYYMMDD_HHMMSS}.html` | HTML | 交互式可视化 |

### 7.2 JSONL 文件格式（实际）

**格式：** JSON Lines，每行一个完整 JSON 对象，UTF-8 编码，`\n` 分隔

```
{"extractions": [...], "text": "...", "document_id": "0.LangChain技术生态介绍"}
{"extractions": [...], "text": "...", "document_id": "数组"}
```

> 单文档运行时文件只有 1 行；多文档运行时每文档一行。

### 7.3 AnnotatedDocument 顶层字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `document_id` | string | MinerU 输出目录名（原始文件 stem） |
| `text` | string | 完整原始文本（含 Markdown 标记）；char_interval 坐标的基准 |
| `extractions` | array | 所有抽取结果（含 grounded 和 ungrounded） |

### 7.4 单条 Extraction 字段规范（实际）

```json
{
  "extraction_class": "product",
  "extraction_text": "LangChain",
  "char_interval": {
    "start_pos": 38,
    "end_pos": 47
  },
  "alignment_status": "match_exact",
  "extraction_index": 1,
  "group_index": 0,
  "description": null,
  "attributes": {
    "type": "元老级Agent开发工具, 大模型开发框架",
    "open_sourced": "2022年10月开源",
    "programming_language": "Python/TS",
    "core_components": "链, 代理",
    "evolved_to": "LangChain AI",
    "website": "https://www.langchain.com/"
  }
}
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `extraction_class` | string | 实体类型（见 6.3） |
| `extraction_text` | string | LLM 抽取的原文文字 |
| `char_interval` | object\|null | 原文字符坐标；`null` = 未定位，**需过滤** |
| `char_interval.start_pos` | int | 起始索引（inclusive，基于全文 UTF-8 字符） |
| `char_interval.end_pos` | int | 结束索引（exclusive） |
| `alignment_status` | string\|null | `match_exact` / `match_fuzzy` / `null` |
| `extraction_index` | int\|null | Chunk 内顺序编号（每 Chunk 从 1 重置） |
| `group_index` | int\|null | 跨 Chunk 全局编号（从 0 开始） |
| `description` | string\|null | 实测均为 `null` |
| `attributes` | object\|null | 自由 KV，含实体属性和关系 |

### 7.5 alignment_status 含义

| 状态 | 含义 | 建议 |
|------|------|------|
| `match_exact` | 精确子串匹配 | 最高质量，优先使用 |
| `match_fuzzy` | token 重叠模糊匹配 | 坐标范围可能偏大，谨慎使用 |
| `null` | 无法定位（ungrounded） | 过滤掉，不可信 |

### 7.6 char_interval 坐标系（实测）

- **基准：** `Document.text` 全文，UTF-8 字符索引（非字节）
- **实测范围：** start_pos 38~10,645，end_pos 47~10,652（10,671 字符文档）
- **exact 匹配实体长度：** 最短 1 字符，最长 55 字符，平均 9.9 字符
- **还原原文片段：**
  ```python
  span = doc["text"][e["char_interval"]["start_pos"]:e["char_interval"]["end_pos"]]
  ```

### 7.7 结果过滤与读取

```python
import json

# 读取 JSONL（多文档逐行解析）
with open("output/kg_extraction_20260412_223231.jsonl") as f:
    for line in f:
        doc = json.loads(line)
        extractions = doc["extractions"]
        text = doc["text"]

        # 1. 过滤 ungrounded（必做）
        grounded = [e for e in extractions if e["char_interval"]]

        # 2. 只保留精确匹配（推荐，最高质量）
        exact = [e for e in grounded if e["alignment_status"] == "match_exact"]

        # 3. 还原原文片段
        for e in exact:
            span = text[e["char_interval"]["start_pos"]:e["char_interval"]["end_pos"]]
            print(f"[{e['extraction_class']}] {span}")
            print(f"  attributes: {e['attributes']}")

        # 4. 按类型分组（构建 KG 节点）
        from collections import defaultdict
        by_class = defaultdict(list)
        for e in grounded:
            by_class[e["extraction_class"]].append(e)
```

---

## 8. 当前文档状态总览

| 文档 | MinerU 解析 | LangExtract 抽取 | 抽取结果文件 |
|------|------------|----------------|------------|
| 0.LangChain技术生态介绍 | ✅ 完成 | ✅ 完成（96条，61 exact） | `kg_extraction_20260412_223231.jsonl` |
| （第2次运行，多文档） | — | ✅ 完成（3文档合并） | `kg_extraction_20260413_110626.jsonl` |
| （第3次运行，多文档） | — | ✅ 完成（3文档合并） | `kg_extraction_20260413_111429.jsonl` |
| 数组 | ✅ 完成 | ✅ 已包含在多文档运行中 | 见上 |
| 销售数据统计 | ✅ 完成 | ✅ 已包含在多文档运行中 | 见上 |
| 图1 | ✅ 完成 | ⏳ 待运行（单独） | — |
| 测试图片 | ✅ 完成 | ⚠️ 建议跳过 | 纯图片，文本仅 162 字符 |

**Agentic RAG 实际加载状态（2026-04-13）：**

```
[KG] 已加载 3 个文档，130 个实体
```

KGRetriever 从 `output/` 目录的全部 JSONL 文件中加载，当前读取 3 个 JSONL 文件，汇总 `match_exact` 实体共 **130 个**。

---

## 9. 性能与质量参考

### 9.1 实测基准（LangChain 文档）

| 项目 | 值 |
|------|-----|
| 模型 | qwen3.6-plus（DashScope） |
| 文档字符数 | 10,671 |
| MAX_CHAR_BUFFER | 3,000 |
| Chunk 数 | 4 |
| MAX_WORKERS | 3 |
| 耗时 | ~417 秒 |
| 总抽取条数 | 96 |
| grounded（有效定位） | 70（72.9%） |
| match_exact | 61（87.1% of grounded） |
| match_fuzzy | 9（12.9% of grounded） |
| ungrounded | 26（27.1%） |

### 9.2 实体类型分布（grounded，LangChain 文档）

| extraction_class | 数量 |
|----------------|------|
| product | 30 |
| technology | 19 |
| organization | 16 |
| event | 5 |

### 9.3 Ungrounded 主要原因

1. **归纳性概念**：LLM 抽取了文中未以该精确形式出现的概括性词语（如"补全模型"）
2. **Few-shot 示例溢出**：LLM 将 few-shot 示例中的词误识别为目标文档内容

### 9.4 已知问题

| 问题 | 原因 | 状态 |
|------|------|------|
| `Prompt alignment FAILED` 警告 | few-shot 示例中某词多次出现，顺序检查误报 | 不影响抽取，可忽略 |
| qwen/deepseek 被路由到 Ollama | langextract 内置 `^qwen`/`^deepseek` 模式匹配到 OllamaProvider | ✅ 已修复：直接传 model 实例绕过路由 |
| 纯图片文档抽取内容极少 | LangExtract 不支持图像理解，图片内容无法提取 | 建议通过 doc_filter 跳过 |

---

## 10. 下游对接：Agentic RAG（已实现，2026-04-13）

> 完整规范见：`docs/agentic-rag-pipeline-spec-v1.0.md`

### 10.1 JSONL 产物作为 KG 检索数据源

Agentic RAG 的 `KGRetriever` 直接读取本 pipeline 输出的 JSONL 文件：

```python
# agentic_rag/retrievers/kg_retriever.py
class KGRetriever:
    def __init__(self, jsonl_dir, context_window=200, min_alignment="match_exact"):
        # 扫描 jsonl_dir 下所有 .jsonl 文件
        for jsonl_file in Path(jsonl_dir).glob("*.jsonl"):
            with open(jsonl_file) as f:
                for line in f:
                    record = json.loads(line)
                    for ext in record.get("extractions", []):
                        # 只使用 match_exact 状态的实体
                        if ext["alignment_status"] == min_alignment:
                            # 加入 BM25 索引（entity_text + attribute values）
                            # 保存 context_snippet（原文±200字）
```

**数据流**：
```
langextract_pipeline/output/kg_extraction_*.jsonl
        │
        ▼ KGRetriever.__init__()
BM25 索引（130 个 match_exact 实体）
        │
        ▼ KGRetriever.retrieve(query, top_k=5)
list[dict]（实体卡片，含 entity_text / attributes / context_snippet）
        │
        ▼ kg_retriever.format_for_prompt(results)
实体卡片文本（注入 LLM Prompt）
```

### 10.2 KGRetriever 消费的 JSONL 字段

| JSONL 字段 | KGRetriever 用途 |
|-----------|----------------|
| `extractions[].extraction_text` | 实体名称（BM25 索引 + 返回） |
| `extractions[].extraction_class` | 实体类型（返回供展示） |
| `extractions[].attributes` | 属性字典（BM25 索引 + 返回） |
| `extractions[].char_interval.start_pos` | 原文偏移（取 context_snippet） |
| `extractions[].char_interval.end_pos` | 原文偏移（取 context_snippet） |
| `extractions[].alignment_status` | 过滤条件（仅 match_exact） |
| `document_id` | 来源文档 ID（返回供引用） |
| `text` | 原始全文（context_snippet 取 ±200 字） |

### 10.3 实测接入效果（3 问题验证）

| 问题类型 | 路由 | KG 命中实体数 | 关键命中实体 |
|---------|------|-------------|------------|
| LangChain 核心组件 + LlamaIndex 对比 | hybrid_query | 5 | LangChain, LlamaIndex, LCEL, LangSmith, LangGraph |
| LangSmith 是什么 | entity_query | 5 | LangSmith, LangSmith追踪功能, LangSmith评测 |
| LangGraph 应用场景 | hybrid_query | 5 | LangGraph, LangGraph Platform, LangChain, LCEL |

KG 实体检索精准命中细粒度概念实体（如"LangSmith 追踪功能"、"LangSmith评测"），为 LLM 生成提供了结构化的属性信息，显著提升了答案质量。

### 10.4 JSONL 文件管理建议

- **不要删除旧 JSONL**：KGRetriever 会加载目录下所有 JSONL，多次运行会**累积**实体
- **去重说明**：目前 KGRetriever 不对实体去重，相同实体可能在 BM25 中出现多次（BM25 TF 加权会自然抑制重复）
- **增量更新**：新增文档后运行 `run_pipeline.py "新文档名"`，产生新 JSONL，KGRetriever 下次加载自动包含
