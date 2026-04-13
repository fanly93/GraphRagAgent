# LangExtract Pipeline — Claude Code 工作指南

## 虚拟环境（强制要求）

**此目录使用独立 venv（Python 3.13.12），与 mineru_parser 的 venv 完全独立。**

```bash
# 每次运行前必须激活
source /Users/tanglin/VibeCoding/GraphRagAgent/langextract_pipeline/.venv/bin/activate
```

- **禁止**使用系统 `python3` 直接执行
- **禁止**与 `mineru_parser/.venv` 混用
- langextract 以 editable 模式从 `../reference_projects/langextract` 安装

**首次初始化：**
```bash
python3 -m venv .venv
.venv/bin/pip install -e "../reference_projects/langextract[test]" openai python-dotenv tqdm
```

---

## 运行命令

```bash
python run_pipeline.py                          # 处理全部文档
python run_pipeline.py "0.LangChain技术生态介绍" # 指定文档
python run_pipeline.py --dry-run                # 预览，不调用 API
```

---

## 项目结构

```
langextract_pipeline/
├── .venv/              # 虚拟环境（Python 3.13.12）
├── .env                # API Keys + 参数（不提交 git）
├── config.py           # 配置加载
├── providers.py        # DashScope / DeepSeek 模型接入
├── mineru_reader.py    # 读取 MinerU output → lx.data.Document
├── kg_prompts.py       # KG 抽取 Prompt + Few-shot 示例
├── run_pipeline.py     # 主入口
└── output/             # 抽取结果（.jsonl + .html）
```

---

## .env 关键配置

| 参数 | 默认值 | 说明 |
|---|---|---|
| `KG_MODEL_PROVIDER` | `dashscope` | `dashscope` 或 `deepseek` |
| `KG_MODEL_ID` | `qwen-plus` | 模型 ID（实测用 `qwen3.6-plus`） |
| `DASHSCOPE_API_KEY` | — | DashScope 时必填 |
| `DEEPSEEK_API_KEY` | — | DeepSeek 时必填 |
| `MAX_CHAR_BUFFER` | `3000` | 每 Chunk 最大字符数 |
| `MAX_WORKERS` | `3` | 并行数（DashScope 免费额度建议 ≤ 3） |
| `EXTRACTION_PASSES` | `1` | 多轮抽取（>1 提升召回率，成倍增加 API 调用） |

---

## 模型接入

langextract 内置路由会将 `qwen*`/`deepseek*` 误路由到 Ollama。  
**解决方案：** 直接实例化 `OpenAILanguageModel` 通过 `model=` 参数传入，绕过路由。

| Provider | base_url |
|---|---|
| DashScope | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| DeepSeek | `https://api.deepseek.com/v1` |

**必要配置：** `use_schema_constraints=False`、`fence_output=True`

---

## MinerU → LangExtract 对接规范（mineru_reader.py）

**输入：** `mineru_parser/output/{文档名}/`  
**输出：** `list[lx.data.Document]`

| 文件 | 处理方式 |
|------|----------|
| `full.md` | 主文本（必读） |
| `*_content_list.json` 中 `type=table` | 若 full.md 无 MD 表格则追加 HTML（防重复） |
| `discarded` 块 / `layout.json` / `images/` | 不读取 |

**文本 < 200 字符时自动打印警告**（纯图片文档，建议用 `doc_filter` 跳过）

---

## 输出规范（实测）

每次运行产生 2 个文件：

| 文件 | 格式 | 说明 |
|---|---|---|
| `output/kg_extraction_{YYYYMMDD_HHMMSS}.jsonl` | JSONL | 每行一个 AnnotatedDocument |
| `output/kg_extraction_{YYYYMMDD_HHMMSS}.html` | HTML | 交互式可视化 |

### JSONL 结构

```json
{"document_id": "0.LangChain技术生态介绍", "text": "...", "extractions": [
  {
    "extraction_class": "product",
    "extraction_text": "LangChain",
    "char_interval": { "start_pos": 38, "end_pos": 47 },
    "alignment_status": "match_exact",
    "extraction_index": 1,
    "group_index": 0,
    "description": null,
    "attributes": { "type": "大模型开发框架" }
  }
]}
```

### 关键字段

| 字段 | 说明 |
|---|---|
| `char_interval` | 原文字符坐标（基于 `text` 字段）；`null` = 未定位，**必须过滤** |
| `alignment_status` | `match_exact`（精确）/ `match_fuzzy`（模糊）/ `null`（未定位） |
| `group_index` | 跨 Chunk 全局编号（从 0 开始） |
| `attributes` | 自由 KV，含实体属性和关系 |

### 结果过滤

```python
import json
with open("output/kg_extraction_xxx.jsonl") as f:
    for line in f:
        doc = json.loads(line)
        grounded = [e for e in doc["extractions"] if e["char_interval"]]
        exact    = [e for e in grounded if e["alignment_status"] == "match_exact"]
        span = doc["text"][e["char_interval"]["start_pos"]:e["char_interval"]["end_pos"]]
```

---

## 实测性能参考

| 文档 | 字符数 | Chunk 数 | 耗时 | 抽取 | grounded | match_exact |
|---|---|---|---|---|---|---|
| 0.LangChain技术生态介绍 | 10,671 | 4 | ~417s | 96 | 70（72.9%） | 61（87%） |

---

## 已知问题

| 问题 | 原因 | 状态 |
|---|---|---|
| `Prompt alignment FAILED` 警告 | few-shot 示例中词多次出现，顺序检查误报 | 不影响抽取，可忽略 |
| qwen/deepseek 路由到 Ollama | langextract 内置模式匹配 | ✅ 已修复：传 model 实例绕过 |
| 纯图片文档抽取结果极少 | 图片内容无法被文本 LLM 处理 | 用 `--dry-run` 确认后通过 doc_filter 跳过 |

---

## 完整规范文档

详见 `docs/mineru-langextract-pipeline-v1.0.md`
