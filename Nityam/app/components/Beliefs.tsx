import styles from "./styles.module.css";

const beliefs = [
  {
    title: "The teacher is the centre",
    body: "The best thing about an Indian classroom is the person standing at the board. We build instruments for her, not around her.",
  },
  {
    title: "The real syllabus, not a generic one",
    body: "If what a child studies at home does not match what was taught at school, it is just one more thing to keep up with.",
  },
  {
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
