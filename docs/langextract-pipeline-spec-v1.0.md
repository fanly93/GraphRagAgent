# LangExtract Pipeline 规范文档 v1.0

> 基于源码 `v1.2.1` + 实际 MVP 运行结果（2026-04-12）编写
> 模型：`qwen3.6-plus`（DashScope OpenAI-compatible 接口）
> 测试文档：`0.LangChain技术生态介绍`（MinerU 精准 API 解析产物，10,671 字符）

---

## 目录

1. [项目定位与能力边界](#1-项目定位与能力边界)
2. [完整 Pipeline 执行流程](#2-完整-pipeline-执行流程)
3. [实际执行步骤（MVP 复现）](#3-实际执行步骤mvp-复现)
4. [输入规范](#4-输入规范)
5. [输出规范（以实际结果为准）](#5-输出规范以实际结果为准)
6. [模型接入规范](#6-模型接入规范)
7. [关键参数速查](#7-关键参数速查)
8. [实际运行数据参考](#8-实际运行数据参考)

---

## 1. 项目定位与能力边界

LangExtract 是 Google 开源的**纯文本结构化信息抽取库**，在多模态 RAG 系统中的角色是：

```
MinerU 解析层（PDF/Word/图片 → Markdown 文本）
    ↓
LangExtract 抽取层（文本 → 知识图谱三元组）
    ↓
知识存储层（图数据库 / 向量库）
```

**能力边界（v1.2.1）：**

| 能力 | 是否支持 |
|---|---|
| 纯文本实体/关系抽取 | ✅ |
| 抽取结果精确定位（字符级） | ✅ |
| 文档分块（Text Chunking） | ✅ |
| 多轮抽取 Pass（提升召回率） | ✅ |
| 并行处理 | ✅ |
| OpenAI-compatible 接口模型（DashScope / DeepSeek） | ✅（通过 base_url 接入） |
| PDF/Word 等文档直接解析 | ❌（需先经 MinerU 转为文本） |
| 图像/表格多模态理解 | ❌ |
| 向量检索 / 图谱存储 | ❌ |

---

## 2. 完整 Pipeline 执行流程

### 2.1 数据流总览

```
MinerU output/{doc}/full.md
        │
        ▼
[1] mineru_reader.py
    scan_mineru_outputs() → list[lx.data.Document]
    - 读取 full.md 作为主文本
    - 可选：从 *_content_list.json 追加表格 HTML
    - document_id = 目录名（原始文件 stem）
        │
        ▼
[2] providers.py
    create_model() → OpenAILanguageModel(base_url=DashScope/DeepSeek)
    - 直接实例化，绕过 langextract 内部路由匹配
    - 通过 model= 参数传入 lx.extract()
        │
        ▼
[3] lx.extract()  ← langextract 核心
    ├── Prompt 校验（few-shot examples 对齐检查）
    ├── 文本分块（ChunkIterator，按 max_char_buffer 切分）
    ├── Prompt 构建（QAPromptGenerator）
    ├── LLM 推理（并行调用，ThreadPoolExecutor）
    ├── 输出解析（FormatHandler，解析代码围栏中的 JSON）
    └── 文本对齐（Resolver.align()，extraction_text → char_interval）
        │
        ▼
[4] AnnotatedDocument
    ├── document_id
    ├── text（原始全文）
    └── extractions: list[Extraction]（含 char_interval 定位）
        │
        ▼
[5] 结果输出
    ├── lx.io.save_annotated_documents() → JSONL 文件（无扩展名）
    └── lx.visualize() → 交互式 HTML 可视化
```

### 2.2 文本对齐策略（实测优先级）

LangExtract 按以下顺序尝试将 LLM 输出的 `extraction_text` 定位回原文：

| 策略 | alignment_status | 说明 |
|---|---|---|
| 1. 精确子串匹配 | `match_exact` | LLM 输出与原文完全一致（最优） |
| 2. 扩展匹配 | `match_greater` | LLM 输出包含原文（如带了额外标点） |
| 3. 子集匹配 | `match_lesser` | LLM 输出是原文子串 |
| 4. 模糊 token 匹配 | `match_fuzzy` | token 重叠率 ≥ 阈值（降级策略） |
| 5. 无法定位 | `null` | `char_interval = null`，应过滤掉 |

**实测结果**：精确匹配（match_exact）占 87%，模糊匹配（match_fuzzy）占 13%，未定位 27%（26/96条）。

---

## 3. 实际执行步骤（MVP 复现）

### 3.1 目录结构

```
langextract_pipeline/
├── .venv/              # Python 3.13.12 虚拟环境（激活后运行）
├── .env                # API Keys + 参数配置
├── CLAUDE.md           # Claude Code 工作指南（venv 强制要求）
├── config.py           # 配置加载（读取 .env）
├── providers.py        # DashScope / DeepSeek 模型接入
├── mineru_reader.py    # MinerU 输出读取 → lx.data.Document
├── kg_prompts.py       # KG 抽取 Prompt + Few-shot 示例
├── run_pipeline.py     # 主入口
└── output/             # 抽取结果（JSONL + HTML）
```

### 3.2 环境准备

```bash
cd /Users/tanglin/VibeCoding/GraphRagAgent/langextract_pipeline

# 虚拟环境不存在时初始化
python3 -m venv .venv
.venv/bin/pip install -e "../reference_projects/langextract[test]" openai python-dotenv tqdm

# 激活虚拟环境
source .venv/bin/activate
```

### 3.3 配置 .env

```ini
# 必填：选择 Provider
KG_MODEL_PROVIDER=dashscope     # 或 deepseek

# 必填：对应 Provider 的 API Key
DASHSCOPE_API_KEY=sk-xxxx       # DashScope 时必填
DEEPSEEK_API_KEY=sk-xxxx        # DeepSeek 时必填

# 必填：模型 ID
KG_MODEL_ID=qwen-plus           # 或 deepseek-chat 等

# 可选参数（有默认值）
MAX_CHAR_BUFFER=3000
MAX_WORKERS=3
BATCH_LENGTH=5
EXTRACTION_PASSES=1
```

### 3.4 运行命令

```bash
# 处理全部 MinerU 已解析文档
python run_pipeline.py

# 只处理指定文档
python run_pipeline.py "0.LangChain技术生态介绍"

# dry-run（只读取文档，不调用 API）
python run_pipeline.py --dry-run
```

### 3.5 执行耗时参考

| 文档字符数 | MAX_CHAR_BUFFER | Chunk 数 | MAX_WORKERS | 耗时 |
|---|---|---|---|---|
| 10,671 | 3000 | 4 | 3 | ~417 秒 |

> DashScope 免费额度 QPS 较低（≤ 3），耗时主要受限于并发配额。付费额度可将 MAX_WORKERS 提升至 10+，预计耗时压缩至 60 秒以内。

---

## 4. 输入规范

### 4.1 lx.extract() 调用参数

```python
result = lx.extract(
    text_or_documents=documents,     # list[lx.data.Document]
    model=model,                     # 预构建 OpenAILanguageModel 实例（绕过路由）
    max_char_buffer=3000,            # 每 Chunk 最大字符数
    batch_length=5,                  # 每批 Chunk 数量
    max_workers=3,                   # 并行 Worker 数
    extraction_passes=1,             # 抽取轮数
    context_window_chars=None,       # 跨 Chunk 上下文（None=不启用）
    prompt_description=KG_PROMPT,   # 自然语言抽取指令
    examples=KG_EXAMPLES,           # few-shot 示例
    use_schema_constraints=False,    # OpenAI-compat 模型不支持 Gemini Schema
    fence_output=True,               # 要求 LLM 用代码围栏包裹 JSON（更稳定）
    show_progress=True,
)
```

### 4.2 lx.data.Document 字段

```python
lx.data.Document(
    text="...",                         # 原始文本内容（必填）
    document_id="0.LangChain技术生态介绍",  # 文档唯一 ID（建议用文件 stem）
    additional_context="来源文档：xxx",    # 注入所有 Chunk 的额外上下文（可选）
)
```

### 4.3 MinerU 文档读取规则

| 输入文件 | 处理方式 |
|---|---|
| `full.md` | 主文本内容，所有 API 类型均有，作为 Document.text |
| `*_content_list.json` | 可选追加：提取其中 `type=table` 的 `table_body`（HTML），拼接到文本末尾 |
| `layout.json` | 版面布局信息，LangExtract 阶段不使用 |
| `images/` | 图像文件，LangExtract 不处理 |

---

## 5. 输出规范（以实际结果为准）

### 5.1 输出文件类型和数量

**每次 run_pipeline.py 运行产生 2 类输出文件：**

| 文件 | 命名规则 | 格式 | 说明 |
|---|---|---|---|
| JSONL 结果文件 | `output/kg_extraction_{YYYYMMDD_HHMMSS}` | JSON（**无扩展名**） | 每行一个 AnnotatedDocument |
| HTML 可视化 | `output/kg_extraction_{YYYYMMDD_HHMMSS}.html` | HTML | 交互式可视化，可直接浏览器打开 |

> ⚠️ **重要**：`lx.io.save_annotated_documents()` 保存的文件**不带 `.jsonl` 后缀**，调用 `lx.visualize()` 时也应传入无后缀路径。

### 5.2 JSONL 文件结构（实际）

单文档时，文件为单行 JSON（非 JSONL 多行格式），结构如下：

```json
{
  "document_id": "0.LangChain技术生态介绍",
  "text": "# LangChain快速入门与Agent开发实战-Part 1\n\n...",
  "extractions": [ ... ]
}
```

**顶层字段：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `document_id` | `string` | MinerU 输出目录名（原始文件 stem） |
| `text` | `string` | 完整原始文本（含 Markdown 标记，10,671 字符） |
| `extractions` | `array` | 所有抽取结果（含 grounded 和 ungrounded） |

### 5.3 单条 Extraction 字段规范（实际）

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
|---|---|---|
| `extraction_class` | `string` | 实体类型（`product` / `organization` / `technology` / `event` / `person` / `location`） |
| `extraction_text` | `string` | LLM 抽取出的原文文字（或轻微改写，改写时 alignment_status = match_fuzzy） |
| `char_interval` | `object\|null` | 在原文中的字符位置；`null` 表示无法定位（应过滤） |
| `char_interval.start_pos` | `int` | 起始字符索引（inclusive，基于全文绝对坐标） |
| `char_interval.end_pos` | `int` | 结束字符索引（exclusive） |
| `alignment_status` | `string\|null` | 对齐质量：`match_exact` / `match_fuzzy` / `null` |
| `extraction_index` | `int\|null` | 该实体在本 Chunk 中的顺序编号（从 1 开始，每个 Chunk 重置） |
| `group_index` | `int\|null` | 实体跨 Chunk 的全局编组索引（从 0 开始，全文唯一） |
| `description` | `string\|null` | 抽取描述（实测均为 `null`） |
| `attributes` | `object\|null` | 实体属性 KV（见 5.4） |

### 5.4 attributes 字段规范（实际高频 key）

attributes 为自由格式 KV，由 LLM 根据 few-shot 示例自动生成。实测最常见的 key：

| key | 出现频次 | 含义 |
|---|---|---|
| `type` | 51 | 实体类型描述 |
| `role` | 17 | 实体在上下文中的角色 |
| `context` | 15 | 出现的上下文背景 |
| `used_by` | 14 | 被哪个产品/组织使用 |
| `category` | 10 | 分类标签 |
| `related_ecosystem` | 7 | 所属生态 |
| `actor` | 3 | 事件的执行者（仅 event 类型） |
| `based_on` | 3 | 基于哪个框架/技术构建 |

### 5.5 char_interval 坐标系

- **坐标基准**：全文绝对字符索引，以 `Document.text` 为基准（UTF-8 字符为单位，非字节）
- **坐标范围**（实测，10,671 字符文档）：
  - `start_pos`：最小 38，最大 10,645
  - `end_pos`：最小 47，最大 10,652
- **片段还原方式**：
  ```python
  span = doc.text[extraction.char_interval["start_pos"]:extraction.char_interval["end_pos"]]
  ```
- **实体文本长度分布**（实测）：最短 1 字符，最长 1,050 字符，平均 54.5 字符

> ⚠️ 注意：`match_fuzzy` 时 `end_pos - start_pos` 可能远大于 `extraction_text` 长度（如 "GPT-3.5模型的发布" 对应区间 104→1056，长达 952 字符），说明模糊匹配扩展了范围。使用时建议优先以 `match_exact` 结果为准。

### 5.6 过滤与使用建议

```python
import json

with open("output/kg_extraction_20260412_223231") as f:
    doc = json.load(f)

extractions = doc["extractions"]
text = doc["text"]

# 1. 只保留有效定位的抽取（过滤 ungrounded）
grounded = [e for e in extractions if e["char_interval"]]

# 2. 高质量过滤（只保留精确匹配）
exact = [e for e in grounded if e["alignment_status"] == "match_exact"]

# 3. 还原原文片段
for e in exact:
    span = text[e["char_interval"]["start_pos"]:e["char_interval"]["end_pos"]]
    print(f"[{e['extraction_class']}] '{span}'")
    print(f"  attributes: {e['attributes']}")

# 4. 按类型分组（构建知识图谱节点）
from collections import defaultdict
by_class = defaultdict(list)
for e in grounded:
    by_class[e["extraction_class"]].append(e)
```

### 5.7 实测输出数量（LangChain 文档，10,671 字符）

| 指标 | 数值 |
|---|---|
| 总抽取条数 | 96 |
| grounded（有效定位） | 70（72.9%） |
| ungrounded（未定位） | 26（27.1%） |
| match_exact | 61（87% of grounded） |
| match_fuzzy | 9（13% of grounded） |
| 输出文件大小 | 47,906 字节（~47 KB） |

**实体类型分布：**

| extraction_class | 数量（grounded） |
|---|---|
| product | 30 |
| technology | 19 |
| organization | 16 |
| event | 5 |

---

## 6. 模型接入规范

### 6.1 DashScope（阿里云 Qwen）

```python
from langextract.providers.openai import OpenAILanguageModel

model = OpenAILanguageModel(
    model_id="qwen-plus",           # 或 qwen-turbo / qwen-max
    api_key="sk-xxx",               # DASHSCOPE_API_KEY
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    max_workers=3,                  # 免费额度建议 ≤ 3
)
```

**常用 model_id：**

| model_id | 特点 |
|---|---|
| `qwen-plus` | 均衡性能，推荐首选 |
| `qwen-turbo` | 低延迟，适合长文档批量 |
| `qwen-max` | 最强能力，成本较高 |

### 6.2 DeepSeek

```python
model = OpenAILanguageModel(
    model_id="deepseek-chat",       # 或 deepseek-reasoner
    api_key="sk-xxx",               # DEEPSEEK_API_KEY
    base_url="https://api.deepseek.com/v1",
    max_workers=5,
)
```

### 6.3 接入关键配置

| 参数 | 必要性 | 说明 |
|---|---|---|
| `use_schema_constraints=False` | **必须** | OpenAI-compat 模型不支持 Gemini 结构化 Schema |
| `fence_output=True` | **推荐** | 要求 LLM 用代码围栏包裹 JSON，在非 Gemini 模型上更稳定 |
| `model=model_instance` | **推荐** | 直接传预构建实例，绕过路由匹配（避免 qwen/deepseek 被误路由到 Ollama Provider） |

---

## 7. 关键参数速查

### 7.1 分块参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `max_char_buffer` | 3000 | 每个 Chunk 的最大字符数。越小越精确，但 API 调用次数增加。10,671 字符文档会被切为 4 个 Chunk |
| `batch_length` | 5 | 每批 Chunk 数量，应 ≥ max_workers |
| `max_workers` | 3 | 并行推理线程数。DashScope 免费额度建议 ≤ 3 |
| `extraction_passes` | 1 | 多轮抽取次数。>1 时合并结果（先到先得），提升召回率，但成倍增加 API 调用 |
| `context_window_chars` | None | 前一 Chunk 尾部注入当前 Chunk，用于跨块共指消解 |

### 7.2 对齐参数（通过 resolver_params 传入）

```python
resolver_params={
    "enable_fuzzy_alignment": True,        # 是否启用模糊匹配（默认 True）
    "fuzzy_alignment_threshold": 0.75,     # 模糊匹配 token 重叠率阈值
    "accept_match_lesser": True,           # 是否接受子集匹配
    "suppress_parse_errors": True,         # 忽略单 Chunk 解析错误
}
```

### 7.3 环境变量

```bash
# Provider 与模型
KG_MODEL_PROVIDER=dashscope      # dashscope | deepseek
KG_MODEL_ID=qwen-plus

# API Keys
DASHSCOPE_API_KEY=sk-xxx
DEEPSEEK_API_KEY=sk-xxx

# 抽取参数（均有默认值）
MAX_CHAR_BUFFER=3000
MAX_WORKERS=3
BATCH_LENGTH=5
EXTRACTION_PASSES=1
CONTEXT_WINDOW_CHARS=           # 留空 = 不启用

# MinerU 输出目录（默认指向 ../mineru_parser/output）
MINERU_OUTPUT_DIR=/path/to/mineru_parser/output
```

---

## 8. 实际运行数据参考

### 8.1 MVP 测试基准

| 项目 | 值 |
|---|---|
| 运行日期 | 2026-04-12 |
| 模型 | qwen3.6-plus（DashScope） |
| 文档 | 0.LangChain技术生态介绍（MinerU 精准 API 解析） |
| 文档字符数 | 10,671 |
| Chunk 数量 | 4（MAX_CHAR_BUFFER=3000） |
| 抽取总数 | 96 |
| Grounded | 70（72.9%） |
| Match Exact | 61/70（87%） |
| 耗时 | 417 秒 |
| 输出文件大小 | ~48 KB |

### 8.2 Ungrounded 产生原因

实测 26 条 ungrounded 主要来自两类情况：

1. **归纳性概念**：模型抽取了 `"补全模型"`、`"对话模型"` 等概括性词语，但这些词语在原文中未以该精确形式出现（原文是 `"以补全模型为主"`）
2. **examples 溢出**：LLM 将 few-shot 示例中的文字错误地视为目标文档的内容

**过滤方法**：
```python
grounded = [e for e in extractions if e["char_interval"] is not None]
```

### 8.3 Prompt alignment 警告说明

运行时出现的 7 条警告：
```
WARNING: Prompt alignment: FAILED to align: [example#0] class='product' text='LangChain'
```

**原因**：few-shot 示例的 `text` 中 `"LangChain"` 多次出现，langextract 顺序对齐检查在该词首次出现位置前已记录了其他实体，导致检查认为顺序不满足要求。

**影响**：仅影响示例对齐检查，**不影响实际文档的抽取质量**。

**解决方法**：确保 few-shot 示例中每个 extraction_text 只在 text 中出现一次，或调整示例让每个词在 extractions 中严格按出现顺序排列。

### 8.4 已知问题与修复记录

| 问题 | 原因 | 修复 |
|---|---|---|
| HTML 生成失败：`JSONL file not found` | `save_annotated_documents` 保存的文件无 `.jsonl` 后缀，但 `visualize()` 传入了带后缀的路径 | `run_pipeline.py:_save_results()` 中改为传无后缀的实际路径 |
| qwen/deepseek 被路由到 Ollama Provider | langextract 内置模式匹配：`^qwen`、`^deepseek` 均指向 OllamaLanguageModel | 通过 `model=` 直接传入预构建 OpenAILanguageModel 实例，绕过路由 |
