/* Where the marketing/landing page lives — a separate Next.js project
 * (../Nityam), not part of this app. `VITE_*` env vars are inlined at build
 * time by Vite; in local dev, unset falls back to the port Nityam/'s own dev
 * server defaults to (backend/run.sh's NITYAM_LANDING_PORT ?? 3001), so the
 * two dev servers are connected out of the box with no setup required — the
 * mirror image of Nityam/app/lib/config.ts's NEXT_PUBLIC_APP_URL.
 *
 * That local-dev default used to be unconditional, and a real deployment
 * inherited it: the landing page isn't deployed anywhere yet, so every
 * signed-out visitor to the real, deployed app got bounced to a dead
 * http://localhost:3001 in THEIR OWN browser — confirmed live. A relative
 * path is the safe default for any environment that hasn't explicitly
 * wired up a separate landing page: it always resolves to this same app's
 * own sign-in screen, never an external host that may not exist. Local
 * dev is unaffected — run.sh always sets VITE_LANDING_URL explicitly. */
export const LANDING_URL =
  import.meta.env.VITE_LANDING_URL ||
  (import.meta.env.DEV ? "http://localhost:3001" : "/login");
