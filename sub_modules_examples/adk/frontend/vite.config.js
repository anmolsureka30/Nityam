import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Ports live in exactly one place. This module runs next to the product front
// end, which owns 5173 and 8000-ish, so both are moved out of the way — and
// the proxy target is derived from the API port rather than written twice, or
// they drift and the orb silently never connects.
const WEB = Number(process.env.NITYAM_ADK_WEB_PORT ?? 5273);
const API = Number(process.env.NITYAM_ADK_API_PORT ?? 8100);

// The dev server proxies the WebSocket to uvicorn so the browser sees a single
// origin. In production the FastAPI app serves dist/ and there is no proxy.
export default defineConfig({
  plugins: [react()],
  server: {
    port: WEB,
    strictPort: true,
    proxy: {
      "/ws": { target: `ws://127.0.0.1:${API}`, ws: true },
      "/health": { target: `http://127.0.0.1:${API}` },
    },
  },
});
