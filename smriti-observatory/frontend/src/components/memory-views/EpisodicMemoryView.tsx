import type { SessionLog } from "../../lib/types";
import { TurnTranscript } from "./TurnTranscript";
import styles from "./EpisodicMemoryView.module.css";

function formatDuration(startedAt: string, endedAt: string): string {
  const ms = new Date(endedAt).getTime() - new Date(startedAt).getTime();
  const minutes = Math.floor(ms / 60000);
  const seconds = Math.floor((ms % 60000) / 1000);
  return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
}

export function EpisodicMemoryView({ log }: { log: SessionLog | null }) {
  if (!log) {
    return <p className={styles.empty}>Not written yet — the episodic record is created once, when the session closes.</p>;
  }
  return (
    <div className={styles.container}>
      <div className={styles.meta}>
        <span className={styles.metaItem}><strong>{log.turns.length}</strong> turns</span>
        <span className={styles.metaItem}>{formatDuration(log.started_at, log.ended_at)}</span>
        <span className={styles.metaItem}>ended {new Date(log.ended_at).toLocaleTimeString()}</span>
      </div>
      {log.summary && <p className={styles.summary}>{log.summary}</p>}
      <TurnTranscript turns={log.turns} />
    </div>
  );
}
