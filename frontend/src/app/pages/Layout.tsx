import { NavLink, Outlet, useNavigate } from "react-router";
import { useDocumentStore } from "../store";
import { Activity, BrainCircuit, Database } from "lucide-react";
import { cn } from "../components/ui";

export default function Layout() {
  const navigate = useNavigate();
  const documents = useDocumentStore(state => state.documents);
  const readyCount = documents.filter(d => d.status === "READY").length;
  
  return (
    <div className="flex flex-col h-full w-full bg-[#0F1117] text-[#F0F2FF]">
      {/* Header */}
      <header className="h-16 flex-none border-b border-[#2D3148] bg-[#1A1D27] px-6 flex items-center justify-between z-10">
        {/* Left: Logo */}
        <div className="flex items-center gap-2 w-60">
          <BrainCircuit className="text-[#7C6FE0] w-6 h-6" />
          <span className="font-bold text-lg tracking-tight">GraphRAG Agent</span>
        </div>

        {/* Center: Tabs */}
        <nav className="flex-1 flex justify-center gap-8">
          <NavLink 
            to="/knowledge"
            className={({ isActive }) => cn(
              "px-4 py-4 text-sm font-medium border-b-2 transition-colors relative top-[1px]",
              isActive 
                ? "border-[#7C6FE0] text-[#7C6FE0]" 
                : "border-transparent text-[#8B90AC] hover:text-[#F0F2FF]"
            )}
          >
            知识库
          </NavLink>
          <NavLink 
            to="/kg"
            className={({ isActive }) => cn(
              "px-4 py-4 text-sm font-medium border-b-2 transition-colors relative top-[1px]",
              isActive 
                ? "border-[#7C6FE0] text-[#7C6FE0]" 
                : "border-transparent text-[#8B90AC] hover:text-[#F0F2FF]"
            )}
          >
            图谱检索可视化
          </NavLink>
          <NavLink 
            to="/vector"
            className={({ isActive }) => cn(
              "px-4 py-4 text-sm font-medium border-b-2 transition-colors relative top-[1px]",
              isActive 
                ? "border-[#7C6FE0] text-[#7C6FE0]" 
                : "border-transparent text-[#8B90AC] hover:text-[#F0F2FF]"
            )}
          >
            向量检索及可视化
          </NavLink>
          <NavLink 
            to="/chat"
            className={({ isActive }) => cn(
              "px-4 py-4 text-sm font-medium border-b-2 transition-colors relative top-[1px]",
              isActive 
                ? "border-[#7C6FE0] text-[#7C6FE0]" 
                : "border-transparent text-[#8B90AC] hover:text-[#F0F2FF]"
            )}
          >
            问答
          </NavLink>
        </nav>

        {/* Right: Status */}
        <div 
          className="flex items-center gap-3 w-60 justify-end cursor-pointer group"
          onClick={() => navigate("/system")}
        >
          <div className="flex items-center gap-1.5 text-sm text-[#8B90AC] group-hover:text-white transition-colors">
            <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]"></span>
            <span>系统正常</span>
            <span className="px-1.5 py-0.5 rounded bg-[#2D3148] text-xs ml-2">
              {readyCount}/{documents.length} 就绪
            </span>
          </div>
          <Activity className="w-4 h-4 text-[#8B90AC] group-hover:text-white" />
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 overflow-hidden relative">
        <Outlet />
      </main>
    </div>
  );
}
