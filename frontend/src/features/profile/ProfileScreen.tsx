import { Shell } from "../../components/Shell";
import { Chip, Label, MasteryInline, Panel, Stat, StatStrip } from "../../components/ui";
import { conceptName } from "../../lib/conceptCatalog";
import { useAuth } from "../../lib/auth/AuthContext";
import { masteryPct, useStudentMemory, type Weakness } from "../../lib/memory";
import s from "./ProfileScreen.module.css";

const MASTERY_LABEL: Record<Weakness["mastery"], string> = {
  unknown: "Not yet assessed",
  misconceived: "Misconception found",
  partial: "Partially there",
  known: "Known",
  durable: "Solid",
};

/* Your student profile, your memory, your interests — all of it read from
 * the same store the tutor writes to at session close (backend/app/memory/).
 * Nothing on this screen is hardcoded: a brand-new student sees an honest
 * empty state, not placeholder numbers pretending to be real. */
export default function ProfileScreen() {
  const { user } = useAuth();
  const state = useStudentMemory(user?.uid);

  return (
    <Shell back={{ to: "/", label: "Dashboard" }}>
      <section className={`ruled ${s.band}`}>
        <div className="margin">
          <Label>Your profile</Label>
        </div>
        <div className="body">
          <h1 className="display">What I know about you.</h1>
          <p className={`lede ${s.subline}`}>
            Everything below comes from your own sessions — nothing here is filled in for you.
          </p>
        </div>
      </section>

      {state.status === "loading" && (
        <section className={`ruled ${s.band}`}>
          <div className="margin" />
          <div className="body">
            <Panel>
              <p className={s.muted}>Loading your profile…</p>
            </Panel>
          </div>
        </section>
      )}

      {state.status === "error" && (
        <section className={`ruled ${s.band}`}>
          <div className="margin" />
          <div className="body">
            <Panel>
              <p className={s.muted}>
                Couldn't reach your memory just now ({state.error}). Try reloading —
                nothing about your progress is lost.
              </p>
            </Panel>
          </div>
        </section>
      )}

      {state.status === "ready" && (
        <ReadyProfile data={state.data} />
      )}
    </Shell>
  );
}

function ReadyProfile({ data }: { data: import("../../lib/memory").StudentMemoryState }) {
  const profile = data.long_term.dpm_profile;
  const memory = data.long_term.teaching_memory;
  const interests = profile?.persona.interests ?? [];
  const weaknesses = profile ? Object.entries(profile.weaknesses) : [];
  const sorted = [...weaknesses].sort((a, b) => masteryPct(a[1]) - masteryPct(b[1]));
  const doubts = memory?.open_doubts.filter((d) => d.status !== "resolved") ?? [];
  const notes = profile?.self_reflection.filter((r) => r.status === "active") ?? [];
  const hasAnything = sorted.length > 0 || interests.length > 0 || doubts.length > 0 || notes.length > 0;

  if (!hasAnything) {
    return (
      <section className={`ruled ${s.band}`}>
        <div className="margin" />
        <div className="body">
          <Panel>
            <p className={s.muted}>
              You haven't had a session yet — start one from the dashboard and I'll
              begin building this the moment it ends.
            </p>
          </Panel>
        </div>
      </section>
    );
  }

  const solid = sorted.filter(([, w]) => w.mastery === "known" || w.mastery === "durable").length;
  const shaky = sorted.filter(
    ([, w]) => w.mastery === "misconceived" || w.mastery === "unknown" || w.mastery === "partial",
  ).length;

  return (
    <>
      {/* The shape of the record before any of the detail. Someone looking at
          this for the first time — a parent, a teacher, a judge — should be
          able to read the state of things in one glance and then decide
          whether to read further. */}
      <section className={`ruled ${s.band}`}>
        <div className="margin" />
        <div className="body">
          <StatStrip>
            <Stat label="Concepts tracked" value={sorted.length} />
            <Stat label="Solid" value={solid} note="known or durable" />
            <Stat label="Needs work" value={shaky} note="where I'll start" />
            <Stat label="Open doubts" value={doubts.length} note="still unresolved" />
          </StatStrip>
        </div>
      </section>

      {interests.length > 0 && (
        <section className={`ruled ${s.band}`}>
          <div className="margin"><Label>Your interests</Label></div>
          <div className="body">
            <div className={s.interests}>
              {interests.map((topic) => (
                <Chip key={topic} tone="accent">{topic}</Chip>
              ))}
            </div>
            <p className={s.hint}>
              I use these to make examples land — a projectile question framed
              around something you actually follow sticks better than one that isn't.
            </p>
          </div>
        </section>
      )}

      {sorted.length > 0 && (
        <section className={`ruled ${s.band}`}>
          <div className="margin"><Label>Mastery, worst first</Label></div>
          <div className="body">
            <Panel style={{ padding: 0 }}>
              <ul className={s.masteryList}>
                {sorted.map(([conceptId, w]) => (
                  <li key={conceptId} className={s.masteryRow}>
                    <div className={s.masteryHead}>
                      <span className={s.masteryName}>{conceptName(conceptId)}</span>
                      <span className={s.masteryState}>{MASTERY_LABEL[w.mastery]}</span>
                    </div>
                    <MasteryInline pct={masteryPct(w)} />
                    {w.evidence.length > 0 && (
                      /* Evidence pointers are `session_id#turn`, which is
                         exactly right in the store — every claim resolves
                         back to a moment that happened — and meaningless on
                         screen. Count them instead, and say what they are. */
                      <p className={s.evidence}>
                        {w.evidence.length === 1
                          ? "Based on one moment in a session"
                          : `Based on ${w.evidence.length} moments across your sessions`}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </Panel>
          </div>
        </section>
      )}

      {doubts.length > 0 && (
        <section className={`ruled ${s.band}`}>
          <div className="margin"><Label>Open doubts</Label></div>
          <div className="body">
            {/* Two bare paragraphs, one after the other, with nothing saying
                which was the mistake and which the correction — that is what
                made this read as raw text. Each half is labelled now, and the
                concept is named above them. */}
            <ul className={s.doubtList}>
              {doubts.map((d) => (
                <li key={d.concept_id} className={s.doubtRow}>
                  <div className={s.doubtHead}>
                    <span className={s.doubtConcept}>{conceptName(d.concept_id)}</span>
                    <Chip>{d.status === "remediating" ? "Working on it" : "Still open"}</Chip>
                  </div>
                  <p className={s.doubtLabel}>What happens</p>
                  <p className={s.doubtText}>{d.doubt}</p>
                  <p className={s.doubtLabel}>What's actually true</p>
                  <p className={s.doubtAnswer}>{d.correct_understanding}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      {notes.length > 0 && (
        <section className={`ruled ${s.band}`}>
          <div className="margin"><Label>What I've noticed</Label></div>
          <div className="body">
            <ul className={s.noteList}>
              {notes.map((n, i) => (
                <li key={i} className={s.noteRow}>{n.note}</li>
              ))}
            </ul>
          </div>
        </section>
      )}
    </>
  );
}
