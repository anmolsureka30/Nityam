import { useNavigate } from "react-router-dom";
import { Shell } from "../../components/Shell";
import { Label, MasteryInline } from "../../components/ui";
import {
  concepts, daysToUnitTest, readinessPattern, readinessPct, readinessRecommendation,
} from "../../lib/data";
import s from "./ReadinessScreen.module.css";

export default function ReadinessScreen() {
  const nav = useNavigate();
  const examinable = concepts.filter((c) => c.examinable);
  // Worst first: the ranking is the advice.
  const rows = [...examinable].sort((a, b) => a.mastery - b.mastery);
  const worst = rows[0];

  return (
    <Shell back={{ to: "/", label: "Home" }}>
      <div className={s.head}>
        <div>
          <h1 className={s.title}>Unit test in {daysToUnitTest} days</h1>
          <p className={s.sub}>Motion in a plane · {examinable.length} concepts examinable</p>
        </div>
        <div>
          <Label>Readiness</Label>
          <div className={s.score}>
            <span className={s.scoreValue}>{readinessPct}%</span>
          </div>
        </div>
      </div>

      <table className={s.table}>
        <thead>
          <tr>
            <th>Concept</th>
            <th className={s.barCell}>Mastery</th>
            <th>Your main issue</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.id} className={c.id === worst.id ? s.rowWorst : undefined}>
              <td>
                <div className={s.name}>{c.name}</div>
                <div className={s.id}>{c.id}</div>
              </td>
              <td className={s.barCell}>
                <MasteryInline pct={c.mastery} />
              </td>
              <td className={s.issue}>{c.issue}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className={s.lower}>
        <div className={s.pattern}>
          <Label>The pattern behind it</Label>
          <p className={s.patternText}>{readinessPattern}</p>
        </div>
        <button
          type="button"
          className={s.next}
          onClick={() => nav(`/session?mode=exam&concept=${worst.id}`)}
        >
          <span className={s.nextLabel}>Recommended next</span>
          <span className={s.recText}>{readinessRecommendation}</span>
          <span className={s.nextGo}>Start that session <span aria-hidden="true">→</span></span>
        </button>
      </div>
    </Shell>
  );
}
