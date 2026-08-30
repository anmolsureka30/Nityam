import type { ObservatoryEvent, Tier } from "../lib/types";
import { RECORD_TYPE_LABEL, TIER_LABEL, TOOL_CALL_PHASE_LABEL, describeEvent, describeToolCall } from "../lib/labels";
import { cloudTraceUrl } from "../lib/traceLinks";
import { Transition, MasteryBadge, StrengthBadge, CoverageBadge, DoubtStatusBadge } from "./Badge";
import styles from "./TraceGroup.module.css";

const TIER_DOT: Record<Tier, string> = {
  workflow: styles.dotWorkflow,
  episodic: styles.dotEpisodic,
  long_term: styles.dotLongTerm,
};

function renderBadgeFor(path: string, value: string) {
  if (path.endsWith(".mastery")) return <MasteryBadge value={value} />;
  if (path.endsWith(".strength")) return <StrengthBadge value={value} />;
  if (path.includes("covered.")) return <CoverageBadge value={value} />;
  if (path.startsWith("open_doubts")) return <DoubtStatusBadge value={value} />;
  return <span>{value}</span>;
}

function shortTraceId(traceId: string): string {
  return `${traceId.slice(0, 8)}…${traceId.slice(-4)}`;
}

interface TraceGroupProps {
  traceId: string | null;
  events: ObservatoryEvent[];
  gcpProject: string;
  selectedEventId: string | null;
  onSelect: (event: ObservatoryEvent) => void;
}

export function TraceGroup({ traceId, events, gcpProject, selectedEventId, onSelect }: TraceGroupProps) {
  const first = events[0].event;
  const last = events[events.length - 1].event;
  const timeRange =
    first.ts === last.ts
      ? new Date(first.ts).toLocaleTimeString()
      : `${new Date(first.ts).toLocaleTimeString()} – ${new Date(last.ts).toLocaleTimeString()}`;

  return (
    <div className={styles.group}>
      <div className={styles.groupHeader}>
        {traceId ? (
          <a
            className={styles.traceLink}
            href={cloudTraceUrl(traceId, gcpProject)}
            target="_blank"
            rel="noreferrer"
            title="Open this trace in Cloud Trace"
          >
            trace {shortTraceId(traceId)}
          </a>
        ) : (
          <span className={styles.untraced}>untraced operation</span>
        )}
        <span className={styles.timeRange}>{timeRange}</span>
        <span className={styles.opCount}>{events.length} operation{events.length === 1 ? "" : "s"}</span>
      </div>
      <ol className={styles.rows}>
        {events.map((enriched) => {
          if (enriched.kind === "tool_call") {
            const { event } = enriched;
            const isSelected = event.event_id === selectedEventId;
            return (
              <li key={event.event_id}>
                <button
                  className={isSelected ? styles.rowSelected : styles.row}
                  onClick={() => onSelect(enriched)}
                >
                  <span className={styles.toolIcon}>🔧</span>
                  <span className={styles.toolPhase} data-phase={event.phase}>
                    {TOOL_CALL_PHASE_LABEL[event.phase]}
                  </span>
                  <span className={styles.summary}>{describeToolCall(event)}</span>
                </button>
              </li>
            );
          }

          const { event, diff } = enriched;
          const isSelected = event.event_id === selectedEventId;
          return (
            <li key={event.event_id}>
              <button
                className={isSelected ? styles.rowSelected : styles.row}
                onClick={() => onSelect(enriched)}
              >
                <span className={`${styles.dot} ${TIER_DOT[event.tier]}`} />
                <span className={styles.tierLabel}>{TIER_LABEL[event.tier]}</span>
                <span className={event.operation === "write" ? styles.opWrite : styles.opRead}>
                  {event.operation}
                </span>
                <span className={styles.recordType}>{RECORD_TYPE_LABEL[event.record_type]}</span>
                <span className={styles.summary}>{describeEvent(event)}</span>
              </button>
              {diff.length > 0 && (
                <ul className={styles.diffList}>
                  {diff.map((change, i) => (
                    <li key={i} className={styles.diffRow}>
                      <span className={styles.diffPath}>{change.path}</span>
                      {change.kind === "changed" && typeof change.old === "string" && typeof change.new === "string" ? (
                        <Transition from={change.old} to={change.new} renderBadge={(v) => renderBadgeFor(change.path, v)} />
                      ) : (
                        <span className={styles.diffLabel}>{change.label}</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
