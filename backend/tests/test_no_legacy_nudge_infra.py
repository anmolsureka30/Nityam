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
