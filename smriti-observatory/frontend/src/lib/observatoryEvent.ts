import type { MemoryEvent, ObservatoryEvent, ToolCallEvent } from "./types";

/** Maps one raw item from the REST backlog (`GET
 * /api/sessions/{id}/events`, which reads smriti:events:recent's raw JSON
 * directly — see backend/app/memory_routes.py's `_read_recent_events`) into
 * the discriminated `ObservatoryEvent` union the rest of the UI expects.
 *
 * smriti:events:recent holds both MemoryEvent and ToolCallEvent JSON on one
 * list. A MemoryEvent's own wire JSON never carries a "kind" field (see
 * app/memory/instrumentation.py); a ToolCallEvent's always does — exactly
 * how ingest.py's own live-path dispatch tells the two apart too.
 *
 * Extracted out of SessionView.tsx's `.map()` callback (a .tsx component
 * file, not directly importable by a plain Node test) so this exact
 * mapping — the logic a real production bug lived in with zero coverage,
 * see "Fix session_events_endpoint dropping tool-call history from the REST
 * backlog" — can carry its own unit test. See tests/observatoryEvent.test.mjs.
 */
export function mapBacklogEvent(event: MemoryEvent | ToolCallEvent): ObservatoryEvent {
  return "kind" in event && event.kind === "tool_call"
    ? { kind: "tool_call", event }
    : { kind: "memory", event: event as MemoryEvent, diff: [] };
}
