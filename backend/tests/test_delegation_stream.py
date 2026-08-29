"""The delegation tools must stay async generators, and ADK must keep routing
them through its STREAMING branch. Offline — no credentials, no network.

This is a tripwire, not a behaviour test. The entire no-silence design rests on
three private ADK behaviours, and if a google-adk upgrade quietly reroutes these
tools the symptom is not an exception — it is the tutor going silent for the
whole delegation again, which nothing else here would notice.

    .venv/bin/python -m tests.test_delegation_stream
"""
from __future__ import annotations

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("NITYAM_AUTH", "mock")

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


def main() -> int:
    from google.genai import types

    from app.agents.artifact_agent import ask_artifact
    from app.agents.board_agent import ask_board
    from app.agents.quiz_agent import ask_quiz
    from app.agents.specialist_runner import (
        KEEP_TALKING_INTERVAL_S,
        TURN_TIMEOUT_S,
        _holding,
        _opening,
    )
    from app.agents.textbook_agent import ask_textbook
    from app.agents.voice_agent import build_voice_agent

    tools = {
        "ask_board": ask_board, "ask_textbook": ask_textbook,
        "ask_quiz": ask_quiz, "ask_artifact": ask_artifact,
    }

    for name, func in tools.items():
        check(f"{name} is an async generator",
              inspect.isasyncgenfunction(func))

    # ── the ADK branch this design needs ────────────────────────────────────
    # flows/llm_flows/functions.py picks the streaming path on exactly this
    # predicate, and the OLD non-blocking path on the other one. Taking the
    # wrong branch means one response instead of a stream: silence, no error.
    agent = build_voice_agent()
    seen = 0
    for tool in agent.tools:
        name = getattr(tool, "name", "")
        if not str(name).startswith("ask_"):
            continue
        seen += 1
        func = getattr(tool, "func", None)
        streaming = func is not None and inspect.isasyncgenfunction(func)
        check(f"{name} takes ADK's streaming branch", streaming)
        check(f"{name} does NOT take the old non-blocking branch",
              not (not streaming and tool.response_scheduling is not None))
        # base_llm_flow._mark_live_async_tools_non_blocking stamps
        # Behavior.NON_BLOCKING off this, and the Live API only accepts
        # asynchronous FunctionResponses for a NON_BLOCKING declaration.
        check(f"{name} still declares WHEN_IDLE",
              tool.response_scheduling
              == types.FunctionResponseScheduling.WHEN_IDLE,
              str(tool.response_scheduling))
    check("all four are on VoiceAgent", seen == 4, f"{seen} found")

    # ── the chunks themselves ───────────────────────────────────────────────
    opening = _opening("artifact")
    check("the opening chunk names the specialist",
          opening["still_working"] == "artifact")
    check("and carries that specialist's own clause",
          "simulation" in opening["do"], opening["do"])

    early, late = _holding("board", 6), _holding("board", 45)
    check("a progress chunk is scheduled WHEN_IDLE — the thing that makes her speak",
          early.scheduling == types.FunctionResponseScheduling.WHEN_IDLE)
    check("it escalates once the wait gets long",
          early.response["do"] != late.response["do"])
    for label, chunk in (("opening", opening), ("progress", early.response)):
        # Everything injected is bracketed so the existing "anything in
        # [square brackets] is for you" rule covers this channel too, and so
        # test_routing's never-reads-a-bracket check keeps guarding it.
        check(f"the {label} directive is bracketed",
              chunk["do"].strip().startswith("[")
              and chunk["do"].strip().endswith("]"))

    # ── coverage, the bug the old timer had ─────────────────────────────────
    # _MAX_NUDGES = 3 at 7s covered 21s of a 70s cap and nobody noticed. There
    # is no count any more, but assert the property that was violated.
    check("the cadence covers the whole timeout, not a prefix of it",
          KEEP_TALKING_INTERVAL_S < TURN_TIMEOUT_S,
          f"{KEEP_TALKING_INTERVAL_S}s cadence, {TURN_TIMEOUT_S}s cap")
    check("and is short enough to beat one of her utterances",
          KEEP_TALKING_INTERVAL_S <= 6.0, f"{KEEP_TALKING_INTERVAL_S}s")

    print()
    print(f"{FAILED} failed" if FAILED else "all passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
