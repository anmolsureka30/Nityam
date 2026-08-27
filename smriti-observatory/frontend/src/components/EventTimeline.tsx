import { useState } from "react";
import type { EnrichedEvent } from "../lib/types";
import { cloudTraceUrl } from "../lib/traceLinks";
import styles from "./EventTimeline.module.css";

type ViewMode = "timeline" | "trace";

interface EventTimelineProps {
  events: EnrichedEvent[];
  gcpProject: string;
}

export function EventTimeline({ events, gcpProject }: EventTimelineProps) {
  const [mode, setMode] = useState<ViewMode>("timeline");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  return (
    <div className={styles.container}>
      <div className={styles.toggleGroup} role="group" aria-label="View mode">
        <button
          className={mode === "timeline" ? styles.toggleActive : styles.toggle}
          onClick={() => setMode("timeline")}
        >
          Timeline
        </button>
        <button className={mode === "trace" ? styles.toggleActive : styles.toggle} onClick={() => setMode("trace")}>
          Trace
        </button>
      </div>
      <ul className={styles.list} data-testid="event-list">
        {events.map((enriched) => {
          const { event } = enriched;
          const isExpanded = expandedId === event.event_id;
          return (
            <li key={event.event_id} className={styles.row}>
              <button className={styles.rowHeader} onClick={() => setExpandedId(isExpanded ? null : event.event_id)}>
                <span className={styles.recordType}>{event.record_type}</span>
                <span className={styles.op}>{event.operation}</span>
                <span className={styles.fn}>{event.source_fn}</span>
                <span className={styles.ts}>{new Date(event.ts).toLocaleTimeString()}</span>
              </button>
              {isExpanded && (
                <div className={styles.detail}>
                  {mode === "trace" && event.trace_id ? (
                    <a href={cloudTraceUrl(event.trace_id, gcpProject)} target="_blank" rel="noreferrer">
                      Open in Cloud Trace
                    </a>
                  ) : (
                    <pre className={styles.payload}>{JSON.stringify(event.payload, null, 2)}</pre>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
