import { useState } from "react";
import s from "./SpeechBubble.module.css";

export default function SpeechBubble({
  caption,
  error,
  agent,
}: {
  caption: string;
  /** Connection or stream failures surface here rather than in the console:
   *  a silent tutor with a dead socket looks identical to one that is thinking. */
  error?: string | null;
  agent?: string;
}) {
  const [minimised, setMinimised] = useState(false);
  /* Minimising is a preference, not a dismissal: she keeps talking and we keep
     her collapsed, but the cloud has to admit that something new was said.
     Derived from the last line the student actually saw, rather than a flag set
     from an effect — one less piece of state to get out of step, and no
     cascading render on every sentence she speaks. */
  const [seen, setSeen] = useState(caption);
  const unread = minimised && caption !== seen;

  const text = error ? `I lost the connection — ${error}` : caption;
  if (!text) return null;

  if (minimised) {
    return (
      <button
        type="button"
        className={`${s.cloud} ${unread ? s.cloudNew : ""}`}
        onClick={() => {
          setMinimised(false);
          setSeen(caption);
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
    <div className={`${s.bubble} ${error ? s.bubbleError : ""}`}>
      <div className={s.head}>
        <button
          type="button"
          className={s.min}
          onClick={() => {
            setSeen(caption);
            setMinimised(true);
          }}
          aria-expanded={true}
          aria-label="Minimise her words"
          title="Minimise"
        >
          <span aria-hidden="true">−</span>
        </button>
        {agent && agent !== "tutor" && <span className={s.agent}>{agent}</span>}
      </div>
      {/* The live region covers only what she said — a screen reader announcing
          the minimise glyph before every sentence is worse than no button. */}
      <div role="status" aria-live="polite">
        <p className={s.text}>{text}</p>
      </div>
    </div>
  );
}
