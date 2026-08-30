/* Drawings for the student-facing screens.
 *
 * Same rule as everywhere else in this product: each one depicts something
 * that actually exists. The tutor is the avatar lib/avatar/rig.js draws, with
 * its own colouring; the board carries the notebook's margin rule and its
 * real block kinds; the readiness chart uses the five mastery levels the
 * schema has.
 *
 * Chrome comes from tokens so these follow the palette. Skin, hair and cloth
 * are literals — they are not brand colours and must not move with it. */

type P = { className?: string };

const SKIN = "#C08256";
const SKIN_SHADE = "#A66840";
const HAIR = "#2A2118";
const CLOTH = "#96C6B4";
const CLOTH_LIGHT = "#CFEBE0";
const GOLD = "#C0A64B";
const LIP = "#A2565A";

/** The tutor, waiting. Shown on the dashboard so the person you are about to
 *  talk to is present before you press anything. */
export function TutorBust({ className }: P) {
  return (
    <svg
      className={className}
      viewBox="0 0 180 168"
      role="img"
      aria-label="Your tutor, ready to start."
    >
      {/* the notebook she teaches on, behind her */}
      <rect x="96" y="14" width="80" height="104" rx="6"
        fill="var(--paper)" stroke="var(--line-hard)" />
      <line x1="110" y1="14" x2="110" y2="118" stroke="var(--accent-rule)" strokeWidth="1.4" />
      <g fill="var(--line-hard)">
        <rect x="118" y="30" width="42" height="6" rx="3" />
        <rect x="118" y="46" width="30" height="5" rx="2.5" />
        <rect x="118" y="72" width="48" height="5" rx="2.5" />
        <rect x="118" y="84" width="36" height="5" rx="2.5" />
      </g>
      <rect x="116" y="56" width="34" height="11" rx="3" fill="var(--accent-tint)" />

      {/* her */}
      <path d="M4 166c0-30 26-48 58-48s58 18 58 48z" fill={CLOTH} />
      <path d="M22 166c0-20 17-33 40-33s40 13 40 33z" fill={CLOTH_LIGHT} />
      <path d="M50 100h24v20a12 12 0 0 1-24 0z" fill={SKIN_SHADE} />
      <ellipse cx="62" cy="62" rx="45" ry="48" fill={HAIR} />
      <ellipse cx="62" cy="66" rx="35" ry="39" fill={SKIN} />
      <path d="M27 58c2-24 16-35 35-35s33 11 35 35c-6-15-18-21-35-21S33 43 27 58z" fill={HAIR} />
      <path d="M44 58q7-4 14-1" stroke={HAIR} strokeWidth="2.8" fill="none" strokeLinecap="round" />
      <path d="M66 57q7-3 14 1" stroke={HAIR} strokeWidth="2.8" fill="none" strokeLinecap="round" />
      <ellipse cx="50" cy="69" rx="6" ry="4.6" fill="#FFFFFF" />
      <ellipse cx="74" cy="69" rx="6" ry="4.6" fill="#FFFFFF" />
      <circle cx="51" cy="69" r="2.9" fill={HAIR} />
      <circle cx="75" cy="69" r="2.9" fill={HAIR} />
      <circle cx="52" cy="68" r="0.9" fill="#FFFFFF" />
      <circle cx="76" cy="68" r="0.9" fill="#FFFFFF" />
      <circle cx="62" cy="52" r="2.8" fill="var(--accent)" />
      <path d="M62 74v7h-4" stroke={SKIN_SHADE} strokeWidth="1.4" fill="none" strokeLinecap="round" />
      <path d="M54 89q8 6 16 0" stroke={LIP} strokeWidth="2.6" fill="none" strokeLinecap="round" />
      <circle cx="24" cy="75" r="3.6" fill={GOLD} />
      <circle cx="100" cy="75" r="3.6" fill={GOLD} />
      <path d="M24 79v5M100 79v5" stroke={GOLD} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

/* ── the three things you can do tonight ──────────────────────────────
   Small, and set at the end of their row rather than above it, because
   these rows are read left to right as sentences. */

/** Revise today's class: the board, already part-written. */
export function MarkRevise({ className }: P) {
  return (
    <svg className={className} viewBox="0 0 64 48" aria-hidden="true">
      <rect x="1" y="1" width="62" height="46" rx="5"
        fill="var(--paper)" stroke="var(--line-hard)" />
      <line x1="12" y1="1" x2="12" y2="47" stroke="var(--accent-rule)" strokeWidth="1.3" />
      <rect x="19" y="10" width="26" height="5" rx="2.5" fill="var(--ink-mid)" />
      <rect x="19" y="22" width="20" height="7" rx="2.5" fill="var(--accent-tint)" />
      <rect x="43" y="24" width="12" height="4" rx="2" fill="var(--line-hard)" />
      <rect x="19" y="35" width="34" height="4" rx="2" fill="var(--line-hard)" />
    </svg>
  );
}

/** Ask a doubt: a marked term, and the question about it. */
export function MarkDoubt({ className }: P) {
  return (
    <svg className={className} viewBox="0 0 64 48" aria-hidden="true">
      <rect x="1" y="8" width="42" height="32" rx="5"
        fill="var(--paper)" stroke="var(--line-hard)" />
      <rect x="9" y="17" width="26" height="4" rx="2" fill="var(--line-hard)" />
      <rect x="9" y="26" width="16" height="6" rx="2" fill="var(--accent-tint)" />
      <circle cx="49" cy="30" r="13" fill="var(--accent-wash)" stroke="var(--accent-rule)" />
      <path d="M45 26a4.2 4.2 0 1 1 4.6 4.2v2.2" stroke="var(--accent)" strokeWidth="2"
        fill="none" strokeLinecap="round" />
      <circle cx="49.6" cy="36.4" r="1.5" fill="var(--accent)" />
    </svg>
  );
}

/** Prepare for exam: where you stand, worst first. */
export function MarkExam({ className }: P) {
  return (
    <svg className={className} viewBox="0 0 64 48" aria-hidden="true">
      <rect x="1" y="1" width="62" height="46" rx="5"
        fill="var(--paper)" stroke="var(--line-hard)" />
      <g>
        <rect x="10" y="11" width="44" height="6" rx="3" fill="var(--line)" />
        <rect x="10" y="11" width="14" height="6" rx="3" fill="var(--warn)" />
        <rect x="10" y="21" width="44" height="6" rx="3" fill="var(--line)" />
        <rect x="10" y="21" width="28" height="6" rx="3" fill="var(--accent)" />
        <rect x="10" y="31" width="44" height="6" rx="3" fill="var(--line)" />
        <rect x="10" y="31" width="38" height="6" rx="3" fill="var(--good)" />
      </g>
    </svg>
  );
}

/** The board as the class ended: the derivation written out, the question
 *  asked, and the answer never written — the last line trails off into
 *  nothing and the clock has run out.
 *
 *  This was a raised hand in a circle. At 66px a hand is unreadable — it came
 *  out as a brown shape in a pink disc — and it was also the wrong subject:
 *  the section is about what was left on the BOARD when the bell went, not
 *  about a student asking. */
export function MarkOpenQuestion({ className }: P) {
  return (
    <svg
      className={className}
      viewBox="0 0 150 92"
      role="img"
      aria-label="The board at the end of the lesson: the question still written up, and the answer never filled in."
    >
      {/* the board */}
      <rect x="1" y="9" width="122" height="74" rx="6" fill="var(--ink-strong)" />
      <rect x="9" y="17" width="106" height="58" rx="3" fill="none"
        stroke="rgba(255,255,255,0.16)" />

      {/* what he got through */}
      <g stroke="var(--cream)" strokeWidth="3" strokeLinecap="round" opacity=".82">
        <path d="M20 30h44" />
        <path d="M20 42h64" />
      </g>
      {/* the question */}
      <path d="M20 55a5 5 0 1 1 5.6 5v2.6" stroke="var(--accent-lift)" strokeWidth="2.6"
        fill="none" strokeLinecap="round" />
      <circle cx="25.6" cy="67" r="1.8" fill="var(--accent-lift)" />
      {/* and the line that never got written */}
      <path d="M38 62h48" stroke="rgba(255,255,255,0.34)" strokeWidth="3"
        strokeLinecap="round" strokeDasharray="1 9" />

      {/* time up */}
      <circle cx="128" cy="24" r="17" fill="var(--ground)" stroke="var(--line-hard)" />
      <path d="M128 14v10l6 4" stroke="var(--ink-mid)" strokeWidth="2.2"
        fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M141 12a13 13 0 0 1 3 7M115 12a13 13 0 0 0-3 7"
        stroke="var(--accent)" strokeWidth="1.8" fill="none" strokeLinecap="round" />
    </svg>
  );
}
