/* Where the marketing/landing page lives — a separate Next.js project
 * (../Nityam), not part of this app. `VITE_*` env vars are inlined at build
 * time by Vite; unset, this falls back to the port Nityam/'s own dev server
 * defaults to (backend/run.sh's NITYAM_LANDING_PORT ?? 3001), so the two dev
 * servers are connected out of the box with no setup required — the mirror
 * image of Nityam/app/lib/config.ts's NEXT_PUBLIC_APP_URL. */
export const LANDING_URL = import.meta.env.VITE_LANDING_URL ?? "http://localhost:3001";
