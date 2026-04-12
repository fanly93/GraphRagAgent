# LangExtract 核心 Pipeline 规范文档

> 基于源码 `v1.2.1` 深度分析，面向多模态 RAG 系统对接设计

---

## 目录

1. [项目定位与核心能力](#1-项目定位与核心能力)
2. [核心 Pipeline 处理流程](#2-核心-pipeline-处理流程)
3. [输入规范](#3-输入规范)
4. [输出规范](#4-输出规范)
5. [模型接入规范](#5-模型接入规范)
6. [关键参数速查](#6-关键参数速查)
7. [对接多模态 RAG 的架构建议](#7-对接多模态-rag-的架构建议)

---

## 1. 项目定位与核心能力

LangExtract 是 Google 开源的**纯文本结构化信息抽取库**，其核心能力是：

- 接收**纯文本**输入
- 基于用户定义的 few-shot 示例，使用 LLM 从文本中**抽取结构化实体/关系**
- 将抽取结果精确**定位回原文的字符区间**（`char_interval`）
- 输出带位置标注的 JSONL 文件，支持可视化审查

**能力边界（截至 v1.2.1）：**

| 能力 | 是否支持 |
|---|---|
| 纯文本信息抽取 | ✅ |
| 实体定位（字符级别） | ✅ |
| 文档分块（Text Chunking） | ✅ |
| 多轮抽取 Pass（提升 Recall） | ✅ |
| 并行处理 | ✅ |
| PDF/Word/Excel 等文档解析 | ❌ |
| 图像/表格/公式多模态理解 | ❌ |
| 向量检索 / 关键词检索 | ❌ |
| 知识图谱构建与图谱检索 | ❌ |
| 数据库存储（向量库/图库） | ❌ |
| Embedding 模型调用 | ❌ |

---

## 2. 核心 Pipeline 处理流程

### 2.1 完整数据流

```
用户调用 lx.extract()
        │
        ▼
[1] 输入预处理 (extraction.py)
    ├── 字符串 URL → io.download_text_from_url() → 纯文本
    ├── 字符串文本 → 直接封装为 Document 对象
    └── Iterable[Document] → 直接使用
        │
        ▼
[2] Prompt 验证 (prompt_validation.py)
    └── 检查 few-shot examples 中 extraction_text 是否能在 text 中定位
        (WARNING 模式：仅打印警告；ERROR 模式：抛出异常)
        │
        ▼
[3] 模型工厂 (factory.py)
    ├── 根据 model_id 的正则 pattern 匹配 Provider 类
    ├── 从环境变量读取 API Key
    ├── 可选：从 examples 自动生成 Schema 约束 (use_schema_constraints=True)
    └── 实例化 BaseLanguageModel 子类
        │
        ▼
[4] 分块处理 (chunking.py)
    ├── RegexTokenizer / UnicodeTokenizer → 分词 (TokenizedText)
    ├── ChunkIterator → 按 max_char_buffer 切分 TextChunk
    │   规则：以句子边界为切点，不硬切单词
    └── make_batches_of_textchunk() → 组成 batch_length 大小的批次
        │
        ▼
[5] Prompt 构建 (prompting.py)
    ├── QAPromptGenerator.render(chunk_text) → 拼接完整 Prompt
    │   格式：
    │   {description}
    │   [Previous text]: ...{前块尾部文本}  ← 仅 context_window_chars 启用时
    │   Examples
    │   Q: {example.text}
    │   A: {格式化后的 extractions}
    │   ...
    │   Q: {当前 chunk 文本}
    │   A:
    └── ContextAwarePromptBuilder → 跨 Chunk 上下文注入（用于共指消解）
        │
        ▼
[6] LLM 推理 (providers/)
    ├── model.infer(batch_prompts) → 并行调用 LLM API
    └── 返回 Iterator[Sequence[ScoredOutput]]
        每个 ScoredOutput: { score: float, output: str }
        │
        ▼
[7] 输出解析 (resolver.py + format_handler.py)
    ├── FormatHandler.parse_output() → 从 LLM 输出中提取 JSON/YAML 块
    │   支持：代码围栏解析、<think> 标签去除（DeepSeek-R1/QwQ 推理模型）
    └── Resolver.resolve() → 解析为 List[Extraction] (raw，无位置信息)
        │
        ▼
[8] 文本对齐 (resolver.py)
    ├── Resolver.align() → 将 extraction_text 定位回 chunk 原文
    │   ├── 精确匹配 (MATCH_EXACT)
    │   ├── 扩展匹配 (MATCH_GREATER：LLM 输出文本包含原文)
    │   ├── 子集匹配 (MATCH_LESSER：LLM 输出是原文子集)
    │   └── 模糊匹配 (MATCH_FUZZY：token 重叠率 >= fuzzy_alignment_threshold)
    ├── 计算全文字符偏移 char_offset + 块内位置 → 全文绝对坐标
    └── 无法定位的抽取：char_interval = None（来自 examples 的幻觉内容）
        │
        ▼
[9] 多 Pass 合并 (annotation.py)  ← 仅 extraction_passes > 1 时
    └── _merge_non_overlapping_extractions()
        先到先得：早期 Pass 的抽取优先，后期 Pass 仅补充不重叠的新抽取
        │
        ▼
[10] 输出 AnnotatedDocument
     └── io.save_annotated_documents() → JSONL 文件 (可选)
```

### 2.2 关键模块映射表

| 步骤 | 源码文件 | 核心类/函数 |
|---|---|---|
| 入口 | `extraction.py` | `extract()` |
| IO 处理 | `io.py` | `download_text_from_url()`, `Dataset.load()` |
| 模型工厂 | `factory.py` | `create_model()`, `ModelConfig` |
| 分块 | `chunking.py` | `ChunkIterator`, `TextChunk` |
| 分词 | `core/tokenizer.py` | `RegexTokenizer`, `UnicodeTokenizer` |
| Prompt 构建 | `prompting.py` | `QAPromptGenerator`, `ContextAwarePromptBuilder` |
| LLM 推理抽象 | `core/base_model.py` | `BaseLanguageModel.infer()` |
| 输出格式处理 | `core/format_handler.py` | `FormatHandler.parse_output()` |
| 解析与对齐 | `resolver.py` | `Resolver.resolve()`, `Resolver.align()` |
| 注解编排 | `annotation.py` | `Annotator` |
| 数据类型 | `core/data.py` | `Document`, `AnnotatedDocument`, `Extraction` |
| 序列化 | `data_lib.py` | `annotated_document_to_dict()` |
| 文件 IO | `io.py` | `save_annotated_documents()`, `load_annotated_documents_jsonl()` |

---

## 3. 输入规范

### 3.1 `lx.extract()` 完整签名

```python
lx.extract(
    text_or_documents,           # [必填] 见 3.2
    prompt_description,          # [必填] 抽取指令，自然语言描述
    examples,                    # [必填] few-shot 示例列表
    model_id="gemini-2.5-flash", # 模型 ID，决定 Provider 路由
    api_key=None,                # LLM API Key（可用环境变量替代）
    model_url=None,              # 本地模型端点（Ollama 等）
    max_char_buffer=1000,        # 每个 Chunk 的最大字符数
    batch_length=10,             # 每批处理的 Chunk 数量
    max_workers=10,              # 并行推理 Worker 数
    extraction_passes=1,         # 多轮抽取次数（>1 时合并结果）
    context_window_chars=None,   # 跨 Chunk 上下文字符数（用于共指消解）
    additional_context=None,     # 注入所有 Chunk 的额外上下文
    temperature=None,            # 采样温度（None=使用模型默认值）
    use_schema_constraints=True, # 是否启用结构化输出 Schema
    fence_output=None,           # 是否要求 LLM 输出代码围栏（None=自动）
    format_type=None,            # JSON 或 YAML（默认 JSON）
    resolver_params=None,        # Resolver 参数字典（见 6.3）
    language_model_params=None,  # Provider 额外参数
    model=None,                  # 直接传入预构建的 model 实例
    config=None,                 # ModelConfig 对象（高级用法）
    fetch_urls=True,             # 是否自动下载 URL 内容
    show_progress=True,          # 显示进度条
    debug=False,                 # 调试日志
)
```

### 3.2 `text_or_documents` 支持的输入类型

#### 类型一：纯文本字符串

```python
result = lx.extract(
    text_or_documents="Marie Curie was a pioneering physicist.",
    ...
)
# 返回单个 AnnotatedDocument
```

#### 类型二：HTTP/HTTPS URL（仅限文本内容）

```python
result = lx.extract(
    text_or_documents="https://www.gutenberg.org/files/1513/1513-0.txt",
    fetch_urls=True,   # 默认 True
    ...
)
# 自动下载文本，返回单个 AnnotatedDocument
# 注意：仅支持 Content-Type 为 text/* / application/json / application/xml
# 不支持 PDF、Word 等二进制格式的 URL
```

#### 类型三：`Iterable[data.Document]`（批量文档）

```python
documents = [
    lx.data.Document(
        text="Marie Curie discovered radium.",
        document_id="doc_001",           # 可选，不填则自动生成 doc_xxxxxxxx
        additional_context="Chemistry"   # 可选，注入该文档的额外上下文
    ),
    lx.data.Document(
        text="Einstein developed the theory of relativity.",
        document_id="doc_002",
    ),
]
results = lx.extract(text_or_documents=documents, ...)
# 返回 list[AnnotatedDocument]
```

#### 类型四：CSV 文件（通过 `Dataset` 类）

```python
dataset = lx.io.Dataset(
    input_path=pathlib.Path("data.csv"),
    id_key="id",        # CSV 中作为 document_id 的列名
    text_key="content"  # CSV 中作为 text 的列名
)
documents = list(dataset.load(delimiter=','))  # → Iterator[Document]
results = lx.extract(text_or_documents=documents, ...)
```

**CSV 文件格式要求：**
```csv
id,content
doc_001,"First document text..."
doc_002,"Second document text..."
```

### 3.3 `examples` 规范（few-shot 示例，必填）

`examples` 是驱动模型行为的核心，必须至少提供 1 条。

```python
examples = [
    lx.data.ExampleData(
        # text: 示例输入文本（应与实际输入文本风格一致）
        text="Marie Curie was awarded the Nobel Prize in Physics in 1903.",
        
        # extractions: 该文本中期望抽取的结果列表
        extractions=[
            lx.data.Extraction(
                # extraction_class: 实体/关系的类型名称（自定义，如 person/org/relation）
                extraction_class="person",
                
                # extraction_text: 必须是 text 中的原文子串（不能改写/摘要）
                # 建议按出现顺序排列，不可重叠
                extraction_text="Marie Curie",
                
                # attributes: 可选，该实体的附加属性 key-value 对
                attributes={
                    "occupation": "physicist",
                    "award": "Nobel Prize in Physics"
                }
            ),
            lx.data.Extraction(
                extraction_class="award",
                extraction_text="Nobel Prize in Physics",
                attributes={"year": "1903"}
            ),
        ]
    )
]
```

**`ExampleData` 字段规范：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `text` | `str` | 示例输入文本（原始文本） |
| `extractions` | `list[Extraction]` | 对应该文本的抽取结果 |

**`Extraction` 字段规范（在 examples 中）：**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `extraction_class` | `str` | 是 | 实体类型，全局唯一命名（如 `"person"`, `"event"`） |
| `extraction_text` | `str` | 是 | 原文中的精确文字，不能改写 |
| `attributes` | `dict[str, str\|list[str]]` | 否 | 附加属性，key 为属性名，value 为字符串或字符串列表 |

> **关键约束：** `extraction_text` 必须是 `text` 的子串，按出现顺序排列，不可相互重叠。违反此约束会触发 `PromptAlignment` 警告/错误。

### 3.4 Prompt 描述规范

```python
prompt_description = """
Extract all person names, organizations, and relationships from the text.
Use exact text spans for extractions—do not paraphrase or summarize.
List extractions in order of appearance. Do not include overlapping spans.
Provide meaningful attributes for context.
"""
```

推荐在 prompt 中明确：
- 需要抽取的实体类型
- 强调"使用原文精确文字"
- 要求"按出现顺序"排列
- 说明"不能重叠"

---

## 4. 输出规范

### 4.1 Python 返回值

| 输入类型 | 返回类型 |
|---|---|
| 单个字符串 / URL | `data.AnnotatedDocument`（单个对象） |
| `Iterable[Document]` / CSV | `list[data.AnnotatedDocument]`（列表） |

### 4.2 `AnnotatedDocument` 数据结构

```python
@dataclasses.dataclass
class AnnotatedDocument:
    document_id: str          # 文档唯一 ID（自动生成或用户指定）
    text: str | None          # 原始输入文本
    extractions: list[Extraction] | None  # 抽取结果列表
```

### 4.3 `Extraction` 数据结构（完整字段）

```python
@dataclasses.dataclass
class Extraction:
    extraction_class: str           # 实体类型（如 "person", "event"）
    extraction_text: str            # 从 LLM 输出解析出的实体文本
    
    char_interval: CharInterval | None
    # 该实体在原始全文中的字符位置（绝对坐标）
    # None 表示无法在原文中定位（通常是 LLM 幻觉或来自 examples 的内容）
    # 过滤方式：[e for e in result.extractions if e.char_interval]
    
    alignment_status: AlignmentStatus | None
    # 对齐质量：
    #   MATCH_EXACT   = "match_exact"   → LLM 输出与原文完全一致（最高质量）
    #   MATCH_GREATER = "match_greater" → LLM 输出包含原文（如带了额外标点）
    #   MATCH_LESSER  = "match_lesser"  → LLM 输出是原文的子串
    #   MATCH_FUZZY   = "match_fuzzy"   → 模糊 token 匹配（降级策略）
    
    extraction_index: int | None    # 该抽取在文档中的序号（按出现顺序）
    group_index: int | None         # 分组索引（多实体关联场景）
    description: str | None        # 抽取描述（可选）
    attributes: dict[str, str | list[str]] | None  # 附加属性 KV
    token_interval: TokenInterval | None  # Token 级位置（内部用）

@dataclasses.dataclass
class CharInterval:
    start_pos: int | None  # 字符起始位置（inclusive，基于原始全文）
    end_pos: int | None    # 字符结束位置（exclusive，基于原始全文）
```

**使用 `char_interval` 还原原文片段：**
```python
for extraction in result.extractions:
    if extraction.char_interval:
        span = result.text[
            extraction.char_interval.start_pos:
            extraction.char_interval.end_pos
        ]
        print(f"[{extraction.extraction_class}] '{span}'")
        print(f"  → LLM输出: '{extraction.extraction_text}'")
        print(f"  → 对齐质量: {extraction.alignment_status.value}")
        print(f"  → 属性: {extraction.attributes}")
```

### 4.4 JSONL 文件格式

通过 `lx.io.save_annotated_documents()` 保存，每行为一个 JSON 对象：

```jsonl
{
  "document_id": "doc_a1b2c3d4",
  "text": "Marie Curie was awarded the Nobel Prize in Physics in 1903.",
  "extractions": [
    {
      "extraction_class": "person",
      "extraction_text": "Marie Curie",
      "char_interval": {
        "start_pos": 0,
        "end_pos": 11
      },
      "alignment_status": "match_exact",
      "extraction_index": 0,
      "group_index": null,
      "description": null,
      "attributes": {
        "occupation": "physicist",
        "award": "Nobel Prize in Physics"
      },
      "token_interval": {
        "start_index": 0,
        "end_index": 2
      }
    },
    {
      "extraction_class": "award",
      "extraction_text": "Nobel Prize in Physics",
      "char_interval": {
        "start_pos": 36,
        "end_pos": 58
      },
      "alignment_status": "match_exact",
      "extraction_index": 1,
      "group_index": null,
      "description": null,
      "attributes": {
        "year": "1903"
      },
      "token_interval": {
        "start_index": 7,
        "end_index": 11
      }
    }
  ]
}
```

### 4.5 读取已保存的 JSONL

```python
for adoc in lx.io.load_annotated_documents_jsonl("extraction_results.jsonl"):
    print(adoc.document_id, len(adoc.extractions))
```

### 4.6 过滤与使用建议

```python
# 1. 仅保留有效定位的抽取（过滤幻觉/examples溢出）
grounded = [e for e in result.extractions if e.char_interval]

# 2. 按 extraction_class 分组
from collections import defaultdict
by_class = defaultdict(list)
for e in grounded:
    by_class[e.extraction_class].append(e)

# 3. 高质量过滤（仅精确匹配）
from langextract.core.data import AlignmentStatus
exact_only = [
    e for e in grounded
    if e.alignment_status == AlignmentStatus.MATCH_EXACT
]

# 4. 转为字典（适合存入数据库）
import dataclasses
records = [dataclasses.asdict(e) for e in grounded]
```

---

## 5. 模型接入规范

### 5.1 内置 Provider 速查

| Provider | 适用 `model_id` 前缀 | 依赖安装 | API Key 环境变量 |
|---|---|---|---|
| `GeminiLanguageModel` | `gemini-*` | 内置（默认） | `GEMINI_API_KEY` 或 `LANGEXTRACT_API_KEY` |
| `OpenAILanguageModel` | `gpt-4*`, `gpt-5*` | `pip install langextract[openai]` | `OPENAI_API_KEY` 或 `LANGEXTRACT_API_KEY` |
| `OllamaLanguageModel` | `gemma*`, `llama*`, `mistral*`, `qwen*`, `deepseek*`, `phi*` 等 | 内置，需本地 Ollama 服务 | 无需 Key（`OLLAMA_BASE_URL` 可选） |

**Ollama 完整支持的 model_id 前缀：**
```
gemma, llama, mistral, mixtral, phi, qwen, deepseek,
command-r, starcoder, codellama, codegemma, tinyllama,
wizardcoder, gpt-oss
以及 HuggingFace 格式：meta-llama/*, google/gemma-*, mistralai/*, 等
```

### 5.2 三种接入方式

#### 方式一：通过 model_id 自动路由（推荐）

```python
# Gemini（云端）
result = lx.extract(
    text_or_documents=text,
    model_id="gemini-2.5-flash",    # 自动路由到 GeminiLanguageModel
    prompt_description=prompt,
    examples=examples,
)

# OpenAI（需额外安装 pip install langextract[openai]）
result = lx.extract(
    text_or_documents=text,
    model_id="gpt-4o",              # 自动路由到 OpenAILanguageModel
    prompt_description=prompt,
    examples=examples,
    fence_output=True,
    use_schema_constraints=False,   # OpenAI 目前不支持 schema 约束
)

# Ollama（本地，无需 API Key）
result = lx.extract(
    text_or_documents=text,
    model_id="gemma2:2b",           # 自动路由到 OllamaLanguageModel
    model_url="http://localhost:11434",
    prompt_description=prompt,
    examples=examples,
    fence_output=False,
    use_schema_constraints=False,
)
```

#### 方式二：通过 `ModelConfig` 精确指定

```python
from langextract import factory

config = factory.ModelConfig(
    model_id="gemini-2.5-pro",
    provider="GeminiLanguageModel",  # 显式指定 Provider 类名
    provider_kwargs={
        "api_key": "YOUR_KEY",
        "temperature": 0.0,
        "max_workers": 20,
        # Vertex AI 模式
        "vertexai": True,
        "project": "your-gcp-project",
        "location": "us-central1",
    }
)

result = lx.extract(
    text_or_documents=text,
    config=config,
    prompt_description=prompt,
    examples=examples,
)
```

#### 方式三：预构建 Model 实例直接传入

```python
from langextract.providers.gemini import GeminiLanguageModel

model = GeminiLanguageModel(
    model_id="gemini-2.5-flash",
    api_key="YOUR_KEY",
    temperature=0.0,
    max_workers=10,
)

result = lx.extract(
    text_or_documents=text,
    model=model,              # 直接传入，优先级最高
    prompt_description=prompt,
    examples=examples,
)
```

### 5.3 自定义 Provider 接入规范

实现自定义 Provider 需遵循以下接口：

```python
import langextract as lx
from langextract.providers import router
from langextract.core import base_model, types

@router.register(
    r'^my-model',      # 正则 pattern，匹配此 model_id 时使用该 Provider
    r'^my-llm',
    priority=10        # 优先级（数字越大越优先；内置 Provider 均为 10）
)
class MyCustomLanguageModel(base_model.BaseLanguageModel):
    
    def __init__(
        self,
        model_id: str = "my-model-v1",
        api_key: str | None = None,
        base_url: str | None = None,
        format_type = lx.data.FormatType.JSON,
        temperature: float | None = None,
        max_workers: int = 10,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.model_id = model_id
        self.api_key = api_key or os.environ.get("MY_MODEL_API_KEY")
        self.client = MySDKClient(api_key=self.api_key, base_url=base_url)
    
    def infer(
        self,
        batch_prompts: list[str],
        **kwargs
    ) -> Iterator[list[types.ScoredOutput]]:
        """
        核心推理方法。
        
        Args:
            batch_prompts: 一批 prompt 字符串列表
            
        Yields:
            每个 prompt 对应一个 list[ScoredOutput]
            ScoredOutput: namedtuple(score=float, output=str)
            通常只返回 1 个候选：[ScoredOutput(score=1.0, output=llm_response)]
        """
        # 并行示例
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [
                executor.submit(self._call_api, prompt, **kwargs)
                for prompt in batch_prompts
            ]
            for future in futures:
                response_text = future.result()
                yield [types.ScoredOutput(score=1.0, output=response_text)]
    
    def _call_api(self, prompt: str, **kwargs) -> str:
        response = self.client.generate(
            model=self.model_id,
            prompt=prompt,
        )
        return response.text
```

**`ScoredOutput` 结构：**
```python
# core/types.py
ScoredOutput = collections.namedtuple('ScoredOutput', ['score', 'output'])
# score: float  - 候选输出的置信分（无评分时固定为 1.0）
# output: str   - LLM 生成的原始文本（JSON/YAML 格式的抽取结果）
```

**以 Python Entry Point 注册 Plugin（推荐的分发方式）：**
```toml
# pyproject.toml
[project.entry-points."langextract.providers"]
myprovider = "langextract_myprovider:MyCustomLanguageModel"
```

### 5.4 支持结构化输出 Schema（可选）

若 LLM 支持结构化输出（如 Gemini 的 `response_schema`），可实现 `BaseSchema`：

```python
from langextract.core import schema

class MySchema(schema.BaseSchema):
    
    @classmethod
    def from_examples(cls, examples, attribute_suffix="_attributes"):
        """从 few-shot examples 自动推断 JSON Schema 结构"""
        # 分析 examples 中的 extraction_class 和 attributes 构建 schema
        ...
        return cls(schema_dict)
    
    def to_provider_config(self) -> dict:
        """转换为 Provider 的初始化参数（如 response_schema）"""
        return {"response_schema": self._schema_dict}
    
    @property
    def requires_raw_output(self) -> bool:
        """True 表示 LLM 直接输出 JSON，不需要代码围栏"""
        return True
    
    @property
    def supports_strict_mode(self) -> bool:
        return True

# 在 Provider 中声明关联的 Schema 类
class MyCustomLanguageModel(base_model.BaseLanguageModel):
    @classmethod
    def get_schema_class(cls):
        return MySchema
```

### 5.5 Provider 选择的注意事项

| Provider | Schema 约束 | fence_output 默认值 | 特殊配置 |
|---|---|---|---|
| GeminiLanguageModel | ✅ 支持 | `False`（schema 直接输出 JSON） | `vertexai=True` 用于企业级；支持 Batch API |
| OpenAILanguageModel | ❌ 不支持（v1.2.1） | `False`（JSON mode） | 需设 `use_schema_constraints=False`, `fence_output=True` |
| OllamaLanguageModel | ❌ 不支持 | `False` | 需设 `use_schema_constraints=False` |
| 自定义 Provider | 可选实现 | 取决于 schema | 通过 entry point 注册 |

---

## 6. 关键参数速查

### 6.1 分块参数

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `max_char_buffer` | `int` | `1000` | 每个 Chunk 的最大字符数。越小越精确但 API 调用次数越多 |
| `batch_length` | `int` | `10` | 每批 Chunk 数量，应 >= `max_workers` 才能充分并行 |
| `max_workers` | `int` | `10` | 并行推理线程数（有效并行 = min(batch_length, max_workers)） |
| `extraction_passes` | `int` | `1` | 多轮抽取，>1 时按"先到先得"合并，提升召回率，成倍增加 API 成本 |
| `context_window_chars` | `int\|None` | `None` | 前一 Chunk 尾部注入当前 Chunk，用于跨块共指消解 |

### 6.2 对齐参数（通过 `resolver_params` 传入）

```python
result = lx.extract(
    ...,
    resolver_params={
        "enable_fuzzy_alignment": True,       # 是否启用模糊匹配（默认 True）
        "fuzzy_alignment_threshold": 0.75,    # 模糊匹配 token 重叠率阈值（0.0-1.0）
        "accept_match_lesser": True,          # 是否接受子集匹配（默认 True）
        "suppress_parse_errors": True,        # 忽略单 Chunk 解析错误（默认 True）
        "extraction_index_suffix": "_index",  # 排序 index 字段后缀（None=按出现顺序）
        # 或直接传入 FormatHandler 对象：
        "format_handler": lx.core.format_handler.FormatHandler(
            format_type=lx.data.FormatType.JSON,
            use_fences=True,
            use_wrapper=True,
        ),
    }
)
```

### 6.3 环境变量

```bash
# Gemini API Key（两者等价）
export GEMINI_API_KEY="your-gemini-key"
export LANGEXTRACT_API_KEY="your-key"   # 通用 fallback

# OpenAI API Key
export OPENAI_API_KEY="your-openai-key"

# Ollama 服务地址（默认 http://localhost:11434）
export OLLAMA_BASE_URL="http://your-ollama-host:11434"

# 禁用 Plugin 自动发现
export LANGEXTRACT_DISABLE_PLUGINS=1
```

---

## 7. 对接多模态 RAG 的架构建议

基于以上规范，langextract 在多模态 RAG 系统中的定位应是**纯文本层的实体/关系抽取器**，负责从已解析好的文本内容中提取结构化知识，其上下游需要额外组件支撑。

### 7.1 推荐分层架构

```
┌──────────────────────────────────────────────────────┐
│  Layer 0: 文档解析层（langextract 不提供，需自建）        │
│  pypdf / python-docx / openpyxl / unstructured        │
│  → 输出：{ text: str, images: [PIL.Image], tables: [] }│
└──────────────────────┬───────────────────────────────┘
                       │
         ┌─────────────┴──────────────┐
         ▼                            ▼
┌────────────────┐         ┌──────────────────────┐
│  文本分支       │         │  图像/表格/公式分支    │
│  langextract   │         │  多模态 LLM（自建）    │
│  ──────────── │         │  GPT-4o / Gemini Pro  │
│  实体抽取       │         │  图像描述 / 表格转文本  │
│  关系抽取       │         │  公式识别              │
│  → extractions │         │  → text + metadata    │
└───────┬────────┘         └─────────┬────────────┘
        │                            │
        └─────────────┬──────────────┘
                      ▼
        ┌─────────────────────────────┐
        │  Layer 1: 知识存储层（自建）  │
        │  向量数据库（Milvus/Qdrant）  │
        │  图数据库（Neo4j/NebulaGraph）│
        │  关系数据库（PostgreSQL）     │
        └─────────────┬───────────────┘
                      ▼
        ┌─────────────────────────────┐
        │  Layer 2: 检索层（自建）     │
        │  向量检索 + 关键词检索 +      │
        │  图谱检索 混合检索            │
        └─────────────┬───────────────┘
                      ▼
        ┌─────────────────────────────┐
        │  Layer 3: 生成层（自建）     │
        │  多模态 LLM 生成最终回答      │
        │  图片/表格一起展示给用户       │
        └─────────────────────────────┘
```

### 7.2 langextract 在 RAG 中的具体接入点

**接入点一：知识图谱实体/关系抽取**

```python
# 将解析出的文本页面送入 langextract 进行实体抽取
# 然后将 extractions 写入图数据库
for page_text in document_pages:
    result = lx.extract(
        text_or_documents=page_text,
        prompt_description="Extract entities and relationships for knowledge graph.",
        examples=kg_examples,
        model_id="gemini-2.5-flash",
    )
    # 将 result.extractions 写入 Neo4j
    for extraction in result.extractions:
        if extraction.char_interval:  # 过滤幻觉
            neo4j_session.write(
                node_type=extraction.extraction_class,
                text=extraction.extraction_text,
                properties=extraction.attributes,
                source_doc=result.document_id,
                char_start=extraction.char_interval.start_pos,
                char_end=extraction.char_interval.end_pos,
            )
```

**接入点二：利用 `char_interval` 定位原文来源**

langextract 的 `char_interval` 可精确定位每个实体在原文中的位置，这是 RAG 引用溯源的基础：

```python
# 在 RAG 检索到某个实体后，还原其原文上下文
def get_context_for_extraction(extraction, source_text, window=200):
    if not extraction.char_interval:
        return None
    start = max(0, extraction.char_interval.start_pos - window)
    end = min(len(source_text), extraction.char_interval.end_pos + window)
    return source_text[start:end]
```

### 7.3 输入对接注意事项

由于 langextract 只接受**纯文本字符串**，在 RAG 系统中需要在上游完成：

1. **PDF 解析** → 文字层提取（pypdf / pdfplumber）
2. **Word/PPT/Excel** → python-docx / python-pptx / openpyxl 转文本
3. **图片中的文字** → OCR（paddleocr / tesseract）+ 多模态 LLM 描述
4. **表格** → 转为 Markdown 或 CSV 文本格式
5. **公式** → LaTeX 字符串或自然语言描述

处理后的文本才能传入 `lx.extract(text_or_documents=...)`。
