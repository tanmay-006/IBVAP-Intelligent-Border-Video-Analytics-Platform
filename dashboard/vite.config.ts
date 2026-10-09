import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev: the dashboard runs on Vite and forwards API calls to ibvap-core.
// Build: ibvap-core serves the built files under /ui/ (same origin as the API).
const API = process.env.IBVAP_API ?? "http://127.0.0.1:8000";
const apiPaths = ["/events", "/alerts", "/cameras", "/health", "/metrics", "/media"];

export default defineConfig(({ command }) => ({
  base: command === "build" ? "/ui/" : "/",
  plugins: [react()],
  build: { chunkSizeWarningLimit: 1600 }, // maplibre-gl alone is ~1 MB
  server: {
    port: 5173,
    proxy: {
      ...Object.fromEntries(apiPaths.map((p) => [p, { target: API, changeOrigin: true }])),
      "/ws": { target: API.replace(/^http/, "ws"), ws: true },
    },
  },
}));
