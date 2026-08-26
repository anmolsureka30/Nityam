import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies the WebSocket to uvicorn so the browser sees a single
// origin. In production the FastAPI app serves dist/ and there is no proxy.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/ws": { target: "ws://localhost:8000", ws: true },
      "/health": { target: "http://localhost:8000" },
    },
  },
});
