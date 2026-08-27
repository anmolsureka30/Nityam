import type { DPMProfile } from "../../lib/types";
import { MasteryBadge, StrengthBadge } from "../Badge";
import { EvidenceChips } from "../EvidenceChips";
import { jumpToTurn } from "../../lib/jumpToTurn";
import styles from "./LearnerProfileView.module.css";

export function LearnerProfileView({ profile }: { profile: DPMProfile | null }) {
  if (!profile) {
    return <p className={styles.empty}>No learner profile yet — created the first time a session closes.</p>;
  }
  const weaknesses = Object.entries(profile.weaknesses);
  return (
    <div className={styles.container}>
      {(profile.persona.preferred_pace || profile.persona.language_mix || profile.persona.interests.length > 0) && (
        <section className={styles.section}>
          <h4 className={styles.heading}>Persona</h4>
          <div className={styles.personaRow}>
            {profile.persona.preferred_pace && <span className={styles.personaItem}>pace: {profile.persona.preferred_pace}</span>}
            {profile.persona.language_mix && <span className={styles.personaItem}>language: {profile.persona.language_mix}</span>}
            {profile.persona.interests.map((i) => (
              <span key={i} className={styles.personaItem}>interest: {i}</span>
            ))}
          </div>
        </section>
      )}

      <section className={styles.section}>
        <h4 className={styles.heading}>Concept mastery ({weaknesses.length})</h4>
        {weaknesses.length === 0 ? (
          <p className={styles.empty}>No concepts tracked yet.</p>
        ) : (
          <ul className={styles.conceptList}>
            {weaknesses.map(([conceptId, w]) => (
              <li key={conceptId} className={styles.conceptRow}>
                <div className={styles.conceptRowTop}>
                  <span className={styles.conceptId}>{conceptId}</span>
                  <span className={styles.badges}>
                    <MasteryBadge value={w.mastery} />
                    <StrengthBadge value={w.strength} />
                  </span>
                </div>
                <EvidenceChips evidence={w.evidence} onJumpToTurn={jumpToTurn} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className={styles.section}>
        <h4 className={styles.heading}>Self-reflections ({profile.self_reflection.length})</h4>
        {profile.self_reflection.length === 0 ? (
          <p className={styles.empty}>None yet.</p>
        ) : (
          <ul className={styles.noteList}>
            {profile.self_reflection.map((note, i) => (
              <li key={i} className={note.status === "superseded" ? styles.noteSuperseded : styles.note}>
                {note.note}
                {note.status === "superseded" && <span className={styles.supersededTag}>superseded</span>}
                <EvidenceChips evidence={note.evidence} onJumpToTurn={jumpToTurn} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
