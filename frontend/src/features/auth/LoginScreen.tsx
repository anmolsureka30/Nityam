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

        <Button block onClick={google} disabled={busy}>
          Continue with Google
        </Button>
      </Card>
    </div>
  );
}
