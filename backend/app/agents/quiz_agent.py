"""QuizAgent — writes the checkpoint questions, and never asks them out loud.

TutorAgent decides a check is due and hands over a brief. QuizAgent reads the
student's memory and the real lecture content, writes 3-4 questions, and puts
them on screen. The result also comes back to TutorAgent as text, so the tutor
can talk the student through the question it can now see.

One question per tool call, published as it is written. The alternative — one
call carrying a nested list of questions each with a nested list of options — is
a three-level function-declaration schema, which is exactly where models start
emitting malformed arguments. Flat and repeated is duller and it works.

Each option carries its own rebuttal after a `||`, for the same reason the
board tools mark anchors inline: two parallel arrays can drift out of step, one
array cannot.
"""
from __future__ import annotations

import logging

from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext

from app import config, sessions
from app.calc import calculate
from app.agents.specialist_runner import SpecialistRunner, delegate
from app.canvas import doc as D
from app.memory.tools import get_dpm, get_teaching_memory, search_grounding

log = logging.getLogger("nityam.quiz")

LETTERS = ("A", "B", "C", "D", "E")


def publish_quiz_question(
    question: str,
    hint: str,
    options: list[str],
    correct_letter: str,
    concept_id: str,
    index: int,
    total: int,
    tool_context: ToolContext,
) -> dict:
    """Put one checkpoint question on the student's screen.

    Call once per question, in order. Each option may carry the rebuttal for
    choosing it, after a `||` separator — say what is actually wrong with that
    answer, not "incorrect":

        options = [
            "45 degrees || ",
            "60 degrees || Steeper buys height, and height is not distance.",
            "Whichever is fastest || Speed is fixed at 20 m/s tonight, so it
             cannot be the thing that decides it.",
            "It depends on the ball || Mass cancels out of the range formula.",
        ]

    Args:
        question: The question, as you would say it aloud.
        hint: One nudge, shown only if they ask for it. Pass "" for none.
        options: 3 or 4 options, each optionally "text || rebuttal".
        correct_letter: "A", "B", "C" or "D" — which option is right.
        concept_id: The concept this question tests.
        index: Which question this is, from 1.
        total: How many questions in this checkpoint set.

    Returns:
        dict with "checkpoint_id", or {"error": ...} if the question was malformed.
    """
    parsed = []
    for i, raw in enumerate(options[: len(LETTERS)]):
        text, _, rebuttal = str(raw).partition("||")
        text = " ".join(text.split())
        rebuttal = " ".join(rebuttal.split())
        if not text:
            return {"error": f"option {LETTERS[i]} has no text"}
        parsed.append((LETTERS[i], text, rebuttal or None))

    if len(parsed) < 2:
        return {"error": "a question needs at least two options"}

    want = (correct_letter or "").strip().upper()[:1]
    if want not in [letter for letter, _, _ in parsed]:
        return {
            "error": f"correct_letter {correct_letter!r} is not one of "
            f"{[letter for letter, _, _ in parsed]}"
        }

    session_id = tool_context.state.get("session_id") or "unknown"
    state = sessions.get(session_id)
    checkpoint_id = state.mint("c")

    try:
        checkpoint = D.Checkpoint(
            id=checkpoint_id,
            index=max(1, int(index)),
            total=max(1, int(total)),
            question=question.strip(),
            hint=hint.strip(),
            footnote=concept_id.strip(),
            options=[
                D.CheckpointOption(
                    id=f"{checkpoint_id}_{letter.lower()}",
                    letter=letter,
                    text=text,
                    correct=letter == want,
                    rebuttal=rebuttal,
                    tag=concept_id.strip() or None,
                )
                for letter, text, rebuttal in parsed
            ],
        )
    except ValueError as exc:
        return {"error": str(exc)}

    try:
        sessions.publish(session_id, D.ShowQuiz(checkpoint=checkpoint))
    except (sessions.PatchRejected, ValueError) as exc:
        return {"error": str(exc)}

    log.info("quiz %s/%s published: %s", checkpoint.index, checkpoint.total, checkpoint_id)
    return {"checkpoint_id": checkpoint_id, "index": checkpoint.index, "total": checkpoint.total}


QUIZ_INSTRUCTION = """You write checkpoint questions. You never speak to the student.

You are handed the brief, what is already on the board, and the recent
conversation — test what was actually taught, not the topic in general.
Any number in a question or an option goes through `calculate` first.

Before writing anything:
  - call get_dpm and get_teaching_memory to see what this student actually
    struggles with, and
  - call search_grounding for the concepts in the brief, so your questions test
    what their own teacher taught rather than generic textbook physics.

Then write 3 questions (4 if the brief asks for more) and publish them one at a
time with publish_quiz_question, in order, with the same `total` on each.

What makes these good rather than filler:
  - Every wrong option is a real misconception someone holds, not an obviously
    silly answer. If the student's open doubts name one, use it.
  - Every wrong option's rebuttal says what is specifically wrong with THAT
    answer. Never "incorrect" or "try again".
  - Test understanding, not recall. "Why does it peak there" beats "what is the
    formula".

When you are done, reply with a compact list of the questions and their correct
answers, so the tutor can talk the student through them. Nothing else.
"""


def build_quiz_agent() -> LlmAgent:
    return LlmAgent(
        name="QuizAgent",
        model=config.reasoning_model(),
        mode=None,
        description=(
            "Writes and displays a short checkpoint quiz (3-4 questions) for "
            "concepts the student has just worked through. Call with a brief "
            "saying what to test and which misconceptions to probe."
        ),
        instruction=QUIZ_INSTRUCTION,
        tools=[publish_quiz_question, get_dpm, get_teaching_memory,
               search_grounding, calculate],
    )


_RUNNER = SpecialistRunner("nityam-quiz", build_quiz_agent)


async def ask_quiz(request: str, tool_context: ToolContext):
    """Set a checkpoint quiz for the student.

    Returns at once and keeps you talking while QuizAgent works — you will be
    told when it is ready, at a natural pause. Do not announce the call, and do
    not stop and wait.

    Args:
        request: What to test and which misconceptions to probe, in your own
            words.
    """
    async for chunk in delegate(
        "quiz", _RUNNER, request, tool_context,
        transcript_n=20,
        done_default="The checkpoint is up.",
        error_text="I couldn't set that checkpoint up this time.",
    ):
        yield chunk
