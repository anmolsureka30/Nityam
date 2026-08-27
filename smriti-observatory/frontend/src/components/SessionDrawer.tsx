import styles from "./SessionDrawer.module.css";

export interface SessionSummary {
  session_id: string;
  student_id: string;
  status: "live" | "closed";
  started_at: string;
  last_event_at: string;
}

interface SessionDrawerProps {
  sessions: SessionSummary[];
  selectedId: string | null;
  onSelect: (sessionId: string) => void;
}

export function SessionDrawer({ sessions, selectedId, onSelect }: SessionDrawerProps) {
  return (
    <nav className={styles.drawer} aria-label="Sessions">
      <div className={styles.header}>Sessions</div>
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
    </nav>
  );
}
