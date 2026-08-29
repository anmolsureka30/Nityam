import styles from "./styles.module.css";

export default function Mission() {
  return (
    <section
      className={`${styles.section} ${styles.bgWhiteTop} ${styles.textCenter}`}
      style={{ padding: "100px 32px" }}
    >
      <div style={{ maxWidth: "900px", margin: "0 auto" }}>
        <div className={styles.missionQuoteMark}>
          नित्यम् means daily, constant, without pause
        </div>
        <p className={styles.missionQuote}>
          &ldquo;Every classroom in India, powered by Nityam&rdquo;
        </p>
        <p className={styles.missionBody}>
          We start with Tier-1 private schools because that is where we can
          prove it fastest. The goal is bigger than that: individual
          attention for every student in the country, private and government
          alike.
        </p>
      </div>
    </section>
  );
}
