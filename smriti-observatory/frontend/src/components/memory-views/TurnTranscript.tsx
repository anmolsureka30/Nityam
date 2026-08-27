import type { Turn } from "../../lib/types";
import styles from "./TurnTranscript.module.css";

export function turnDomId(sessionId: string, turn: number): string {
  return `turn-${sessionId}-${turn}`;
}

/** Shared by Working Memory (live turn_buffer) and Episodic Memory
 * (closed session_log.turns) — same shape, same rendering. A chat
 * transcript, not a JSON dump. Each turn gets a stable DOM id so a
 * long-term claim's evidence citation (EvidenceChips) can scroll straight
 * to the turn that produced it — the concrete answer to "what went from
 * short-term to long-term, in what form." */
export function TurnTranscript({ turns, sessionId }: { turns: Turn[]; sessionId: string }) {
  if (turns.length === 0) {
    return <p className={styles.empty}>No turns yet.</p>;
  }
  return (
    <ol className={styles.list}>
      {turns.map((turn) => (
        <li key={turn.turn} id={turnDomId(sessionId, turn.turn)} className={turn.role === "student" ? styles.student : styles.tutor}>
          <div className={styles.rowHead}>
            <span className={styles.turnNumber}>#{turn.turn}</span>
            <span className={styles.role}>{turn.role}</span>
            {turn.concept_id && <span className={styles.concept}>{turn.concept_id}</span>}
            {turn.artifact_id && <span className={styles.artifact}>📎 {turn.artifact_id}</span>}
          </div>
          <p className={styles.text}>{turn.text}</p>
        </li>
      ))}
    </ol>
  );
}
