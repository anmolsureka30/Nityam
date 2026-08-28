# Firebase Authentication — Implementation Guide

Extracted from the Nityam Prototype repo before a full revert to Arnav's
`origin/main` commit. This captures the complete, working Firebase Auth
implementation — architecture, every file, every config value needed — so it
can be rebuilt from scratch on a clean checkout.

Firebase project used: **`nityam-506707`** — the same GCP project already
backing Firestore for the memory layer (`store_firestore.py`). This is Auth
added to an *existing* project, not a new one.

---

## 1. What this buys you

Before this, there was **zero authentication anywhere**: the WebSocket
(`/ws/{user_id}/{session_id}`) trusted `user_id` verbatim with no token, no
check, and the frontend hardcoded `student_id = "demo_student"` everywhere.
This implementation:

1. Adds real sign-in (email/password + Google) to the frontend, with route
   protection and sign-out.
2. Verifies a Firebase ID token server-side, in the one place identity flows
   into the backend — the WebSocket handshake — replacing the trusted-but-
   unchecked path param.
3. Keeps the demo/seeded Firestore data working by pinning a real Firebase
   user's `uid` to `"demo_student"`, so no data migration is needed.
4. Locks Firestore security rules to deny-all-client-access (belt-and-
   suspenders — all real access is server-side via the Admin SDK, which
   bypasses rules entirely regardless).

**Explicitly out of scope, then and now:** a teacher/student ownership model
(`RoleSwitch` stays a client-side UI toggle with no server backing — auth
answers "who is this," not "what can they see"), a deployment pipeline,
Firebase App Check, and email-verification enforcement.

---

## 2. Architecture

```
frontend/
  main.tsx                         <AuthProvider> wraps <App/> inside <BrowserRouter>
  lib/firebase.ts                  initializeApp() + getAuth()
  lib/auth/AuthContext.tsx         useAuth() hook — user, loading, sign in/up/out
  components/ProtectedRoute.tsx    redirects to /login when signed out
  features/auth/LoginScreen.tsx    email/password + Google, styled to match the app
  App.tsx                          every route wrapped in <ProtectedRoute>, plus /login
  components/Shell.tsx             UserChip — real user initial, click to sign out
  lib/live/session.ts              connect() takes getToken(), appends ?token=<ID token>
        │
        │  wss://host/ws/{uid}/{session_id}?token=<fresh Firebase ID token>
        ▼
backend/
  app/user_auth.py                 init_firebase() + verify_token() — NEW file
  app/main.py  ws_endpoint()        verify token, assert decoded uid == path uid,
                                    send an error control frame + close(4401) on failure
                                    (everything downstream is unchanged — user_id was
                                    already threaded through sessions.get() etc.)
        │
        ▼
  Firestore `smriti` DB, nityam-506707 — same project, now also hosts Firebase
  Auth users. Security rules set to deny-all-client-access.
```

Key design decisions, and why:

- **`app/user_auth.py`, not `app/auth.py`.** The existing `app/auth.py`
  governs GenAI *platform* credential selection (`ai_studio`/`vertex`/
  `vertex_express`/`mock`) — a completely different concept. Reusing the name
  would make both files harder to reason about.
- **ADC (Application Default Credentials), no service-account JSON.**
  `firebase_admin.initialize_app()` with no explicit credential argument
  resolves ADC — identical to how `store_firestore.py` already authenticates.
  Local dev uses `gcloud auth application-default login`; a future Cloud Run
  deploy works unchanged via its attached service account. Zero new
  credential plumbing.
- **Verify after `ws.accept()`, not before.** A pre-accept WebSocket
  rejection carries no reason string the browser can read (a platform
  limitation, not a FastAPI one) — `WebSocket.onerror`/`onclose` expose no
  status text for handshake-level rejections. Accepting first and then
  sending the existing `{nityam:{kind:"error",...}}` control frame means the
  message actually reaches the screen. Nothing sensitive happens between
  `accept()` and the check (no session state created, no board data sent),
  so the brief accept-before-verify window costs nothing.
- **Check `decoded.uid == user_id`, not just "is the token valid."** Without
  this, a signed-in user could still put someone else's uid in the URL path
  while presenting their own valid token — the path value (not the verified
  uid) is what flows into `student_id` everywhere downstream. This check
  closes that gap while leaving all the downstream code (`sessions.get(
  session_id, student_id=user_id)`, `state={"student_id": user_id}`)
  completely unchanged: `user_id` becomes trustworthy because it's checked
  against the token, not because its origin changed.
- **`4401` close code.** `>=4000` is the range reserved for application use.
  Not required for the message to reach the user (the control frame already
  carries it) but lets the frontend distinguish "you got signed out" later if
  needed.
- **No auth-bypass flag for tests.** Bypass flags outlive their
  justification. Instead, tests provision a *real* Firebase user and sign in
  for a *real* ID token via the Identity Toolkit REST API (see §6) — matching
  this repo's existing "no fake socket" test philosophy.

---

## 3. Prerequisites / manual console steps

These cannot be scripted — do them once in the Firebase console for
`nityam-506707`:

1. **Authentication → Sign-in method**: enable **Email/Password** and
   **Google** providers.
2. **Authentication → Settings → Authorized domains**: `localhost` is present
   by default (covers local dev); add the production domain once one exists.
3. **Firestore → Rules**: paste the rules from §7 below (or confirm they're
   already non-default — a fresh project defaults to a 30-day open "test
   mode" window).
4. Locally: `gcloud auth application-default login` (same ADC Firestore
   already needs) and `Email/Password` sign-in must be enabled in the console
   before `tests/_firebase_test_tokens.py` will work (it signs in for real).

---

## 4. Dependencies

**Backend** (`backend/requirements.txt`):
```
firebase-admin>=7.2
```

**Frontend** (`frontend/package.json`):
```
"firebase": "^12.18.0",
```
Only `firebase/app` and `firebase/auth` are imported — **not**
`firebase/analytics` (unused; skips an extra bundle cost and the console step
of enabling Google Analytics on the project).

---

## 5. Environment variables

**`backend/.env.example`** (add):
```
# Firebase web API key — same value as frontend/.env's VITE_FIREBASE_API_KEY.
# Not a secret (it identifies the project, not a credential), but tests need
# it to sign in as a fixed test account and get a real ID token. See
# backend/tests/_firebase_test_tokens.py.
FIREBASE_WEB_API_KEY=
```
No other backend env vars needed — `firebase_admin.initialize_app()` uses the
same ADC path already configured for Firestore.

**`frontend/.env.example`** (new file, or append):
```
VITE_FIREBASE_API_KEY=
VITE_FIREBASE_AUTH_DOMAIN=
VITE_FIREBASE_PROJECT_ID=
VITE_FIREBASE_STORAGE_BUCKET=
VITE_FIREBASE_MESSAGING_SENDER_ID=
VITE_FIREBASE_APP_ID=
```
These are the Firebase web app config values from the console (Project
settings → General → Your apps → SDK setup and configuration). They are not
secrets — they identify the project; access is governed by Auth + API-key
restrictions, not by hiding them — but for consistency with the rest of this
repo's `.env` handling they go in `frontend/.env` (gitignored) with
`.env.example` carrying placeholders.

Real values actually used for `nityam-506707` (fill in `frontend/.env` and
the backend's `FIREBASE_WEB_API_KEY` with the console's actual values — they
were not re-derived here since the project itself still exists in Firebase,
only this repo's checkout is being reset).

---

## 6. Backend implementation — full files

### 6.1 `backend/app/user_auth.py` (new file)

```python
"""Firebase Auth: verifying a browser-supplied ID token server-side.

The one place identity flows into this backend is app/main.py's ws_endpoint —
see that file. This module owns nothing about WHERE the token comes from,
only whether it's real.
"""
from __future__ import annotations

import firebase_admin
from firebase_admin import auth as firebase_auth

_app: firebase_admin.App | None = None


def init_firebase() -> None:
    """Idempotent. ADC (Application Default Credentials) — the same
    credential path app/memory/store_firestore.py already uses, so local dev
    keeps using `gcloud auth application-default login` and a future Cloud
    Run deploy keeps working via its attached service account, with zero new
    credential plumbing."""
    global _app
    if _app is None:
        _app = firebase_admin.initialize_app()


def verify_token(id_token: str) -> dict:
    """Raises firebase_admin.auth.* exceptions (ValueError, InvalidIdTokenError,
    ExpiredIdTokenError, etc.) on anything not a currently-valid ID token for
    this project. Callers catch broadly — see app/main.py:ws_endpoint."""
    return firebase_auth.verify_id_token(id_token)
```

### 6.2 `backend/app/main.py` — three surgical additions

Import, alongside the existing top-level imports:
```python
from app import incoming, sessions, user_auth  # noqa: E402
```

Right after `app = FastAPI(title="Nityam backend")`:
```python
user_auth.init_firebase()
```

Inside `ws_endpoint`, immediately after `await ws.accept()` and before
anything else (before `logs.open_session`, before `sessions.get`):
```python
    token = ws.query_params.get("token")
    decoded = None
    if token:
        try:
            # In a thread: verify_id_token() is synchronous and makes a real
            # HTTPS call whenever Google's signing certificates are not already
            # cached (the first connection after startup, and periodically
            # after that). Called inline it would stall the whole event loop —
            # and with it every concurrent student's audio stream — for as long
            # as that fetch takes.
            decoded = await asyncio.to_thread(user_auth.verify_token, token)
        except Exception:
            decoded = None
    if not decoded or decoded.get("uid") != user_id:
        # Accept-then-reject, not a pre-accept close: a pre-accept WebSocket
        # rejection carries no reason string the browser can read (a platform
        # limitation, not a FastAPI one), so the actual "please sign in again"
        # message would never reach the screen. Nothing sensitive happens
        # before this check — no session state, no board data.
        await send_control(
            ws, kind="error",
            message="Your sign-in has expired. Please refresh and sign in again.",
        )
        await ws.close(code=4401)
        return
```
(`send_control` is an existing helper in `main.py` that sends a
`{nityam:{kind:..., ...}}` control frame — defined elsewhere in the same
file, callable regardless of definition order since both are module-level
async functions.)

Everything downstream of this (`logs.open_session`, `sessions.get(session_id,
student_id=user_id)`, `state={"session_id": ..., "student_id": user_id}`) was
already threading `user_id` through — no other change needed there.
`tutor_agent.py`'s `state.setdefault("student_id", "demo_student")` becomes
dead-code-in-practice (state is always set before it runs) but is harmless
left as a safety net.

### 6.3 `backend/scripts/create_demo_firebase_user.py` (new file)

One-time setup so the seeded Firestore data (`seed_demo_data.py`, all keyed
to `student_id="demo_student"`) has a real Firebase account to sign in as.
Idempotent — safe to re-run; a real `run.sh` wired this to run alongside the
Firestore seed on first start.

```python
"""One-time setup: creates the demo Firebase user backend/scripts/seed_demo_data.py's
Firestore documents are keyed to. Pins uid="demo_student" explicitly (the
Admin SDK allows choosing the uid at creation) so none of the already-seeded
data needs to change.

Idempotent — safe to re-run. `run.sh` runs it alongside the Firestore seed on
first start, so a fresh clone gets both halves of "the demo student".

**This account and its password are public — they are checked into git.**
Delete it or rotate its password before any real/production deployment; it
exists only for local dev and CI.

Run directly: `.venv/bin/python -m scripts.create_demo_firebase_user`
"""
from __future__ import annotations

from firebase_admin import auth as firebase_auth

from app import user_auth

DEMO_UID = "demo_student"
DEMO_EMAIL = "demo@nityam.local"
DEMO_PASSWORD = "nityam-demo-2026"  # local/demo only — not a real account


def main() -> None:
    user_auth.init_firebase()
    try:
        firebase_auth.get_user(DEMO_UID)
        print(f"{DEMO_UID} already exists — nothing to do")
        return
    except firebase_auth.UserNotFoundError:
        pass

    firebase_auth.create_user(
        uid=DEMO_UID, email=DEMO_EMAIL, password=DEMO_PASSWORD, email_verified=True,
    )
    print(f"created {DEMO_UID} ({DEMO_EMAIL})")


if __name__ == "__main__":
    main()
```

`run.sh` called this once, right after the Firestore seed step, on first run
only (guarded by checking whether the local sqlite/Firestore seed marker
already existed):
```bash
$PY -m scripts.create_demo_firebase_user || {
  echo "(no demo Firebase user — nobody can sign in as demo_student yet."
  echo " Fix: gcloud auth application-default login"
  echo "      .venv/bin/python -m scripts.create_demo_firebase_user)"
}
```

### 6.4 `backend/tests/_firebase_test_tokens.py` (new file) — real tokens for tests

This is the non-obvious piece: getting a *real* Firebase ID token inside a
test, with no signing/impersonation permission needed, no fake socket, no
mocked auth layer.

```python
"""Get a real Firebase ID token for a fixed, auto-provisioned test account.

No signing/impersonation permission needed: this creates (if missing) a real
Firebase Auth user with a known email/password via the Admin SDK's plain
create_user/get_user_by_email (ordinary authenticated Admin API calls — same
as scripts/create_demo_firebase_user.py, works with plain ADC), then signs
in as that user via the real (free, no-quota-cost) Identity Toolkit password
sign-in REST API. Tests get a real ID token, exactly what a browser gets.

Needs: Email/Password sign-in enabled in the Firebase console (Authentication
-> Sign-in method — a one-time manual step), ADC
(`gcloud auth application-default login`), and FIREBASE_WEB_API_KEY in the
environment.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from firebase_admin import auth as firebase_auth

from app import user_auth


def ensure_test_user(email: str, password: str) -> str:
    """Idempotent: returns the uid, creating the account if it doesn't exist."""
    user_auth.init_firebase()
    try:
        return firebase_auth.get_user_by_email(email).uid
    except firebase_auth.UserNotFoundError:
        return firebase_auth.create_user(email=email, password=password).uid


def mint_id_token(email: str, password: str) -> str:
    """Auto-provisions the account if needed, then signs in for a real ID token."""
    ensure_test_user(email, password)
    api_key = os.environ["FIREBASE_WEB_API_KEY"]
    url = (
        "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
        f"?key={api_key}"
    )
    body = json.dumps(
        {"email": email, "password": password, "returnSecureToken": True},
    ).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.load(resp)["idToken"]
    except urllib.error.HTTPError as e:
        # The body is the whole diagnosis and urllib throws it away: a bare
        # "HTTP Error 400: Bad Request" hides OPERATION_NOT_ALLOWED, which is
        # what a fresh project says until Email/Password sign-in is enabled in
        # the console — by far the likeliest first-run failure here.
        raise RuntimeError(f"Firebase sign-in failed: {e.read().decode()}") from e
```

Used in `test_wire.py` / `test_live.py` like:
```python
from tests._firebase_test_tokens import mint_id_token
token = mint_id_token("demo@nityam.local", "nityam-demo-2026")
url = f"ws://127.0.0.1:{port}/ws/demo_student/s_live_test?token={token}"
```

### 6.5 Backend tests written for this feature

- `tests/test_user_auth.py` — unit tests for `init_firebase`/`verify_token`
  against a real token (mints one via `_firebase_test_tokens`), and confirms
  a garbage/expired/wrong-project token raises.
- `tests/test_ws_auth.py` — drives a real WebSocket against a real server
  process and confirms: no token → rejected; garbage token → rejected;
  valid token but wrong `uid` in the path → rejected; valid token + matching
  uid → connects normally. Each rejection case asserts the close code
  (`4401`) and that the `{nityam:{kind:"error",...}}` frame actually arrived
  before the close.

---

## 7. Frontend implementation — full files

### 7.1 `frontend/src/lib/firebase.ts` (new file)

```typescript
import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

export const firebaseApp = initializeApp(firebaseConfig);
export const auth = getAuth(firebaseApp);
```

### 7.2 `frontend/src/lib/auth/AuthContext.tsx` (new file)

```typescript
import {
  type User,
  GoogleAuthProvider,
  createUserWithEmailAndPassword,
  onAuthStateChanged,
  sendPasswordResetEmail,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut as firebaseSignOut,
} from "firebase/auth";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { auth } from "../firebase";

interface AuthValue {
  user: User | null;
  loading: boolean;
  signInWithGoogle: () => Promise<void>;
  signInWithEmail: (email: string, password: string) => Promise<void>;
  signUpWithEmail: (email: string, password: string) => Promise<void>;
  resetPassword: (email: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(
    () =>
      onAuthStateChanged(auth, (u) => {
        setUser(u);
        setLoading(false);
      }),
    [],
  );

  const value: AuthValue = {
    user,
    loading,
    signInWithGoogle: async () => {
      await signInWithPopup(auth, new GoogleAuthProvider());
    },
    signInWithEmail: async (email, password) => {
      await signInWithEmailAndPassword(auth, email, password);
    },
    signUpWithEmail: async (email, password) => {
      await createUserWithEmailAndPassword(auth, email, password);
    },
    resetPassword: async (email) => {
      await sendPasswordResetEmail(auth, email);
    },
    signOut: async () => {
      await firebaseSignOut(auth);
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
```

`loading` is true only until the very first `onAuthStateChanged` callback
fires (Firebase's local persistence means this resolves near-instantly for a
returning user, but the app must not flash the login screen during that
window).

### 7.3 `frontend/src/main.tsx` — wiring

`<AuthProvider>` goes inside `<BrowserRouter>` (needs router context for
post-login redirects) and outside `<App/>`:

```typescript
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./lib/auth/AuthContext";
import "./styles/base.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
```

### 7.4 `frontend/src/components/ProtectedRoute.tsx` (new file)

```typescript
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../lib/auth/AuthContext";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return null;
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />;
  return <>{children}</>;
}
```

### 7.5 `frontend/src/App.tsx` — every route wrapped, plus `/login`

```typescript
import { ProtectedRoute } from "./components/ProtectedRoute";
// ...
<Route path="/login" element={<LoginScreen />} />
<Route path="/" element={<ProtectedRoute><HomeScreen /></ProtectedRoute>} />
<Route path="/intensity" element={<ProtectedRoute><IntensityScreen /></ProtectedRoute>} />
<Route path="/session" element={<ProtectedRoute><SessionScreen /></ProtectedRoute>} />
<Route path="/readiness" element={<ProtectedRoute><ReadinessScreen /></ProtectedRoute>} />
<Route path="/summary" element={<ProtectedRoute><SummaryScreen /></ProtectedRoute>} />
<Route path="/teacher" element={<ProtectedRoute><TeacherClassScreen /></ProtectedRoute>} />
<Route path="/teacher/intervene" element={<ProtectedRoute><TeacherIntervene /></ProtectedRoute>} />
<Route path="/teacher/insights" element={<ProtectedRoute><TeacherInsights /></ProtectedRoute>} />
```
`/teacher/*` gets no additional check beyond "signed in" — role stays a pure
UI toggle (`RoleSwitch`), per scope.

### 7.6 `frontend/src/features/auth/LoginScreen.tsx` (new file)

Built from the app's existing `ui.tsx` primitives (`Card`, `Button`, `Label`)
so it matches the app's own theme rather than looking like a bolted-on
third-party form. Email/password with a sign-in/create-account tab toggle,
"Forgot password?", and "Continue with Google."

```typescript
import { type FormEvent, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Button, Card, Label } from "../../components/ui";
import { useAuth } from "../../lib/auth/AuthContext";
import s from "./LoginScreen.module.css";

const cx = (...p: (string | false | undefined)[]) => p.filter(Boolean).join(" ");

function friendlyError(code: string): string {
  switch (code) {
    case "auth/invalid-email":
      return "That doesn't look like a valid email address.";
    case "auth/user-not-found":
    case "auth/wrong-password":
    case "auth/invalid-credential":
      return "Wrong email or password.";
    case "auth/email-already-in-use":
      return "An account already exists for that email — sign in instead.";
    case "auth/weak-password":
      return "Password should be at least 6 characters.";
    case "auth/popup-closed-by-user":
      return "Google sign-in was closed before finishing.";
    default:
      return "Something went wrong. Please try again.";
  }
}

export default function LoginScreen() {
  const { signInWithEmail, signUpWithEmail, signInWithGoogle, resetPassword } = useAuth();
  const nav = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: { pathname: string } })?.from?.pathname ?? "/";

  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      if (mode === "signin") await signInWithEmail(email, password);
      else await signUpWithEmail(email, password);
      nav(from, { replace: true });
    } catch (err) {
      setError(friendlyError((err as { code?: string }).code ?? ""));
    } finally {
      setBusy(false);
    }
  }

  async function google() {
    setError(null);
    setBusy(true);
    try {
      await signInWithGoogle();
      nav(from, { replace: true });
    } catch (err) {
      setError(friendlyError((err as { code?: string }).code ?? ""));
    } finally {
      setBusy(false);
    }
  }

  async function forgot() {
    if (!email) {
      setError('Enter your email above first, then click "Forgot password".');
      return;
    }
    setError(null);
    try {
      await resetPassword(email);
      setNotice(`Password reset email sent to ${email}.`);
    } catch (err) {
      setError(friendlyError((err as { code?: string }).code ?? ""));
    }
  }

  return (
    <div className={s.page}>
      <Card size="md" style={{ width: 380 }}>
        <div className={s.brand}>
          <span className={s.mark} />
          <span className={s.wordmark}>Nityam</span>
        </div>

        <div className={s.tabs} role="tablist" aria-label="Sign in or create an account">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "signin"}
            className={cx(s.tab, mode === "signin" && s.tabOn)}
            onClick={() => setMode("signin")}
          >
            Sign in
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "signup"}
            className={cx(s.tab, mode === "signup" && s.tabOn)}
            onClick={() => setMode("signup")}
          >
            Create account
          </button>
        </div>

        <form className={s.form} onSubmit={submit}>
          <label className={s.field}>
            <Label>Email</Label>
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={s.input}
            />
          </label>
          <label className={s.field}>
            <Label>Password</Label>
            <input
              type="password"
              required
              minLength={6}
              autoComplete={mode === "signin" ? "current-password" : "new-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={s.input}
            />
          </label>

          {error && <p className={s.error}>{error}</p>}
          {notice && <p className={s.notice}>{notice}</p>}

          <Button type="submit" variant="primary" block disabled={busy}>
            {mode === "signin" ? "Sign in" : "Create account"}
          </Button>
        </form>

        {mode === "signin" && (
          <button type="button" className={s.forgot} onClick={forgot}>
            Forgot password?
          </button>
        )}

        <div className={s.divider}>
          <span>or</span>
        </div>

        <Button block onClick={google} disabled={busy}>
          Continue with Google
        </Button>
      </Card>
    </div>
  );
}
```

### 7.7 `frontend/src/features/auth/LoginScreen.module.css` (new file)

```css
.page {
  min-height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.brand { display: flex; align-items: center; gap: 8px; justify-content: center; margin-bottom: 22px; }
.mark { width: 20px; height: 20px; border-radius: var(--r-xs); background: var(--accent); }
.wordmark { font-family: var(--prose); font-size: 19px; font-weight: 600; letter-spacing: -0.01em; }

.tabs {
  display: flex;
  border: 1px solid var(--line);
  border-radius: var(--r-pill);
  padding: 3px;
  margin-bottom: 20px;
}
.tab {
  flex: 1;
  text-align: center;
  padding: 8px 0;
  border: none;
  background: none;
  border-radius: var(--r-pill);
  font-size: 13.5px;
  font-weight: 500;
  color: var(--ink-mid);
}
.tabOn { background: var(--accent-wash); color: var(--accent-deep); }

.form { display: flex; flex-direction: column; gap: 14px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.input {
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  padding: 10px 12px;
  font-size: 14.5px;
  background: var(--paper);
}
.input:focus-visible { border-color: var(--accent); }

.error { color: var(--danger); font-size: 13px; margin: 0; }
.notice { color: var(--good); font-size: 13px; margin: 0; }

.forgot {
  display: block;
  margin: 12px auto 0;
  border: none;
  background: none;
  color: var(--ink-mid);
  font-size: 12.5px;
}
.forgot:hover { color: var(--accent-deep); }

.divider {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 18px 0 14px;
  color: var(--ink-dim);
  font-size: 12px;
}
.divider::before, .divider::after { content: ""; flex: 1; height: 1px; background: var(--line); }
```
(Relies on the app's existing design tokens — `--accent`, `--line`, `--ink-mid`,
etc. — defined in `frontend/src/styles/tokens.css`. If rebuilding against a
different visual system, swap these for its own tokens.)

### 7.8 `frontend/src/components/Shell.tsx` — real user chip + sign-out

Exported so `SessionScreen` (which has its own header, not `Shell`) can reuse
the exact same chip — it's the one screen a student sits on for a whole
session, so it's the last place that should show a mock name.

```typescript
import { useAuth } from "../lib/auth/AuthContext";
import { useNavigate } from "react-router-dom";

/** Real signed-in user, replacing the old hardcoded avatar initial. Doubles
 *  as the sign-out control — clicking it signs out and returns to /login. */
export function UserChip() {
  const { user, signOut } = useAuth();
  const nav = useNavigate();
  const label = user?.email ?? "";
  const initial = label ? label[0]!.toUpperCase() : "?";

  async function handleClick() {
    await signOut();
    nav("/login", { replace: true });
  }

  return (
    <button
      type="button"
      className={s.avatarChip}
      title={label ? `Sign out (${label})` : "Sign out"}
      onClick={handleClick}
    >
      {initial}
    </button>
  );
}
```
Used in both `Shell` (student header) and `TeacherShell`, in place of the old
hardcoded `{student.initial}` span. The corresponding CSS class needs
`padding: 0` added (a `<button>` has default UA padding a `<span>` didn't).

### 7.9 Token flowing into the WebSocket — `session.ts` / `useLiveSession.ts`

`LiveSession`'s constructor takes an async token source and calls it right
before opening the socket, appending the token as a query param:

```typescript
constructor(opts: {
  userId: string;
  sessionId: string;
  getToken: () => Promise<string>;
  onFrame?: (frame: ServerFrame) => void;
  onStatus?: (status: SessionStatus) => void;
}) {
  this.userId = opts.userId;
  this.sessionId = opts.sessionId;
  this.getToken = opts.getToken;
  // ...
}

async connect(): Promise<void> {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const token = await this.getToken();
  const url =
    `${scheme}://${location.host}/ws/${this.userId}/${this.sessionId}` +
    `?token=${encodeURIComponent(token)}`;
  // ...open the WebSocket with this url...
}
```

`useLiveSession(userId, sessionId, plan, getToken)` threads this through from
the caller. In `SessionScreen.tsx`:

```typescript
const { user } = useAuth();          // ProtectedRoute guarantees non-null here
const userId = user!.uid;
const tutor = useLiveSession(userId, sessionId, plan, () => user!.getIdToken());
```

`user.getIdToken()` is Firebase's own SDK method — it auto-refreshes if the
cached token is near expiry, so this is cheap to call right before every
connect (not a network round-trip unless a refresh is actually needed). No
other change is needed anywhere else in `lib/live/` — the token is purely an
addition to the connect-time URL.

---

## 8. Test-suite integration (`frontend/tests/ui.mjs`)

The end-to-end browser test signs in as the real demo account before
reaching `/session`, rather than special-casing test mode in application
code:

```javascript
await fill("email", "demo@nityam.local");
await fill("password", "nityam-demo-2026");
await ev(
  // Scoped to type="submit": the login screen's mode tab reads "Sign in" too
  // (its default-active state), and comes first in document order, so an
  // unscoped text match clicks the inert tab instead of submitting the form.
  `[...document.querySelectorAll('button[type="submit"]')].find(b=>b.textContent.trim()==="Sign in")?.click(); return 1;`,
);
for (let i = 0; i < 100; i++) {
  if ((await ev(`return location.pathname;`)) === "/session") break;
  await sleep(100);
}
```
Also injects a WebSocket `send` interceptor for other assertions, unrelated
to auth specifically.

---

## 9. Firestore security rules

All current Firestore access is server-side through the Admin SDK, which
bypasses security rules entirely — so this is a safety net, not something in
the actual request path:

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /{document=**} {
      allow read, write: if false;
    }
  }
}
```

---

## 10. Suggested rebuild order

1. Backend: `user_auth.py`, `_firebase_test_tokens.py`, `FIREBASE_WEB_API_KEY`
   env var. Verify `init_firebase()`/`verify_token()` against a real minted
   token.
2. Backend: wire the three `main.py` additions into `ws_endpoint`. Verify
   with a real-vs-garbage-vs-wrong-uid token test over an actual socket.
3. Backend: `create_demo_firebase_user.py`, run it once.
4. Backend: attach a real token to `test_wire.py`/`test_live.py`'s WS URLs.
5. Frontend: `npm install firebase`, `.env`/`.env.example`, `lib/firebase.ts`.
   Verify it builds.
6. Frontend: `AuthContext.tsx`, wire into `main.tsx`. Verify it builds/runs.
7. Frontend: `ProtectedRoute.tsx`, `LoginScreen.tsx`/`.module.css`, wire
   `/login` + `ProtectedRoute` into `App.tsx`. Manually verify sign-in/up/out,
   wrong-password message, Google sign-in.
8. Frontend: `UserChip` in `Shell.tsx`/`TeacherShell`, fix the avatar-chip CSS
   for a `<button>`.
9. Frontend: thread `getToken` through `SessionScreen.tsx` → `useLiveSession`
   → `session.ts`'s `connect()`.
10. Frontend test: sign in for real in `tests/ui.mjs` before `/session`.
11. Firestore rules + console setup (§3, §9). Full manual pass: sign up, sign
    in, sign out, wrong-password error, Google sign-in, session persists
    across a page reload, a real tutoring session connects and the board
    renders (proves the token round-trip), and the negative case — an
    expired/tampered token produces the "please sign in again" message
    rather than a silent hang or a raw connection-failed error.

---

## 11. Known gaps worth deciding on next time

- No teacher/student ownership model — `/teacher/*` is behind "signed in,"
  not "is actually a teacher." Deliberately out of scope originally; revisit
  if that boundary starts to matter.
- No Firebase App Check, no email-verification enforcement, no password-
  strength UI beyond Firebase's own client-side defaults.
- No deployment pipeline exists for this repo at all (no Dockerfile, no CI) —
  this auth code is deployment-ready (ADC-based, works unchanged on Cloud
  Run) but the pipeline itself was never built.
