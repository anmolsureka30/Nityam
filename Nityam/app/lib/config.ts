/* Where the real product lives — a separate Vite app (../frontend), not part
 * of this Next.js project. `NEXT_PUBLIC_*` env vars are inlined at build
 * time, so this is configurable per environment without a code change;
 * unset, it falls back to the port frontend/'s own dev server uses
 * (frontend/vite.config.ts's default, NITYAM_WEB_PORT ?? 5173), so the two
 * dev servers are connected out of the box with no setup required. */
export const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:5173";
export const APP_LOGIN_URL = `${APP_URL}/login`;
