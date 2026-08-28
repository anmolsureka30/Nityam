"""TextbookAgent — finds and places real pages/figures from the student's
own NCERT textbook. Split out of TutorAgent's textbook tools.
"""
from __future__ import annotations

import logging

from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext

from app import config
from app.agents.specialist_runner import (
    SpecialistRunner,
    recent_transcript,
    refresh_brief,
)
from app.textbook import TEXTBOOK_TOOLS

log = logging.getLogger("nityam.textbook_agent")

TEXTBOOK_INSTRUCTION = """You find and place pages or figures from the
student's real, actual textbook. You never speak to the student directly —
your report becomes what the voice layer says.

  search_textbook      — where a topic, section or figure lives. Ask it the
                         way the student asked — "figure 3.14",
                         "that diagram", "section 3.9" all work. Never
                         guess a page number.
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
        # A specialist's own work is the moment the student's record is most
        # likely to have moved, so re-brief the voice layer here. This is the
        # trigger point precisely BECAUSE this function runs to completion —
        # ADK yields no function_response event for a WHEN_IDLE tool, so the
        # event-stream hook this replaces never fired once. refresh_brief
        # swallows its own failures, so it cannot turn a good answer into an
        # error, and no-ops entirely when no live sink is set.
        await refresh_brief(session_id, student_id)
        return {"status": "done", "summary": summary or "Found it."}
    except Exception:  # noqa: BLE001 - WHEN_IDLE delivers nothing at all if this raises
        log.exception("TextbookAgent turn failed")
        return {"status": "error", "summary": "I couldn't check the textbook just now."}
