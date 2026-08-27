import { useNavigate } from "react-router-dom";
import { Shell } from "../../components/Shell";
import { ActionCard, Card, Chip, Label, MasteryBar } from "../../components/ui";
import { classRecap, concepts, daysToUnitTest, readinessPct, student } from "../../lib/data";
import s from "./HomeScreen.module.css";

function greetingFor(hour: number) {
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

export default function HomeScreen() {
  const nav = useNavigate();
  const greeting = greetingFor(new Date().getHours());

  // The three weakest examinable concepts, worst first — this is the list the
  // student should act on, not an inventory of everything they have studied.
  const weakest = [...concepts]
    .filter((c) => c.examinable)
    .sort((a, b) => a.mastery - b.mastery)
    .slice(0, 3);

  const target = concepts.find((c) => c.id === "PHY-11-K2")!;

  return (
    <Shell>
      <div className={s.hero}>
        <div>
          <h1 className={s.greeting}>{greeting}, {student.firstName}.</h1>
          <p className={s.subline}>
            Your class covered {classRecap.subject.toLowerCase()} today. I listened to all of it —
            there are two things worth going over.
          </p>
        </div>
        <div className={s.countdown}>
          <Label>Unit test</Label>
          <span className={s.countdownValue}>{daysToUnitTest} days</span>
        </div>
      </div>

      <div className={s.actions}>
        <ActionCard
          primary
          eyebrow="Start here"
          title="Revise today's class"
          body="Projectile motion — range, angle, symmetry. We pick up exactly where Mr. Deshpande ran out of time."
          footer={
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
              <span style={{ fontWeight: 600, color: "var(--accent-deep)" }}>Begin session</span>
              <Label>≈ 20 min</Label>
            </div>
          }
          onClick={() => nav(`/intensity/${target.id}`)}
        />
        <ActionCard
          eyebrow="Anytime"
          title="Ask a doubt"
          body="Anything from the board — today, or three weeks ago."
          footer={<Label>⌨ Type or speak →</Label>}
          onClick={() => nav("/session?mode=doubt")}
        />
        <ActionCard
          eyebrow={`Readiness · ${readinessPct}%`}
          title="Exam readiness"
          body="Four concepts on the test. One is holding you back."
          footer={
            <div className={s.sparkline} aria-hidden="true">
              {concepts.map((c) => (
                <span
                  key={c.id}
                  className={`${s.spark} ${c.mastery < 50 ? s.sparkLow : c.mastery < 75 ? s.sparkMid : s.sparkHigh}`}
                  style={{ height: `${Math.max(14, c.mastery)}%` }}
                />
              ))}
            </div>
          }
          onClick={() => nav("/readiness")}
        />
      </div>

      <div className={s.lower}>
        <Card size="lg" style={{ display: "flex", flexDirection: "column" }}>
          <div className={s.cardHead}>
            <Label>
              Today's class · {classRecap.startedAt}–{classRecap.endedAt}
            </Label>
            <Label>{classRecap.captureCount} board captures</Label>
          </div>
          <blockquote className={s.quote} style={{ margin: 0 }}>
            “{classRecap.openQuestion}”
          </blockquote>
          <p className={s.quoteWhy}>{classRecap.openQuestionContext}</p>
          <div className={s.sources}>
            {classRecap.sources.map((src) => (
              <Chip key={src.id}>▤ {src.label}</Chip>
            ))}
          </div>
        </Card>

        <Card size="lg">
          <div className={s.cardHead}>
            <Label>Weak areas</Label>
          </div>
          <div className={s.weakList}>
            {weakest.map((c) => (
              <MasteryBar key={c.id} name={c.name} pct={c.mastery} />
            ))}
          </div>
          <p className={s.weakNote}>
            You solve these correctly when the angle is 45°. You stop when it isn't.
          </p>
        </Card>
      </div>
    </Shell>
  );
}
