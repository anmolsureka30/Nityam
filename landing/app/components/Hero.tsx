import { APP_LOGIN_URL, APP_SIGNUP_URL } from "../lib/config";
import { BoardSketch, TutorPortrait } from "./Illustrations";
import styles from "./styles.module.css";

export default function Hero() {
  return (
    <section className={styles.hero}>
      <div className={styles.heroInner}>
        <h1 className={styles.heroTitle}>
          A tutor that teaches like a great one does: personalized to you,
          grounded in what you're actually studying.
        </h1>

        <p className={styles.heroTagline}>Learn the way you want.</p>

        {/* She is the product and the hero was entirely type. Aria-hidden
            here only: the same drawing is labelled where it carries the
            argument, and repeating the label in the headline block would
            interrupt the sentence a screen reader is mid-way through. */}
        <div className={styles.heroFigure} aria-hidden="true">
          <TutorPortrait className={styles.heroTutor} />
          <BoardSketch className={styles.heroBoard} />
        </div>

        <p className={styles.heroSubtitle}>
          Nityam teaches the way a good tutor does (asking before telling,
          checking understanding with a question before moving on), grounded
          in the textbooks and lectures you're actually covering, so one
          conversation can hold learning something new, revising what's
          shaky, and chasing a question you're curious about.
        </p>

        <div className={styles.heroCtas}>
          {/* Says what pressing it does. "Start learning free" implied you
              could begin reading right there; you cannot, since the tutor needs an
              account before it has anywhere to keep what it learns about you,
              which is the whole product. Better to be plain about it here
              than to have the login form say it for us. */}
          <a href={APP_SIGNUP_URL} className={styles.btnAccent}>
            Create your free account
          </a>
          <a href="#how" className={styles.btnOutline}>
            See how it works
          </a>
        </div>

        <p className={styles.ctaNote}>
          Free to start. Sign up with Google or an email address; Nityam needs
          an account to remember what you have covered.{" "}
          <a href={APP_LOGIN_URL} className={styles.ctaNoteLink}>
            Already have one? Sign in
          </a>
        </p>

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
                  <span style={{ color: "var(--warn)", fontWeight: 600 }}>
                    re-teaching
                  </span>
                </div>
                <div className={styles.progressTrack}>
                  <div
                    className={styles.progressFill}
                    style={{ width: "38%", background: "var(--warn)" }}
                  />
                </div>
              </div>
              <div>
                <div className={styles.progressRow}>
                  <span>Diya, ready to go further</span>
                  <span style={{ color: "var(--good)", fontWeight: 600 }}>
                    harder set
                  </span>
                </div>
                <div className={styles.progressTrack}>
                  <div
                    className={styles.progressFill}
                    style={{ width: "86%", background: "var(--good)" }}
                  />
                </div>
              </div>
              <div>
                <div className={styles.progressRow}>
                  <span>Class mastery this week</span>
                  <span style={{ color: "var(--good)", fontWeight: 600 }}>
                    up 22%
                  </span>
                </div>
                <div className={styles.progressTrack}>
                  <div
                    className={styles.progressFill}
                    style={{ width: "64%", background: "var(--accent)" }}
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
