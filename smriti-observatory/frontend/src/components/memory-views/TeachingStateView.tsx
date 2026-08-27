import type { TeachingMemoryState } from "../../lib/types";
import { CoverageBadge, DoubtStatusBadge } from "../Badge";
import { EvidenceChips } from "../EvidenceChips";
import { jumpToTurn } from "../../lib/jumpToTurn";
import styles from "./TeachingStateView.module.css";

export function TeachingStateView({ state }: { state: TeachingMemoryState | null }) {
  if (!state) {
    return <p className={styles.empty}>No teaching state yet — created the first time a session closes.</p>;
  }
  const covered = Object.entries(state.covered);
  return (
    <div className={styles.container}>
      <section className={styles.section}>
        <h4 className={styles.heading}>Teaching mode</h4>
        <span className={styles.modeChip}>{state.teaching_style.current_mode.replace("-", " ")}</span>
      </section>

      <section className={styles.section}>
        <h4 className={styles.heading}>Curriculum coverage ({covered.length})</h4>
        {covered.length === 0 ? (
          <p className={styles.empty}>Nothing covered yet.</p>
        ) : (
          <ul className={styles.list}>
            {covered.map(([conceptId, c]) => (
              <li key={conceptId} className={styles.row}>
                <span className={styles.conceptId}>{conceptId}</span>
                <CoverageBadge value={c.status} />
                {c.elements_used.length > 0 && (
                  <span className={styles.elements}>{c.elements_used.join(", ")}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className={styles.section}>
        <h4 className={styles.heading}>Open doubts ({state.open_doubts.length})</h4>
        {state.open_doubts.length === 0 ? (
          <p className={styles.empty}>None.</p>
        ) : (
          <ul className={styles.doubtList}>
            {state.open_doubts.map((doubt, i) => (
              <li key={i} className={styles.doubtCard}>
                <div className={styles.doubtHead}>
                  <span className={styles.conceptId}>{doubt.concept_id}</span>
                  <DoubtStatusBadge value={doubt.status} />
                </div>
                <p className={styles.doubtText}><strong>Doubt:</strong> {doubt.doubt}</p>
                <p className={styles.doubtText}><strong>Correct:</strong> {doubt.correct_understanding}</p>
                <EvidenceChips evidence={doubt.evidence} onJumpToTurn={jumpToTurn} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
