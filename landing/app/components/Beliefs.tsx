import {
  AttentionForEveryone, TeacherAtCentre, TextbookFigure,
} from "./Illustrations";
import styles from "./styles.module.css";

/* One drawing per belief, inside the belief it belongs to.
 *
 * There were two drawings for three beliefs, floated above the grid, and
 * neither depicted any of them: a page of a textbook and a simulation, both
 * true of the product and both silent about what was written underneath.
 * A picture that does not argue the sentence next to it is worse than none,
 * because the reader spends a moment trying to connect them.
 *
 * These three do argue theirs: who is subordinate to whom, that the page at
 * home is the page from school, and that the change is in WHO gets a tutor. */
const beliefs = [
  {
    art: TeacherAtCentre,
    title: "The teacher is the centre",
    body: "The best thing about an Indian classroom is the person standing at the board. We build instruments for her, not around her.",
  },
  {
    /* This one was already exactly right, it was just in the wrong place:
       the child's own NCERT page, and the figure lifted off it onto the
       board, IS "the real syllabus, not a generic one". */
    art: TextbookFigure,
    title: "The real syllabus, not a generic one",
    body: "If what a child studies at home does not match what was taught at school, it is just one more thing to keep up with.",
  },
  {
    art: AttentionForEveryone,
    title: "Attention should not be a privilege",
    body: "What a private tutor gives a few children, software can give everyone. Private schools first, government schools next, same product either way.",
  },
];

export default function Beliefs() {
  return (
    <section className={`${styles.section} ${styles.bgCream}`}>
      <div className={styles.sectionInnerWide}>
        <h2
          className={styles.h2}
          style={{ fontSize: "42px", marginBottom: "40px", maxWidth: "none" }}
        >
          What we believe
        </h2>
        <div className={styles.beliefsGrid}>
          {beliefs.map((belief) => (
            <div key={belief.title} className={styles.beliefItem}>
              <belief.art className={styles.beliefArt} />
              <h3 className={styles.h3}>{belief.title}</h3>
              <p className={styles.bodyText} style={{ fontSize: "16px" }}>
                {belief.body}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
