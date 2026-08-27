import { useNavigate } from "react-router-dom";
import { Shell } from "../../components/Shell";
import {
  ActionCard, Choices, Chip, Label, MasteryInline, Panel,
} from "../../components/ui";
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
      {/* Every band on this page hangs off one rule, and everything ABOUT the
          work — the date, the countdown, the section name — sits in the margin
          to the left of it. That is the whole layout, and it is why the eye
          always knows where a line begins. */}
      <section className={`ruled ${s.band}`}>
        <div className="margin">
          <Label>Unit test</Label>
          <div className={s.countdown}>{daysToUnitTest}</div>
          <Label>days away</Label>
        </div>
        <div className="body">
          <h1 className="display">{greeting}, {student.firstName}.</h1>
          <p className={`lede ${s.subline}`}>
            Your class covered {classRecap.subject.toLowerCase()} today. I listened to all
            of it — there are two things worth going over.
          </p>
        </div>
      </section>

      <section className={`ruled ${s.band}`}>
        <div className="margin"><Label>Tonight</Label></div>
        <div className="body">
          <Choices>
            <ActionCard
              primary
              eyebrow="Start here"
              title="Revise today's class"
              body="Projectile motion — range, angle, symmetry. We pick up exactly where Mr. Deshpande ran out of time."
              footer={<span className={s.rowMeta}>≈ 20 min</span>}
              onClick={() => nav(`/intensity/${target.id}`)}
            />
            <ActionCard
              eyebrow="Anytime"
              title="Ask a doubt"
              body="Anything from the board — today, or three weeks ago. Type it or say it."
              footer={<span className={s.rowMeta}>Voice or text</span>}
              onClick={() => nav("/session?mode=doubt")}
            />
            <ActionCard
              eyebrow={`Readiness · ${readinessPct}%`}
              title="Exam readiness"
              body="Four concepts on the test. One is holding you back."
              footer={
                <span className={s.sparkline} title={`Readiness ${readinessPct}%`}>
                  {concepts.map((c) => (
                    <span
                      key={c.id}
                      className={`${s.spark} ${c.mastery < 50 ? s.sparkLow : c.mastery < 75 ? s.sparkMid : s.sparkHigh}`}
                      style={{ height: `${Math.max(16, c.mastery)}%` }}
                    />
                  ))}
                </span>
              }
              onClick={() => nav("/readiness")}
            />
          </Choices>
        </div>
      </section>

      <section className={`ruled ${s.band}`}>
        <div className="margin">
          <Label>Today's class</Label>
          <div className={s.marginMeta}>
            {classRecap.startedAt}–{classRecap.endedAt}
          </div>
          <div className={s.marginMeta}>{classRecap.captureCount} captures</div>
        </div>

        <div className={`body ${s.lower}`}>
          {/* The emotional centre of the product, so it is set as the largest
              thing on the page after the greeting rather than as body copy in
              a card. A question the teacher never answered is the reason this
              student is here tonight. */}
          <div className={s.recap}>
            <blockquote className={s.quote}>{classRecap.openQuestion}</blockquote>
            <p className={s.quoteWhy}>{classRecap.openQuestionContext}</p>
            <div className={s.sources}>
              {classRecap.sources.map((src) => (
                <Chip key={src.id}>▤ {src.label}</Chip>
              ))}
            </div>
          </div>

          {/* Data, so it is a PANEL — cool and hairlined, visibly a different
              kind of thing from the notebook prose beside it. */}
          <Panel as="aside" style={{ padding: 0 }}>
            <div className={s.weakHead}>
              <Label>Where you lose marks</Label>
            </div>
            <ul className={s.weakList}>
              {weakest.map((c) => (
                <li key={c.id} className={s.weakRow}>
                  <span className={s.weakName}>{c.name}</span>
                  <MasteryInline pct={c.mastery} />
                </li>
              ))}
            </ul>
            <p className={s.weakNote}>
              You solve these correctly when the angle is 45°. You stop when it isn't.
            </p>
          </Panel>
        </div>
      </section>
    </Shell>
  );
}
