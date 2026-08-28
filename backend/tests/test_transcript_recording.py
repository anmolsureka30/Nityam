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


def main() -> int:
    asyncio.run(run())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
