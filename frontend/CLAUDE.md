# Frontend（Vite + React）

## 启动

```bash
cd frontend
npm install   # 首次或依赖变更后
npm run dev   # 开发服
```

默认开发地址：**http://localhost:5173/**（Vite 默认端口；若被占用会在终端提示新端口）

生产构建：`npm run build`，产物在 `frontend/dist/`。

## 入口与路径

| 说明 | 路径 |
|------|------|
| 应用入口 | `src/main.tsx` |
| 路由定义 | `src/app/routes.tsx` |
| 源码别名 | `@/` → `src/`（见 `vite.config.ts`） |

**主要页面路由**（根路径 `/` 会重定向到 `/knowledge`）：

| URL | 页面 |
|-----|------|
| `/knowledge` | 知识库 |
| `/kg` | 知识图谱可视化 |
| `/vector` | 向量可视化 |
| `/chat` | 对话 |
| `/system` | 系统 |

## 技术栈（摘要）

React 18、Vite 6、Tailwind CSS 4、`react-router` 7。
