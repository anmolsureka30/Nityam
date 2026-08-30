import type { ReactNode } from "react";
import AccountMenu from "./AccountMenu";
import { Link, useLocation, useNavigate } from "react-router-dom";
import s from "./Shell.module.css";
import { teacher } from "../lib/data";

const cx = (...p: (string | false | undefined)[]) => p.filter(Boolean).join(" ");

/** The header avatar. Kept as a named export because the shells reference it
 *  by this name; the behaviour lives in AccountMenu, which opens a menu rather
 *  than signing you out on a single unconfirmed click. */
export function UserChip() {
  return <AccountMenu />;
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
            <img className={s.logo} src="/nityam-logo.png" alt="" width={30} height={30} />
            <span className={s.wordmark}>Nityam</span>
          </Link>
          <div className={s.right}>
            <Link to="/sessions" className={s.profileLink}>My sessions</Link>
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
              <img className={s.logo} src="/nityam-logo.png" alt="" width={30} height={30} />
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
            <span className="mono">{teacher.klass}</span>
            <UserChip />
          </div>
        </header>
        {children}
      </div>
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
