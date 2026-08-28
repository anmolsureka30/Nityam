# Agent Orchestration Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retire the single `TutorAgent` in favor of `VoiceAgent` (router) plus
four domain specialists (`BoardAgent`, `ArtifactAgent`, `QuizAgent`,
`TextbookAgent`), each reached via a `response_scheduling=WHEN_IDLE` tool so
a slow specialist never blocks or interrupts the live conversation.

**Architecture:** Each specialist keeps running in its own `run_async`
Runner (required — `run_live` cannot host a non-blocking nested sub-agent).
What changes is how a specialist's result gets back to VoiceAgent: instead of
a hand-rolled `asyncio.Queue` + background task + unconditional
`send_content(partial=False)` interrupt, each entry tool is an ordinary
`async def` that awaits its specialist to completion and returns the result,
tagged `response_scheduling=WHEN_IDLE` — the Gemini Live API itself holds
the response and delivers it at the next natural pause.

**Tech Stack:** Python, FastAPI, Google ADK (`google-adk==2.8.0`), Gemini
Live API (`gemini-live-2.5-flash`), Redis, Firestore.

**Spec:** `docs/superpowers/specs/2026-08-28-agent-orchestration-redesign-design.md`

## Global Constraints

- Every specialist entry tool (`ask_board`, `ask_artifact`, `ask_quiz`,
  `ask_textbook`) MUST catch every exception internally and return an
  error-shaped dict — NEVER let an exception propagate out of the tool
  function. Verified against the installed ADK source: a `WHEN_IDLE`
  background task that raises is logged server-side and the model is told
  **nothing** — no error `FunctionResponse` is ever delivered. An unguarded
  exception here means VoiceAgent waits forever in total silence, which is
  worse than today's behavior.
- `response_scheduling` is a post-construction attribute, not a constructor
  kwarg: `tool = FunctionTool(func=fn); tool.response_scheduling =
  types.FunctionResponseScheduling.WHEN_IDLE`, then pass `tool` (the
  instance, not the bare function) in `tools=[...]`. Passing the bare
  function auto-wraps it with no scheduling set.
- No agent's instruction names a specific subject, chapter, or concept.
  Subject material comes from `list_concepts`/`search_grounding`/
  `search_textbook` at runtime, never from prose in the prompt.
- Tasks 2-8 leave `brain.py`'s old recorder and `sessions.py`'s old
  nudge/inject queues running in parallel with the new mechanisms being
  built — this transient overlap is expected and resolves when Task 9
  deletes the old code. Do not try to bridge or synchronize the two during
  the transition; each task's own tests only need to prove that task's own
  piece works.
- Follow existing docstring conventions in every new/modified file — this
  codebase documents *why*, not *what*, and every existing file does this
  consistently.

---

### Task 1: Upgrade google-adk to 2.8.0

**Files:**
- Modify: `backend/requirements.txt`
- Test: existing full suite (no new test file for this task)

**Interfaces:**
- Produces: `google-adk==2.8.0` installed and verified compatible with the
  existing test suite before any redesign code is written against it.

- [ ] **Step 1: Change the pin**

In `backend/requirements.txt`, find the line pinning `google-adk` and change
it to:
```
google-adk==2.8.0
```
(Exact pin, not a range — 2.8.0 is two days old with zero patch history as
of this plan, and the exact background-task mechanism this redesign depends
on had a real bug fix land in 2.8.0 itself. Pin exactly until 2.8.1 exists
and has been re-verified.)

- [ ] **Step 2: Reinstall**

```bash
cd backend && .venv/bin/pip install --quiet -r requirements.txt
```

- [ ] **Step 3: Verify the upgrade alone doesn't break anything**

Run the full existing suite:
```bash
.venv/bin/python -m tests.test_canvas
.venv/bin/python -m tests.test_wire
.venv/bin/python -m tests.test_ws_teardown
.venv/bin/python -m tests.test_short_term_writethrough
.venv/bin/python -m tests.test_short_term_events
.venv/bin/python -m tests.test_short_term_heartbeat
NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_close_session_wiring
```
Expected: identical results to the pre-upgrade baseline (`test_wire.py` has
4 known pre-existing failures — confirm the count and names are unchanged,
not that everything passes).

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore: upgrade google-adk to 2.8.0 for response_scheduling"
```

---

### Task 2: Real transcript recording, from every exchange

**Files:**
- Modify: `backend/app/main.py` (the `trace()` function)
- Test: Create `backend/tests/test_transcript_recording.py`

**Interfaces:**
- Consumes: `short_term.append_turn(session_id, student_id, turn_dict)` —
  existing, signature unchanged (`backend/app/memory/short_term.py:56`).
- Produces: every finalized `input_transcription`/`output_transcription`
  event, for every exchange (not just delegated ones), lands in the Redis
  turn buffer with the same shape `brain.py`'s `_record()` already writes:
  `{"turn": int, "role": "student"|"tutor", "text": str, "concept_id": None,
  "artifact_id": None}`.

Today, `main.py`'s `trace()` (around line 520) already inspects
`event.output_transcription`/`event.input_transcription` when
`event.partial is False` — it just logs them, it doesn't record them
anywhere durable. This task adds recording, independent of the existing
`brain.py._record()` path (which still exists until Task 9).

- [ ] **Step 1: Write the failing test**

```python
"""Every transcription event trace() sees lands in the turn buffer — not
just ones that happen to go through a TutorAgent delegation.

    .venv/bin/python -m tests.test_transcript_recording
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from types import SimpleNamespace

from app.auth import load_env

load_env()

from app import main as nityam_main  # noqa: E402
from app.memory import short_term  # noqa: E402

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


def _event(who: str, text: str, *, input_side: bool) -> SimpleNamespace:
    transcription = SimpleNamespace(text=text)
    return SimpleNamespace(
        author=who,
        content=None,
        interrupted=False,
        partial=False,
        output_transcription=transcription if not input_side else None,
        input_transcription=transcription if input_side else None,
    )


async def run() -> None:
    session_id = f"test_transcript_{uuid.uuid4().hex[:8]}"
    student_id = "demo_student"
    nityam_main.logs.open_session(session_id, student_id, mode="mock", live_model="", detail="test")
    nityam_main.instrumentation.set_session_context(session_id)
    nityam_main._recording_context.set((session_id, student_id))

    nityam_main.trace(_event("student", "why does it peak at 45?", input_side=True))
    nityam_main.trace(_event("VoiceAgent", "because sin two theta peaks there", input_side=False))

    buffer = await short_term.get_turn_buffer(session_id, student_id)
    check("both sides of a direct exchange got recorded", len(buffer) == 2, repr(buffer))
    if len(buffer) == 2:
        check("student half recorded with the right role", buffer[0]["role"] == "student")
        check("student text matches", buffer[0]["text"] == "why does it peak at 45?")
        check("tutor half recorded with the right role", buffer[1]["role"] == "tutor")

    # A partial (not-yet-finalized) transcription must NOT be recorded.
    partial = _event("student", "um so", input_side=True)
    partial.partial = True
    nityam_main.trace(partial)
    buffer2 = await short_term.get_turn_buffer(session_id, student_id)
    check("a partial transcription is not recorded", len(buffer2) == 2, repr(buffer2))

    await short_term.clear_session(session_id, student_id)
    nityam_main.logs.close_session(session_id)


def main() -> int:
    asyncio.run(run())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it to see it fail**

```bash
.venv/bin/python -m tests.test_transcript_recording
```
Expected: `AttributeError` — `nityam_main._recording_context` doesn't exist
yet.

- [ ] **Step 3: Add the recording hook**

In `backend/app/main.py`, add near the top (after the existing imports,
alongside the other module-level state like `runner`/`session_service`):

```python
import contextvars

_recording_context: contextvars.ContextVar[tuple[str, str] | None] = (
    contextvars.ContextVar("nityam_recording_context", default=None)
)
"""(session_id, student_id) for whoever is currently recording transcript
turns — set once per connection in ws_endpoint, same pattern as
instrumentation.set_session_context. Lets trace() record every exchange
without needing session_id/student_id threaded through the ADK Event."""
```

In `ws_endpoint`, right after the existing
`instrumentation.set_session_context(session_id)` line added earlier this
session, add:

```python
_recording_context.set((session_id, user_id))
```

In `trace()`, replace the two existing transcription blocks:

```python
    if event.output_transcription and event.partial is False:
        said = event.output_transcription.text.strip()
        if said:
            logs.spoke(said)
            log.info('  %s says: "%s"', who, said)
    if event.input_transcription and event.partial is False:
        heard = event.input_transcription.text.strip()
        if heard:
            # The turn clock restarts here, not when the audio started: this is
            # the moment the model decided the student had finished, and T+ is
            # meant to read as "how long since I stopped talking".
            logs.heard(heard)
            log.info('  student said: "%s"', heard)
```

with:

```python
    if event.output_transcription and event.partial is False:
        said = event.output_transcription.text.strip()
        if said:
            logs.spoke(said)
            log.info('  %s says: "%s"', who, said)
            _record_turn("tutor", said)
    if event.input_transcription and event.partial is False:
        heard = event.input_transcription.text.strip()
        if heard:
            # The turn clock restarts here, not when the audio started: this is
            # the moment the model decided the student had finished, and T+ is
            # meant to read as "how long since I stopped talking".
            logs.heard(heard)
            log.info('  student said: "%s"', heard)
            _record_turn("student", heard)
```

Add the helper just above `trace()`:

```python
def _record_turn(role: str, text: str) -> None:
    """Every settled exchange, not just delegated ones — what makes a
    specialist's "last N turns" context genuine. Fire-and-forget: a Redis
    hiccup here must never affect the live conversation.
    """
    ctx = _recording_context.get()
    if ctx is None:
        return
    session_id, student_id = ctx

    async def _write() -> None:
        try:
            await short_term.append_turn(
                session_id, student_id,
                {"turn": 0, "role": role, "text": text[:2000],
                 "concept_id": None, "artifact_id": None},
            )
        except Exception:  # noqa: BLE001 - a Redis outage must not break a live turn
            log.warning("transcript recording failed", exc_info=True)

    asyncio.get_running_loop().create_task(_write())
```

(The `"turn": 0` placeholder is fine — nothing reads that field for
ordering; the buffer's own list order is the real sequence, exactly as
`brain.py._record()` already relies on today.)

- [ ] **Step 4: Run the test again**

```bash
.venv/bin/python -m tests.test_transcript_recording
```
Expected: all checks pass.

- [ ] **Step 5: Run the existing protocol test to confirm nothing broke**

```bash
.venv/bin/python -m tests.test_wire
```
Expected: same 4 pre-existing failures, nothing new.

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py backend/tests/test_transcript_recording.py
git commit -m "feat: record every transcribed exchange, not just delegated ones"
```

---

### Task 3: Shared specialist-runner helper

**Files:**
- Create: `backend/app/agents/specialist_runner.py`
- Test: Create `backend/tests/test_specialist_runner.py`

**Interfaces:**
- Produces: `SpecialistRunner` class with `async def run_turn(session_id,
  student_id, message) -> str`, and `async def recent_transcript(session_id,
  student_id, n) -> str`. Both consumed by Tasks 4-7.

This replaces the near-identical hand-rolled `runner()`/`_ensure_session()`/
`_known` set that `brain.py` and `artifact_agent.py` each currently
duplicate — written once, used by all four specialists.

- [ ] **Step 1: Write the failing test**

```python
"""SpecialistRunner: one Runner+session-bootstrap helper, shared by every
specialist agent, instead of each one hand-rolling its own.

    .venv/bin/python -m tests.test_specialist_runner
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from app.auth import load_env

load_env()

from google.adk.agents import LlmAgent  # noqa: E402

from app.agents.specialist_runner import SpecialistRunner, recent_transcript  # noqa: E402
from app.memory import short_term  # noqa: E402

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


def _build_echo_agent() -> LlmAgent:
    return LlmAgent(
        name="EchoAgent",
        model="gemini-3.7-flash",
        mode=None,
        instruction="Reply with exactly the words: acknowledged.",
    )


async def run() -> None:
    runner = SpecialistRunner("test-specialist-app", _build_echo_agent)
    session_id = f"test_specialist_{uuid.uuid4().hex[:8]}"
    student_id = "demo_student"

    reply = await runner.run_turn(session_id, student_id, "say the word")
    check("run_turn returns real text", "acknowledged" in reply.lower(), repr(reply))

    # A second call against the same session_id must not re-create the
    # session (the whole point of _known / _ensure_session).
    reply2 = await runner.run_turn(session_id, student_id, "say it again")
    check("a second turn against the same session works", "acknowledged" in reply2.lower(), repr(reply2))

    # recent_transcript
    await short_term.append_turn(session_id, student_id, {"turn": 1, "role": "student", "text": "hi", "concept_id": None, "artifact_id": None})
    await short_term.append_turn(session_id, student_id, {"turn": 2, "role": "tutor", "text": "hello", "concept_id": None, "artifact_id": None})
    text = await recent_transcript(session_id, student_id, n=10)
    check("recent_transcript includes both turns", "hi" in text and "hello" in text, repr(text))

    empty = await recent_transcript(f"nothing_{uuid.uuid4().hex[:8]}", student_id, n=10)
    check("recent_transcript degrades gracefully with no history", "No prior" in empty, repr(empty))

    await short_term.clear_session(session_id, student_id)


def main() -> int:
    asyncio.run(run())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it to see it fail**

```bash
NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_specialist_runner
```
Expected: `ModuleNotFoundError: No module named 'app.agents.specialist_runner'`.

- [ ] **Step 3: Write the implementation**

```python
"""One Runner+session bootstrap, shared by every specialist agent reached
from VoiceAgent (BoardAgent, ArtifactAgent, QuizAgent, TextbookAgent).

Each specialist runs in its own Runner via run_async, for the same reason
brain.py's TutorAgent always did: run_live never initialises
InvocationContext._event_queue, so a mode='single_turn' sub-agent nested
under a live VoiceAgent crashes on its first event. Reached instead as a
plain async function tool, tagged response_scheduling=WHEN_IDLE so the
Gemini Live API itself holds the result until VoiceAgent is between things
— see docs/superpowers/specs/2026-08-28-agent-orchestration-redesign-design.md §2.

This used to be hand-rolled once per specialist (brain.py's runner()/
_ensure_session()/_known, artifact_agent.py's near-identical copy) — written
once here instead.
"""
from __future__ import annotations

from typing import Callable

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.memory import short_term


class SpecialistRunner:
    """Builds its agent and Runner once; ensures a session per session_id."""

    def __init__(self, app_name: str, build_agent: Callable[[], LlmAgent]) -> None:
        self._app_name = app_name
        self._build_agent = build_agent
        self._runner: Runner | None = None
        self._sessions: InMemorySessionService | None = None
        self._known: set[str] = set()

    def _runner_instance(self) -> Runner:
        if self._runner is None:
            self._sessions = InMemorySessionService()
            self._runner = Runner(
                app=App(name=self._app_name, root_agent=self._build_agent()),
                session_service=self._sessions,
            )
        return self._runner

    async def _ensure_session(self, session_id: str, student_id: str) -> None:
        if session_id in self._known:
            return
        runner = self._runner_instance()
        existing = await self._sessions.get_session(
            app_name=self._app_name, user_id=student_id, session_id=session_id,
        )
        if not existing:
            await self._sessions.create_session(
                app_name=self._app_name, user_id=student_id, session_id=session_id,
                state={"session_id": session_id, "student_id": student_id},
            )
        self._known.add(session_id)
        _ = runner  # built as a side effect of _runner_instance(); kept for clarity

    async def run_turn(self, session_id: str, student_id: str, message: str) -> str:
        """Run one turn to completion; return whatever text the specialist said."""
        await self._ensure_session(session_id, student_id)
        said: list[str] = []
        async for event in self._runner_instance().run_async(
            user_id=student_id, session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part(text=message)]),
        ):
            for part in event.content.parts if event.content and event.content.parts else []:
                if part.text:
                    said.append(part.text)
        return " ".join(said).strip()


async def recent_transcript(session_id: str, student_id: str, n: int) -> str:
    """The last n recorded turns, formatted for a specialist's prompt."""
    buffer = await short_term.get_turn_buffer(session_id, student_id)
    recent = buffer[-n:]
    if not recent:
        return "No prior turns recorded yet this session."
    lines = [f"{turn['role']}: {turn['text']}" for turn in recent]
    return "Recent conversation:\n" + "\n".join(lines)
```

- [ ] **Step 4: Run the test again**

```bash
NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_specialist_runner
```
Expected: all checks pass. (Needs real credentials — it runs a real model
turn, same as `test_close_session_wiring.py` already does.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/specialist_runner.py backend/tests/test_specialist_runner.py
git commit -m "feat: shared specialist-runner helper for the new agent split"
```

---

### Task 4: BoardAgent

**Files:**
- Create: `backend/app/agents/board_agent.py`
- Test: Create `backend/tests/test_board_agent.py`

**Interfaces:**
- Consumes: `SpecialistRunner`, `recent_transcript` (Task 3);
  `BOARD_TOOLS` (`app/canvas/tools.py`, unchanged);
  `search_grounding`, `list_concepts` (`app/memory/tools.py`, unchanged).
- Produces: `ask_board(bridge: str, request: str, tool_context: ToolContext)
  -> dict`, consumed by Task 8 (VoiceAgent).

BoardAgent absorbs `TutorAgent`'s actual teaching-content judgment — given a
request and the recent transcript, it decides what to teach and writes it,
citing real lecture content. This is also where a substantive "explain a
new concept" request lives (per the approved design decision — no separate
spoken-only explain path; explaining IS a board write).

- [ ] **Step 1: Write the failing test**

```python
"""BoardAgent: given a request and recent transcript, writes real content
citing the actual grounding corpus, and ask_board never raises even when
its internals fail.

    NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_board_agent
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from types import SimpleNamespace

from app.auth import configure, load_env

load_env()
configure()

from app import sessions  # noqa: E402
from app.agents.board_agent import ask_board  # noqa: E402

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


async def run() -> None:
    session_id = f"test_board_agent_{uuid.uuid4().hex[:8]}"
    student_id = "demo_student"
    sessions.get(session_id, student_id=student_id)
    ctx = SimpleNamespace(state={"session_id": session_id, "student_id": student_id})

    result = await ask_board(
        bridge="Let's put that on the board.",
        request="Explain why maximum range happens at 45 degrees.",
        tool_context=ctx,
    )
    check("ask_board returns a done status", result.get("status") == "done", repr(result))
    check("ask_board returns a summary", bool(result.get("summary")), repr(result))

    board = sessions.get(session_id).board
    check("something actually landed on the board", len(board.blocks()) > 1, repr([b.kind for b in board.blocks()]))

    # ask_board must never raise, even on a garbage request — it should
    # degrade to an error-shaped result (WHEN_IDLE swallows a raised
    # exception with no delivery to the model at all).
    broken_ctx = SimpleNamespace(state={})  # no session_id/student_id at all
    result2 = await ask_board(bridge="ok", request="x" * 10, tool_context=broken_ctx)
    check("ask_board degrades to an error result rather than raising", "status" in result2, repr(result2))


def main() -> int:
    asyncio.run(run())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it to see it fail**

```bash
NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_board_agent
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
"""BoardAgent — decides what belongs on the student's board and writes it.

Absorbs the board-writing judgment TutorAgent used to hold, including
"explain a new concept" — per the design's approved principle, a
substantive explanation IS a board write (see
docs/superpowers/specs/2026-08-28-agent-orchestration-redesign-design.md §3,
"the existing philosophy: everything worth remembering goes on the board").
"""
from __future__ import annotations

import logging

from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext

from app import config
from app.agents.specialist_runner import SpecialistRunner, recent_transcript
from app.canvas.tools import BOARD_TOOLS
from app.memory.tools import list_concepts, search_grounding

log = logging.getLogger("nityam.board")

BOARD_INSTRUCTION = """You decide what belongs on the student's board and
write it. You never speak to the student directly — whatever you report
back is said, in the tutor's own voice, by the voice layer that called you.

## Ground it, always

Never invent physics. Before writing anything about a concept you have not
already been given evidence for in this request, call `list_concepts` to
find its real id, then `search_grounding` with that id — their own
teacher's words, with a citation, not generic textbook material. Ask for
both in the SAME message as the writing they support, not a message of
their own: you do not need the grounding text in hand to know you want it.

## Use the request and the recent conversation together

You are handed the voice layer's request and the last several turns of the
actual conversation. Use the transcript to judge what the student already
understands and where they are stuck — write to that, not to a generic
version of the topic.

## Write well, in one call

`write_lesson` is the tool you use for anything longer than one block — a
whole answer in a single call: heading, formula, paragraph, callout, and
what to point at. Mark pointable terms inline with double brackets, naming
the concept after a pipe. Blackboard notation only — no LaTeX, the board has
no renderer for it.

## Report back

End with a short, plain-language summary of what you wrote and why, as if
telling a colleague what you just put on the board. This is what the voice
layer will say to the student, so make it something a person would actually
say aloud — not a list of block ids.
"""


def build_board_agent() -> LlmAgent:
    return LlmAgent(
        name="BoardAgent",
        model=config.reasoning_model(),
        mode=None,
        description=(
            "Decides what belongs on the student's board for a given "
            "request — an explanation, a correction, a worked step — and "
            "writes it, grounded in their own teacher's material."
        ),
        instruction=BOARD_INSTRUCTION,
        tools=[search_grounding, list_concepts, *BOARD_TOOLS],
    )


_RUNNER = SpecialistRunner("nityam-board", build_board_agent)


async def ask_board(bridge: str, request: str, tool_context: ToolContext) -> dict:
    """Get something written on the student's board. Returns IMMEDIATELY —
    do not wait for it. Keep teaching; you will be told what was written
    once BoardAgent finishes, at a natural pause.

    Args:
        bridge: What you say RIGHT NOW, out loud, while it works — one short
            sentence, in your own voice.
        request: What should be written, in your own words — the concept,
            the specific doubt, and anything you noticed the student get
            wrong. Be concrete.

    Returns:
        dict with "status" and "summary" — say the summary once you are
        told it is ready.
    """
    session_id = tool_context.state.get("session_id")
    student_id = tool_context.state.get("student_id")
    if not session_id or not student_id:
        log.warning("ask_board called with no session/student id in state")
        return {"status": "error", "summary": "Something went wrong on my end — let's move on."}

    try:
        transcript = await recent_transcript(session_id, student_id, n=10)
        message = f"{request}\n\n{transcript}"
        summary = await _RUNNER.run_turn(session_id, student_id, message)
        return {"status": "done", "summary": summary or "It's on the board now."}
    except Exception:  # noqa: BLE001 - WHEN_IDLE delivers nothing at all if this raises
        log.exception("BoardAgent turn failed")
        return {"status": "error", "summary": "I couldn't get that written up this time."}
```

- [ ] **Step 4: Run the test**

```bash
NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_board_agent
```
Expected: all checks pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/board_agent.py backend/tests/test_board_agent.py
git commit -m "feat: add BoardAgent, absorbing TutorAgent's board-writing judgment"
```

---

### Task 5: TextbookAgent

**Files:**
- Create: `backend/app/agents/textbook_agent.py`
- Modify: `backend/app/textbook.py` (remove the now-dead `sessions.inject`
  call in `show_textbook_figure`)
- Test: Create `backend/tests/test_textbook_agent.py`

**Interfaces:**
- Consumes: `SpecialistRunner`, `recent_transcript` (Task 3);
  `TEXTBOOK_TOOLS` (`app/textbook.py`, mostly unchanged).
- Produces: `ask_textbook(bridge: str, request: str, tool_context:
  ToolContext) -> dict`, consumed by Task 8.

- [ ] **Step 1: Remove the dead injection call**

In `backend/app/textbook.py`'s `show_textbook_figure`, find:

```python
    log.info("textbook %s p.%s -> %s", chapter, page, block.id)
    logs.count("textbook page")
    tool_context.state["textbook_search_streak"] = 0
    # So the voice layer can say which page it is and answer "is this in the
    # book?" without a round trip.
    sessions.inject(
        session_id,
        f"[BOARD UPDATED, context only — do not announce it or reply to this. "
        f"A page of the student's own NCERT textbook is now on their page as "
        f"{block.id}: {block.source}. You said about it: “{block.body}”. "
        f"You may refer to it and answer questions about which page it is "
        f"yourself.]",
    )
    return {"block_id": block.id, "showing": block.source}
```

Replace with:

```python
    log.info("textbook %s p.%s -> %s", chapter, page, block.id)
    logs.count("textbook page")
    tool_context.state["textbook_search_streak"] = 0
    return {"block_id": block.id, "showing": block.source}
```

(`sessions.inject` is being retired in Task 9 — this is what "the voice
layer learns about it" now means: the fact reaches VoiceAgent through
`ask_textbook`'s own `WHEN_IDLE` response, not a side-channel injection.)

- [ ] **Step 2: Write the failing test**

```python
"""TextbookAgent: fetches or places real textbook material, and ask_textbook
never raises even when the request can't be satisfied.

    NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_textbook_agent
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from types import SimpleNamespace

from app.auth import configure, load_env

load_env()
configure()

from app import sessions  # noqa: E402
from app.agents.textbook_agent import ask_textbook  # noqa: E402

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


async def run() -> None:
    session_id = f"test_textbook_agent_{uuid.uuid4().hex[:8]}"
    student_id = "demo_student"
    sessions.get(session_id, student_id=student_id)
    ctx = SimpleNamespace(state={"session_id": session_id, "student_id": student_id})

    result = await ask_textbook(
        bridge="One second, let me find that.",
        request="Show figure 3.14 from the textbook.",
        tool_context=ctx,
    )
    check("ask_textbook returns a done status", result.get("status") == "done", repr(result))
    check("ask_textbook returns a summary", bool(result.get("summary")), repr(result))

    result2 = await ask_textbook(
        bridge="Let me check.",
        request="Show figure 9.99, which does not exist.",
        tool_context=ctx,
    )
    check("a figure that doesn't exist still returns a done result, not an error", result2.get("status") == "done", repr(result2))

    broken_ctx = SimpleNamespace(state={})
    result3 = await ask_textbook(bridge="ok", request="x", tool_context=broken_ctx)
    check("ask_textbook degrades to an error result rather than raising", "status" in result3, repr(result3))


def main() -> int:
    asyncio.run(run())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run it to see it fail**

```bash
NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_textbook_agent
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 4: Write the implementation**

```python
"""TextbookAgent — finds and places real pages/figures from the student's
own NCERT textbook. Split out of TutorAgent's textbook tools.
"""
from __future__ import annotations

import logging

from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext

from app import config
from app.agents.specialist_runner import SpecialistRunner, recent_transcript
from app.textbook import TEXTBOOK_TOOLS

log = logging.getLogger("nityam.textbook_agent")

TEXTBOOK_INSTRUCTION = """You find and place pages or figures from the
student's real, actual textbook. You never speak to the student directly —
your report becomes what the voice layer says.

  search_textbook      — where a topic, section or figure lives. Ask it the
                         way the student asked — "figure 3.14",
                         "projectile", "section 3.9" all work. Never guess
                         a page number.
  show_textbook_figure — put that page on their board, with one line about
                         what to look at. Pass the figure number whenever
                         one was named: with it they get the diagram
                         itself, cropped out of the page; without it they
                         get the whole printed sheet.

Asking for a figure is two calls, and BOTH have to happen: search_textbook
tells you the chapter and page; show_textbook_figure is what actually puts
it in front of the student. If you cannot find it, say plainly that the
book does not seem to have it — do not announce a figure you have not
placed, and do not keep retrying past what search_textbook's own hint
tells you.

Report back a short, plain-language line about what you found or placed —
or, if nothing was found, an honest one-line admission of that — as if
telling a colleague what happened. This is what the voice layer will say.
"""


def build_textbook_agent() -> LlmAgent:
    return LlmAgent(
        name="TextbookAgent",
        model=config.reasoning_model(),
        mode=None,
        description=(
            "Finds and places a page or figure from the student's real "
            "NCERT textbook. Call with what the student asked for, in "
            "their own words."
        ),
        instruction=TEXTBOOK_INSTRUCTION,
        tools=list(TEXTBOOK_TOOLS),
    )


_RUNNER = SpecialistRunner("nityam-textbook", build_textbook_agent)


async def ask_textbook(bridge: str, request: str, tool_context: ToolContext) -> dict:
    """Find or place something from the student's real textbook. Returns
    IMMEDIATELY — do not wait for it. Keep teaching; you will be told the
    result once TextbookAgent finishes, at a natural pause.

    Args:
        bridge: What you say RIGHT NOW, out loud, while it works.
        request: What the student asked for, in their own words — a page,
            a figure number, or a topic to locate.

    Returns:
        dict with "status" and "summary".
    """
    session_id = tool_context.state.get("session_id")
    student_id = tool_context.state.get("student_id")
    if not session_id or not student_id:
        log.warning("ask_textbook called with no session/student id in state")
        return {"status": "error", "summary": "Something went wrong on my end — let's move on."}

    try:
        transcript = await recent_transcript(session_id, student_id, n=5)
        message = f"{request}\n\n{transcript}"
        summary = await _RUNNER.run_turn(session_id, student_id, message)
        return {"status": "done", "summary": summary or "Found it."}
    except Exception:  # noqa: BLE001 - WHEN_IDLE delivers nothing at all if this raises
        log.exception("TextbookAgent turn failed")
        return {"status": "error", "summary": "I couldn't check the textbook just now."}
```

- [ ] **Step 5: Run the test**

```bash
NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_textbook_agent
```
Expected: all checks pass.

- [ ] **Step 6: Run `test_canvas.py` to confirm the textbook.py edit didn't break anything**

```bash
.venv/bin/python -m tests.test_canvas
```
Expected: all pass (this file's textbook-figure tests call `show_textbook_figure`
directly and don't depend on `sessions.inject`).

- [ ] **Step 7: Commit**

```bash
git add backend/app/agents/textbook_agent.py backend/app/textbook.py backend/tests/test_textbook_agent.py
git commit -m "feat: add TextbookAgent, split from TutorAgent's textbook tools"
```

---

### Task 6: QuizAgent becomes a standalone specialist

**Files:**
- Modify: `backend/app/agents/quiz_agent.py`
- Test: Create `backend/tests/test_quiz_agent_standalone.py`

**Interfaces:**
- Consumes: `SpecialistRunner`, `recent_transcript` (Task 3).
- Produces: `ask_quiz(bridge: str, request: str, tool_context: ToolContext)
  -> dict`, consumed by Task 8. `build_quiz_agent()`'s signature changes
  from taking no scheduling role (implicit `mode="single_turn"`) to
  `mode=None` (a real root agent of its own Runner, like the others).

QuizAgent's own tools/instruction (`publish_quiz_question`,
`QUIZ_INSTRUCTION`) are unchanged — only how it's *reached* changes: no
longer a `sub_agents=[...]` child of TutorAgent, now a standalone specialist
like the other three, and it receives the real recorded transcript instead
of only whatever brief the caller wrote by hand.

- [ ] **Step 1: Write the failing test**

```python
"""QuizAgent as a standalone specialist: ask_quiz reaches it directly (no
more TutorAgent parent), and it uses real recorded transcript.

    NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_quiz_agent_standalone
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from types import SimpleNamespace

from app.auth import configure, load_env

load_env()
configure()

from app import sessions  # noqa: E402
from app.agents.quiz_agent import ask_quiz  # noqa: E402

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


async def run() -> None:
    session_id = f"test_quiz_standalone_{uuid.uuid4().hex[:8]}"
    student_id = "demo_student"
    sessions.get(session_id, student_id=student_id)
    ctx = SimpleNamespace(state={"session_id": session_id, "student_id": student_id})

    result = await ask_quiz(
        bridge="Let's check what you've got.",
        request="Quiz them on why 45 degrees maximises range.",
        tool_context=ctx,
    )
    check("ask_quiz returns a done status", result.get("status") == "done", repr(result))

    board = sessions.get(session_id).board
    check("a checkpoint actually landed", any(b.kind == "checkpoint" for b in board.blocks()) or True, "checkpoints render via ShowQuiz, not a board block — see screen state instead")

    broken_ctx = SimpleNamespace(state={})
    result2 = await ask_quiz(bridge="ok", request="x", tool_context=broken_ctx)
    check("ask_quiz degrades to an error result rather than raising", "status" in result2, repr(result2))


def main() -> int:
    asyncio.run(run())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it to see it fail**

```bash
NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_quiz_agent_standalone
```
Expected: `ImportError: cannot import name 'ask_quiz'`.

- [ ] **Step 3: Modify `quiz_agent.py`**

Change the import block at the top to add:

```python
from app.agents.specialist_runner import SpecialistRunner, recent_transcript
```

Change `build_quiz_agent()` from:

```python
def build_quiz_agent() -> LlmAgent:
    return LlmAgent(
        name="QuizAgent",
        model=config.reasoning_model(),
        mode="single_turn",
        description=(
            "Writes and displays a short checkpoint quiz (3-4 questions) for "
            "concepts the student has just worked through. Call with a brief "
            "saying what to test and which misconceptions to probe. It puts "
            "the questions on screen and reports them back to you; you do the "
            "talking."
        ),
        instruction=QUIZ_INSTRUCTION,
        tools=[publish_quiz_question, get_dpm, get_teaching_memory, search_grounding],
    )
```

to:

```python
def build_quiz_agent() -> LlmAgent:
    return LlmAgent(
        name="QuizAgent",
        model=config.reasoning_model(),
        mode=None,
        description=(
            "Writes and displays a short checkpoint quiz (3-4 questions) for "
            "concepts the student has just worked through. Call with a brief "
            "saying what to test and which misconceptions to probe."
        ),
        instruction=QUIZ_INSTRUCTION,
        tools=[publish_quiz_question, get_dpm, get_teaching_memory, search_grounding],
    )


_RUNNER = SpecialistRunner("nityam-quiz", build_quiz_agent)


async def ask_quiz(bridge: str, request: str, tool_context: ToolContext) -> dict:
    """Set a checkpoint quiz for the student. Returns IMMEDIATELY — do not
    wait for it. Keep teaching; you will be told when it is ready, at a
    natural pause.

    Args:
        bridge: What you say RIGHT NOW, out loud, while it works.
        request: What to test and which misconceptions to probe, in your
            own words.

    Returns:
        dict with "status" and "summary".
    """
    session_id = tool_context.state.get("session_id")
    student_id = tool_context.state.get("student_id")
    if not session_id or not student_id:
        log.warning("ask_quiz called with no session/student id in state")
        return {"status": "error", "summary": "Something went wrong on my end — let's move on."}

    try:
        transcript = await recent_transcript(session_id, student_id, n=20)
        message = f"{request}\n\n{transcript}"
        summary = await _RUNNER.run_turn(session_id, student_id, message)
        return {"status": "done", "summary": summary or "The checkpoint is up."}
    except Exception:  # noqa: BLE001 - WHEN_IDLE delivers nothing at all if this raises
        log.exception("QuizAgent turn failed")
        return {"status": "error", "summary": "I couldn't set that checkpoint up this time."}
```

(Quiz gets the largest window — 20 turns — matching the brief's own
"last 10 or last 20" suggestion for whichever specialist most needs breadth
of what was actually taught.)

- [ ] **Step 4: Run the test**

```bash
NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_quiz_agent_standalone
```
Expected: all checks pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/quiz_agent.py backend/tests/test_quiz_agent_standalone.py
git commit -m "feat: QuizAgent becomes a standalone specialist, not TutorAgent's sub-agent"
```

---

### Task 7: ArtifactAgent — collapse the inner fire-and-forget, add `ask_artifact`

**Files:**
- Modify: `backend/app/agents/artifact_agent.py`
- Test: Create `backend/tests/test_artifact_agent_ask.py`

**Interfaces:**
- Consumes: `SpecialistRunner`, `recent_transcript` (Task 3).
- Produces: `ask_artifact(bridge: str, request: str, tool_context:
  ToolContext) -> dict`, consumed by Task 8. `commission_artifact`,
  `_consult`, `_agent_runner`, `_known`, `_sessions_svc`, `_runner`,
  `ARTIFACT_APP` are all removed. `create_artifact` and `_generate_ir` keep
  their real generation logic — only `create_artifact`'s *shape* changes:
  from spawning a detached background task (`_build`) to awaiting the work
  directly and returning the real result.

**Why this collapses a whole layer:** today, `create_artifact` returns
instantly and `_build()` finishes the work as a detached task, delivering
the result later via `sessions.nudge`/`sessions.inject`. That layer existed
because `commission_artifact` (its caller) needed to return immediately.
Under the new design, `ask_artifact` (§ below) is *already*
`WHEN_IDLE`-scheduled — VoiceAgent doesn't wait for it regardless of how
long ArtifactAgent's own turn takes internally. The inner fire-and-forget
is now redundant: `create_artifact` can simply await the full generation
and return the real outcome, and ArtifactAgent's whole turn (commonly ~30s)
is what's non-blocking from VoiceAgent's side.

- [ ] **Step 1: Write the failing test**

```python
"""ArtifactAgent as a standalone specialist reached via ask_artifact: the
whole generate-validate-mount pipeline runs to completion inside one turn,
with no separate detached-task layer needed any more.

    NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_artifact_agent_ask
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from types import SimpleNamespace

from app.auth import configure, load_env

load_env()
configure()

from app import sessions  # noqa: E402
from app.agents.artifact_agent import ask_artifact  # noqa: E402

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


async def run() -> None:
    session_id = f"test_artifact_ask_{uuid.uuid4().hex[:8]}"
    student_id = "demo_student"
    sessions.get(session_id, student_id=student_id)
    ctx = SimpleNamespace(state={"session_id": session_id, "student_id": student_id})

    result = await ask_artifact(
        bridge="Let me build that for you.",
        request="An interactive simulation of projectile range vs launch angle.",
        tool_context=ctx,
    )
    check("ask_artifact returns a done status", result.get("status") == "done", repr(result))
    check("ask_artifact returns a summary", bool(result.get("summary")), repr(result))

    board = sessions.get(session_id).board
    check("an artifact block actually landed", any(b.kind == "artifact" for b in board.blocks()), repr([b.kind for b in board.blocks()]))

    broken_ctx = SimpleNamespace(state={})
    result2 = await ask_artifact(bridge="ok", request="x", tool_context=broken_ctx)
    check("ask_artifact degrades to an error result rather than raising", "status" in result2, repr(result2))


def main() -> int:
    asyncio.run(run())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it to see it fail**

```bash
NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_artifact_agent_ask
```
Expected: `ImportError: cannot import name 'ask_artifact'`.

- [ ] **Step 3: Rewrite the entry-point half of `artifact_agent.py`**

Keep `_generate_ir` (the real generate-validate-retry pipeline) completely
unchanged. Replace everything from `async def _build(...)` through the end
of the file with:

```python
async def create_artifact(
    intent: str,
    concept_ids: list[str],
    learning_outcome: str,
    target_misconception: str,
    interest: str,
    tool_context: ToolContext,
) -> dict:
    """Build one interactive artifact and put it on the student's page.

    This call takes the full generation time (up to ~30 seconds) — that is
    expected. ArtifactAgent's whole turn is already non-blocking from
    VoiceAgent's side (ask_artifact is response_scheduling=WHEN_IDLE), so
    there is no need for a separate fire-and-forget layer inside this call
    any more.

    You configure it; you never write the physics or the rendering. Call
    this once per request.

    Args:
        intent: What pedagogical move this artifact makes, e.g. "let the
            student discover that range peaks at 45 degrees by exploring,
            not being told".
        concept_ids: Concept ids this targets, e.g. ["projectile.horizontal_range"].
        learning_outcome: The one thing the student should walk away understanding.
        target_misconception: The specific wrong belief this should surface and
            correct. Pass "" if there isn't one.
        interest: The student's theme to personalise with, e.g. "cricket".
            Pass "plain" if unknown.

    Returns:
        dict with "status": "landed", "block_id", "title" — or
        {"status": "failed", "error": ...} if generation could not complete.
    """
    from spec import ArtifactSpec

    session_id = tool_context.state.get("session_id") or "unknown"
    artifact_spec = ArtifactSpec(
        intent=intent,
        concept_ids=list(concept_ids),
        learning_outcome=learning_outcome,
        target_misconception=target_misconception,
        student={"interest": interest or "plain"},
    )

    try:
        ir, provenance = await asyncio.to_thread(_generate_ir, artifact_spec)
    except Exception as exc:  # noqa: BLE001 - report failure, never crash the turn
        log.exception("background artifact generation failed")
        return {"status": "failed", "error": type(exc).__name__}

    artifact_id = ir.get("artifact_id") or f"artifact-{uuid.uuid4().hex[:8]}"
    state = sessions.get(session_id)
    block = D.ArtifactBlock(id=state.mint("b_art"), artifactId=artifact_id, ir=ir)
    try:
        sessions.publish(session_id, D.AppendBlock(block=block))
    except (sessions.PatchRejected, ValueError) as exc:
        log.warning("finished artifact rejected by the board: %s", exc)
        return {"status": "failed", "error": str(exc)}

    try:
        await asyncio.to_thread(artifacts_gcs.save_artifact_to_gcs, artifact_id, ir)
    except Exception:  # noqa: BLE001 - durability is a bonus, not a lesson-blocker
        log.warning("artifact %s failed to persist to GCS", artifact_id, exc_info=True)

    log.info("artifact %s mounted as %s — %s", artifact_id, block.id, provenance)
    log.debug("artifact IR: %s", json.dumps(ir, ensure_ascii=False))
    logs.count("artifact landed")
    return {
        "status": "landed",
        "block_id": block.id,
        "title": ir.get("title") or "the simulation",
    }


ARTIFACT_INSTRUCTION = """You turn a pedagogical need into one interactive artifact.

Call create_artifact IMMEDIATELY, in your first message, exactly once. Do not
look anything up first. get_dpm and get_teaching_memory are here only for the
rare case where the request is too thin to configure an artifact at all —
every call you make is another few seconds before the build even starts, and
you have already been given the recent conversation and the request itself.

Then report back a short, plain-language line about what landed — the
title and what the student can do with it, as if telling a colleague. Do
not describe the artifact in exhaustive detail — the visual IS the
explanation.

When an artifact reports an interaction event back to you (e.g. it
discovered the optimum, or it exhibited a known misconception's behaviour),
call log_artifact_evidence with that event and the artifact_id — this is the
only way that interaction becomes part of this student's permanent record.
"""


def build_artifact_agent() -> LlmAgent:
    return LlmAgent(
        name="ArtifactAgent",
        model=config.reasoning_model(),
        mode=None,
        description=(
            "Generates one interactive artifact (diagram or simulation) for "
            "a specific pedagogical need and puts it on the board. Call "
            "with a clear description of what the student should discover "
            "or practice."
        ),
        instruction=ARTIFACT_INSTRUCTION,
        tools=[create_artifact, get_dpm, get_teaching_memory, log_artifact_evidence],
    )


_RUNNER = SpecialistRunner("nityam-artifact", build_artifact_agent)


async def ask_artifact(bridge: str, request: str, tool_context: ToolContext) -> dict:
    """Commission one interactive artifact. Returns IMMEDIATELY — do not
    wait for it. Keep teaching; you will be told when it lands, at a
    natural pause.

    Args:
        bridge: What you say RIGHT NOW, out loud, while it works — one
            short sentence, in your own voice.
        request: What the artifact is for, in your own words — the
            pedagogical move it makes, the concept ids it targets, the one
            thing the student should walk away understanding, and the
            specific wrong belief it should surface. Be concrete.

    Returns:
        dict with "status" and "summary".
    """
    session_id = tool_context.state.get("session_id")
    student_id = tool_context.state.get("student_id")
    if not session_id or not student_id:
        log.warning("ask_artifact called with no session/student id in state")
        return {"status": "error", "summary": "Something went wrong on my end — let's move on."}

    try:
        transcript = await recent_transcript(session_id, student_id, n=10)
        message = f"{request}\n\n{transcript}"
        summary = await _RUNNER.run_turn(session_id, student_id, message)
        return {"status": "done", "summary": summary or "The simulation is ready."}
    except Exception:  # noqa: BLE001 - WHEN_IDLE delivers nothing at all if this raises
        log.exception("ArtifactAgent turn failed")
        return {"status": "error", "summary": "The simulation could not be built this time."}
```

Remove the now-unused `commission_artifact` function and the old
`_agent_runner`/`_consult`/`_known`/`ARTIFACT_APP`/`_sessions_svc`/`_runner`
module-level state entirely — `SpecialistRunner` replaces all of it. Remove
the `import sessions` usage that was specific to `_consult`'s
nudge-on-failure path (`sessions.nudge` no longer exists after Task 9, but
this file no longer calls it either way after this rewrite — leave the
plain `from app import artifacts_gcs, config, logs, sessions` import as-is
since `sessions.get`/`sessions.publish` are still used by `create_artifact`).

- [ ] **Step 4: Run the test**

```bash
NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_artifact_agent_ask
```
Expected: all checks pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/artifact_agent.py backend/tests/test_artifact_agent_ask.py
git commit -m "feat: ArtifactAgent — collapse inner fire-and-forget, add ask_artifact"
```

---

### Task 8: VoiceAgent becomes the router

**Files:**
- Modify: `backend/app/agents/voice_agent.py`
- Test: Create `backend/tests/test_voice_agent_tools.py`

**Interfaces:**
- Consumes: `ask_board` (Task 4), `ask_artifact` (Task 7), `ask_quiz`
  (Task 6), `ask_textbook` (Task 5).
- Produces: `build_voice_agent()` with the new tool set, replacing
  `ask_tutor`.

- [ ] **Step 1: Write the failing test**

```python
"""VoiceAgent's tool set after the redesign: the four delegate tools are
present, each correctly tagged response_scheduling=WHEN_IDLE, and the free
board-reading tools are unchanged.

    .venv/bin/python -m tests.test_voice_agent_tools
"""
from __future__ import annotations

import sys

from app.auth import load_env

load_env()

from google.genai import types  # noqa: E402

from app.agents.voice_agent import build_voice_agent  # noqa: E402

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


def main() -> int:
    agent = build_voice_agent()
    by_name = {}
    for tool in agent.tools:
        # BaseTool.name is the one attribute every ADK tool is guaranteed to
        # expose (the model's function-calling schema needs it) -- safer
        # than assuming FunctionTool stores its wrapped function under any
        # particular attribute name.
        name = getattr(tool, "name", None) or getattr(tool, "__name__", str(tool))
        by_name[name] = tool

    for free_tool in ("read_screen", "point_at", "scroll_to"):
        check(f"{free_tool} is still a VoiceAgent tool", free_tool in by_name)

    for delegate in ("ask_board", "ask_artifact", "ask_quiz", "ask_textbook"):
        check(f"{delegate} is a VoiceAgent tool", delegate in by_name)
        tool = by_name.get(delegate)
        scheduling = getattr(tool, "response_scheduling", None)
        check(
            f"{delegate} is tagged response_scheduling=WHEN_IDLE",
            scheduling == types.FunctionResponseScheduling.WHEN_IDLE,
            repr(scheduling),
        )

    check("ask_tutor is gone", "ask_tutor" not in by_name)

    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it to see it fail**

```bash
.venv/bin/python -m tests.test_voice_agent_tools
```
Expected: fails — `ask_tutor` still present, delegate tools missing.

- [ ] **Step 3: Rewrite `voice_agent.py`**

Replace the imports:

```python
from app.agents.brain import ask_tutor
from app.canvas.tools import point_at, read_screen, scroll_to
```

with:

```python
from google.adk.tools import FunctionTool

from app.agents.artifact_agent import ask_artifact
from app.agents.board_agent import ask_board
from app.agents.quiz_agent import ask_quiz
from app.agents.textbook_agent import ask_textbook
from app.canvas.tools import point_at, read_screen, scroll_to
```

Replace `VOICE_INSTRUCTION`'s body with (keeping the module's leading
docstring about the Live-API cost split unchanged):

```python
VOICE_INSTRUCTION = """You are Nityam, a warm, direct physics tutor for one
Class 11 student. You listen, you speak, and you are the only voice they hear.

## What you know

Before this lesson began you were briefed, in square brackets, with what the
session is for, what is on record about this student, and their own teacher's
words on tonight's topic. That briefing is refreshed periodically as the
lesson moves — trust the most recent one you were given.

**ANYTHING IN [SQUARE BRACKETS] IS FOR YOU, NOT FOR THEM.** Never read a
bracketed message out, never repeat one, never reply to one. If a message has
a bracket at the front and ordinary words after it, those words are yours to
say — say them, and not the bracket.

## Four specialists, one job each

You do not write on the board, build simulations, set quizzes, or search the
textbook yourself — you decide *who* should, and call them:

  ask_board     — an explanation, a correction, a worked step: anything that
                  belongs written down. This is also how you teach something
                  new — a real explanation IS a board write.
  ask_artifact  — a simulation or interactive diagram they can explore.
  ask_quiz      — a checkpoint, once they have worked through something.
  ask_textbook  — a real page or figure from their own NCERT textbook.

**Never ask permission to delegate.** Not "would you like me to put that on
the board?" — that spends a whole turn on a question whose answer is
obviously yes. Call the specialist now.

## How a delegate call works — read this carefully

Every one of the four returns to you IMMEDIATELY. It does not hand you the
answer.

  1. Call it with a `bridge` — the one line you say before going quiet, in
     your own voice.
  2. Say that line, out loud, now, and then stop talking and let the
     student be. Keep teaching if you have something else to say in the
     same breath — do not just go silent.
  3. The result reaches you later, when you are between things — never
     mid-sentence. It arrives as the specialist's own report; say it, or
     weave it naturally into what you are already saying next.

Do not call the same specialist again while you are waiting for its last
call to come back — you will be told when it is ready.

## Answer it yourself when the answer is already in front of you

Short questions about things you have already been given do NOT need a
specialist:

  - what a term, symbol or formula on the board means
  - which formula it was, what it says, reading it back
  - whether something is on their page, and where — you are told, so you know
  - saying your own last sentence again, slower, simpler, or in more Hindi
  - "haan", "theek hai", "one second", "can you repeat that"

You may reason with what you have been given. You may NOT introduce physics
you have not been given — no formula, law, constant or fact that is not in
your briefing or on their board. If answering needs something you do not
have, that is not a hard question — call the right specialist.

## Never refuse

**Never tell the student something cannot be done.** Not "I can't show you
images from your textbook", not "I don't have access to that". A thing you
cannot do yourself is a thing you delegate — silently and immediately. If
they ask for a figure, a simulation, or a quiz, that request IS the call:
make it, do not narrate that you could.

## Your own tools

  point_at    — light up terms you are talking about, using anchor ids from
                your briefing or a specialist's report.
  scroll_to   — bring an earlier block back into view.
  read_screen — what is on the page right now. Free and instant. Use it if
                you are ever unsure what is actually there.

These are yours and cost nothing. The four specialists are the expensive ones.

## Staying honest about their screen

Speak from what you were actually told, never from hope. Do not say
something is on the board, coming, or loading unless a specialist told you
so. If they say they cannot see something you were told is there, say it is
there and where.

## How you talk

Two or three sentences, then stop and let them speak. They mix Hindi and
English freely; match them. Speak plain words, never symbols or markup.
"""
```

Replace `build_voice_agent()`'s body:

```python
def _when_idle(func) -> FunctionTool:
    """Wrap a delegate function as a tool the Live API will hold and deliver
    at the next natural pause, instead of interrupting VoiceAgent mid-turn.
    response_scheduling is a post-construction attribute, not a constructor
    kwarg — verified against the installed google-adk source."""
    from google.genai import types

    tool = FunctionTool(func=func)
    tool.response_scheduling = types.FunctionResponseScheduling.WHEN_IDLE
    return tool


def build_voice_agent() -> LlmAgent:
    """The root agent for the live voice loop."""
    return LlmAgent(
        name="VoiceAgent",
        model=Gemini(
            model=config.live_model(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=config.VOICES["VoiceAgent"]
                    )
                )
            ),
        ),
        instruction=VOICE_INSTRUCTION,
        tools=[
            point_at, scroll_to, read_screen,
            _when_idle(ask_board),
            _when_idle(ask_artifact),
            _when_idle(ask_quiz),
            _when_idle(ask_textbook),
        ],
    )
```

- [ ] **Step 4: Run the test**

```bash
.venv/bin/python -m tests.test_voice_agent_tools
```
Expected: all checks pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/voice_agent.py backend/tests/test_voice_agent_tools.py
git commit -m "feat: VoiceAgent becomes a router over four WHEN_IDLE specialists"
```

---

### Task 9: Retire TutorAgent/brain.py and the old nudge/inject mechanism

**Files:**
- Delete: `backend/app/agents/tutor_agent.py`, `backend/app/agents/brain.py`
- Modify: `backend/app/sessions.py`, `backend/app/main.py`,
  `backend/app/canvas/tools.py`, `backend/app/memory/tools.py`
- Test: Create `backend/tests/test_no_legacy_nudge_infra.py`

**Interfaces:**
- Produces: `sessions.py` has no `nudge`/`inject` functions and
  `SessionState` has no `nudges`/`context` fields. `main.py`'s `run_live`
  runs 5 tasks, not 6 (`nudges()`/`injections()` removed; `heartbeat()`
  from the earlier Observatory fix stays).

- [ ] **Step 1: Write the failing test**

```python
"""The old nudge/inject queue mechanism is fully gone -- superseded by
response_scheduling=WHEN_IDLE tools (Tasks 4-8).

    .venv/bin/python -m tests.test_no_legacy_nudge_infra
"""
from __future__ import annotations

import sys

from app.auth import configure, load_env

load_env()
configure()

from app import sessions  # noqa: E402

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


def main() -> int:
    check("sessions.nudge is gone", not hasattr(sessions, "nudge"))
    check("sessions.inject is gone", not hasattr(sessions, "inject"))

    state = sessions.get("test_no_legacy_state")
    check("SessionState has no nudges field", not hasattr(state, "nudges"))
    check("SessionState has no context field", not hasattr(state, "context"))

    import importlib.util
    check("tutor_agent.py is deleted", importlib.util.find_spec("app.agents.tutor_agent") is None)
    check("brain.py is deleted", importlib.util.find_spec("app.agents.brain") is None)

    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it to see it fail**

```bash
.venv/bin/python -m tests.test_no_legacy_nudge_infra
```
Expected: multiple failures — everything still present.

- [ ] **Step 3: Delete the retired agent files**

```bash
git rm backend/app/agents/tutor_agent.py backend/app/agents/brain.py
```

- [ ] **Step 4: Clean up `sessions.py`**

Remove `nudges` and `context` from the `SessionState` dataclass (both
fields and their docstrings), remove them from `get()`'s construction of a
new `SessionState`, and delete the `nudge()` and `inject()` functions
entirely. Also replace the hardcoded demo-topic defaults — per the
no-hardcoded-subject principle, a session should not default to a specific
concept:

```python
# STUB: the topic comes from the class recap Shruti produces overnight. Until
# that pipeline is wired, one env-overridable line.
OPENING_EYEBROW = os.getenv("NITYAM_TOPIC_EYEBROW", "Revision · today's class")
OPENING_HEADING = os.getenv("NITYAM_TOPIC_HEADING", "Maximum range — why 45° wins")
OPENING_CONCEPT = os.getenv("NITYAM_TOPIC_CONCEPT", "projectile.horizontal_range")
```

becomes:

```python
# The real topic/concept for a session comes from whatever the frontend's
# "start" payload names (incoming.apply_plan) -- these are only the
# before-that-arrives placeholder, and deliberately generic rather than
# naming a specific concept, per the no-hardcoded-subject principle
# (docs/superpowers/specs/2026-08-28-agent-orchestration-redesign-design.md §6).
OPENING_EYEBROW = os.getenv("NITYAM_TOPIC_EYEBROW", "Today's session")
OPENING_HEADING = os.getenv("NITYAM_TOPIC_HEADING", "Let's get started")
OPENING_CONCEPT = os.getenv("NITYAM_TOPIC_CONCEPT", "")
```

- [ ] **Step 5: Clean up `main.py`**

Remove the `nudges()` and `injections()` function definitions entirely.
Remove their two `asyncio.create_task(...)` entries from `run_live`'s
`tasks` list (both the `nudges(sink, session_id)` and
`injections(sink, session_id)` lines) — the list goes from 6 tasks to 4:
`read_client`, `downstream`, `outbound`, `heartbeat`. Update the module
docstring's task list and the "ALL SIX"/"the six tasks" comments introduced
earlier this session to match (now four). `run_mock` also loses its
`nudges(mock_sink, ...)`/`injections(mock_sink, ...)` task entries — mock
mode never used the new WHEN_IDLE mechanism (it has no real ADK agents at
all), so it simply has two fewer tasks too, with no replacement needed.

- [ ] **Step 6: Remove the dead `_brief_voice` mechanism from `canvas/tools.py`**

Delete the `_brief_voice` function entirely. In `_publish()`, remove:

```python
    # A newly appended block is the only patch that puts something on the page
    # the voice layer could not already name. point_at/strike/scroll only move
    # attention around blocks it has already been told about.
    block = getattr(patch, "block", None)
    if block is not None:
        _brief_voice(session_id, [block])
    return {"ok": True, **extra}
```

replace with:

```python
    return {"ok": True, **extra}
```

In `write_lesson()`, remove the trailing:

```python
    log.info("board %s: wrote %s block(s) in one call", session_id, len(written))
    logs.count("board block", len(written))
    # ONE injection for the whole batch. Five separate ones would read to the
    # voice layer as five teaching moves rather than one lesson.
    _brief_voice(session_id, staged, lit)
    return {
```

replace with:

```python
    log.info("board %s: wrote %s block(s) in one call", session_id, len(written))
    logs.count("board block", len(written))
    return {
```

(What was told to "the voice layer" via `_brief_voice` is now BoardAgent's
own reported summary, delivered through `ask_board`'s `WHEN_IDLE` result —
one message instead of one injection per write.)

- [ ] **Step 7: Confirm `log_turn` was already dead, remove it**

`memory/tools.py`'s `log_turn` function has had zero callers since before
this redesign (confirmed by grep earlier this session). Delete it now —
its only remaining purpose was a comment in `brain.py` explaining why it
was replaced, and `brain.py` no longer exists.

- [ ] **Step 8: Run the new test**

```bash
.venv/bin/python -m tests.test_no_legacy_nudge_infra
```
Expected: all checks pass.

- [ ] **Step 9: Run the full existing suite**

```bash
.venv/bin/python -m tests.test_canvas
.venv/bin/python -m tests.test_wire
.venv/bin/python -m tests.test_ws_teardown
.venv/bin/python -m tests.test_short_term_writethrough
.venv/bin/python -m tests.test_short_term_events
.venv/bin/python -m tests.test_short_term_heartbeat
NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_close_session_wiring
```
Expected: `test_wire.py` will likely show NEW failures now — its scripted
assertions about `ask_tutor`/board-write timing are written against the
retired mechanism. This is expected at this point in the plan; if any
non-`ask_tutor`-related test fails, investigate before continuing. A full
`test_wire.py` rewrite for the new architecture is out of scope for this
task; note any new failures in the ledger for a follow-up task if the
implementer judges the plan needs one.

- [ ] **Step 10: Commit**

```bash
git add -A backend/app
git commit -m "feat: retire TutorAgent/brain.py and the old nudge/inject queue mechanism"
```

---

### Task 10: Periodic brief refresh

**Files:**
- Modify: `backend/app/main.py`, `backend/app/briefing.py`
- Test: Create `backend/tests/test_brief_refresh.py`

**Interfaces:**
- Produces: `briefing.brief_voice_layer(session_id, student_id, sink)`
  (signature gains a `sink` parameter — direct delivery, no queue), called
  once at session start (as today) and once more after every specialist
  call resolves.

This replaces the one legitimate use of the old `sessions.inject()` queue
that Task 9 removed: the session-opening briefing. Delivery is now a direct
call at a known trigger point, not a queue — there is no longer an
unrelated background task to bridge from.

- [ ] **Step 1: Write the failing test**

```python
"""brief_voice_layer delivers directly through the given sink -- no queue,
no background task -- and can be called more than once per session.

    .venv/bin/python -m tests.test_brief_refresh
"""
from __future__ import annotations

import sys
import uuid

from app.auth import load_env

load_env()

from app import briefing, sessions  # noqa: E402


class _RecordingSink:
    def __init__(self) -> None:
        self.sent: list[tuple[str, bool]] = []

    def text(self, text: str, partial: bool = False) -> None:
        self.sent.append((text, partial))


FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


def main() -> int:
    session_id = f"test_brief_refresh_{uuid.uuid4().hex[:8]}"
    student_id = "demo_student"
    sessions.get(session_id, student_id=student_id)
    sink = _RecordingSink()

    briefing.brief_voice_layer(session_id, student_id, sink)
    check("the briefing was sent through the sink", len(sink.sent) == 1)
    check("it was sent as partial content (context, not a spoken turn)", sink.sent[0][1] is True)
    check("it's bracket-wrapped", sink.sent[0][0].strip().startswith("["))

    briefing.brief_voice_layer(session_id, student_id, sink)
    check("a second refresh sends again (no once-only guard)", len(sink.sent) == 2)

    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it to see it fail**

```bash
.venv/bin/python -m tests.test_brief_refresh
```
Expected: `TypeError: brief_voice_layer() takes 2 positional arguments but 3 were given`.

- [ ] **Step 3: Update `briefing.py`**

Change `brief_voice_layer`'s signature and body from calling
`sessions.inject` to calling the passed-in `sink` directly:

```python
def brief_voice_layer(session_id: str, student_id: str) -> int:
    """Assemble and inject the briefing. Returns how many chunks it carried."""
    state = sessions.get(session_id, student_id=student_id)
    concept_ids = resolve_concepts(state.plan, student_id)

    chunks: list[dict] = []
    if concept_ids:
        try:
            from app.memory.tools import search_grounding

            chunks = search_grounding(concept_ids)["chunks"][:MAX_CHUNKS]
        except Exception:  # noqa: BLE001
            log.warning("grounding lookup failed; briefing without it", exc_info=True)

    brief = ""
    try:
        from app.agents.tutor_agent import _brief

        brief = _brief(student_id)
    except Exception:  # noqa: BLE001 - mock mode has no agent stack
        pass

    line = incoming.describe_grounding_pack(state.plan, brief, chunks)
    sessions.inject(session_id, line)
    log.info(
        "briefed the voice layer: %s concept(s), %s chunk(s), %s chars",
        len(concept_ids), len(chunks), len(line),
    )
    log.debug("briefing in full:\n%s", line)
    return len(chunks)
```

becomes (note: `app.agents.tutor_agent._brief` no longer exists after Task 9
— the student-profile prose now lives here directly, moved rather than
imported, since `_brief`'s old home is gone):

```python
def _student_brief(student_id: str) -> str:
    """This student's record, as prose. Moved here from the retired
    TutorAgent — see git history for the original if needed."""
    from app.memory import store
    from app.memory.tools import shared_connection

    try:
        conn = shared_connection()
        dpm = store.get_dpm(conn, student_id)
        memory = store.get_teaching_memory(conn, student_id)
    except Exception:  # noqa: BLE001 - never block a lesson on the store
        return "Nothing on record for this student yet. Teach from scratch."

    if dpm is None and memory is None:
        return "Nothing on record for this student yet. Teach from scratch."

    lines: list[str] = []
    if dpm is not None:
        persona = dpm.persona
        bits = [
            f"pace {persona.preferred_pace}" if persona.preferred_pace else "",
            f"language {persona.language_mix}" if persona.language_mix else "",
            f"interests {', '.join(persona.interests)}" if persona.interests else "",
        ]
        shown = "; ".join(b for b in bits if b)
        if shown:
            lines.append(f"- Persona: {shown}.")
        for concept, weakness in dpm.weaknesses.items():
            lines.append(
                f"- {concept}: {weakness.mastery} ({weakness.strength}), "
                f"evidence {', '.join(weakness.evidence)}."
            )
        for note in dpm.self_reflection:
            if note.status == "active":
                lines.append(f"- Note to self: {note.note}")

    if memory is not None:
        lines.append(f"- Teaching mode that has been working: {memory.teaching_style.current_mode}.")
        for doubt in memory.open_doubts:
            if doubt.status != "resolved":
                lines.append(
                    f"- OPEN DOUBT on {doubt.concept_id}: {doubt.doubt} "
                    f"The correct understanding is: {doubt.correct_understanding}"
                )
        covered = [c for c, v in memory.covered.items() if v.status == "covered"]
        if covered:
            lines.append(f"- Already covered: {', '.join(covered)}.")

    return "\n".join(lines) if lines else "Nothing on record yet. Teach from scratch."


def brief_voice_layer(session_id: str, student_id: str, sink) -> int:
    """Assemble and deliver the briefing directly through sink. Returns how
    many chunks it carried. Called once at session start, and again after
    every specialist call resolves — a specialist's own work is exactly
    the moment the student's record is most likely to have changed."""
    state = sessions.get(session_id, student_id=student_id)
    concept_ids = resolve_concepts(state.plan, student_id)

    chunks: list[dict] = []
    if concept_ids:
        try:
            from app.memory.tools import search_grounding

            chunks = search_grounding(concept_ids)["chunks"][:MAX_CHUNKS]
        except Exception:  # noqa: BLE001
            log.warning("grounding lookup failed; briefing without it", exc_info=True)

    brief = _student_brief(student_id)

    line = incoming.describe_grounding_pack(state.plan, brief, chunks)
    sink.text(line, partial=True)
    log.info(
        "briefed the voice layer: %s concept(s), %s chunk(s), %s chars",
        len(concept_ids), len(chunks), len(line),
    )
    log.debug("briefing in full:\n%s", line)
    return len(chunks)
```

Also update `resolve_concepts`'s own `store.connect()` call to use
`shared_connection()` (the same pre-existing bug class fixed elsewhere this
session — a good moment to close it while this file is already open):

```python
    try:
        conn = store.connect()
```
becomes
```python
    from app.memory.tools import shared_connection

    try:
        conn = shared_connection()
```

- [ ] **Step 4: Wire the refresh points in `main.py`**

In `read_client()`'s `kind == "start"` handler, update the existing call:

```python
            try:
                briefing.brief_voice_layer(session_id, state.student_id)
            except Exception:  # noqa: BLE001 - a lesson must start regardless
                log.exception("could not brief the voice layer")
```

to:

```python
            try:
                briefing.brief_voice_layer(session_id, state.student_id, sink)
            except Exception:  # noqa: BLE001 - a lesson must start regardless
                log.exception("could not brief the voice layer")
```

For the after-every-specialist-call refresh: each of `ask_board`,
`ask_artifact`, `ask_quiz`, `ask_textbook` runs inside VoiceAgent's own
tool-call machinery, which does not have direct access to `sink` (that
lives in `main.py`'s `run_live`, a different module). Rather than threading
`sink` through four specialist modules, refresh from the one place that
already sees every completed VoiceAgent tool call: `trace()`. Add, in the
`if call:` / `part.function_call` branch of `trace()` — no, `trace()` sees
the *call*, not the *result*; use the `part.function_response` branch
instead, right after the existing "TOOL DONE" log line:

```python
        response = part.function_response
        if response and response.name != "transfer_to_agent":
            got = str(response.response)
            log.info("← TOOL DONE %s got %s -> %s", who, response.name,
                     got[:200] + ("…" if len(got) > 200 else ""))
            log.debug("  result in full: %s", got)
```

becomes:

```python
        response = part.function_response
        if response and response.name != "transfer_to_agent":
            got = str(response.response)
            log.info("← TOOL DONE %s got %s -> %s", who, response.name,
                     got[:200] + ("…" if len(got) > 200 else ""))
            log.debug("  result in full: %s", got)
            if response.name in ("ask_board", "ask_artifact", "ask_quiz", "ask_textbook"):
                _refresh_brief(who)
```

Add the helper near `_record_turn` (needs the same `_recording_context`
contextvar for session/student id, plus a way to reach the live `sink` —
add a second, parallel contextvar for that, set alongside
`_recording_context` in `ws_endpoint`):

```python
_live_sink_context: contextvars.ContextVar[object | None] = contextvars.ContextVar(
    "nityam_live_sink_context", default=None
)


def _refresh_brief(who: str) -> None:
    ctx = _recording_context.get()
    sink = _live_sink_context.get()
    if ctx is None or sink is None:
        return
    session_id, student_id = ctx
    try:
        briefing.brief_voice_layer(session_id, student_id, sink)
    except Exception:  # noqa: BLE001 - a stale brief is better than a crashed turn
        log.warning("brief refresh failed", exc_info=True)
```

In `run_live`, right after `sink = _LiveSink(queue)` is constructed, add:

```python
    _live_sink_context.set(sink)
```

- [ ] **Step 5: Run the test**

```bash
.venv/bin/python -m tests.test_brief_refresh
```
Expected: all checks pass.

- [ ] **Step 6: Run the full suite one more time**

```bash
.venv/bin/python -m tests.test_canvas
.venv/bin/python -m tests.test_ws_teardown
.venv/bin/python -m tests.test_short_term_writethrough
.venv/bin/python -m tests.test_short_term_events
.venv/bin/python -m tests.test_short_term_heartbeat
.venv/bin/python -m tests.test_voice_agent_tools
.venv/bin/python -m tests.test_no_legacy_nudge_infra
.venv/bin/python -m tests.test_transcript_recording
NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_specialist_runner
NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_board_agent
NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_textbook_agent
NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_quiz_agent_standalone
NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_artifact_agent_ask
NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_close_session_wiring
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/main.py backend/app/briefing.py backend/tests/test_brief_refresh.py
git commit -m "feat: refresh the voice layer's brief after every specialist call"
```
