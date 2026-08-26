import { TeacherShell } from "../../components/Shell";
import { Button, Card, Label, MasteryBar, Stat } from "../../components/ui";
import { teacherClass } from "../../lib/data";
import s from "./teacher.module.css";

export default function TeacherClassScreen() {
  const c = teacherClass;
  const maxCount = Math.max(...c.distribution.map((d) => d.count));

  return (
    <TeacherShell>
      <div className={s.head}>
        <div>
          <h1 className={s.title}>{c.topic}</h1>
          <div className={s.meta}>{c.meta}</div>
        </div>
        <div className={s.headRight}>
          <Label>Updated {c.updatedAt}</Label>
          <Button size="sm">Export</Button>
        </div>
      </div>

      <div className={s.tiles}>
        <Stat
          label="Class understanding"
          value={`${c.understanding}%`}
          note={`${c.belowHalf} of ${c.cohort} below 50%`}
        />
        <Stat
          label="Shared misconception"
          value={<span style={{ fontSize: 19 }}>{c.sharedMisconception}</span>}
          note={`${c.sharedMisconceptionCount} students`}
        />
        <Stat
          label="Revision time · median"
          value={`${c.medianRevisionMin} min`}
          note={`${c.cohort - c.didNotOpen.length} of ${c.cohort} revised at home`}
        />
      </div>

      <section className={s.section}>
        <div className={s.sectionHead}>
          <span className={s.sectionTitle}>Concepts taught today</span>
          <Label>From audio + board capture</Label>
        </div>
        <table className={s.table}>
          <thead>
            <tr>
              <th>Concept</th>
              <th className={s.barCell}>Class mastery</th>
              <th>Trend</th>
              <th>Board time</th>
            </tr>
          </thead>
          <tbody>
            {c.concepts.map((con) => (
              <tr key={con.id}>
                <td className={s.name}>{con.name}</td>
                <td className={s.barCell}>
                  <MasteryBar pct={con.classMastery} hideName />
                  <div className={s.num} style={{ marginTop: 6 }}>{con.classMastery}%</div>
                </td>
                <td>
                  <span className={`${s.trend} ${con.trend >= 0 ? s.up : s.down}`}>
                    {con.trend >= 0 ? "▲" : "▼"} {Math.abs(con.trend)}
                  </span>
                </td>
                <td className={s.num}>{con.boardMinutes} min</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <div className={s.lower}>
        <Card size="lg">
          <Label>Mastery distribution</Label>
          <div className={s.dist}>
            {c.distribution.map((d, i) => (
              <div className={s.distCol} key={d.band}>
                <span className={s.distCount}>{d.count}</span>
                <span
                  className={`${s.distBar} ${i < 2 ? s.distBarLow : ""}`}
                  style={{ height: `${(d.count / maxCount) * 100}%` }}
                />
                <span className={s.distLabel}>{d.band}</span>
              </div>
            ))}
          </div>
        </Card>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div className={s.bell}>
            <div className={s.bellLabel}>Before the bell</div>
            <p className={s.bellText}>{c.beforeTheBell}</p>
          </div>
          <Card size="lg">
            <Label tone="warn">Did not open Nityam</Label>
            <div className={s.names}>
              {c.didNotOpen.map((n) => (
                <span className={s.nameChip} key={n}>{n}</span>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </TeacherShell>
  );
}
