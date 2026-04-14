import React, { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Search, FileText, X, CheckCircle, FileSpreadsheet, FileImage, FileCode, Clock, Check, MoreVertical, BrainCircuit } from "lucide-react";
import { cn, ProgressBar, StatusBadge, toast } from "../components/ui";
import { useDocumentStore, Document } from "../store";
import { useNavigate } from "react-router";
import { format } from "date-fns";

const FILE_ICONS: Record<string, any> = {
  PDF: FileText,
  DOCX: FileText,
  DOC: FileText,
  XLSX: FileSpreadsheet,
  XLS: FileSpreadsheet,
  PPTX: FileText,
  JPG: FileImage,
  PNG: FileImage,
  HTML: FileCode,
};

export default function KnowledgePage() {
  const { documents, addDocument, removeDocument, updateDocument } = useDocumentStore();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [ocrEnabled, setOcrEnabled] = useState(true);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    acceptedFiles.forEach(file => {
      const ext = file.name.split('.').pop()?.toUpperCase() || 'UNKNOWN';
      const sizeMB = file.size / (1024 * 1024);

      if (['XLS', 'XLSX'].includes(ext) && sizeMB > 10) {
        toast.error(`Excel 文件过大：${file.name}`);
        return;
      }
      if (sizeMB > 200) {
        toast.error(`文件超过 200MB 限制：${file.name}`);
        return;
      }

      const newDoc: Document = {
        id: `doc-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        name: file.name,
        type: ext,
        size: file.size,
        status: "UPLOADED",
        uploadTime: new Date().toISOString(),
      };

      addDocument(newDoc);
      toast.success(`${file.name} 上传成功`);

      // Mock Processing flow
      setTimeout(() => {
        updateDocument(newDoc.id, { status: "PARSING" });
        
        setTimeout(() => {
          updateDocument(newDoc.id, { status: "PARSED" });

          setTimeout(() => {
            updateDocument(newDoc.id, { status: "INDEXING", vectorProgress: 10, kgProgress: 20 });
            
            let p1 = 10, p2 = 20;
            const iv = setInterval(() => {
              p1 += Math.random() * 20;
              p2 += Math.random() * 20;
              if (p1 >= 100 && p2 >= 100) {
                clearInterval(iv);
                updateDocument(newDoc.id, { 
                  status: "READY", 
                  finishTime: new Date().toISOString(),
                  chunks: Math.floor(Math.random() * 50) + 10,
                  entities: Math.floor(Math.random() * 200) + 50
                });
                toast.success(`${newDoc.name} 已就绪`);
              } else {
                updateDocument(newDoc.id, { 
                  vectorProgress: Math.min(100, p1), 
                  kgProgress: Math.min(100, p2) 
                });
              }
            }, 800);
          }, 1500);
        }, 2000);
      }, 1000);
    });
  }, [addDocument, updateDocument]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({ 
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'application/msword': ['.doc'],
      'application/vnd.openxmlformats-officedocument.presentationml.presentation': ['.pptx'],
      'application/vnd.ms-powerpoint': ['.ppt'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/vnd.ms-excel': ['.xls'],
      'image/jpeg': ['.jpg', '.jpeg'],
      'image/png': ['.png'],
      'image/gif': ['.gif'],
      'image/webp': ['.webp'],
      'text/html': ['.html']
    }
  });

  const filteredDocs = documents.filter(d => d.name.toLowerCase().includes(search.toLowerCase()));
  const readyCount = documents.filter(d => d.status === "READY").length;
  const selectedDoc = documents.find(d => d.id === selectedDocId);

  const getProgress = (doc: Document) => {
    switch (doc.status) {
      case "UPLOADED": return 5;
      case "PARSING": return 30;
      case "PARSED": return 55;
      case "INDEXING": return 55 + ((doc.vectorProgress || 0) * 0.225) + ((doc.kgProgress || 0) * 0.225);
      case "READY": return 100;
      default: return 0;
    }
  };

  return (
    <div className="flex h-full size-full bg-[#0F1117]">
      {/* Sidebar - Document List */}
      <div className="w-[280px] flex-none border-r border-[#2D3148] flex flex-col bg-[#1A1D27]">
        <div className="p-4 border-b border-[#2D3148]">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#8B90AC]" />
            <input 
              type="text" 
              placeholder="搜索文档..." 
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-[#0F1117] border border-[#2D3148] rounded-md py-1.5 pl-9 pr-3 text-sm text-[#F0F2FF] placeholder:text-[#4A5070] focus:outline-none focus:border-[#7C6FE0] transition-colors"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-2 relative">
          {filteredDocs.map(doc => {
            const Icon = FILE_ICONS[doc.type] || FileText;
            return (
              <div 
                key={doc.id}
                onClick={() => setSelectedDocId(doc.id)}
                className={cn(
                  "p-3 rounded-lg cursor-pointer transition-colors border group",
                  selectedDocId === doc.id 
                    ? "bg-[#21253A] border-[#7C6FE0]" 
                    : "bg-[#0F1117] border-transparent hover:border-[#2D3148]"
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2 overflow-hidden flex-1">
                    <Icon className="w-4 h-4 text-[#8B90AC] shrink-0" />
                    <span className="text-sm truncate text-[#F0F2FF] font-medium" title={doc.name}>
                      {doc.name}
                    </span>
                  </div>
                  <button 
                    onClick={(e) => {
                      e.stopPropagation();
                      if (doc.status === "READY" || doc.status.includes("FAILED")) {
                        removeDocument(doc.id);
                        if (selectedDocId === doc.id) setSelectedDocId(null);
                        toast.success("已删除文档");
                      } else {
                        toast.error("处理中不可删除");
                      }
                    }}
                    className="opacity-0 group-hover:opacity-100 text-[#8B90AC] hover:text-red-400 transition-opacity p-1 -mr-1"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>

                <div className="mt-2 flex items-center justify-between">
                  <StatusBadge status={doc.status} />
                  <span className="text-[10px] text-[#4A5070]">
                    {format(new Date(doc.uploadTime), "MM-dd HH:mm")}
                  </span>
                </div>

                {!["READY", "PARSE_FAILED", "INDEX_FAILED"].includes(doc.status) && (
                  <div className="mt-3">
                    <ProgressBar progress={getProgress(doc)} status={doc.status} />
                    {doc.status === "INDEXING" && (
                      <div className="flex justify-between text-[10px] text-[#4A5070] mt-1">
                        <span>V: {doc.vectorProgress?.toFixed(0)}%</span>
                        <span>KG: {doc.kgProgress?.toFixed(0)}%</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
          
          {filteredDocs.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center text-[#4A5070] text-sm mt-20">
              <FileText className="w-8 h-8 mb-2 opacity-50" />
              <p>暂无文档</p>
            </div>
          )}
        </div>

        <div className="p-3 border-t border-[#2D3148] text-xs text-[#8B90AC] flex justify-between">
          <span>共 {documents.length} 个文档</span>
          <span className="text-emerald-400">{readyCount} 个就绪</span>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0 p-6 bg-[#0F1117] overflow-y-auto">
        <div className="max-w-4xl mx-auto w-full space-y-6">
          
          {/* Upload Zone */}
          <div 
            {...getRootProps()} 
            className={cn(
              "h-44 border-2 border-dashed rounded-xl flex flex-col items-center justify-center p-6 text-center cursor-pointer transition-all bg-[#1A1D27]",
              isDragActive 
                ? "border-[#7C6FE0] bg-[#21253A]" 
                : "border-[#2D3148] hover:border-[#4A5070]"
            )}
          >
            <input {...getInputProps()} />
            <div className="w-12 h-12 rounded-full bg-[#21253A] flex items-center justify-center mb-4 text-[#8B90AC]">
              {isDragActive ? <CheckCircle className="w-6 h-6 text-[#7C6FE0]" /> : <FileText className="w-6 h-6" />}
            </div>
            <h3 className="text-[#F0F2FF] font-medium mb-1">
              {isDragActive ? "↓ 释放以上传文件" : "拖拽文件到此处，或点击选择文件"}
            </h3>
            <p className="text-[#8B90AC] text-xs mb-4">
              支持：PDF · Word · PPT · Excel · 图片 · HTML <br/> 最大 200MB（Excel 最大 10MB）
            </p>
            <div className="flex items-center gap-4 text-sm" onClick={e => e.stopPropagation()}>
              <label className="flex items-center gap-2 text-[#8B90AC] cursor-pointer">
                <input 
                  type="checkbox" 
                  checked={ocrEnabled} 
                  onChange={e => setOcrEnabled(e.target.checked)}
                  className="rounded border-[#2D3148] bg-[#0F1117] text-[#7C6FE0] focus:ring-[#7C6FE0] focus:ring-offset-[#1A1D27]"
                />
                启用 OCR（扫描件建议开启）
              </label>
              <button 
                onClick={() => {
                  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
                  input?.click();
                }}
                className="bg-[#7C6FE0] hover:bg-[#A598F0] text-white px-4 py-1.5 rounded-md font-medium transition-colors"
              >
                上传并解析
              </button>
            </div>
          </div>

          {/* Document Detail Card */}
          {selectedDoc && (
            <div className="bg-[#1A1D27] rounded-xl border border-[#2D3148] p-6 shadow-sm animate-in fade-in slide-in-from-bottom-4 duration-300">
              <div className="flex items-start justify-between mb-6 pb-6 border-b border-[#2D3148]">
                <div>
                  <div className="flex items-center gap-3 mb-2">
                    {FILE_ICONS[selectedDoc.type] ? React.createElement(FILE_ICONS[selectedDoc.type], { className: "w-6 h-6 text-[#8B90AC]" }) : <FileText className="w-6 h-6 text-[#8B90AC]" />}
                    <h2 className="text-xl font-bold text-[#F0F2FF]">{selectedDoc.name}</h2>
                  </div>
                  <div className="flex gap-4 text-sm text-[#8B90AC]">
                    <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> {format(new Date(selectedDoc.uploadTime), "yyyy-MM-dd HH:mm:ss")}</span>
                    <span>{(selectedDoc.size / (1024 * 1024)).toFixed(2)} MB</span>
                    <span>{selectedDoc.type} (Precision API)</span>
                  </div>
                </div>
                <div className="flex gap-3">
                  <button 
                    onClick={() => {
                      if (selectedDoc.status === "READY" || selectedDoc.status.includes("FAILED")) {
                        removeDocument(selectedDoc.id);
                        setSelectedDocId(null);
                        toast.success("已删除文档");
                      } else {
                        toast.error("处理中不可删除");
                      }
                    }}
                    className="px-3 py-1.5 text-sm text-red-400 bg-red-400/10 hover:bg-red-400/20 rounded-md transition-colors font-medium border border-red-400/20"
                  >
                    删除文档
                  </button>
                  <button 
                    onClick={() => {
                      if (selectedDoc.status === "READY") {
                        useDocumentStore.setState({ selectedDocIds: [selectedDoc.id] });
                        navigate("/chat");
                      } else {
                        toast.error("文档未就绪，请等待完成");
                      }
                    }}
                    disabled={selectedDoc.status !== "READY"}
                    className="px-4 py-1.5 text-sm bg-[#7C6FE0] text-white rounded-md hover:bg-[#A598F0] transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed shadow-[0_0_15px_rgba(124,111,224,0.3)] disabled:shadow-none flex items-center gap-1"
                  >
                    开始提问 →
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-8">
                {/* Vector Index Info */}
                <div>
                  <h3 className="text-sm font-semibold text-[#8B90AC] mb-4 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span>向量检索与切分</span>
                      <div className="flex-1 h-px bg-[#2D3148] w-12"></div>
                    </div>
                    {selectedDoc.status === "READY" && (
                      <button 
                        onClick={() => navigate("/vector")}
                        className="text-xs text-[#7C6FE0] hover:text-[#A598F0] transition-colors flex items-center gap-1"
                      >
                        前往测试与可视化 →
                      </button>
                    )}
                  </h3>
                  <div className="space-y-4">
                    <div className="flex justify-between items-center text-sm">
                      <span className="text-[#4A5070]">状态</span>
                      {selectedDoc.status === "READY" ? (
                        <span className="text-emerald-400 flex items-center gap-1"><Check className="w-4 h-4"/> 完成</span>
                      ) : selectedDoc.status.includes("FAILED") ? (
                        <span className="text-red-400 flex items-center gap-1"><X className="w-4 h-4"/> 失败</span>
                      ) : (
                        <span className="text-yellow-400 flex items-center gap-1">构建中 ({selectedDoc.vectorProgress?.toFixed(0)}%)</span>
                      )}
                    </div>
                    <div className="flex justify-between items-center text-sm">
                      <span className="text-[#4A5070]">切分块数</span>
                      <span className="text-[#F0F2FF] font-mono">{selectedDoc.chunks || '-'} 个</span>
                    </div>
                  </div>
                </div>

                {/* KG Info */}
                <div>
                  <h3 className="text-sm font-semibold text-[#8B90AC] mb-4 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span>知识图谱</span>
                      <div className="flex-1 h-px bg-[#2D3148] w-12"></div>
                    </div>
                    {selectedDoc.status === "READY" && (
                      <button 
                        onClick={() => navigate("/kg")}
                        className="text-xs text-[#7C6FE0] hover:text-[#A598F0] transition-colors flex items-center gap-1"
                      >
                        前往测试与可视化 →
                      </button>
                    )}
                  </h3>
                  <div className="space-y-4">
                    <div className="flex justify-between items-center text-sm">
                      <span className="text-[#4A5070]">状态</span>
                      {selectedDoc.status === "READY" ? (
                        <span className="text-emerald-400 flex items-center gap-1"><Check className="w-4 h-4"/> 完成</span>
                      ) : selectedDoc.status.includes("FAILED") ? (
                        <span className="text-red-400 flex items-center gap-1"><X className="w-4 h-4"/> 失败</span>
                      ) : (
                        <span className="text-yellow-400 flex items-center gap-1">构建中 ({selectedDoc.kgProgress?.toFixed(0)}%)</span>
                      )}
                    </div>
                    <div className="flex justify-between items-center text-sm">
                      <span className="text-[#4A5070]">实体数</span>
                      <span className="text-[#F0F2FF] font-mono">{selectedDoc.entities || '-'} 个</span>
                    </div>
                  </div>
                </div>
              </div>
              
              {selectedDoc.status.includes("FAILED") && (
                <div className="mt-6 p-3 bg-red-400/10 border border-red-400/20 rounded text-red-400 text-sm">
                  失败原因：{selectedDoc.errorMsg || "未知错误，请重试"}
                </div>
              )}
            </div>
          )}
          
          {!selectedDoc && documents.length > 0 && (
            <div className="text-center text-[#4A5070] py-20">
              <p>从左侧选择文档查看详情，或上传新文档</p>
            </div>
          )}
          
          {documents.length === 0 && (
            <div className="bg-[#1A1D27] border border-[#2D3148] rounded-xl p-10 text-center flex flex-col items-center justify-center">
              <div className="w-16 h-16 rounded-full bg-[#21253A] flex items-center justify-center mb-4 border border-[#2D3148] shadow-[0_0_20px_rgba(124,111,224,0.1)]">
                <BrainCircuit className="w-8 h-8 text-[#7C6FE0]" />
              </div>
              <h2 className="text-xl font-bold text-[#F0F2FF] mb-2">开始构建你的知识库</h2>
              <p className="text-[#8B90AC] mb-6 max-w-md">
                上传 PDF、Word、Excel 等格式的文档，系统将自动解析并构建双引擎驱动的 AI 可检索知识库。
              </p>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
