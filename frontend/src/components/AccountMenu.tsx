import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth/AuthContext";
import s from "./AccountMenu.module.css";

/* The avatar used to sign you out on a single click, with no confirmation and
 * no warning — the only thing in the header that did something irreversible
 * immediately. It opens a menu now.
 *
 * "Reset my account" is the destructive one and is treated as such: it asks
 * first, says exactly what it will do, and only ever resets YOUR account —
 * the server verifies the Firebase token and refuses any uid but the caller's
 * own, so this button cannot be pointed at anyone else even by editing it. */
export default function AccountMenu() {
  const { user, signOut } = useAuth();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const wrap = useRef<HTMLDivElement>(null);

  const email = user?.email ?? "";
  const initial = email ? email[0]!.toUpperCase() : "?";

  // Close on an outside click or Escape — a menu that can only be dismissed
  // by choosing something from it is a trap.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  useEffect(() => {
    if (!open) {
      setConfirming(false);
      setError("");
    }
  }, [open]);

  async function handleSignOut() {
    await signOut();
    nav("/login", { replace: true });
  }

  async function handleReset() {
    if (!user) return;
    setBusy(true);
    setError("");
    try {
      // A fresh token rather than a cached one: the server verifies it, and
      // an hour-old session would fail for a reason that has nothing to do
      // with the button.
      const token = await user.getIdToken();
      const res = await fetch(
        `/memory/students/${encodeURIComponent(user.uid)}/reset`,
        { method: "POST", headers: { Authorization: `Bearer ${token}` } },
      );
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail ?? `server returned ${res.status}`);
      }
      // Hard reload rather than a route change: the profile, the session list
      // and every cached memory fetch are all stale now, and reloading is
      // both simpler and more obviously correct than invalidating each one.
      window.location.href = "/profile";
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className={s.wrap} ref={wrap}>
      <button
        type="button"
        className={s.avatar}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        title={email || "Account"}
      >
        {initial}
      </button>

      {open && (
        <div className={s.menu} role="menu">
          <div className={s.who}>
            <span className={s.whoLabel}>Signed in as</span>
            <span className={s.whoEmail}>{email || "unknown"}</span>
          </div>

          {!confirming ? (
            <>
              <button
                type="button"
                role="menuitem"
                className={s.item}
                onClick={() => setConfirming(true)}
              >
                Reset my account
                <span className={s.itemNote}>
                  Clear my history and start from the demo record
                </span>
              </button>
              <button
                type="button"
                role="menuitem"
                className={s.item}
                onClick={handleSignOut}
              >
                Log out
              </button>
            </>
          ) : (
            <div className={s.confirm}>
              {/* Say what is actually lost. "Are you sure?" is not a warning. */}
              <p className={s.confirmText}>
                This deletes every session you have had and every judgement I
                have made about you, then puts back the two demo sessions.
                It cannot be undone.
              </p>
              {error && <p className={s.error}>{error}</p>}
              <div className={s.confirmRow}>
                <button
                  type="button"
                  className={s.danger}
                  onClick={handleReset}
                  disabled={busy}
                >
                  {busy ? "Resetting…" : "Yes, reset it"}
                </button>
                <button
                  type="button"
                  className={s.cancel}
                  onClick={() => setConfirming(false)}
                  disabled={busy}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
