import { useMemo } from "react";
import type { ObservatoryEvent } from "../lib/types";
import { TraceGroup } from "./TraceGroup";
import styles from "./EventTimeline.module.css";

interface EventTimelineProps {
  events: ObservatoryEvent[];
  gcpProject: string;
  selectedEventId: string | null;
  onSelect: (event: ObservatoryEvent) => void;
}

/** Groups consecutive events sharing one trace_id into one "what happened
 * in this trace" block — this is the visualization's main content: not a
 * flat event log, but the session's story broken into the traces that
 * produced it, each showing what it read/wrote and what changed. */
export function groupByTrace(events: ObservatoryEvent[]): { traceId: string | null; events: ObservatoryEvent[] }[] {
  const groups: { traceId: string | null; events: ObservatoryEvent[] }[] = [];
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
