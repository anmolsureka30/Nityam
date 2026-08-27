import type { EnrichedEvent, Tier } from "../lib/types";
import styles from "./TierPanel.module.css";

const TIER_CLASS: Record<Tier, string> = {
  workflow: styles.workflow,
  episodic: styles.episodic,
  long_term: styles.longTerm,
};

interface TierPanelProps {
  tier: Tier;
  title: string;
  events: EnrichedEvent[];
  content: React.ReactNode;
}

export function TierPanel({ tier, title, events, content }: TierPanelProps) {
  const isPulsing = events.length > 0 && Date.now() - new Date(events[events.length - 1].event.ts).getTime() < 1500;
  return (
    <section className={`${styles.panel} ${TIER_CLASS[tier]}`} data-testid={`tier-panel-${tier}`}>
      <header className={styles.header}>
        <span className={isPulsing ? styles.dotPulsing : styles.dot} />
        <h3 className={styles.title}>{title}</h3>
        <span className={styles.count}>{events.length}</span>
      </header>
      <div className={styles.body}>{content}</div>
    </section>
  );
}
