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
