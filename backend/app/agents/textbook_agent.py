"""TextbookAgent — finds and places real pages/figures from the student's
own NCERT textbook. Split out of TutorAgent's textbook tools.
"""
from __future__ import annotations

import logging

from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext

from app import config
from app.agents.specialist_runner import SpecialistRunner, delegate
from app import textbook
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

You are also told what is already on the board. Do not place a figure that
is already there.

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


async def ask_textbook(request: str, tool_context: ToolContext):
    """Find or place something from the student's real textbook.

    Returns at once and keeps you talking while TextbookAgent works — you will
    be handed the result at a natural pause. Do not announce the call, and do
    not stop and wait.

    Args:
        request: What the student asked for, in their own words — a page, a
            figure number, or a topic to locate.
    """
    # FAST PATH. A named figure needs no reasoning: the number is a regex away
    # and the index maps it straight to a page and a crop box. Routing that
    # through TextbookAgent cost a full gemini-3.7-flash turn — about eight
    # seconds — to make two lookups that take under a millisecond, and it is
    # the single most common textbook request there is.
    hit = textbook.resolve_figure(request)
    if hit is not None:
        placed = textbook.show_textbook_figure(
            chapter=hit["chapter"], page=hit["page"],
            caption=hit["caption"], figure=hit["figure"],
            tool_context=tool_context,
        )
        if "error" not in placed:
            log.info("textbook fast path: figure %s, no model turn", hit["figure"])
            yield {
                "status": "done",
                "summary": (
                    f"Figure {hit['figure']} is on the board — "
                    f"{hit['title']}, page {hit['page']}."
                ),
            }
            return
        # A real figure the board would not take. Fall through rather than
        # reporting an error: the agent may still find another way to it.
        log.warning("textbook fast path failed, delegating: %s", placed["error"])

    async for chunk in delegate(
        "textbook", _RUNNER, request, tool_context,
        transcript_n=5,
        done_default="Found it.",
        error_text="I couldn't check the textbook just now.",
    ):
        yield chunk
