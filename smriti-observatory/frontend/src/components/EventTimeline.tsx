import { useMemo } from "react";
import type { EnrichedEvent } from "../lib/types";
import { TraceGroup } from "./TraceGroup";
import styles from "./EventTimeline.module.css";

interface EventTimelineProps {
  events: EnrichedEvent[];
  gcpProject: string;
  selectedEventId: string | null;
  onSelect: (event: EnrichedEvent) => void;
}

/** Groups consecutive events sharing one trace_id into one "what happened
 * in this trace" block — this is the visualization's main content: not a
 * flat event log, but the session's story broken into the traces that
 * produced it, each showing what it read/wrote and what changed. */
function groupByTrace(events: EnrichedEvent[]): { traceId: string | null; events: EnrichedEvent[] }[] {
  const groups: { traceId: string | null; events: EnrichedEvent[] }[] = [];
  for (const enriched of events) {
    const traceId = enriched.event.trace_id;
    const last = groups[groups.length - 1];
    if (last && last.traceId === traceId) {
      last.events.push(enriched);
    } else {
      groups.push({ traceId, events: [enriched] });
    }
  }
  return groups;
}

export function EventTimeline({ events, gcpProject, selectedEventId, onSelect }: EventTimelineProps) {
  const groups = useMemo(() => groupByTrace(events), [events]);

  if (groups.length === 0) {
    return <p className={styles.empty}>Nothing has happened in this session yet.</p>;
  }

  return (
    <div className={styles.container}>
      {groups.map((group, i) => (
        <TraceGroup
          key={group.traceId ?? `untraced-${i}`}
          traceId={group.traceId}
          events={group.events}
          gcpProject={gcpProject}
          selectedEventId={selectedEventId}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}
