import type { SessionSummary } from "./SessionDrawer";
import styles from "./SessionListInline.module.css";

/** The session picker's content, without SessionDrawer's fixed-width nav
 * chrome — used inside the SidePanel's "Sessions" tab, which is useful
 * mainly when the left drawer has been collapsed. */
export function SessionListInline({ sessions, selectedId, onSelect }: {
  sessions: SessionSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (sessions.length === 0) {
    return <p className={styles.empty}>No sessions observed yet.</p>;
  }
  return (
    <ul className={styles.list}>
      {sessions.map((session) => (
        <li key={session.session_id}>
          <button
            className={session.session_id === selectedId ? styles.itemActive : styles.item}
            onClick={() => onSelect(session.session_id)}
          >
            <span className={session.status === "live" ? styles.dotLive : styles.dotClosed} />
            <span className={styles.label}>{session.session_id}</span>
            <span className={styles.sublabel}>{session.student_id}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
