import { useEffect, useRef, useState, useMemo } from 'react';
import { useDocumentStore } from '../store';
import {
  Network, ZoomIn, ZoomOut, Maximize, Search, Hexagon, Database, Link as LinkIcon,
  Settings2, Loader2, Sparkles, X, Layers, AlertTriangle,
} from 'lucide-react';
import ForceGraph2D from 'react-force-graph-2d';
import { cn } from '../components/ui';

/** ⚠️ 后端未开发提示横幅 */
function UnimplementedBanner() {
  return (
    <div className="flex items-center gap-3 mx-6 mt-4 px-4 py-3 bg-yellow-400/10 border border-yellow-400/30 rounded-xl text-yellow-400 text-sm">
      <AlertTriangle className="w-5 h-5 shrink-0" />
      <div>
        <span className="font-semibold">后端接口未开发</span>
        <span className="text-yellow-300/80 ml-2">
          KG 图谱可视化所需的实体图数据接口（/api/v1/kg/graph）在当前版本中尚未实现，
          页面展示的图谱数据为 Mock 数据，不反映真实知识库内容。
        </span>
      </div>
    </div>
  );
}

const generateMockGraphData = (docCount: number) => {
  if (docCount === 0) return { nodes: [], links: [] };
  const nodes: any[] = [];
  const links: any[] = [];
  
  nodes.push({ id: 'GraphRAG', name: 'GraphRAG System', val: 30, group: 0, color: '#7C6FE0', type: 'Concept', description: 'Advanced RAG system utilizing Knowledge Graphs for context retrieval.' });
  
  const topics = ['Architecture', 'Implementation', 'Deployment', 'Use Cases', 'Evaluation'];
  topics.forEach((topic, i) => {
    nodes.push({ id: topic, name: topic, val: 20, group: 1, color: '#A598F0', type: 'Category', description: `Main category representing the ${topic} of the system.` });
    links.push({ id: `l-${i}`, source: 'GraphRAG', target: topic, value: 3, relation: 'contains', description: 'System includes this topic component.' });
    
    const subEntityCount = 3 + (docCount * 2) + Math.floor(Math.random() * 5);
    for (let j = 0; j < subEntityCount; j++) {
      const entityId = `${topic}-entity-${j}`;
      nodes.push({ 
        id: entityId, 
        name: `Entity ${j + 1}`, 
        val: 10 + Math.random() * 5, 
        group: 2,
        type: ['Technology', 'Process', 'Metric'][Math.floor(Math.random() * 3)],
        description: `Detailed entity related to ${topic}, extracted from the documentation.`,
        color: ['#4A5070', '#8B90AC', '#2D3148'][Math.floor(Math.random() * 3)]
      });
      links.push({ id: `sub-l-${topic}-${j}`, source: topic, target: entityId, value: 1, relation: 'relates_to', description: 'Hierarchical or structural relationship.' });
      
      if (Math.random() > 0.8 && nodes.length > 10) {
        const targetNode = nodes[Math.floor(Math.random() * (nodes.length - 1))];
        if (targetNode.id !== entityId && targetNode.group === 2) {
          links.push({ id: `cross-l-${entityId}-${targetNode.id}`, source: entityId, target: targetNode.id, value: 0.5, relation: 'co_occurs', description: 'Occurs in the same document chunk context.' });
        }
      }
    }
  });

  return { nodes, links };
};

export default function KGVisualizerPage() {
  const fgRef = useRef<any>();
  const documents = useDocumentStore(state => state.documents);
  const readyDocs = documents.filter(d => d.status === 'READY');
  
  const [viewMode, setViewMode] = useState<'browse' | 'search'>('browse');

  // Browse States
  const [browseQuery, setBrowseQuery] = useState('');
  
  // Search States
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [searchResultGraph, setSearchResultGraph] = useState<{nodes: any[], links: any[]}>({ nodes: [], links: [] });
  const [searchDepth, setSearchDepth] = useState(2);
  const [topKEntities, setTopKEntities] = useState(15);
  const [minSimilarity, setMinSimilarity] = useState(0.75);

  // Common States
  const [selectedNode, setSelectedNode] = useState<any>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const containerRef = useRef<HTMLDivElement>(null);

  const globalGraphData = useMemo(() => generateMockGraphData(readyDocs.length), [readyDocs.length]);

  const browseFilteredData = useMemo(() => {
    if (!browseQuery) return globalGraphData;
    
    const query = browseQuery.toLowerCase();
    const filteredNodes = globalGraphData.nodes.filter(n => n.name.toLowerCase().includes(query) || n.id.toLowerCase().includes(query));
    const filteredNodeIds = new Set(filteredNodes.map(n => n.id));
    
    const filteredLinks = globalGraphData.links.filter(l => 
      filteredNodeIds.has(typeof l.source === 'object' ? l.source.id : l.source) ||
      filteredNodeIds.has(typeof l.target === 'object' ? l.target.id : l.target)
    );
    
    filteredLinks.forEach(l => {
      filteredNodeIds.add(typeof l.source === 'object' ? l.source.id : l.source);
      filteredNodeIds.add(typeof l.target === 'object' ? l.target.id : l.target);
    });
    
    return {
      nodes: globalGraphData.nodes.filter(n => filteredNodeIds.has(n.id)),
      links: filteredLinks
    };
  }, [globalGraphData, browseQuery]);

  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight
        });
      }
    };
    
    updateDimensions();
    const resizeObserver = new ResizeObserver(() => updateDimensions());
    if (containerRef.current) resizeObserver.observe(containerRef.current);
    window.addEventListener('resize', updateDimensions);
    return () => {
      window.removeEventListener('resize', updateDimensions);
      resizeObserver.disconnect();
    };
  }, []);

  // Center Graph When Switching View Mode
  useEffect(() => {
    setSelectedNode(null);
    if (fgRef.current) {
      setTimeout(() => {
        fgRef.current.zoomToFit(400, 50);
      }, 200);
    }
  }, [viewMode]);

  const handleNodeClick = (node: any) => {
    setSelectedNode(node);
    if (fgRef.current) {
      setTimeout(() => {
        try {
          fgRef.current.centerAt(node.x, node.y, 1000);
          fgRef.current.zoom(4, 1000);
        } catch (e) {}
      }, 50);
    }
  };

  const handleSearch = () => {
    if (!searchQuery.trim()) {
      clearSearch();
      return;
    }

    setIsSearching(true);
    setHasSearched(true);
    setSelectedNode(null);
    
    setTimeout(() => {
      const seed = searchQuery.length % globalGraphData.nodes.length;
      const candidateNodes = globalGraphData.nodes.filter(n => n.group > 0);
      const centerNode = candidateNodes[seed % candidateNodes.length] || globalGraphData.nodes[0];
      
      const retrievedNodeIds = new Set<string>();
      const retrievedLinks = new Set<any>();
      
      if (centerNode) {
        retrievedNodeIds.add(centerNode.id);
        let currentLevel = new Set([centerNode.id]);
        
        for (let depth = 0; depth < searchDepth; depth++) {
          const nextLevel = new Set<string>();
          globalGraphData.links.forEach(l => {
            const sourceId = typeof l.source === 'object' ? l.source.id : l.source;
            const targetId = typeof l.target === 'object' ? l.target.id : l.target;
            if (currentLevel.has(sourceId)) { nextLevel.add(targetId); retrievedLinks.add(l); } 
            else if (currentLevel.has(targetId)) { nextLevel.add(sourceId); retrievedLinks.add(l); }
          });
          nextLevel.forEach(id => retrievedNodeIds.add(id));
          currentLevel = nextLevel;
          if (retrievedNodeIds.size >= topKEntities) break;
        }
      }
      
      const finalNodeIds = Array.from(retrievedNodeIds).slice(0, topKEntities);
      const finalNodeIdsSet = new Set(finalNodeIds);
      
      const nodes = globalGraphData.nodes.filter(n => finalNodeIdsSet.has(n.id)).map(n => ({
        ...n,
        relevanceScore: n.id === centerNode.id ? 0.99 : Math.max(0.65, 0.95 - Math.random() * 0.3)
      }));
      
      const links = Array.from(retrievedLinks).filter(l => {
        const sourceId = typeof l.source === 'object' ? l.source.id : l.source;
        const targetId = typeof l.target === 'object' ? l.target.id : l.target;
        return finalNodeIdsSet.has(sourceId) && finalNodeIdsSet.has(targetId);
      });
      
      setSearchResultGraph({ nodes, links });
      setIsSearching(false);
      
      setTimeout(() => {
        if (fgRef.current) fgRef.current.zoomToFit(1000, 50);
      }, 100);
    }, 1000);
  };

  const clearSearch = () => {
    setSearchQuery('');
    setHasSearched(false);
    setSearchResultGraph({ nodes: [], links: [] });
    setSelectedNode(null);
  };

  if (readyDocs.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center bg-[#0F1117] h-full">
        <Network className="w-16 h-16 text-[#2D3148] mb-4" />
        <h2 className="text-xl font-bold text-[#F0F2FF] mb-2">暂无可用图谱</h2>
        <p className="text-[#8B90AC]">请先在知识库中上传并处理文档，完成后即可预览知识图谱与检索测试</p>
      </div>
    );
  }

  const currentGraphData = viewMode === 'browse' ? browseFilteredData : searchResultGraph;

  return (
    <div className="flex flex-col h-full w-full bg-[#0F1117] overflow-hidden">
      <UnimplementedBanner />
      <div className="flex flex-col md:flex-row flex-1 overflow-hidden">

      {/* Left Sidebar Control Panel */}
      <div className="w-full md:w-[320px] flex-none border-b md:border-b-0 md:border-r border-[#2D3148] bg-[#1A1D27] flex flex-col z-10 shadow-xl">
        
        {/* Mode Switcher */}
        <div className="p-4 border-b border-[#2D3148] bg-[#14161E]">
          <div className="flex bg-[#0F1117] border border-[#2D3148] rounded-lg p-1">
            <button
              onClick={() => setViewMode('browse')}
              className={cn(
                "flex-1 py-1.5 text-sm font-medium rounded-md flex items-center justify-center gap-2 transition-colors",
                viewMode === 'browse' ? "bg-[#2D3148] text-[#F0F2FF]" : "text-[#8B90AC] hover:text-[#F0F2FF]"
              )}
            >
              <Network className="w-4 h-4" /> 图谱可视化
            </button>
            <button
              onClick={() => setViewMode('search')}
              className={cn(
                "flex-1 py-1.5 text-sm font-medium rounded-md flex items-center justify-center gap-2 transition-colors",
                viewMode === 'search' ? "bg-[#7C6FE0] text-white" : "text-[#8B90AC] hover:text-[#F0F2FF]"
              )}
            >
              <Search className="w-4 h-4" /> 图谱检索
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-6">
          {/* Browse Mode Sidebar */}
          {viewMode === 'browse' && (
            <>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#8B90AC]" />
                <input 
                  type="text" 
                  placeholder="在全图谱中过滤节点..." 
                  value={browseQuery}
                  onChange={(e) => setBrowseQuery(e.target.value)}
                  className="w-full bg-[#0F1117] border border-[#2D3148] rounded-md py-2 pl-9 pr-3 text-sm text-[#F0F2FF] placeholder:text-[#4A5070] focus:outline-none focus:border-[#7C6FE0] transition-colors shadow-inner"
                />
              </div>

              {selectedNode ? (
                <div className="space-y-4 animate-in fade-in">
                  <div className="flex justify-between items-center">
                    <h3 className="text-[#F0F2FF] font-semibold text-lg truncate pr-2">{selectedNode.name}</h3>
                    <span className="text-xs px-2 py-1 rounded bg-[#2D3148] text-[#8B90AC] shrink-0 font-mono">
                      {selectedNode.id.substring(0, 8)}
                    </span>
                  </div>
                  
                  <div className="p-3 bg-[#0F1117] border border-[#2D3148] rounded-lg shadow-sm">
                    <p className="text-sm text-[#8B90AC] leading-relaxed">
                      {selectedNode.description || 'No description available for this entity.'}
                    </p>
                  </div>
                  
                  <div className="space-y-2 text-sm bg-[#0F1117] p-3 rounded-lg border border-[#2D3148] shadow-sm">
                    <div className="flex justify-between border-b border-[#2D3148] pb-2">
                      <span className="text-[#4A5070]">实体类型</span>
                      <span className="text-[#F0F2FF] flex items-center gap-1">
                        <Hexagon className="w-3.5 h-3.5 text-[#7C6FE0]" />
                        {selectedNode.type || 'Entity'}
                      </span>
                    </div>
                    <div className="flex justify-between pt-2">
                      <span className="text-[#4A5070]">图谱度数 (Degree)</span>
                      <span className="text-[#F0F2FF] font-mono">
                        {globalGraphData.links.filter(l => 
                          (typeof l.source === 'object' ? l.source.id : l.source) === selectedNode.id || 
                          (typeof l.target === 'object' ? l.target.id : l.target) === selectedNode.id
                        ).length}
                      </span>
                    </div>
                  </div>

                  <div className="mt-6">
                    <h4 className="text-sm font-medium text-[#8B90AC] mb-3 flex items-center gap-2 uppercase tracking-wider">
                      <LinkIcon className="w-4 h-4" />
                      直连子图 (1-hop)
                    </h4>
                    <div className="space-y-2">
                      {globalGraphData.links
                        .filter(l => 
                          (typeof l.source === 'object' ? l.source.id : l.source) === selectedNode.id || 
                          (typeof l.target === 'object' ? l.target.id : l.target) === selectedNode.id
                        )
                        .slice(0, 10)
                        .map((l, i) => {
                          const sourceId = typeof l.source === 'object' ? l.source.id : l.source;
                          const targetId = typeof l.target === 'object' ? l.target.id : l.target;
                          const otherId = sourceId === selectedNode.id ? targetId : sourceId;
                          const otherNode = globalGraphData.nodes.find(n => n.id === otherId);
                          
                          return (
                            <div key={i} className="flex items-center gap-2 p-2 rounded-lg bg-[#0F1117] border border-[#2D3148] cursor-pointer hover:border-[#7C6FE0] transition-all shadow-sm" onClick={() => otherNode && handleNodeClick(otherNode)}>
                              <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: otherNode?.color || '#8B90AC' }}></div>
                              <span className="text-sm text-[#F0F2FF] truncate flex-1 hover:text-[#7C6FE0]">{otherNode?.name || otherId}</span>
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#1A1D27] text-[#4A5070] border border-[#2D3148]">
                                {l.relation}
                              </span>
                            </div>
                          )
                        })}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="h-full flex flex-col items-center justify-center text-[#4A5070] text-sm text-center pt-20">
                  <Network className="w-10 h-10 mb-4 opacity-30 text-[#8B90AC]" />
                  <p>在右侧全局图谱中<br/>点击节点查看详细特征及三元组</p>
                  
                  <div className="mt-10 text-left w-full space-y-4">
                    <h4 className="text-xs font-semibold text-[#8B90AC] flex items-center gap-2 uppercase tracking-wider">
                      <Database className="w-4 h-4" /> 当前图谱库统计
                    </h4>
                    <div className="grid grid-cols-2 gap-2">
                      <div className="bg-[#0F1117] p-3 rounded-lg border border-[#2D3148] shadow-sm">
                        <div className="text-2xl font-bold text-[#F0F2FF]">{globalGraphData.nodes.length}</div>
                        <div className="text-xs text-[#4A5070]">实体 (Nodes)</div>
                      </div>
                      <div className="bg-[#0F1117] p-3 rounded-lg border border-[#2D3148] shadow-sm">
                        <div className="text-2xl font-bold text-[#F0F2FF]">{globalGraphData.links.length}</div>
                        <div className="text-xs text-[#4A5070]">关系 (Edges)</div>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}

          {/* Search Mode Sidebar */}
          {viewMode === 'search' && (
            <>
              <div>
                <h3 className="text-xs font-semibold text-[#8B90AC] uppercase tracking-wider mb-4">检索召回参数</h3>
                <div className="space-y-6">
                  <div className="space-y-3">
                    <div className="flex justify-between items-center text-sm">
                      <label className="text-[#8B90AC]">扩展深度 (Hop Size)</label>
                      <span className="text-[#F0F2FF] font-mono">{searchDepth}</span>
                    </div>
                    <input type="range" min="1" max="3" step="1" value={searchDepth} onChange={(e) => setSearchDepth(parseInt(e.target.value))} className="w-full accent-[#7C6FE0]" />
                    <div className="flex justify-between text-xs text-[#4A5070]"><span>1 级 (精准)</span><span>3 级 (泛化)</span></div>
                  </div>

                  <div className="space-y-3">
                    <div className="flex justify-between items-center text-sm">
                      <label className="text-[#8B90AC]">返回最大实体数 (Top K)</label>
                      <span className="text-[#F0F2FF] font-mono">{topKEntities}</span>
                    </div>
                    <input type="range" min="5" max="50" step="5" value={topKEntities} onChange={(e) => setTopKEntities(parseInt(e.target.value))} className="w-full accent-[#7C6FE0]" />
                  </div>

                  <div className="space-y-3">
                    <div className="flex justify-between items-center text-sm">
                      <label className="text-[#8B90AC]">实体相似度阈值</label>
                      <span className="text-[#F0F2FF] font-mono">{minSimilarity.toFixed(2)}</span>
                    </div>
                    <input type="range" min="0.5" max="0.95" step="0.05" value={minSimilarity} onChange={(e) => setMinSimilarity(parseFloat(e.target.value))} className="w-full accent-[#7C6FE0]" />
                  </div>
                </div>
              </div>

              {hasSearched && (
                <div className="pt-6 border-t border-[#2D3148] space-y-4">
                  <h3 className="text-xs font-semibold text-[#8B90AC] uppercase tracking-wider flex items-center justify-between">
                    召回子图特征
                    <span className="px-2 py-0.5 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded text-[10px]">
                      局部视图
                    </span>
                  </h3>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="bg-[#0F1117] p-3 rounded-lg border border-[#2D3148] shadow-sm">
                      <div className="text-2xl font-bold text-[#F0F2FF]">{searchResultGraph.nodes.length}</div>
                      <div className="text-xs text-[#4A5070]">实体 (Nodes)</div>
                    </div>
                    <div className="bg-[#0F1117] p-3 rounded-lg border border-[#2D3148] shadow-sm">
                      <div className="text-2xl font-bold text-[#F0F2FF]">{searchResultGraph.links.length}</div>
                      <div className="text-xs text-[#4A5070]">关系 (Edges)</div>
                    </div>
                  </div>
                </div>
              )}

              {selectedNode && (
                <div className="pt-6 border-t border-[#2D3148] space-y-3 animate-in fade-in slide-in-from-bottom-2">
                  <h3 className="text-xs font-semibold text-[#8B90AC] uppercase tracking-wider flex justify-between items-center">
                    <span>选中实体详情</span>
                    <button onClick={() => setSelectedNode(null)} className="text-[#4A5070] hover:text-[#F0F2FF]">
                      <X className="w-3 h-3" />
                    </button>
                  </h3>
                  <div className="bg-[#0F1117] border border-[#2D3148] rounded-xl p-4 shadow-sm relative overflow-hidden">
                    <div className="absolute top-0 left-0 w-1 h-full" style={{ backgroundColor: selectedNode.color || '#7C6FE0' }}></div>
                    <div className="flex justify-between items-start mb-2">
                      <h4 className="text-[#F0F2FF] font-medium leading-tight pr-2">{selectedNode.name}</h4>
                    </div>
                    <div className="flex items-center gap-2 mb-3">
                      <span className="text-[10px] px-2 py-1 rounded bg-[#1A1D27] text-[#8B90AC] border border-[#2D3148] flex items-center gap-1">
                        <Hexagon className="w-3 h-3 text-[#7C6FE0]" />
                        {selectedNode.type || 'Entity'}
                      </span>
                      <span className="text-[10px] px-2 py-1 rounded bg-[#1A1D27] text-[#8B90AC] border border-[#2D3148] font-mono">
                        ID: {selectedNode.id.substring(0, 6)}
                      </span>
                    </div>
                    <p className="text-xs text-[#8B90AC] leading-relaxed mb-3">{selectedNode.description || 'No description available for this entity.'}</p>
                    {selectedNode.relevanceScore && (
                      <div className="flex items-center justify-between text-xs pt-3 border-t border-[#2D3148] mt-3">
                        <span className="text-[#4A5070]">检索匹配度</span>
                        <span className="text-emerald-400 font-mono font-medium">{(selectedNode.relevanceScore * 100).toFixed(1)}%</span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {hasSearched && searchResultGraph.nodes.length > 0 && !selectedNode && (
                <div className="pt-6 border-t border-[#2D3148] space-y-3 animate-in fade-in">
                  <h3 className="text-xs font-semibold text-[#8B90AC] uppercase tracking-wider">Top 命中实体</h3>
                  <div className="space-y-2 max-h-[250px] overflow-y-auto pr-1">
                    {[...searchResultGraph.nodes]
                      .sort((a, b) => (b.relevanceScore || 0) - (a.relevanceScore || 0))
                      .slice(0, 10)
                      .map((n) => (
                        <div 
                          key={n.id} 
                          onClick={() => handleNodeClick(n)}
                          className="flex items-center justify-between text-xs p-2.5 bg-[#0F1117] rounded-lg border border-[#2D3148] cursor-pointer hover:border-[#7C6FE0] transition-all group shadow-sm"
                        >
                          <div className="flex items-center gap-2 overflow-hidden">
                            <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: n.color || '#7C6FE0' }}></div>
                            <span className="text-[#F0F2FF] truncate max-w-[130px] group-hover:text-[#7C6FE0] transition-colors">{n.name}</span>
                          </div>
                          <span className="text-emerald-400 font-mono font-medium shrink-0">{(n.relevanceScore * 100).toFixed(1)}%</span>
                        </div>
                    ))}
                  </div>
                </div>
              )}

              {!hasSearched && (
                 <div className="pt-6 border-t border-[#2D3148] flex flex-col items-center justify-center text-center opacity-50 py-10">
                   <Database className="w-10 h-10 text-[#4A5070] mb-3" />
                   <p className="text-xs text-[#8B90AC]">
                     在上方使用输入框进行图谱召回测试<br/>系统将动态展示相关子图
                   </p>
                 </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Main Graph Area */}
      <div className="flex-1 bg-[#0B0D13] relative flex flex-col min-w-0">
        
        {/* Search Header for Search Mode */}
        {viewMode === 'search' && (
          <div className="p-5 md:p-6 border-b border-[#2D3148] bg-[#1A1D27] shrink-0 z-10 shadow-sm flex flex-col gap-4">
            <div className="flex flex-col sm:flex-row gap-3">
              <div className="relative flex-1">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-[#8B90AC]" />
                <input 
                  type="text" 
                  placeholder="输入问题，图谱引擎将计算并高亮召回相关子图 (Sub-Graph)..." 
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  className="w-full bg-[#0F1117] border border-[#2D3148] rounded-xl py-3.5 pl-12 pr-10 text-[#F0F2FF] placeholder:text-[#4A5070] focus:outline-none focus:border-[#7C6FE0] focus:ring-1 focus:ring-[#7C6FE0] transition-all text-base shadow-inner"
                />
                {searchQuery && (
                  <button onClick={clearSearch} className="absolute right-4 top-1/2 -translate-y-1/2 text-[#4A5070] hover:text-[#F0F2FF]">
                    <X className="w-4 h-4" />
                  </button>
                )}
              </div>
              
              <div className="flex gap-2 shrink-0">
                <button 
                  onClick={handleSearch}
                  disabled={isSearching || !searchQuery.trim()}
                  className="px-6 py-3.5 bg-[#7C6FE0] hover:bg-[#6A5DD3] text-white rounded-xl font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 shadow-lg shadow-[#7C6FE0]/20"
                >
                  {isSearching ? <Loader2 className="w-5 h-5 animate-spin" /> : <Sparkles className="w-5 h-5" />}
                  检索图谱
                </button>
              </div>
            </div>
          </div>
        )}

        {/* View Tools */}
        {(viewMode === 'browse' || (viewMode === 'search' && hasSearched && searchResultGraph.nodes.length > 0)) && (
          <div className={cn("absolute right-4 z-10 flex flex-col gap-2", viewMode === 'search' ? "top-6" : "top-4")}>
            <button className="p-2.5 bg-[#1A1D27] border border-[#2D3148] rounded-lg hover:border-[#7C6FE0] text-[#8B90AC] hover:text-[#F0F2FF] transition-colors shadow-lg" onClick={() => fgRef.current?.zoom(fgRef.current.zoom() * 1.5, 400)}>
              <ZoomIn className="w-5 h-5" />
            </button>
            <button className="p-2.5 bg-[#1A1D27] border border-[#2D3148] rounded-lg hover:border-[#7C6FE0] text-[#8B90AC] hover:text-[#F0F2FF] transition-colors shadow-lg" onClick={() => fgRef.current?.zoom(fgRef.current.zoom() / 1.5, 400)}>
              <ZoomOut className="w-5 h-5" />
            </button>
            <button className="p-2.5 bg-[#1A1D27] border border-[#2D3148] rounded-lg hover:border-[#7C6FE0] text-[#8B90AC] hover:text-[#F0F2FF] transition-colors shadow-lg" onClick={() => fgRef.current?.zoomToFit(400, 50)}>
              <Maximize className="w-5 h-5" />
            </button>
          </div>
        )}

        {/* Empty States for Search Mode */}
        {viewMode === 'search' && isSearching && (
          <div className="absolute inset-0 top-[100px] z-20 flex flex-col items-center justify-center bg-[#0B0D13]/80 backdrop-blur-sm">
            <Loader2 className="w-12 h-12 animate-spin text-[#7C6FE0] mb-4" />
            <p className="text-[#F0F2FF] font-medium text-lg">正在执行基于种子的社区扩展与图谱寻路...</p>
            <p className="text-[#8B90AC] text-sm mt-2">Extracting High-Relevance Sub-Graphs</p>
          </div>
        )}

        {viewMode === 'search' && hasSearched && !isSearching && searchResultGraph.nodes.length === 0 && (
          <div className="absolute inset-0 top-[100px] z-10 flex flex-col items-center justify-center bg-[#0B0D13]">
            <Network className="w-16 h-16 text-[#2D3148] mb-4" />
            <p className="text-[#F0F2FF] text-lg font-medium mb-2">未能检索到相关的实体子图</p>
            <p className="text-[#8B90AC]">请尝试调整左侧检索阈值参数，或更换不同的查询词</p>
          </div>
        )}

        {viewMode === 'search' && !hasSearched && !isSearching && (
          <div className="absolute inset-0 top-[100px] z-10 flex flex-col items-center justify-center bg-[#0B0D13]">
            <Database className="w-16 h-16 text-[#2D3148] mb-4 opacity-50" />
            <p className="text-[#F0F2FF] text-lg font-medium mb-2">等待检索请求</p>
            <p className="text-[#8B90AC]">在上方的搜索框中输入内容以查看相关子图</p>
          </div>
        )}

        {/* Canvas Container */}
        {(viewMode === 'browse' || (viewMode === 'search' && hasSearched && searchResultGraph.nodes.length > 0)) && (
          <div className="flex-1 relative" ref={containerRef}>
            {dimensions.width > 0 && dimensions.height > 0 && (
              <ForceGraph2D
                ref={fgRef}
                width={dimensions.width}
                height={dimensions.height}
                graphData={currentGraphData}
                nodeLabel={(node: any) => viewMode === 'search' && node.relevanceScore ? `${node.name} (${(node.relevanceScore * 100).toFixed(1)}%)` : node.name}
                nodeColor={(node: any) => {
                  if (selectedNode && node.id === selectedNode.id) return '#FFFFFF';
                  return node.color || '#A598F0';
                }}
                nodeRelSize={viewMode === 'search' ? 6 : 4}
                linkColor={() => '#2D3148'}
                linkWidth={(link: any) => {
                  if (selectedNode) {
                    const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
                    const targetId = typeof link.target === 'object' ? link.target.id : link.target;
                    if (sourceId === selectedNode.id || targetId === selectedNode.id) return 2;
                  }
                  return 1;
                }}
                linkDirectionalParticles={(link: any) => {
                  if (selectedNode) {
                    const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
                    const targetId = typeof link.target === 'object' ? link.target.id : link.target;
                    if (sourceId === selectedNode.id || targetId === selectedNode.id) return viewMode === 'search' ? 3 : 2;
                  }
                  return viewMode === 'search' ? 1 : 0;
                }}
                linkDirectionalParticleSpeed={d => typeof d.value === 'number' ? d.value * 0.001 : 0.002}
                linkDirectionalParticleWidth={selectedNode ? 3 : 2}
                onNodeClick={handleNodeClick}
                onBackgroundClick={() => setSelectedNode(null)}
                backgroundColor="transparent"
                linkHoverPrecision={10}
                onEngineStop={() => { if (!selectedNode && viewMode === 'search') fgRef.current?.zoomToFit(400, 80); }}
              />
            )}
          </div>
        )}
      </div>
      </div>
    </div>
  );
}