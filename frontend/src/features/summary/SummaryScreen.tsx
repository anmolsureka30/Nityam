import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Shell } from "../../components/Shell";
import { Button, Card, Label } from "../../components/ui";
import { conceptName } from "../../lib/conceptCatalog";
import { useAuth } from "../../lib/auth/AuthContext";
import {
  MASTERY,
  fetchSessionRecap,
  fetchSessions,
  movedForward,
  type MemoryChange,
  type SessionRecap,
} from "../../lib/memory";
import s from "./SummaryScreen.module.css";

/* The recap exists to answer one question the student actually has: was that
 * worth twenty minutes?
 *
 * It used to answer it with `lib/data`'s `summary` object — a fixed headline,
 * two fixed concepts at 68→84% and null→62%, a fixed quote and a fixed line
 * about Mr. Deshpande. Every session ended on those same numbers no matter
 * what had happened, which is worse than showing nothing: it is a confident
 * claim about a student that is false by construction. The percentages were
 * not even expressible — mastery is categorical (misconceived / unknown /
 * partial / known / durable), so there was no real number those bars could
 * ever have been showing.
 *
 * It now reads the session that just ended, through the same endpoint
 * /sessions/:id uses, and says only what that returns.
 *
 * WHY IT POLLS. close_session runs in ws_endpoint's `finally`, so it starts
 * when this screen navigates and the socket unmounts — not before. It writes
 * the log, then snapshots, then calls reflect() (one model call, several
 * seconds), then writes again. So at mount the recap genuinely does not exist
 * yet, and the two intermediate states are distinguishable and worth showing:
 *   found:false                  -> the log has not landed
 *   found:true, has_recap:false  -> saved; reflect() still running
 *   has_recap:true               -> done */

const POLL_MS = 1500;
/* reflect() is a model call behind a socket that has only just closed. Sixty
   seconds is generous on purpose: giving up early and showing "nothing
   changed" would be the same lie the mock told. */
const GIVE_UP_MS = 60_000;

function label(mastery: string | null): string {
  if (!mastery) return "Not seen yet";
  return MASTERY[mastery]?.label ?? mastery;
}

function ChangeRow({ change }: { change: MemoryChange }) {
  const forward = change.kind === "mastery"
    ? movedForward(change.from, change.to)
    : change.to === "resolved";
  return (
    <li className={s.change}>
      <div className={s.changeConcept}>
        {conceptName(change.concept_id) || change.concept_id}
        {change.kind === "doubt" && <span className={s.kindTag}>doubt</span>}
      </div>
      <div className={s.changeArrow}>
        <span className={s.from}>{label(change.from)}</span>
        <span className={s.arrow} aria-hidden="true">→</span>
        <span className={forward ? s.toBetter : s.toWorse}>
          {change.kind === "doubt" && change.to === "removed" ? "cleared" : label(change.to)}
        </span>
      </div>
      {change.doubt && <p className={s.changeNote}>{change.doubt}</p>}
    </li>
  );
}

function minutesBetween(a: string | null, b: string | null): number | null {
  if (!a || !b) return null;
  const ms = Date.parse(b) - Date.parse(a);
  if (!Number.isFinite(ms) || ms < 0) return null;
  return Math.max(1, Math.round(ms / 60000));
}

type State =
  | { status: "waiting"; stage: "saving" | "reflecting" }
  | { status: "ready"; recap: SessionRecap }
  | { status: "norecap"; recap: SessionRecap }
  | { status: "missing" }
  | { status: "error"; error: string };

export default function SummaryScreen() {
  const nav = useNavigate();
  const { user } = useAuth();
  const location = useLocation();
  /* Set by SessionScreen's onEnd. A student who reloads /summary or opens it
     from history has no nav state, so fall back to their newest session —
     which, having just ended, is the one they mean. */
  const passed = (location.state as { sessionId?: string } | null)?.sessionId;
  const [state, setState] = useState<State>({ status: "waiting", stage: "saving" });
  const startedAt = useRef(Date.now());

  useEffect(() => {
    if (!user) return;
    let alive = true;
    let timer: number | undefined;

    async function resolveId(): Promise<string | null> {
      if (passed) return passed;
      const { sessions } = await fetchSessions(user!.uid);
      return sessions[0]?.session_id ?? null;
    }

    async function tick() {
      try {
        const id = await resolveId();
        if (!alive) return;
        if (!id) {
          setState({ status: "missing" });
          return;
        }
        const recap = await fetchSessionRecap(user!.uid, id);
        if (!alive) return;

        if (recap.found && recap.has_recap) {
          setState({ status: "ready", recap });
          return;
        }
        if (Date.now() - startedAt.current > GIVE_UP_MS) {
          // Out of patience, but the transcript and board are real even when
          // reflect() never returned — show them rather than nothing.
          setState(recap.found ? { status: "norecap", recap } : { status: "missing" });
          return;
        }
        setState({ status: "waiting", stage: recap.found ? "reflecting" : "saving" });
        timer = window.setTimeout(tick, POLL_MS);
      } catch (e) {
        if (alive) setState({ status: "error", error: (e as Error).message });
      }
    }

    tick();
    return () => {
      alive = false;
      if (timer) window.clearTimeout(timer);
    };
  }, [user, passed]);

  if (state.status === "waiting") {
    return (
      <Shell>
        <div className={s.wrap}>
          <Label>Session ended</Label>
          <h1 className={s.headline}>Writing up your session…</h1>
          <p className={s.body}>
            {state.stage === "saving"
              ? "Saving everything that was said and everything on your board."
              : "Working out what changed about what I know of you. This takes a few seconds."}
          </p>
          <div className={s.dots} aria-hidden="true"><i /><i /><i /></div>
        </div>
      </Shell>
    );
  }

  if (state.status === "missing" || state.status === "error") {
    return (
      <Shell>
        <div className={s.wrap}>
          <Label>Session ended</Label>
          <h1 className={s.headline}>I could not load that session.</h1>
          <p className={s.body}>
            {state.status === "error"
              ? state.error
              : "Nothing was recorded for it — a session that ends before anyone " +
                "speaks has nothing to write up."}
          </p>
          <div className={s.actions}>
            <Button variant="primary" onClick={() => nav("/")}>Back to tonight</Button>
            <Button onClick={() => nav("/sessions")}>All sessions</Button>
          </div>
        </div>
      </Shell>
    );
  }

  const { recap } = state;
  const mins = minutesBetween(recap.started_at, recap.ended_at);
  const spoken = recap.turns.filter((t) => t.role === "student").length;
  const changes = recap.changes ?? [];
  const openDoubts = Object.entries(state.status === "ready" ? recap.after.doubts : {})
    .filter(([, d]) => d.status === "open");

  return (
    <Shell>
      <div className={s.wrap}>
        <Label>
          Session ended
          {mins !== null && ` · ${mins} min`}
          {` · ${spoken} thing${spoken === 1 ? "" : "s"} you said`}
        </Label>

        {/* The tutor's own summary of the session, written by reflect() at
            close. It was being stored and never read back, which is why "last
            time we…" never worked and why this screen had nothing true to
            lead with. */}
        <h1 className={s.headline}>{recap.topic || "Tonight's session"}</h1>
        {recap.summary && <p className={s.lede}>{recap.summary}</p>}

        <Card size="lg" style={{ marginTop: 26 }}>
          <Label>What moved</Label>
          {changes.length ? (
            <ul className={s.changes}>
              {changes.map((c, i) => (
                <ChangeRow key={`${c.concept_id}-${c.kind}-${i}`} change={c} />
              ))}
            </ul>
          ) : (
            /* Said plainly rather than hidden. A session where nothing moved
               is a real outcome, and pretending otherwise is what the mock
               did. */
            <p className={s.body}>
              {state.status === "norecap"
                ? "The review did not finish for this session, so I have not " +
                  "recorded what changed. What was said and what went on your " +
                  "board are both saved."
                : "Nothing moved far enough to change what I know of you tonight. " +
                  "That happens on a short session, or one spent on something " +
                  "you already had."}
            </p>
          )}
        </Card>

        {!!openDoubts.length && (
          <Card size="lg" quiet style={{ marginTop: 14 }}>
            <Label tone="warn">Still open</Label>
            <ul className={s.openList}>
              {openDoubts.map(([cid, d]) => (
                <li key={cid}>
                  <span className={s.openConcept}>{conceptName(cid) || cid}</span>
                  <span className={s.openDoubt}>{d.doubt}</span>
                </li>
              ))}
            </ul>
          </Card>
        )}

        <div className={s.actions}>
          <Button variant="primary" onClick={() => nav("/")}>Done for tonight</Button>
          <Button onClick={() => nav(`/sessions/${recap.session_id}`)}>
            See everything that changed
          </Button>
          <Button onClick={() => nav(`/sessions/${recap.session_id}/export`)}>
            Export your notes
          </Button>
        </div>
      </div>
    </Shell>
  );
}
