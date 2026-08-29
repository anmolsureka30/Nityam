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
from app.agents.specialist_runner import SpecialistRunner, delegate
from app.canvas.tools import BOARD_TOOLS
from app.memory.tools import get_dpm, get_teaching_memory, list_concepts, search_grounding

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

If the request is narrow — "put the formula on the board" — that is where
you start, not where you stop. Include the reasoning or step that makes it
make sense, if it was already covered out loud and is not on the board yet.
The board is the student's real, lasting record of the lesson, not a bare
answer to an isolated question.

## Teach to this student, not a generic one

Call `get_dpm` and `get_teaching_memory` when knowing more about this
student would change what you write — a misconception already on record
for this concept, a note about what has worked before, their pace. Ask for
it in the same message as the writing it informs, same as grounding above.

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
        tools=[search_grounding, list_concepts, get_dpm, get_teaching_memory, *BOARD_TOOLS],
    )


_RUNNER = SpecialistRunner("nityam-board", build_board_agent)


async def ask_board(bridge: str, request: str, tool_context: ToolContext):
    """Get something written on the student's board.

    Returns at once and keeps you talking while BoardAgent works — you will be
    handed its report at a natural pause. Do not announce the call, and do not
    stop and wait.

    Args:
        bridge: One short sentence in your own voice, said as you call.
        request: What should be written, in your own words — the concept, the
            specific doubt, and anything you noticed the student get wrong.
    """
    async for chunk in delegate(
        "board", _RUNNER, request, tool_context,
        transcript_n=10,
        done_default="It's on the board now.",
        error_text="I couldn't get that written up this time.",
    ):
        yield chunk
