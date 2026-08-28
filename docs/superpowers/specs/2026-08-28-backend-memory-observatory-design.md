# Live Memory Visualization for the Real `backend/` Tutor

## Goal

Watch the real production tutor's memory layer — Working (Redis turn buffer),
Episodic (`session_log`), Long-term (`dpm_profile` / `teaching_memory`) — change
live, tier by tier, as an actual voice session runs against `backend/` +
`frontend/`, with zero manual session selection: open the viewer while a
session is live and it's already showing it.

## Why not the actual Google ADK web UI

Ruled out, not assumed — verified directly against the running code:
`backend/app/main.py` is a hand-built FastAPI app (`@app.websocket
("/ws/{user_id}/{session_id}")`, a `/health` route, static frontend hosting).
It does not call `google.adk.cli.fast_api.get_fast_api_app`, so it exposes
none of the REST surface ADK web's Angular app talks to (`/apps/{app}/users/
{user}/sessions`, `/run_sse`, `/dev/apps/{app}/debug/trace/session/{id}`).
ADK web cannot list, load, or stream a session from a server that doesn't
speak that API — that's not a configuration gap, it's a different protocol
entirely. Making `backend/` speak it would mean giving the production
WebSocket/voice-loop app a second, parallel ADK-server identity — real
surgery on the exact code five recent commits just spent hardening
(`e1330fd`, `4ffb005`, `e46b174`, `3f1ff90`). Declined for that reason.

What's already fully wired to real Google ADK web is `sub_modules_examples/
tutor` + `smriti-observatory/adk-web` — confirmed built and merged
(`510cc2b`, `358507f`, `5f009aa`), not just designed. That pair is unaffected
by anything in this document.

Instead: extend the **standalone Observatory** (`smriti-observatory/backend`
+ `smriti-observatory/frontend`) — a plain HTTP/Redis-WebSocket client with
no ADK-protocol dependency at all — to point at `backend/` instead of (or as
well as) the ADK tutor scaffold it was originally built against.

## Non-goals

- No change to `frontend/` (the real product UI) at all.
- No change to `backend/`'s WebSocket connection lifecycle, session-close
  trigger, or auth path — every addition here is new, read-only surface
  bolted on beside it.
- No agent/tool graph panel for `backend/` (its agents aren't ADK-dev-ui
  scaffolded the way `sub_modules_examples/tutor`'s are) — `AgentToolGraph`
  degrades to empty, already handled by `routes_rest.py`'s existing
  try/except-to-`{"dot_src": ""}` fallback. Not fixed here.
- No Cloud Trace correlation fix — `backend/` runs no OpenTelemetry
  instrumentation today (confirmed: no `opentelemetry` import anywhere under
  `backend/app/`), so every `MemoryEvent` it publishes will carry
  `trace_id: null`. The Observatory already renders untraced events fine
  (`SessionView.tsx`'s own comment: "untraced operation" fallback) — this is
  an accepted, pre-existing capability gap, not a regression to fix here.
- No historical/cross-session timeline view — same v1 scope line the
  original Observatory design already drew; still not built.
- `sub_modules_examples/tutor` + `smriti-observatory/adk-web` are not
  touched by this plan at all.

## Architecture overview

```
 backend/ (existing, gets 2 additive pieces)
 ┌───────────────────────────────────────────────────────────┐
 │ app/memory/store.py        ← NEW: emit_memory_event        │
 │   (module-level re-export    wraps put_dpm/get_dpm/        │
 │    wrapping point, works       put_teaching_memory/         │
 │    for BOTH sqlite AND         get_teaching_memory/         │
 │    firestore backends          put_session_log/             │
 │    transparently)               get_session_log             │
 │ app/memory/short_term.py    ← NEW: same decorator on         │
 │                                append_turn/                 │
 │                                append_artifact_event         │
 │ app/memory_routes.py        ← NEW file: 2 read-only GETs    │
 │ app/main.py                 ← +2 lines: mount router,        │
 │                                set_session_context() call    │
 └───────────────┬─────────────────────────────────────────────┘
                  │ every store/short_term call publishes 1 event
                  ▼
      Redis Pub/Sub + capped list         (existing Redis instance
 smriti:events:live / smriti:events:recent    backend/ already depends on)
                  │
                  ▼
 smriti-observatory/backend  (existing, loses its `tutor` package
                               import coupling — becomes backend-agnostic)
   - subscribes smriti:events:live (unchanged)
   - NEW: talks to whichever agent server via plain HTTP
     (AGENT_BASE_URL env var) instead of importing its Python package
   - NEW: reads Firestore directly via its own google-cloud-firestore
     client instead of importing app.memory.store
                  │ WebSocket (unchanged)
                  ▼
 smriti-observatory/frontend  (existing, gains one behavior)
   - NEW: auto-selects the live session, no click required
   - existing live Workflow/Episodic/Long-term panels, diff view,
     per-event Cloud Trace deep link — unchanged
```

## 1. Instrumenting `backend/`'s memory layer

Same non-invasive pattern already proven in `sub_modules_examples/tutor/app/
memory/instrumentation.py` — a fire-and-forget decorator that never raises
and never changes a wrapped function's return value, so every existing test
in `backend/tests/` keeps passing unmodified. New file:
`backend/app/memory/instrumentation.py`, essentially a straight port:

- Same `MemoryEvent` fields (`event_id, ts, session_id, student_id, tier,
  operation, record_type, source_fn, trace_id, span_id, payload`), same two
  Redis keys (`smriti:events:live` pub/sub channel, `smriti:events:recent`
  capped list, `LTRIM`-ed to 2000) — this is the one place the wire contract
  must not drift from `sub_modules_examples/tutor`'s, since
  `smriti-observatory/backend`'s ingest loop reads both apps' events through
  the same code path (§3).
- `trace_id`/`span_id` come from `opentelemetry.trace.get_current_span()`
  exactly as before — since `backend/` runs no OTel SDK, this always
  resolves to `(None, None)`. Documented, not special-cased: the decorator
  doesn't need to know that ahead of time, it just reads whatever ambient
  span exists (none).
- One difference from the tutor's copy, because `backend/`'s own functions
  already carry both ids where the tutor's don't: `short_term.append_turn`/
  `append_artifact_event`/`get_turn_buffer`/`clear_session` all take
  `(session_id, student_id, ...)` positionally already (confirmed,
  `backend/app/memory/short_term.py`) — so their `extract_ids` callbacks are
  trivial (`args[0], args[1]`), no contextvar needed for those two.

**Wrapping point — `backend/app/memory/store.py`, not each backend impl
file.** `store.py` already centralizes every function as a module-level
re-export (`put_dpm = _impl.put_dpm`, etc., picking `_impl` = `store_sqlite`
or `store_firestore` per `NITYAM_STORE`). Wrapping at that re-export point,
not inside `store_firestore.py`, means the instrumentation works identically
under both backends — sqlite-mode local dev included — with one set of
decorator call sites instead of two:

```python
# backend/app/memory/store.py — new imports + wrapped re-exports
from app.memory.instrumentation import emit_memory_event, get_session_context

# Each function's own argument shape decides how student_id is found;
# session_id always comes from the ambient contextvar, since none of these
# six functions receive one directly (mirrors the tutor's own
# instrumentation.py exactly, same underlying gap). One extractor per
# function, not one generic one — get_dpm(db, student_id) and
# put_dpm(db, profile) don't share a shape.
def _get_ids(args, kwargs, result):        # get_dpm / get_teaching_memory(db, student_id)
    return get_session_context(), (args[1] if len(args) > 1 else kwargs.get("student_id"))

def _put_ids(args, kwargs, result):        # put_dpm(db, profile) / put_teaching_memory(db, memory)
    obj = args[1] if len(args) > 1 else kwargs.get("profile") or kwargs.get("memory")
    return get_session_context(), obj.student_id

def _log_ids(args, kwargs, result):        # put_session_log(db, log) / get_session_log(db, session_id)
    obj = args[1] if len(args) > 1 else kwargs.get("log") or kwargs.get("session_id")
    return (obj.session_id if hasattr(obj, "session_id") else obj), None

put_dpm = emit_memory_event("long_term", "dpm_profile", "write", _put_ids)(_impl.put_dpm)
get_dpm = emit_memory_event("long_term", "dpm_profile", "read", _get_ids)(_impl.get_dpm)
put_teaching_memory = emit_memory_event("long_term", "teaching_memory", "write", _put_ids)(_impl.put_teaching_memory)
get_teaching_memory = emit_memory_event("long_term", "teaching_memory", "read", _get_ids)(_impl.get_teaching_memory)
put_session_log = emit_memory_event("episodic", "session_log", "write", _log_ids)(_impl.put_session_log)
get_session_log = emit_memory_event("episodic", "session_log", "read", _log_ids)(_impl.get_session_log)
```

(Illustrative — the implementation plan should re-verify each function's
exact positional/keyword call shape against real call sites before
finalizing these, same as any extractor in this codebase's existing
instrumentation.)

`get_dpm`/`put_dpm`/`get_teaching_memory`/`put_teaching_memory` never receive
a `session_id` argument (same gap the tutor's version documents) — same
fix: a `contextvars.ContextVar` + `set_session_context(session_id)` /
`get_session_context()` pair in the new `instrumentation.py`. Verified
directly where the tutor's real (not illustrative) code calls this:
`sub_modules_examples/tutor/app/session_close.py:169`, the **first line
inside `close_session(...)` itself** — not in its caller. `backend/app/
session_close.py` gets the identical one-line addition at the top of its
own `close_session(...)`:

```python
# backend/app/session_close.py, first line of close_session(...):
def close_session(conn, session_id, student_id, started_at, buffer, client):
    instrumentation.set_session_context(session_id)
    ...  # rest unchanged
```

Since `close_session` runs synchronously inside the background thread
`main.py`'s `_flush_session_memory` already spawns via `asyncio.to_thread`,
setting the contextvar as the function's own first statement and reading it
moments later in the same synchronous call stack (still the same thread)
needs no cross-thread/cross-task propagation reasoning at all — it's a
plain same-thread set-then-read, same as the tutor's own call site.
`main.py` needs no change for this part.

No changes anywhere else: `app/memory/tools.py` (the ADK-tool-facing layer)
and `app/session_close.py` call `store.*`/`short_term.*` by name and never
touch the connection object directly, so both need **zero changes** — the
same "one wrapping layer, smallest possible diff" property the original
Observatory design relied on.

## 2. Read-only memory endpoints on `backend/`'s own server

New file `backend/app/memory_routes.py` (backend/ has no `app_utils/`
subpackage the way the tutor scaffold does — this lives as a flat module,
matching `sessions.py`/`logs.py`/`briefing.py`'s existing layout):

```python
router = APIRouter(prefix="/memory")

@router.get("/sessions/{session_id}/state")
async def session_state_endpoint(session_id: str, student_id: str):
    db = store.connect()
    profile = store.get_dpm(db, student_id)
    memory = store.get_teaching_memory(db, student_id)
    session_log = store.get_session_log(db, session_id)
    turn_buffer = await short_term.get_turn_buffer(session_id, student_id)
    return {...}  # identical shape to sub_modules_examples/tutor's endpoint

@router.get("/sessions/{session_id}/events")
async def session_events_endpoint(session_id: str, student_id: str, trace_id: str | None = None):
    ...  # identical shape, reusing the same _read_recent_events/_replay_diffs
    # pattern already proven in sub_modules_examples/tutor/app/app_utils/memory_routes.py
```

Mounted in `main.py` via one new line, `app.include_router(memory_router)`,
beside the existing `@app.websocket(...)`/`@app.get("/health")` routes — pure
addition, no interaction with the WebSocket handler.

**Deliberately no `POST /memory/sessions/{id}/close` on `backend/`.** Unlike
`sub_modules_examples/tutor` (where wiring `close_session` into production
*was* the gap), `backend/`'s own `_flush_session_memory` already calls the
real `close_session` correctly on every WebSocket teardown (the fix landed
in `e46b174`/`4ffb005`) — there is no missing trigger to add, and inventing
a second, REST-triggerable close path for a session that's supposed to be
tied to one live connection would be new risk surface for no real need.
`smriti-observatory/backend`'s existing close-proxy route simply won't
resolve against `backend/` (404) — the frontend UI's "close this session"
action is hidden when the connected agent server doesn't advertise support
for it (a small existing-vs-absent check against `/api/health`'s response,
§4).

## 3. Decoupling `smriti-observatory/backend` from the `tutor` package

**The concrete problem, verified directly:** `smriti-observatory/backend/
pyproject.toml` declares a `uv` path dependency on `sub_modules_examples/
tutor` (distribution name `tutor`, importable module `app`) specifically so
`observatory/routes_rest.py`, `observatory/main.py`, and `observatory/
events.py` can `from app.memory import store, short_term` and `from
app.memory.instrumentation import MemoryEvent` — reusing the tutor's actual
Pydantic classes rather than re-declaring them, a deliberate accuracy choice
in the original design. `backend/` ships its **own** top-level package also
named `app`. Two distributions both providing a module named `app` cannot
coexist in one dependency graph — pointing this Observatory instance at
`backend/` by adding a second path dependency the same way is not viable.

**Fix: make `smriti-observatory/backend` protocol-based instead of
import-based** — it already does this for one route
(`close_session_proxy` already proxies over `httpx` instead of importing
`close_session`), this extends the same pattern to the two reads:

- `observatory/events.py` — replace `from app.memory.instrumentation import
  MemoryEvent` with a **local** re-declaration of the same Pydantic model
  (identical field set: `event_id, ts, session_id, student_id, tier,
  operation, record_type, source_fn, trace_id, span_id, payload`). This is
  safe specifically because §1 keeps the wire shape byte-identical to
  `sub_modules_examples/tutor`'s own `instrumentation.py` — both apps
  publish JSON either copy of this model can decode. `FieldChange`/
  `EnrichedEvent` (already local, non-imported types) are untouched.
- `observatory/routes_rest.py` — `session_state`/`session_events` become
  `httpx` proxies to `{agent_base_url}/memory/sessions/{id}/state?
  student_id=...` and `.../events?student_id=...&trace_id=...`, mirroring
  the existing `close_session_proxy`'s own shape exactly. `list_sessions`
  and `health` stop reading `app.config.REDIS_HOST`/`REDIS_PORT` (the
  tutor's config) and take the Observatory's *own* already-loaded
  `REDIS_HOST`/`REDIS_PORT` (from `main.py`'s existing `os.environ.get(...)`
  reads) as constructor params to `build_router(...)` instead — this was
  already a latent inconsistency (the Observatory has always had its own
  `.env` values for these; `routes_rest.py` just wasn't using them) that
  this refactor also fixes as a side effect.
- `observatory/main.py` — replace `from app.memory import store; store.
  connect()` with a plain, local `google.cloud.firestore.Client(project=
  GCP_PROJECT, database=FIRESTORE_DATABASE)` (both already read from the
  Observatory's own env in `main.py` today) plus two small local functions
  reading `.collection("dpm_profiles"/"teaching_memories").document(
  student_id).get().to_dict()` directly — no Pydantic validation needed
  here at all (these two callables only exist to prime `ingest.py`'s diff
  cache with a plain `dict | None`, which `.to_dict()` already is).
  `observatory/diff.py` needs **zero changes** — confirmed it already
  operates on plain dicts, never imports either app's schema classes.
  `observatory/ingest.py` needs **zero changes** — its `get_dpm`/
  `get_teaching_memory` params are already typed as plain `Callable[[str],
  dict | None]`, agnostic to what's behind them.
- `pyproject.toml` — move the `tutor` path dependency out of `[project]
  dependencies` and into `[dependency-groups] dev` instead of dropping it
  outright: `tests/test_end_to_end.py` is a real, valuable integration test
  that deliberately drives `sub_modules_examples/tutor`'s actual
  `app.memory.tools`/`app.app_utils.memory_routes`/`app.session_close` in
  process to prove the whole tutor-specific pipeline works — that test stays
  exactly as it is, still tutor-coupled on purpose, since it's testing that
  integration specifically. What moves off the dependency is the
  **production code path** (`main.py`, `routes_rest.py`, `events.py`) — it
  no longer imports `app.*` at all, so the running `observatory.main:app`
  process itself has no coupling to either app's package, and can be
  pointed at `backend/` (which also ships a package literally named `app`)
  without a naming collision. Also add `"google-cloud-firestore>=2.16"`
  (same version floor `sub_modules_examples/tutor` already pins) as its own
  explicit runtime dependency instead of an inherited transitive one.
- `tests/conftest.py`'s `firestore_db`/`redis_client` fixtures currently
  import `app.memory.store`/`app.config` too (confirmed by grep) — update
  both to build a plain `firestore.Client`/`redis.Redis` directly from the
  Observatory's own env vars, same as `main.py`'s new lifespan (previous
  bullet). `test_end_to_end.py` doesn't use these fixtures (it builds its
  own tutor-specific connections directly), so this doesn't affect it.
- `tests/test_routes_rest.py` seeds Firestore via `store.put_dpm(firestore_db,
  DPMProfile(...))`/`TeachingMemory(...)` — switch these two seed calls to
  writing the equivalent plain dict directly through the (now plain)
  `firestore_db` fixture (`firestore_db.collection("dpm_profiles").
  document(...).set({...})`), since the fixture and the router under test no
  longer have typed schema classes available. Every other test in this file
  is already dict/JSON-based and needs no change.
- `tests/test_events.py::test_memory_event_is_the_tutor_apps_own_class`
  currently asserts identity (`MemoryEvent is TutorMemoryEvent`) — this
  assertion's premise goes away by design once `events.py` declares its own
  local model. Replace it with a wire-compatibility test instead: construct
  the tutor's real `app.memory.instrumentation.MemoryEvent` (this one test
  file may keep that one import, exactly like `test_end_to_end.py`, since
  it's explicitly testing cross-app JSON compatibility) with a sample
  payload, serialize it, and assert the Observatory's own local
  `MemoryEvent.model_validate_json(...)` parses it into an equal object —
  proving the two classes stay wire-compatible without being the same
  class.
- **Health check** (`routes_rest.py`'s `health()`): the `tutor_reachable`
  probe currently hits `/list-apps` (an ADK-dev-server-only route). Switch
  to hitting `{agent_base_url}/health` — a route `backend/`'s own
  `main.py:644` already serves, and functionally equivalent for
  `sub_modules_examples/tutor` too, since `get_fast_api_app` also always
  serves `/health` verified separately by every existing docs reference to
  it (`sub_modules_examples/tutor` boots under ADK's own dev server, which
  serves this alongside its dev-ui routes). One probe, works against either
  backend the Observatory might be pointed at.
- **Env var naming**: `TUTOR_BASE_URL` is kept as the variable name (not
  renamed) to avoid churning `.env.example`/existing running instructions
  for the `sub_modules_examples/tutor` use case, which keeps working
  unmodified — its meaning is simply documented as "base URL of whichever
  agent server exposes `/memory/*` routes," and for this project it now
  points at `backend/`'s own port when that's what's being observed.

**Net effect:** `smriti-observatory/backend` becomes a genuinely
backend-agnostic memory-event viewer — it can point at
`sub_modules_examples/tutor` (unchanged behavior, still works) or at
`backend/` (new), purely via `.env` values, with no code fork and no Python
package coupling to either.

## 4. Auto-selecting the live session (the actual ask)

`smriti-observatory/frontend/src/features/session/SessionView.tsx` today:
fetches `/api/sessions` exactly once on mount (line 28-33), and requires a
manual click in `SessionDrawer` to set `selectedId` (line 103) before
anything else renders — "Select a session on the left..." is the default
empty state (line 128-130).

Two additive changes, both inside `SessionView.tsx`:

1. **Poll `/api/sessions` every 4s** (not a WebSocket — there's no
   "session list changed" broadcast today, and a periodic fetch of one
   small JSON list is negligible load, matching the "don't add a new
   broadcaster" restraint the original design already applied elsewhere).
   Extracts the existing mount-only fetch into a function, calls it once
   immediately and then on an interval, clearing the interval on unmount.
2. **Auto-select**: when the fetched list changes, if there is no
   `selectedId` yet, or the currently selected session's own entry just
   flipped to `status !== "live"` while a *different* session is now
   `"live"`, select the most-recently-active `"live"` one
   (`sessions.filter(s => s.status === "live").sort by last_event_at,
   take newest`). If the user has manually clicked a different (e.g.
   closed/historical) session, that stays selected — auto-select only ever
   fires to fill an *empty* selection or to follow a session hand-off, never
   overrides an explicit choice while its session is still live.

This satisfies the literal ask: open `smriti-observatory/frontend` while a
`backend/` voice session is in progress, and it is already showing that
session's Working/Episodic/Long-term panels and live event timeline, no
click required. If nothing is live yet, it falls back to today's existing
behavior (empty state / manual pick from history) — not a new failure mode.

**"Open in ADK web ↗" header link** (`SessionView.tsx` line 114): stays as
today's plain `adkWebUrl(TUTOR_BASE_URL)` helper, unchanged code, in both
configurations. When pointed at `backend/`, clicking it 404s (no ADK
dev-ui there) — same category of harmless rough edge as the already-accepted
empty agent/tool graph (non-goals list), not fixed in this pass: wiring a
real "does this agent server have a dev-ui" signal through `/api/health`
into the frontend is real, separable plumbing for one dead link with no
functional impact on the actual memory visualization. Deferred, not
silently dropped — noted here and in the open items below.

## Data flow, end to end (backend/ case)

```
Student talks to backend/'s Live voice loop (unchanged)
  → TutorAgent calls log_turn(...) → short_term.append_turn (now decorated)
    publishes a MemoryEvent{tier: workflow, operation: write,
    record_type: turn_buffer, trace_id: null}
  → smriti-observatory/backend's ingest loop receives it over
    smriti:events:live, broadcasts to any WS client watching this session_id
  → smriti-observatory/frontend already has this session auto-selected
    (§4) → Workflow TierPanel appends a new turn card live

WebSocket disconnects → backend/main.py's finally block runs (unchanged)
  → _flush_session_memory: set_session_context(session_id) (NEW). then
    asyncio.to_thread(_flush) → close_session(...) → put_session_log
    (decorated, tier: episodic) fires one event; reflect() proposes ops;
    apply_operations → put_dpm/put_teaching_memory (decorated, tier:
    long_term, session_id from the context var) fire events
  → Observatory's ingest loop diffs the new DPMProfile against its cached
    previous value (primed via §3's direct Firestore read), broadcasts
    {event, diff}
  → frontend's Episodic panel renders the full turn ledger for the first
    time; Long-term panel shows e.g. a mastery-badge diff transition
```

## Prerequisites to actually see Firestore-backed tiers

`backend/`'s own `NITYAM_STORE` env var must be `firestore` (not the default
`sqlite`) for Episodic/Long-term data to exist anywhere the Observatory's
direct Firestore reads can see it — the Working tier (Redis turn buffer)
works under either, since `short_term.py` always uses Redis regardless of
`NITYAM_STORE`. This is not a new requirement invented by this document: it
is exactly the already-documented real-credentials run mode
`MEMORY_VALIDATION_GUIDE.md` §0 already describes ("confirm your real
credentials are set... `NITYAM_AUTH=vertex_express`"), stated here
explicitly because it's load-bearing for this feature specifically.

## Testing

Matches this repo's established "real Firestore + local Redis, skip (not
fail) if unreachable" convention:

- `backend/tests/` — a new test mirroring `sub_modules_examples/tutor`'s
  own instrumentation tests: decorated `store.py`/`short_term.py` functions
  still return exactly what they returned before (existing tests keep
  passing unmodified, confirmed by running the existing suite after the
  change, not just asserted); a focused test that a `put_dpm` call while
  `set_session_context(...)` is active publishes a `MemoryEvent` with that
  `session_id` on a real local Redis.
- `backend/tests/` — `memory_routes.py`'s two new endpoints: happy path,
  missing session/student, `trace_id` filter — same style as
  `sub_modules_examples/tutor`'s `test_routes_rest.py`-equivalent.
- `smriti-observatory/backend/tests/` — `test_ingest.py`/`test_diff.py`/
  `test_snapshot_cache.py`/`test_trace_links.py` re-run unmodified (none of
  them import `app.*`, confirmed by grep). `test_routes_rest.py`/
  `test_main.py`/`conftest.py`/`test_events.py` get the specific,
  intentional updates §3 already describes (dict-based seeding instead of
  typed schema classes, a wire-compatibility test instead of a
  same-class-identity one) — `test_end_to_end.py` is the one file that
  keeps its tutor-specific imports on purpose. One new test pointing
  `build_router(...)` at a fake `agent_base_url` (a local `httpx` mock or a
  bare FastAPI test app standing in for `backend/`) to confirm the proxy
  path works with no `app.*` import present in the router itself.
- **End-to-end acceptance** (the real proof): run `backend/` locally with
  `NITYAM_STORE=firestore`, `NITYAM_AUTH=mock` (per its own existing mock
  mode) or real credentials, drive a session via `scripts/drive.py` (the
  existing smoke-test script), open `smriti-observatory/frontend` with
  `VITE_TUTOR_BASE_URL` pointed at `backend/`'s port, and confirm: it's
  already showing the session with no click, the Workflow panel fills live
  turn by turn, and after the script's connection ends, the Episodic panel
  renders the full ledger and the Long-term panel shows a real diff —
  cross-checked directly against Firestore console state, not just the UI.
  Per this project's standing rule for UI work, this is a real dev-server
  run exercised in an actual browser, not just unit tests passing.

## Open items, explicitly flagged

1. **Exact `extract_ids` implementations for `store.py`'s six wrapped
   functions** — the pattern is settled (§1), the six small
   argument-shape-specific extractors are implementation-plan detail, not
   designed line-by-line here (mirrors how `sub_modules_examples/tutor`'s
   own `instrumentation.py` handles this per-function, not generically).
2. **Poll interval (4s, §4)** — a reasonable starting value for "feels
   live" without meaningfully loading a local dev server; not derived from
   a specific requirement, easy to tune if it ever matters.
3. **The "Open in ADK web" link 404ing against `backend/` (§4)** — deferred
   rather than fixed: hiding it correctly needs a real "does this agent
   server expose a dev-ui" signal plumbed through `/api/health`, which is
   separable, low-value plumbing for one dead link with zero effect on
   memory visualization itself. Worth doing if it proves confusing in
   practice, not required for this feature to work.
4. This document does not touch, and is not blocked by,
   `sub_modules_examples/tutor` + `smriti-observatory/adk-web` in any way —
   confirmed no shared files between the two efforts other than the (now
   removed, §3) `tutor` path dependency.
