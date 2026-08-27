"""VoiceAgent — the ears and the mouth. Nothing else lives here.

The student perceives one tutor. Underneath there are two model layers, and the
split is forced, not stylistic: **the Live API bills every context token,
including the system instruction, on every single turn.** A memory-sized prompt
re-billed across sixty turns of a session is real money and real latency. So
memory, grounding and the board all live in TutorAgent, reached through a tool
call, and this instruction stays deliberately small.

The cost of the split is a pause: a substantive turn is Live → tool → a full
reasoning turn with its own tool calls → back to Live → speech.

## Why the bridge line is a tool argument

The first version of this instruction said "say one short thing first, THEN call
ask_tutor", on the reasoning that the Live model can emit audio and then call a
tool in the same turn. In a real six-minute session it did the opposite, every
time. Read the transcript in order:

    student said: "I need to know what was taught today."
    VoiceAgent says: "Achha so you want to know what we covered today Let me
                      check for you"                        <- and then nothing
    student said: "Arrivement what is taught in class today?"
    VoiceAgent says: "Ah my apologies Let me look at that with you"
                                                            <- and then nothing
    student said: "Could teach me how to calculate the range and height…"
    VoiceAgent says: "Okay so you'd like to learn about… Let me see how I can
                      help you with that"                   <- and then nothing
    (44 seconds pass)
    student said: "Go on."
    → TOOL CALL VoiceAgent calls ask_tutor(…)               <- finally

Speaking and calling turned out to be **mutually exclusive in practice**: every
turn that spoke a bridge line made no call, and every turn that made a call
spoke no bridge. Emitting the audio completes the turn, and the bridge
instruction became a *substitute* for the delegation rather than a preface to
it. Worse, the same model then narrated actions it had not taken — "main abhi
board par simulation daal rahi hoon" with no tool call behind it, five times in
a row, while the student watched a page that never changed.

So the bridge is now a required **parameter** of ask_tutor. There is exactly one
action available for anything substantive: call the tool. There is no way to say
the reassuring line without calling, because the line *is* an argument to the
call. The student still sees it immediately — main.py forwards the whole
function_call to the browser, so the frontend reads `args.bridge` off that frame
and puts it in her speech bubble while the reasoning layer works.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.models import Gemini
from google.genai import types

from app import config
from app.agents.brain import ask_tutor

VOICE_INSTRUCTION = """You are Nityam, a warm, direct physics tutor for one
Class 11 student. You are their voice interface: you listen, you speak, and for
anything that counts you consult your own teaching layer.

## The one rule that matters

For anything with teaching content — a question, a doubt, an answer to work
through, something they marked on the page, a checkpoint they answered, a
request to be quizzed or shown or simulated something, or a complaint that
something has not appeared — your ONLY move is to call ask_tutor.

Do not answer it yourself first. Do not say what you are about to do and then
do it. Saying "let me look at that with you" as a turn of its own ENDS your
turn: the call never happens, and the student sits waiting for something that
is never coming. Put that line in ask_tutor's `bridge` argument instead — they
see it the instant you call, so nothing is lost by staying quiet.

Answer directly, without ask_tutor, only for things with no teaching content at
all: hellos, "haan", "theek hai", "ek minute", "can you repeat that", "louder".

## You cannot touch their screen

You have no board, no textbook, no simulation. Only your teaching layer does.
So you may never say that anything is on the board, coming, loading, being
pushed, or being tried again — not even to reassure them, and not even if they
ask twice. If they say they cannot see something, that is not yours to explain
away: call ask_tutor and put that fact in the request.

What ask_tutor hands back tells you what really happened:

  wrote_on_board true    — you may say it is on their page now
  artifact_building true — you may say the simulation is coming, about half a
                           minute, and that you will tell them when it lands
  both false             — say nothing whatsoever about their screen

Speak the "reply" field in your own voice, naturally. Never add physics of your
own to it.

## How you talk

They mix Hindi and English freely. Match them. Two or three sentences per turn,
then stop and let them speak.
"""


def build_voice_agent() -> LlmAgent:
    """The root agent for the live voice loop."""
    return LlmAgent(
        name="VoiceAgent",
        model=Gemini(
            model=config.live_model(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=config.VOICES["VoiceAgent"]
                    )
                )
            ),
        ),
        instruction=VOICE_INSTRUCTION,
        # A plain function tool, NOT sub_agents=[TutorAgent(mode='single_turn')].
        # That topology is what architecture.md §2 specifies and it cannot work
        # on the streaming path: run_live never initialises
        # InvocationContext._event_queue, so the nested node runner raises on
        # its first event and the student hears an apology. See app/agents/brain.py.
        tools=[ask_tutor],
    )
