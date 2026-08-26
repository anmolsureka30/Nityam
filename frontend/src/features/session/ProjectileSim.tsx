import { useMemo, useState } from "react";
import { Label } from "../../components/ui";
import { bestAngle, makeScale, polyline, trajectory } from "../../lib/kinematics";
import type { ProjectileArtifact } from "../../lib/types";
import s from "./ProjectileSim.module.css";

const W = 720, H = 172, FLOOR = 150;

/* One kernel, one control. The point of the artifact is not the picture — it
 * is that dragging the angle is the only way to answer the question the class
 * ran out of time for, so the interaction *is* the lesson.
 *
 * `onExplored` fires once the student has been either side of the maximum,
 * which is the behavioural evidence that they have seen the peak rather than
 * just read about it. In production this is a probe (see artifact_generator).
 */
export default function ProjectileSim({
  spec, onExplored,
}: { spec: ProjectileArtifact; onExplored?: (angle: number) => void }) {
  const [angle, setAngle] = useState(spec.angle);
  const [seenBelow, setSeenBelow] = useState(false);
  const [seenAbove, setSeenAbove] = useState(false);

  const scale = useMemo(
    () => makeScale(spec.speed, spec.gravity, W, FLOOR, spec.angleMax),
    [spec.speed, spec.gravity, spec.angleMax],
  );

  const live = useMemo(
    () => trajectory(spec.speed, angle, spec.gravity),
    [spec.speed, angle, spec.gravity],
  );

  /* Complementary angles land in the same place, so their dots and labels sit
     on top of each other. Grouping them is not cosmetic — "30° · 60°" under a
     single dot IS the symmetry result, visible before it is taught. */
  const ghosts = useMemo(() => {
    const drawn = spec.ghosts.map((g) => ({ angle: g, traj: trajectory(spec.speed, g, spec.gravity) }));
    const groups = new Map<number, { angles: number[]; range: number; points: { x: number; y: number }[] }>();
    for (const g of drawn) {
      const key = Math.round(g.traj.range * 10);
      const existing = groups.get(key);
      if (existing) existing.angles.push(g.angle);
      else groups.set(key, { angles: [g.angle], range: g.traj.range, points: g.traj.points });
    }
    return [...groups.values()];
  }, [spec.ghosts, spec.speed, spec.gravity]);

  const best = bestAngle();
  const atBest = Math.abs(angle - best) <= 1;

  function change(next: number) {
    setAngle(next);
    if (next < best - 2) setSeenBelow(true);
    if (next > best + 2) setSeenAbove(true);
    // Both sides seen and now at the top: the student has found it themselves.
    if (seenBelow && seenAbove && Math.abs(next - best) <= 1) onExplored?.(next);
  }

  const hint = atBest
    ? "This is the furthest it will go. Why this angle and not a steeper one?"
    : seenBelow && seenAbove
      ? "You have been either side. Where was it furthest?"
      : "Drag through the range. Watch where the landing dot stops moving forward.";

  return (
    <div className={s.wrap}>
      <div className={s.head}>
        <Label>{spec.eyebrow}</Label>
        <Label>v = {spec.speed} m/s · g = {spec.gravity} m/s²</Label>
      </div>

      <div className={s.body}>
        <div className={s.stage}>
          <svg
            viewBox={`0 0 ${W} ${H}`}
            className={s.svg}
            role="img"
            aria-label={`Projectile launched at ${angle} degrees travels ${live.range.toFixed(1)} metres.`}
          >
            <line x1="0" y1={FLOOR} x2={W} y2={FLOOR} stroke="var(--line)" strokeWidth="1" />

            {/* Ghosts stay on screen so the comparison is visible rather than
                remembered. Complementary angles overlap exactly — that is the
                next concept, discovered for free. */}
            {ghosts.map((g) => (
              <g key={g.angles.join("-")} opacity="0.75">
                <polyline
                  points={polyline(g.points, scale)}
                  fill="none"
                  stroke="var(--ink-dim)"
                  strokeWidth="1.4"
                  strokeDasharray="3 4"
                />
                <circle cx={scale.x(g.range)} cy={FLOOR} r="3" fill="var(--ink-dim)" />
                <text
                  x={scale.x(g.range)}
                  y={FLOOR + 14}
                  textAnchor="middle"
                  fontSize="10"
                  fontFamily="var(--mono)"
                  fill="var(--ink-dim)"
                >
                  {g.angles.map((a) => `${a}°`).join(" · ")}
                </text>
              </g>
            ))}

            <polyline
              points={polyline(live.points, scale)}
              fill="none"
              stroke="var(--sim)"
              strokeWidth="2.5"
              strokeLinecap="round"
            />
            <circle cx={scale.x(live.range)} cy={FLOOR} r="4.5" fill="var(--sim)" />
          </svg>

          <input
            type="range"
            className={s.slider}
            min={spec.angleMin}
            max={spec.angleMax}
            step={1}
            value={angle}
            aria-label="Launch angle"
            onChange={(e) => change(Number(e.target.value))}
          />
          <div className={s.ticks}>
            <span>{spec.angleMin}°</span>
            <span>{best}°</span>
            <span>{spec.angleMax}°</span>
          </div>
        </div>

        <div className={s.readouts}>
          <div>
            <Label>Angle</Label>
            <div className={s.readValue}>{angle}°</div>
          </div>
          <div>
            <Label>Range</Label>
            <div className={`${s.readValue} ${s.readValueSim}`}>
              {live.range.toFixed(1)} m
            </div>
          </div>
          <p className={s.hint}>
            {atBest && <span className={s.best}>Furthest. </span>}
            {hint}
          </p>
        </div>
      </div>
    </div>
  );
}
