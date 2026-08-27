import styles from "./EvidenceChips.module.css";

/** Renders the actual "{session_id}#{turn}" citations a long-term claim
 * carries — this IS the answer to "what went from short-term to long-term,
 * in what form": every claim here is a literal pointer back to a specific
 * turn in a specific session's Episodic record, not a vague summary.
 * Clicking a chip jumps to (and highlights) that turn if it's the
 * currently-open session; otherwise it just shows where it came from. */
export function EvidenceChips({ evidence, onJumpToTurn }: { evidence: string[]; onJumpToTurn?: (sessionId: string, turn: number) => void }) {
  if (evidence.length === 0) return null;
  return (
    <div className={styles.row}>
      {evidence.map((ref) => {
        const [sessionId, turnPart] = ref.split("#");
        const turn = Number(turnPart);
        const clickable = onJumpToTurn && !Number.isNaN(turn);
        return clickable ? (
          <button key={ref} className={styles.chipButton} onClick={() => onJumpToTurn(sessionId, turn)} title={`Jump to turn ${turn} in ${sessionId}`}>
            {sessionId.length > 14 ? `${sessionId.slice(0, 14)}…` : sessionId}#{turn}
          </button>
        ) : (
          <span key={ref} className={styles.chip}>{ref}</span>
        );
      })}
    </div>
  );
}
