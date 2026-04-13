# 多模态 RAG Web 系统前端设计规范 v1.0

> 角色定位：资深前端架构师 + 产品设计师  
> 对接后端规范：`docs/backend-api-spec-v1.0.md`  
> 编写日期：2026-04-13  
> 目标：可运行的 Web 原型，覆盖完整核心流程

---

## 目录

1. [产品定位与设计原则](#1-产品定位与设计原则)
2. [技术架构选型](#2-技术架构选型)
3. [整体 UI 布局](#3-整体-ui-布局)
4. [设计语言规范](#4-设计语言规范)
5. [页面清单与路由](#5-页面清单与路由)
6. [页面详细设计](#6-页面详细设计)
   - 6.1 知识库管理页
   - 6.2 智能问答页
   - 6.3 系统状态页
7. [核心交互逻辑](#7-核心交互逻辑)
8. [组件规范](#8-组件规范)
9. [响应式设计规范](#9-响应式设计规范)
10. [前端目录结构](#10-前端目录结构)
11. [API 对接层规范](#11-api-对接层规范)
12. [状态管理规范](#12-状态管理规范)

---

## 1. 产品定位与设计原则

### 1.1 产品定位

**GraphRAG Agent** 是一款面向知识工作者的多模态智能知识问答系统。用户将企业文档（PDF/Word/PPT/Excel/图片）上传后，系统自动构建向量+知识图谱双引擎索引，并通过 Agentic RAG 流程回答自然语言问题，同时提供精确的检索来源溯源。

**核心价值主张**：
- 上传即用，全自动处理（无需手动配置索引）
- 答案有据可查（KG 实体卡 + 原文段落双来源）
- AI 推理透明（展示路由策略、改写次数、检索充分性）

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| **专业感** | 面向企业用户，界面沉稳、信息密度适中，区别于消费级 AI 产品 |
| **过程可见** | 异步任务（解析/建索引）全程进度可视，消除等待焦虑 |
| **溯源优先** | 答案来源（KG 实体 + 原文段落）与答案等权重展示，不隐藏 |
| **渐进式披露** | 核心内容优先展示，详细信息按需展开（Expandable Cards） |
| **零学习成本** | 上传 → 等待 → 提问，三步核心流程无需说明书 |

---

## 2. 技术架构选型

### 2.1 前端技术栈

| 层次 | 选型 | 版本 | 理由 |
|------|------|------|------|
| 框架 | **React** | 18.x | 生态成熟，Hooks + Context 足够 MVP |
| 构建工具 | **Vite** | 5.x | 极快冷启动，ESM 原生 |
| 语言 | **TypeScript** | 5.x | 类型安全，与后端 Pydantic 模型对齐 |
| 样式 | **Tailwind CSS** | 3.x | 原子化 CSS，快速实现设计系统 |
| 组件库 | **shadcn/ui** | latest | Tailwind 原生，可定制，无样式锁定 |
| Markdown | **react-markdown + remark-gfm** | — | 渲染 answer 字段的 GFM Markdown |
| HTTP | **Axios** | 1.x | 拦截器 + 请求取消 |
| 状态管理 | **Zustand** | 4.x | 轻量，无 Redux 样板代码 |
| 路由 | **React Router** | 6.x | 声明式路由 |
| 图标 | **Lucide React** | — | shadcn/ui 配套图标集 |

### 2.2 项目初始化命令

```bash
cd /Users/tanglin/VibeCoding/GraphRagAgent
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npx shadcn@latest init
npm install axios zustand react-router-dom react-markdown remark-gfm lucide-react
```

---

## 3. 整体 UI 布局

### 3.1 宏观布局结构

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Header Bar（64px）                            │
│  [Logo] GraphRAG Agent    [知识库] [问答]              [●系统状态]   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│                         Main Content Area                            │
│                      (切换：知识库管理 / 智能问答)                    │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

**知识库管理视图（双栏）**：
```
┌──────────────────┬───────────────────────────────────────────────────┐
│  文档列表侧边栏   │              文档上传 + 详情区                      │
│   (280px)        │                                                   │
│                  │  ┌─────────────────────────────────────────────┐  │
│ [搜索文档...]    │  │          拖拽上传区 / 文件选择器                │  │
│ ─────────────── │  └─────────────────────────────────────────────┘  │
│ ● 技术报告.pdf   │                                                   │
│   READY         │  ┌─────────────────────────────────────────────┐  │
│ ○ 销售数据.xlsx  │  │           当前选中文档详情卡片                  │  │
│   INDEXING 73%  │  │  状态 / chunks / 实体数 / 两路索引进度          │  │
│ ⊗ 图1.jpg       │  └─────────────────────────────────────────────┘  │
│   PARSE_FAILED  │                                                   │
└──────────────────┴───────────────────────────────────────────────────┘
```

**智能问答视图（三栏）**：
```
┌──────────────────┬────────────────────────────┬───────────────────────┐
│   文档选择器     │      对话主区域               │    来源溯源面板        │
│   (220px)        │                             │    (340px，可折叠)     │
│                  │  ┌──────────────────────┐  │                       │
│ □ 全部文档       │  │  用户问题气泡         │  │  ── KG 实体 ─────────  │
│ ☑ 技术报告.pdf  │  │  AI 回答（Markdown）  │  │  [LangChain] product   │
│ ☑ 产品文档.docx │  │  ─────────────────── │  │   属性展开...          │
│                  │  │  用户问题气泡         │  │                       │
│                  │  │  AI 回答             │  │  ── 原文段落 ─────────  │
│                  │  └──────────────────────┘  │  [1] 章节：组件...     │
│                  │                             │   第0页，text chunk    │
│                  │  ┌──────────────────────┐  │                       │
│                  │  │ [输入问题...] [发送] │  │  ── 元信息 ─────────── │
│                  │  └──────────────────────┘  │  路由: hybrid_query    │
│                  │                             │  耗时: 3.2s            │
└──────────────────┴────────────────────────────┴───────────────────────┘
```

### 3.2 Header 固定布局

```
┌──────────────────────────────────────────────────────────────────────┐
│ ◈ GraphRAG Agent    │  知识库   问答  │         ● 系统正常  3/5 就绪  │
└──────────────────────────────────────────────────────────────────────┘
```

- 左：Logo（品牌色图标 + 产品名）
- 中：主导航 Tab（知识库 / 问答），当前页高亮
- 右：系统状态快捷入口（● 绿色=正常 / ● 黄色=部分异常）+ READY 文档数/总数

---

## 4. 设计语言规范

### 4.1 色彩系统

**主题模式**：默认暗色模式（Dark Mode），可切换亮色。

```
── 暗色主题 Dark ──────────────────────────────
Background Base:     #0F1117   (深海军蓝黑)
Background Surface:  #1A1D27   (卡片/面板背景)
Background Elevated: #21253A   (悬浮/Hover 背景)
Border:              #2D3148   (边框/分割线)

Text Primary:        #F0F2FF   (主文本)
Text Secondary:      #8B90AC   (次要文本/标签)
Text Muted:          #4A5070   (占位符/禁用)

Accent Purple:       #7C6FE0   (主品牌色，按钮/选中)
Accent Purple Light: #A598F0   (悬浮态)
Accent Blue:         #4F9CF9   (链接/次强调)

Success:             #34D399   (READY 状态/成功)
Warning:             #FBBF24   (INDEXING/进行中)
Error:               #F87171   (FAILED 状态/错误)
Info:                #60A5FA   (PARSING/信息)

── 亮色主题 Light ─────────────────────────────
Background Base:     #F8F9FC
Background Surface:  #FFFFFF
Background Elevated: #EEF0F8
Border:              #E2E5F0
Text Primary:        #1A1D2E
Text Secondary:      #5A6080
Accent Purple:       #6B5FD0
```

### 4.2 状态色彩映射（文档状态徽章）

| 状态 | 颜色 | 图标 | 文字 |
|------|------|------|------|
| `UPLOADED` | Info Blue | `↑` | 已上传 |
| `PARSING` | Info Blue + 动画 | `⟳` | 解析中... |
| `PARSED` | Warning Yellow | `⟳` | 建立索引中 |
| `INDEXING` | Warning Yellow + 动画 | `⟳` | 索引构建中 |
| `READY` | Success Green | `●` | 就绪 |
| `PARSE_FAILED` | Error Red | `⊗` | 解析失败 |
| `INDEX_FAILED` | Error Red | `⊗` | 索引失败 |

### 4.3 路由类型标签样式

| 路由值 | 标签文字 | 标签颜色 |
|--------|---------|---------|
| `entity_query` | 实体查询 | Accent Purple |
| `semantic_query` | 语义查询 | Accent Blue |
| `hybrid_query` | 混合检索 | 渐变 Purple→Blue |
| `direct_answer` | 直接回答 | Text Secondary |

### 4.4 字体规范

```css
/* 主字体：系统无衬线 */
font-family: -apple-system, 'Inter', 'PingFang SC', sans-serif;

/* 标题 */
h1: font-size: 24px; font-weight: 700; letter-spacing: -0.02em;
h2: font-size: 18px; font-weight: 600;
h3: font-size: 15px; font-weight: 600;

/* 正文 */
body: font-size: 14px; line-height: 1.6; font-weight: 400;
small: font-size: 12px; font-weight: 400;

/* Markdown 答案渲染 */
prose: font-size: 14px; line-height: 1.8; max-width: 680px;
code: font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 13px;
```

### 4.5 间距与圆角

```css
/* 间距尺度（基于 4px 栅格） */
spacing-1: 4px   spacing-2: 8px   spacing-3: 12px  spacing-4: 16px
spacing-6: 24px  spacing-8: 32px  spacing-12: 48px

/* 圆角 */
radius-sm: 4px   (badge, tag)
radius-md: 8px   (button, input)
radius-lg: 12px  (card, panel)
radius-xl: 16px  (modal, drawer)
radius-full: 9999px (avatar, pill)
```

### 4.6 阴影

```css
shadow-sm:  0 1px 3px rgba(0,0,0,0.3)      /* card */
shadow-md:  0 4px 16px rgba(0,0,0,0.4)     /* dropdown, tooltip */
shadow-lg:  0 8px 32px rgba(0,0,0,0.5)     /* modal */
shadow-glow: 0 0 20px rgba(124,111,224,0.3) /* 品牌色发光，用于 READY 状态 */
```

---

## 5. 页面清单与路由

| 路由 | 页面名称 | 描述 | 对应后端 API |
|------|---------|------|------------|
| `/` | 重定向 → `/knowledge` | — | — |
| `/knowledge` | 知识库管理 | 上传文档 + 处理状态监控 | `GET /documents`, `POST /documents/upload`, `DELETE /documents/{id}` |
| `/chat` | 智能问答 | 多轮问答 + 来源溯源 | `POST /qa/query`, `GET /documents?status=READY` |
| `/system` | 系统状态 | 服务健康 + 组件状态 | `GET /health` |

**导航守卫**：
- 访问 `/chat` 时检查是否有 READY 文档，若无则提示跳转至 `/knowledge` 上传

---

## 6. 页面详细设计

### 6.1 知识库管理页（`/knowledge`）

#### 6.1.1 页面整体结构

```
Header（固定）
├── Sidebar（280px，固定左侧）
│   ├── 搜索框
│   ├── 文档列表（虚拟滚动，每项约 72px）
│   │   └── 文档条目：图标 + 文件名 + 状态徽章 + 更新时间
│   └── 底部：总计 N 个文档，M 个就绪
└── Main Area（flex-1）
    ├── 上传区块（顶部，固定高度 200px）
    └── 文档详情区块（选中文档时展示）
```

#### 6.1.2 文档上传区块

**状态 A：空闲可上传**
```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│           ↑  拖拽文件到此处，或  [点击选择文件]                  │
│                                                                 │
│    支持：PDF · Word · PPT · Excel · 图片 · HTML                  │
│    大小：最大 200MB（Excel 最大 10MB）                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
  □ 启用 OCR（扫描件建议开启）    [上传并解析]
```

**状态 B：拖拽悬停**
```
┌─────────────────────────────────────────────────────────────────┐
│  （品牌色边框 + 背景微亮）                                        │
│              ↓  释放以上传文件                                   │
└─────────────────────────────────────────────────────────────────┘
```

**状态 C：上传中（已选文件，进度条）**
```
┌─────────────────────────────────────────────────────────────────┐
│  📄 技术报告-Q1.pdf   12.4 MB                        [×]         │
│  ████████████████████████░░░░░░░░░░░░░░   67%                   │
│  正在提交 MinerU 解析任务...                                     │
└─────────────────────────────────────────────────────────────────┘
```

#### 6.1.3 文档列表条目设计

```
┌────────────────────────────────────────────────────────────────┐
│ [PDF]  技术报告-Q1-2026.pdf                    [● 就绪]        │
│        Chunks: 15  ·  实体: 130  ·  2026-04-13 10:12          │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│ [XLS]  销售数据统计.xlsx                    [⟳ 索引构建中]      │
│        向量索引 ████████░░ 80%  ·  知识图谱 ████████████ 100%  │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│ [JPG]  产品架构图.jpg                         [⊗ 解析失败]     │
│        解析超时（>600s）                        [重新上传]      │
└────────────────────────────────────────────────────────────────┘
```

#### 6.1.4 文档详情卡片（选中后展示在 Main Area）

```
┌─────────────────────────────────────────────────────────────────┐
│  📄 技术报告-Q1-2026.pdf                             [删除文档]  │
│  ─────────────────────────────────────────────────────────────  │
│                                                                 │
│  状态                ● 就绪，可以提问                            │
│  文件类型            PDF（Precision API 精准解析）               │
│  上传时间            2026-04-13 10:00:00                        │
│  完成时间            2026-04-13 10:12:45（耗时 12m 45s）         │
│                                                                 │
│  ── 向量索引 ─────────────────────────────────────────────────  │
│  状态      ✓ 完成                                               │
│  Chunks    15 个（text: 13，table: 2）                          │
│  平均长度  500 字符/chunk                                       │
│                                                                 │
│  ── 知识图谱 ─────────────────────────────────────────────────  │
│  状态      ✓ 完成                                               │
│  实体数    130 个（match_exact）                                 │
│                                                                 │
│                                    [开始提问 →]                 │
└─────────────────────────────────────────────────────────────────┘
```

---

### 6.2 智能问答页（`/chat`）

#### 6.2.1 页面整体结构

```
Header（固定）
├── Document Selector（220px，左侧固定面板）
│   ├── "检索范围" 标题
│   ├── [全部文档] 选项
│   └── READY 文档列表（复选框）
├── Chat Area（flex-1，中间滚动区域）
│   ├── 历史消息列表
│   └── Input Bar（底部固定）
└── Source Panel（340px，右侧，可折叠）
    ├── KG 实体卡片列表
    ├── 原文段落列表
    └── 元信息面板
```

#### 6.2.2 文档选择器

```
┌────────────────────────────────────────┐
│  检索范围                              │
│  ────────────────────────────────────  │
│  ☑ 全部文档（3 个就绪）               │
│  ────────────────────────────────────  │
│  ☑ 📄 技术报告-Q1.pdf                 │
│       15 chunks · 130 实体            │
│  ☑ 📝 产品设计文档.docx               │
│       22 chunks · 87 实体             │
│  ☑ 📊 销售数据.xlsx                   │
│       8 chunks · 0 实体               │
│                                        │
│  ⚫ 数组.docx（INDEXING...）           │
│     （灰色禁用，不可选）              │
└────────────────────────────────────────┘
```

#### 6.2.3 对话消息设计

**用户消息气泡**（右对齐）：
```
                    ┌──────────────────────────────────┐
                    │  LangChain 的核心组件有哪些？        │
                    │  它与 LlamaIndex 有什么区别？        │
                    └──────────────────────────────────┘
                                            10:15:32
```

**AI 回答卡片**（左对齐，全宽）：
```
┌────────────────────────────────────────────────────────────────┐
│ ◈  GraphRAG Agent                                              │
│ ─────────────────────────────────────────────────────────────  │
│                                                                │
│ ## LangChain 核心组件                                           │
│                                                                │
│ LangChain 的核心组件主要包括**链（Chain）**和**代理（Agent）**  │
│ ...（完整 Markdown 渲染）                                       │
│                                                                │
│ | 维度 | LangChain | LlamaIndex |                              │
│ |------|-----------|------------|                              │
│ | 定位 | 通用框架   | RAG 专注    |                              │
│                                                                │
│ ─────────────────────────────────────────────────────────────  │
│ [混合检索] [改写 0次] [充分 ✓] [耗时 3.2s]    [查看来源 5 →]   │
└────────────────────────────────────────────────────────────────┘
```

底部元信息 Tag 行：
- 路由策略 Tag（颜色区分，见第4.3节）
- 改写次数 Tag（0次时显示灰色，>0时显示黄色警示）
- 检索充分性 Tag
- 耗时
- "查看来源 N →" 按钮（点击展开/聚焦右侧 Source Panel）

**加载中状态**（AI 回答生成中）：
```
┌────────────────────────────────────────────────────────────────┐
│ ◈  GraphRAG Agent                                              │
│ ─────────────────────────────────────────────────────────────  │
│  ● 路由分析中...                                 [hybrid_query] │
│  ● 检索知识图谱（5 个实体）                               ✓     │
│  ● 检索文档段落（9 个 chunks）                            ✓     │
│  ● 评估检索充分性...                                      ✓     │
│  ● 生成答案中   ▌                                              │
└────────────────────────────────────────────────────────────────┘
```

注：通过轮询或 SSE 实现步骤级进度展示（MVP 可简化为 loading spinner）。

#### 6.2.4 输入框区域

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  输入你的问题...                                                 │
│                                                                 │
│                               [Shift+Enter 换行]  [↑ 发送]     │
└─────────────────────────────────────────────────────────────────┘
  ℹ 检索范围：技术报告.pdf, 产品文档.docx（共 2 份文档）
```

- 支持多行输入（Shift+Enter 换行，Enter 发送）
- 底部显示当前检索范围概要
- 问答进行中：输入框禁用 + 显示取消按钮

#### 6.2.5 来源溯源面板（右侧）

**面板头部**：
```
┌──────────────────────────────────────────┐
│  来源溯源              [← 折叠]          │
│  最近回答：hybrid_query · 3.2s · 充分 ✓  │
└──────────────────────────────────────────┘
```

**KG 实体卡片**：
```
── KG 实体（5 个）──────────────────────────

┌────────────────────────────────────────────┐
│ LangChain                    [product]      │
│ 来源：0.LangChain技术生态介绍               │
│                                            │
│ type         大模型开发框架                 │
│ open_sourced 2022年10月开源                 │
│ core_compo.. 链, 代理                       │
│                                            │
│ [展开原文片段 ▼]                            │
│ LangChain可以称之为自2022年底大模型...       │
└────────────────────────────────────────────┘

┌────────────────────────────────────────────┐
│ LlamaIndex                   [product]      │
│ focus: 文档处理, RAG                        │
│ [展开 ▼]                                    │
└────────────────────────────────────────────┘
```

**原文段落卡片**：
```
── 原文段落（9 个）─────────────────────────

┌────────────────────────────────────────────┐
│ [1] 4. 组件（Component）          page 0   │
│     text  ·  0.LangChain技术生态介绍        │
│     实体：LCEL, LangChain                  │
│ ──────────────────────────────────────     │
│ 在LangChain中，Components是一系列可         │
│ 组合的构建块，让开发者能够高效地...          │
└────────────────────────────────────────────┘

┌────────────────────────────────────────────┐
│ [2] 1. LlamaIndex                page 0   │
│     text  ·  0.LangChain技术生态介绍        │
│ [展开 ▼]                                    │
└────────────────────────────────────────────┘
```

**元信息面板**（来源面板底部）：
```
── 本次问答元信息 ──────────────────────────

路由策略      hybrid_query（KG + 段落并行）
原始问题      LangChain 的核心组件...
最终问题      同上（未改写）
改写次数      0 次
检索充分      是
KG 实体数     5 个
段落 Chunks   9 个
答案生成耗时  3.2 秒
```

---

### 6.3 系统状态页（`/system`）

```
┌──────────────────────────────────────────────────────────────────┐
│  系统状态                                    最后更新：10s 前    │
│                                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │ ● 数据库 │ │ ● 向量库 │ │ ● KG文件 │ │ ●MinerU  │           │
│  │   正常   │ │   正常   │ │   正常   │ │   正常   │           │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘           │
│                                                                  │
│  ── 文档统计 ─────────────────────────────────────────────────  │
│  总计 5 个文档                                                   │
│  ██████████████ 3 个就绪 (60%)                                   │
│  ████░░░░░░░░░ 1 个处理中 (20%)                                  │
│  ██░░░░░░░░░░░ 1 个失败 (20%)                                    │
│                                                                  │
│  ── 最近活动 ─────────────────────────────────────────────────  │
│  10:12  技术报告.pdf  → READY（耗时 12m45s）                    │
│  10:30  销售数据.xlsx → INDEXING（进行中）                       │
│  09:45  图1.jpg      → PARSE_FAILED（超时）                     │
└──────────────────────────────────────────────────────────────────┘
```

---

## 7. 核心交互逻辑

### 7.1 文件上传交互流程

```
用户拖入/选择文件
        │
        ▼
前端校验（格式 + 大小）
  ├── 不合法 → Toast 错误提示（"不支持 .mp4 格式"）
  └── 合法 → 显示文件预览条 + [上传并解析] 按钮激活
        │
        ▼ 点击上传
POST /api/v1/documents/upload
        │
        ▼ 202 响应，获取 doc_id
文档条目出现在左侧列表（status=PARSING）
启动轮询 → setInterval(pollStatus, 5000)
        │
        ▼ 轮询 GET /documents/{doc_id}/status
状态更新：
  PARSING   → 蓝色动画 spinner，文字"文档解析中..."
  PARSED    → 进度条跳至 55%
  INDEXING  → 进度条动画（向量进度 + KG 进度分别显示）
  READY     → 绿色完成，停止轮询，Toast "文档已就绪"
  *FAILED   → 红色错误，停止轮询，显示错误原因 + [重新上传]
```

### 7.2 进度计算规则

| 阶段 | 进度百分比计算 |
|------|--------------|
| `UPLOADED` | 5% |
| `PARSING` | 5% + 时间线性插值（最多 50%，600s满） |
| `PARSED` | 55% |
| `INDEXING` (两路独立) | `55% + vector_progress * 0.225 + kg_progress * 0.225` |
| `READY` | 100% |

`vector_progress` 和 `kg_progress` 取值：
- `pending` = 0%, `building` = 50%（无精确进度时估算）, `done` = 100%

### 7.3 问答交互流程

```
用户在输入框输入问题
        │
        ▼ 按 Enter 或点击发送
前端校验：
  ├── 问题为空 → 输入框 shake 动画
  ├── 无 READY 文档 → Toast "请先上传文档"
  └── 合法 → 发送请求
        │
        ▼
POST /api/v1/qa/query（含 doc_ids）
输入框禁用 + 显示停止按钮
Chat Area 追加 AI 回答卡片（loading 状态）
        │
        ▼ 后端响应（同步，最多 60s）
解析 QAResponse：
  - answer → react-markdown 渲染
  - meta   → 路由/改写/耗时标签
  - sources.kg_entities → KG 实体卡片（右侧面板）
  - sources.passages   → 段落来源卡片（右侧面板）
        │
        ▼
右侧 Source Panel 自动打开（若为折叠状态）
滚动 Chat Area 到最新消息底部
输入框恢复可用
```

### 7.4 来源面板交互

- 问答完成时，右侧面板若折叠则**自动展开**（仅首次，之后由用户控制）
- 点击 AI 回答卡片底部的"查看来源 N →"按钮：高亮右侧面板并滚动到顶部
- KG 实体卡片：点击展开原文片段（默认折叠）
- 段落卡片：点击展开全文（超过 3 行时折叠，显示"展开全文"）
- 实体类型 Badge 点击：在左侧文档选择器中筛选包含该实体类型的文档（预留功能）

### 7.5 空状态设计

**首次进入知识库**（无文档）：
```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│                   ◈  开始构建你的知识库                          │
│                                                                 │
│         上传 PDF、Word、Excel 等格式的文档                       │
│         系统将自动解析并构建 AI 可检索的知识库                   │
│                                                                 │
│                  [上传第一个文档 ↑]                             │
│                                                                 │
│    支持：PDF · Word · PPT · Excel · 图片 · HTML                 │
└─────────────────────────────────────────────────────────────────┘
```

**首次进入问答**（无 READY 文档）：
```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│              还没有可以检索的文档                               │
│                                                                 │
│       请先在知识库页面上传并等待文档处理完成                     │
│                                                                 │
│                [去上传文档 →]                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 7.6 错误处理交互

| 错误场景 | 前端处理 |
|---------|---------|
| 网络断开 | Toast "网络连接异常，请检查网络" + 自动重试 3 次 |
| 上传格式不支持 | 输入框摇动动画 + 红色提示文字 |
| 文件过大 | 即时校验（不发请求）+ Toast 提示 |
| Q&A 超时（504） | "问答超时，请重试" + [重新发送] 按钮 |
| PARSE_FAILED | 列表条目红色 + 错误原因 tooltip + [重新上传] 按钮 |
| INDEX_FAILED | 同上 + [重试建索引] 按钮（预留） |

---

## 8. 组件规范

### 8.1 核心组件清单

```
components/
├── layout/
│   ├── Header.tsx              # 顶部导航栏
│   ├── PageLayout.tsx          # 通用页面容器
│   └── SplitLayout.tsx         # 左右分栏布局（知识库/问答均用）
│
├── knowledge/
│   ├── UploadZone.tsx          # 拖拽上传区
│   ├── UploadProgress.tsx      # 上传进度条
│   ├── DocumentList.tsx        # 文档列表（含搜索）
│   ├── DocumentListItem.tsx    # 单条文档（状态徽章+进度）
│   ├── DocumentDetail.tsx      # 文档详情卡片
│   └── StatusBadge.tsx         # 状态徽章组件
│
├── chat/
│   ├── ChatArea.tsx            # 滚动消息区域
│   ├── UserMessage.tsx         # 用户气泡
│   ├── AIMessage.tsx           # AI 回答卡片（含 Markdown）
│   ├── AIMessageLoading.tsx    # AI 回答加载中骨架
│   ├── ChatInput.tsx           # 输入框 + 发送按钮
│   ├── MetaTagRow.tsx          # 路由/耗时标签行
│   └── DocSelector.tsx         # 文档检索范围选择器
│
├── sources/
│   ├── SourcePanel.tsx         # 来源溯源面板容器（可折叠）
│   ├── KGEntityCard.tsx        # KG 实体卡片
│   ├── PassageCard.tsx         # 原文段落卡片
│   └── QAMetaPanel.tsx         # 问答元信息展示
│
├── system/
│   ├── HealthCard.tsx          # 组件健康状态卡
│   ├── DocumentStats.tsx       # 文档统计可视化
│   └── ActivityLog.tsx         # 最近活动日志
│
└── ui/                         # shadcn/ui 基础组件（Button/Card/Badge/Toast...）
```

### 8.2 StatusBadge 组件 Props

```typescript
interface StatusBadgeProps {
  status: 'UPLOADED' | 'PARSING' | 'PARSED' | 'INDEXING' |
          'READY' | 'PARSE_FAILED' | 'INDEX_FAILED';
  animated?: boolean;  // 进行中状态是否显示动画（默认 true）
  size?: 'sm' | 'md'; // 默认 md
}
```

### 8.3 AIMessage 组件 Props

```typescript
interface AIMessageProps {
  answer: string;           // Markdown 字符串
  meta: {
    route: string;
    rewrite_count: number;
    question_used: string;
    original_question: string;
    sufficient: boolean;
    latency_ms: number;
  };
  sources: {
    kg_entities: KGEntity[];
    passages: PassageSource[];
  };
  onViewSources: () => void; // 点击"查看来源"的回调
}
```

### 8.4 KGEntityCard 组件

```typescript
interface KGEntityCardProps {
  entity: {
    name: string;
    type: string;               // product | concept | technology | ...
    attributes: Record<string, string>;
    context_snippet: string;
    document_id: string;
  };
  defaultExpanded?: boolean;   // 默认展开原文片段
}
```

**渲染规则**：
- `attributes` 展示最多 4 个 key-value（超出折叠）
- `context_snippet` 默认折叠，点击"展开原文片段"展开
- `type` 对应不同颜色的小徽章

---

## 9. 响应式设计规范

### 9.1 断点定义

| 断点 | 最小宽度 | 目标设备 |
|------|---------|---------|
| `sm` | 640px | 大屏手机横屏 |
| `md` | 768px | 平板竖屏 |
| `lg` | 1024px | 平板横屏 / 小笔记本 |
| `xl` | 1280px | 桌面标准 |
| `2xl` | 1536px | 大屏桌面 |

### 9.2 知识库页响应式策略

| 屏幕 | 布局调整 |
|------|---------|
| `< md`（移动端） | 侧边栏隐藏，顶部显示文档 Tab 切换；详情卡片全屏展示 |
| `md ~ lg`（平板） | 侧边栏收缩至 200px |
| `>= lg`（桌面） | 标准双栏布局（280px + flex-1） |

### 9.3 问答页响应式策略

| 屏幕 | 布局调整 |
|------|---------|
| `< md`（移动端） | 文档选择器折叠为顶部下拉；Source Panel 变为底部抽屉 |
| `md ~ lg`（平板） | 文档选择器 160px；Source Panel 默认收起（点击展开） |
| `>= xl`（桌面） | 标准三栏（220px + flex-1 + 340px） |

---

## 10. 前端目录结构

```
frontend/
├── public/
│   └── favicon.svg
├── src/
│   ├── main.tsx                 # 应用入口
│   ├── App.tsx                  # 路由配置
│   ├── index.css                # Tailwind 基础样式
│   │
│   ├── types/                   # TypeScript 类型定义（对齐后端 Pydantic）
│   │   ├── document.ts          # DocumentStatus, DocumentListItem
│   │   └── qa.ts                # QAResponse, KGEntity, PassageSource
│   │
│   ├── api/                     # API 请求层
│   │   ├── client.ts            # Axios 实例 + 拦截器
│   │   ├── documents.ts         # 文档相关 API
│   │   ├── qa.ts                # 问答相关 API
│   │   └── health.ts            # 健康检查 API
│   │
│   ├── store/                   # Zustand 状态
│   │   ├── documentStore.ts     # 文档列表 + 轮询管理
│   │   ├── chatStore.ts         # 对话历史 + 来源数据
│   │   └── uiStore.ts           # UI 状态（侧边栏折叠/主题）
│   │
│   ├── hooks/                   # 自定义 Hooks
│   │   ├── useDocumentPolling.ts # 文档状态轮询
│   │   ├── useFileUpload.ts      # 上传逻辑
│   │   └── useChat.ts            # 问答逻辑
│   │
│   ├── pages/
│   │   ├── KnowledgePage.tsx    # 知识库管理页
│   │   ├── ChatPage.tsx         # 智能问答页
│   │   └── SystemPage.tsx       # 系统状态页
│   │
│   ├── components/              # （见第8.1节组件清单）
│   │
│   └── utils/
│       ├── formatters.ts        # 时间/文件大小/状态文字格式化
│       ├── statusHelpers.ts     # 状态 → 颜色/图标/进度映射
│       └── constants.ts         # SUPPORTED_FORMATS, MAX_UPLOAD_SIZE
│
├── tailwind.config.ts           # Tailwind 配置（含自定义颜色变量）
├── vite.config.ts               # Vite 配置（API 代理）
├── tsconfig.json
└── package.json
```

---

## 11. API 对接层规范

### 11.1 Axios 实例配置

```typescript
// src/api/client.ts
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1',
  timeout: 65000,          // Q&A 最长 60s + 5s 缓冲
  headers: { 'Content-Type': 'application/json' },
});

// 请求拦截：注入 X-Request-ID
apiClient.interceptors.request.use((config) => {
  config.headers['X-Request-ID'] = crypto.randomUUID();
  return config;
});

// 响应拦截：统一错误处理
apiClient.interceptors.response.use(
  (res) => res.data,
  (error) => {
    const code = error.response?.data?.error;
    const message = error.response?.data?.message || '服务异常，请稍后重试';
    // 触发全局 Toast 通知
    toast.error(message);
    return Promise.reject({ code, message });
  }
);
```

### 11.2 文档 API 封装

```typescript
// src/api/documents.ts
export const documentsApi = {
  upload: (file: File, enableOcr = true) => {
    const form = new FormData();
    form.append('file', file);
    form.append('enable_ocr', String(enableOcr));
    return apiClient.post<UploadResponse>('/documents/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 30000,
    });
  },
  getStatus: (docId: string) =>
    apiClient.get<DocumentStatus>(`/documents/${docId}/status`),

  list: (params?: { status?: string; limit?: number; offset?: number }) =>
    apiClient.get<DocumentListResponse>('/documents', { params }),

  delete: (docId: string) =>
    apiClient.delete<{ message: string }>(`/documents/${docId}`),
};
```

### 11.3 Q&A API 封装

```typescript
// src/api/qa.ts
export const qaApi = {
  query: (question: string, docIds?: string[], sessionId?: string) =>
    apiClient.post<QAResponse>('/qa/query', {
      question,
      doc_ids: docIds ?? null,
      session_id: sessionId ?? null,
    }, { timeout: 65000 }),
};
```

### 11.4 环境变量

```bash
# frontend/.env.development
VITE_API_BASE_URL=http://localhost:8000/api/v1

# frontend/.env.production
VITE_API_BASE_URL=https://your-backend.com/api/v1
```

```typescript
// vite.config.ts — 开发环境 API 代理
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
    }
  }
}
```

---

## 12. 状态管理规范

### 12.1 documentStore

```typescript
interface DocumentStore {
  // State
  documents: DocumentListItem[];
  selectedDocId: string | null;
  pollingIds: Set<string>;           // 正在轮询的 doc_id 集合

  // Actions
  fetchDocuments: () => Promise<void>;
  uploadDocument: (file: File, enableOcr: boolean) => Promise<string>; // returns doc_id
  startPolling: (docId: string) => void;
  stopPolling: (docId: string) => void;
  updateDocumentStatus: (docId: string, status: DocumentStatus) => void;
  deleteDocument: (docId: string) => Promise<void>;
  selectDocument: (docId: string | null) => void;

  // Computed
  readyDocuments: () => DocumentListItem[];  // status=READY 的文档
}
```

**轮询策略**：
- 每 5 秒调用 `GET /documents/{id}/status`
- 状态变为 READY / PARSE_FAILED / INDEX_FAILED 时停止轮询
- 页面切换时不停止轮询（后台继续）
- 页面关闭时清理所有定时器

### 12.2 chatStore

```typescript
interface ChatStore {
  // State
  messages: ChatMessage[];           // 对话历史
  currentSources: QASources | null;  // 最新一条回答的来源
  currentMeta: QAMeta | null;
  isLoading: boolean;
  selectedDocIds: string[];          // 检索范围选择
  sourcePanelOpen: boolean;

  // Actions
  sendMessage: (question: string) => Promise<void>;
  clearHistory: () => void;
  setSelectedDocIds: (ids: string[]) => void;
  toggleSourcePanel: () => void;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;                   // user: 问题文本；assistant: Markdown 答案
  meta?: QAMeta;                     // 仅 assistant 有
  sources?: QASources;               // 仅 assistant 有
  timestamp: Date;
  status: 'pending' | 'done' | 'error';
}
```

### 12.3 uiStore

```typescript
interface UIStore {
  theme: 'dark' | 'light';
  sidebarCollapsed: boolean;         // 移动端侧边栏收起状态
  toggleTheme: () => void;
  toggleSidebar: () => void;
}
```

---

## 附录 A：关键数据字段可视化总结

后端返回数据与前端 UI 元素的对应关系：

```
QAResponse
├── answer ──────────────────────→ AI 回答卡片 Markdown 渲染区
├── meta
│   ├── route ───────────────────→ 路由策略 Tag（颜色区分）
│   ├── rewrite_count ───────────→ 改写次数 Tag
│   ├── question_used ───────────→ 来源面板"最终问题"字段
│   ├── sufficient ──────────────→ 充分性 Tag（✓/✗）
│   └── latency_ms ──────────────→ 耗时文字（"3.2s"）
└── sources
    ├── kg_entities[]
    │   ├── name ────────────────→ KG 实体卡片标题
    │   ├── type ────────────────→ 类型徽章
    │   ├── attributes ──────────→ 属性键值表格
    │   ├── context_snippet ─────→ 可展开原文片段
    │   └── document_id ─────────→ 来源标签
    └── passages[]
        ├── content ─────────────→ 段落文本（超3行折叠）
        ├── section ─────────────→ 章节标题
        ├── page ────────────────→ 页码显示
        ├── document_id ─────────→ 文档来源
        ├── chunk_type ──────────→ text/table 图标区分
        ├── entities ────────────→ 实体标签列表
        └── char_range ──────────→ 字符位置（[start, end]，预留高亮用）

DocumentStatus
├── status ──────────────────────→ StatusBadge 状态徽章
├── vector_status ───────────────→ 向量索引进度子状态
├── kg_status ───────────────────→ KG 索引进度子状态
├── chunk_count ─────────────────→ 文档详情卡"Chunks N个"
├── entity_count ────────────────→ 文档详情卡"实体 N个"
├── error_msg ───────────────────→ 失败状态 tooltip 错误原因
└── ready_for_qa ────────────────→ 控制"开始提问"按钮可用性
```
