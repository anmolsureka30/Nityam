import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Shell } from "../../components/Shell";
import { Button, Label } from "../../components/ui";
import { concepts, intensities } from "../../lib/data";
import type { Intensity } from "../../lib/types";
import s from "./IntensityScreen.module.css";

const cx = (...p: (string | false | undefined)[]) => p.filter(Boolean).join(" ");

/* Asking for time up front is the one thing that makes the session honest:
   the plan is built to fit the time the student actually has. */
export default function IntensityScreen() {
  const nav = useNavigate();
  const { conceptId } = useParams();
  const concept = concepts.find((c) => c.id === conceptId) ?? concepts[0];
  const [picked, setPicked] = useState<Intensity>(
    intensities.find((i) => i.suggested)?.id ?? "standard",
  );

  return (
    <Shell back={{ to: "/", label: "Home" }}>
      <div className={s.wrap}>
        <h1 className={s.question}>How long do you have tonight?</h1>
        <p className={s.sub}>{concept.name} · from today's class</p>

        <div className={s.options} role="radiogroup" aria-label="Session length">
          {intensities.map((opt) => (
            <button
              key={opt.id}
              role="radio"
              aria-checked={picked === opt.id}
              className={cx(s.option, picked === opt.id && s.optionOn)}
              onClick={() => setPicked(opt.id)}
            >
              {opt.suggested && <span className={s.suggested}>Suggested</span>}
              <div className={s.optionHead}>
                <span className={s.optionLabel}>{opt.label}</span>
                <Label>{opt.minutes} min</Label>
              </div>
              <span className={s.optionPromise}>{opt.promise}</span>
            </button>
          ))}
        </div>

        <Button variant="primary" block onClick={() => nav(`/session?mode=revision&concept=${conceptId}&intensity=${picked}`)}>
          Begin session
        </Button>
      </div>
    </Shell>
  );
}
