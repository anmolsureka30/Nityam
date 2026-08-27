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
  checkpoint, onDone,
}: {
  checkpoint: Checkpoint;
  /** The chosen option travels with the verdict: the tutor answers about the
   *  specific wrong answer, so "correct: false" alone is not enough for it to
   *  say anything useful. */
  onDone: (correct: boolean, optionId: string, optionText: string) => void;
}) {
  const [chosen, setChosen] = useState<string | null>(null);
  const picked = checkpoint.options.find((o) => o.id === chosen) ?? null;
  const answered = picked !== null;
  const correct = picked?.correct ?? false;

  return (
    <div className={s.veil} role="dialog" aria-modal="true" aria-label="Checkpoint">
      <div className={s.modal}>
        <div className={s.head}>
          <Label>Checkpoint · {checkpoint.index} of {checkpoint.total}</Label>
          <Label tone={answered && correct ? undefined : "accent"}>
            {answered ? (correct ? "Got it" : "Try again") : "Answer to continue"}
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
                  onClick={() => setChosen(opt.id)}
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
            {correct ? "Keep going" : answered ? "Show me why" : "Pick one"}
          </Button>
        </div>
      </div>
    </div>
  );
}
