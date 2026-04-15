import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tsconfigPaths from "vite-tsconfig-paths";
import { visualizer } from "rollup-plugin-visualizer";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import path from "path";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  return {
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
        "^/api($|/)": {
          target: "http://localhost:5000",
          changeOrigin: true,
        },
        "^/s3($|/)": {
          target: getS3Host(mode),
          changeOrigin: true,
        },
      },
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes("node_modules")) {
              // Keep lazily-imported heavy parsers out of vendor chunks so they stay as separate lazy chunks
              if (id.includes("pdfjs-dist") || id.includes("mammoth") || id.includes("xlsx")) return undefined;
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
  };
});

// Get S3 host from .env in monorepo root. Only needed in development.
// In production the /s3 route is handled by Caddy
function getS3Host(mode: string) {
  const rootEnvPath = path.resolve(__dirname, "../");
  const env = loadEnv(mode, rootEnvPath, "");
  return env.AMCAT4_S3_HOST;
}
