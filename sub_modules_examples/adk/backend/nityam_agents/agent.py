"""The two agents.

`tutor` is the root agent: it talks to the student and, when the student asks
to be tested, hands off to `quiz_master`. ADK does the handoff itself — it
gives every agent with sub_agents a `transfer_to_agent` tool and executes the
call for you. Nothing in main.py knows there are two agents.

The handoff is *audible*: each agent carries its own voice, because voice is
configured on the model instance rather than on the session. That is the whole
reason the two-agent structure is worth demonstrating in a voice app — the
student hears a different person start asking the questions.
"""

import os

from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini
from google.adk.tools import ToolContext
from google.genai import types

# Set by auth.configure(): a bare name on AI Studio, a full
# projects/…/publishers/google/models/… path on Vertex, where the Live API
# rejects anything shorter.
MODEL = os.getenv("NITYAM_RESOLVED_MODEL") or os.getenv(
    "NITYAM_MODEL", "gemini-2.5-flash-native-audio-latest"
)


def _voice(name: str) -> Gemini:
    """A model instance that speaks with one specific voice."""
    return Gemini(
        model=MODEL,
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=name)
            )
        ),
    )


# ---------------------------------------------------------------- tools

def show_formula(name: str, tool_context: ToolContext) -> dict:
    """Display a physics formula on the student's screen.

    Call this whenever you state a formula out loud, so the student can read it
    while you explain it.

    Args:
      name: Which formula to show. One of: projectile_range, projectile_max_height,
        time_of_flight, kinematic_v, kinematic_s.
    """
    formulas = {
        "projectile_range": ("Range", "R = u² sin(2θ) / g"),
        "projectile_max_height": ("Maximum height", "H = (u sinθ)² / 2g"),
        "time_of_flight": ("Time of flight", "T = 2u sinθ / g"),
        "kinematic_v": ("Velocity", "v = u + at"),
        "kinematic_s": ("Displacement", "s = ut + ½at²"),
    }
    if name not in formulas:
        return {"status": "unknown_formula", "available": sorted(formulas)}

    label, tex = formulas[name]
    tool_context.state["last_formula"] = name
    return {"status": "shown", "label": label, "formula": tex}


def record_answer(concept: str, correct: bool, tool_context: ToolContext) -> dict:
    """Record whether the student answered a quiz question correctly.

    Call this after each question you ask, so the score on screen stays honest.

    Args:
      concept: The concept the question tested, e.g. "projectile.max_height".
      correct: True if the student's answer was right.
    """
    asked = tool_context.state.get("quiz_asked", 0) + 1
    right = tool_context.state.get("quiz_right", 0) + (1 if correct else 0)
    tool_context.state["quiz_asked"] = asked
    tool_context.state["quiz_right"] = right

    missed = list(tool_context.state.get("quiz_missed", []))
    if not correct and concept not in missed:
        missed.append(concept)
        tool_context.state["quiz_missed"] = missed

    return {"asked": asked, "correct": right, "missed": missed}


# ---------------------------------------------------------------- agents

quiz_master = Agent(
    name="quiz_master",
    model=_voice("Puck"),
    description=(
        "Tests the student with short spoken questions on physics they have "
        "just studied, and keeps score."
    ),
    instruction=(
        "You are Nityam's quiz master for Class 11 physics. You have just been "
        "handed a student who asked to be tested.\n"
        "Ask ONE question at a time and wait for the spoken answer. Keep each "
        "question under fifteen words.\n"
        "\nRECORDING ANSWERS — this is mandatory, not optional:\n"
        "The moment the student answers, call record_answer BEFORE you say "
        "anything back. Judge the answer, call the tool, then speak.\n"
        "Never say 'correct', 'right', 'सही' or anything equivalent unless you "
        "have called record_answer for that answer in this same turn. The score "
        "on the student's screen comes only from that tool — if you skip it, "
        "your praise is a lie and the screen stays blank.\n"
        "This applies to wrong answers too. Record every single one.\n"
        "\nSay briefly why an answer was wrong — do not lecture, that is the "
        "tutor's job.\n"
        "After three questions, say how they did and transfer back to the "
        "tutor so they can work on whatever was shaky.\n"
        "Speak in whichever of Hindi or English the student is using."
    ),
    tools=[record_answer],
)

root_agent = Agent(
    name="tutor",
    model=_voice("Leda"),
    description="Explains Class 11 physics conversationally.",
    instruction=(
        "You are Nityam, a warm and patient physics tutor for Class 11 students "
        "in India.\n"
        "Speak in whichever of Hindi or English the student uses, and code-switch "
        "as freely as a real Indian teacher does.\n"
        "Keep your turns to two or three sentences, then ask the student "
        "something back. Never deliver a monologue — this is a conversation, and "
        "they can interrupt you at any time.\n"
        "\nSHOWING FORMULAS — this is mandatory, not optional:\n"
        "Call show_formula FIRST, then speak. Call it whenever any of these is "
        "true:\n"
        "  - the student asks to see, or asks for, a formula\n"
        "  - you are about to say a formula out loud\n"
        "  - you refer to a formula the student needs to look at\n"
        "Never say you have shown, are showing, or will show something unless "
        "you have actually called show_formula in this same turn. Saying 'here "
        "it is' or 'मैंने दिखा दिया' without the tool call is a lie — the "
        "student's screen stays empty and they lose trust in you.\n"
        "Do not ask which formula they mean. Pick the most likely one and call "
        "the tool; you can always call it again with a different one. Asking "
        "first and showing later is how the formula never gets shown at all.\n"
        "\nIf the student asks to be quizzed or tested, transfer to quiz_master.\n"
        "Open by greeting them and asking what they want to work on."
    ),
    tools=[show_formula],
    sub_agents=[quiz_master],
)
