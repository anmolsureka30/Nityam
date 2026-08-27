import { useEffect, useRef, useState } from "react";
import s from "./PointerStick.module.css";

/* She picks up a stick and points at the thing she is talking about.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * THE SIGNAL ALREADY EXISTED. `point_at(anchor_ids, reason)` is a tool the
 * tutor already calls — four times in a nine-minute session — and it already
 * reaches the page: a `point_at` patch sets `hot[anchorId] = expiry` in
 * notebookReducer, and Notebook renders `.anchorHot` on the `<mark
 * data-anchor="…">`. All that was missing was the picture.
 *
 * WHY IT IS NOT PART OF THE AVATAR. lib/avatar/rig.js is a hand-drawn bust —
 * head, hair, shoulders, no arms, deliberately cropped "so the crop reads as a
 * bust and not a hill". Posing a limb inside 607 lines of hand-authored canvas
 * would be invasive, and the stick has to reach a word anywhere on the page,
 * which a 254x288 canvas cannot do. So it is an overlay, and her hand is BELOW
 * THE CROP: the stick emerges from behind her shoulder, which reads as held
 * without a hand ever being drawn.
 *
 * WHEN IT SHOWS, which is the part that needed judgement:
 *   - only while an anchor is hot, so it follows her actual pointing
 *   - only if that anchor is ON SCREEN — pointing at something scrolled out of
 *     view would look broken
 *   - only while she is speaking; a stick held up in silence is odd
 * point_at fires a handful of times a session with a few seconds' TTL, so this
 * is noticeable without being constant, and needs no throttle of its own.
 *
 * IT TOUCHES THE WORD. An earlier version stopped three hundred pixels short
 * and left the eye to extrapolate the line — and a few degrees of error in the
 * angle put the imagined continuation nowhere near the term, so it read as
 * pointing at the wrong thing. Landing the tip ON the target makes the aim
 * exact by construction, and testable.
 *
 * It approaches the word's UNDERSIDE from the lower right, because she stands
 * to the right of the page: that is the shortest path to the term and the one
 * that crosses least of the lesson, and a pointer resting under a word is what
 * a teacher actually does. */

interface Aim {
  /** Where the stick is held, and where it points. Viewport pixels. */
  from: { x: number; y: number };
  to: { x: number; y: number };
}

/** How long the raise/lower takes; matches the CSS transition. */
const SETTLE_MS = 260;

/** How far the shaft carries on behind her hand, so the near end is hidden by
 *  her figure rather than stopping in mid-air. */
const BUTT_PX = 46;

export default function PointerStick({
  hot, speaking, revision,
}: {
  /** anchorId -> expiry timestamp, straight from the board reducer. */
  hot: Record<string, number>;
  speaking: boolean;
  /** Bumped on every patch, so the stick re-measures when the page changes
   *  under it — a new block above the target moves the target. */
  revision: number;
}) {
  const [aim, setAim] = useState<Aim | null>(null);
  const raf = useRef(0);

  const live = Object.keys(hot).length > 0 && speaking;

  useEffect(() => {
    if (!live) {
      setAim(null);
      return;
    }

    const measure = () => {
      /* The newest hot anchor wins. She points at one thing at a time, and
         when she lights up two terms the later one is the one she is on. */
      const word = Object.entries(hot)
        .sort((a, b) => b[1] - a[1])
        .map(([id]) => document.querySelector<HTMLElement>(`[data-anchor="${id}"]`))
        .find(Boolean);

      const figure = document.querySelector<HTMLElement>("[data-avatar-dock] canvas");
      if (!word || !figure) { setAim(null); return; }

      const t = word.getBoundingClientRect();
      const d = figure.getBoundingClientRect();

      // Off screen, or scrolled behind the chrome: no stick rather than a stick
      // pointing into nowhere.
      const onScreen =
        t.bottom > 96 && t.top < window.innerHeight - 8 &&
        t.right > 0 && t.left < window.innerWidth;
      if (!onScreen) { setAim(null); return; }

      /* Held low on her near shoulder — below the visible crop, so the stick
         appears to come from a hand we never have to draw. Measured off the
         AVATAR CANVAS rather than the dock: the dock is a flex column that also
         holds the mic control and its gap, so its box is taller than she is and
         the hand ended up floating below her. */
      const from = { x: d.left + d.width * 0.2, y: d.top + d.height * 0.62 };

      /* Just under the word, a little right of centre — where a pointer rests
         when a teacher underlines a term. Not the centre of the box: a tip
         sitting on top of the glyphs hides the thing being pointed at. */
      const to = { x: t.left + t.width * 0.66, y: t.bottom + 4 };

      // Pointing backwards past her own body looks wrong; skip it.
      if (to.x > from.x - 40) { setAim(null); return; }
      setAim({ from, to });
    };

    measure();

    /* Re-measure on anything that moves the target: scrolling the notebook,
       resizing, or the page growing as she writes. rAF-coalesced, because the
       notebook scroll fires continuously. */
    const onMove = () => {
      cancelAnimationFrame(raf.current);
      raf.current = requestAnimationFrame(measure);
    };
    const scroller = document.querySelector('[class*="scroll"]');
    scroller?.addEventListener("scroll", onMove, { passive: true });
    window.addEventListener("resize", onMove);
    return () => {
      cancelAnimationFrame(raf.current);
      scroller?.removeEventListener("scroll", onMove);
      window.removeEventListener("resize", onMove);
    };
  }, [live, hot, revision]);

  if (!aim) return null;

  const { from, to } = aim;
  const angle = Math.atan2(to.y - from.y, to.x - from.x);
  const butt = {
    x: from.x - Math.cos(angle) * BUTT_PX,
    y: from.y - Math.sin(angle) * BUTT_PX,
  };
  const cane = taperedCane(butt, to);

  return (
    <svg
      className={s.layer}
      aria-hidden="true"
      style={{ ["--settle" as string]: `${SETTLE_MS}ms` }}
    >
      <path className={s.shadow} d={cane.outline} />
      <path className={s.shaft} d={cane.outline} />
      {/* Two lacquer bands near the grip. Cheap, and they are most of what makes
          a line read as a cane rather than as a connector. */}
      {cane.bands.map((b, i) => (
        <line key={i} className={s.band}
              x1={b.x1} y1={b.y1} x2={b.x2} y2={b.y2} />
      ))}
      {/* The brass ferrule, resting on the word. */}
      <circle className={s.tip} cx={to.x} cy={to.y} r={3.2} />
    </svg>
  );
}

/* A bamboo pointer: long, thin, tapering to the tip, with a little flex in it.
 *
 * A plain <line> read as a connector drawn between two boxes. What makes it a
 * STICK is that it is thicker in the hand than at the tip and that it is not
 * perfectly straight — so the shaft is a closed path built by walking a shallow
 * curve and offsetting it perpendicular by a width that shrinks along the way.
 */
function taperedCane(
  butt: { x: number; y: number },
  tip: { x: number; y: number },
) {
  const dx = tip.x - butt.x;
  const dy = tip.y - butt.y;
  const length = Math.hypot(dx, dy) || 1;
  // Perpendicular unit vector, for both the sag and the thickness.
  const nx = -dy / length;
  const ny = dx / length;

  // A hand-span of sag, so it looks like cane rather than steel. Scaled with
  // length: a short pointer held close should not bow like a fishing rod.
  const sag = Math.min(14, length * 0.028);
  const ctrl = {
    x: (butt.x + tip.x) / 2 + nx * sag,
    y: (butt.y + tip.y) / 2 + ny * sag,
  };

  const at = (t: number) => {
    const u = 1 - t;
    return {
      x: u * u * butt.x + 2 * u * t * ctrl.x + t * t * tip.x,
      y: u * u * butt.y + 2 * u * t * ctrl.y + t * t * tip.y,
    };
  };
  // 3.4px in the hand down to 1.0px at the tip, eased so the taper is gentle
  // along the shaft and quicker near the point.
  const halfWidth = (t: number) => (3.4 - 2.4 * t * t) / 2;

  const STEPS = 24;
  const left: string[] = [];
  const right: { x: number; y: number }[] = [];
  for (let i = 0; i <= STEPS; i++) {
    const t = i / STEPS;
    const p = at(t);
    const w = halfWidth(t);
    left.push(`${i ? "L" : "M"}${(p.x + nx * w).toFixed(2)},${(p.y + ny * w).toFixed(2)}`);
    right.push({ x: p.x - nx * w, y: p.y - ny * w });
  }
  const back = right
    .reverse()
    .map((p) => `L${p.x.toFixed(2)},${p.y.toFixed(2)}`)
    .join("");

  // Bands sit a third and two-fifths of the way along — near the grip, where a
  // real one is bound.
  const bands = [0.1, 0.17].map((t) => {
    const p = at(t);
    const w = halfWidth(t) + 0.6;
    return {
      x1: p.x + nx * w, y1: p.y + ny * w,
      x2: p.x - nx * w, y2: p.y - ny * w,
    };
  });

  return { outline: `${left.join("")}${back}Z`, bands };
}
