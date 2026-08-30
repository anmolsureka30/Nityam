import {
  ClassroomCapture, OneToOne, ProfileBuild, TeacherView,
} from "./Illustrations";
import styles from "./styles.module.css";

/* Each step gets the picture of itself. Four cards of text alone left the
   section reading as a wall, and the drawings carry what the words cannot:
   that the board is a real page, that the profile is per-student and rebuilt
   daily, that the class view names who is stuck. */
const steps = [
  {
    art: ClassroomCapture,
    title: "Capture the lesson",
    body: "A camera and mic in the classroom record the lesson: the teacher's examples, her words, what she wrote on the board.",
  },
  {
    art: ProfileBuild,
    title: "Build the profile",
    body: "A picture of each student that updates every day: what they have understood, where they are stuck, how fast they work, which explanation clicks.",
  },
  {
    art: OneToOne,
    title: "Teach one to one",
    body: "The AI tutor explains today's topic again, in the way that works for this student, then sets practice for the exam they are preparing for.",
  },
  {
    art: TeacherView,
    title: "Hand it back to the teacher",
    body: "The next morning she knows exactly who needs five extra minutes, and on what. The class itself gets better.",
  },
];

export default function HowItWorks() {
  return (
    <section id="how" className={`${styles.section} ${styles.bgCream}`}>
      <div className={styles.sectionInnerWide}>
        <h2 className={styles.h2} style={{ marginBottom: "18px" }}>
          Nityam closes the loop between the classroom and the child.
        </h2>
        <p className={styles.sectionLede} style={{ marginBottom: "52px" }}>
          Four things happen every school day, on your school&apos;s own
          curriculum.
        </p>
        <div className={styles.howGrid}>
          {steps.map((step, i) => (
            <div key={step.title} className={styles.howCard}>
              <step.art className={styles.howArt} />
              <div className={styles.howNum}>{i + 1}</div>
              <h3 className={styles.h3}>{step.title}</h3>
              <p className={styles.bodyText}>{step.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
