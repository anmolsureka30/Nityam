import { useEffect, useState } from "react";
import { conceptName } from "../../lib/conceptCatalog";
import { MASTERY, fetchBriefingPreview, type BriefingPreview } from "../../lib/memory";
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
export default function SessionBriefing({
  studentId, topic, mode, open,
}: {
  studentId: string | undefined;
  topic: string;
  mode: string;
  /** False once she has spoken; the overlay fades and stops mattering. */
  open: boolean;
}) {
  const [brief, setBrief] = useState<BriefingPreview | null>(null);

  useEffect(() => {
    if (!studentId) return;
    let live = true;
    fetchBriefingPreview(studentId, topic, mode)
      .then((b) => live && setBrief(b))
      .catch(() => {
        /* An overlay must never be the reason a lesson does not start. It
           simply shows the topic and the spinner instead. */
      });
    return () => {
      live = false;
    };
  }, [studentId, topic, mode]);

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
          <span>Getting your tutor on the line…</span>
        </div>
      </div>
    </div>
  );
}
