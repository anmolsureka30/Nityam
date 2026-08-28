# Memory Storage Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the three Google-managed storage tiers the design spec already decided on
(Firestore, Cloud Storage, Memorystore) actually load-bearing — durable artifact storage, a real
workflow-tier write-through mirror, and, critically, a real fix for `close_session` never being
invoked, which today means no real session's memory reaches Firestore at all.

**Architecture:** Three independent-but-sequenced additions to the existing backend: (1) a small
new module writes generated-artifact IR to the already-provisioned GCS bucket, called from
`ArtifactAgent`'s existing background build step; (2) the two places that actually accumulate
in-session state (`brain.py`'s `_record`, and the live `log_artifact_evidence` tool) gain a Redis
write-through; (3) `ws_endpoint`'s teardown gains the real `session_close.close_session()` call,
reading the turn buffer back from Redis rather than from ADK session state — because the buffer
does not, in fact, live where the spec's source doc assumed it did (see Task 3's note).

**Tech Stack:** Python 3.12, google-cloud-storage (already a dependency), redis.asyncio (already
a dependency, `redis>=5.0` in requirements.txt), a local `redis-server` for dev.

**Spec:** `docs/superpowers/specs/2026-08-28-cloud-memory-and-shruti-integration-design.md` §2,
§3 — this plan is Phase 1 of 4; the Shruti sync bridge, the per-lecture summary, and task-scoped
retrieval are separate follow-on plans, each independently valuable and testable on its own.

## Global Constraints

- GCS bucket: `nityam-506707-tutor-artifacts` (already exists, already verified writable via
  ADC this session — no bucket-creation step needed).
- Redis: local dev uses `redis-server` on `localhost:6379` (already installed on this machine);
  Memorystore itself is a deployment-time concern (Direct VPC egress, per the spec §2), not
  something this plan's tests reach.
- Every new write-through / durability call must be wrapped so its failure never breaks a live
  lesson turn — matches the existing codebase convention throughout `artifact_agent.py`/`brain.py`
  (`except Exception: log.warning(...)`, never let a storage failure propagate into the voice
  path).
- `MODE == "mock"` must keep working exactly as it does today, with no new dependency on GCS/Redis
  credentials — mock mode is the tests' own no-spend, no-network baseline (`AGENTS.md`/`README.md`
  convention throughout this repo).

---

### Task 1: GCS artifact persistence

**Files:**
- Create: `backend/app/artifacts_gcs.py`
- Modify: `backend/app/agents/artifact_agent.py:20-34` (imports), `:145-152` (the `_build` mount
  step)
- Modify: `backend/app/main.py:62-90` (Runner construction)
- Modify: `backend/.env` (add `GCS_BUCKET=nityam-506707-tutor-artifacts`), `backend/.env.example`
  (add the same key, empty)
- Test: `backend/tests/test_gcs_artifacts.py`

**Interfaces:**
- Produces: `app.artifacts_gcs.save_artifact_to_gcs(artifact_id: str, ir: dict) -> None`,
  `app.artifacts_gcs.read_artifact_from_gcs(artifact_id: str) -> dict`,
  `app.artifacts_gcs.delete_artifact_from_gcs(artifact_id: str) -> None`.

- [ ] **Step 1: Add the bucket name to env config**

Edit `backend/.env`, in the ports section, add one line:

```
GCS_BUCKET=nityam-506707-tutor-artifacts
```

Edit `backend/.env.example` the same way, but leave the value empty (matching every other real
credential in that file):

```
# GCS bucket for durable ArtifactAgent output. Must already exist — see
# app/artifacts_gcs.py. `gcloud storage buckets list` to check what you have.
GCS_BUCKET=
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_gcs_artifacts.py`:

```python
"""GCS artifact persistence: the IR a completed artifact mounts with also
lands durably in Cloud Storage, keyed by artifact_id, and can be read back
and deleted.

    .venv/bin/python -m tests.test_gcs_artifacts
"""
from __future__ import annotations

import sys
import uuid

from app.auth import load_env

load_env()

from app.artifacts_gcs import (
    delete_artifact_from_gcs,
    read_artifact_from_gcs,
    save_artifact_to_gcs,
)

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


def main() -> int:
    artifact_id = f"test_{uuid.uuid4().hex[:10]}"
    ir = {"artifact_id": artifact_id, "title": "test artifact", "controls": []}

    save_artifact_to_gcs(artifact_id, ir)
    round_tripped = read_artifact_from_gcs(artifact_id)
    check("the artifact round-trips through GCS", round_tripped == ir, repr(round_tripped))

    delete_artifact_from_gcs(artifact_id)
    try:
        read_artifact_from_gcs(artifact_id)
        check("and is gone after delete", False, "read did not raise")
    except Exception:  # noqa: BLE001 - any exception (NotFound) is the point
        check("and is gone after delete", True)

    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m tests.test_gcs_artifacts`
Expected: `ModuleNotFoundError: No module named 'app.artifacts_gcs'`

- [ ] **Step 4: Write the module**

Create `backend/app/artifacts_gcs.py`:

```python
"""Durable storage for generated artifact IR, in Cloud Storage.

ArtifactAgent's own board write already keeps the IR in the live board for
the running session (app/agents/artifact_agent.py:_build) — this is the copy
that survives a reload or a restart, keyed by artifact_id.

Not routed through ADK's tool_context.save_artifact(): _build() runs as a
detached background asyncio task (see its own docstring — generation is
spawned off the conversation's critical path), so by the time it finishes,
the tool invocation that spawned it has already returned, and ToolContext's
write methods are scoped to a live invocation. A plain google-cloud-storage
client sidesteps that lifetime question entirely.
"""
from __future__ import annotations

import json

from google.cloud import storage

from app import config


def _blob(artifact_id: str) -> storage.Blob:
    client = storage.Client()
    bucket = client.bucket(config.GCS_BUCKET)
    return bucket.blob(f"artifacts/{artifact_id}.json")


def save_artifact_to_gcs(artifact_id: str, ir: dict) -> None:
    _blob(artifact_id).upload_from_string(
        json.dumps(ir, ensure_ascii=False), content_type="application/json",
    )


def read_artifact_from_gcs(artifact_id: str) -> dict:
    return json.loads(_blob(artifact_id).download_as_text())


def delete_artifact_from_gcs(artifact_id: str) -> None:
    _blob(artifact_id).delete()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m tests.test_gcs_artifacts`
Expected: both checks `ok`, `all passed` (or no `FAILED` count printed nonzero)

- [ ] **Step 6: Commit**

```bash
git add backend/app/artifacts_gcs.py backend/tests/test_gcs_artifacts.py backend/.env.example
git commit -m "feat: add GCS-backed durable storage for generated artifacts"
```

(`backend/.env` is gitignored — it's already edited locally, nothing to stage there.)

- [ ] **Step 7: Wire the save call into `_build`**

In `backend/app/agents/artifact_agent.py`, add the import alongside the existing ones (line 32):

```python
from app import artifacts_gcs, config, logs, sessions
```

(This replaces the existing `from app import config, logs, sessions` line — `artifacts_gcs` is
new, `config`/`logs`/`sessions` are unchanged.)

Then in `_build` (currently lines 145-152), immediately after the board publish succeeds and
before the `log.info("artifact %s mounted...")` line:

```python
    artifact_id = ir.get("artifact_id") or placeholder_id
    state = sessions.get(session_id)
    block = D.ArtifactBlock(id=state.mint("b_art"), artifactId=artifact_id, ir=ir)
    try:
        sessions.publish(session_id, D.AppendBlock(block=block))
    except (sessions.PatchRejected, ValueError) as exc:
        log.warning("finished artifact rejected by the board: %s", exc)
        return

    try:
        artifacts_gcs.save_artifact_to_gcs(artifact_id, ir)
    except Exception:  # noqa: BLE001 - durability is a bonus, not a lesson-blocker
        log.warning("artifact %s failed to persist to GCS", artifact_id, exc_info=True)

    log.info("artifact %s mounted as %s — %s", artifact_id, block.id, provenance)
```

- [ ] **Step 8: Wire `GcsArtifactService` into the Runner**

In `backend/app/main.py`, inside the `if MODE != "mock":` block (starts line 62), add the import
alongside the existing ADK imports and add `config` to the top-level import — the block currently
reads:

```python
if MODE != "mock":
    from google.adk.agents.live_request_queue import LiveRequestQueue
    from google.adk.agents.run_config import RunConfig, StreamingMode
    from google.adk.apps import App
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from app.agents.brain import _cache_config
    from app.agents.voice_agent import build_voice_agent
```

Change it to:

```python
if MODE != "mock":
    from google.adk.agents.live_request_queue import LiveRequestQueue
    from google.adk.agents.run_config import RunConfig, StreamingMode
    from google.adk.apps import App
    from google.adk.artifacts import GcsArtifactService
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from app import config
    from app.agents.brain import _cache_config
    from app.agents.voice_agent import build_voice_agent
```

Then the `Runner(...)` construction (currently lines 80-90):

```python
    runner = Runner(
        app=App(
            name=APP_NAME,
            root_agent=build_voice_agent(),
            context_cache_config=_cache_config(),
        ),
        session_service=session_service,
    )
```

becomes:

```python
    runner = Runner(
        app=App(
            name=APP_NAME,
            root_agent=build_voice_agent(),
            context_cache_config=_cache_config(),
        ),
        session_service=session_service,
        artifact_service=GcsArtifactService(bucket_name=config.GCS_BUCKET),
    )
```

- [ ] **Step 9: Verify the backend still imports cleanly in both modes**

Run:
```bash
cd backend
.venv/bin/python -c "from app.auth import load_env, configure; load_env(); import os; os.environ['NITYAM_AUTH']='mock'; configure(); from app import main; print('mock OK')"
NITYAM_AUTH=vertex_express .venv/bin/python -c "from app.auth import load_env, configure; load_env(); configure(); from app import main; print('live OK')"
```
Expected: both print `... OK`, no traceback.

- [ ] **Step 10: Commit**

```bash
git add backend/app/agents/artifact_agent.py backend/app/main.py
git commit -m "feat: persist generated artifacts to GCS and wire GcsArtifactService into the Runner"
```

---

### Task 2: Memorystore write-through for the workflow tier

**Files:**
- Modify: `backend/app/agents/brain.py:130-155` (`_record`), `:303` (its call site)
- Modify: `backend/app/memory/tools.py:120-135` (`log_artifact_evidence`)
- Test: `backend/tests/test_short_term_writethrough.py`

**Interfaces:**
- Consumes: `app.memory.short_term.append_turn(session_id: str, turn: dict) -> None`,
  `app.memory.short_term.append_artifact_event(session_id: str, event: dict) -> None`,
  `app.memory.short_term.get_turn_buffer(session_id: str) -> list[dict]` (all already exist,
  unchanged, in `backend/app/memory/short_term.py`).
- Produces: `_record` and `log_artifact_evidence` become `async def` — any future caller must
  `await` them. (Confirmed during planning: `log_turn` in `app/memory/tools.py`, despite its
  docstring, is **not** an active tool — TutorAgent's tool list does not include it; turn logging
  was moved to `brain.py`'s `_record` specifically to avoid a model round trip for pure
  bookkeeping. This task leaves `tools.py:log_turn` untouched and puts the turn write-through
  where turns are actually recorded.)

- [ ] **Step 1: Start a local Redis for the test**

```bash
redis-server --daemonize yes --port 6379
redis-cli ping   # expect: PONG
```

(Already installed on this machine — confirmed via `command -v redis-server` during planning.
In CI/other machines without it: `docker run -d -p 6379:6379 redis` is the documented
alternative from `google_cloud_storage_integration.md` §5.4.)

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_short_term_writethrough.py`:

```python
"""The workflow-tier write-through: appending a turn or an artifact event
through the real call sites lands in Redis, keyed by session_id, not just in
whatever in-process state the caller happens to hold.

Needs a local Redis on localhost:6379 (`redis-server --daemonize yes`).

    .venv/bin/python -m tests.test_short_term_writethrough
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from app.auth import load_env

load_env()

from app.agents.brain import _record
from app.memory import short_term
from app.memory.tools import log_artifact_evidence

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


class _FakeToolContext:
    """log_artifact_evidence only ever touches .state as a plain dict."""

    def __init__(self) -> None:
        self.state: dict = {}


async def run() -> None:
    session_id = f"test_{uuid.uuid4().hex[:10]}"
    await short_term.clear_session(session_id)

    ctx = _FakeToolContext()
    ctx.state["session_id"] = session_id
    ctx.state["turn_buffer"] = []
    await _record(session_id, "demo_student", "why 45 degrees?", "because sin(2θ) peaks there", ctx)

    turns = await short_term.get_turn_buffer(session_id)
    check("a recorded turn lands in Redis", len(turns) == 2, repr(turns))
    check("student half is first", turns[0]["role"] == "student" if turns else False)
    check("tutor half is second", turns[1]["role"] == "tutor" if len(turns) > 1 else False)

    result = await log_artifact_evidence("discovered_optimum", "art_1", ctx)
    check("log_artifact_evidence still returns its ack", result == {"logged": True}, repr(result))

    await short_term.clear_session(session_id)


def main() -> int:
    asyncio.run(run())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m tests.test_short_term_writethrough`
Expected: `TypeError: object dict can't be used in 'await' expression` (or similar) —
`_record`/`log_artifact_evidence` are not yet `async` and the test awaits them.

- [ ] **Step 4: Make `_record` async and write through**

In `backend/app/agents/brain.py`, the current `_record` (lines 130-155):

```python
def _record(session_id: str, student_id: str, asked: str, replied: str,
            tool_context: ToolContext) -> None:
    """Append the exchange to the session buffer, here rather than as a tool.

    `log_turn` used to be something TutorAgent called, and every call is a model
    round trip: two of them per turn, five to eight seconds of the student
    listening to silence, for bookkeeping they never see. Both halves of the
    exchange are already in hand at this point, so write them directly and give
    the time back to teaching.
    """
    buffer = list(tool_context.state.get("turn_buffer", []))
    for role, text in (("student", asked), ("tutor", replied)):
        clean = (text or "").strip()
        if not clean:
            continue
        # Stage directions are not things the student said.
        if role == "student" and clean.startswith("["):
            clean = clean[:400]
        buffer.append({
            "turn": len(buffer) + 1,
            "role": role,
            "text": clean[:2000],
            "concept_id": None,
            "artifact_id": None,
        })
    tool_context.state["turn_buffer"] = buffer
```

becomes:

```python
async def _record(session_id: str, student_id: str, asked: str, replied: str,
                   tool_context: ToolContext) -> None:
    """Append the exchange to the session buffer, here rather than as a tool.

    `log_turn` used to be something TutorAgent called, and every call is a model
    round trip: two of them per turn, five to eight seconds of the student
    listening to silence, for bookkeeping they never see. Both halves of the
    exchange are already in hand at this point, so write them directly and give
    the time back to teaching.

    Also writes through to Memorystore (async, sub-millisecond, wrapped so an
    outage never breaks a live turn) — the durable copy `close_session` reads
    back from, since this buffer lives in brain.py's own session state, not the
    one main.py's ws_endpoint can see.
    """
    buffer = list(tool_context.state.get("turn_buffer", []))
    for role, text in (("student", asked), ("tutor", replied)):
        clean = (text or "").strip()
        if not clean:
            continue
        # Stage directions are not things the student said.
        if role == "student" and clean.startswith("["):
            clean = clean[:400]
        turn = {
            "turn": len(buffer) + 1,
            "role": role,
            "text": clean[:2000],
            "concept_id": None,
            "artifact_id": None,
        }
        buffer.append(turn)
        try:
            await short_term.append_turn(session_id, turn)
        except Exception:  # noqa: BLE001 - a Redis outage must not break a live turn
            log.warning("turn write-through to Redis failed", exc_info=True)
    tool_context.state["turn_buffer"] = buffer
```

Add the import near the top of `backend/app/agents/brain.py`, alongside the existing
`from app import logs, sessions`:

```python
from app.memory import short_term
```

- [ ] **Step 5: Update `_record`'s call site**

Line 303 currently reads:

```python
    reply = _speakable(" ".join(said))
    _record(session_id, student_id, request, reply, tool_context)
```

becomes:

```python
    reply = _speakable(" ".join(said))
    await _record(session_id, student_id, request, reply, tool_context)
```

- [ ] **Step 6: Make `log_artifact_evidence` async and write through**

In `backend/app/memory/tools.py`, the current function (lines 120-135):

```python
def log_artifact_evidence(event: str, artifact_id: str, tool_context: ToolContext) -> dict:
    """Append an artifact interaction event (e.g. "discovered_optimum",
    "misconception_behavior" — see sub_modules/artifact_generator's probes)
    to the in-session buffer.

    Args:
        event: The event name the artifact reported.
        artifact_id: Which artifact reported it.

    Returns:
        dict confirming the event was buffered.
    """
    events = tool_context.state.get("artifact_events", [])
    events.append({"event": event, "artifact_id": artifact_id})
    tool_context.state["artifact_events"] = events
    return {"logged": True}
```

becomes:

```python
async def log_artifact_evidence(event: str, artifact_id: str, tool_context: ToolContext) -> dict:
    """Append an artifact interaction event (e.g. "discovered_optimum",
    "misconception_behavior" — see sub_modules/artifact_generator's probes)
    to the in-session buffer, and write through to Memorystore.

    Args:
        event: The event name the artifact reported.
        artifact_id: Which artifact reported it.

    Returns:
        dict confirming the event was buffered.
    """
    events = tool_context.state.get("artifact_events", [])
    entry = {"event": event, "artifact_id": artifact_id}
    events.append(entry)
    tool_context.state["artifact_events"] = events
    session_id = tool_context.state.get("session_id")
    if session_id:
        try:
            await short_term.append_artifact_event(session_id, entry)
        except Exception:  # noqa: BLE001 - a Redis outage must not break a live turn
            log.warning("artifact-event write-through to Redis failed", exc_info=True)
    return {"logged": True}
```

Add the import near the top of `backend/app/memory/tools.py`, alongside the existing
`from app.memory import store`:

```python
from app.memory import short_term, store
```

Also add a module-level logger, since this file has none yet — near the top, after the imports:

```python
log = logging.getLogger("nityam.memory")
```

(add `import logging` to the existing import block too.)

- [ ] **Step 7: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m tests.test_short_term_writethrough`
Expected: all four checks `ok`.

- [ ] **Step 8: Confirm nothing else broke**

Run the existing protocol test, which exercises `create_artifact`/board-write tools end to end in
mock mode:
```bash
cd backend && .venv/bin/python -m tests.test_wire
```
Expected: same result as before this task (the 4 pre-existing mock-teaching failures noted
earlier this project — unrelated to this change — may still show; no *new* failures).

- [ ] **Step 9: Commit**

```bash
git add backend/app/agents/brain.py backend/app/memory/tools.py backend/tests/test_short_term_writethrough.py
git commit -m "feat: write-through the workflow-tier buffer to Memorystore"
```

---

### Task 4: Fix `close_session` — real sessions actually reach Firestore

> Renumbered from Task 3 during execution (2026-08-28): implementing this task surfaced a
> separate, pre-existing bug blocking it — see the new Task 3 inserted below, and the ruling
> in `.superpowers/sdd/2026-08-28-memory-storage-completion/progress.md`. This task's own text
> is otherwise unchanged from the original plan; Task 3 must land first.

**Files:**
- Modify: `backend/app/main.py:35` (import), `:169-172` (the `finally` block)
- Test: `backend/tests/test_close_session_wiring.py`

**Interfaces:**
- Consumes: `app.memory.short_term.get_turn_buffer(session_id: str) -> list[dict]` (Task 2),
  `app.session_close.close_session(conn, session_id: str, student_id: str, started_at: datetime,
  buffer: list[dict], client: genai.Client) -> SessionLog` (already exists, unchanged),
  `app.memory.store.connect()` / `store.get_dpm` / `store.get_teaching_memory` (already exist),
  and `tests._firebase_test_tokens.mint_id_token` (already exists, from the Firebase-auth work
  earlier this project) — the test connects with a real token, since `ws_endpoint` now rejects
  any connection without one before it ever reaches the code this task adds.
- Produces: a real `session_log` document in Firestore per WebSocket session (mock mode
  excepted — see Step 4), and `dpm_profile`/`teaching_memory` actually updated by the Reflect
  call, for the first time in this codebase's history reachable from the live app rather than
  only from `seed_demo_data.py`'s one hand-written record.

**Why the buffer comes from Redis, not `tool_context.state`:** verified during planning —
`ws_endpoint` (`main.py`) and `ask_tutor`'s TutorAgent (`brain.py`) run under **two separate
`InMemorySessionService` instances** (`main.py`'s top-level `session_service`, app name
`"nityam"`; `brain.py`'s own `_sessions`, app name `"nityam-brain"`). The turn buffer
`_record` builds (Task 2) lives in the second one. `ws_endpoint` has no reachable handle on
`brain.py`'s internal `_sessions` object, so `session_service.get_session(...)` from `main.py`
would never see it. This is exactly the situation `google_cloud_storage_integration.md` §7 item 4
flagged without resolving — Task 2's write-through *is* the resolution: read the buffer back
from Redis instead.

- [ ] **Step 1: Write the failing test**

**This test needs real credentials, and costs one small Gemini call** — because
`_flush_session_memory` (Step 4) is deliberately never invoked in mock mode (mock mode's whole
point, per `README.md`, is zero network calls; the Reflect call inside `close_session` is a real
`generate_content` call regardless of which mode taught the lesson). This mirrors
`tests/test_live.py`'s own established pattern exactly: skip when `NITYAM_AUTH` is unset or
`mock`, inherit the real environment otherwise (no env override, unlike `test_wire.py`'s
mock-forcing `Server`). The test itself never sends audio or waits for a live reply — it connects
just long enough to get the session frame, then disconnects immediately, so the only real-model
cost is the one Reflect call inside `close_session`, not a live conversation.

Create `backend/tests/test_close_session_wiring.py`:

```python
"""close_session is now actually invoked when a WebSocket session ends —
before this task it silently never was, and only the debug log file got
closed. Needs real credentials (NITYAM_AUTH != mock) because
_flush_session_memory is deliberately a no-op in mock mode — see this
task's own note in the plan. Seeds a turn into Memorystore under the test's
session id (bypassing an actual live conversation, which this test isn't
about), connects just long enough to get the session frame, disconnects, and
checks the store for a session_log afterward.

    NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_close_session_wiring
"""
from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from app.auth import load_env  # noqa: E402

load_env()

from app.memory import short_term, store  # noqa: E402
from tests._firebase_test_tokens import mint_id_token  # noqa: E402

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
        self.port = port
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}  # real NITYAM_AUTH, inherited as-is
        self.proc = subprocess.Popen(
            [str(ROOT / ".venv/bin/uvicorn"), "app.main:app",
             "--port", str(port), "--log-level", "warning"],
            cwd=ROOT, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )

    def wait(self, timeout: float = 30) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                print(self.proc.stdout.read()[-2000:])
                return False
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/health", timeout=1
                ) as r:
                    if r.status == 200:
                        return True
            except Exception:
                time.sleep(0.3)
        return False

    def stop(self) -> None:
        self.proc.kill()
        self.proc.wait(timeout=5)


async def run(port: int, session_id: str) -> None:
    import websockets

    await short_term.append_turn(session_id, {
        "turn": 1, "role": "student", "text": "why 45 degrees?",
        "concept_id": "projectile.horizontal_range", "artifact_id": None,
    })
    await short_term.append_turn(session_id, {
        "turn": 2, "role": "tutor", "text": "because sin(2θ) peaks there",
        "concept_id": "projectile.horizontal_range", "artifact_id": None,
    })

    token = mint_id_token("demo@nityam.local", "nityam-demo-2026")
    url = f"ws://127.0.0.1:{port}/ws/demo_student/{session_id}?token={token}"
    async with websockets.connect(url) as ws:
        await ws.recv()  # the session frame — then disconnect immediately
    # ws_endpoint's finally block runs server-side after the close; give the
    # one Reflect call room to finish.
    await asyncio.sleep(6.0)


def main() -> int:
    mode = os.getenv("NITYAM_AUTH", "").strip().lower()
    if mode in ("", "mock"):
        print("NITYAM_AUTH is mock or unset — nothing to test against. Skipping.")
        return 0

    port = free_port()
    session_id = "s_close_session_wiring_test"
    server = Server(port)
    try:
        if not server.wait():
            check("the server starts against real credentials", False, "it did not come up")
            return 1
        check("the server starts against real credentials", True, f"port {port}, mode {mode}")
        asyncio.run(run(port, session_id))
    finally:
        server.stop()

    conn = store.connect()
    log = store.get_session_log(conn, session_id)
    check("a session_log now exists after the socket closes", log is not None)
    if log:
        check("it carries the turns that were in the buffer", len(log.turns) == 2, repr(log.turns))

    print()
    print(f"{FAILED} failed" if FAILED else "all passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_close_session_wiring`
Expected: `FAIL a session_log now exists after the socket closes` (it's `None` — `close_session`
is not yet called).

- [ ] **Step 3: Add the import**

Alongside the existing `from app import incoming, sessions, user_auth` line in
`backend/app/main.py`, add:

```python
from app import incoming, sessions, user_auth  # noqa: E402
from app.memory import short_term, store  # noqa: E402
from app.session_close import close_session as _close_session_memory  # noqa: E402
```

(Named `_close_session_memory` on import specifically to avoid any reader confusing it with
`logs.close_session` two lines below it in the `finally` block — they do different things and
the existing code already has this naming collision across two modules.)

- [ ] **Step 4: Wire the real call into the `finally` block**

`backend/app/main.py` lines 169-172 currently read:

```python
    finally:
        log.info("closed user=%s", user_id)
        # Prints the turn timeline to the terminal and appends it to the file.
        logs.close_session(session_id)
```

becomes:

```python
    finally:
        log.info("closed user=%s", user_id)
        if MODE != "mock":
            await _flush_session_memory(session_id, user_id)
        # Prints the turn timeline to the terminal and appends it to the file.
        logs.close_session(session_id)
```

Add the new `_flush_session_memory` function right after `ws_endpoint` (i.e. after its closing
`logs.close_session(session_id)` line, before `async def send_control`):

```python
async def _flush_session_memory(session_id: str, student_id: str) -> None:
    """The actual memory write `close_session` exists for — session_log
    persisted, dpm_profile/teaching_memory updated via one Reflect call.

    Buffer comes from Redis, not ADK session state: TutorAgent's own Runner
    (app/agents/brain.py) keeps a SEPARATE InMemorySessionService from this
    module's, so tool_context.state["turn_buffer"] is not reachable from
    here — the write-through this same session's Task 2 added to _record()
    is what makes this readable at all. Never raised past this function: a
    memory-write failure must not prevent the WebSocket from closing cleanly.
    """
    from google import genai

    state = sessions.get(session_id, student_id=student_id)
    try:
        buffer = await short_term.get_turn_buffer(session_id)
        conn = store.connect()
        client = genai.Client()
        _close_session_memory(
            conn, session_id, student_id, state.started_at, buffer, client,
        )
        log.info("session memory flushed: %s turn(s)", len(buffer))
    except Exception:  # noqa: BLE001 - closing the socket must not fail on this
        log.warning("failed to flush session memory for %s", session_id, exc_info=True)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_close_session_wiring`
Expected: both checks `ok`, `all passed`. (If the log shows `RESOURCE_EXHAUSTED`, that's Express
Mode quota, not this fix — matching `test_live.py`'s own documented note on the same failure
mode; retry in a few minutes.)

- [ ] **Step 6: Confirm the mock-mode server still starts and the existing suite is unaffected**

```bash
cd backend
.venv/bin/python -m tests.test_wire
.venv/bin/python -m tests.test_ws_auth
```
Expected: no new failures beyond the pre-existing, unrelated mock-teaching ones already
documented earlier in this project.

- [ ] **Step 7: Commit**

```bash
git add backend/app/main.py backend/tests/test_close_session_wiring.py
git commit -m "fix: actually call close_session when a WebSocket session ends"
```

---

## Self-review notes (already applied above)

- **Spec coverage**: §3.1 (GCS) → Task 1. §3.2 (Memorystore) → Task 2. §3.3 (close_session fix)
  → Task 3. §3.4 (embedding dimension) belongs to the Shruti sync bridge plan (Phase 2), not
  here — noted, not a gap in this plan. §2 (Cloud Run) is a deployment concern this plan's tests
  don't touch directly; nothing here is Cloud-Run-specific beyond using the same env vars and
  ADC pattern already in place.
- **Type consistency**: `_record` and `log_artifact_evidence` are both `async def` end to end,
  and every call site shown (`brain.py:303`, the ADK tool-dispatch path for
  `log_artifact_evidence`) awaits them. `close_session` (the memory-writing one) is imported
  under an alias specifically to avoid the pre-existing name collision with `logs.close_session`.
- **Corrected against the spec during planning, not just implemented as originally written**:
  the spec's illustrative code (from the earlier research doc) assumed `log_turn` in
  `app/memory/tools.py` was the live turn-recording path. Reading the actual code found it is
  not — `brain.py`'s `_record` replaced it, specifically to avoid a model round trip. This plan
  targets `_record`, not the dead `log_turn`, and leaves `log_turn` untouched (unused, but not
  this task's concern to remove).
- **Two more corrections caught during this plan's own self-review**: Task 3's test originally
  ran the server in mock mode, which would never exercise the fix at all —
  `_flush_session_memory` is intentionally a no-op in mock mode (Global Constraints), so the test
  needed real credentials instead, mirroring `test_live.py`'s skip-when-mock convention. And the
  test's WebSocket connection needed a real minted token — `ws_endpoint` now rejects any
  connection without one (from this project's earlier Firebase-auth work) *before* reaching the
  code this task adds, so a tokenless test connection would have failed for an unrelated reason.
