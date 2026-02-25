import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tsconfigPaths from "vite-tsconfig-paths";
import { visualizer } from "rollup-plugin-visualizer";

import { tanstackRouter } from "@tanstack/router-plugin/vite";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    tanstackRouter(),
    react(),
    tsconfigPaths(),
    visualizer({
      template: "treemap", // or 'sunburst'
      open: true,
      gzipSize: true,
      brotliSize: true,
      filename: "bundle-analysis.html",
    }),
  ],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:5000",
        changeOrigin: true,
        // rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules")) {
            // 1. Keep the absolute heavyweights in their own dedicated files
            if (id.includes("recharts") || id.includes("react-dom") || id.includes("jszip")) {
              return "vendor-large";
            }
            // 2. Group all other smaller dependencies into a single 'vendor-small' chunk
            // This avoids having 50 files that are only 1-2kb
            return "vendor-others";
          }
        },
      },
    },
  },
});
