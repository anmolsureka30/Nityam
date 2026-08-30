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
import { auth as maybeAuth } from "../firebase";

/* Non-null by construction: main.tsx renders the setup notice instead of this
   provider when Firebase is unconfigured. Asserted once here rather than at
   each call site below. */
const auth = maybeAuth!;

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

/** Give a brand-new account its starting record, once, at sign-in.
 *
 *  The backend also checks this when a session's WebSocket opens, but that is
 *  too late for what it is for: somebody signs in, lands on the dashboard, and
 *  sees an empty profile and an empty session list — exactly the impression
 *  the record exists to prevent — and only finds out otherwise if they happen
 *  to start a session first.
 *
 *  Fire-and-forget and deliberately silent. It is idempotent server-side (an
 *  existing student is left alone), and a seeding failure must never be the
 *  reason somebody cannot get into the app — the worst case is the empty
 *  dashboard they would have had anyway. */
const seedAttempted = new Set<string>();

async function ensureSeeded(user: User): Promise<void> {
  if (seedAttempted.has(user.uid)) return;
  seedAttempted.add(user.uid);
  try {
    const token = await user.getIdToken();
    await fetch(`/memory/students/${encodeURIComponent(user.uid)}/ensure`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    /* see above */
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(
    () =>
      onAuthStateChanged(auth, (u) => {
        setUser(u);
        setLoading(false);
        if (u) ensureSeeded(u);
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
