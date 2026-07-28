import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  // Electron 渲染进程通过 http://localhost:5173 加载，base 用相对路径
  base: "./",
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    // manualChunks 拆包：把第三方依赖单独切分，提升缓存命中率 + 减少首屏 JS 体积
    // react-vendor: react/react-dom（变更极少，长期缓存）
    // virtual: react-window（虚拟列表库，按需加载）
    // 注：state chunk（react-query）已删除 — 全代码无 useQuery 调用，依赖已从 package.json 移除
    rollupOptions: {
      output: {
        manualChunks: {
          "react-vendor": ["react", "react-dom"],
          virtual: ["react-window"],
        },
      },
    },
  },
});
