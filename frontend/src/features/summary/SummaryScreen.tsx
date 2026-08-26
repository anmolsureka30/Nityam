import { useNavigate } from "react-router-dom";
import { Shell } from "../../components/Shell";
import { Button, Card, Label, MasteryBar } from "../../components/ui";
import { summary } from "../../lib/data";
import s from "./SummaryScreen.module.css";

/* The recap exists to answer one question the student actually has: was that
 * worth twenty minutes? So it leads with what moved, and ends with what
 * happens tomorrow in the room they have to walk into. */
export default function SummaryScreen() {
  const nav = useNavigate();

  return (
    <Shell>
      <div className={s.wrap}>
        <Label>Session ended · {summary.endedAt} · {summary.minutes} min</Label>
        <h1 className={s.headline}>{summary.headline}</h1>

        <Card size="lg" style={{ marginTop: 26 }}>
          <Label>What moved</Label>
          <div className={s.moved}>
            {summary.moved.map((m) => (
              <div className={s.movedRow} key={m.conceptName}>
                <div className={s.movedHead}>
                  <span className={s.movedName}>{m.conceptName}</span>
                  <span className={s.movedNums}>
                    <span className={s.from}>{m.from === null ? "—" : `${m.from}%`}</span>
                    <span className={s.arrow}>→</span>
                    <span className={s.to}>{m.to}%</span>
                  </span>
                </div>
                <MasteryBar pct={m.to} hideName />
              </div>
            ))}
          </div>
        </Card>

        <Card size="lg" style={{ marginTop: 14 }}>
          <Label tone="accent">The moment</Label>
          <p className={s.momentText}>“{summary.moment}”</p>
        </Card>

        <div className={s.grid}>
          <Card size="lg" quiet>
            <Label tone="warn">Still open</Label>
            <p className={s.body}>{summary.stillOpen}</p>
          </Card>
          <Card size="lg" quiet>
            <Label>Tomorrow in class</Label>
            <p className={s.body}>{summary.tomorrow}</p>
          </Card>
        </div>

        <div className={s.actions}>
          <Button variant="primary" onClick={() => nav("/")}>Done for tonight</Button>
          <Button onClick={() => nav("/readiness")}>See exam readiness</Button>
        </div>
      </div>
    </Shell>
  );
}
