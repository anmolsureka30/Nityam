import { useEffect, useRef, useState } from "react";
import type { TutorState } from "../../lib/types";
import s from "./SpeechBubble.module.css";

export default function SpeechBubble({ tutor }: { tutor: TutorState }) {
  const [minimised, setMinimised] = useState(false);
  /* Minimising is a preference, not a dismissal: she keeps talking and we keep
     her collapsed, but the cloud has to admit that something new was said. */
  const [unread, setUnread] = useState(false);
  const spoken = useRef(tutor.caption);

  useEffect(() => {
    if (!tutor.caption || tutor.caption === spoken.current) return;
    spoken.current = tutor.caption;
    if (minimised) setUnread(true);
  }, [tutor.caption, minimised]);

  if (!tutor.caption) return null;

  if (minimised) {
    return (
      <button
        type="button"
        className={`${s.cloud} ${unread ? s.cloudNew : ""}`}
        onClick={() => {
          setMinimised(false);
          setUnread(false);
        }}
        aria-expanded={false}
        aria-label={unread ? "Show what she just said" : "Show her last words"}
        title="Show her words"
      >
        <span className={s.dots} aria-hidden="true">
          <i /><i /><i />
        </span>
      </button>
    );
  }

  return (
    <div className={s.bubble}>
      <div className={s.head}>
        <button
          type="button"
          className={s.min}
          onClick={() => setMinimised(true)}
          aria-expanded={true}
          aria-label="Minimise her words"
          title="Minimise"
        >
          <span aria-hidden="true">−</span>
        </button>
        {tutor.agent === "quiz_master" && <span className={s.agent}>Quiz master</span>}
      </div>
      {/* The live region covers only what she said — a screen reader announcing
          the minimise glyph before every sentence is worse than no button. */}
      <div role="status" aria-live="polite">
        <p className={s.text}>{tutor.caption}</p>
        {tutor.masteryNote && <span className={s.note}>{tutor.masteryNote}</span>}
      </div>
    </div>
  );
}
