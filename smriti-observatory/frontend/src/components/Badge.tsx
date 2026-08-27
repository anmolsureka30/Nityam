import styles from "./Badge.module.css";

type BadgeTone = "neutral" | "weak" | "progress" | "strong" | "done" | "danger";

const MASTERY_TONE: Record<string, BadgeTone> = {
  unknown: "neutral",
  misconceived: "danger",
  partial: "weak",
  known: "progress",
  durable: "strong",
};

const STRENGTH_TONE: Record<string, BadgeTone> = { weak: "weak", strong: "strong" };

const COVERAGE_TONE: Record<string, BadgeTone> = { in_progress: "progress", covered: "done" };

const DOUBT_TONE: Record<string, BadgeTone> = { active: "danger", remediating: "progress", resolved: "done" };

export function Badge({ tone, children }: { tone: BadgeTone; children: React.ReactNode }) {
  return <span className={`${styles.badge} ${styles[tone]}`}>{children}</span>;
}

export function MasteryBadge({ value }: { value: string }) {
  return <Badge tone={MASTERY_TONE[value] ?? "neutral"}>{value}</Badge>;
}

export function StrengthBadge({ value }: { value: string }) {
  return <Badge tone={STRENGTH_TONE[value] ?? "neutral"}>{value}</Badge>;
}

export function CoverageBadge({ value }: { value: string }) {
  return <Badge tone={COVERAGE_TONE[value] ?? "neutral"}>{value.replace("_", " ")}</Badge>;
}

export function DoubtStatusBadge({ value }: { value: string }) {
  return <Badge tone={DOUBT_TONE[value] ?? "neutral"}>{value}</Badge>;
}

export function Transition({ from, to, renderBadge }: { from: string | null; to: string; renderBadge: (v: string) => React.ReactNode }) {
  return (
    <span className={styles.transition}>
      {from ? renderBadge(from) : <span className={styles.none}>none</span>}
      <span className={styles.arrow}>→</span>
      {renderBadge(to)}
    </span>
  );
}
