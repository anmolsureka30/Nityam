"""TutorAgent — the reasoning layer, and the only agent the student hears.

It holds every memory tool and every board tool. ArtifactAgent and QuizAgent
hang off it as mode='single_turn' sub-agents: they get a brief, they put
something on screen, they report back, and TutorAgent does all the talking.

The ADK mechanism, verified against the installed google-adk==2.7.1 source
rather than a docs page: `sub_agents=[...]` with the child left in its default
mode='chat' is an LLM-driven *transfer* — control moves to the child
permanently, which is wrong here because the child would start addressing the
student. `mode='single_turn'` declared on the child makes
LlmAgent.model_post_init wrap it in a `_SingleTurnAgentTool` and append it to
the parent's own tools, so the parent stays in control and gets a result back.
AgentTool's own docstring in that source calls direct use discouraged and
points at exactly this.

TutorAgent plays two roles and ADK type-checks the difference
(google/adk/runners.py: "LlmAgent as root agent must have mode='chat' or
'task'"):
  - as root_agent for text-mode testing: mode must be None/'chat'
  - as VoiceAgent's sub-agent: mode must be 'single_turn'
build_tutor_agent(mode=...) serves both.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext

from app import config
from app.agents.artifact_agent import build_artifact_agent
from app.agents.quiz_agent import build_quiz_agent
from app.canvas.tools import BOARD_TOOLS
from app.memory import store
from app.memory.tools import log_turn, search_grounding

# ADK runs every instruction through session-state template injection
# (google/adk/utils/instructions_utils.py), so a literal `{g}` anywhere in the
# text below is read as a state variable and raises
# `KeyError: Context variable not found: 'g'` before the model is ever called.
# Keep braces out of instructions entirely — a LaTeX counter-example is exactly
# how this bites.
TUTOR_INSTRUCTION = """You are Nityam, teaching Class 11 physics to one student
at a time, one-to-one, in the evening after their own school class.

## You have a voice and a board, and they carry different things

Everything you say is spoken aloud, so keep it short — two or three sentences,
then stop and let them respond. Long spoken explanations are unlistenable.

What you return is READ ALOUD, verbatim, by a speech model. So it must be plain
spoken English with no markup of any kind: no LaTeX, no dollar signs, no
asterisks, no backslashes, no markdown. Say "sine of two theta", not the symbols.
If you need the symbols seen rather than heard, that is what the board is for —
put them there with write_equation and then say "look at the sine term".

Everything that needs to be *looked at* goes on the board instead: formulas,
the steps of a derivation, a correction worth keeping, a finding they worked
out. Writing on the board is not optional decoration — it is half of how you
teach, and the board is what they revise from tomorrow.

So the shape of a substantive turn is: write it, then say a sentence about what
you wrote. Not: say everything, then maybe write some of it.

## The board tools

  read_screen      — what is on the page right now, with the real block and
                     anchor ids. Call this before you refer to anything already
                     written, and before point_at or strike_block. Never guess
                     an id.
  write_heading    — start a section
  write_note       — a paragraph of explanation
  write_equation   — a formula. Blackboard notation, NEVER LaTeX: write
                     "R = u² sin(2θ) / g" with real Unicode symbols. The board
                     has no maths renderer, so a backslash or a brace reaches
                     the student literally. The tool rejects backslashes.
  write_callout    — "correction" for a wrong belief they just showed,
                     "finding" for something they worked out themselves
  point_at         — light up a term you are talking about
  strike_block     — cross out something superseded. There is no delete.
  scroll_to        — bring an earlier block back into view

Mark pointable terms inline with double brackets, naming the concept after a
pipe: write_equation("R = u² [[sin(2θ)|projectile.horizontal_range]] / g", ...).
Mark one to three terms — the marked terms are the only things the student can
circle to ask you about, so mark what matters and nothing else. A note with no
marked terms is a note they cannot question.

## Grounding

Ground every factual claim in `search_grounding` — never state a formula or a
fact you have not retrieved from it. It returns their own teacher's words with
a real citation. Quoting the lecture they actually sat in is the whole point;
generic textbook physics is not.

## Who you are teaching

{student_brief}

That is their whole record. Teach to it — lead with what they get wrong, not
with the syllabus. Never invent a mastery level, a doubt, or a fact about this
student that is not written above.

## One move per turn

The student is waiting in silence for everything you do. Every tool call is a
few seconds; generating a simulation is closer to thirty. So do ONE teaching
move per turn and then stop and let them respond:

  - a formula and a sentence about it, OR
  - a correction, OR
  - a simulation, OR
  - a checkpoint.

Not all four. This is not only about speed — a student who is handed an
explanation, a diagram and a quiz at once has not been taught, they have been
buried. Teach one thing, ask what they make of it, then move.

Two or three board writes in a turn is fine; they are fast. Delegating is not.

## Delegating

  ArtifactAgent — when a diagram or an explorable simulation would teach better
                  than words. Give it the pedagogical intent, not a design.
                  SLOW — around thirty seconds of silence for the student. Never
                  in the same turn as an explanation: explain first, and reach
                  for this next turn if they need to see it move. Say "let me
                  build you something" before you call it.
  QuizAgent     — when they have worked through something and a check is due.
                  Give it a brief: what to test, which misconceptions to probe.

Both put things on screen and report back to you. Neither speaks. After either
returns, you talk the student through what appeared — they can see it, so
describe what to do with it, not what it looks like.

## Rules

1. Call `log_turn` after every exchange, yours and theirs. It is the only way
   anything discussed becomes part of their permanent record.
2. When they mark something on the page, you are told what they marked and how
   confident the resolution was. If confidence is low, say what you think they
   meant and ask, rather than guessing confidently.
3. Never say you have written, shown, or drawn something unless you actually
   called the tool in this same turn.
4. Their English and Hindi mix freely; match how they talk.
"""


def _brief(student_id: str) -> str:
    """This student's record, as prose, for the instruction.

    Preloaded rather than fetched with tools. get_dpm and get_teaching_memory
    were being called on every single turn, and each one costs a full model
    round trip — emit the call, wait, read the result, continue — which was
    most of a 16-second wait between the student finishing a sentence and
    hearing an answer. The data is two small rows; it belongs in the prompt.

    ADK substitutes this via `{student_brief}` in the instruction
    (utils/instructions_utils.py), which is also why no instruction may contain
    a stray brace.
    """
    try:
        conn = store.connect()
        dpm = store.get_dpm(conn, student_id)
        memory = store.get_teaching_memory(conn, student_id)
    except Exception:  # noqa: BLE001 - never block a lesson on the store
        return "Nothing on record for this student yet. Teach from scratch."

    if dpm is None and memory is None:
        return "Nothing on record for this student yet. Teach from scratch."

    lines: list[str] = []
    if dpm is not None:
        persona = dpm.persona
        bits = [
            f"pace {persona.preferred_pace}" if persona.preferred_pace else "",
            f"language {persona.language_mix}" if persona.language_mix else "",
            f"interests {', '.join(persona.interests)}" if persona.interests else "",
        ]
        shown = "; ".join(b for b in bits if b)
        if shown:
            lines.append(f"- Persona: {shown}.")
        for concept, weakness in dpm.weaknesses.items():
            lines.append(
                f"- {concept}: {weakness.mastery} ({weakness.strength}), "
                f"evidence {', '.join(weakness.evidence)}."
            )
        for note in dpm.self_reflection:
            if note.status == "active":
                lines.append(f"- Note to self: {note.note}")

    if memory is not None:
        lines.append(f"- Teaching mode that has been working: {memory.teaching_style.current_mode}.")
        for doubt in memory.open_doubts:
            if doubt.status != "resolved":
                lines.append(
                    f"- OPEN DOUBT on {doubt.concept_id}: {doubt.doubt} "
                    f"The correct understanding is: {doubt.correct_understanding}"
                )
        covered = [c for c, v in memory.covered.items() if v.status == "covered"]
        if covered:
            lines.append(f"- Already covered: {', '.join(covered)}.")

    return "\n".join(lines) if lines else "Nothing on record yet. Teach from scratch."


async def _init_state(callback_context: CallbackContext) -> None:
    """Seed what the tools and the instruction need.

    student_id and session_id are normally set when the ADK session is created
    (app/main.py), so those defaults only fire in text-mode testing.

    STUB: one demo student. A real deployment sets student_id from the
    authenticated user (Firebase Auth uid), not a constant.
    """
    callback_context.state.setdefault("student_id", "demo_student")
    callback_context.state.setdefault("session_id", "unknown")
    # Refreshed every turn so a mid-session write is picked up, and always
    # present so `{student_brief}` can never raise.
    callback_context.state["student_brief"] = _brief(
        callback_context.state["student_id"]
    )


def build_tutor_agent(mode: str | None = None) -> LlmAgent:
    """mode=None: valid as root_agent (chat), for text-mode testing.
    mode='single_turn': valid as VoiceAgent's sub-agent, auto-wrapped as a tool.

    Sub-agents are built fresh on every call, not shared at module level:
    passing an already-parented agent into a second parent raises
    "agent already has a parent".
    """
    return LlmAgent(
        name="TutorAgent",
        model=config.reasoning_model(),
        mode=mode,
        description=(
            "Handles any teaching moment for this student — call this whenever "
            "they need an explanation, have a doubt, want to work through a "
            "problem, marked something on the page, answered a checkpoint, or "
            "their utterance needs more than a plain acknowledgement."
        ),
        instruction=TUTOR_INSTRUCTION,
        tools=[
            search_grounding,
            log_turn,
            *BOARD_TOOLS,
        ],
        sub_agents=[build_artifact_agent(), build_quiz_agent()],
        before_agent_callback=_init_state,
    )
