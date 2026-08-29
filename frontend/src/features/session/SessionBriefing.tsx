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
          {mode === "exam" ? "Exam preparation" : mode === "doubt" ? "Your doubt" : "Revision"}
        </p>
        <h2 className={s.topic}>{brief?.topic || topic || "Tonight's session"}</h2>

        {brief?.last_session && (
          <div className={s.block}>
            <p className={s.label}>Where we stopped</p>
            <p className={s.last}>{brief.last_session}</p>
          </div>
        )}

        {!!brief?.weak_points?.length && (
          <div className={s.block}>
            <p className={s.label}>What I'll start with</p>
            <ul className={s.weak}>
              {brief.weak_points.map((w) => (
                <li key={w.concept_id}>
                  <span className={s.weakName}>
                    {conceptName(w.concept_id) || w.concept_id}
                  </span>
                  <span className={s.weakState}>
                    {MASTERY[w.mastery]?.label ?? w.mastery}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {!!brief?.open_doubts?.length && (
          <div className={s.block}>
            <p className={s.label}>Still open from before</p>
            <ul className={s.doubts}>
              {brief.open_doubts.map((d) => (
                <li key={d.concept_id}>{d.doubt}</li>
              ))}
            </ul>
          </div>
        )}

        {!!brief?.covered?.length && (
          <div className={s.block}>
            <p className={s.label}>Already solid</p>
            <p className={s.covered}>
              {brief.covered.map((c) => conceptName(c) || c).join(" · ")}
            </p>
          </div>
        )}

        <div className={s.waiting}>
          <span className={s.dots} aria-hidden="true"><i /><i /><i /></span>
          <span>Getting your tutor on the line…</span>
        </div>
      </div>
    </div>
  );
}
