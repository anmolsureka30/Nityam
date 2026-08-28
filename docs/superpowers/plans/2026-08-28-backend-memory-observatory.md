# Live Memory Visualization for `backend/` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `smriti-observatory/frontend` show the real production
tutor's (`backend/`'s) memory tiers — Working/Episodic/Long-term — live and
auto-selected, with zero manual session picking, while leaving `backend/`'s
WebSocket/session-close path and `sub_modules_examples/tutor` + ADK web
completely untouched.

**Architecture:** Port the already-proven `emit_memory_event` Redis
instrumentation pattern from `sub_modules_examples/tutor` onto `backend/`'s
memory layer (additive, fire-and-forget, never raises); add two read-only
GET endpoints to `backend/`'s own FastAPI app; decouple
`smriti-observatory/backend`'s production code from its `tutor`
path-dependency so it can point at either agent server over plain HTTP; add
auto-select-the-live-session to `smriti-observatory/frontend`.

**Tech Stack:** Python 3.11+/FastAPI/redis.asyncio/google-cloud-firestore
(backend/, smriti-observatory/backend), TypeScript/React 19/Vite
(smriti-observatory/frontend).

**Spec:** `docs/superpowers/specs/2026-08-28-backend-memory-observatory-design.md`

## Global Constraints

- Every change to `backend/app/` is additive/read-only — no modification to
  the WebSocket connection lifecycle, auth path, or the existing
  `close_session` call site's control flow (only one new line inside
  `close_session` itself, §Task 4).
- The instrumentation decorator must never raise and must never change a
  wrapped function's return value — every existing test in `backend/tests/`
  must keep passing unmodified after each task.
- `sub_modules_examples/tutor` and `smriti-observatory/adk-web` are not
  touched by any task in this plan.
- `backend/tests/` convention: standalone scripts with a global `check(name,
  ok, extra)` counter, run via `.venv/bin/python -m tests.test_x`, real
  Redis/Firestore, no mocks, no FastAPI `TestClient` (confirmed: this
  convention is used with zero exceptions across the existing suite).
- `smriti-observatory/backend/tests/` convention: pytest, `firestore_db`/
  `redis_client` fixtures that skip (not fail) when unreachable.
- `MemoryEvent`'s wire shape must stay byte-identical to
  `sub_modules_examples/tutor/app/memory/instrumentation.py`'s fields
  (`event_id, ts, session_id, student_id, tier, operation, record_type,
  source_fn, trace_id, span_id, payload`) — both apps' events flow through
  the same `smriti-observatory/backend` ingest code.

---

### Task 1: `backend/app/memory/instrumentation.py`

**Files:**
- Create: `backend/app/memory/instrumentation.py`
- Test: `backend/tests/test_memory_instrumentation.py`

**Interfaces:**
- Produces: `emit_memory_event(tier, record_type, operation, extract_ids)`
  (decorator factory), `set_session_context(session_id: str | None) -> None`,
  `get_session_context() -> str | None`, `MemoryEvent` (pydantic model).
  Every later task imports these from `app.memory.instrumentation`.

This is a direct port of `sub_modules_examples/tutor/app/memory/
instrumentation.py` — same fields, same Redis keys, same fire-and-forget
contract. Only the module path changes (`app.memory.instrumentation` inside
`backend/`, a sibling package to `backend/app/memory/store.py`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_memory_instrumentation.py
"""The instrumentation decorator publishes a MemoryEvent to Redis without
changing what the wrapped function returns, and never raises even if Redis
is unreachable.

Needs a local Redis on localhost:6379 (`redis-server --daemonize yes`).

    .venv/bin/python -m tests.test_memory_instrumentation
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid

from app.auth import load_env

load_env()

import redis as redis_sync  # noqa: E402

from app import config  # noqa: E402
from app.memory import instrumentation  # noqa: E402

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


def _ids(args, kwargs, result):
    return args[0], args[1]


@instrumentation.emit_memory_event(
    tier="workflow", record_type="turn_buffer", operation="write", extract_ids=_ids,
)
def _sample_write(session_id: str, student_id: str, value: int) -> int:
    return value * 2


async def run() -> None:
    client = redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
    client.delete("smriti:events:recent")

    session_id = f"test_instr_{uuid.uuid4().hex[:8]}"
    result = _sample_write(session_id, "demo_student", 21)
    check("the wrapped function's return value is unchanged", result == 42, repr(result))

    raw = client.lrange("smriti:events:recent", 0, -1)
    check("exactly one event was published", len(raw) == 1, repr(raw))
    if raw:
        event = json.loads(raw[0])
        check("session_id round-trips", event["session_id"] == session_id, event["session_id"])
        check("student_id round-trips", event["student_id"] == "demo_student", event["student_id"])
        check("tier/record_type/operation are set", (
            event["tier"] == "workflow" and event["record_type"] == "turn_buffer" and event["operation"] == "write"
        ), repr(event))

    instrumentation.set_session_context("ctx_session_1")
    check("session context round-trips", instrumentation.get_session_context() == "ctx_session_1")
    instrumentation.set_session_context(None)

    client.delete("smriti:events:recent")


def main() -> int:
    asyncio.run(run())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m tests.test_memory_instrumentation`
Expected: `ModuleNotFoundError: No module named 'app.memory.instrumentation'`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/memory/instrumentation.py
"""Publishes a structured MemoryEvent to Redis for every persisted memory
operation, so an external observer (the SMRITI Observatory) can watch
memory tiers change in real time without touching store.py/short_term.py's
own logic. Fire-and-forget: a Redis hiccup here must never break a real
memory write. One global channel/list, not per-session — some store.py
functions (get_dpm, put_dpm, get_teaching_memory, put_teaching_memory)
never receive a session_id at all, and a per-session scheme would silently
drop them.

Direct port of sub_modules_examples/tutor/app/memory/instrumentation.py —
same wire shape, same Redis keys — so smriti-observatory/backend's ingest
loop can decode events from either app identically. See
docs/superpowers/specs/2026-08-28-backend-memory-observatory-design.md.
"""
from __future__ import annotations

import contextvars
import functools
import inspect
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Literal

import redis as redis_sync
import redis.asyncio as redis_async
from opentelemetry import trace
from pydantic import BaseModel

from app import config

_CHANNEL = "smriti:events:live"
_LIST_KEY = "smriti:events:recent"
_LIST_CAP = 2000

Tier = Literal["workflow", "episodic", "long_term"]
Operation = Literal["read", "write"]
RecordType = Literal[
    "grounding_chunk", "dpm_profile", "teaching_memory",
    "session_log", "turn_buffer", "artifact_event",
]

_session_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "smriti_session_id", default=None
)


def set_session_context(session_id: str | None) -> None:
    """Set the session id long-term-tier writes should carry when their own
    arguments don't include one (only session_close.py calls this)."""
    _session_ctx.set(session_id)


def get_session_context() -> str | None:
    return _session_ctx.get()


class MemoryEvent(BaseModel):
    event_id: str
    ts: str
    session_id: str | None
    student_id: str | None
    tier: Tier
    operation: Operation
    record_type: RecordType
    source_fn: str
    trace_id: str | None
    span_id: str | None
    payload: Any = None


_sync_client: redis_sync.Redis | None = None


def _get_sync_client() -> redis_sync.Redis:
    global _sync_client
    if _sync_client is None:
        _sync_client = redis_sync.Redis(
            host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True
        )
    return _sync_client


def _current_trace_ids() -> tuple[str | None, str | None]:
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return None, None
    return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")


def _to_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    return value


def _payload_source(operation: Operation, args: tuple, result: Any) -> Any:
    """Write functions (put_dpm, put_teaching_memory, put_session_log,
    put_grounding_chunk, append_turn, append_artifact_event) all return
    None or an ack — the data actually written is the object passed in.
    By convention every one of these takes the connection/session id as
    args[0] and the written object/dict as args[1]. Reads use the return
    value as-is (including a legitimate None for "not found")."""
    if operation == "read":
        return result
    return args[1] if len(args) > 1 else result


def _build_event(
    tier: Tier, record_type: RecordType, operation: Operation, fn_name: str,
    session_id: str | None, student_id: str | None, payload_source: Any,
) -> MemoryEvent:
    trace_id, span_id = _current_trace_ids()
    return MemoryEvent(
        event_id=str(uuid.uuid4()),
        ts=datetime.now(timezone.utc).isoformat(),
        session_id=session_id,
        student_id=student_id,
        tier=tier,
        operation=operation,
        record_type=record_type,
        source_fn=fn_name,
        trace_id=trace_id,
        span_id=span_id,
        payload=_to_jsonable(payload_source),
    )


def _publish_sync(event: MemoryEvent) -> None:
    try:
        client = _get_sync_client()
        body = event.model_dump_json()
        client.publish(_CHANNEL, body)
        client.rpush(_LIST_KEY, body)
        client.ltrim(_LIST_KEY, -_LIST_CAP, -1)
    except Exception:
        pass


async def _publish_async(event: MemoryEvent) -> None:
    try:
        client = redis_async.Redis(
            host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True
        )
        body = event.model_dump_json()
        await client.publish(_CHANNEL, body)
        await client.rpush(_LIST_KEY, body)
        await client.ltrim(_LIST_KEY, -_LIST_CAP, -1)
        await client.aclose()
    except Exception:
        pass


def emit_memory_event(
    tier: Tier,
    record_type: RecordType,
    operation: Operation,
    extract_ids: Callable[[tuple, dict, Any], tuple[str | None, str | None]],
):
    """extract_ids(args, kwargs, result) -> (session_id, student_id)."""
    def decorator(fn):
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                result = await fn(*args, **kwargs)
                try:
                    session_id, student_id = extract_ids(args, kwargs, result)
                    event = _build_event(
                        tier, record_type, operation, fn.__name__, session_id, student_id,
                        _payload_source(operation, args, result),
                    )
                    await _publish_async(event)
                except Exception:
                    pass
                return result
            return async_wrapper
        else:
            @functools.wraps(fn)
            def sync_wrapper(*args, **kwargs):
                result = fn(*args, **kwargs)
                try:
                    session_id, student_id = extract_ids(args, kwargs, result)
                    event = _build_event(
                        tier, record_type, operation, fn.__name__, session_id, student_id,
                        _payload_source(operation, args, result),
                    )
                    _publish_sync(event)
                except Exception:
                    pass
                return result
            return sync_wrapper
    return decorator
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m tests.test_memory_instrumentation`
Expected: `all passed` (0 FAIL lines) — requires local Redis running
(`redis-cli ping` → `PONG`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/memory/instrumentation.py backend/tests/test_memory_instrumentation.py
git commit -m "feat: add memory-event instrumentation to backend/ (Redis, fire-and-forget)"
```

---

### Task 2: Instrument `backend/app/memory/store.py`

**Files:**
- Modify: `backend/app/memory/store.py`
- Test: `backend/tests/test_memory_store_events.py`

**Interfaces:**
- Consumes: `emit_memory_event`, `get_session_context` from Task 1's
  `app.memory.instrumentation`.
- Produces: same six re-exported names as before (`put_dpm`, `get_dpm`,
  `put_teaching_memory`, `get_teaching_memory`, `put_session_log`,
  `get_session_log`), now each individually wrapped — callers in
  `app/memory/tools.py`/`app/session_close.py` see no signature or behavior
  change. Also wraps `put_grounding_chunk`/`search_grounding` (parity with
  the tutor's real, current `store.py`, confirmed by direct read).

`store.py` re-exports functions from whichever backend `_impl` resolves to
(`store_sqlite` or `store_firestore`) — wrapping happens at this dispatch
point so instrumentation works under both backends with one set of call
sites, not two.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_memory_store_events.py
"""put_dpm/get_dpm/put_teaching_memory/get_teaching_memory/put_session_log/
get_session_log each publish exactly one correctly-shaped MemoryEvent, and
put_dpm/put_teaching_memory pick up session_id from the context var since
neither function receives one directly.

Needs local Redis + real Firestore credentials (NITYAM_STORE=firestore,
real ADC) OR NITYAM_STORE=sqlite (instrumentation fires either way — only
the underlying storage differs).

    .venv/bin/python -m tests.test_memory_store_events
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid

from app.auth import load_env

load_env()

import redis as redis_sync  # noqa: E402

from app import config  # noqa: E402
from app.memory import instrumentation, store  # noqa: E402
from app.memory.schemas import DPMProfile  # noqa: E402

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


async def run() -> None:
    client = redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
    client.delete("smriti:events:recent")

    student_id = f"test_store_events_{uuid.uuid4().hex[:8]}"
    conn = store.connect()

    instrumentation.set_session_context("ctx_for_put_dpm")
    store.put_dpm(conn, DPMProfile(student_id=student_id))
    instrumentation.set_session_context(None)
    store.get_dpm(conn, student_id)

    raw = client.lrange("smriti:events:recent", 0, -1)
    events = [json.loads(r) for r in raw]
    write_events = [e for e in events if e["source_fn"] == "put_dpm"]
    read_events = [e for e in events if e["source_fn"] == "get_dpm"]

    check("put_dpm published one write event", len(write_events) == 1, repr(write_events))
    if write_events:
        check("put_dpm's event carries the context session_id", write_events[0]["session_id"] == "ctx_for_put_dpm")
        check("put_dpm's event carries the real student_id", write_events[0]["student_id"] == student_id)
        check("put_dpm's event tier/record_type", write_events[0]["tier"] == "long_term" and write_events[0]["record_type"] == "dpm_profile")

    check("get_dpm published one read event", len(read_events) == 1, repr(read_events))
    if read_events:
        check("get_dpm's event has no session_id (context was cleared)", read_events[0]["session_id"] is None)
        check("get_dpm's event carries the real student_id", read_events[0]["student_id"] == student_id)

    conn.collection("dpm_profiles").document(student_id).delete() if hasattr(conn, "collection") else None
    client.delete("smriti:events:recent")


def main() -> int:
    asyncio.run(run())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m tests.test_memory_store_events`
Expected: FAIL — "put_dpm published one write event" (0 events published,
since `store.py` doesn't wrap anything yet).

- [ ] **Step 3: Modify `backend/app/memory/store.py`**

Add after the existing `BACKEND = os.getenv(...)` / `_impl` import block,
replacing the plain re-export lines with wrapped ones:

```python
from app.memory import instrumentation


def _ids_student_from_arg1(args, kwargs, result):
    student_id = kwargs.get("student_id", args[1] if len(args) > 1 else None)
    return instrumentation.get_session_context(), student_id


def _ids_from_profile(args, kwargs, result):
    profile = kwargs.get("profile", args[1] if len(args) > 1 else None)
    return instrumentation.get_session_context(), getattr(profile, "student_id", None)


def _ids_from_memory(args, kwargs, result):
    memory = kwargs.get("memory", args[1] if len(args) > 1 else None)
    return instrumentation.get_session_context(), getattr(memory, "student_id", None)


def _ids_from_log(args, kwargs, result):
    log = kwargs.get("log", args[1] if len(args) > 1 else None)
    return getattr(log, "session_id", None), getattr(log, "student_id", None)


def _ids_session_from_arg1(args, kwargs, result):
    session_id = kwargs.get("session_id", args[1] if len(args) > 1 else None)
    return session_id, None


def _ids_none(args, kwargs, result):
    return None, None


def _ids_context_session_only(args, kwargs, result):
    return instrumentation.get_session_context(), None


connect = _impl.connect
put_grounding_chunk = instrumentation.emit_memory_event(
    "long_term", "grounding_chunk", "write", _ids_none,
)(_impl.put_grounding_chunk)
search_grounding = instrumentation.emit_memory_event(
    "long_term", "grounding_chunk", "read", _ids_context_session_only,
)(_impl.search_grounding)
get_dpm = instrumentation.emit_memory_event(
    "long_term", "dpm_profile", "read", _ids_student_from_arg1,
)(_impl.get_dpm)
put_dpm = instrumentation.emit_memory_event(
    "long_term", "dpm_profile", "write", _ids_from_profile,
)(_impl.put_dpm)
get_teaching_memory = instrumentation.emit_memory_event(
    "long_term", "teaching_memory", "read", _ids_student_from_arg1,
)(_impl.get_teaching_memory)
put_teaching_memory = instrumentation.emit_memory_event(
    "long_term", "teaching_memory", "write", _ids_from_memory,
)(_impl.put_teaching_memory)
put_session_log = instrumentation.emit_memory_event(
    "episodic", "session_log", "write", _ids_from_log,
)(_impl.put_session_log)
get_session_log = instrumentation.emit_memory_event(
    "episodic", "session_log", "read", _ids_session_from_arg1,
)(_impl.get_session_log)
```

Leave the `#: Firestore-only extras` block (`search_grounding_semantic`,
`list_concept_ids`) and everything below it unchanged — the design's
non-goals don't require instrumenting those, and `search_grounding_semantic`
is `getattr`-guarded specifically so the sqlite path degrades, which an
unconditional wrap would break for the `None` case.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m tests.test_memory_store_events`
Expected: `all passed`

- [ ] **Step 5: Run the full existing backend suite to confirm no regressions**

Run: `cd backend && for t in tests/test_*.py; do .venv/bin/python -m "${t%.py}" | tr '/' '.'; done`
(or run each existing test module individually per its own docstring
invocation) — every test that passed before this task must still pass.
Expected: no new failures relative to the pre-task baseline.

- [ ] **Step 6: Commit**

```bash
git add backend/app/memory/store.py backend/tests/test_memory_store_events.py
git commit -m "feat: instrument backend/'s store.py with memory-event publishing"
```

---

### Task 3: Instrument `backend/app/memory/short_term.py`

**Files:**
- Modify: `backend/app/memory/short_term.py`
- Test: `backend/tests/test_short_term_events.py`

**Interfaces:**
- Consumes: `emit_memory_event` from Task 1.
- Produces: same four function names (`append_turn`, `append_artifact_event`,
  `get_turn_buffer`, `clear_session`), same signatures
  (`(session_id, student_id, ...)`), now each wrapped. `backend/app/memory/
  tools.py` and `backend/app/main.py`'s call sites need no changes.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_short_term_events.py
"""append_turn/append_artifact_event/get_turn_buffer/clear_session each
publish a workflow-tier MemoryEvent, carrying the real session_id/student_id
straight from their own arguments (no context var needed here).

    .venv/bin/python -m tests.test_short_term_events
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid

from app.auth import load_env

load_env()

import redis as redis_sync  # noqa: E402

from app import config  # noqa: E402
from app.memory import short_term  # noqa: E402

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


async def run() -> None:
    client = redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
    client.delete("smriti:events:recent")

    session_id = f"test_short_term_events_{uuid.uuid4().hex[:8]}"
    student_id = "demo_student"

    await short_term.append_turn(session_id, student_id, {"turn": 1, "role": "student", "text": "hi", "concept_id": None, "artifact_id": None})
    await short_term.get_turn_buffer(session_id, student_id)
    await short_term.clear_session(session_id, student_id)

    raw = client.lrange("smriti:events:recent", 0, -1)
    events = [json.loads(r) for r in raw]
    by_fn = {e["source_fn"]: e for e in events}

    check("append_turn published a workflow write event", "append_turn" in by_fn, list(by_fn))
    check("get_turn_buffer published a workflow read event", "get_turn_buffer" in by_fn, list(by_fn))
    check("clear_session published a workflow write event", "clear_session" in by_fn, list(by_fn))
    if "append_turn" in by_fn:
        e = by_fn["append_turn"]
        check("append_turn's event carries the real session/student ids", (
            e["session_id"] == session_id and e["student_id"] == student_id
        ), repr(e))

    client.delete("smriti:events:recent")


def main() -> int:
    asyncio.run(run())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m tests.test_short_term_events`
Expected: FAIL — none of the three functions have published anything yet.

- [ ] **Step 3: Modify `backend/app/memory/short_term.py`**

Add the import and decorate the four functions in place (signatures and
bodies unchanged):

```python
from app.memory import instrumentation


def _ids_from_args01(args, kwargs, result):
    session_id = kwargs.get("session_id", args[0] if len(args) > 0 else None)
    student_id = kwargs.get("student_id", args[1] if len(args) > 1 else None)
    return session_id, student_id


@instrumentation.emit_memory_event(
    tier="workflow", record_type="turn_buffer", operation="write", extract_ids=_ids_from_args01,
)
async def append_turn(session_id: str, student_id: str, turn: dict) -> None:
    ...  # body unchanged


@instrumentation.emit_memory_event(
    tier="workflow", record_type="artifact_event", operation="write", extract_ids=_ids_from_args01,
)
async def append_artifact_event(session_id: str, student_id: str, event: dict) -> None:
    ...  # body unchanged


@instrumentation.emit_memory_event(
    tier="workflow", record_type="turn_buffer", operation="read", extract_ids=_ids_from_args01,
)
async def get_turn_buffer(session_id: str, student_id: str) -> list[dict]:
    ...  # body unchanged


@instrumentation.emit_memory_event(
    tier="workflow", record_type="turn_buffer", operation="write", extract_ids=_ids_from_args01,
)
async def clear_session(session_id: str, student_id: str) -> None:
    ...  # body unchanged
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m tests.test_short_term_events`
Expected: `all passed`

- [ ] **Step 5: Re-run `test_short_term_writethrough.py` to confirm no regression**

Run: `cd backend && .venv/bin/python -m tests.test_short_term_writethrough`
Expected: `all passed`, unchanged from before this task (proves the
decorator is a transparent pass-through for the real call sites in
`app/agents/brain.py`/`app/memory/tools.py`).

- [ ] **Step 6: Commit**

```bash
git add backend/app/memory/short_term.py backend/tests/test_short_term_events.py
git commit -m "feat: instrument backend/'s short_term.py with memory-event publishing"
```

---

### Task 4: Wire session context into `close_session`

**Files:**
- Modify: `backend/app/session_close.py:162-181` (the `close_session`
  function itself)
- Test: `backend/tests/test_session_close_events.py`

**Interfaces:**
- Consumes: `instrumentation.set_session_context` (Task 1),
  `store.put_dpm`/`get_dpm`/`put_teaching_memory`/`get_teaching_memory`/
  `put_session_log` (Task 2, already instrumented).
- Produces: no change to `close_session`'s signature or return value —
  every long-term write it triggers now carries the real `session_id` on
  its `MemoryEvent`, not `null`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_session_close_events.py
"""close_session's own long-term writes (put_dpm/put_teaching_memory/
put_session_log) carry the real session_id on their MemoryEvents — the one
gap none of the four DPM/TeachingMemory store functions can close on their
own, since neither function receives a session_id directly.

Needs real Gemini credentials (this calls the real reflect() LLM call) —
same requirement as test_close_session_wiring.py.

    NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_session_close_events
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone

from app.auth import load_env

load_env()

import redis as redis_sync  # noqa: E402
from google import genai  # noqa: E402

from app import config  # noqa: E402
from app.memory import store  # noqa: E402
from app.session_close import close_session  # noqa: E402

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


def main() -> int:
    mode = os.getenv("NITYAM_AUTH", "").strip().lower()
    if mode in ("", "mock"):
        print("NITYAM_AUTH is mock or unset — nothing to test against. Skipping.")
        return 0

    client = redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
    client.delete("smriti:events:recent")

    session_id = f"test_session_close_events_{uuid.uuid4().hex[:8]}"
    student_id = f"test_student_{uuid.uuid4().hex[:8]}"
    buffer = [
        {"turn": 1, "role": "student", "text": "why 45 degrees?", "concept_id": "projectile.range", "artifact_id": None},
        {"turn": 2, "role": "tutor", "text": "because sin(2θ) peaks there", "concept_id": "projectile.range", "artifact_id": None},
    ]
    conn = store.connect()
    close_session(conn, session_id, student_id, datetime.now(timezone.utc), buffer, genai.Client())

    raw = client.lrange("smriti:events:recent", 0, -1)
    events = [json.loads(r) for r in raw]
    long_term_writes = [e for e in events if e["tier"] == "long_term" and e["operation"] == "write"]

    check("close_session produced at least one long-term write event", len(long_term_writes) >= 1, repr(long_term_writes))
    for e in long_term_writes:
        check(f"{e['source_fn']}'s event carries the real session_id", e["session_id"] == session_id, repr(e))

    client.delete("smriti:events:recent")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_session_close_events`
Expected: FAIL — long-term write events exist (Task 2 wired that) but their
`session_id` is `null`, not the real session id.

- [ ] **Step 3: Modify `backend/app/session_close.py`**

```python
# backend/app/session_close.py — add the import, and one line at the top
# of close_session (line ~162):
from app.memory import instrumentation


def close_session(
    conn: sqlite3.Connection,
    session_id: str,
    student_id: str,
    started_at: datetime,
    buffer: list[dict],
    client: genai.Client,
) -> SessionLog:
    instrumentation.set_session_context(session_id)
    log = build_session_log(session_id, student_id, started_at, buffer)
    store.put_session_log(conn, log)
    ...  # rest of the function unchanged
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_session_close_events`
Expected: `all passed` (note: makes one real Gemini call and writes to the
test student's Firestore record, same cost profile as
`test_close_session_wiring.py`).

- [ ] **Step 5: Re-run `test_close_session_wiring.py` and `test_session_close.py` to confirm no regression**

Run: `cd backend && NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_close_session_wiring`
Run: `cd backend && .venv/bin/python -m tests.test_session_close`
Expected: both `all passed`, unchanged from before this task.

- [ ] **Step 6: Commit**

```bash
git add backend/app/session_close.py backend/tests/test_session_close_events.py
git commit -m "feat: carry the real session_id onto close_session's long-term memory events"
```

---

### Task 5: Read-only memory endpoints on `backend/`'s own server

**Files:**
- Create: `backend/app/memory_routes.py`
- Modify: `backend/app/main.py` (mount the router; no other change)
- Test: `backend/tests/test_memory_routes.py`

**Interfaces:**
- Consumes: `app.memory.store`, `app.memory.short_term` (unchanged public
  API from the caller's perspective).
- Produces: `GET /memory/sessions/{session_id}/state?student_id=...` and
  `GET /memory/sessions/{session_id}/events?student_id=...&trace_id=...`,
  same JSON shape as `sub_modules_examples/tutor/app/app_utils/
  memory_routes.py` — this is what Task 7's Observatory proxy calls.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_memory_routes.py
"""GET /memory/sessions/{id}/state and /events, served directly by
backend/'s own FastAPI app — same shape as
sub_modules_examples/tutor/app/app_utils/memory_routes.py, over real HTTP
against a spawned server (this repo's own convention — see
test_close_session_wiring.py), not FastAPI's in-process TestClient.

    .venv/bin/python -m tests.test_memory_routes
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

from app.auth import load_env  # noqa: E402

load_env()

import redis as redis_sync  # noqa: E402

from app import config  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    def __init__(self, port: int) -> None:
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        self.proc = subprocess.Popen(
            [str(ROOT / ".venv/bin/uvicorn"), "app.main:app",
             "--port", str(port), "--log-level", "warning"],
            cwd=ROOT, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        self.port = port

    def wait(self, timeout: float = 30) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                print(self.proc.stdout.read()[-2000:])
                return False
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=1) as r:
                    if r.status == 200:
                        return True
            except Exception:
                time.sleep(0.3)
        return False

    def stop(self) -> None:
        self.proc.kill()
        self.proc.wait(timeout=5)


def main() -> int:
    port = free_port()
    session_id = f"test_memory_routes_{uuid.uuid4().hex[:8]}"
    student_id = "demo_student"

    redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True).rpush(
        f"session:{student_id}:{session_id}:turns",
        json.dumps({"turn": 1, "role": "student", "text": "hi", "concept_id": None, "artifact_id": None}),
    )

    server = Server(port)
    try:
        if not server.wait():
            check("the server starts", False, "it did not come up")
            return 1
        check("the server starts", True)

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/memory/sessions/{session_id}/state?student_id={student_id}"
        ) as r:
            body = json.loads(r.read())
        check("state endpoint returns the workflow turn buffer", len(body["workflow"]["turn_buffer"]) == 1, repr(body))
        check("state endpoint echoes session/student ids", (
            body["session_id"] == session_id and body["student_id"] == student_id
        ), repr(body))

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/memory/sessions/{session_id}/events?student_id={student_id}"
        ) as r:
            events_body = json.loads(r.read())
        check("events endpoint responds with an events list", "events" in events_body, repr(events_body))
    finally:
        server.stop()
        redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True).delete(
            f"session:{student_id}:{session_id}:turns"
        )

    print()
    print(f"{FAILED} failed" if FAILED else "all passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m tests.test_memory_routes`
Expected: HTTP 404 on both new routes (they don't exist yet).

- [ ] **Step 3: Write `backend/app/memory_routes.py`**

```python
"""Read-only memory endpoints on backend/'s own FastAPI server — the same
shape as sub_modules_examples/tutor/app/app_utils/memory_routes.py's two
GET routes, so smriti-observatory/backend can proxy to either agent server
identically (see docs/superpowers/specs/2026-08-28-backend-memory-observatory-design.md).

No POST /close endpoint here: unlike the tutor scaffold, backend/'s own
_flush_session_memory (app/main.py) already calls the real close_session on
every WebSocket teardown — there's no missing trigger to add.
"""
from __future__ import annotations

import functools

import redis as redis_sync
from fastapi import APIRouter

from app import config
from app.memory import short_term, store
from app.memory.diff import diff_dpm, diff_teaching_memory
from app.memory.instrumentation import MemoryEvent

router = APIRouter(prefix="/memory")


@functools.cache
def _firestore_client():
    return store.connect()


@router.get("/sessions/{session_id}/state")
async def session_state_endpoint(session_id: str, student_id: str):
    db = _firestore_client()
    profile = store.get_dpm(db, student_id)
    memory = store.get_teaching_memory(db, student_id)
    session_log = store.get_session_log(db, session_id)
    turn_buffer = await short_term.get_turn_buffer(session_id, student_id)
    return {
        "session_id": session_id,
        "student_id": student_id,
        "workflow": {"turn_buffer": turn_buffer},
        "episodic": {"session_log": session_log.model_dump(mode="json") if session_log else None},
        "long_term": {
            "dpm_profile": profile.model_dump(mode="json") if profile else None,
            "teaching_memory": memory.model_dump(mode="json") if memory else None,
        },
    }


def _read_recent_events(session_id: str) -> list[MemoryEvent]:
    try:
        client = redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
        raw_events = client.lrange("smriti:events:recent", 0, -1)
    except Exception:
        return []
    events = [MemoryEvent.model_validate_json(raw) for raw in raw_events]
    return [e for e in events if e.session_id == session_id]


@router.get("/sessions/{session_id}/events")
async def session_events_endpoint(session_id: str, student_id: str, trace_id: str | None = None):
    events = _read_recent_events(session_id)
    if trace_id:
        events = [e for e in events if e.trace_id == trace_id]
    return {"events": [e.model_dump(mode="json") for e in events]}
```

Note: unlike `sub_modules_examples/tutor`'s version, this does not compute
before/after diffs server-side (`_replay_diffs`) — `backend/`'s
`smriti-observatory/backend` consumer already computes diffs itself in
`observatory/ingest.py`/`diff.py` for the live WebSocket path (Task 6), and
the `/events` REST read here is only used for the initial backlog fetch
(`SessionView.tsx`'s mount-time fetch), which renders with `diff: []` today
(confirmed: `SessionView.tsx`'s existing events-fetch already maps
`{ event, diff: [] }`) — so no new diff logic is required to match current
frontend behavior. `diff_dpm`/`diff_teaching_memory` are imported for
parity/future use but not yet called; if left unused, drop the import
rather than leave a lint warning.

- [ ] **Step 4: Modify `backend/app/main.py`**

Add near the other route/router registrations (find the existing
`app = FastAPI(title="Nityam backend")` line and the `@app.websocket(...)`
below it):

```python
from app.memory_routes import router as memory_router
...
app.include_router(memory_router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m tests.test_memory_routes`
Expected: `all passed`

- [ ] **Step 6: Commit**

```bash
git add backend/app/memory_routes.py backend/app/main.py backend/tests/test_memory_routes.py
git commit -m "feat: add read-only /memory/sessions/{id}/state and /events to backend/"
```

---

### Task 6: Decouple `smriti-observatory/backend` from the `tutor` package

**Files:**
- Modify: `smriti-observatory/backend/observatory/events.py`
- Modify: `smriti-observatory/backend/observatory/main.py`
- Modify: `smriti-observatory/backend/observatory/routes_rest.py`
- Modify: `smriti-observatory/backend/tests/conftest.py`
- Modify: `smriti-observatory/backend/tests/test_routes_rest.py`
- Modify: `smriti-observatory/backend/tests/test_events.py`
- Modify: `smriti-observatory/backend/pyproject.toml`
- Test: existing pytest suite, run after each change (this task is a
  refactor — the test *behavior* it must satisfy already exists; the work
  is making it pass without the `app.*` import).

**Interfaces:**
- Produces: `observatory.events.MemoryEvent` — now a locally-declared model
  (same fields as `app.memory.instrumentation.MemoryEvent`), not an import.
  `build_router(tutor_base_url, redis_host, redis_port)` — `routes_rest.py`'s
  `build_router` gains two new required params (previously read
  `app.config.REDIS_HOST`/`REDIS_PORT` directly). `observatory.main`'s
  `get_dpm`/`get_teaching_memory` callables now come from a local Firestore
  read, not `app.memory.store`.
- `test_end_to_end.py` is explicitly **not** touched by this task — it keeps
  its own direct `sub_modules_examples/tutor` imports on purpose.

This task is best done as one atomic change (all six production/test files
together) since `routes_rest.py`'s new `build_router` signature and
`main.py`'s call to it must agree — a partial edit leaves the app unable to
start.

- [ ] **Step 1: Confirm today's baseline passes**

Run: `cd smriti-observatory/backend && uv run pytest -q` (requires local
Redis + `gcloud auth application-default login` against `nityam-506707`,
per this package's own `.env.example`/README — fixtures skip cleanly if
unreachable). Record which tests pass today, before any change, so Step 6
has something concrete to compare against.

- [ ] **Step 2: Rewrite `observatory/events.py`**

```python
"""MemoryEvent — a local re-declaration of the same wire shape
sub_modules_examples/tutor's (and backend/'s) app.memory.instrumentation.
MemoryEvent publishes. Deliberately not imported from either app's package:
this service can point at either one purely via config (AGENT_BASE_URL/
REDIS_HOST), and importing one specific app's `app` package here would
prevent it from ever pointing at the other (both ship a top-level module
literally named `app`). See docs/superpowers/specs/
2026-08-28-backend-memory-observatory-design.md §3.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

Tier = Literal["workflow", "episodic", "long_term"]
Operation = Literal["read", "write"]
RecordType = Literal[
    "grounding_chunk", "dpm_profile", "teaching_memory",
    "session_log", "turn_buffer", "artifact_event",
]


class MemoryEvent(BaseModel):
    event_id: str
    ts: str
    session_id: str | None
    student_id: str | None
    tier: Tier
    operation: Operation
    record_type: RecordType
    source_fn: str
    trace_id: str | None
    span_id: str | None
    payload: Any = None


class FieldChange(BaseModel):
    path: str
    kind: str  # "added" | "removed" | "changed"
    old: object = None
    new: object = None
    label: str


class EnrichedEvent(BaseModel):
    event: MemoryEvent
    diff: list[FieldChange] = []


__all__ = ["MemoryEvent", "FieldChange", "EnrichedEvent"]
```

- [ ] **Step 3: Rewrite `observatory/main.py`**

```python
"""SMRITI Observatory backend entry point. Run with:
    uv run uvicorn observatory.main:app --reload --port 8100
"""
from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import firestore

from observatory.broadcaster import Broadcaster
from observatory.ingest import run_ingest_loop
from observatory.routes_rest import build_router
from observatory.routes_ws import build_ws_router
from observatory.snapshot_cache import SnapshotCache

load_dotenv()

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
GCP_PROJECT = os.environ.get("GCP_PROJECT", "nityam-506707")
FIRESTORE_DATABASE = os.environ.get("FIRESTORE_DATABASE", "smriti")
TUTOR_BASE_URL = os.environ.get("TUTOR_BASE_URL", "http://localhost:8000")

broadcaster = Broadcaster()
snapshot_cache = SnapshotCache()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.firestore = firestore.Client(project=GCP_PROJECT, database=FIRESTORE_DATABASE)

    def get_dpm(student_id: str):
        doc = app.state.firestore.collection("dpm_profiles").document(student_id).get()
        return doc.to_dict() if doc.exists else None

    def get_teaching_memory(student_id: str):
        doc = app.state.firestore.collection("teaching_memories").document(student_id).get()
        return doc.to_dict() if doc.exists else None

    ingest_task = asyncio.create_task(
        run_ingest_loop(REDIS_HOST, REDIS_PORT, snapshot_cache, broadcaster, get_dpm, get_teaching_memory)
    )
    yield
    ingest_task.cancel()
    app.state.firestore.close()


app = FastAPI(title="SMRITI Observatory", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(build_router(tutor_base_url=TUTOR_BASE_URL, redis_host=REDIS_HOST, redis_port=REDIS_PORT))
app.include_router(build_ws_router(broadcaster))
```

- [ ] **Step 4: Rewrite `observatory/routes_rest.py`**

```python
"""REST snapshot endpoints. Talks to whichever agent server is configured
(sub_modules_examples/tutor or backend/) purely over HTTP — never imports
either app's Python package. See
docs/superpowers/specs/2026-08-28-backend-memory-observatory-design.md §3.
"""
from __future__ import annotations

import httpx
import redis as redis_sync
from fastapi import APIRouter, Request

from observatory.events import MemoryEvent


def build_router(tutor_base_url: str, redis_host: str, redis_port: int) -> APIRouter:
    router = APIRouter(prefix="/api")
    _agent_graph_cache: dict[str, str] = {}

    @router.get("/agent-graph")
    async def agent_graph():
        if "dot_src" in _agent_graph_cache:
            return {"dot_src": _agent_graph_cache["dot_src"]}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{tutor_base_url}/dev/apps/app/graph", params={"dark_mode": "true"}, timeout=5.0)
            dot_src = response.json().get("dotSrc", "")
        except Exception:
            return {"dot_src": ""}
        _agent_graph_cache["dot_src"] = dot_src
        return {"dot_src": dot_src}

    @router.get("/sessions")
    def list_sessions():
        try:
            client = redis_sync.Redis(host=redis_host, port=redis_port, decode_responses=True)
            raw_events = client.lrange("smriti:events:recent", 0, -1)
        except Exception:
            return {"sessions": []}
        events = [MemoryEvent.model_validate_json(raw) for raw in raw_events]
        by_session: dict[str, dict] = {}
        for event in events:
            if not event.session_id:
                continue
            entry = by_session.setdefault(event.session_id, {
                "session_id": event.session_id,
                "student_id": event.student_id,
                "started_at": event.ts,
                "last_event_at": event.ts,
            })
            entry["last_event_at"] = event.ts
            if event.student_id:
                entry["student_id"] = event.student_id
        for session_id, entry in by_session.items():
            try:
                entry["status"] = "live" if client.exists(f"session:{session_id}:heartbeat") else "closed"
            except Exception:
                entry["status"] = "closed"
        return {"sessions": sorted(by_session.values(), key=lambda s: s["last_event_at"], reverse=True)}

    @router.get("/sessions/{session_id}/state")
    async def session_state(session_id: str, student_id: str):
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{tutor_base_url}/memory/sessions/{session_id}/state",
                params={"student_id": student_id}, timeout=10.0,
            )
        return response.json()

    @router.get("/sessions/{session_id}/events")
    async def session_events(session_id: str, student_id: str = ""):
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{tutor_base_url}/memory/sessions/{session_id}/events",
                params={"student_id": student_id}, timeout=10.0,
            )
        return response.json()

    @router.post("/sessions/{session_id}/close")
    async def close_session_proxy(session_id: str, body: dict):
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{tutor_base_url}/memory/sessions/{session_id}/close", json=body)
        return response.json()

    @router.get("/health")
    def health(request: Request):
        redis_ok = True
        try:
            redis_sync.Redis(host=redis_host, port=redis_port).ping()
        except Exception:
            redis_ok = False
        firestore_ok = True
        try:
            request.app.state.firestore.collection("_healthcheck").document("x").get()
        except Exception:
            firestore_ok = False
        tutor_ok = True
        try:
            httpx.get(f"{tutor_base_url}/health", timeout=2.0)
        except Exception:
            tutor_ok = False
        return {"redis": redis_ok, "firestore": firestore_ok, "tutor_reachable": tutor_ok}

    return router
```

Two behavior notes versus the pre-refactor version, both intentional:
`session_state`/`session_events` are now `httpx` proxies (matching
`close_session_proxy`'s existing shape) instead of direct Firestore/Redis
reads — this is the whole point of the decoupling. `health()`'s
`tutor_reachable` probe now hits `/health` instead of `/list-apps` — a
route both `sub_modules_examples/tutor` (served by ADK's
`get_fast_api_app`) and `backend/` (`app/main.py:644`) serve, so one probe
works against either.

- [ ] **Step 5: Update `smriti-observatory/backend/tests/conftest.py`**

```python
"""Fixtures build their own Firestore/Redis clients directly from this
package's own env vars — no import from either agent app's `app` package
(see docs/superpowers/specs/2026-08-28-backend-memory-observatory-design.md §3).
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture
def firestore_db():
    from google.cloud import firestore

    project = os.environ.get("GCP_PROJECT", "nityam-506707")
    database = os.environ.get("FIRESTORE_DATABASE", "smriti")
    try:
        client = firestore.Client(project=project, database=database)
        client.collection("_healthcheck").document("x").get()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Firestore unreachable ({exc}); run `gcloud auth application-default login`")
    yield client
    client.close()


@pytest.fixture
def redis_client():
    import redis as redis_module

    host = os.environ.get("REDIS_HOST", "localhost")
    port = int(os.environ.get("REDIS_PORT", "6379"))
    try:
        client = redis_module.Redis(host=host, port=port, decode_responses=True)
        client.ping()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Redis unreachable at {host}:{port} ({exc}); run `brew services start redis`")
    yield client
```

- [ ] **Step 6: Update `smriti-observatory/backend/tests/test_routes_rest.py`**

Replace the `store`/`DPMProfile`/`TeachingMemory` imports and the two seed
calls with plain-dict writes through the fixture; update `build_router(...)`
call sites to pass `redis_host`/`redis_port`; update `session_state`/
`session_events` tests to stand up a tiny fake agent server (since they're
now HTTP proxies, not direct reads):

```python
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from observatory.routes_rest import build_router


@pytest.fixture
def client_app(firestore_db, redis_client):
    app = FastAPI()
    app.state.firestore = firestore_db
    app.include_router(build_router(tutor_base_url="http://localhost:9999", redis_host="localhost", redis_port=6379))
    return TestClient(app)


def test_agent_graph_returns_empty_dot_src_when_tutor_unreachable(client_app):
    response = client_app.get("/api/agent-graph")
    assert response.status_code == 200
    assert response.json() == {"dot_src": ""}


def test_agent_graph_proxies_and_caches_the_tutor_apps_dot_source(monkeypatch):
    calls = []

    class FakeResponse:
        def json(self):
            return {"dotSrc": "strict digraph { TutorAgent }"}

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, **kwargs):
            calls.append(url)
            return FakeResponse()

    monkeypatch.setattr("observatory.routes_rest.httpx.AsyncClient", FakeAsyncClient)

    app = FastAPI()
    app.include_router(build_router(tutor_base_url="http://fake-tutor", redis_host="localhost", redis_port=6379))
    client = TestClient(app)

    first = client.get("/api/agent-graph")
    second = client.get("/api/agent-graph")

    assert first.json() == {"dot_src": "strict digraph { TutorAgent }"}
    assert second.json() == {"dot_src": "strict digraph { TutorAgent }"}
    assert calls == ["http://fake-tutor/dev/apps/app/graph"]


def test_session_state_proxies_to_the_configured_agent_server(monkeypatch):
    class FakeResponse:
        def json(self):
            return {"session_id": "s1", "student_id": "stu1", "workflow": {}, "episodic": {}, "long_term": {}}

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, **kwargs):
            assert url == "http://fake-agent/memory/sessions/s1/state"
            assert kwargs["params"] == {"student_id": "stu1"}
            return FakeResponse()

    monkeypatch.setattr("observatory.routes_rest.httpx.AsyncClient", FakeAsyncClient)

    app = FastAPI()
    app.include_router(build_router(tutor_base_url="http://fake-agent", redis_host="localhost", redis_port=6379))
    response = TestClient(app).get("/api/sessions/s1/state", params={"student_id": "stu1"})
    assert response.status_code == 200
    assert response.json()["student_id"] == "stu1"


def test_health_reports_redis_and_firestore_reachability(client_app):
    response = client_app.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["redis"] is True
    assert body["firestore"] is True
    assert "tutor_reachable" in body


def test_events_endpoint_returns_recent_backlog(client_app, redis_client):
    redis_client.delete("smriti:events:recent")
    from observatory.events import MemoryEvent
    event = MemoryEvent(
        event_id="e1", ts="2026-08-27T00:00:00Z", session_id="test_rest_session_2", student_id="s",
        tier="workflow", operation="write", record_type="turn_buffer", source_fn="append_turn",
        trace_id=None, span_id=None, payload=None,
    )
    redis_client.rpush("smriti:events:recent", event.model_dump_json())
    response = client_app.get("/api/sessions/test_rest_session_2/events")
    assert response.status_code == 200


def test_events_endpoint_filters_by_session_id(client_app, redis_client):
    redis_client.delete("smriti:events:recent")
    from observatory.events import MemoryEvent
    for i, sid in enumerate(["test_rest_session_3", "test_rest_session_4"]):
        event = MemoryEvent(
            event_id=f"e{i}", ts="2026-08-27T00:00:00Z", session_id=sid, student_id="s",
            tier="workflow", operation="write", record_type="turn_buffer", source_fn="append_turn",
            trace_id=None, span_id=None, payload=None,
        )
        redis_client.rpush("smriti:events:recent", event.model_dump_json())
    response = client_app.get("/api/sessions/test_rest_session_3/events")
    assert response.status_code == 200


def test_list_sessions_derives_from_recent_events(client_app, redis_client):
    redis_client.delete("smriti:events:recent")
    from observatory.events import MemoryEvent

    event = MemoryEvent(
        event_id="e1", ts="2026-08-27T00:00:00Z", session_id="test_rest_session_list", student_id="stu_list",
        tier="workflow", operation="write", record_type="turn_buffer", source_fn="append_turn",
        trace_id=None, span_id=None, payload=None,
    )
    redis_client.rpush("smriti:events:recent", event.model_dump_json())
    try:
        response = client_app.get("/api/sessions")
        assert response.status_code == 200
        sessions = response.json()["sessions"]
        match = next(s for s in sessions if s["session_id"] == "test_rest_session_list")
        assert match["student_id"] == "stu_list"
        assert match["status"] == "closed"
    finally:
        redis_client.delete("smriti:events:recent")


def test_list_sessions_marks_a_session_with_a_live_heartbeat_as_live(client_app, redis_client):
    redis_client.delete("smriti:events:recent")
    from observatory.events import MemoryEvent

    event = MemoryEvent(
        event_id="e2", ts="2026-08-27T00:00:00Z", session_id="test_rest_session_live", student_id="stu_live",
        tier="workflow", operation="write", record_type="turn_buffer", source_fn="append_turn",
        trace_id=None, span_id=None, payload=None,
    )
    redis_client.rpush("smriti:events:recent", event.model_dump_json())
    redis_client.set("session:test_rest_session_live:heartbeat", "1", ex=60)
    try:
        response = client_app.get("/api/sessions")
        sessions = response.json()["sessions"]
        match = next(s for s in sessions if s["session_id"] == "test_rest_session_live")
        assert match["status"] == "live"
    finally:
        redis_client.delete("smriti:events:recent", "session:test_rest_session_live:heartbeat")
```

(`test_session_state_returns_current_long_term_snapshot`/
`test_session_state_handles_missing_records_gracefully` from the old file
are replaced by `test_session_state_proxies_to_the_configured_agent_server`
above — they tested a direct-read behavior this endpoint no longer has.)

- [ ] **Step 7: Update `smriti-observatory/backend/tests/test_events.py`**

```python
from __future__ import annotations

from observatory.events import EnrichedEvent, MemoryEvent


def test_a_real_tutor_published_event_parses_under_the_local_model():
    """Wire-compatibility, not class identity: the Observatory's own
    MemoryEvent must be able to decode JSON produced by either agent app's
    instrumentation.py, without importing either one's package."""
    from app.memory.instrumentation import MemoryEvent as TutorMemoryEvent

    tutor_event = TutorMemoryEvent(
        event_id="e1", ts="2026-08-27T00:00:00Z", session_id="s1", student_id="stu1",
        tier="long_term", operation="write", record_type="dpm_profile",
        source_fn="put_dpm", trace_id=None, span_id=None, payload={"student_id": "stu1"},
    )
    parsed = MemoryEvent.model_validate_json(tutor_event.model_dump_json())
    assert parsed.model_dump() == tutor_event.model_dump()


def test_enriched_event_wraps_a_memory_event_with_an_optional_diff():
    event = MemoryEvent(
        event_id="e1", ts="2026-08-27T00:00:00Z", session_id="s1", student_id="stu1",
        tier="long_term", operation="write", record_type="dpm_profile",
        source_fn="put_dpm", trace_id=None, span_id=None, payload={"student_id": "stu1"},
    )
    enriched = EnrichedEvent(event=event, diff=[])
    assert enriched.event.session_id == "s1"
    assert enriched.diff == []
```

- [ ] **Step 8: Update `smriti-observatory/backend/pyproject.toml`**

Move `"tutor"` from `[project] dependencies` into `[dependency-groups] dev`
(it's still needed there, by `tests/test_end_to_end.py` alone); add
`"google-cloud-firestore>=2.16"` to `[project] dependencies`:

```toml
[project]
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "redis>=5.0",
    "pydantic>=2.0",
    "httpx>=0.27",
    "python-dotenv>=1.0",
    "google-cloud-firestore>=2.16",
]

[dependency-groups]
dev = [
    "pytest>=9.0.2,<10.0.0",
    "pytest-asyncio>=1.0.0,<2.0.0",
    "tutor",
]

[tool.uv.sources]
tutor = { path = "../../sub_modules_examples/tutor", editable = true }
```

Run `uv sync` after this change (updates `uv.lock`).

- [ ] **Step 9: Run the full pytest suite and compare against the Step 1 baseline**

Run: `cd smriti-observatory/backend && uv run pytest -q`
Expected: same pass count as the Step 1 baseline (or more, with the two new
tests), zero new failures, zero collection errors. `test_end_to_end.py`
must still pass unmodified (proves the tutor-specific dev dependency still
works).

- [ ] **Step 10: Commit**

```bash
git add smriti-observatory/backend/observatory/events.py \
        smriti-observatory/backend/observatory/main.py \
        smriti-observatory/backend/observatory/routes_rest.py \
        smriti-observatory/backend/tests/conftest.py \
        smriti-observatory/backend/tests/test_routes_rest.py \
        smriti-observatory/backend/tests/test_events.py \
        smriti-observatory/backend/pyproject.toml \
        smriti-observatory/backend/uv.lock
git commit -m "refactor: decouple smriti-observatory/backend from the tutor package import"
```

---

### Task 7: Point the Observatory at `backend/`

**Files:**
- Modify: `smriti-observatory/backend/.env.example` (document, don't
  silently change, the value)
- Create/modify locally (not committed, per existing `.gitignore`):
  `smriti-observatory/backend/.env`, `smriti-observatory/frontend/.env`

**Interfaces:** none — this is configuration, not code.

- [ ] **Step 1: Update `.env.example` with both pointing options documented**

```
# smriti-observatory/backend/.env.example
GCP_PROJECT=nityam-506707
FIRESTORE_DATABASE=smriti
REDIS_HOST=localhost
REDIS_PORT=6379
# Base URL of whichever agent server exposes /memory/sessions/*: either
# sub_modules_examples/tutor's own uvicorn port, or backend/'s (this repo's
# real production tutor) — both serve the same two GET routes.
TUTOR_BASE_URL=http://localhost:8000
```

- [ ] **Step 2: Run `backend/` locally with real storage, and start the Observatory pointed at it**

```bash
# terminal 1 — the real production tutor, real storage so Firestore/Redis
# reads actually have data (see spec's "Prerequisites" section):
cd backend && NITYAM_STORE=firestore NITYAM_AUTH=mock ./run.sh

# terminal 2 — point the Observatory backend at backend/'s port (adjust if
# backend/'s actual port differs from 8000 — check backend/.env or run.sh):
cd smriti-observatory/backend
echo "TUTOR_BASE_URL=http://localhost:8000" >> .env
uv run uvicorn observatory.main:app --reload --port 8100

# terminal 3:
cd smriti-observatory/frontend
echo "VITE_TUTOR_BASE_URL=http://localhost:8000" >> .env
npm run dev
```

- [ ] **Step 3: Confirm connectivity before moving on**

`curl http://localhost:8100/api/health` — expect `{"redis": true,
"firestore": true, "tutor_reachable": true}`. If `tutor_reachable` is
false, confirm `backend/`'s actual port (its own `.env`/`run.sh` may bind
somewhere other than 8000) and adjust `TUTOR_BASE_URL` to match.

No commit for this task — the repo root `.gitignore`'s `.env`/`*.env`
patterns (confirmed: no leading `/`, so they match at any depth) already
cover both `smriti-observatory/backend/.env` and
`smriti-observatory/frontend/.env`; nothing to add.

---

### Task 8: Auto-select the live session in `smriti-observatory/frontend`

**Files:**
- Modify: `smriti-observatory/frontend/src/features/session/SessionView.tsx`

**Interfaces:**
- Consumes: `SessionSummary` (`components/SessionDrawer.tsx`, unchanged:
  `{session_id, student_id, status, started_at, last_event_at}`).
- No new exports — this is entirely internal to `SessionView`'s own state
  management.

- [ ] **Step 1: Replace the mount-only session fetch with a polling one, and add auto-select**

Replace the existing first `useEffect` (lines 28-33) with:

```tsx
useEffect(() => {
  let cancelled = false;
  const fetchSessions = () => {
    fetch(`${BACKEND_URL}/api/sessions`)
      .then((r) => r.json())
      .then((body) => {
        if (cancelled) return;
        setSessions(body.sessions ?? []);
      })
      .catch(() => {
        if (!cancelled) setSessions([]);
      });
  };
  fetchSessions();
  const interval = setInterval(fetchSessions, 4000);
  return () => {
    cancelled = true;
    clearInterval(interval);
  };
}, []);

// Auto-select the most-recently-active live session whenever there is no
// selection yet, or the selected session just stopped being live while a
// different one is now live — never overrides a manual pick that's still
// live (see docs/superpowers/specs/2026-08-28-backend-memory-observatory-design.md §4).
useEffect(() => {
  const live = sessions.filter((s) => s.status === "live");
  if (live.length === 0) return;
  const currentlySelectedIsLive = live.some((s) => s.session_id === selectedId);
  if (selectedId && currentlySelectedIsLive) return;
  const newest = [...live].sort((a, b) => b.last_event_at.localeCompare(a.last_event_at))[0];
  setSelectedId(newest.session_id);
}, [sessions, selectedId]);
```

Leave the second `useEffect` (`sessionsRef.current = sessions`, lines
40-42) and the third (`selectedId`-keyed fetch/WS-connect, lines 44-62)
unchanged — they already react correctly to `selectedId` changing,
regardless of whether the change came from a click or the new
auto-select effect.

- [ ] **Step 2: Manually verify in a real browser (per this repo's own UI-work standard)**

With Task 7's three servers running:
1. Open `http://localhost:5173` (or whatever port `npm run dev` picks) —
   confirm it shows either the empty state (nothing live yet) or, if a
   session is already live, that session's panels with no click.
2. Drive a real session against `backend/` (a real voice/mock-mode
   conversation through `frontend/`, or `backend/scripts/drive.py` if it
   supports pointing at a running server — check its own `--help`/docstring
   for the current invocation) while the Observatory tab is open.
3. Confirm: the Observatory auto-selects that session within ~4s of it
   going live, the Workflow panel fills turn by turn, and after the
   conversation ends, the Episodic panel renders the full ledger and the
   Long-term panel shows a real diff — no manual session click at any
   point. Check the browser console for errors.

- [ ] **Step 3: Commit**

```bash
git add smriti-observatory/frontend/src/features/session/SessionView.tsx
git commit -m "feat: auto-select the live session in the Observatory frontend"
```

---

### Task 9: Final end-to-end verification

**Files:** none (verification only).

- [ ] **Step 1: Run every automated test touched by this plan, fresh**

```bash
cd backend && for f in tests/test_memory_instrumentation.py tests/test_memory_store_events.py \
  tests/test_short_term_events.py tests/test_memory_routes.py; do
  .venv/bin/python -m "${f%.py}" | tr '/' '.' || exit 1
done
NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_session_close_events
NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_close_session_wiring
.venv/bin/python -m tests.test_short_term_writethrough
cd ../smriti-observatory/backend && uv run pytest -q
```

Expected: everything passes.

- [ ] **Step 2: Confirm `sub_modules_examples/tutor` + `smriti-observatory/adk-web` are unaffected**

```bash
cd sub_modules_examples/tutor && uv run pytest tests/unit -q
```

Expected: passes exactly as before this plan started (this plan touched no
file under `sub_modules_examples/`).

- [ ] **Step 3: The real end-to-end walkthrough from Task 8 Step 2, once more, start to finish**

This is the actual proof the feature works: open the Observatory with
nothing running, start a real `backend/` session, watch it auto-appear and
update live, end the session, watch Episodic/Long-term populate — all
without touching the session drawer.

- [ ] **Step 4: Final commit if anything was left uncommitted**

```bash
git status
git add -A  # only if Step 3 surfaced a fix; review the diff first
git commit -m "fix: <whatever Step 3 found>"
```
