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

    # The 7-second timer that used to cover a delegation's silence. Retired in
    # favour of the streaming-tool responses in specialist_runner.delegate,
    # which are causally tied to the delegation rather than to a clock, go over
    # send_tool_response rather than the send_client_content channel Google
    # warns races with realtime audio, and cover the whole 70s cap instead of
    # the first 21s. Asserted gone because reinstating it "just as a backstop"
    # would put two things in charge of when she talks.
    from app.agents import specialist_runner
    for name in ("_nudge_while_waiting", "_NUDGE_TEXT",
                 "_NUDGE_INTERVAL_S", "_MAX_NUDGES"):
        check(f"specialist_runner.{name} is gone",
              not hasattr(specialist_runner, name))
    check("delegate() replaced it",
          hasattr(specialist_runner, "delegate"))

    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
