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

    # A single consumer draining an ordered queue, exactly like run_live sets
    # up per connection -- not a fire-and-forget task per _record_turn call
    # (that raced: ~71% failure rate reordering/dropping entries).
    queue: asyncio.Queue = asyncio.Queue()
    nityam_main._transcript_queue_context.set(queue)
    writer_task = asyncio.create_task(nityam_main._transcript_writer(queue))

    try:
        nityam_main.trace(_event("student", "why does it peak at 45?", input_side=True))
        nityam_main.trace(_event("VoiceAgent", "because sin two theta peaks there", input_side=False))

        # Deterministic wait: blocks until both enqueued items have been
        # drained and task_done() called, instead of hoping a sleep was
        # long enough.
        await queue.join()

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
        await queue.join()
        buffer2 = await short_term.get_turn_buffer(session_id, student_id)
        check("a partial transcription is not recorded", len(buffer2) == 2, repr(buffer2))
    finally:
        writer_task.cancel()
        await short_term.clear_session(session_id, student_id)
        nityam_main.logs.close_session(session_id)


async def run_turn_numbering() -> None:
    """Consecutive turns get 1, 2, 3... and validate against the `Turn`
    schema the durable write actually uses.

    _transcript_writer used to hardcode `"turn": 0`, and `Turn` declares
    `turn: int = Field(ge=1)` -- so every single write failed Pydantic
    validation inside session_close.close_session, swallowed by
    _flush_session_memory's broad except. Nothing looked broken; no
    SessionLog was ever persisted and no Reflect call ever ran, for every
    session ever recorded. This asserts the numbers directly AND feeds them
    through the real schema, because "not 0" is not the same claim as
    "the durable write will accept it".
    """
    session_id = f"test_turnno_{uuid.uuid4().hex[:8]}"
    student_id = "demo_student"
    nityam_main.logs.open_session(session_id, student_id, mode="mock", live_model="", detail="test")
    nityam_main.instrumentation.set_session_context(session_id)
    nityam_main._recording_context.set((session_id, student_id))

    queue: asyncio.Queue = asyncio.Queue()
    nityam_main._transcript_queue_context.set(queue)
    writer_task = asyncio.create_task(nityam_main._transcript_writer(queue))

    try:
        nityam_main.trace(_event("student", "first", input_side=True))
        nityam_main.trace(_event("VoiceAgent", "second", input_side=False))
        nityam_main.trace(_event("student", "third", input_side=True))
        await queue.join()

        buffer = await short_term.get_turn_buffer(session_id, student_id)
        numbers = [t["turn"] for t in buffer]
        check("three turns recorded", len(buffer) == 3, repr(buffer))
        check("turns are numbered 1, 2, 3 -- not 0, 0, 0", numbers == [1, 2, 3], repr(numbers))

        # The real gate: the schema session_close validates against.
        from app.memory.schemas import Turn

        try:
            parsed = [Turn(**t) for t in buffer]
            check("every recorded turn validates against Turn's schema", True)
            check("and keeps its number through validation",
                  [t.turn for t in parsed] == [1, 2, 3], repr(parsed))
        except Exception as exc:  # noqa: BLE001 - the failure IS the finding
            check("every recorded turn validates against Turn's schema", False, repr(exc))
    finally:
        writer_task.cancel()
        await short_term.clear_session(session_id, student_id)
        nityam_main.logs.close_session(session_id)


async def run_drain_on_disconnect() -> None:
    """The exact sequence run_live now uses at teardown: drain the transcript
    queue (bounded, via asyncio.wait_for(queue.join(), ...)) BEFORE cancelling
    the pending tasks, which include the consumer -- not cancel-then-hope.
    Without this, a turn enqueued right as the connection closes is lost not
    just from the ephemeral Redis buffer but from the durable session_log
    _flush_session_memory writes from that same buffer moments later, on the
    single most common shutdown path (an ordinary disconnect).

    Artificially slows the Redis write so the consumer is still mid-flight
    at the exact moment we would otherwise cancel it -- this reproduces "the
    connection closes right as the last turn settles" deterministically,
    instead of relying on a real race to land the right way by chance (the
    original fire-and-forget bug hid for exactly that reason).
    """
    session_id = f"test_drain_{uuid.uuid4().hex[:8]}"
    student_id = "demo_student"
    nityam_main.logs.open_session(session_id, student_id, mode="mock", live_model="", detail="test")
    nityam_main.instrumentation.set_session_context(session_id)
    nityam_main._recording_context.set((session_id, student_id))

    queue: asyncio.Queue = asyncio.Queue()
    nityam_main._transcript_queue_context.set(queue)
    writer_task = asyncio.create_task(nityam_main._transcript_writer(queue))

    real_append_turn = short_term.append_turn

    async def _slow_append_turn(*args, **kwargs):
        # Guarantees _transcript_writer is still awaiting the Redis write
        # (not idle on queue.get()) at the instant the test tries to cancel
        # it -- the race the drain step exists to survive.
        await asyncio.sleep(0.2)
        await real_append_turn(*args, **kwargs)

    short_term.append_turn = _slow_append_turn
    try:
        nityam_main.trace(_event("student", "last thing before disconnect", input_side=True))

        # Mirrors run_live's fixed sequence: bounded drain BEFORE cancelling
        # the consumer. (Reverting to cancel-first-then-drain would cancel
        # the writer mid-sleep, above, and this turn would never reach
        # Redis -- this assertion is what catches that regression.)
        try:
            await asyncio.wait_for(queue.join(), timeout=2.0)
        except asyncio.TimeoutError:
            pass
        writer_task.cancel()

        buffer = await short_term.get_turn_buffer(session_id, student_id)
        check(
            "a turn enqueued right before teardown survives the drain",
            len(buffer) == 1 and buffer[0]["text"] == "last thing before disconnect",
            repr(buffer),
        )
    finally:
        short_term.append_turn = real_append_turn
        writer_task.cancel()
        await short_term.clear_session(session_id, student_id)
        nityam_main.logs.close_session(session_id)


def main() -> int:
    asyncio.run(run())
    asyncio.run(run_turn_numbering())
    asyncio.run(run_drain_on_disconnect())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
