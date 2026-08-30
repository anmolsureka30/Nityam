import styles from "./styles.module.css";

export default function Footer() {
  return (
    <footer className={styles.footer}>
      <div className={styles.footerInner}>
        <div className={styles.footerLogo}>
          <span className={styles.footerLogoMark}>NITYAM</span>
          <span className={styles.footerLogoDevanagari}>नित्यम्</span>
        </div>
        <div>Every classroom in India, powered by Nityam.</div>
        <div style={{ display: "flex", gap: "16px" }}>
          <a
            href="https://www.linkedin.com/in/thearnavprasad/"
            target="_blank"
            rel="noopener noreferrer"
          >
            Arnav Prasad
          </a>
          <a
            href="https://www.linkedin.com/in/anmolsureka/"
            target="_blank"
            rel="noopener noreferrer"
          >
            Anmol Sureka
          </a>
        </div>
      </div>
    </footer>
  );
}
