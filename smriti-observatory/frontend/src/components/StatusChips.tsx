import type { Tier } from "../lib/types";
import { TIER_LABEL } from "../lib/labels";
import styles from "./StatusChips.module.css";

const TIER_ORDER: Tier[] = ["workflow", "episodic", "long_term"];
const TIER_CLASS: Record<Tier, string> = {
  workflow: styles.workflow,
  episodic: styles.episodic,
  long_term: styles.longTerm,
};

interface StatusChipsProps {
  counts: Record<Tier, number>;
  pulsing: Record<Tier, boolean>;
  activeTier: Tier | null;
  onSelectTier: (tier: Tier | null) => void;
}

/** A glanceable "is anything happening" strip — click a chip to filter the
 * timeline to that tier. Deliberately not a JSON dump: the actual content
 * of each tier lives in the State tab, this is just presence + activity. */
export function StatusChips({ counts, pulsing, activeTier, onSelectTier }: StatusChipsProps) {
  return (
    <div className={styles.row} role="group" aria-label="Memory tiers">
      {TIER_ORDER.map((tier) => (
        <button
          key={tier}
          className={`${styles.chip} ${TIER_CLASS[tier]} ${activeTier === tier ? styles.active : ""}`}
          onClick={() => onSelectTier(activeTier === tier ? null : tier)}
        >
          <span className={pulsing[tier] ? styles.dotPulsing : styles.dot} />
          {TIER_LABEL[tier]}
          <span className={styles.count}>{counts[tier]}</span>
        </button>
      ))}
    </div>
  );
}
