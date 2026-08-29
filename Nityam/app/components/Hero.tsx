import { APP_LOGIN_URL } from "../lib/config";
import styles from "./styles.module.css";

export default function Hero() {
  return (
    <section className={styles.hero}>
      <div className={styles.heroInner}>
        <div className={styles.badge}>
          <span className={styles.badgeDot} />
          Piloting now with Tier-1 schools in India
        </div>

        <h1 className={styles.heroTitle}>
          A personal teacher for every student, built on what their class
          actually taught today.
        </h1>

        <p className={styles.heroTagline}>Learn the way you want.</p>

        <p className={styles.heroSubtitle}>
          Nityam records the lesson in the classroom, learns how each student
          thinks, and teaches that same lesson back to them at their own
          speed. Teachers can see who is ahead, who is stuck, and what to do
          about it the next day.
        </p>

        <div className={styles.heroCtas}>
          <a href={APP_LOGIN_URL} className={styles.btnLime}>
            Start learning free
          </a>
          <a href="#how" className={styles.btnOutline}>
            See how it works
          </a>
        </div>

        <div className={styles.mockCard}>
          <div className={styles.mockCardHeader}>
            <span className={styles.mockCardDot} />
            <span className={styles.mockCardLabel}>
              Class VIII · Mathematics · Period 3
            </span>
          </div>
          <div className={styles.mockCardGrid}>
            <div>
              <div className={styles.mockCardHandwritten}>
                Today on the board:
                <br />
                completing the square
              </div>
              <p className={styles.mockCardCaption}>
                Nityam caught the example the teacher solved and the two
                shortcuts she used, then built tonight&apos;s practice around
                them.
              </p>
            </div>
            <div className={styles.progressList}>
              <div>
                <div className={styles.progressRow}>
                  <span>Aarav, gap in factoring</span>
                  <span style={{ color: "var(--orange)", fontWeight: 600 }}>
                    re-teaching
                  </span>
                </div>
                <div className={styles.progressTrack}>
                  <div
                    className={styles.progressFill}
                    style={{ width: "38%", background: "var(--orange)" }}
                  />
                </div>
              </div>
              <div>
                <div className={styles.progressRow}>
                  <span>Diya, ready to go further</span>
                  <span style={{ color: "var(--violet)", fontWeight: 600 }}>
                    harder set
                  </span>
                </div>
                <div className={styles.progressTrack}>
                  <div
                    className={styles.progressFill}
                    style={{ width: "86%", background: "var(--lavender)" }}
                  />
                </div>
              </div>
              <div>
                <div className={styles.progressRow}>
                  <span>Class mastery this week</span>
                  <span style={{ color: "var(--violet)", fontWeight: 600 }}>
                    up 22%
                  </span>
                </div>
                <div className={styles.progressTrack}>
                  <div
                    className={styles.progressFill}
                    style={{ width: "64%", background: "var(--lime)" }}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
