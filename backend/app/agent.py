"""Entry points for the two ways this backend gets run.

`root_agent` is BoardAgent in chat mode — what `adk web`, `adk run` and
scripts/drive.py use to exercise board-writing with no microphone in the
way. `voice_root_agent` is the live voice loop, used by app/main.py.

Both are factories rather than module-level singletons where it matters: an
agent object already attached to one parent raises "agent already has a
parent" if handed to a second.
"""
from __future__ import annotations

from google.adk.apps import App

from app.agents.board_agent import build_board_agent
from app.agents.voice_agent import build_voice_agent

APP_NAME = "nityam"

root_agent = build_board_agent()

app = App(root_agent=root_agent, name=APP_NAME)

__all__ = ["APP_NAME", "app", "root_agent", "build_voice_agent"]
