# SMRITI Observatory — Design Spec

**Status:** Design only. No code written yet — this spec is what the implementation plan
(`docs/superpowers/plans/`) will be built from.

**Spec this argues from:** `project_documentation/memory_nityam_architecture/memory_layer.md`
(v2.0) and `google_cloud_storage_integration.md` (v1.0) — the three-tier model, four record
schemas, and storage backends this tool visualizes. This document doesn't re-litigate those
decisions; it plans how to make their live behavior visible and legible in real time. It also
argues from a live inspection of the real Google ADK web dev UI (`google/adk/cli/browser/` inside
the installed `google-adk==2.7.1` package, plus `adk.dev`'s own docs) — the exact tab structure,
color tokens, typography, and layout facts cited in §7 were read from that source, not guessed.

---

## 1. Purpose

SMRITI (the tutor's memory layer) has no visualization of any kind today. `close_session` — the
only path into episodic and long-term memory — is fully built and tested but **never invoked
outside tests**, so there is currently no live event to watch even in principle. ADK web's own dev
UI shows agent events/tool calls/traces, not Firestore/Redis memory content. This project builds a
standalone companion product — the **SMRITI Observatory** — that makes every memory read and write
visible in real time as an agent session runs: what tier it touched, what changed, and a direct
link back to the real OpenTelemetry trace span that caused it. It is explicitly a **companion to**
ADK web, not a replacement or a fork of it — visually and structurally modeled on it, cross-linking
to it, owning none of its code.

## 2. Scope

**In scope (v1):**
1. Wiring `close_session` into the real running tutor app (it currently has zero production
   trigger) via an explicit endpoint plus an idle-timeout safety net.
2. Instrumenting every persisted memory operation (not just writes — reads too, since "what was
   retrieved from which memory" was an explicit requirement) with a structured event, carried over
   Redis Pub/Sub and correlated to the live OpenTelemetry trace/span that produced it.
3. A backend service that ingests those events, computes human-readable diffs on long-term writes,
   and serves both a live WebSocket stream and REST snapshots.
4. A frontend that visualizes one live session in real time: the workflow tier's turn buffer
   filling up, the episodic write landing at session close, and the long-term DPM/TeachingMemory
   diff — styled and structured to read as a natural extension of ADK web.
5. Testing against real Firestore + local Redis (project `nityam-506707`), matching this
   repo's existing "skip, don't mock" test convention.

**Explicitly out of scope for v1** (confirmed with the user):
- Cross-session / historical timeline view (a student's DPM evolving over many sessions) — the
  event/storage model below is designed not to preclude this, but no UI for it ships in v1.
- Any change to the real product `frontend/` — it stays fully mocked, untouched.
- Fixing the pre-existing GCS-artifact-path disconnect (`config.GCS_BUCKET` defined but unused,
  `ArtifactAgent` writes to local disk instead) — a real bug the research surfaced, unrelated to
  memory visualization, not required for this to work.
- Multi-student support — `student_id` is still hardcoded to `"demo_student"` upstream
  (`app/agents/tutor_agent.py`); the Observatory reflects that limitation rather than fixing it.
- Authentication/multi-user access control — this is a local, internal engineering tool for v1
  (binds to `localhost` only), the same trust model `adk web` itself uses.

## 3. Architecture overview

Two new pieces plus one small addition to the existing tutor app; nothing else in the repo changes.

```
 sub_modules_examples/tutor (existing, gets 3 small additions)
 ┌──────────────────────────────────────────────────────────────┐
 │ app/memory/store.py, short_term.py   ← instrumented (§5)      │
 │ app/app_utils/memory_routes.py       ← NEW: close endpoint,   │
 │                                         idle-timeout sweep    │
 │                                         (§6)                  │
 └───────────────┬──────────────────────────────────────────────┘
                  │ every store/short_term call publishes 1 event
                  ▼
            Redis Pub/Sub + one capped list        (existing Redis instance,
       smriti:events:live   (channel, all events)    already a dependency)
       smriti:events:recent (capped list, backlog)
                  │
                  ▼
 smriti-observatory/backend  (NEW, standalone FastAPI service, §7)
   - subscribes smriti:events:live (plain Redis SUBSCRIBE)
   - imports app.memory.store / app.memory.schemas from the tutor
     package directly (path dependency — never re-implements reads)
   - maintains an in-memory per-student snapshot cache, diffs each
     long-term write against it
   - serves REST snapshots + WebSocket live stream
                  │ WebSocket
                  ▼
 smriti-observatory/frontend  (NEW, React+TS+Vite, §8)
   - live Workflow / Episodic / Long-term panels
   - per-event deep link → real Cloud Trace (trace_id)
   - per-session deep link → real ADK web /dev-ui/
```

## 4. Directory layout

```
smriti-observatory/
├── README.md                      # what this is, how to run it, screenshots
├── backend/
│   ├── pyproject.toml              # own venv; [tool.uv.sources] path-depends on
│   │                                # ../../sub_modules_examples/tutor for app.memory.*
│   ├── .env.example                 # GCP_PROJECT, FIRESTORE_DATABASE, REDIS_HOST, TUTOR_BASE_URL
│   ├── observatory/
│   │   ├── __init__.py
│   │   ├── main.py                  # FastAPI app, lifespan, CORS (localhost only)
│   │   ├── events.py                # MemoryEvent schema (mirrors the wire shape from §5)
│   │   ├── ingest.py                # Redis PSUBSCRIBE loop → snapshot cache → diff → broadcast
│   │   ├── diff.py                  # schema-aware diff_dpm() / diff_teaching_memory()
│   │   ├── snapshot_cache.py        # in-memory per-student last-seen state
│   │   ├── routes_rest.py           # /api/sessions, /api/sessions/{id}/state, /events, /close
│   │   ├── routes_ws.py             # /ws/sessions/{id}, /ws/global
│   │   └── trace_links.py           # Cloud Trace / ADK web URL builders
│   └── tests/
│       ├── conftest.py              # same skip-if-unreachable fixtures as tutor's
│       ├── test_ingest.py
│       ├── test_diff.py
│       └── test_routes.py
└── frontend/
    ├── package.json                 # React 19 + Vite 8 + TS 6 + oxlint — matches frontend/
    ├── src/
    │   ├── main.tsx
    │   ├── App.tsx
    │   ├── styles/tokens.css        # ADK web's exact dark-theme tokens (§8.1)
    │   ├── styles/base.css
    │   ├── lib/
    │   │   ├── types.ts             # MemoryEvent, Diff, SessionState (mirrors backend/observatory/events.py)
    │   │   ├── ws.ts                 # WebSocket client + reconnect
    │   │   └── traceLinks.ts
    │   ├── components/
    │   │   ├── SessionDrawer.tsx     # left picker — mirrors ADK web's session drawer
    │   │   ├── TierPanel.tsx         # one of Workflow / Episodic / Long-term
    │   │   ├── EventTimeline.tsx     # main pane — Timeline ⟷ Trace toggle
    │   │   ├── DiffView.tsx          # before → after rendering
    │   │   └── SidePanel.tsx         # resizable right panel, tabs (§8.2)
    │   └── features/session/SessionView.tsx
    └── tests/ui.mjs                  # same headless-Chrome-over-CDP harness as frontend/tests/ui.mjs
```

Backend `pyproject.toml` uses a **uv path dependency** on the tutor package
(`[tool.uv.sources] app = { path = "../../sub_modules_examples/tutor", editable = true }` or
equivalent) so the Observatory imports `app.memory.store`, `app.memory.short_term`, and
`app.memory.schemas` directly rather than re-implementing Firestore/Redis reads or duplicating
Pydantic models. This is a deliberate accuracy choice: the Observatory must never decode a real
`DPMProfile`/`TeachingMemory` document with a schema that could drift from the one that wrote it.

## 5. Instrumentation: the event layer

**Where it hooks in:** `app/memory/store.py`'s 8 functions (`search_grounding`,
`search_grounding_semantic`, `get_dpm`, `put_dpm`, `get_teaching_memory`, `put_teaching_memory`,
`put_session_log`, `get_session_log`) and `app/memory/short_term.py`'s 4 functions (`append_turn`,
`append_artifact_event`, `get_turn_buffer`, `clear_session`) — the I/O boundary, not the
agent-facing tools. Every memory operation, from any caller (`tools.py`, `session_close.py`,
`scripts/seed_demo_data.py`, anything written later) flows through exactly these 12 functions, so
one wrapping layer gives complete coverage with the smallest possible diff — consistent with this
codebase's own established pattern (`google_cloud_storage_integration.md` §3.5: *"ops.py needs
zero changes... session_close.py needs zero changes"*).

A single decorator, `app/memory/instrumentation.py` (new file, ~40 lines):

```python
def emit_memory_event(tier: Literal["workflow", "episodic", "long_term"],
                       record_type: str, operation: Literal["read", "write"]):
    def decorator(fn):
        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            result = await fn(*args, **kwargs)
            _publish(tier, record_type, operation, fn.__name__, args, kwargs, result)
            return result
        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            result = fn(*args, **kwargs)
            _publish(tier, record_type, operation, fn.__name__, args, kwargs, result)
            return result
        return async_wrapper if inspect.iscoroutinefunction(fn) else sync_wrapper
    return decorator
```

`_publish` is fire-and-forget from the caller's perspective (Redis `PUBLISH`/`RPUSH` is
sub-millisecond, matching the same non-blocking reasoning already used for the Memorystore
write-through in `short_term.py` §5.3) and never raises — a Redis hiccup must never break a real
memory write. It builds:

```python
class MemoryEvent(BaseModel):
    event_id: str                 # uuid4
    ts: str                       # ISO 8601
    session_id: str | None
    student_id: str | None
    tier: Literal["workflow", "episodic", "long_term"]
    operation: Literal["read", "write"]
    record_type: str              # "grounding_chunk" | "dpm_profile" | "teaching_memory" |
                                   # "session_log" | "turn_buffer" | "artifact_event"
    source_fn: str                # e.g. "put_dpm"
    trace_id: str | None          # 32-hex, from the ambient OTel span, if any
    span_id: str | None           # 16-hex
    payload: dict | list | None   # the write value, or the read result
```

`session_id`/`student_id` are recovered from `args`/`kwargs` by function-specific extractors.
**Four of the eight `store.py` functions never receive a `session_id` at all** —
`get_dpm`/`put_dpm`/`get_teaching_memory`/`put_teaching_memory` take only `student_id` or a
profile/memory object with no session reference (by design: a DPM/TeachingMemory record outlives
any one session). Rather than changing those signatures, `instrumentation.py` exposes a
`contextvars.ContextVar[str | None]` and a `set_session_context(session_id)` setter;
`session_close.py`'s `close_session(...)` calls it once, at the top, with the session id it
already has in scope — since each invocation runs in its own asyncio Task, contextvars don't leak
across concurrent calls, so no explicit reset is needed. The four extractors fall back to this
context var when their own arguments don't carry a session id. This means long-term **writes**
(which only ever happen inside `close_session`, per `memory_layer.md` §3: *"the only path that
updates them is close_session"*) get correctly session-scoped events; long-term **reads** during a
live conversation (`get_dpm`/`get_teaching_memory`/`search_grounding*`, called from `tools.py`)
do not — `tools.py` itself gets zero changes, so these read events carry `session_id: null` and
surface only in the global/unscoped feed, not a specific session's panel. Documented as a known v1
limitation in §10, not silently decided.

`trace_id`/`span_id` come from `opentelemetry.trace.get_current_span().get_span_context()`,
formatted as `format(ctx.trace_id, "032x")` / `format(ctx.span_id, "016x")`; `None` when there's no
ambient span (e.g. a bare script call). Every event — scoped or not — publishes to one **global**
channel/list pair, not a per-session one, precisely so unscoped reads are never silently dropped:
- `PUBLISH smriti:events:live <json>` — for anyone currently watching (backend does one plain
  `SUBSCRIBE`, not a pattern subscribe — there's only one channel)
- `RPUSH smriti:events:recent <json>` (capped to the last 2000 via `LTRIM`, no TTL — the
  Observatory backend owns the reconnect-backlog concern, not `short_term.py`'s TTL semantics)

The Observatory backend filters this single stream by `session_id` server-side to serve
`/ws/sessions/{id}`; `/ws/global` passes everything through unfiltered, including unscoped reads.

This is a **pure side effect** — the decorated functions still return exactly what they returned
before, so every existing test in `tests/unit/memory/` and `tests/unit/test_session_close.py`
keeps passing unmodified. New tests cover the decorator itself (§9).

## 6. Wiring `close_session` into production

Two additions to the tutor app (`app/app_utils/memory_routes.py`, new file, mounted into
`fast_api_app.py` via `app.include_router(...)`):

**6.1 Explicit close endpoint** — `POST /memory/sessions/{session_id}/close`:
1. Reads the turn buffer back via `short_term.get_turn_buffer(session_id)` — the exact fallback
   path `google_cloud_storage_integration.md` §5.3 already anticipated for "outside the live
   process."
2. Resolves `student_id` from the request body if provided, else falls back to `"demo_student"`
   (the existing stub — not fixed here, see §2 non-goals).
3. Calls the real `close_session(...)` unchanged.
4. Deletes the Redis buffer (`short_term.clear_session`) and the heartbeat key (§6.2) on success.

This is the **one real production trigger**. The Observatory's own "close this session" debug
action (§8) calls this exact endpoint — it never reimplements `close_session` logic, so there is no
parallel/fake code path.

**6.2 Idle-timeout safety net**, mirroring the "safety-net TTL" philosophy already used for the
Redis turn-buffer (`short_term.py`'s 6-hour TTL): every `log_turn`/`log_artifact_evidence` call
refreshes a `session:{id}:heartbeat` key with a short TTL (default 30 minutes, configurable). Redis
keyspace notifications (`notify-keyspace-events Ex`) are enabled on the instance; a background task
started in `fast_api_app.py`'s `lifespan` subscribes to `__keyevent@0__:expired` and, on a
`session:*:heartbeat` expiry, calls the same close path in-process. This means a session actually
gets reflected into long-term memory even before anything in the product UI explicitly ends it —
closing the gap the research found, not just working around it for a demo.

## 7. Backend service (`smriti-observatory/backend`)

FastAPI, `uvicorn`, `redis.asyncio`, reusing `app.memory.store`/`schemas` per §4.

**Ingest loop** (`ingest.py`): one background task, `SUBSCRIBE smriti:events:live` (a single global
channel — see §5 for why events aren't split per-session at the source). On each
message: parse into `MemoryEvent`; if `record_type` is `dpm_profile` or `teaching_memory` and
`operation == "write"`, look up the previous value in `snapshot_cache.py` (seeded on backend
startup by reading current Firestore state via `store.get_dpm`/`get_teaching_memory` for any
student seen so far, refreshed as new students appear) and compute a diff via `diff.py`; update the
cache to the new value; broadcast `{event, diff}` to every WebSocket subscribed to that
`session_id` (and to `/ws/global`, for a future cross-session dashboard — cheap to support given
the `PSUBSCRIBE` already covers all sessions, not built into the UI in v1).

**`diff.py`** is schema-aware, not a generic recursive differ dumped raw into the UI: for
`DPMProfile`, it walks `weaknesses` by `concept_id` and reports `mastery: partial → known` /
`strength: weak → strong` style changes plus new/superseded `self_reflection` entries; for
`TeachingMemory`, `covered` status transitions and `open_doubts` lifecycle transitions
(`active → remediating → resolved`), matching the exact enums in `memory_layer.md` §2.2–2.3. Uses
`deepdiff` for the underlying recursive comparison, with a thin post-processing layer that turns
raw paths into these human-readable labels — avoids hand-rolling recursive dict diffing while
keeping the UI's language schema-literate rather than JSON-Pointer-literate.

**REST (`routes_rest.py`):**

| Route | Returns |
|---|---|
| `GET /api/sessions` | Sessions with observed activity — `{session_id, student_id, status: live\|closed, started_at, last_event_at, turn_count}`, derived from distinct `session_id`s seen on `smriti:events:recent` plus live `session:{id}:heartbeat` keys (§6.2), cross-referenced against Firestore `session_logs` for closed ones |
| `GET /api/sessions/{id}/state` | Full current snapshot: workflow (`short_term.get_turn_buffer`), episodic (`store.get_session_log`, may be absent), long-term (`store.get_dpm` + `get_teaching_memory` for that session's student) — for initial page load before live events arrive |
| `GET /api/sessions/{id}/events?since=<event_id>` | Backlog from the capped Redis list, paginated — so a client connecting mid-session isn't blind to what already happened |
| `POST /api/sessions/{id}/close` | Proxies to the tutor app's `POST /memory/sessions/{id}/close` (§6.1) — no reimplementation |
| `GET /api/health` | `{redis: bool, firestore: bool, tutor_reachable: bool}` — connectivity status the frontend surfaces as a banner |

**WebSocket (`routes_ws.py`):** `/ws/sessions/{id}` (scoped live stream) and `/ws/global` (all
sessions, `session_id` field per message) — both push `{type: "memory_event", event, diff}`.

**Trace links (`trace_links.py`):** builds
`https://console.cloud.google.com/traces/list?tid={trace_id}&project={GCP_PROJECT}` from an
event's `trace_id`. The ADK-web deep link (`/dev-ui/...` on the tutor's own port) is included as a
plain per-session link to the tutor server's dev-ui root; the research done for this spec could not
confirm a session-scoping query parameter ADK web accepts (its session drawer supports "Search
using session ID" as a manual UI action, not a confirmed URL param) — **this is verified during
implementation** (§10), not asserted here as settled.

## 8. Frontend (`smriti-observatory/frontend`)

React 19 + TypeScript + Vite 8 + oxlint + CSS Modules — the exact stack and conventions already
used by `frontend/` (including its dependency-free, no-framework CSS approach and its headless
Chrome-over-CDP visual test harness, `tests/ui.mjs`) — for tooling consistency across the repo,
even though this is a fully separate package/audience per §2.

### 8.1 Visual language — copied from the real ADK web build, not guessed

Read directly from `google/adk/cli/browser/styles-*.css` inside the installed `google-adk==2.7.1`
package. `src/styles/tokens.css` defines these as CSS custom properties, dark theme as the default
(matching ADK web's own default):

| Token | Value |
|---|---|
| `--surface` / `--background` | `#121212` |
| `--surface-container-low` / `-container` / `-high` / `-highest` | `#1a1a1a` / `#1e1e1e` / `#2a2a2a` / `#3a3a3a` |
| `--primary` / `--on-primary` / `--primary-container` | `#7cc4ff` / `#003366` / `#004b8d` |
| `--secondary` / `--on-secondary` / `--secondary-container` | `#b5c9e2` / `#203246` / `#3a485a` |
| `--tertiary` / `--tertiary-container` | `#d5baff` / `#5f00c0` |
| `--error` / `--error-container` | `#ffb4ab` / `#93000a` |
| `--outline` / `--outline-variant` | `#958e99` / `#49454e` |
| `--on-surface` | `#e6e1e6` |
| `--graph-canvas` | `#0e172a` (their graph/diagram-canvas-specific dark navy — reused here for the tier-relationship diagram) |
| Corner radii | 4 / 8 / 12 / 16 / 28 / 9999px (xs/sm/md/lg/xl/pill) |
| Type | **Google Sans** (UI text, full Material type scale), **Google Sans Mono** (JSON/diff/code panels) |
| Icons | Material Symbols Outlined |

A `tokens.css` `[data-theme="light"]` block carries the light-theme values found in the same
research pass (§background above) for completeness, even though dark is the shipped default,
matching ADK web. **Not** copied: ADK web's Google Analytics telemetry (consent-gated) — the
Observatory ships with zero external analytics, stated explicitly in its README.

### 8.2 Structural layout — parallel to ADK web's shape, not identical

| ADK web | Observatory equivalent |
|---|---|
| Left session-selector drawer (New/Import/Export/Search by ID) | `SessionDrawer.tsx` — same interaction shape, listing sessions from `GET /api/sessions` |
| Main pane, Events ⟷ Traces toggle | `EventTimeline.tsx` — Timeline ⟷ Trace toggle; Trace mode deep-links out to real Cloud Trace via `trace_links.ts` |
| Right resizable panel (480px/360min/50vw max), tabs: Events, State, Artifacts, Sessions, Evals, Tests | `SidePanel.tsx`, same resize behavior, tabs: **Workflow, Episodic, Long-term, Diff, Sessions** — our tier-oriented equivalent |
| Selecting an event → Info/Graph/Request/Response sub-tabs | Selecting a `MemoryEvent` row → Info/Trace-link/Payload sub-tabs |

Each `TierPanel.tsx` instance renders one tier with tier-appropriate visual treatment: **Workflow**
(blue accent, cards appending live as turns arrive, an ephemeral/pulsing indicator while a session
is live), **Episodic** (amber accent, empty/pending until session close, then renders the full
`SessionLog.turns` ledger at once), **Long-term** (green/durable accent, `DiffView.tsx` renders
each field-level change from §7's diff engine — e.g. a concept's mastery badge visibly transitions
`partial → known` with a brief highlight animation). A session header shows session/student id,
live/closed status, and the "Open in ADK web" + "close this session" (§6.1) actions.

### 8.3 Data flow — concrete walkthrough

1. Student sends a turn → `TutorAgent` calls `log_turn(...)` → `short_term.append_turn` (now
   decorated) publishes a `MemoryEvent{tier: workflow, operation: write, record_type: turn_buffer}`
   with the `execute_tool` span's `trace_id` attached.
2. Backend's ingest loop receives it, no diff needed (workflow tier isn't diffed), broadcasts to
   `/ws/sessions/{id}`.
3. Frontend's `Workflow` `TierPanel` appends a new turn card, pulses once.
4. Session goes idle 30 minutes → heartbeat key expires → tutor's background task calls
   `close_session` → `put_session_log` (decorated, `tier: episodic`) fires one event; `reflect()`
   proposes operations; `apply_operations` calls `put_dpm`/`put_teaching_memory` (decorated,
   `tier: long_term`) — these calls happen outside any tool-call span, but inside the HTTP request
   span FastAPI's OTel instrumentation creates for the triggering request, so `trace_id` is still
   populated (verified in testing, §10).
5. Backend diffs the new `DPMProfile` against its cached previous value, finds
   `weaknesses.projectile_motion.mastery: partial → known`, broadcasts `{event, diff}`.
6. Frontend's `Episodic` panel renders the full turn ledger for the first time; `Long-term` panel
   shows the mastery badge transition with the diff highlight.

## 9. Testing & validation

Matches this repo's existing convention exactly — **real Firestore + local Redis, skip (not
fail) if unreachable**, no mocked backends (`tests/conftest.py`'s `firestore_db`/`redis_client`
fixtures are the pattern; the Observatory's own `conftest.py` reuses the same shape).

- `test_ingest.py` — publish a synthetic `MemoryEvent` on a real Redis channel, assert the ingest
  loop updates the snapshot cache and produces the expected diff.
- `test_diff.py` — pure, no I/O: feed known before/after `DPMProfile`/`TeachingMemory` pairs,
  assert the human-readable diff labels match (mastery transitions, doubt lifecycle transitions).
- `test_routes.py` — REST endpoints against real Firestore-backed state (seeded via
  `scripts/seed_demo_data.py`'s pattern).
- **End-to-end acceptance test** (the actual proof this works): script that (a) starts the tutor
  app and the Observatory backend, (b) drives a real conversation through the tutor's chat API
  invoking `log_turn` several times, (c) asserts events arrive over the Observatory's WebSocket in
  order with correct `trace_id`s, (d) triggers `POST .../close`, (e) asserts the long-term diff
  event arrives and matches Firestore's actual post-close state.
- Frontend: `tests/ui.mjs`, same headless-Chrome-over-CDP pattern as `frontend/tests/ui.mjs` —
  drives a live session end-to-end and asserts the three tier panels render expected content, no
  console errors. Per this project's standing rule for UI work, the dev server is actually started
  and the feature is exercised in a real browser before this is called done — not just unit-tested.

## 10. Open items, explicitly flagged rather than assumed

1. **ADK web session-scoping URL param** — not confirmed by research (§7). Verify against the real
   running dev UI during implementation; if no clean deep-link exists, the "Open in ADK web" action
   links to the dev-ui root with the session id shown for manual paste into its search box instead.
2. **Idle-timeout default (30 min)** — a reasonable starting value, not derived from any product
   requirement; make it configurable via env var so it can be tuned against real usage.
3. **OTel span presence during `close_session`'s Firestore writes** — expected to inherit the
   triggering HTTP request's span per `otel_to_cloud`'s app-wide instrumentation, but not yet
   verified against the installed `google-adk==2.7.1` FastAPI instrumentation; confirm in
   `test_routes.py` rather than assume.
4. **`deepdiff` as a new backend dependency** — a mature, widely-used library; flagged only because
   it's new to this repo's dependency set, not because of any concern about it.
5. Cross-session history (§2 out-of-scope) is deliberately not precluded by this data model
   (Firestore already holds full history; the event stream is additive) — a natural v2.
6. **Long-term reads aren't session-scoped** (§5) — `get_dpm`/`get_teaching_memory`/
   `search_grounding*` happen mid-session via `tools.py`, which gets zero changes, so those read
   events carry `session_id: null` and only appear in `/ws/global`'s unscoped feed, not a specific
   session's Long-term panel. A session's Long-term panel is instead driven by the REST snapshot
   (`GET /api/sessions/{id}/state`, a direct Firestore read for that session's student) for
   current state, plus write-side diffs from `close_session` (which is session-scoped). Threading
   session id into live reads too — e.g. by having `tools.py` set the same context var — is a
   small, deferrable follow-up if the unscoped feed proves confusing in practice.

---

*v1.0 — new document, companion to `memory_layer.md` v2.0 and `google_cloud_storage_integration.md`
v1.0. Written after live inspection of the running tutor app's memory code and the real ADK web dev
UI (installed package + `adk.dev` docs).*
