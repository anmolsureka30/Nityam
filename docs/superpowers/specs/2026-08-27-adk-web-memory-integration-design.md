# SMRITI Memory Layer Integration Into ADK Web

## Goal

Move memory-layer visualization (working/episodic/long-term memory, evidence
lineage, agent/tool graph) out of the standalone React "Observatory" app and
into ADK web itself, so running ADK web against the tutor app is enough to
see memory state and how each trace changed it — no second server, no
second app to run. This travels with the agent when it's deployed for real,
since it lives in the same FastAPI process ADK's dev-ui already runs on.

## Architecture

**Backend** — extend the tutor app's own FastAPI server
(`app/fast_api_app.py`), which already hosts both ADK's dev-ui routes and
our `/memory/sessions/{id}/close` route on one process/port. Add two
read-only endpoints to `app/app_utils/memory_routes.py`:

- `GET /memory/sessions/{session_id}/state?student_id=...` — current
  Working/Episodic/Long-Term snapshot. Ports the logic already written in
  `smriti-observatory/backend/observatory/routes_rest.py::session_state`.
- `GET /memory/sessions/{session_id}/events?trace_id=...` — the event
  backlog for a session, optionally filtered to one trace_id. Ports
  `routes_rest.py::session_events`, adding the trace_id filter (the
  standalone app never needed it — it grouped client-side).

Both read from the same Redis (`smriti:events:recent`) and Firestore the
existing `app/memory/store.py` / `app/memory/short_term.py` already use —
no new datastore, no new dependency.

**Frontend** — a maintained fork of `adk-web`
(`/private/tmp/.../scratchpad/adk-web`, to be moved into this repo at
`smriti-observatory/adk-web/`), with two integration points, both reusing
*existing* adk-web UI surface rather than inventing new chrome:

1. **New "Memory" tab** in `side-panel.component.html`, added the same way
   Artifacts/Tests/Eval already are — conditional on a feature flag,
   sibling to the existing "State" tab (which shows ADK's own generic
   `session.state`, left untouched). Shows:
   - The full current State view — Working Memory (turn buffer), Episodic
     Memory (session log), Long-Term Memory (Learner Profile + Teaching
     State) — ported from the React `StateOverview` /
     `WorkingMemoryView` / `EpisodicMemoryView` / `LearnerProfileView` /
     `TeachingStateView` / `EvidenceChips` components already built.
   - The real agent/tool graph, reusing adk-web's own `@viz-js/viz`
     DOT renderer (`GraphService`, already used by
     `agent-structure-graph-dialog`) against the *same*
     `/dev/apps/{app}/graph` DOT source — not a hand-rolled layout like
     the React version's `AgentToolGraph.tsx`, the real thing ADK already
     renders elsewhere in this app.

2. **A "Memory operations" section inside the existing `app-trace-tab`**
   (already shown in the side panel's "Info" tab whenever a trace span is
   selected, via `traceData: Span[]` — confirmed each `Span` carries a
   real `trace_id` field). Reads `traceData[0]?.trace_id`, fetches
   matching memory events from the new `/events?trace_id=...` endpoint,
   and renders them the same way `TraceGroup.tsx`'s operation rows do —
   tier, read/write, record type, one-line summary, diff. This is the
   literal "linking with each trace, each tool call" ask: click a trace
   span you're already looking at, see what it did to memory right there.

**Live updates**: polling/refetch, not a new WebSocket client. The Memory
tab refetches state on tab activation and on session/event-list change
(adk-web's own signals already fire on every new turn); the trace-tab's
memory section refetches whenever `traceData` changes (new span
selected). No broadcaster port, no WS client in Angular.

**Cutover**: once this works end-to-end, delete
`smriti-observatory/frontend` and `smriti-observatory/backend`.

## Correlation key

One ADK invocation is one OpenTelemetry trace (`invoke_agent` root span);
every `execute_tool` sub-span shares that trace_id. Our
`MemoryEvent.trace_id` is captured from `trace.get_current_span()` at the
moment a memory operation fires — the same trace_id. So
`Span.trace_id === MemoryEvent.trace_id` is an exact match, not a
heuristic (verified against adk-web's own `Trace.ts` span model, which
carries `trace_id` as a required, typed field).

## File-level plan

**Backend** (`sub_modules_examples/tutor/`):
- `app/app_utils/memory_routes.py` — add `session_state_endpoint` and
  `session_events_endpoint` (GET), reusing `app/memory/store.py` /
  `app/memory/short_term.py` reads. Add a small diff helper ported from
  `smriti-observatory/backend/observatory/diff.py` if the trace-tab
  section needs before/after diffs (it does, matching `TraceGroup.tsx`).
- Tests alongside existing `tests/unit/` for the new endpoints.

**Frontend** (new `smriti-observatory/adk-web/` fork):
- `src/app/core/services/memory.service.ts` (+ interface) — `getState`,
  `getEvents`, following the existing `AGENT_SERVICE` /
  `URLUtil.getApiServerBaseUrl()` pattern exactly.
- `src/app/components/memory-tab/` — ported State views + graph, new
  Angular components mirroring the deleted React ones structurally
  (same component boundaries: working/episodic/long-term/evidence-chips),
  translated to Angular signals + Material.
- `src/app/components/trace-tab/` — extend with a memory-operations
  section (new child component + a few lines in the existing template).
- `src/app/components/side-panel/side-panel.component.html` — one new
  conditional `<mat-tab>`, following the Artifacts/Tests/Eval pattern
  exactly (own feature-flag observable).

## Testing

- Backend: pytest for the two new endpoints (happy path, missing
  session/student, trace_id filter), same style as
  `test_routes_rest.py`.
- Frontend: component-level specs for the new Angular components
  (adk-web's existing `.spec.ts` convention), plus a real Playwright
  pass driving the actual running app — select a session, open a trace
  span, confirm the memory section shows real data, open the Memory tab,
  confirm Working/Episodic/Long-Term all populate from a real demo
  session (reusing the `_demo_rich_session.py` script already built for
  this).
