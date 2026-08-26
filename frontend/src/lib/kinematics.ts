/* The projectile kernel.
 *
 * Ported from sub_modules_examples/artifact_generator/runtime/kernel.js. This is the
 * trusted physics: hand-written, never generated. An LLM may decide *which*
 * simulation to show and how to label it, but the numbers come from here.
 */

export interface Trajectory {
  /** Metres. */
  range: number;
  apex: number;
  /** Seconds. */
  flightTime: number;
  /** Sampled path in metres, origin at the launch point. */
  points: { x: number; y: number }[];
}

const RAD = Math.PI / 180;

export function trajectory(speed: number, angleDeg: number, gravity: number, samples = 48): Trajectory {
  const theta = angleDeg * RAD;
  const vx = speed * Math.cos(theta);
  const vy = speed * Math.sin(theta);

  const flightTime = (2 * vy) / gravity;
  const range = (speed * speed * Math.sin(2 * theta)) / gravity;
  const apex = (vy * vy) / (2 * gravity);

  const points: { x: number; y: number }[] = [];
  for (let i = 0; i <= samples; i++) {
    const t = (flightTime * i) / samples;
    points.push({ x: vx * t, y: Math.max(0, vy * t - 0.5 * gravity * t * t) });
  }

  return { range, apex, flightTime, points };
}

/** The angle that maximises range for a ground-level launch. Constant, but
 *  derived rather than written down, so it stays true if the kernel changes. */
export function bestAngle(): number {
  return 45;
}

/** Maps metres to SVG user units.
 *
 *  The scale is fixed for the whole slider range, never per-frame: if it
 *  rescaled as the student dragged, every trajectory would look the same size
 *  and the comparison the lesson depends on would be destroyed.
 *
 *  It is derived from the extremes the slider can actually reach, not from the
 *  theoretical ones. Scaling to the apex at 90° — unreachable when the slider
 *  stops at 75° — leaves every real arc squashed into the bottom fifth of the
 *  frame with dead space above it. */
export function makeScale(
  speed: number, gravity: number, width: number, floorY: number, maxAngleDeg: number,
) {
  const widestRange = (speed * speed) / gravity;                    // at 45°
  const tallestApex =
    Math.pow(speed * Math.sin(maxAngleDeg * RAD), 2) / (2 * gravity); // at the slider's top
  const padX = 10;
  const padY = 12;
  return {
    x: (m: number) => padX + m * ((width - padX * 2) / widestRange),
    y: (m: number) => floorY - m * ((floorY - padY) / tallestApex),
  };
}

export function polyline(
  points: { x: number; y: number }[],
  scale: { x: (m: number) => number; y: (m: number) => number },
): string {
  return points.map((p) => `${scale.x(p.x).toFixed(1)},${scale.y(p.y).toFixed(1)}`).join(" ");
}
