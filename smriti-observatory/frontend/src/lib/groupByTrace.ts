import type { ObservatoryEvent } from "./types";

/** Groups consecutive events sharing one trace_id into one "what happened
 * in this trace" block — this is the visualization's main content: not a
 * flat event log, but the session's story broken into the traces that
 * produced it, each showing what it read/wrote and what changed.
 *
 * Extracted out of EventTimeline.tsx (a .tsx component file, not directly
 * importable by a plain Node test) so this pure grouping logic can carry
 * its own unit test — see tests/observatoryEvent.test.mjs. */
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
