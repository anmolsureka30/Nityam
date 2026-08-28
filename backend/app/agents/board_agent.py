"""BoardAgent — decides what belongs on the student's board and writes it.

Absorbs the board-writing judgment TutorAgent used to hold, including
"explain a new concept" — per the design's approved principle, a
substantive explanation IS a board write (see
docs/superpowers/specs/2026-08-28-agent-orchestration-redesign-design.md §3,
"the existing philosophy: everything worth remembering goes on the board").
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
from app.canvas.tools import BOARD_TOOLS
from app.memory.tools import list_concepts, search_grounding

log = logging.getLogger("nityam.board")

BOARD_INSTRUCTION = """You decide what belongs on the student's board and
write it. You never speak to the student directly — whatever you report
back is said, in the tutor's own voice, by the voice layer that called you.

## Ground it, always

Never invent physics. Before writing anything about a concept you have not
already been given evidence for in this request, call `list_concepts` to
find its real id, then `search_grounding` with that id — their own
teacher's words, with a citation, not generic textbook material. Ask for
both in the SAME message as the writing they support, not a message of
their own: you do not need the grounding text in hand to know you want it.

## Use the request and the recent conversation together

You are handed the voice layer's request and the last several turns of the
actual conversation. Use the transcript to judge what the student already
understands and where they are stuck — write to that, not to a generic
version of the topic.

## Write well, in one call

`write_lesson` is the tool you use for anything longer than one block — a
whole answer in a single call: heading, formula, paragraph, callout, and
what to point at. Mark pointable terms inline with double brackets, naming
the concept after a pipe. Blackboard notation only — no LaTeX, the board has
no renderer for it.

## Report back

End with a short, plain-language summary of what you wrote and why, as if
telling a colleague what you just put on the board. This is what the voice
layer will say to the student, so make it something a person would actually
say aloud — not a list of block ids.
"""


def build_board_agent() -> LlmAgent:
    return LlmAgent(
        name="BoardAgent",
        model=config.reasoning_model(),
        mode=None,
        description=(
            "Decides what belongs on the student's board for a given "
            "request — an explanation, a correction, a worked step — and "
            "writes it, grounded in their own teacher's material."
        ),
        instruction=BOARD_INSTRUCTION,
        tools=[search_grounding, list_concepts, *BOARD_TOOLS],
    )


_RUNNER = SpecialistRunner("nityam-board", build_board_agent)


async def ask_board(bridge: str, request: str, tool_context: ToolContext) -> dict:
    """Get something written on the student's board. Returns IMMEDIATELY —
    do not wait for it. Keep teaching; you will be told what was written
    once BoardAgent finishes, at a natural pause.

    Args:
        bridge: What you say RIGHT NOW, out loud, while it works — one short
            sentence, in your own voice.
        request: What should be written, in your own words — the concept,
            the specific doubt, and anything you noticed the student get
            wrong. Be concrete.

    Returns:
        dict with "status" and "summary" — say the summary once you are
        told it is ready.
    """
    session_id = tool_context.state.get("session_id")
    student_id = tool_context.state.get("student_id")
    if not session_id or not student_id:
        log.warning("ask_board called with no session/student id in state")
        return {"status": "error", "summary": "Something went wrong on my end — let's move on."}

    try:
        transcript = await recent_transcript(session_id, student_id, n=10)
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
        return {"status": "done", "summary": summary or "It's on the board now."}
    except Exception:  # noqa: BLE001 - WHEN_IDLE delivers nothing at all if this raises
        log.exception("BoardAgent turn failed")
        return {"status": "error", "summary": "I couldn't get that written up this time."}
