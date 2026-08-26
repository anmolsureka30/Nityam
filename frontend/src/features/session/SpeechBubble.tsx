import type { TutorState } from "../../lib/types";
import s from "./SpeechBubble.module.css";

export default function SpeechBubble({ tutor }: { tutor: TutorState }) {
  if (!tutor.caption) return null;
  return (
    <div className={s.bubble} role="status" aria-live="polite">
      {tutor.agent === "quiz_master" && <span className={s.agent}>Quiz master</span>}
      <p className={s.text}>{tutor.caption}</p>
      {tutor.masteryNote && <span className={s.note}>{tutor.masteryNote}</span>}
    </div>
  );
}
