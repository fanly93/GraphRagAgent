"""所有 Prompt 模板集中管理。"""

# ── Node 1: 路由 ──
ROUTE_PROMPT = """\
你是一个查询路由器。根据用户问题，判断最适合的检索策略。

检索策略说明：
- entity_query：问题涉及某个具体实体的属性、来源、关系
  示例："LangGraph 是谁开发的？"、"qwen-plus 支持哪些功能？"
- semantic_query：需要段落级理解，涉及流程、背景、综合描述
  示例："LangChain 的发展历程是什么？"、"RAG 有哪些应用场景？"
- hybrid_query：同时需要精确实体信息 + 段落上下文
  示例："LangChain 和 LangGraph 的关系，以及各自的应用场景？"
- direct_answer：通用常识问题，无需检索文档
  示例："什么是大语言模型？"

用户问题：{question}

只输出策略名称（entity_query / semantic_query / hybrid_query / direct_answer），不要其他内容。"""

# ── Node 3: 文档评分 ──
GRADE_PROMPT = """\
你是一个文档相关性评估器。

用户问题：{question}

以下是检索到的内容，判断整体是否足够回答该问题：

{context}

请用 JSON 格式回答（不要有其他内容）：
{{
  "sufficient": true 或 false,
  "reason": "简短说明（1句话）"
}}

sufficient=true：内容足够回答问题
sufficient=false：内容不足、偏题或缺少关键信息"""

# ── Node 4: 问题改写 ──
REWRITE_PROMPT = """\
当前检索结果不足以回答用户问题，请改写问题以获得更好的检索效果。

原始问题：{question}
检索不足原因：{reason}

改写要求：
1. 保持原始意图不变
2. 使用更精确的关键词或术语
3. 可以拆解为更具体的子问题
4. 只输出改写后的问题，不要解释

改写后的问题："""

# ── Node 5: 答案生成 ──
GENERATE_PROMPT = """\
你是一个专业的知识问答助手，拥有两类参考资料：

【知识图谱实体信息】（结构化，来自文档实体抽取）
{kg_context}

【文档段落】（原文，来自结构感知切分）
{passage_context}

回答规则：
1. 优先用知识图谱实体信息回答属性/关系类问题（标注 [KG]）
2. 用文档段落补充上下文、解释流程和背景（标注 [段落]）
3. 两类来源均需标注引用，格式：[KG: 实体名] 或 [段落: 文档/章节]
4. 信息冲突时，以文档段落原文为准
5. 若信息不足，明确说明

用户问题：{question}

回答："""

# ── 直接回答（无检索）──
DIRECT_ANSWER_PROMPT = """\
请直接回答以下问题（无需检索文档）：

{question}

回答："""
