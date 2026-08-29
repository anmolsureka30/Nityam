import styles from "./styles.module.css";

export default function AudienceSplit() {
  return (
    <section className={`${styles.section} ${styles.bgPanel}`}>
      <div className={`${styles.sectionInnerWide} ${styles.audienceGrid}`}>
        <div className={`${styles.panel} ${styles.panelLight}`}>
          <div className={`${styles.eyebrow} ${styles.eyebrowOrange}`}>
            For students and parents
          </div>
          <h3 className={styles.panelTitle}>A tutor who sat in the class.</h3>
          <p className={styles.panelBody}>
            Not a chatbot pulling answers off the internet. Nityam knows
            which chapter was covered, which example went on the board, and
            which steps your child did not follow. It starts right there, in
            the language they think in, whenever they sit down to study.
          </p>
        </div>
        <div className={`${styles.panel} ${styles.panelDark}`}>
          <div className={`${styles.eyebrow} ${styles.eyebrowLime}`}>
            For teachers and schools
          </div>
          <h3 className={styles.panelTitle}>The class, finally legible.</h3>
          <p className={styles.panelBodyLight}>
            A live view of who has understood today&apos;s topic and who is
            quietly stuck, section by section. Nityam does not replace any
            teaching. It only takes out the guesswork, and gives the school a
            clear record to show parents.
          </p>
        </div>
      </div>
    </section>
  );
}
