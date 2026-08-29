import { APP_LOGIN_URL } from "../lib/config";
import styles from "./styles.module.css";

export default function Header() {
  return (
    <header className={styles.header}>
      <div className={styles.logoGroup}>
        <span className={styles.logoMark}>NITYAM</span>
        <span className={styles.logoDevanagari}>नित्यम्</span>
      </div>
      <div className={styles.headerRight}>
        <a href="#waitlist" className={styles.headerLink}>
          For schools
        </a>
        <a href={APP_LOGIN_URL} className={styles.btnPrimary}>
          Sign in
        </a>
      </div>
    </header>
  );
}
