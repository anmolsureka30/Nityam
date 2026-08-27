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
 * IT DOES NOT REACH THE WORD, and that is deliberate. The first version drew a
 * line all the way to the anchor: from her shoulder at the bottom right to a
 * formula at the top left, that is a thirteen-hundred-pixel diagonal slicing
 * straight through the lesson — obscuring the very text it was indicating. A
 * real pointer is a pointer-length object. So the stick is capped at a
 * plausible physical length and gives DIRECTION; the `.anchorHot` highlight
 * that point_at already puts on the word gives PRECISION. Together they read
 * correctly, and neither has to cover the page to do it. */

interface Aim {
  /** Where the stick is held, and where it points. Viewport pixels. */
  from: { x: number; y: number };
  to: { x: number; y: number };
}

/** How long the raise/lower takes; matches the CSS transition. */
const SETTLE_MS = 260;

/** A pointer is about this long on screen. Capped so it never crosses the
 *  lesson — see the note above. */
const STICK_PX = 300;
/** And never so long that it overshoots a nearby target. */
const CLEARANCE = 34;

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

      const dock = document.querySelector<HTMLElement>("[data-avatar-dock]");
      if (!word || !dock) { setAim(null); return; }

      const t = word.getBoundingClientRect();
      const d = dock.getBoundingClientRect();

      // Off screen, or scrolled behind the chrome: no stick rather than a stick
      // pointing into nowhere.
      const onScreen =
        t.bottom > 96 && t.top < window.innerHeight - 8 &&
        t.right > 0 && t.left < window.innerWidth;
      if (!onScreen) { setAim(null); return; }

      /* Held low on her near shoulder — below the visible crop, so the stick
         appears to come from a hand we never have to draw. */
      const from = { x: d.left + d.width * 0.24, y: d.top + d.height * 0.72 };
      // Aim at the word's centre for the ANGLE, then stop short of it.
      const target = { x: t.left + t.width / 2, y: t.top + t.height / 2 };

      // Pointing backwards past her own body looks wrong; skip it.
      if (target.x > from.x - 40) { setAim(null); return; }

      const dx = target.x - from.x;
      const dy = target.y - from.y;
      const distance = Math.hypot(dx, dy);
      const reach = Math.min(STICK_PX, Math.max(80, distance - CLEARANCE));
      const to = {
        x: from.x + (dx / distance) * reach,
        y: from.y + (dy / distance) * reach,
      };
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
  // Overshoot behind her hand so the near end is hidden by her figure rather
  // than stopping in mid-air.
  const tailX = from.x + Math.cos(angle) * -34;
  const tailY = from.y + Math.sin(angle) * -34;

  return (
    <svg
      className={s.layer}
      aria-hidden="true"
      style={{ ["--settle" as string]: `${SETTLE_MS}ms` }}
    >
      {/* Drawn in two strokes: a soft dark one underneath for separation
          against a white page, then the stick itself on top. */}
      <line
        className={s.shadow}
        x1={tailX} y1={tailY} x2={to.x} y2={to.y}
      />
      <line
        className={s.stick}
        x1={tailX} y1={tailY} x2={to.x} y2={to.y}
      />
      {/* The ferrule at the stick's own tip. There is no marker on the word:
          point_at already lights it up, and a second dot floating in the gap
          between the two would read as a broken connector. */}
      <circle className={s.tip} cx={to.x} cy={to.y} r={3.5} />
    </svg>
  );
}
