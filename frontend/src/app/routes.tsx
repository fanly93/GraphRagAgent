import { createBrowserRouter, Navigate } from "react-router";
import Layout from "./pages/Layout";
import KnowledgePage from "./pages/KnowledgePage";
import ChatPage from "./pages/ChatPage";
import SystemPage from "./pages/SystemPage";
import KGBrowsePage from "./pages/KGBrowsePage";
import KGSearchPage from "./pages/KGSearchPage";
import KGVisualizerPage from "./pages/KGVisualizerPage";
import VectorVisualizerPage from "./pages/VectorVisualizerPage";

export const router = createBrowserRouter([
  {
    path: "/",
    Component: Layout,
    children: [
      { index: true, element: <Navigate to="/knowledge" replace /> },
      { path: "knowledge", Component: KnowledgePage },
      { path: "kg", Component: KGVisualizerPage },
      { path: "vector", Component: VectorVisualizerPage },
      { path: "chat", Component: ChatPage },
      { path: "system", Component: SystemPage },
      { path: "*", element: <Navigate to="/knowledge" replace /> }
    ]
  }
]);
