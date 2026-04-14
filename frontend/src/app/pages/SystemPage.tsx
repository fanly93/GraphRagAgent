import React, { useEffect, useState } from "react";
import { Database, Search, Box, RefreshCw, Server, Activity, Check, X, AlertTriangle } from "lucide-react";
import { useDocumentStore } from "../store";
import { cn } from "../components/ui";
import { format } from "date-fns";

const COMPONENTS = [
  { id: "database", name: "数据库", icon: Database, status: "ok" },
  { id: "chroma_db", name: "向量库", icon: Search, status: "ok" },
  { id: "kg_jsonl", name: "KG文件", icon: Box, status: "ok" },
  { id: "mineru_api", name: "MinerU", icon: Server, status: "ok" },
];

const LOGS = [
  { time: new Date(Date.now() - 1000 * 60 * 5), action: "销售数据.xlsx → INDEXING (进行中)" },
  { time: new Date(Date.now() - 1000 * 60 * 15), action: "技术报告.pdf → READY (耗时 12m 45s)" },
  { time: new Date(Date.now() - 1000 * 60 * 45), action: "图1.jpg → PARSE_FAILED (MinerU 超时)" },
];

export default function SystemPage() {
  const { documents } = useDocumentStore();
  const [lastUpdate, setLastUpdate] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setLastUpdate((prev) => prev + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const total = documents.length;
  const ready = documents.filter((d) => d.status === "READY").length;
  const processing = documents.filter((d) => !["READY", "PARSE_FAILED", "INDEX_FAILED"].includes(d.status)).length;
  const failed = documents.filter((d) => d.status.includes("FAILED")).length;

  const readyPct = total > 0 ? (ready / total) * 100 : 0;
  const processingPct = total > 0 ? (processing / total) * 100 : 0;
  const failedPct = total > 0 ? (failed / total) * 100 : 0;

  return (
    <div className="flex h-full size-full bg-[#0F1117] overflow-y-auto">
      <div className="max-w-4xl w-full mx-auto p-6 space-y-8">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3 text-xl font-bold text-[#F0F2FF]">
            <Activity className="w-6 h-6 text-emerald-400" />
            系统健康状态
          </div>
          <div className="flex items-center gap-2 text-sm text-[#8B90AC]">
            <RefreshCw className={cn("w-4 h-4", lastUpdate % 30 === 0 && "animate-spin text-[#7C6FE0]")} />
            最后更新：{lastUpdate % 30}s 前
          </div>
        </div>

        {/* Components */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {COMPONENTS.map((comp) => (
            <div key={comp.id} className="bg-[#1A1D27] border border-[#2D3148] rounded-xl p-5 flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <comp.icon className="w-5 h-5 text-[#8B90AC]" />
                <div className="flex items-center gap-1.5 text-xs font-medium text-emerald-400 bg-emerald-400/10 px-2 py-0.5 rounded border border-emerald-400/20">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_5px_rgba(52,211,153,0.5)]"></span>
                  正常
                </div>
              </div>
              <span className="font-semibold text-[#F0F2FF]">{comp.name}</span>
            </div>
          ))}
        </div>

        <div className="grid md:grid-cols-2 gap-8">
          {/* Stats */}
          <div className="bg-[#1A1D27] border border-[#2D3148] rounded-xl p-6">
            <h3 className="font-semibold text-[#8B90AC] mb-6 flex items-center gap-2">
              <span>文档统计</span>
              <div className="flex-1 h-px bg-[#2D3148]"></div>
            </h3>
            
            <div className="flex items-baseline gap-2 mb-8">
              <span className="text-4xl font-bold text-[#F0F2FF]">{total}</span>
              <span className="text-[#8B90AC] text-sm">个文档</span>
            </div>

            <div className="space-y-4">
              <div className="space-y-1.5">
                <div className="flex justify-between text-sm">
                  <span className="flex items-center gap-1.5 text-emerald-400"><Check className="w-4 h-4" /> {ready} 个就绪</span>
                  <span className="text-[#8B90AC]">{readyPct.toFixed(0)}%</span>
                </div>
                <div className="w-full h-2 bg-[#0F1117] rounded-full overflow-hidden">
                  <div className="h-full bg-emerald-400" style={{ width: `${readyPct}%` }}></div>
                </div>
              </div>
              
              <div className="space-y-1.5">
                <div className="flex justify-between text-sm">
                  <span className="flex items-center gap-1.5 text-blue-400"><RefreshCw className="w-4 h-4" /> {processing} 个处理中</span>
                  <span className="text-[#8B90AC]">{processingPct.toFixed(0)}%</span>
                </div>
                <div className="w-full h-2 bg-[#0F1117] rounded-full overflow-hidden">
                  <div className="h-full bg-blue-400" style={{ width: `${processingPct}%` }}></div>
                </div>
              </div>

              <div className="space-y-1.5">
                <div className="flex justify-between text-sm">
                  <span className="flex items-center gap-1.5 text-red-400"><AlertTriangle className="w-4 h-4" /> {failed} 个失败</span>
                  <span className="text-[#8B90AC]">{failedPct.toFixed(0)}%</span>
                </div>
                <div className="w-full h-2 bg-[#0F1117] rounded-full overflow-hidden">
                  <div className="h-full bg-red-400" style={{ width: `${failedPct}%` }}></div>
                </div>
              </div>
            </div>
          </div>

          {/* Activity Log */}
          <div className="bg-[#1A1D27] border border-[#2D3148] rounded-xl p-6">
            <h3 className="font-semibold text-[#8B90AC] mb-6 flex items-center gap-2">
              <span>近期活动</span>
              <div className="flex-1 h-px bg-[#2D3148]"></div>
            </h3>

            <div className="space-y-0 relative before:absolute before:inset-0 before:ml-[11px] before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-[#2D3148] before:to-transparent">
              {LOGS.map((log, idx) => (
                <div key={idx} className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
                  <div className="flex items-center justify-center w-6 h-6 rounded-full border border-[#2D3148] bg-[#0F1117] text-[#8B90AC] group-[.is-active]:text-emerald-400 group-[.is-active]:border-emerald-400 shadow shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 z-10">
                    <div className="w-1.5 h-1.5 rounded-full bg-current"></div>
                  </div>
                  <div className="w-[calc(100%-2.5rem)] md:w-[calc(50%-1.5rem)] p-3 rounded bg-[#0F1117] border border-[#2D3148] shadow">
                    <div className="flex items-center justify-between mb-1">
                      <div className="font-bold text-[#F0F2FF] text-xs">System</div>
                      <time className="font-mono text-xs text-[#8B90AC]">{format(log.time, "HH:mm")}</time>
                    </div>
                    <div className="text-[#8B90AC] text-xs">
                      {log.action}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
