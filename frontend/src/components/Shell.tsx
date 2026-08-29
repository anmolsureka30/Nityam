import type { ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import s from "./Shell.module.css";
import { teacher } from "../lib/data";
import { useAuth } from "../lib/auth/AuthContext";

const cx = (...p: (string | false | undefined)[]) => p.filter(Boolean).join(" ");

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

function useClock() {
  // The design shows a wall clock in the header. Real time, so a demo at
  // 21:00 looks like an evening revision session without anyone faking it.
  const now = new Date();
  const day = now.toLocaleDateString("en-GB", { weekday: "short" }).toUpperCase();
  const time = now.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  return `${day} · ${time}`;
}

/** The student-facing frame: centred page, wordmark, clock, avatar. */
export function Shell({
  children, back,
}: { children: ReactNode; back?: { to: string; label: string } }) {
  const clock = useClock();
  return (
    <div className={s.shell}>
      <div className={s.page}>
        <header className={s.header}>
          <Link to="/" className={s.brand} aria-label="Nityam home">
            <span className={s.mark} />
            <span className={s.wordmark}>Nityam</span>
          </Link>
          <div className={s.right}>
            <RoleSwitch />
            <Link to="/profile" className={s.profileLink}>My profile</Link>
            <span className={s.clock}>{clock}</span>
            <UserChip />
          </div>
        </header>
        {back && (
          <div className={s.backRow}>
            <BackLink to={back.to} label={back.label} />
          </div>
        )}
        {children}
      </div>
    </div>
  );
}

/** The teacher-facing frame: same wordmark, different navigation, and a
 *  deliberately distinct label so nobody mistakes one for the other. */
export function TeacherShell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const tabs = [
    { to: "/teacher", label: "Today's class" },
    { to: "/teacher/intervene", label: "Intervention" },
    { to: "/teacher/insights", label: "Insights" },
  ];
  return (
    <div className={s.shell}>
      <div className={s.page}>
        <header className={s.header}>
          <div className={s.headLeft}>
            <Link to="/teacher" className={s.brand}>
              <span className={s.mark} style={{ background: "var(--ink-strong)" }} />
              <span className={s.wordmark}>Nityam</span>
            </Link>
            <span className={s.teacherMark}>Teacher</span>
            <nav className={s.tabs}>
              {tabs.map((t) => (
                <Link
                  key={t.to}
                  to={t.to}
                  className={cx(s.tab, pathname === t.to && s.tabOn)}
                >
                  {t.label}
                </Link>
              ))}
            </nav>
          </div>
          <div className={s.right}>
            <RoleSwitch />
            <span className="mono">{teacher.klass}</span>
            <UserChip />
          </div>
        </header>
        {children}
      </div>
    </div>
  );
}

/** Student / teacher switch. Lives in the header on every screen because the
 *  two dashboards are the same product, seen from two sides. */
function RoleSwitch() {
  const nav = useNavigate();
  const { pathname } = useLocation();
  const isTeacher = pathname.startsWith("/teacher");
  return (
    <div className={s.roleSwitch} role="group" aria-label="Switch role">
      <button
        className={cx(s.roleBtn, !isTeacher && s.roleBtnOn)}
        onClick={() => nav("/")}
        aria-pressed={!isTeacher}
      >
        Student
      </button>
      <button
        className={cx(s.roleBtn, isTeacher && s.roleBtnOn)}
        onClick={() => nav("/teacher")}
        aria-pressed={isTeacher}
      >
        Teacher
      </button>
    </div>
  );
}

export function BackLink({ to, label }: { to: string; label: string }) {
  const nav = useNavigate();
  return (
    <button className={s.back} onClick={() => nav(to)}>
      ← {label}
    </button>
  );
}
