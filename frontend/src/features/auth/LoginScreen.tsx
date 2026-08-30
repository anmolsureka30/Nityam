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
    case "auth/unauthorized-domain":
      return "This site isn't yet approved for sign-in — add it under Firebase Console → Authentication → Settings → Authorized domains.";
    default:
      return "Something went wrong. Please try again.";
  }
}

export default function LoginScreen() {
  const { signInWithEmail, signUpWithEmail, signInWithGoogle, resetPassword } = useAuth();
  const nav = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: { pathname: string } })?.from?.pathname ?? "/";

  /* The landing page's primary call to action is "Create your free account",
     and it used to land here on the Sign in tab — so the one journey the site
     pushes hardest opened on the wrong form. ?mode=signup is what that CTA
     now links to; anything else still defaults to signing in, which is the
     right default for a returning student typing /login themselves. */
  const [mode, setMode] = useState<"signin" | "signup">(
    new URLSearchParams(location.search).get("mode") === "signup" ? "signup" : "signin",
  );
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
          <img className={s.logo} src="/nityam-logo.png" alt="" width={40} height={40} />
          <span className={s.wordmark}>Nityam</span>
        </div>
        <p className={s.tagline}>Learn the Way You Want</p>

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
            <span className={s.inputWrap}>
              <input
                type="email"
                required
                inputMode="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className={s.input}
              />
            </span>
          </label>
          <label className={s.field}>
            <Label>Password</Label>
            <span className={s.inputWrap}>
              <input
                type="password"
                required
                minLength={6}
                autoComplete={mode === "signin" ? "current-password" : "new-password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={s.input}
              />
            </span>
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

        {/* Google is how almost everyone will actually sign in — a judge at a
            hackathon is not going to invent a password — so it gets the real
            mark and the weight of a primary action, instead of sitting under
            the form as an afterthought in the same grey as everything else.
            The G is inline SVG at Google's own four brand colours rather than
            an image: no network fetch, and it cannot fail to load on the one
            screen that has to work. */}
        <button type="button" className={s.google} onClick={google} disabled={busy}>
          <svg className={s.googleMark} viewBox="0 0 18 18" aria-hidden="true">
            <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z"/>
            <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.81.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18z"/>
            <path fill="#FBBC05" d="M3.97 10.72a5.4 5.4 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33z"/>
            <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.46.89 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58z"/>
          </svg>
          <span>Continue with Google</span>
        </button>
      </Card>
    </div>
  );
}
