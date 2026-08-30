import { APP_LOGIN_URL, APP_SIGNUP_URL } from "../lib/config";
import styles from "./styles.module.css";

/* Two doors, and the one for new visitors is the filled one. The header used
 * to offer a single "Sign in" button, which is the wrong door for almost
 * everyone arriving on a landing page: they have no account yet, and being
 * asked for a password you never set reads as a dead end. */
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
        <a href={APP_LOGIN_URL} className={styles.headerLink}>
          Sign in
        </a>
        <a href={APP_SIGNUP_URL} className={styles.btnPrimary}>
          Create account
        </a>
      </div>
    </header>
  );
}
