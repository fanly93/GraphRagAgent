import { RouterProvider } from "react-router";
import { router } from "./routes";
import { Toaster } from "sonner";

export default function App() {
  return (
    <div className="h-screen w-full bg-[#0F1117] text-[#F0F2FF] font-sans selection:bg-[#7C6FE0]/30 overflow-hidden flex flex-col">
      <RouterProvider router={router} />
      <Toaster
        theme="dark"
        position="top-center"
        toastOptions={{
          style: {
            background: "#1A1D27",
            border: "1px solid #2D3148",
            color: "#F0F2FF",
          },
        }}
      />
    </div>
  );
}