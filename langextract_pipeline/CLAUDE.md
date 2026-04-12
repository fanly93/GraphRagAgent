# LangExtract Pipeline — Claude Code 工作指南

## 虚拟环境（强制要求）

**在此目录下执行任何 Python 命令之前，必须先激活虚拟环境。**

```bash
source .venv/bin/activate
```

### 执行规则

- **禁止** 使用系统 `python3` 直接执行
- **必须** 使用 `.venv/bin/python` 或先 `source .venv/bin/activate`
- langextract 以 editable 模式从 `../reference_projects/langextract` 安装

### 虚拟环境不存在时初始化

```bash
cd /Users/tanglin/VibeCoding/GraphRagAgent/langextract_pipeline
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
├── .venv/              # 虚拟环境
├── .env                # API Keys + 参数（不提交 git）
├── config.py           # 配置加载
├── providers.py        # DashScope / DeepSeek 模型接入
├── mineru_reader.py    # 读取 MinerU output → lx.data.Document
├── kg_prompts.py       # KG 抽取 Prompt + Few-shot 示例
├── run_pipeline.py     # 主入口
└── output/             # 抽取结果（JSONL + HTML）
```

---

## .env 关键配置

| 参数 | 默认值 | 说明 |
|---|---|---|
| `KG_MODEL_PROVIDER` | `dashscope` | `dashscope` 或 `deepseek` |
| `KG_MODEL_ID` | `qwen-plus` | 模型 ID |
| `DASHSCOPE_API_KEY` | — | DashScope 时必填 |
| `DEEPSEEK_API_KEY` | — | DeepSeek 时必填 |
| `MAX_CHAR_BUFFER` | `3000` | 每 Chunk 最大字符数（越小越精确，API 调用越多） |
| `MAX_WORKERS` | `3` | 并行数（DashScope 免费额度建议 ≤ 3） |
| `EXTRACTION_PASSES` | `1` | 多轮抽取（>1 提升召回率，成倍增加 API 调用） |

---

## 模型接入

通过 `OpenAILanguageModel(base_url=...)` 对接 OpenAI-compatible 接口，
用 `model=` 参数直接传给 `lx.extract()`，**绕过内部路由**（避免 qwen/deepseek 被误路由到 Ollama）。

| Provider | base_url |
|---|---|
| DashScope | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| DeepSeek | `https://api.deepseek.com/v1` |

**必要配置**：`use_schema_constraints=False`、`fence_output=True`

---

## 输出规范（实测）

每次运行产生 2 个文件（`output/kg_extraction_{YYYYMMDD_HHMMSS}`）：

| 文件 | 格式 | 说明 |
|---|---|---|
| `kg_extraction_*`（无后缀） | JSON | AnnotatedDocument，含 text + extractions |
| `kg_extraction_*.html` | HTML | 交互式可视化，浏览器直接打开 |

> ⚠️ `lx.io.save_annotated_documents()` 保存的文件**无 `.jsonl` 后缀**，调用 `lx.visualize()` 时也传无后缀路径。

### JSONL 结构

```json
{
  "document_id": "0.LangChain技术生态介绍",
  "text": "...",
  "extractions": [
    {
      "extraction_class": "product",
      "extraction_text": "LangChain",
      "char_interval": { "start_pos": 38, "end_pos": 47 },
      "alignment_status": "match_exact",
      "extraction_index": 1,
      "group_index": 0,
      "description": null,
      "attributes": { "type": "大模型开发框架", "evolved_to": "LangChain AI" }
    }
  ]
}
```

### 关键字段

| 字段 | 说明 |
|---|---|
| `char_interval` | 原文字符绝对坐标；`null` = 未定位，需过滤 |
| `alignment_status` | `match_exact`（精确）/ `match_fuzzy`（模糊）/ `null`（未定位） |
| `group_index` | 跨 Chunk 全局编组索引（从 0 开始） |
| `attributes` | 自由 KV，常见 key：`type` / `role` / `used_by` / `actor` |

### 结果过滤

```python
# 只保留有效定位
grounded = [e for e in extractions if e["char_interval"]]

# 只保留精确匹配（最高质量）
exact = [e for e in grounded if e["alignment_status"] == "match_exact"]

# 还原原文片段
span = text[e["char_interval"]["start_pos"]:e["char_interval"]["end_pos"]]
```

---

## 实测性能参考

| 文档字符数 | MAX_CHAR_BUFFER | Chunk 数 | MAX_WORKERS | 耗时 |
|---|---|---|---|---|
| 10,671 | 3000 | 4 | 3 | ~417 秒 |

**实测抽取质量（LangChain 文档）**：

- 总抽取 96 条 | grounded 70（72.9%）| match_exact 61（87%）
- 实体类型：product 30 / technology 19 / organization 16 / event 5

---

## 已知问题

| 问题 | 原因 | 状态 |
|---|---|---|
| `Prompt alignment FAILED` 警告 | few-shot 示例中某词多次出现，顺序检查误报 | 不影响抽取，可忽略 |
| HTML 生成失败（已修复） | `visualize()` 传入带 `.jsonl` 后缀路径，但文件无后缀 | ✅ 已修复 |
