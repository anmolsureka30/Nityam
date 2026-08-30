import { ClassOfForty, TwoSyllabuses, WideningGap } from "./Illustrations";
import styles from "./styles.module.css";

/* A number and a paragraph is an assertion; the drawing under it is the
   shape of the claim: forty dots with the edges missed, two lines coming
   apart over four years, two syllabuses that never meet. */
const stats = [
  {
    art: ClassOfForty,
    number: "1:40",
    caption:
      "A teacher has forty students and forty minutes. The middle of the class gets taught. The fastest and the slowest get missed.",
  },
  {
    art: WideningGap,
    number: "4 yrs",
    caption:
      "A small gap in Class VI turns into a failed paper in Class X. By then it takes a year of tuition to repair.",
  },
  {
    art: TwoSyllabuses,
    number: "0%",
    caption:
      "Almost no study app knows what was taught in class that day. So the child ends up learning the same subject twice, two different ways.",
  },
];

export default function ProblemStats() {
  return (
    <section className={`${styles.section} ${styles.bgWhite}`}>
      <div className={styles.sectionInner}>
        <h2 className={styles.h2}>
          One lesson. Forty students. Everyone learns at a different speed.
        </h2>
        <p className={styles.sectionLede}>
          The lesson moves at one speed. The students who keep up do well. A
          student who misses one step carries that gap into the next chapter,
          and nobody notices until the exam. Study apps do not fix this,
          because they teach their own version of the syllabus instead of the
          lesson the child actually sat through that morning.
        </p>
        <div className={styles.statsGrid}>
          {stats.map((stat) => (
            <div key={stat.number} className={styles.card}>
              <div className={styles.statNumber}>{stat.number}</div>
              <p className={styles.statCaption}>{stat.caption}</p>
              <stat.art className={styles.statArt} />
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
