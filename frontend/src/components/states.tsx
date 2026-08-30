import type { ReactNode } from "react";
import { SpotNoProfile, SpotNoSessions, SpotUnreachable, SpotWorking } from "./Spot";
import s from "./states.module.css";

/* One treatment for "there is nothing here yet", used on every screen that
 * can be in that state.
 *
 * Each screen had written its own — a bare <p> of muted text, differently
 * sized and differently spaced on each one — so the emptiest screens, which
 * are exactly what a new student sees first, were the least designed. The
 * copy was always good; it just had nothing around it.
 *
 * `kind` picks the drawing rather than the caller passing one, so a screen
 * cannot end up with a picture that contradicts its own sentence. */

const ART = {
  sessions: SpotNoSessions,
  profile: SpotNoProfile,
  unreachable: SpotUnreachable,
  working: SpotWorking,
} as const;

export function EmptyState({
  kind, title, children, action, compact,
}: {
  kind: keyof typeof ART;
  /** One short line. The detail goes in `children`. */
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  /** For a panel sitting beside a populated one — the dashboard's pair. At
   *  full size an empty panel grows taller than its filled neighbour, which
   *  makes the emptiness look like the more important half. */
  compact?: boolean;
}) {
  const Art = ART[kind];
  return (
    <div className={compact ? `${s.empty} ${s.emptyCompact}` : s.empty}>
      <Art className={s.art} />
      <p className={s.title}>{title}</p>
      {children && <p className={s.body}>{children}</p>}
      {action && <div className={s.action}>{action}</div>}
    </div>
  );
}

/** Waiting on the network. Same beat as the session screens' dots, so the
 *  whole product pulses at one rhythm rather than three. */
export function LoadingState({ label }: { label: string }) {
  return (
    <div className={s.loading} role="status" aria-live="polite">
      <span className={s.dots} aria-hidden="true"><i /><i /><i /></span>
      <span className={s.loadingLabel}>{label}</span>
    </div>
  );
}
