/* Drawings of the actual product, not stock spot-art.
 *
 * Every one of these depicts something that really exists: the tutor is the
 * avatar frontend/src/lib/avatar/rig.js draws (same colouring — dark hair,
 * warm skin, the mint dupatta #96C6B4 and gold #C0A64B it uses); the board is
 * the real notebook with its margin rule and its real block kinds (heading,
 * equation with a pointable anchor, callout, struck line); the memory card
 * uses the five mastery levels the schema actually has and their real labels.
 *
 * Inline SVG, no libraries, no external images — the page is statically
 * rendered and these ship as markup. Chrome is drawn from the shared tokens
 * so the illustrations restyle with the palette; skin, hair and cloth are
 * literals because they are not brand colours and must not shift with it.
 *
 * Each carries role="img" and an aria-label saying what it shows, because a
 * decorative-looking drawing that in fact carries the argument of its section
 * should not be silent. */

type P = { className?: string };

const SKIN = "#C08256";
const SKIN_SHADE = "#A66840";
const HAIR = "#2A2118";
const CLOTH = "#96C6B4";
const CLOTH_LIGHT = "#CFEBE0";
const GOLD = "#C0A64B";
const LIP = "#A2565A";

/* ── the tutor ─────────────────────────────────────────────────────────
   The face the student actually sees, drawn flat. Speaking: mouth open,
   waveform running under her. */
export function TutorPortrait({ className }: P) {
  return (
    <svg
      className={className}
      viewBox="0 0 170 190"
      role="img"
      aria-label="The Nityam tutor: a teacher mid-sentence, with her speech waveform beneath her."
    >
      <ellipse cx="85" cy="176" rx="66" ry="9" fill="var(--cream)" />

      {/* dupatta over the shoulders */}
      <path d="M22 176c0-30 28-49 63-49s63 19 63 49z" fill={CLOTH} />
      <path d="M42 176c0-22 19-36 43-36s43 14 43 36z" fill={CLOTH_LIGHT} />
      <path d="M85 140v36" stroke={CLOTH} strokeWidth="1.5" opacity=".7" />

      {/* neck */}
      <path d="M72 112h26v22a13 13 0 0 1-26 0z" fill={SKIN_SHADE} />

      {/* hair behind */}
      <ellipse cx="85" cy="70" rx="49" ry="52" fill={HAIR} />

      {/* face */}
      <ellipse cx="85" cy="74" rx="38" ry="43" fill={SKIN} />

      {/* centre-parted hair over the brow */}
      <path d="M47 66c2-26 18-38 38-38s36 12 38 38c-6-16-19-23-38-23S53 50 47 66z" fill={HAIR} />
      <path d="M85 28v15" stroke={SKIN_SHADE} strokeWidth="1.2" opacity=".35" />

      {/* brows */}
      <path d="M65 66q8-5 16-1" stroke={HAIR} strokeWidth="3" fill="none" strokeLinecap="round" />
      <path d="M89 65q8-4 16 1" stroke={HAIR} strokeWidth="3" fill="none" strokeLinecap="round" />

      {/* eyes */}
      <ellipse cx="72" cy="77" rx="6.5" ry="5" fill="#FFFFFF" />
      <ellipse cx="98" cy="77" rx="6.5" ry="5" fill="#FFFFFF" />
      <circle cx="73" cy="77" r="3.1" fill={HAIR} />
      <circle cx="99" cy="77" r="3.1" fill={HAIR} />
      <circle cx="74.2" cy="75.8" r="1" fill="#FFFFFF" />
      <circle cx="100.2" cy="75.8" r="1" fill="#FFFFFF" />

      {/* bindi */}
      <circle cx="85" cy="60" r="3" fill="var(--accent)" />

      {/* nose, and a mouth caught mid-word */}
      <path d="M85 82v8h-4" stroke={SKIN_SHADE} strokeWidth="1.5" fill="none" strokeLinecap="round" />
      <ellipse cx="85" cy="99" rx="9" ry="6.5" fill={LIP} />
      <path d="M76 99q9-5 18 0" stroke="#8A4249" strokeWidth="1.2" fill="none" />

      {/* gold jhumkas */}
      <circle cx="45" cy="83" r="4" fill={GOLD} />
      <circle cx="125" cy="83" r="4" fill={GOLD} />
      <path d="M45 87v6M125 87v6" stroke={GOLD} strokeWidth="2" strokeLinecap="round" />

      {/* she is talking */}
      <g stroke="var(--accent)" strokeWidth="2.5" strokeLinecap="round" opacity=".85">
        <path d="M16 152v8" />
        <path d="M25 147v18" />
        <path d="M34 143v26" />
        <path d="M136 143v26" />
        <path d="M145 147v18" />
        <path d="M154 152v8" />
      </g>
    </svg>
  );
}

/* ── the board ─────────────────────────────────────────────────────────
   The real notebook page: margin rule down the left, a heading, an equation
   with one term marked as a pointable anchor, a callout, and a struck line
   — every block kind canvas/tools.py can publish. */
export function BoardSketch({ className }: P) {
  return (
    <svg
      className={className}
      viewBox="0 0 300 210"
      role="img"
      aria-label="The tutor's board: a heading, the range formula with one term highlighted, a note, a struck-out wrong line, and a finding callout."
    >
      <rect x="1" y="1" width="298" height="208" rx="8" fill="var(--paper)" stroke="var(--line)" />
      {/* the exercise-book margin rule */}
      <line x1="34" y1="1" x2="34" y2="209" stroke="var(--accent-rule)" strokeWidth="1.5" />

      {/* heading */}
      <rect x="48" y="20" width="112" height="9" rx="3" fill="var(--ink)" />

      {/* equation, with sin(2θ) marked as an anchor */}
      <rect x="48" y="46" width="26" height="7" rx="2.5" fill="var(--ink-mid)" />
      <rect x="80" y="42" width="52" height="15" rx="3" fill="var(--accent-tint)" />
      <rect x="86" y="46" width="40" height="7" rx="2.5" fill="var(--accent-deep)" />
      <rect x="138" y="46" width="18" height="7" rx="2.5" fill="var(--ink-mid)" />
      <line x1="48" y1="63" x2="156" y2="63" stroke="var(--line-hard)" strokeWidth="1" />
      <rect x="90" y="68" width="22" height="7" rx="2.5" fill="var(--ink-mid)" />

      {/* prose */}
      <rect x="48" y="90" width="216" height="6" rx="3" fill="var(--line-hard)" />
      <rect x="48" y="102" width="186" height="6" rx="3" fill="var(--line-hard)" />

      {/* a line she struck out */}
      <rect x="48" y="122" width="150" height="6" rx="3" fill="var(--line)" />
      <line x1="44" y1="125" x2="204" y2="125" stroke="var(--danger)" strokeWidth="1.6" />

      {/* callout: YOU WORKED THIS OUT */}
      <rect x="44" y="144" width="220" height="48" rx="6" fill="var(--accent-wash)" />
      <rect x="44" y="144" width="3.5" height="48" rx="1.75" fill="var(--accent)" />
      <rect x="58" y="156" width="88" height="7" rx="3" fill="var(--accent-deep)" />
      <rect x="58" y="172" width="186" height="6" rx="3" fill="var(--ink-dim)" />

      {/* the pointing stick touching the anchor */}
      <path d="M286 30 L140 47" stroke="var(--ink-mid)" strokeWidth="2" strokeLinecap="round" />
      <circle cx="140" cy="47" r="4" fill="var(--accent)" />
    </svg>
  );
}

/* ── what it remembers ─────────────────────────────────────────────────
   The five mastery levels the schema really has, one of them moving, and an
   open doubt underneath with the citation that backs it. */
export function MemoryCard({ className }: P) {
  return (
    <svg
      className={className}
      viewBox="0 0 300 200"
      role="img"
      aria-label="What the tutor remembers: two concepts with their mastery moving from Misunderstood to Getting there, and an open doubt with the session and turn it came from."
    >
      <rect x="1" y="1" width="298" height="198" rx="8" fill="var(--paper)" stroke="var(--line)" />

      <rect x="18" y="16" width="74" height="7" rx="3.5" fill="var(--ink-dim)" />

      {/* row one — moved forward */}
      <rect x="18" y="38" width="264" height="42" rx="6" fill="var(--ground)" />
      <rect x="30" y="48" width="96" height="7" rx="3.5" fill="var(--ink)" />
      <rect x="30" y="63" width="54" height="10" rx="5" fill="var(--line-hard)" />
      <path d="M92 68h14" stroke="var(--ink-dim)" strokeWidth="1.4" />
      <path d="M103 65l4 3-4 3" stroke="var(--ink-dim)" strokeWidth="1.4" fill="none" />
      <rect x="112" y="63" width="58" height="10" rx="5" fill="var(--good)" />
      <rect x="214" y="61" width="68" height="14" rx="4" fill="var(--good-wash, #F0F8F5)" />
      <rect x="222" y="66" width="52" height="5" rx="2.5" fill="var(--good)" />

      {/* row two — still where it was */}
      <rect x="18" y="88" width="264" height="34" rx="6" fill="var(--ground)" />
      <rect x="30" y="97" width="118" height="7" rx="3.5" fill="var(--ink)" />
      <rect x="30" y="110" width="46" height="8" rx="4" fill="var(--warn)" />

      {/* the open doubt */}
      <rect x="18" y="132" width="264" height="52" rx="6" fill="var(--warn-wash, #FCF7F0)" />
      <rect x="18" y="132" width="3.5" height="52" rx="1.75" fill="var(--warn)" />
      <rect x="32" y="142" width="62" height="6" rx="3" fill="var(--warn)" />
      <rect x="32" y="156" width="228" height="5.5" rx="2.75" fill="var(--ink-mid)" />
      <rect x="32" y="167" width="164" height="5.5" rx="2.75" fill="var(--ink-mid)" />
      {/* the citation — every claim points at a real turn */}
      <rect x="210" y="164" width="56" height="12" rx="3" fill="var(--paper)" stroke="var(--line-hard)" />
      <rect x="216" y="168" width="44" height="4" rx="2" fill="var(--ink-dim)" />
    </svg>
  );
}

/* ── step 1: the lesson gets recorded ─────────────────────────────────── */
export function ClassroomCapture({ className }: P) {
  return (
    <svg
      className={className}
      viewBox="0 0 220 130"
      role="img"
      aria-label="A camera and microphone in the classroom recording the teacher's board."
    >
      <rect x="14" y="12" width="128" height="82" rx="5" fill="var(--ink-strong)" />
      <g stroke="var(--cream)" strokeWidth="2.6" strokeLinecap="round" opacity=".82">
        <path d="M30 32h52" />
        <path d="M30 46h78" />
        <path d="M30 60h40" />
        <path d="M86 60h34" />
      </g>
      <path d="M30 76q22-16 44 0t44-4" stroke="var(--accent-lift)" strokeWidth="2.4" fill="none" strokeLinecap="round" />

      {/* the teacher at the board */}
      <circle cx="160" cy="52" r="10" fill={SKIN} />
      <path d="M150 52a10 10 0 0 1 20 0z" fill={HAIR} />
      <path d="M146 94c0-9 6-16 14-16s14 7 14 16z" fill={CLOTH} />

      {/* camera + mic */}
      <rect x="176" y="14" width="32" height="22" rx="4" fill="var(--paper)" stroke="var(--line-hard)" />
      <circle cx="192" cy="25" r="6" fill="var(--ink-mid)" />
      <circle cx="192" cy="25" r="2.4" fill="var(--accent)" />
      <g stroke="var(--accent)" strokeWidth="1.8" fill="none" strokeLinecap="round">
        <path d="M170 108q6-6 0-12" />
        <path d="M178 112q11-10 0-20" />
      </g>
      <rect x="154" y="102" width="12" height="18" rx="6" fill="var(--ink-mid)" />
      <line x1="14" y1="112" x2="142" y2="112" stroke="var(--line-hard)" strokeWidth="1.5" />
    </svg>
  );
}

/* ── step 2: one profile per student, rebuilt daily ───────────────────── */
export function ProfileBuild({ className }: P) {
  return (
    <svg
      className={className}
      viewBox="0 0 220 130"
      role="img"
      aria-label="A profile of one student being assembled: mastery bars at different levels, updated each day."
    >
      <circle cx="40" cy="42" r="19" fill="var(--accent-wash)" stroke="var(--accent-rule)" />
      <circle cx="40" cy="36" r="7.5" fill="var(--accent)" />
      <path d="M26 56a14 14 0 0 1 28 0z" fill="var(--accent)" />

      <g>
        <rect x="74" y="24" width="130" height="9" rx="4.5" fill="var(--line)" />
        <rect x="74" y="24" width="104" height="9" rx="4.5" fill="var(--good)" />
        <rect x="74" y="42" width="130" height="9" rx="4.5" fill="var(--line)" />
        <rect x="74" y="42" width="52" height="9" rx="4.5" fill="var(--warn)" />
        <rect x="74" y="60" width="130" height="9" rx="4.5" fill="var(--line)" />
        <rect x="74" y="60" width="84" height="9" rx="4.5" fill="var(--accent)" />
      </g>

      {/* it is rebuilt every day, not once */}
      <g stroke="var(--ink-dim)" strokeWidth="1.6" fill="none" strokeLinecap="round">
        <path d="M28 96a16 16 0 1 1 5 11" />
        <path d="M28 86v10h10" />
      </g>
      <rect x="58" y="90" width="76" height="6" rx="3" fill="var(--line-hard)" />
      <rect x="58" y="102" width="120" height="6" rx="3" fill="var(--line-hard)" />
      <rect x="58" y="114" width="52" height="6" rx="3" fill="var(--line-hard)" />
    </svg>
  );
}

/* ── step 3: she teaches it back, one to one ──────────────────────────── */
export function OneToOne({ className }: P) {
  return (
    <svg
      className={className}
      viewBox="0 0 220 130"
      role="img"
      aria-label="The tutor speaking, with her board filling in beside her as she talks."
    >
      {/* tutor */}
      <circle cx="38" cy="46" r="18" fill={SKIN} />
      <path d="M20 46a18 18 0 0 1 36 0z" fill={HAIR} />
      <circle cx="38" cy="34" r="2.6" fill="var(--accent)" />
      <circle cx="32" cy="48" r="2.2" fill={HAIR} />
      <circle cx="44" cy="48" r="2.2" fill={HAIR} />
      <ellipse cx="38" cy="56" rx="4.5" ry="3" fill={LIP} />
      <path d="M14 100c0-14 11-24 24-24s24 10 24 24z" fill={CLOTH} />

      {/* what she is saying */}
      <g stroke="var(--accent)" strokeWidth="2.2" strokeLinecap="round">
        <path d="M70 44v12" />
        <path d="M78 38v24" />
        <path d="M86 44v12" />
      </g>

      {/* the board she is filling */}
      <rect x="100" y="16" width="106" height="92" rx="6" fill="var(--paper)" stroke="var(--line)" />
      <line x1="112" y1="16" x2="112" y2="108" stroke="var(--accent-rule)" strokeWidth="1.2" />
      <rect x="120" y="30" width="48" height="6" rx="3" fill="var(--ink)" />
      <rect x="120" y="46" width="34" height="10" rx="3" fill="var(--accent-tint)" />
      <rect x="160" y="48" width="30" height="6" rx="3" fill="var(--ink-mid)" />
      <rect x="120" y="68" width="74" height="5" rx="2.5" fill="var(--line-hard)" />
      <rect x="120" y="80" width="58" height="5" rx="2.5" fill="var(--line-hard)" />

    </svg>
  );
}

/* ── step 4: the class, back to the teacher ───────────────────────────── */
export function TeacherView({ className }: P) {
  return (
    <svg
      className={className}
      viewBox="0 0 220 130"
      role="img"
      aria-label="A teacher's view of the whole class: most students understood today's topic, eleven are quietly stuck."
    >
      <rect x="12" y="10" width="196" height="108" rx="7" fill="var(--paper)" stroke="var(--line)" />
      <rect x="26" y="24" width="70" height="7" rx="3.5" fill="var(--ink)" />
      <rect x="150" y="23" width="44" height="14" rx="7" fill="var(--good-wash, #F0F8F5)" />
      <rect x="158" y="28" width="28" height="4" rx="2" fill="var(--good)" />

      {/* forty students; the stuck ones are not hidden */}
      <g>
        {Array.from({ length: 40 }, (_, i) => {
          const stuck = [3, 6, 9, 14, 17, 21, 25, 28, 31, 35, 38].includes(i);
          return (
            <circle
              key={i}
              cx={30 + (i % 10) * 17}
              cy={54 + Math.floor(i / 10) * 16}
              r="5.4"
              fill={stuck ? "var(--warn)" : "var(--line-hard)"}
            />
          );
        })}
      </g>
    </svg>
  );
}

/* ── one lesson, forty speeds ─────────────────────────────────────────── */
export function ClassOfForty({ className }: P) {
  return (
    <svg
      className={className}
      viewBox="0 0 200 96"
      role="img"
      aria-label="Forty students taught at one speed: the middle keeps up, the fastest and the slowest are missed."
    >
      <rect x="0" y="38" width="200" height="20" rx="10" fill="var(--accent-wash)" />
      {Array.from({ length: 40 }, (_, i) => {
        const col = i % 20;
        const row = Math.floor(i / 20);
        const missed = col < 3 || col > 16;
        return (
          <circle
            key={i}
            cx={8 + col * 9.6}
            cy={row === 0 ? 40 : 56}
            r="3.6"
            fill={missed ? "var(--warn)" : "var(--ink-faint)"}
            opacity={missed ? 1 : 0.55}
          />
        );
      })}
      <path d="M4 78h192" stroke="var(--line-hard)" strokeWidth="1.4" />
      <path d="M96 70v16" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

/* ── a small gap, four years later ────────────────────────────────────── */
export function WideningGap({ className }: P) {
  return (
    <svg
      className={className}
      viewBox="0 0 200 96"
      role="img"
      aria-label="Two paths from the same point: one keeps rising, the other falls away over four years."
    >
      <line x1="14" y1="82" x2="192" y2="82" stroke="var(--line-hard)" strokeWidth="1.4" />
      <line x1="14" y1="10" x2="14" y2="82" stroke="var(--line-hard)" strokeWidth="1.4" />
      <path d="M20 62q52-24 168-42" stroke="var(--good)" strokeWidth="2.6" fill="none" strokeLinecap="round" />
      <path d="M20 62q52 6 168 16" stroke="var(--warn)" strokeWidth="2.6" fill="none" strokeLinecap="round" />
      <path d="M188 20v58" stroke="var(--danger)" strokeWidth="1.4" strokeDasharray="3 3" />
      <circle cx="20" cy="62" r="4" fill="var(--ink-mid)" />
      <circle cx="188" cy="20" r="4" fill="var(--good)" />
      <circle cx="188" cy="78" r="4" fill="var(--warn)" />
    </svg>
  );
}

/* ── the app teaches a different lesson than the school did ───────────── */
export function TwoSyllabuses({ className }: P) {
  return (
    <svg
      className={className}
      viewBox="0 0 200 96"
      role="img"
      aria-label="Two syllabuses that do not meet: what the class taught, and what a study app teaches instead."
    >
      <rect x="10" y="18" width="72" height="60" rx="6" fill="var(--paper)" stroke="var(--line-hard)" />
      <line x1="20" y1="18" x2="20" y2="78" stroke="var(--accent-rule)" strokeWidth="1.3" />
      <rect x="28" y="30" width="42" height="5" rx="2.5" fill="var(--ink)" />
      <rect x="28" y="42" width="46" height="4.5" rx="2.25" fill="var(--line-hard)" />
      <rect x="28" y="52" width="34" height="4.5" rx="2.25" fill="var(--line-hard)" />

      <rect x="118" y="18" width="72" height="60" rx="6" fill="var(--ground-deep)" stroke="var(--line-hard)" />
      <rect x="132" y="30" width="42" height="5" rx="2.5" fill="var(--ink-dim)" />
      <rect x="132" y="42" width="46" height="4.5" rx="2.25" fill="var(--line)" />
      <rect x="132" y="52" width="30" height="4.5" rx="2.25" fill="var(--line)" />

      <path d="M88 40l24 18M112 40L88 58" stroke="var(--danger)" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}

/* ── the NCERT page, and the figure cropped out of it ─────────────────── */
export function TextbookFigure({ className }: P) {
  return (
    <svg
      className={className}
      viewBox="-10 0 240 150"
      role="img"
      aria-label="A page of the NCERT textbook with one figure cropped out of it and put on the board."
    >
      <rect x="6" y="8" width="98" height="134" rx="5" fill="var(--paper)" stroke="var(--line-hard)" />
      <g fill="var(--line-hard)">
        <rect x="18" y="22" width="60" height="5" rx="2.5" />
        <rect x="18" y="34" width="74" height="4" rx="2" />
        <rect x="18" y="44" width="70" height="4" rx="2" />
        <rect x="18" y="112" width="74" height="4" rx="2" />
        <rect x="18" y="122" width="52" height="4" rx="2" />
      </g>
      {/* the figure, and the box the build script computed for it */}
      <rect x="16" y="58" width="78" height="46" rx="3" fill="var(--ground)" stroke="var(--accent)" strokeDasharray="4 3" />
      <path d="M24 96q20-30 40-6t22-18" stroke="var(--ink-mid)" strokeWidth="1.8" fill="none" />
      <line x1="24" y1="96" x2="88" y2="96" stroke="var(--ink-dim)" strokeWidth="1.2" />

      <path d="M108 80h24" stroke="var(--accent)" strokeWidth="2" />
      <path d="M128 75l6 5-6 5" stroke="var(--accent)" strokeWidth="2" fill="none" strokeLinecap="round" />

      <rect x="138" y="52" width="76" height="52" rx="5" fill="var(--paper)" stroke="var(--line)" />
      <path d="M148 92q20-32 40-8t18-20" stroke="var(--ink)" strokeWidth="2" fill="none" />
      <line x1="148" y1="92" x2="206" y2="92" stroke="var(--ink-dim)" strokeWidth="1.2" />
      <rect x="148" y="60" width="30" height="5" rx="2.5" fill="var(--accent-deep)" />
    </svg>
  );
}

/* ── a simulation she built, with the axes held still ─────────────────── */
export function SimulationSketch({ className }: P) {
  return (
    <svg
      className={className}
      viewBox="0 0 220 150"
      role="img"
      aria-label="A projectile simulation with fixed gridlines, three angles drawn, and forty-five degrees reaching furthest."
    >
      <rect x="1" y="1" width="218" height="148" rx="7" fill="var(--paper)" stroke="var(--line)" />
      <g stroke="var(--line-soft)" strokeWidth="1">
        <path d="M14 34h192M14 58h192M14 82h192M14 106h192" />
        <path d="M46 18v106M78 18v106M110 18v106M142 18v106M174 18v106" />
      </g>
      <line x1="14" y1="124" x2="206" y2="124" stroke="var(--ink-mid)" strokeWidth="1.6" />
      <line x1="14" y1="18" x2="14" y2="124" stroke="var(--ink-mid)" strokeWidth="1.6" />

      <path d="M14 124q40-30 78 0" stroke="var(--ink-faint)" strokeWidth="1.8" fill="none" />
      <path d="M14 124q68-96 160 0" stroke="var(--accent)" strokeWidth="2.6" fill="none" />
      <path d="M14 124q30-52 56 0" stroke="var(--ink-faint)" strokeWidth="1.8" fill="none" />
      <circle cx="94" cy="52" r="4" fill="var(--accent)" />

      {/* the control that is swept, not pinned */}
      <rect x="14" y="134" width="192" height="4" rx="2" fill="var(--line-hard)" />
      <circle cx="110" cy="136" r="7" fill="var(--accent)" />
    </svg>
  );
}

/* ── the class, section by section ────────────────────────────────────
   Distinct from TeacherView on purpose: that one is a single cohort of
   forty, this is what the panel copy promises — several sections, each with
   its own share understood and its own share quietly stuck. */
export function ClassRoster({ className }: P) {
  const sections = [
    { name: "11-A", got: 0.82 },
    { name: "11-B", got: 0.54 },
    { name: "11-C", got: 0.71 },
    { name: "11-D", got: 0.38 },
  ];
  return (
    <svg
      className={className}
      viewBox="0 0 300 170"
      role="img"
      aria-label="Four sections of the same class, each showing how much of it understood today's topic — 11-B and 11-D are behind."
    >
      <rect x="1" y="1" width="298" height="168" rx="8" fill="var(--paper)" stroke="var(--line)" />
      <rect x="20" y="18" width="86" height="7" rx="3.5" fill="var(--ink)" />
      <rect x="228" y="16" width="52" height="12" rx="6" fill="var(--accent-wash)" />
      <rect x="236" y="20" width="36" height="4" rx="2" fill="var(--accent-deep)" />
      {sections.map((sec, i) => {
        const y = 46 + i * 29;
        const w = Math.round(178 * sec.got);
        const behind = sec.got < 0.6;
        return (
          <g key={sec.name}>
            <rect x="20" y={y} width="30" height="8" rx="4" fill="var(--ink-mid)" />
            <rect x="62" y={y - 1} width="178" height="10" rx="5" fill="var(--line)" />
            <rect
              x="62"
              y={y - 1}
              width={w}
              height="10"
              rx="5"
              fill={behind ? "var(--warn)" : "var(--good)"}
            />
            <circle cx="264" cy={y + 4} r="5" fill={behind ? "var(--warn)" : "var(--good)"} />
          </g>
        );
      })}
    </svg>
  );
}

/* ── belief 1: the teacher is the centre ──────────────────────────────
   She is drawn largest and at the board; the software is two small panels
   turned toward her, feeding in. "Instruments for her, not around her" is a
   claim about who is subordinate to whom, so the drawing has to get the
   sizes and the arrow directions right or it says the opposite. */
export function TeacherAtCentre({ className }: P) {
  return (
    <svg
      className={className}
      viewBox="0 0 240 150"
      role="img"
      aria-label="The teacher at her board, drawn large and central, with two small instrument panels turned toward her and feeding into her."
    >
      {/* her board */}
      <rect x="70" y="10" width="100" height="62" rx="5" fill="var(--ink-strong)" />
      <g stroke="var(--cream)" strokeWidth="2.2" strokeLinecap="round" opacity=".8">
        <path d="M82 26h44" />
        <path d="M82 38h60" />
        <path d="M82 50h32" />
      </g>

      {/* the teacher, largest thing here */}
      <circle cx="120" cy="92" r="17" fill={SKIN} />
      <path d="M103 92a17 17 0 0 1 34 0z" fill={HAIR} />
      <circle cx="120" cy="81" r="2.6" fill="var(--accent)" />
      <circle cx="114" cy="93" r="2.1" fill={HAIR} />
      <circle cx="126" cy="93" r="2.1" fill={HAIR} />
      <path d="M114 101q6 5 12 0" stroke={LIP} strokeWidth="2" fill="none" strokeLinecap="round" />
      <circle cx="103" cy="96" r="3.2" fill={GOLD} />
      <circle cx="137" cy="96" r="3.2" fill={GOLD} />
      <path d="M92 146c0-17 12.5-30 28-30s28 13 28 30z" fill={CLOTH} />
      <path d="M106 146c0-11 6-19 14-19s14 8 14 19z" fill={CLOTH_LIGHT} />

      {/* the instruments, small and pointed at her */}
      <g>
        <rect x="8" y="88" width="52" height="40" rx="5" fill="var(--paper)" stroke="var(--line-hard)" />
        <rect x="16" y="98" width="30" height="4" rx="2" fill="var(--ink-dim)" />
        <rect x="16" y="107" width="36" height="6" rx="3" fill="var(--line)" />
        <rect x="16" y="107" width="24" height="6" rx="3" fill="var(--good)" />
        <rect x="16" y="118" width="36" height="4" rx="2" fill="var(--line)" />
        <rect x="16" y="118" width="14" height="4" rx="2" fill="var(--warn)" />
      </g>
      <g>
        <rect x="180" y="88" width="52" height="40" rx="5" fill="var(--paper)" stroke="var(--line-hard)" />
        <rect x="188" y="98" width="30" height="4" rx="2" fill="var(--ink-dim)" />
        <g fill="var(--line-hard)">
          <circle cx="191" cy="112" r="3.2" />
          <circle cx="201" cy="112" r="3.2" />
          <circle cx="221" cy="112" r="3.2" />
        </g>
        <circle cx="211" cy="112" r="3.2" fill="var(--warn)" />
        <rect x="188" y="120" width="36" height="4" rx="2" fill="var(--line)" />
      </g>

      {/* feeding in, not out */}
      <g stroke="var(--accent)" strokeWidth="1.8" fill="none" strokeLinecap="round">
        <path d="M62 104h22" />
        <path d="M78 100l5 4-5 4" />
        <path d="M178 104h-22" />
        <path d="M162 100l-5 4 5 4" />
      </g>
    </svg>
  );
}

/* ── belief 3: attention should not be a privilege ────────────────────
   The claim is a change in who gets it, so the drawing is the same thing
   twice: a few children with a tutor beside them, then all of them. */
export function AttentionForEveryone({ className }: P) {
  const ring = (cx: number, cy: number, on: boolean, key: string) => (
    <g key={key}>
      <circle cx={cx} cy={cy} r="8.5" fill={on ? "var(--accent-wash)" : "none"}
        stroke={on ? "var(--accent)" : "var(--line-hard)"} strokeWidth={on ? 1.6 : 1.2} />
      <circle cx={cx} cy={cy - 1.5} r="3" fill={on ? "var(--accent)" : "var(--line-hard)"} />
      <path d={`M${cx - 4.6} ${cy + 6}a4.6 4.6 0 0 1 9.2 0z`} fill={on ? "var(--accent)" : "var(--line-hard)"} />
    </g>
  );
  return (
    <svg
      className={className}
      viewBox="0 0 240 150"
      role="img"
      aria-label="Three children have a tutor of their own today; on the right, every child in the group does."
    >
      <rect x="4" y="16" width="94" height="118" rx="7" fill="var(--ground-deep)" />
      <rect x="16" y="28" width="42" height="5" rx="2.5" fill="var(--ink-dim)" />
      {[0, 1, 2, 3, 4, 5, 6, 7, 8].map((i) =>
        ring(26 + (i % 3) * 24, 58 + Math.floor(i / 3) * 26, i < 3, `a${i}`),
      )}

      <g stroke="var(--accent)" strokeWidth="2.2" fill="none" strokeLinecap="round">
        <path d="M106 75h22" />
        <path d="M122 69l7 6-7 6" />
      </g>

      <rect x="140" y="16" width="96" height="118" rx="7" fill="var(--accent-wash)" />
      <rect x="152" y="28" width="42" height="5" rx="2.5" fill="var(--accent-deep)" />
      {[0, 1, 2, 3, 4, 5, 6, 7, 8].map((i) =>
        ring(163 + (i % 3) * 24, 58 + Math.floor(i / 3) * 26, true, `b${i}`),
      )}
    </svg>
  );
}
