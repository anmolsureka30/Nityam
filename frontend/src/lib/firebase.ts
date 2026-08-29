import { initializeApp } from "firebase/app";
import { getAuth, type Auth } from "firebase/auth";

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

/* Whether there is anything to sign in against.
 *
 * This matters far more than it looks. `getAuth()` does not return a broken
 * client when the API key is missing — it THROWS, at module-evaluation time,
 * `Firebase: Error (auth/invalid-api-key)`. That throw propagates out of
 * main.tsx's import graph before createRoot ever runs, so the entire product
 * renders as A BLANK WHITE PAGE whose only trace is one console line. Every
 * screen, including the landing page that needs no account at all, disappears
 * because one environment variable is absent.
 *
 * So the config is checked before Firebase is ever handed it, and main.tsx
 * renders a setup notice instead. Being unconfigured is a normal state for a
 * fresh clone — frontend/.env is gitignored and holds six values from the
 * Firebase console — and a normal state should not look like a crash. */
export const firebaseConfigured = Object.values(firebaseConfig).every(
  (v) => typeof v === "string" && v.length > 0,
);

export const firebaseApp = firebaseConfigured ? initializeApp(firebaseConfig) : null;

/** Null exactly when `firebaseConfigured` is false. AuthProvider is the only
 *  consumer and main.tsx does not mount it in that case, so the non-null
 *  assertion there is guarded by construction rather than by hope. */
export const auth: Auth | null = firebaseApp ? getAuth(firebaseApp) : null;
