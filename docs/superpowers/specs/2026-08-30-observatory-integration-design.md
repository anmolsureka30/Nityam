# Live Session Observatory Integration — Design

**Status:** Approved by user in chat 2026-08-30. Proceeding to implementation plan.

## Problem

The deployed Nityam app has no visibility into what actually happens inside a
tutoring session: which specialist agent VoiceAgent delegated to, what each
specialist did internally, what dynamic personal memory (DPM) and teaching
memory were loaded at session start, and what got written back after the
session closed. A real production incident (repeated/garbled speech, traced
separately to a mid-session Cloud Run instance recycle plus a since-fixed
ArtifactAgent crash) could only be diagnosed by hand-querying Cloud Logging,
because nothing structured captures a session's actual execution trace.

`smriti-observatory/` already exists as a working FastAPI+React app, but it
only shows **memory tier** read/write events (DPM, teaching memory, grounding
chunks, turn buffer, session log, artifact events) — sourced from
`backend/app/memory/instrumentation.py`'s `MemoryEvent` mechanism. It has no
visibility into **tool calls**: neither VoiceAgent's own delegation to
`ask_board`/`ask_quiz`/`ask_artifact`/`ask_textbook`, nor what each specialist
does internally (`search_grounding`, `get_dpm`, `strike_block`, etc.). Both of
those are already logged today, but only as plain-text Python `logging` calls
(`main.py`'s `trace()` and `specialist_runner.py`'s `_log_tool_activity()`),
invisible to the Observatory's event pipeline.

Additionally: `MemoryEvent.trace_id`/`span_id` are derived from
`opentelemetry.trace.get_current_span()`, but no `TracerProvider` is
configured anywhere in `backend/`. Every `MemoryEvent` published in
production today therefore has `trace_id=None`, and the frontend's
trace-grouping (`EventTimeline.tsx`'s `groupByTrace`) has never actually
grouped anything by real trace. This is a live bug, and fixing it is required
for tool calls and the memory operations they trigger to visibly correlate —
so it is in scope here, not a separate cleanup.

## Goal

Typing `/observatory` on the deployed app shows, per session:
1. The specialist tool-call sequence — VoiceAgent's delegations
   (`ask_board`/`ask_quiz`/`ask_artifact`/`ask_textbook`) and each
   specialist's own internal tool calls, in order, with timing and outcome,
   correlated via trace ID with the memory operations they caused.
2. What DPM and teaching memory were loaded at session start.
3. After the session ends, what was written back to memory (DPM,
   teaching memory, session log) — this already works today via the
   existing memory-event pipeline.
4. Both a live view (updating as a session runs) and a recap view
   (after it closes) — the session list/live-closed distinction already
   exists in the Observatory frontend (`SessionDrawer.tsx`) and REST API
   (`GET /api/sessions`); it needs real tool-call data flowing through it.

Access: open at `/observatory`, same as the main app today — no additional
auth gate.

## Non-goals

- Resurrecting the static ADK agent/tool topology diagram
  (`AgentToolGraph.tsx`, backed by `GET /api/agent-graph`, which proxies an
  ADK dev-server endpoint that only the unrelated `sub_modules_examples/tutor`
  sub-project serves). It stays as dead code, unwired — the new trace view
  supersedes what it was trying to show, and `backend/` will never serve that
  endpoint.
- Real OpenTelemetry export to Cloud Trace or any collector. The
  `TracerProvider` added here exists purely to generate real trace/span IDs
  in-process; no exporter is configured. (`TraceGroup.tsx`'s existing "open in
  Cloud Trace" link will continue to produce a link that 404s — it did
  before this change too, since no traces were ever exported. Not addressed
  here.)
- Fixing the Cloud Run mid-session instance recycle / missing WebSocket
  reconnect logic (tracked separately; out of scope for this feature).
- A separate Cloud Run service for the Observatory. It is mounted into the
  same `backend/` process (see Architecture).

## Architecture

One Cloud Run service, one FastAPI process, one deploy:

- `backend/app/main.py`'s existing `app = FastAPI(...)` gains:
  - `app.include_router(observatory_router, prefix="/observatory/api")` —
    `smriti-observatory/backend/observatory`'s REST router
    (`routes_rest.py`), reconfigured to talk to `backend/`'s own in-process
    memory functions directly (see below) instead of proxying over HTTP to a
    `TUTOR_BASE_URL`.
  - `app.include_router(observatory_ws_router, prefix="/observatory")` —
    `routes_ws.py`'s WebSocket router, unchanged.
  - A static mount serving `smriti-observatory/frontend`'s build at
    `/observatory`, using the same catch-all-SPA pattern `main.py` already
    uses for the main frontend at `frontend/dist` (`main.py:986-1001`).
  - The Observatory's ingest loop (`observatory.ingest.run_ingest_loop`)
    started as a background `asyncio.Task` in `main.py`'s existing lifespan,
    alongside whatever startup work already happens there — same Redis
    instance the main app already uses (`app.config.REDIS_HOST/PORT`), no
    new Redis connection config needed.

- `routes_rest.py`'s `session_state`/`session_events`/`close_session_proxy`
  currently proxy over HTTP to `TUTOR_BASE_URL` because the standalone
  Observatory process has no direct access to `backend/`'s Python objects.
  Once mounted in the same process, these become direct in-process calls to
  `app.memory_routes`'s existing handler functions — removing the HTTP
  round-trip and the `httpx` dependency for these three routes. `list_sessions`
  and `health` keep talking to Redis/Firestore directly, as they do today
  (unaffected by the mount).

- `backend/Dockerfile` gains a second Node build stage for
  `smriti-observatory/frontend` (mirroring the existing `frontend` stage),
  and a `COPY smriti-observatory/backend/observatory/
  /app/backend/observatory/` so the package is importable from
  `backend/app/main.py`.

## Tracing

A minimal `opentelemetry.sdk.trace.TracerProvider` (no exporter) is
constructed once at `backend/app/main.py` startup and installed via
`opentelemetry.trace.set_tracer_provider(...)`. This alone makes
`instrumentation.py`'s existing `_current_trace_ids()` return real,
non-`None` IDs instead of always failing the `ctx.is_valid` check.

A span is opened around each unit of work whose internal memory operations
should be grouped together:
- `specialist_runner.delegate()`, around the call that runs the specialist's
  turn — so every `MemoryEvent` a specialist emits while answering (DPM
  reads, teaching-memory writes, grounding lookups) shares one trace with
  that delegation's tool-call event.
- VoiceAgent's own top-level turn handling in `main.py`, so its own direct
  memory operations (turn buffer appends, session log writes) correlate too.

No manual trace-ID threading is needed: `_build_event()` already reads
whatever span is active via `trace.get_current_span()`, so opening the span
at the right call site is sufficient.

## Tool-call event capture

A new `ToolCallEvent` model, parallel to (not replacing) `MemoryEvent`:

- Fields: `event_id`, `ts`, `session_id`, `student_id`, `trace_id`, `span_id`,
  `actor` (`voice_agent` / `board_agent` / `artifact_agent` / `quiz_agent` /
  `textbook_agent`), `tool_name`, `phase` (`started` / `done` / `error` /
  `busy`), `args_summary`, `result_summary`, `duration_ms` (best-effort —
  populated when a call's start and end can be correlated, `None` otherwise;
  the implementation plan pins down exactly how correlation works).
- Published from two existing call sites, right beside the `log.info()`
  calls already there — not new instrumentation, just an added publish:
  - `main.py`'s `trace()`, on its existing `→ TOOL CALL` / `← TOOL DONE`
    branches (VoiceAgent's dispatch to `ask_*`).
  - `specialist_runner.py`'s `_log_tool_activity()`, on its existing
    function-call / function-response branches (each specialist's internal
    tool calls). This function currently doesn't receive `session_id`/
    `student_id`/trace context — its signature grows to take them, threaded
    from its one caller, `_run_turn_uncapped`, which already has both in
    scope.
- Published as JSON with a top-level `"kind": "tool_call"` field, onto the
  same Redis channel (`smriti:events:live`) and list (`smriti:events:recent`)
  `MemoryEvent` already uses. Existing `MemoryEvent` JSON is unchanged (no
  `kind` field added to it) — `ingest_one_message` distinguishes by checking
  for the `kind` key's presence, so nothing already in the capped 2000-entry
  Redis list needs migrating.

## Observatory backend changes

- `observatory/events.py`: add the `ToolCallEvent` model, plus an
  `EnrichedToolCallEvent` wrapper (`{kind: "tool_call", event: ToolCallEvent}`)
  parallel to the existing `EnrichedEvent` (which gains `kind: "memory"` for
  symmetry).
- `observatory/ingest.py`: `ingest_one_message` peeks at the raw JSON's
  `kind` field; a `tool_call` message is parsed as `ToolCallEvent`, wrapped,
  and broadcast with no diffing (diffing is a memory-event-only concept).
  Existing `MemoryEvent` handling (diffing against the snapshot cache) is
  unchanged.
- `observatory/broadcaster.py` and `routes_ws.py`: unchanged — both already
  move opaque enriched objects through queues and `.model_dump(mode="json")`
  them, so they work with either wrapper without modification.
- `observatory/routes_rest.py`: `session_state`/`session_events`/
  `close_session_proxy` switch from `httpx` calls against `TUTOR_BASE_URL` to
  direct in-process calls (see Architecture). `list_sessions` and `health`
  are unaffected.

## Observatory frontend changes

- `lib/types.ts`: add `ToolCallEvent` and a discriminated
  `ObservatoryEvent = ({kind: "memory"} & EnrichedEvent) | ({kind: "tool_call"} & EnrichedToolCallEvent)`
  type, matching the backend wire shape.
- `EventTimeline.tsx`'s `groupByTrace` groups on the same `trace_id` field
  regardless of event kind — one code path, both kinds interleave correctly
  once trace IDs are real (see Tracing above).
- `TraceGroup.tsx`: its row rendering is currently memory-event-specific
  (tier dot, read/write badge, record-type label). It gains a second row
  renderer for `tool_call` events — an icon, `actor` → `tool_name`, a
  status pill for `phase`, and `duration_ms` when present — selected per-row
  by the event's `kind`, sorted into the group by timestamp alongside the
  memory rows already there.
- `AgentToolGraph.tsx` and its `GET /api/agent-graph` call: left in place,
  unwired from any real data source (see Non-goals) — not deleted, since
  removing working (if currently pointless) code is out of scope for this
  feature.
- `SessionDrawer.tsx`, `StateOverview.tsx`, the DPM/teaching-memory views
  under `memory-views/`: unchanged — they already render exactly what's
  needed for "what was loaded at start" / "what changed after," and already
  work correctly once real data flows to them.

## Testing / verification

- Unit tests for `ingest_one_message` handling a `tool_call`-kind message
  (mirroring the existing `MemoryEvent` test in
  `smriti-observatory/backend/tests/test_ingest.py`).
- Unit test confirming a span opened around a `delegate()` call gives every
  `MemoryEvent` emitted inside it the same non-`None` `trace_id`.
- Manual verification against the deployed app: start a real tutoring
  session, trigger at least one `ask_board` and one `ask_artifact` call,
  confirm `/observatory` shows both the delegation and the specialist's
  internal tool calls grouped under one trace, in the live view while the
  session is open and in the recap view after it closes.

## Deployment

Ships through the existing CI/CD pipeline (`cloudbuild.yaml`, already
verified working) — no new Cloud Run service, no new secrets, no new
networking. `backend/Dockerfile`'s two build stages plus the new
`observatory` package copy are the only deployment-shaped change.
