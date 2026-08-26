"""TutorAgent — the reasoning / intelligence layer (architecture.md §2).

Holds all memory tools. Delegates artifact generation to ArtifactAgent via
ADK's mode='single_turn' sub-agent mechanism (never raw AgentTool — see
architecture.md §2 for why, verified against installed ADK source).
"""
from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext

from app import config
from app.agents.artifact_agent import build_artifact_agent
from app.memory.tools import get_dpm, get_teaching_memory, log_turn, search_grounding

TUTOR_INSTRUCTION = """You are Nityam, a tutor teaching projectile motion to one
student at a time.

Ground every factual claim in `search_grounding` — never state a formula or
fact you haven't retrieved from it. Call `get_dpm` and `get_teaching_memory`
at the start of a topic to see this student's mastery, open doubts, and
current teaching mode before deciding how to teach.

Rules:
1. Call `log_turn` after every exchange (yours and the student's) — this is
   the only way anything discussed becomes part of this student's permanent
   record.
2. When a diagram, an interactive simulation, or a worked example would teach
   better than words alone, delegate to ArtifactAgent with a clear
   pedagogical intent. You decide WHEN one is needed; it decides HOW to
   render it.
3. Never invent a mastery level, a doubt, or a fact about this student that
   didn't come from get_dpm or get_teaching_memory.
"""


async def _init_student(callback_context: CallbackContext) -> None:
    # Single-demo-student prototype (architecture.md "Demo subject" decision):
    # a real multi-student deployment would set this from the session's own
    # user_id instead of defaulting it here.
    callback_context.state.setdefault("student_id", "demo_student")


def build_tutor_agent() -> LlmAgent:
    return LlmAgent(
        name="TutorAgent",
        model=config.REASONING_MODEL,
        mode="single_turn",
        description=(
            "Handles any teaching moment for the projectile-motion student — "
            "call this whenever the student needs an explanation, wants to "
            "work through a problem, or their utterance needs more than a "
            "plain acknowledgement."
        ),
        instruction=TUTOR_INSTRUCTION,
        tools=[search_grounding, get_dpm, get_teaching_memory, log_turn],
        sub_agents=[build_artifact_agent()],
        before_agent_callback=_init_student,
    )
