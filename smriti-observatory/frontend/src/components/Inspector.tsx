import type { ObservatoryEvent } from "../lib/types";
import { RECORD_TYPE_LABEL, TIER_LABEL, TOOL_ACTOR_LABEL, TOOL_CALL_PHASE_LABEL, describeEvent, describeToolCall } from "../lib/labels";
import { cloudTraceUrl } from "../lib/traceLinks";
import styles from "./Inspector.module.css";

export function Inspector({ selected, gcpProject }: { selected: ObservatoryEvent | null; gcpProject: string }) {
  if (!selected) {
    return <p className={styles.empty}>Click an operation in the timeline to inspect it here.</p>;
  }

  if (selected.kind === "tool_call") {
    const { event } = selected;
    return (
      <div className={styles.container}>
        <p className={styles.summary}>{describeToolCall(event)}</p>

        <dl className={styles.factList}>
          <div className={styles.fact}>
            <dt>Actor</dt>
            <dd>{TOOL_ACTOR_LABEL[event.actor] ?? event.actor}</dd>
          </div>
          <div className={styles.fact}>
            <dt>Tool</dt>
            <dd><code>{event.tool_name}</code></dd>
          </div>
          <div className={styles.fact}>
            <dt>Phase</dt>
            <dd>{TOOL_CALL_PHASE_LABEL[event.phase]}</dd>
          </div>
          <div className={styles.fact}>
            <dt>Time</dt>
            <dd>{new Date(event.ts).toLocaleString()}</dd>
          </div>
          {event.duration_ms != null && (
            <div className={styles.fact}>
              <dt>Duration</dt>
              <dd>{(event.duration_ms / 1000).toFixed(2)}s</dd>
            </div>
          )}
          {event.session_id && (
            <div className={styles.fact}>
              <dt>Session</dt>
              <dd className={styles.mono}>{event.session_id}</dd>
            </div>
          )}
          {event.student_id && (
            <div className={styles.fact}>
              <dt>Student</dt>
              <dd className={styles.mono}>{event.student_id}</dd>
            </div>
          )}
          {event.trace_id && (
            <div className={styles.fact}>
              <dt>Trace</dt>
              <dd>
                <a href={cloudTraceUrl(event.trace_id, gcpProject)} target="_blank" rel="noreferrer">
                  {event.trace_id.slice(0, 16)}… ↗
                </a>
              </dd>
            </div>
          )}
        </dl>

        {event.args_summary && (
          <div className={styles.section}>
            <h4 className={styles.heading}>Args</h4>
            <pre className={styles.payload}>{event.args_summary}</pre>
          </div>
        )}

        {event.result_summary && (
          <div className={styles.section}>
            <h4 className={styles.heading}>Result</h4>
            <pre className={styles.payload}>{event.result_summary}</pre>
          </div>
        )}
      </div>
    );
  }

  const { event, diff } = selected;
  return (
    <div className={styles.container}>
      <p className={styles.summary}>{describeEvent(event)}</p>

      <dl className={styles.factList}>
        <div className={styles.fact}>
          <dt>Memory kind</dt>
          <dd>{TIER_LABEL[event.tier]} · {RECORD_TYPE_LABEL[event.record_type]}</dd>
        </div>
        <div className={styles.fact}>
          <dt>Operation</dt>
          <dd>{event.operation === "write" ? "Write" : "Read"} via <code>{event.source_fn}</code></dd>
        </div>
        <div className={styles.fact}>
          <dt>Time</dt>
          <dd>{new Date(event.ts).toLocaleString()}</dd>
        </div>
        {event.session_id && (
          <div className={styles.fact}>
            <dt>Session</dt>
            <dd className={styles.mono}>{event.session_id}</dd>
          </div>
        )}
        {event.student_id && (
          <div className={styles.fact}>
            <dt>Student</dt>
            <dd className={styles.mono}>{event.student_id}</dd>
          </div>
        )}
        {event.trace_id && (
          <div className={styles.fact}>
            <dt>Trace</dt>
            <dd>
              <a href={cloudTraceUrl(event.trace_id, gcpProject)} target="_blank" rel="noreferrer">
                {event.trace_id.slice(0, 16)}… ↗
              </a>
            </dd>
          </div>
        )}
      </dl>

      {diff.length > 0 && (
        <div className={styles.section}>
          <h4 className={styles.heading}>What changed</h4>
          <ul className={styles.diffList}>
            {diff.map((c, i) => (
              <li key={i} className={styles.diffRow}>{c.label}</li>
            ))}
          </ul>
        </div>
      )}

      <div className={styles.section}>
        <h4 className={styles.heading}>Raw payload</h4>
        <pre className={styles.payload}>{JSON.stringify(event.payload, null, 2)}</pre>
      </div>
    </div>
  );
}
