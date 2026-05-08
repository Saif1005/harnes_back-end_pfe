import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  build: {
    target: "es2020",
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks(id: string): string | undefined {
          if (!id.includes("node_modules")) return undefined;
          if (id.includes("recharts")) return "charts";
          if (id.includes("lucide-react")) return "icons";
          if (id.includes("react-dom") || id.includes("react-router")) return "react-vendor";
          return "vendor";
        },
      },
    },
    chunkSizeWarningLimit: 900,
  },
  server: {
    port: 5173,
    proxy: {
      "/harness-proxy": {
        target: process.env.VITE_HARNESS_DEV_TARGET || "http://127.0.0.1:8030",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/harness-proxy/, ""),
      },
    },
  },
});
