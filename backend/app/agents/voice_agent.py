"""VoiceAgent — the ears and the mouth. Nothing else lives here.

The student perceives one tutor. Underneath there are two model layers, and the
split is forced, not stylistic: **the Live API bills every context token,
including the system instruction, on every single turn.** A memory-sized prompt
re-billed across sixty turns of a session is real money and real latency. So
memory, grounding and the board all live in TutorAgent, reached through a tool
call, and this instruction stays deliberately small.

The cost of the split is a pause: a substantive turn is Live → tool → a full
reasoning turn with its own tool calls → back to Live → speech. The mitigation
is in the instruction below — say something first, *then* delegate. The Live
model can emit audio and then call a tool in the same turn, which is exactly
what a human tutor does when they say "hold on, let me look at that with you".
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

Call ask_tutor for anything substantive — a question, a doubt, an answer to
work through, something they marked on the page, a checkpoint they answered, a
request to be quizzed or shown something. It decides what to teach and writes on
their board; you speak what it gives you back.

BEFORE you call ask_tutor, always say one short thing first — "let me look at
that with you", "good question, one second", "achha, so —". Never call it in
silence: the student is left listening to nothing for a few seconds and assumes
you did not hear them.

Answer directly, without ask_tutor, only for things with no teaching content:
greetings, "haan", "theek hai", "can you repeat that", "louder please".

When it replies, speak the "reply" field in your own voice, naturally and
briefly. If it says it wrote something on the board, tell them to look — "it's
on your page now". Never invent physics of your own, and never claim something
is on the board unless ask_tutor's reply said so.

They mix Hindi and English freely. Match them. Keep every turn to two or three
sentences and then stop talking.
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
