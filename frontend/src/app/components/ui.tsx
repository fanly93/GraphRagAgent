import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import * as React from "react";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// Simple Toast wrapper around Sonner
export { Toaster, toast } from "sonner";

export const StatusBadge = ({ 
  status, 
  className 
}: { 
  status: string, 
  className?: string 
}) => {
  let colorClass = "";
  let icon = "";
  let text = "";
  let glow = false;
  let rotate = false;

  switch (status) {
    case "UPLOADED":
      colorClass = "bg-blue-500/10 text-blue-400 border border-blue-500/20";
      icon = "↑";
      text = "已上传";
      break;
    case "PARSING":
      colorClass = "bg-blue-500/10 text-blue-400 border border-blue-500/20";
      icon = "⟳";
      text = "解析中...";
      rotate = true;
      break;
    case "PARSED":
      colorClass = "bg-yellow-500/10 text-yellow-400 border border-yellow-500/20";
      icon = "⟳";
      text = "准备建索引";
      rotate = true;
      break;
    case "INDEXING":
      colorClass = "bg-yellow-500/10 text-yellow-400 border border-yellow-500/20";
      icon = "⟳";
      text = "索引构建中";
      rotate = true;
      break;
    case "READY":
      colorClass = "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 shadow-[0_0_10px_rgba(52,211,153,0.2)]";
      icon = "●";
      text = "就绪";
      glow = true;
      break;
    case "PARSE_FAILED":
      colorClass = "bg-red-500/10 text-red-400 border border-red-500/20";
      icon = "⊗";
      text = "解析失败";
      break;
    case "INDEX_FAILED":
      colorClass = "bg-red-500/10 text-red-400 border border-red-500/20";
      icon = "⊗";
      text = "索引失败";
      break;
    default:
      colorClass = "bg-gray-500/10 text-gray-400";
      text = status;
  }

  return (
    <div className={cn("inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium", colorClass, className)}>
      <span className={cn(rotate && "animate-spin")}>{icon}</span>
      <span>{text}</span>
    </div>
  );
};

export const RouteTag = ({ route, className }: { route: string, className?: string }) => {
  let colorClass = "";
  let text = "";

  switch (route) {
    case "entity_query":
      colorClass = "bg-[#7C6FE0]/20 text-[#7C6FE0]";
      text = "实体查询";
      break;
    case "semantic_query":
      colorClass = "bg-blue-500/20 text-blue-400";
      text = "语义查询";
      break;
    case "hybrid_query":
      colorClass = "bg-gradient-to-r from-[#7C6FE0]/20 to-blue-500/20 text-white";
      text = "混合检索";
      break;
    case "direct_answer":
      colorClass = "bg-gray-500/20 text-gray-400";
      text = "直接回答";
      break;
    default:
      text = route;
      colorClass = "bg-gray-500/20 text-gray-400";
  }

  return (
    <span className={cn("inline-flex items-center px-2 py-0.5 rounded text-xs font-medium", colorClass, className)}>
      {text}
    </span>
  );
};

export const ProgressBar = ({ progress, status, className }: { progress: number, status?: string, className?: string }) => {
  let colorClass = "bg-[#7C6FE0]";
  if (status === "READY") colorClass = "bg-emerald-400";
  if (status?.includes("FAILED")) colorClass = "bg-red-400";
  
  return (
    <div className={cn("w-full h-1.5 bg-[#2D3148] rounded-full overflow-hidden", className)}>
      <div 
        className={cn("h-full transition-all duration-300 ease-out", colorClass)} 
        style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
      />
    </div>
  );
};
