import { TeacherShell } from "../../components/Shell";
import { Button, Card, Label, Stat } from "../../components/ui";
import { teacherClass, teacherInsight } from "../../lib/data";
import s from "./teacher.module.css";

/* Deliberately one screen with two things on it. A teacher checks this between
 * classes; anything longer than thirty seconds does not get read. */
export default function TeacherInsights() {
  return (
    <TeacherShell>
      <div className={s.insight}>
        <h1 className={s.title}>Class insights</h1>
        <div className={s.meta}>One thing to know, one thing to do. Thirty seconds.</div>

        <Card size="lg" style={{ marginTop: 26 }}>
          <Label>Observation</Label>
          <p className={s.insightBig}>{teacherInsight.observation}</p>
        </Card>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginTop: 14 }}>
          <Stat
            label="Recalled formula"
            value={teacherInsight.recalledFormula}
            note="Can state R = v² sin(2θ) / g unprompted"
          />
          <Stat
            label="Axes treated as coupled"
            value={`${teacherClass.sharedMisconceptionCount}/${teacherClass.cohort}`}
            note="Same students, different question"
          />
        </div>

        <div className={s.bell} style={{ marginTop: 14 }}>
          <div className={s.bellLabel}>Do this tomorrow</div>
          <p className={s.bellText}>{teacherInsight.action}</p>
        </div>

        <div style={{ display: "flex", gap: 10, marginTop: 22 }}>
          <Button variant="primary">Add to tomorrow's plan</Button>
          <Button>Share with department</Button>
        </div>
      </div>
    </TeacherShell>
  );
}
