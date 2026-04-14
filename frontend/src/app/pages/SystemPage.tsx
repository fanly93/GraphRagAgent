import { useEffect, useState, useCallback } from "react";
import {
  Database, Search, Box, RefreshCw, Server, Activity,
  Check, AlertTriangle, BrainCircuit, Loader2,
} from "lucide-react";
import { cn } from "../components/ui";
import { healthApi, BackendHealthResponse } from "../api/health";
import { documentsApi, BackendDocumentListItem } from "../api/documents";
import { format } from "date-fns";

const COMPONENT_META: Record<string, { label: string; Icon: React.ElementType }> = {
  database:    { label: "数据库",   Icon: Database },
  chroma_db:   { label: "向量库",   Icon: Search },
  kg_jsonl:    { label: "KG 文件",  Icon: Box },
  mineru_api:  { label: "MinerU",   Icon: Server },
  agentic_rag: { label: "RAG 引擎", Icon: BrainCircuit },
};

const STATUS_COLORS: Record<string, string> = {
  ok: "text-emerald-400", warning: "text-yellow-400", error: "text-red-400",
};
const STATUS_BG: Record<string, string> = {
  ok: "bg-emerald-400/10 border-emerald-400/20",
  warning: "bg-yellow-400/10 border-yellow-400/20",
  error: "bg-red-400/10 border-red-400/20",
};
const STATUS_LABEL: Record<string, string> = {
  ok: "正常", warning: "警告", error: "异常",
};
const DOT_COLOR: Record<string, string> = {
  ok: "bg-emerald-400 shadow-[0_0_5px_rgba(52,211,153,0.5)]",
  warning: "bg-yellow-400",
  error: "bg-red-400",
};

const REFRESH_INTERVAL = 30_000;

export default function SystemPage() {
  const [health, setHealth] = useState<BackendHealthResponse | null>(null);
  const [recentDocs, setRecentDocs] = useState<BackendDocumentListItem[]>([]);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [loadingHealth, setLoadingHealth] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [secondsAgo, setSecondsAgo] = useState(0);

  const fetchAll = useCallback(async () => {
    setLoadingHealth(true);
    setErrorMsg(null);
    try {
      const [h, docs] = await Promise.all([
        healthApi.check(),
        documentsApi.list({ limit: 20 }),
      ]);
      setHealth(h);
      const sorted = [...docs.documents].sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
      setRecentDocs(sorted.slice(0, 5));
      setLastUpdated(new Date());
      setSecondsAgo(0);
    } catch {
      setErrorMsg("无法连接后端服务，请确认服务是否已启动（http://localhost:8000）");
    } finally {
      setLoadingHealth(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  useEffect(() => {
    const interval = setInterval(fetchAll, REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchAll]);

  useEffect(() => {
    if (!lastUpdated) return;
    const t = setInterval(() => {
      setSecondsAgo(Math.floor((Date.now() - lastUpdated.getTime()) / 1000));
    }, 1000);
    return () => clearInterval(t);
  }, [lastUpdated]);

  const stats = health?.document_stats;
  const total = stats?.total ?? 0;
  const ready = stats?.ready ?? 0;
  const processing = (stats?.indexing ?? 0) + (stats?.parsing ?? 0);
  const failed = stats?.failed ?? 0;
  const pct = (n: number) => (total > 0 ? ((n / total) * 100).toFixed(0) : "0");

  return (
    <div className="flex h-full size-full bg-[#0F1117] overflow-y-auto">
      <div className="max-w-4xl w-full mx-auto p-6 space-y-8">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3 text-xl font-bold text-[#F0F2FF]">
            <Activity className="w-6 h-6 text-emerald-400" />
            系统健康状态
          </div>
          <div className="flex items-center gap-3">
            {loadingHealth && <Loader2 className="w-4 h-4 animate-spin text-[#7C6FE0]" />}
            <button
              onClick={fetchAll}
              disabled={loadingHealth}
              className="flex items-center gap-2 text-sm text-[#8B90AC] hover:text-[#F0F2FF] transition-colors disabled:opacity-50"
            >
              <RefreshCw className="w-4 h-4" />
              {lastUpdated ? `${secondsAgo}s 前更新` : "加载中..."}
            </button>
          </div>
        </div>

        {/* Error Banner */}
        {errorMsg && (
          <div className="flex items-center gap-3 p-4 bg-red-400/10 border border-red-400/20 rounded-xl text-red-400 text-sm">
            <AlertTriangle className="w-5 h-5 shrink-0" />
            {errorMsg}
          </div>
        )}

        {/* Component Cards */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {Object.entries(COMPONENT_META).map(([key, { label, Icon }]) => {
            const status = health?.components?.[key as keyof BackendHealthResponse["components"]] ?? "—";
            const color = STATUS_COLORS[status] ?? "text-[#8B90AC]";
            const bg = STATUS_BG[status] ?? "bg-[#2D3148]/40 border-[#2D3148]";
            const dot = DOT_COLOR[status] ?? "bg-[#4A5070]";
            return (
              <div key={key} className="bg-[#1A1D27] border border-[#2D3148] rounded-xl p-5 flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <Icon className="w-5 h-5 text-[#8B90AC]" />
                  <div className={cn(
                    "flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded border",
                    color, bg
                  )}>
                    <span className={cn("w-1.5 h-1.5 rounded-full", dot)} />
                    {STATUS_LABEL[status] ?? status}
                  </div>
                </div>
                <span className="font-semibold text-[#F0F2FF] text-sm">{label}</span>
              </div>
            );
          })}
        </div>

        <div className="grid md:grid-cols-2 gap-8">
          {/* Document Stats */}
          <div className="bg-[#1A1D27] border border-[#2D3148] rounded-xl p-6">
            <h3 className="font-semibold text-[#8B90AC] mb-6 flex items-center gap-2">
              <span>文档统计</span>
              <div className="flex-1 h-px bg-[#2D3148]" />
            </h3>
            <div className="flex items-baseline gap-2 mb-8">
              <span className="text-4xl font-bold text-[#F0F2FF]">{total}</span>
              <span className="text-[#8B90AC] text-sm">个文档</span>
            </div>
            <div className="space-y-4">
              <StatBar
                icon={<Check className="w-4 h-4" />}
                label={`${ready} 个就绪`}
                color="bg-emerald-400"
                textColor="text-emerald-400"
                pct={Number(pct(ready))}
              />
              <StatBar
                icon={<RefreshCw className="w-4 h-4" />}
                label={`${processing} 个处理中`}
                color="bg-blue-400"
                textColor="text-blue-400"
                pct={Number(pct(processing))}
              />
              <StatBar
                icon={<AlertTriangle className="w-4 h-4" />}
                label={`${failed} 个失败`}
                color="bg-red-400"
                textColor="text-red-400"
                pct={Number(pct(failed))}
              />
            </div>
          </div>

          {/* Recent Docs */}
          <div className="bg-[#1A1D27] border border-[#2D3148] rounded-xl p-6">
            <h3 className="font-semibold text-[#8B90AC] mb-6 flex items-center gap-2">
              <span>近期文档</span>
              <div className="flex-1 h-px bg-[#2D3148]" />
            </h3>
            {recentDocs.length === 0 ? (
              <div className="text-sm text-[#4A5070] py-4 text-center">暂无文档记录</div>
            ) : (
              <div className="space-y-3">
                {recentDocs.map((doc) => {
                  const isOk = doc.status === "READY";
                  const isFailed = doc.status.includes("FAILED");
                  const dotCls = isOk
                    ? "bg-emerald-400"
                    : isFailed
                    ? "bg-red-400"
                    : "bg-yellow-400 animate-pulse";
                  return (
                    <div key={doc.doc_id} className="flex items-center gap-3 text-sm">
                      <span className={cn("w-2 h-2 rounded-full shrink-0", dotCls)} />
                      <div className="flex-1 min-w-0">
                        <span className="text-[#F0F2FF] truncate block" title={doc.filename}>
                          {doc.filename}
                        </span>
                        <span className="text-[10px] text-[#4A5070]">
                          {doc.status}
                          {doc.chunk_count != null && ` · ${doc.chunk_count} chunks`}
                          {doc.entity_count != null && ` · ${doc.entity_count} 实体`}
                        </span>
                      </div>
                      <span className="text-[10px] text-[#4A5070] shrink-0">
                        {format(new Date(doc.created_at), "MM-dd HH:mm")}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {health?.timestamp && (
          <p className="text-xs text-[#4A5070] text-center">
            后端服务时间：{health.timestamp}
          </p>
        )}
      </div>
    </div>
  );
}

function StatBar({
  icon, label, color, textColor, pct,
}: {
  icon: React.ReactNode;
  label: string;
  color: string;
  textColor: string;
  pct: number;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-sm">
        <span className={cn("flex items-center gap-1.5", textColor)}>
          {icon} {label}
        </span>
        <span className="text-[#8B90AC]">{pct}%</span>
      </div>
      <div className="w-full h-2 bg-[#0F1117] rounded-full overflow-hidden">
        <div
          className={cn("h-full transition-all duration-500", color)}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
