"""知识图谱抽取 Prompt 与 Few-shot 示例。

目标：从 MinerU 解析出的技术/业务文档中抽取实体和关系，
用于构建知识图谱（Entity-Relation Graph）。

实体类型（extraction_class）：
    person        人物
    organization  组织/公司
    product       产品/工具/框架
    technology    技术/算法/概念
    event         事件/行为
    location      地点

关系通过 attributes 中的 relation / target 字段表达：
    person.works_at       → organization
    product.created_by    → organization/person
    product.part_of       → product/technology
    technology.used_by    → product/organization
    event.actor           → person/organization
    event.object          → product/technology
"""

import langextract as lx

# ─────────────────────────────────────────────
# Prompt 描述（中英双语，适应技术文档）
# ─────────────────────────────────────────────

KG_PROMPT_DESCRIPTION = """\
从文本中提取实体和关系，用于构建知识图谱。

实体类型：
- person（人物）：真实人名，如开发者、研究者、创始人
- organization（组织）：公司、机构、开源社区
- product（产品/工具/框架）：软件框架、库、平台、API
- technology（技术/概念）：算法、技术方法、架构模式、专业术语
- event（事件）：发布、更新、收购、发布会等具体事件

抽取规则：
1. 使用文档中的原始文字，不要改写或摘要
2. 按在文本中出现的先后顺序排列
3. 不同实体的文本区间不得重叠
4. 为每个实体填写有意义的 attributes，包括与其他实体的关系

Extract entities and relationships for knowledge graph construction.
Use exact text spans from the source. List in order of appearance. No overlapping spans.\
"""

# ─────────────────────────────────────────────
# Few-shot 示例
# ─────────────────────────────────────────────

KG_EXAMPLES = [
    lx.data.ExampleData(
        text=(
            "LangChain由Harrison Chase创立，于2022年10月开源，"
            "是一个基于Python和TypeScript的大模型开发框架，"
            "被广泛用于构建RAG应用和Agent系统。"
            "OpenAI的GPT-4发布后，LangChain迅速集成了Function Calling功能。"
        ),
        extractions=[
            lx.data.Extraction(
                extraction_class="product",
                extraction_text="LangChain",
                attributes={
                    "type": "大模型开发框架",
                    "created_by": "Harrison Chase",
                    "language": "Python, TypeScript",
                    "use_case": "RAG应用, Agent系统",
                },
            ),
            lx.data.Extraction(
                extraction_class="person",
                extraction_text="Harrison Chase",
                attributes={
                    "role": "创始人",
                    "created": "LangChain",
                },
            ),
            lx.data.Extraction(
                extraction_class="event",
                extraction_text="2022年10月开源",
                attributes={
                    "actor": "LangChain",
                    "type": "开源发布",
                    "year": "2022",
                },
            ),
            lx.data.Extraction(
                extraction_class="technology",
                extraction_text="RAG应用",
                attributes={
                    "full_name": "Retrieval-Augmented Generation",
                    "used_by": "LangChain",
                },
            ),
            lx.data.Extraction(
                extraction_class="technology",
                extraction_text="Agent系统",
                attributes={
                    "used_by": "LangChain",
                },
            ),
            lx.data.Extraction(
                extraction_class="organization",
                extraction_text="OpenAI",
                attributes={
                    "type": "AI公司",
                    "product": "GPT-4",
                },
            ),
            lx.data.Extraction(
                extraction_class="product",
                extraction_text="GPT-4",
                attributes={
                    "created_by": "OpenAI",
                    "type": "大语言模型",
                },
            ),
            lx.data.Extraction(
                extraction_class="technology",
                extraction_text="Function Calling",
                attributes={
                    "provided_by": "GPT-4",
                    "integrated_by": "LangChain",
                },
            ),
        ],
    ),
]

# ─────────────────────────────────────────────
# lx.extract() 调用参数预设（通过 **KG_EXTRACT_PARAMS 展开）
# ─────────────────────────────────────────────

KG_EXTRACT_PARAMS = {
    "prompt_description": KG_PROMPT_DESCRIPTION,
    "examples": KG_EXAMPLES,
    "use_schema_constraints": False,   # OpenAI-compat 模型不支持 Gemini 结构化 Schema
    "fence_output": True,              # 要求模型用代码围栏包裹 JSON 输出（更稳定）
    "show_progress": True,
    "debug": False,
}
