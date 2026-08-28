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
