import { useEffect, useState } from "react";
import { conceptName } from "../../lib/conceptCatalog";
import { MASTERY, type BriefingPreview } from "../../lib/memory";
import s from "./SessionBriefing.module.css";

/* Shown over the board while the Live model connects.
 *
 * There is a real five-to-six second gap between pressing start and the tutor
 * speaking: the socket opens, the brief is composed out of Firestore, and the
 * Live session handshakes. That was blank, which reads as a slow app.
 *
 * It is filled with the one thing that is both true and worth reading — what
 * she has actually been told about you. Same source as her own briefing
 * (backend memory_routes /briefing, which calls the same resolve_concepts),
 * so this cannot promise something she was never given. It is not the brief
 * text itself: that is written for a model, wrapped in square brackets, and
 * reads like stage directions.
 *
 * It dismisses itself the moment she speaks. Nothing to click, because a
 * student who has to dismiss a loading screen has been given a chore. */
/* The wait is five or six seconds on a good run and has been seen at
 * seventeen, and one unchanging line for that long reads as a hang. These
 * rotate so the screen is visibly alive.
 *
 * They are canned, not wired to real progress signals — there is no per-stage
 * event to key them off, and inventing one to drive a loading screen is not
 * worth the wire. They are ordered to match the rough shape of what actually
 * happens (board, memory, corpus, plan, Live handshake), so a reader who knows
 * the system is not being told something false; nothing here claims a specific
 * step has FINISHED. */
const STAGES = [
  "Making your canvas ready",
  "Reading your last session",
  "Opening your NCERT textbook",
  "Going through your class recordings",
  "Planning what to cover tonight",
  "Getting your tutor on the line",
];
const STAGE_MS = 4500;

export default function SessionBriefing({
  brief, topic, mode, open,
}: {
  /** Fetched once by SessionScreen and passed down. This component used to
   *  fetch its own copy, and the screen fetched another for the plan across
   *  the top — two components wanting the same three facts, so one session
   *  start made FOUR calls to /briefing in dev (React double-invokes effects),
   *  each one several blocking Firestore round trips on the server, during the
   *  exact five seconds the student is waiting to be spoken to. */
  brief: BriefingPreview | null;
  topic: string;
  mode: string;
  /** False once she has spoken; the overlay fades and stops mattering. */
  open: boolean;
}) {
  /* Short enough to take in at a glance: the concepts tonight covers, worst
     first, each with a two-word note on where the student stands. Names are
     already short — "Resolving a vector into components" is trimmed to its
     first clause rather than wrapped over three lines. */
  const plan = (brief?.plan ?? []).slice(0, 4).map((cid) => {
    const weak = brief?.weak_points?.find((w) => w.concept_id === cid);
    const full = conceptName(cid) || cid;
    return {
      key: cid,
      label: full.length > 34 ? full.slice(0, 32).replace(/[ ,]+$/, "") + "…" : full,
      note: weak ? (MASTERY[weak.mastery]?.label ?? weak.mastery) : "",
    };
  });

  /* Advances every 4.5s and then STOPS on the last line rather than looping.
     Six stages cover 27 seconds, past the worst start observed; if the
     connection takes longer than that, holding on "Getting your tutor on the
     line" stays true, whereas wrapping back round to "Making your canvas
     ready" would be plainly false and would read as a stuck spinner. */
  const [stage, setStage] = useState(0);
  useEffect(() => {
    if (!open) {
      setStage(0);
      return;
    }
    const id = setInterval(
      () => setStage((i) => (i < STAGES.length - 1 ? i + 1 : i)),
      STAGE_MS,
    );
    return () => clearInterval(id);
  }, [open]);

  return (
    <div
      className={`${s.veil} ${open ? s.veilOpen : s.veilGone}`}
      aria-hidden={!open}
      /* Not a dialog and not focus-trapped: it is a curtain that lifts on its
         own, and nothing behind it is usable until she speaks anyway. */
      role="status"
      aria-live="polite"
    >
      <div className={s.card}>
        <p className={s.kicker}>
          {mode === "exam" ? "Exam preparation" : mode === "doubt" ? "Your doubt" : "Tonight"}
        </p>
        <h2 className={s.topic}>{brief?.topic || topic || "Tonight's session"}</h2>

        {/* Four or five words each, and only what tonight actually covers.
            This was three paragraphs — the last session's summary, every open
            doubt in full — which nobody reads in the two seconds before she
            starts talking, and which made the wait feel longer rather than
            shorter. A holding screen has to be readable at a glance or it is
            just a wall. */}
        {!!plan.length && (
          <ol className={s.plan}>
            {plan.map((item) => (
              <li key={item.key}>
                <span className={s.planText}>{item.label}</span>
                {item.note && <span className={s.planNote}>{item.note}</span>}
              </li>
            ))}
          </ol>
        )}

        <div className={s.waiting}>
          <span className={s.dots} aria-hidden="true"><i /><i /><i /></span>
          {/* Keyed by index so React remounts the span and the fade replays on
              every change. aria-hidden because the veil is already an
              aria-live region: without it a screen reader announces all six
              lines, turning a decorative progress hint into six
              interruptions. The stable label below is what gets announced. */}
          <span key={stage} className={s.status} aria-hidden="true">
            {STAGES[stage]}…
          </span>
          <span className={s.srOnly}>Getting your tutor ready</span>
        </div>
      </div>
    </div>
  );
}
