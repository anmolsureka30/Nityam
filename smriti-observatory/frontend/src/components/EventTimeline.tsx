import { useMemo } from "react";
import { groupByTrace } from "../lib/groupByTrace";
import type { ObservatoryEvent } from "../lib/types";
import { TraceGroup } from "./TraceGroup";
import styles from "./EventTimeline.module.css";

interface EventTimelineProps {
  events: ObservatoryEvent[];
  gcpProject: string;
  selectedEventId: string | null;
  onSelect: (event: ObservatoryEvent) => void;
}

// Re-exported for anyone still importing it from here — the implementation
// itself now lives in ../lib/groupByTrace.ts (a plain .ts file, not a .tsx
// component) so it can carry its own unit test; see
// tests/observatoryEvent.test.mjs.
export { groupByTrace };

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
