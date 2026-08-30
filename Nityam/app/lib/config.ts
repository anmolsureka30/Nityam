/* Where the real product lives — a separate Vite app (../frontend), not part
 * of this Next.js project. `NEXT_PUBLIC_*` env vars are inlined at build
 * time, so this is configurable per environment without a code change;
 * unset, it falls back to the port frontend/'s own dev server uses
 * (frontend/vite.config.ts's default, NITYAM_WEB_PORT ?? 5173), so the two
 * dev servers are connected out of the box with no setup required.
 *
 * backend/run.sh passes NEXT_PUBLIC_APP_URL explicitly, so if the tutor ends
 * up on a different port the CTAs follow it. */
export const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:5173";

/** For a student who already has an account. Opens on the Sign in tab. */
export const APP_LOGIN_URL = `${APP_URL}/login`;

/** For everyone else, which on a landing page is almost everyone. The tutor's
 *  LoginScreen reads this parameter and opens on Create account — without it
 *  the page's main call to action landed on the sign-in form and asked new
 *  visitors for a password they had never set. */
export const APP_SIGNUP_URL = `${APP_URL}/login?mode=signup`;
