import { useState } from "react";
import { Button, Label } from "../../components/ui";
import type { Checkpoint } from "../../lib/types";
import s from "./CheckpointModal.module.css";

const cx = (...p: (string | false | undefined)[]) => p.filter(Boolean).join(" ");

/* A checkpoint is not a test — it is how the tutor finds out what the student
 * actually believes. So a wrong answer names the misconception and keeps the
 * modal open, and the footnote says nobody else sees it. Guessing has to feel
 * safer than skipping, or the signal is worthless. */
export default function CheckpointModal({
  checkpoint, onAnswer, onDone,
}: {
  checkpoint: Checkpoint;
  /** Fired the instant an option is picked — before any rebuttal is read,
   *  before the continue button exists to click. This is what the tutor
   *  reacts to out loud, so a wrong pick is told wrong right away instead of
   *  waiting on an extra "Show me why" click first. Fires once, on the
   *  first pick only — changing your mind afterward doesn't re-report. */
  onAnswer: (correct: boolean, optionId: string, optionText: string) => void;
  /** Fired when the student is done with this checkpoint — after reading
   *  the rebuttal, if there was one. Closes the modal / advances mastery.
   *  The chosen option travels with the verdict: the tutor answers about the
   *  specific wrong answer, so "correct: false" alone is not enough for it to
   *  say anything useful. */
  onDone: (correct: boolean, optionId: string, optionText: string) => void;
}) {
  /* Keyed by checkpoint, not just the option.
   *
   * This was `useState<string | null>` holding the option id alone, and React
   * reuses this component across questions rather than remounting it — so on
   * question two `chosen` still held question one's answer. That id is not in
   * the new question's options, so `picked` was null, `answered` was false,
   * the continue button stayed disabled, AND the guard below
   * (`if (chosen !== null) return`) swallowed every click. The whole modal
   * went dead after the first answer with no way out of it.
   *
   * Storing which checkpoint the answer belongs to makes the reset automatic:
   * a new question has a new id, so `chosen` is null again without an effect
   * to forget to write. */
  const [answer, setAnswer] = useState<{ checkpoint: string; option: string } | null>(null);
  const chosen = answer?.checkpoint === checkpoint.id ? answer.option : null;
  const setChosen = (option: string) =>
    setAnswer({ checkpoint: checkpoint.id, option });
  const picked = checkpoint.options.find((o) => o.id === chosen) ?? null;
  const answered = picked !== null;
  const correct = picked?.correct ?? false;

  return (
    <div className={s.veil} role="dialog" aria-modal="true" aria-label="Checkpoint">
      <div className={s.modal}>
        <div className={s.head}>
          <Label>Checkpoint · {checkpoint.index} of {checkpoint.total}</Label>
          <Label tone={answered && correct ? undefined : "accent"}>
            {answered ? (correct ? "Got it" : "Pick another") : "Answer to continue"}
          </Label>
        </div>

        <div className={s.body}>
          <h3 className={s.question}>{checkpoint.question}</h3>
          <p className={s.hint}>{checkpoint.hint}</p>

          <div className={s.options}>
            {checkpoint.options.map((opt) => {
              const isPicked = chosen === opt.id;
              const state = !isPicked ? "" : opt.correct ? "right" : "wrong";
              return (
                <button
                  key={opt.id}
                  className={cx(
                    s.option,
                    state === "wrong" && s.optionWrong,
                    state === "right" && s.optionRight,
                  )}
                  onClick={() => {
                    /* A WRONG ANSWER IS NOT THE END OF THE QUESTION.
                       This used to lock on the first pick, so getting it wrong
                       left you staring at a rebuttal explaining your mistake
                       with no way to act on it — which is the one moment a
                       student most wants to try again, and the whole reason
                       the rebuttal is written. Re-picking is allowed until it
                       is right; once it is right it locks, because changing a
                       correct answer is not a thing anyone means to do.

                       Every attempt is reported. A second try IS the lesson —
                       the tutor should know it happened, and the record should
                       show the first answer was wrong rather than quietly
                       keeping only the one that worked. */
                    if (correct) return;
                    if (opt.id === chosen) return;   // same answer, nothing new
                    setChosen(opt.id);
                    onAnswer(opt.correct, opt.id, opt.text);
                  }}
                >
                  <span
                    className={cx(
                      s.letter,
                      state === "wrong" && s.letterWrong,
                      state === "right" && s.letterRight,
                    )}
                  >
                    {opt.letter}
                  </span>
                  <span className={s.optionText}>{opt.text}</span>
                  {opt.tag && !answered && <span className={s.tag}>{opt.tag}</span>}
                </button>
              );
            })}
          </div>

          {picked && !picked.correct && picked.rebuttal && (
            <div className={s.rebuttal}>
              <Label tone="warn">You said · {picked.text.toLowerCase()}</Label>
              <p className={s.rebuttalText}>{picked.rebuttal}</p>
              <p className={s.retry}>Have another go — pick a different one.</p>
            </div>
          )}
        </div>

        <div className={s.foot}>
          <Label>{checkpoint.footnote}</Label>
          <Button
            variant="primary"
            disabled={!answered}
            onClick={() => picked && onDone(correct, picked.id, picked.text)}
          >
            {/* "Show me why" promised an explanation the button did not give —
                the rebuttal is already on screen above it. It is an escape
                hatch, and it should say so: you can always move on without
                getting it right. */}
            {correct ? "Keep going" : answered ? "Move on anyway" : "Pick one"}
          </Button>
        </div>
      </div>
    </div>
  );
}
