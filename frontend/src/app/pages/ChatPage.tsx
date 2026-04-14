import React, { useEffect, useRef, useState } from "react";
import { useDocumentStore, useChatStore, Message, MessageSources } from "../store";
import { useNavigate } from "react-router";
import { Send, FileText, Check, ChevronRight, X, Loader2, Info } from "lucide-react";
import { cn, RouteTag, toast } from "../components/ui";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const MOCK_SOURCES: MessageSources = {
  kg_entities: [
    {
      name: "LangChain",
      type: "product",
      attributes: {
        "type": "大模型开发框架",
        "open_sourced": "2022年10月开源",
        "core_components": "链, 代理"
      },
      context_snippet: "LangChain可以称之为自2022年底大模型爆发以来，最受开发者欢迎的大模型应用开发框架，它提供了一套完整的工具链...",
      document_id: "doc-1"
    },
    {
      name: "LCEL",
      type: "technology",
      attributes: {
        "description": "LangChain Expression Language",
        "feature": "声明式组合链"
      },
      context_snippet: "LCEL是一种声明式语言，用于轻松组合不同的组件。它是构建LangChain应用的核心方式...",
      document_id: "doc-1"
    }
  ],
  passages: [
    {
      id: "p1",
      content: "在LangChain中，Components是一系列可组合的构建块，让开发者能够高效地集成大语言模型。主要包括 Models, Prompts, Indexes 等核心组件。",
      section: "4. 组件（Component）",
      page: 0,
      chunk_type: "text",
      entities: ["LCEL", "LangChain"],
      document_id: "doc-1"
    },
    {
      id: "p2",
      content: "LlamaIndex 与 LangChain 的主要区别在于数据接入和检索方式。LlamaIndex 更侧重于私有数据的摄取和结构化...",
      section: "对比分析",
      page: 2,
      chunk_type: "text",
      entities: ["LlamaIndex", "LangChain"],
      document_id: "doc-1"
    }
  ]
};

export default function ChatPage() {
  const navigate = useNavigate();
  const { documents, selectedDocIds, toggleDocSelection, toggleAllSelection } = useDocumentStore();
  const { messages, addMessage, updateMessage, currentSources, setCurrentSources, isSourcePanelOpen, toggleSourcePanel } = useChatStore();
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [shake, setShake] = useState(false);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const readyDocs = documents.filter(d => d.status === "READY");
  const hasReadyDocs = readyDocs.length > 0;

  useEffect(() => {
    if (!hasReadyDocs) {
      toast("请先上传并等待文档处理完成");
      navigate("/knowledge");
    }
  }, [hasReadyDocs, navigate]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = () => {
    if (!input.trim()) {
      setShake(true);
      setTimeout(() => setShake(false), 500);
      return;
    }
    
    if (selectedDocIds.length === 0) {
      toast.error("请在左侧选择至少一个检索文档");
      return;
    }

    const userMsg: Message = {
      id: `msg-u-${Date.now()}`,
      role: "user",
      content: input,
      timestamp: new Date().toISOString()
    };
    
    addMessage(userMsg);
    setInput("");
    setIsSending(true);

    const aiMsgId = `msg-a-${Date.now()}`;
    const aiMsg: Message = {
      id: aiMsgId,
      role: "ai",
      content: "思考中...",
      timestamp: new Date().toISOString(),
      isLoading: true
    };
    
    addMessage(aiMsg);

    // Mock API call
    setTimeout(() => {
      updateMessage(aiMsgId, {
        content: "LangChain 是一个大模型应用开发框架，它的核心组件包括：\n\n1. **Models（模型）**：与各种大语言模型交互的接口。\n2. **Prompts（提示词）**：管理和优化输入给模型的提示词。\n3. **Indexes（索引）**：用于文档的加载、分块和检索。\n4. **Chains（链）**：将多个组件组合成一个可执行的流程。\n5. **Agents（代理）**：让模型自主决定执行哪些动作。\n\n与 LlamaIndex 的主要区别在于，LlamaIndex 更侧重于私有数据的摄取和结构化检索，而 LangChain 提供了更通用的应用编排能力。",
        isLoading: false,
        meta: {
          route: "hybrid_query",
          rewrite_count: 0,
          sufficient: true,
          latency_ms: 3200
        },
        sources: MOCK_SOURCES
      });
      setCurrentSources(MOCK_SOURCES);
      if (!isSourcePanelOpen) toggleSourcePanel(true);
      setIsSending(false);
      setTimeout(() => inputRef.current?.focus(), 100);
    }, 3000);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!isSending) handleSend();
    }
  };

  return (
    <div className="flex h-full size-full bg-[#0F1117] overflow-hidden">
      {/* Document Selector (Left) */}
      <div className="w-[220px] flex-none border-r border-[#2D3148] flex flex-col bg-[#1A1D27]">
        <div className="p-4 border-b border-[#2D3148]">
          <h3 className="text-sm font-semibold text-[#F0F2FF] mb-3">检索范围</h3>
          <label className="flex items-center gap-2 cursor-pointer group">
            <input 
              type="checkbox"
              checked={selectedDocIds.length === readyDocs.length && readyDocs.length > 0}
              onChange={() => toggleAllSelection(readyDocs.map(d => d.id))}
              className="rounded border-[#2D3148] bg-[#0F1117] text-[#7C6FE0] focus:ring-[#7C6FE0] focus:ring-offset-[#1A1D27]"
            />
            <span className="text-sm text-[#F0F2FF] group-hover:text-[#7C6FE0] transition-colors">
              全部文档 ({readyDocs.length})
            </span>
          </label>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {documents.map(doc => {
            const isReady = doc.status === "READY";
            return (
              <label 
                key={doc.id} 
                className={cn(
                  "flex items-center gap-2 p-2 rounded-md transition-colors",
                  isReady ? "cursor-pointer hover:bg-[#21253A]" : "opacity-50 cursor-not-allowed",
                  selectedDocIds.includes(doc.id) ? "bg-[#21253A]/50" : ""
                )}
                title={!isReady ? "处理中，禁用" : doc.name}
              >
                <input 
                  type="checkbox"
                  checked={selectedDocIds.includes(doc.id)}
                  onChange={() => isReady && toggleDocSelection(doc.id)}
                  disabled={!isReady}
                  className="rounded border-[#2D3148] bg-[#0F1117] text-[#7C6FE0] focus:ring-[#7C6FE0] focus:ring-offset-[#1A1D27]"
                />
                <div className="flex flex-col min-w-0 flex-1">
                  <span className="text-sm text-[#F0F2FF] truncate">{doc.name}</span>
                  {isReady ? (
                    <span className="text-[10px] text-[#8B90AC]">
                      {doc.chunks} chunks · {doc.entities} 实体
                    </span>
                  ) : (
                    <span className="text-[10px] text-yellow-400">处理中</span>
                  )}
                </div>
              </label>
            )
          })}
        </div>
      </div>

      {/* Chat Area (Center) */}
      <div className="flex-1 flex flex-col min-w-0 bg-[#0F1117] relative">
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-[#4A5070]">
              <div className="w-16 h-16 rounded-full bg-[#1A1D27] flex items-center justify-center mb-4 border border-[#2D3148] shadow-[0_0_20px_rgba(124,111,224,0.1)]">
                <FileText className="w-8 h-8 text-[#7C6FE0]" />
              </div>
              <h2 className="text-xl font-bold text-[#F0F2FF] mb-6">有什么我可以帮你的？</h2>
              <div className="grid gap-3 max-w-lg w-full">
                {["这篇文档的核心内容是什么？", "文档中提到了哪些关键概念？", "能给我一个执行摘要吗？"].map((q, i) => (
                  <button 
                    key={i}
                    onClick={() => setInput(q)}
                    className="p-3 text-sm text-left bg-[#1A1D27] hover:bg-[#21253A] border border-[#2D3148] rounded-lg text-[#F0F2FF] transition-all hover:border-[#7C6FE0]"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((msg) => (
              <div key={msg.id} className={cn("flex flex-col max-w-3xl", msg.role === "user" ? "ml-auto items-end" : "mr-auto items-start")}>
                {msg.role === "user" ? (
                  <div className="bg-[#7C6FE0] text-white px-5 py-3 rounded-2xl rounded-tr-sm shadow-md">
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                    <div className="text-[10px] text-white/70 text-right mt-1.5">
                      {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </div>
                  </div>
                ) : (
                  <div className="bg-[#1A1D27] border border-[#2D3148] rounded-2xl rounded-tl-sm w-full shadow-sm overflow-hidden">
                    <div className="px-5 py-3 border-b border-[#2D3148] flex items-center gap-2 bg-[#1A1D27]/80">
                      <div className="w-6 h-6 rounded-full bg-[#7C6FE0]/20 flex items-center justify-center border border-[#7C6FE0]/30">
                        <span className="text-[#7C6FE0] text-xs font-bold">◈</span>
                      </div>
                      <span className="font-medium text-[#F0F2FF] text-sm">GraphRAG Agent</span>
                    </div>
                    
                    <div className="px-5 py-4 prose prose-invert prose-p:leading-relaxed prose-pre:bg-[#0F1117] prose-pre:border prose-pre:border-[#2D3148] max-w-none text-[#F0F2FF] text-sm">
                      {msg.isLoading ? (
                        <div className="flex flex-col gap-2.5">
                          <div className="flex items-center gap-3 text-sm text-[#8B90AC]">
                            <Loader2 className="w-4 h-4 animate-spin text-[#7C6FE0]" />
                            <span>路由分析中...</span>
                            <RouteTag route="hybrid_query" className="ml-auto" />
                          </div>
                          <div className="flex items-center gap-3 text-sm text-emerald-400/70">
                            <Check className="w-4 h-4" />
                            <span>检索知识图谱（5 个实体）</span>
                          </div>
                          <div className="flex items-center gap-3 text-sm text-emerald-400/70">
                            <Check className="w-4 h-4" />
                            <span>检索文档段落（9 个 chunks）</span>
                          </div>
                          <div className="flex items-center gap-3 text-sm text-emerald-400/70">
                            <Check className="w-4 h-4" />
                            <span>评估检索充分性...</span>
                          </div>
                          <div className="flex items-center gap-3 text-sm text-[#F0F2FF] mt-2">
                            <span className="w-1.5 h-4 bg-[#7C6FE0] animate-pulse" />
                            <span className="animate-pulse">生成答案中</span>
                          </div>
                        </div>
                      ) : (
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {msg.content}
                        </ReactMarkdown>
                      )}
                    </div>
                    
                    {!msg.isLoading && msg.meta && (
                      <div className="px-5 py-3 bg-[#0F1117] border-t border-[#2D3148] flex flex-wrap items-center gap-3">
                        <RouteTag route={msg.meta.route} />
                        
                        {msg.meta.rewrite_count > 0 ? (
                          <span className="text-xs text-yellow-400 bg-yellow-400/10 px-2 py-0.5 rounded border border-yellow-400/20">改写 {msg.meta.rewrite_count}次</span>
                        ) : (
                          <span className="text-xs text-[#8B90AC] bg-[#2D3148] px-2 py-0.5 rounded">未改写</span>
                        )}
                        
                        {msg.meta.sufficient ? (
                          <span className="text-xs text-emerald-400 bg-emerald-400/10 px-2 py-0.5 rounded border border-emerald-400/20 flex items-center gap-1"><Check className="w-3 h-3" /> 充分</span>
                        ) : (
                          <span className="text-xs text-yellow-400 bg-yellow-400/10 px-2 py-0.5 rounded border border-yellow-400/20 flex items-center gap-1">待补充</span>
                        )}
                        
                        <span className={cn(
                          "text-xs px-2 py-0.5 rounded border",
                          msg.meta.latency_ms > 10000 
                            ? "text-orange-400 bg-orange-400/10 border-orange-400/20"
                            : "text-[#8B90AC] bg-[#2D3148] border-transparent"
                        )}>
                          {(msg.meta.latency_ms / 1000).toFixed(1)}s
                        </span>
                        
                        <button 
                          onClick={() => {
                            setCurrentSources(msg.sources || null);
                            toggleSourcePanel(true);
                          }}
                          className="ml-auto text-xs text-[#7C6FE0] hover:text-[#A598F0] font-medium flex items-center transition-colors group"
                        >
                          查看来源 {msg.sources?.kg_entities.length || 0} <ChevronRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="p-4 bg-[#1A1D27] border-t border-[#2D3148]">
          <div className="max-w-4xl mx-auto relative">
            <div className={cn(
              "bg-[#0F1117] border rounded-xl flex items-end transition-all focus-within:ring-1 focus-within:ring-[#7C6FE0]/50",
              shake ? "border-red-400 animate-[shake_0.5s_ease-in-out]" : "border-[#2D3148] focus-within:border-[#7C6FE0]",
              isSending ? "opacity-70 pointer-events-none" : ""
            )}>
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="输入你的问题... (Shift+Enter 换行)"
                className="flex-1 bg-transparent text-[#F0F2FF] text-sm p-4 max-h-40 min-h-[56px] resize-none focus:outline-none placeholder:text-[#4A5070]"
                rows={Math.min(5, Math.max(1, input.split('\n').length))}
                disabled={isSending}
              />
              <div className="p-2 flex-none">
                <button
                  onClick={handleSend}
                  disabled={isSending || !input.trim()}
                  className="bg-[#7C6FE0] hover:bg-[#A598F0] disabled:bg-[#2D3148] disabled:text-[#4A5070] text-white p-2 rounded-lg transition-colors flex items-center justify-center shadow-sm"
                >
                  {isSending ? <X className="w-5 h-5" /> : <Send className="w-5 h-5" />}
                </button>
              </div>
            </div>
            <div className="mt-2 flex items-center gap-1.5 text-xs text-[#4A5070]">
              <Info className="w-3 h-3" />
              <span>检索范围：{selectedDocIds.length} 份文档</span>
            </div>
          </div>
        </div>
      </div>

      {/* Source Panel (Right) */}
      <div 
        className={cn(
          "flex-none bg-[#1A1D27] border-l border-[#2D3148] transition-all duration-300 ease-in-out flex flex-col",
          isSourcePanelOpen ? "w-[340px]" : "w-[40px] cursor-pointer hover:bg-[#21253A]"
        )}
        onClick={() => !isSourcePanelOpen && toggleSourcePanel(true)}
      >
        {!isSourcePanelOpen ? (
          <div className="flex-1 flex flex-col items-center py-4">
            <button className="text-[#8B90AC] hover:text-white transition-colors" title="展开溯源面板">
              <ChevronRight className="w-5 h-5 rotate-180" />
            </button>
            <div className="mt-8 rotate-90 whitespace-nowrap text-[#8B90AC] text-sm font-medium tracking-wider">
              来源溯源
            </div>
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between p-4 border-b border-[#2D3148]">
              <div>
                <h3 className="font-semibold text-[#F0F2FF]">来源溯源</h3>
                {currentSources && <p className="text-xs text-[#8B90AC] mt-1">最近回答：hybrid_query</p>}
              </div>
              <button 
                onClick={(e) => { e.stopPropagation(); toggleSourcePanel(false); }}
                className="text-[#8B90AC] hover:text-white transition-colors p-1"
                title="折叠"
              >
                <ChevronRight className="w-5 h-5" />
              </button>
            </div>
            
            <div className="flex-1 overflow-y-auto p-4 space-y-6">
              {!currentSources ? (
                <div className="text-center text-[#4A5070] py-10 text-sm">
                  提问后将在此显示来源追溯
                </div>
              ) : (
                <>
                  {/* KG Entities */}
                  <div>
                    <h4 className="text-xs font-semibold text-[#8B90AC] mb-3 flex items-center gap-2">
                      <span>KG 实体 ({currentSources.kg_entities.length})</span>
                      <div className="flex-1 h-px bg-[#2D3148]"></div>
                    </h4>
                    <div className="space-y-3">
                      {currentSources.kg_entities.map((entity, idx) => (
                        <EntityCard key={idx} entity={entity} />
                      ))}
                    </div>
                  </div>

                  {/* Passages */}
                  <div>
                    <h4 className="text-xs font-semibold text-[#8B90AC] mb-3 flex items-center gap-2">
                      <span>原文段落 ({currentSources.passages.length})</span>
                      <div className="flex-1 h-px bg-[#2D3148]"></div>
                    </h4>
                    <div className="space-y-3">
                      {currentSources.passages.map((passage, idx) => (
                        <PassageCard key={idx} passage={passage} index={idx + 1} />
                      ))}
                    </div>
                  </div>

                  {/* Meta Info */}
                  <div>
                    <h4 className="text-xs font-semibold text-[#8B90AC] mb-3 flex items-center gap-2">
                      <span>元信息</span>
                      <div className="flex-1 h-px bg-[#2D3148]"></div>
                    </h4>
                    <div className="bg-[#0F1117] border border-[#2D3148] rounded-lg p-3 text-xs space-y-2">
                      <div className="flex justify-between">
                        <span className="text-[#4A5070]">路由策略</span>
                        <span className="text-[#F0F2FF]">hybrid_query</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[#4A5070]">改写次数</span>
                        <span className="text-[#F0F2FF]">0 次</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[#4A5070]">检索充分</span>
                        <span className="text-emerald-400">是</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[#4A5070]">耗时</span>
                        <span className="text-[#F0F2FF]">3.2 秒</span>
                      </div>
                    </div>
                  </div>
                </>
              )}
            </div>
          </>
        )}
      </div>

    </div>
  );
}

function EntityCard({ entity }: { entity: any }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="bg-[#0F1117] border border-[#2D3148] rounded-lg p-3 text-sm">
      <div className="flex items-start justify-between mb-2 gap-2">
        <span className="font-semibold text-[#F0F2FF]">{entity.name}</span>
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#7C6FE0]/20 text-[#7C6FE0] shrink-0 border border-[#7C6FE0]/30">{entity.type}</span>
      </div>
      <div className="space-y-1 mb-2">
        {Object.entries(entity.attributes).map(([k, v]) => (
          <div key={k} className="flex gap-2 text-xs">
            <span className="text-[#4A5070] w-20 shrink-0 truncate" title={k}>{k}</span>
            <span className="text-[#F0F2FF] truncate" title={v as string}>{v as string}</span>
          </div>
        ))}
      </div>
      <div className="border-t border-[#2D3148] pt-2 mt-2">
        <button 
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-[#8B90AC] hover:text-[#F0F2FF] flex items-center gap-1 transition-colors w-full"
        >
          {expanded ? "收起原文片段 ▲" : "展开原文片段 ▼"}
        </button>
        {expanded && (
          <div className="mt-2 text-xs text-[#8B90AC] leading-relaxed bg-[#1A1D27] p-2 rounded">
            {entity.context_snippet}
          </div>
        )}
      </div>
    </div>
  );
}

function PassageCard({ passage, index }: { passage: any, index: number }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="bg-[#0F1117] border border-[#2D3148] rounded-lg p-3 text-sm flex gap-3">
      <div className="text-[#7C6FE0] font-mono text-xs font-bold pt-0.5">[{index}]</div>
      <div className="flex-1 min-w-0">
        <div className="flex justify-between items-start mb-1 gap-2">
          <span className="font-medium text-[#F0F2FF] truncate text-xs">{passage.section}</span>
          <span className="text-[10px] text-[#4A5070] shrink-0">pg {passage.page}</span>
        </div>
        <div className="flex gap-1 mb-2 overflow-x-auto no-scrollbar">
          <span className={cn("text-[10px] px-1.5 py-0.5 rounded shrink-0", passage.chunk_type === 'text' ? "bg-blue-500/20 text-blue-400" : "bg-orange-500/20 text-orange-400")}>
            {passage.chunk_type}
          </span>
          {passage.entities.slice(0,2).map((e: string, i: number) => (
            <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-[#2D3148] text-[#8B90AC] shrink-0">{e}</span>
          ))}
        </div>
        <div className={cn("text-xs text-[#8B90AC] leading-relaxed", !expanded && "line-clamp-3")}>
          {passage.content}
        </div>
        <button 
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-[#7C6FE0] hover:text-[#A598F0] mt-1 transition-colors"
        >
          {expanded ? "收起 ▲" : "展开全文 ▼"}
        </button>
      </div>
    </div>
  );
}
