import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Ports come from the environment so backend/run.sh can move both together.
// The backend defaults to 8210 (8200 collides with OpenWhisp on this machine);
// the adk sub-module keeps 8100/5273, so everything can run side by side.
const WEB = Number(process.env.NITYAM_WEB_PORT ?? 5173)
const API = Number(process.env.NITYAM_API_PORT ?? 8210)

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Same-origin from the browser's point of view, so lib/live/session.ts can
  // build its socket URL from location.host and nothing needs a base URL.
  // `preview` needs its own copy — it does not inherit `server.proxy`.
  server: {
    port: WEB,
    strictPort: true,
    proxy: {
      '/ws': { target: `ws://127.0.0.1:${API}`, ws: true },
      '/health': { target: `http://127.0.0.1:${API}` },
    },
  },
  preview: {
    port: WEB,
    strictPort: true,
    proxy: {
      '/ws': { target: `ws://127.0.0.1:${API}`, ws: true },
      '/health': { target: `http://127.0.0.1:${API}` },
    },
  },
})
