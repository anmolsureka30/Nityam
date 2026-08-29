import { useNavigate } from "react-router-dom";
import { Shell } from "../../components/Shell";
import {
  ActionCard, Choices, Chip, Label, MasteryInline, Panel,
} from "../../components/ui";
import { useAuth } from "../../lib/auth/AuthContext";
import { conceptName } from "../../lib/conceptCatalog";
import { classRecap, concepts, daysToUnitTest, student } from "../../lib/data";
import { masteryPct, useStudentMemory } from "../../lib/memory";
import s from "./HomeScreen.module.css";

function greetingFor(hour: number) {
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

export default function HomeScreen() {
  const nav = useNavigate();
  const greeting = greetingFor(new Date().getHours());
  const { user } = useAuth();
  const memory = useStudentMemory(user?.uid);

  // Real weaknesses, worst first, when the tutor has actually recorded any —
  // this is the one number on the whole dashboard that used to be a demo
  // constant. A student with no sessions yet sees that honestly (below)
  // rather than a fabricated mastery bar.
  const realWeaknesses = memory.status === "ready"
    ? Object.entries(memory.data.long_term.dpm_profile?.weaknesses ?? {})
    : [];
  const weakest = [...realWeaknesses]
    .sort((a, b) => masteryPct(a[1]) - masteryPct(b[1]))
    .slice(0, 3);
  const readinessPct = realWeaknesses.length
    ? Math.round(realWeaknesses.reduce((sum, [, w]) => sum + masteryPct(w), 0) / realWeaknesses.length)
    : null;

  // "Revise today's class" still points at tonight's classRecap concept —
  // that recap comes from Shruti's board/lecture capture (lib/data.ts's own
  // header comment), which isn't wired into this dashboard yet. Real per-
  // concept mastery above does not depend on that piece being done.
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
              eyebrow={readinessPct !== null ? `Readiness · ${readinessPct}%` : "Readiness"}
              title="Exam readiness"
              body={
                readinessPct !== null
                  ? `${realWeaknesses.length} concept${realWeaknesses.length === 1 ? "" : "s"} tracked so far.`
                  : "Nothing tracked yet — your first session starts this."
              }
              footer={
                readinessPct !== null ? (
                  <span className={s.sparkline} title={`Readiness ${readinessPct}%`}>
                    {realWeaknesses.map(([id, w]) => {
                      const pct = masteryPct(w);
                      return (
                        <span
                          key={id}
                          className={`${s.spark} ${pct < 50 ? s.sparkLow : pct < 75 ? s.sparkMid : s.sparkHigh}`}
                          style={{ height: `${Math.max(16, pct)}%` }}
                        />
                      );
                    })}
                  </span>
                ) : (
                  <span className={s.rowMeta}>—</span>
                )
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
            {weakest.length > 0 ? (
              <>
                <ul className={s.weakList}>
                  {weakest.map(([conceptId, w]) => (
                    <li key={conceptId} className={s.weakRow}>
                      <span className={s.weakName}>{conceptName(conceptId)}</span>
                      <MasteryInline pct={masteryPct(w)} />
                    </li>
                  ))}
                </ul>
                {weakest[0][1].evidence[0] && (
                  <p className={s.weakNote}>{weakest[0][1].evidence[0]}</p>
                )}
              </>
            ) : (
              <p className={s.weakNote}>
                {memory.status === "loading"
                  ? "Loading…"
                  : "Nothing here yet — this fills in after your first session."}
              </p>
            )}
          </Panel>
        </div>
      </section>
    </Shell>
  );
}
