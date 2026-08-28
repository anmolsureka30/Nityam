"""The brief: composed without a sink, delivered through one, and refreshed
after a specialist call only when it actually changed.

    .venv/bin/python -m tests.test_brief_refresh
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from app.auth import load_env

load_env()

from app import briefing, sessions  # noqa: E402
from app.agents import specialist_runner  # noqa: E402


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


def test_delivery() -> None:
    """The session-start path, unchanged in behaviour by the split."""
    session_id = f"test_brief_refresh_{uuid.uuid4().hex[:8]}"
    student_id = "demo_student"
    sessions.get(session_id, student_id=student_id)
    sink = _RecordingSink()

    line = briefing.brief_voice_layer(session_id, student_id, sink)
    check("the briefing was sent through the sink", len(sink.sent) == 1)
    check("it was sent as partial content (context, not a spoken turn)", sink.sent[0][1] is True)
    check("it's bracket-wrapped", sink.sent[0][0].strip().startswith("["))
    check("brief_voice_layer returns the text it sent", line == sink.sent[0][0])

    briefing.brief_voice_layer(session_id, student_id, sink)
    check("a second call sends again (no once-only guard in the sink path)", len(sink.sent) == 2)

    # compose_brief is the half refresh_brief runs in a thread: it must
    # produce the same text with no sink anywhere in sight.
    composed = briefing.compose_brief(session_id, student_id)
    check("compose_brief needs no sink and returns the same text", composed == line,
          f"{composed[:60]!r} vs {line[:60]!r}")


async def test_refresh() -> None:
    """refresh_brief: the path a specialist actually takes."""
    session_id = f"test_refresh_{uuid.uuid4().hex[:8]}"
    student_id = "demo_student"
    sessions.get(session_id, student_id=student_id)

    # 1. No sink set -> silent no-op. This is the normal state under test and
    #    in mock mode, and it must not raise or block.
    specialist_runner._live_sink_context.set(None)
    specialist_runner._last_brief.clear()
    await specialist_runner.refresh_brief(session_id, student_id)
    check("refresh_brief no-ops with no live sink set", True)

    # 2. Sink set, nothing sent yet -> the first refresh delivers.
    sink = _RecordingSink()
    specialist_runner.set_live_sink(sink)
    await specialist_runner.refresh_brief(session_id, student_id)
    check("with a sink, the first refresh sends the brief", len(sink.sent) == 1, repr(len(sink.sent)))
    if sink.sent:
        check("and sends it as partial context, not a spoken turn", sink.sent[0][1] is True)

    # 3. Nothing has changed since -> it must NOT re-send. Re-injecting
    #    byte-identical text after every specialist call is exactly what the
    #    brief being small is for.
    await specialist_runner.refresh_brief(session_id, student_id)
    await specialist_runner.refresh_brief(session_id, student_id)
    check("an unchanged brief is not re-sent", len(sink.sent) == 1, repr(len(sink.sent)))

    # 4. If the composed text does change, it goes out.
    real_compose = briefing.compose_brief
    briefing.compose_brief = lambda s, st: "[YOUR BRIEFING — something new happened]"
    try:
        await specialist_runner.refresh_brief(session_id, student_id)
        check("a changed brief IS sent", len(sink.sent) == 2, repr(len(sink.sent)))
    finally:
        briefing.compose_brief = real_compose

    # 5. A composition failure must never escape into the caller's turn:
    #    refresh_brief is awaited inside each ask_* tool's own try block, and
    #    an exception here would turn a good specialist answer into an error.
    def _boom(*_args, **_kwargs):
        raise RuntimeError("firestore is having a day")

    briefing.compose_brief = _boom
    try:
        await specialist_runner.refresh_brief(session_id, student_id)
        check("a failing compose is swallowed, not raised", True)
    except Exception as exc:  # noqa: BLE001 - the raise IS the failure
        check("a failing compose is swallowed, not raised", False, repr(exc))
    finally:
        briefing.compose_brief = real_compose

    # 6. note_brief_sent seeds the comparison from the session-start brief,
    #    so the first specialist call of a session doesn't re-inject it.
    fresh = _RecordingSink()
    specialist_runner.set_live_sink(fresh)
    opening = briefing.brief_voice_layer(session_id, student_id, fresh)
    specialist_runner.note_brief_sent(session_id, opening)
    await specialist_runner.refresh_brief(session_id, student_id)
    check("the first refresh after the opening brief re-sends nothing",
          len(fresh.sent) == 1, repr(len(fresh.sent)))

    specialist_runner._live_sink_context.set(None)
    specialist_runner._last_brief.clear()


def main() -> int:
    test_delivery()
    asyncio.run(test_refresh())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
