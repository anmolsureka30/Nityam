/* Small drawings for the states a screen spends most of its life in before
 * it has anything to show: nothing recorded yet, nothing known yet, or the
 * memory service out of reach.
 *
 * These exist because "No sessions yet." on its own is the single clearest
 * tell of an unfinished app — the state a new student sees FIRST is the one
 * that most often gets no design at all.
 *
 * Same language as the rest of the product: hairline strokes, the notebook's
 * own margin rule, tokens for every colour so they follow the palette. They
 * are aria-hidden throughout — each one sits directly above text that already
 * says the same thing, and announcing both is just repetition. */

type P = { className?: string };

/** No sessions recorded yet — an empty notebook page with its margin rule. */
export function SpotNoSessions({ className }: P) {
  return (
    <svg className={className} viewBox="0 0 120 84" aria-hidden="true">
      <rect x="10.5" y="6.5" width="76" height="71" rx="5"
        fill="var(--paper)" stroke="var(--line-hard)" />
      <line x1="26" y1="6.5" x2="26" y2="77.5" stroke="var(--accent-rule)" strokeWidth="1.4" />
      <g stroke="var(--line)" strokeWidth="4" strokeLinecap="round">
        <path d="M34 24h42" />
        <path d="M34 38h34" />
        <path d="M34 52h44" />
        <path d="M34 66h24" />
      </g>
      {/* the first one is waiting to be written */}
      <circle cx="94" cy="62" r="15" fill="var(--accent-wash)" stroke="var(--accent-rule)" />
      <path d="M94 55v14M87 62h14" stroke="var(--accent)" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}

/** No view formed yet — mastery rows with nothing filled in. */
export function SpotNoProfile({ className }: P) {
  return (
    <svg className={className} viewBox="0 0 120 84" aria-hidden="true">
      <circle cx="26" cy="30" r="13" fill="var(--accent-wash)" stroke="var(--accent-rule)" />
      <circle cx="26" cy="26" r="5" fill="var(--accent-tint)" />
      <path d="M17 39a9 9 0 0 1 18 0z" fill="var(--accent-tint)" />
      <g>
        <rect x="48" y="18" width="62" height="7" rx="3.5" fill="var(--line)" />
        <rect x="48" y="32" width="62" height="7" rx="3.5" fill="var(--line)" />
        <rect x="48" y="46" width="62" height="7" rx="3.5" fill="var(--line)" />
      </g>
      <g stroke="var(--line-hard)" strokeWidth="1.6" strokeDasharray="3 3">
        <path d="M14 66h92" />
      </g>
      <rect x="14" y="74" width="34" height="5" rx="2.5" fill="var(--line)" />
    </svg>
  );
}

/** The memory service could not be reached — a broken thread back to it. */
export function SpotUnreachable({ className }: P) {
  return (
    <svg className={className} viewBox="0 0 120 84" aria-hidden="true">
      <rect x="8" y="26" width="34" height="32" rx="5"
        fill="var(--paper)" stroke="var(--line-hard)" />
      <rect x="16" y="35" width="18" height="4" rx="2" fill="var(--line-hard)" />
      <rect x="16" y="44" width="12" height="4" rx="2" fill="var(--line-hard)" />
      <rect x="78" y="26" width="34" height="32" rx="5"
        fill="var(--paper)" stroke="var(--line-hard)" />
      <rect x="86" y="35" width="18" height="4" rx="2" fill="var(--line-hard)" />
      <rect x="86" y="44" width="12" height="4" rx="2" fill="var(--line-hard)" />
      <g stroke="var(--warn)" strokeWidth="2.4" strokeLinecap="round">
        <path d="M44 42h9" />
        <path d="M67 42h9" />
        <path d="M56 36l8 12" />
        <path d="M64 36l-8 12" />
      </g>
    </svg>
  );
}

/** Working — three dots, the same beat the session screens use. */
export function SpotWorking({ className }: P) {
  return (
    <svg className={className} viewBox="0 0 120 84" aria-hidden="true">
      <rect x="24.5" y="20.5" width="71" height="43" rx="6"
        fill="var(--paper)" stroke="var(--line-hard)" />
      <line x1="38" y1="20.5" x2="38" y2="63.5" stroke="var(--accent-rule)" strokeWidth="1.4" />
      <g fill="var(--accent)">
        <circle cx="55" cy="42" r="4" opacity=".35" />
        <circle cx="68" cy="42" r="4" opacity=".6" />
        <circle cx="81" cy="42" r="4" />
      </g>
    </svg>
  );
}
