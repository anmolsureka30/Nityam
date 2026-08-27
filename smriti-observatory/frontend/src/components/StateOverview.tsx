import type { SessionState } from "../lib/types";
import { TIER_DESCRIPTION, TIER_LABEL, RECORD_TYPE_LABEL } from "../lib/labels";
import { WorkingMemoryView } from "./memory-views/WorkingMemoryView";
import { EpisodicMemoryView } from "./memory-views/EpisodicMemoryView";
import { LearnerProfileView } from "./memory-views/LearnerProfileView";
import { TeachingStateView } from "./memory-views/TeachingStateView";
import styles from "./StateOverview.module.css";

/** The current snapshot of every memory kind this student/session has,
 * right now — distinct from the Timeline (which is the *history* of how
 * it got here). Long-term memory is shown as its three real, distinct
 * kinds rather than one blob. */
export function StateOverview({ state }: { state: SessionState | null }) {
  if (!state) {
    return <p className={styles.empty}>Select a session to see its current memory state.</p>;
  }
  return (
    <div className={styles.container}>
      <section className={styles.tierSection}>
        <header className={styles.tierHeader}>
          <span className={`${styles.tierDot} ${styles.workflow}`} />
          <h3 className={styles.tierTitle}>{TIER_LABEL.workflow}</h3>
        </header>
        <p className={styles.tierDesc}>{TIER_DESCRIPTION.workflow}</p>
        <div className={styles.kindCard}>
          <h4 className={styles.kindTitle}>{RECORD_TYPE_LABEL.turn_buffer}</h4>
          <WorkingMemoryView turnBuffer={state.workflow.turn_buffer} sessionId={state.session_id} />
        </div>
      </section>

      <section className={styles.tierSection}>
        <header className={styles.tierHeader}>
          <span className={`${styles.tierDot} ${styles.episodic}`} />
          <h3 className={styles.tierTitle}>{TIER_LABEL.episodic}</h3>
        </header>
        <p className={styles.tierDesc}>{TIER_DESCRIPTION.episodic}</p>
        <div className={styles.kindCard}>
          <h4 className={styles.kindTitle}>{RECORD_TYPE_LABEL.session_log}</h4>
          <EpisodicMemoryView log={state.episodic.session_log} />
        </div>
      </section>

      <section className={styles.tierSection}>
        <header className={styles.tierHeader}>
          <span className={`${styles.tierDot} ${styles.longTerm}`} />
          <h3 className={styles.tierTitle}>{TIER_LABEL.long_term}</h3>
        </header>
        <p className={styles.tierDesc}>{TIER_DESCRIPTION.long_term}</p>

        <div className={styles.kindCard}>
          <h4 className={styles.kindTitle}>{RECORD_TYPE_LABEL.dpm_profile}</h4>
          <LearnerProfileView profile={state.long_term.dpm_profile} />
        </div>

        <div className={styles.kindCard}>
          <h4 className={styles.kindTitle}>{RECORD_TYPE_LABEL.teaching_memory}</h4>
          <TeachingStateView state={state.long_term.teaching_memory} />
        </div>
      </section>
    </div>
  );
}
