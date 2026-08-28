"""One Runner+session bootstrap, shared by every specialist agent reached
from VoiceAgent (BoardAgent, ArtifactAgent, QuizAgent, TextbookAgent).

Each specialist runs in its own Runner via run_async, for the same reason
brain.py's TutorAgent always did: run_live never initialises
InvocationContext._event_queue, so a mode='single_turn' sub-agent nested
under a live VoiceAgent crashes on its first event. Reached instead as a
plain async function tool, tagged response_scheduling=WHEN_IDLE so the
Gemini Live API itself holds the result until VoiceAgent is between things
— see docs/superpowers/specs/2026-08-28-agent-orchestration-redesign-design.md §2.

This used to be hand-rolled once per specialist (brain.py's runner()/
_ensure_session()/_known, artifact_agent.py's near-identical copy) — written
once here instead.
"""
from __future__ import annotations

from typing import Callable

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.memory import short_term


class SpecialistRunner:
    """Builds its agent and Runner once; ensures a session per session_id."""

    def __init__(self, app_name: str, build_agent: Callable[[], LlmAgent]) -> None:
        self._app_name = app_name
        self._build_agent = build_agent
        self._runner: Runner | None = None
        self._sessions: InMemorySessionService | None = None
        self._known: set[str] = set()

    def _runner_instance(self) -> Runner:
        if self._runner is None:
            self._sessions = InMemorySessionService()
            self._runner = Runner(
                app=App(name=self._app_name, root_agent=self._build_agent()),
                session_service=self._sessions,
            )
        return self._runner

    async def _ensure_session(self, session_id: str, student_id: str) -> None:
        if session_id in self._known:
            return
        runner = self._runner_instance()
        existing = await self._sessions.get_session(
            app_name=self._app_name, user_id=student_id, session_id=session_id,
        )
        if not existing:
            await self._sessions.create_session(
                app_name=self._app_name, user_id=student_id, session_id=session_id,
                state={"session_id": session_id, "student_id": student_id},
            )
        self._known.add(session_id)
        _ = runner  # built as a side effect of _runner_instance(); kept for clarity

    async def run_turn(self, session_id: str, student_id: str, message: str) -> str:
        """Run one turn to completion; return whatever text the specialist said."""
        await self._ensure_session(session_id, student_id)
        said: list[str] = []
        async for event in self._runner_instance().run_async(
            user_id=student_id, session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part(text=message)]),
        ):
            for part in event.content.parts if event.content and event.content.parts else []:
                if part.text:
                    said.append(part.text)
        return " ".join(said).strip()


async def recent_transcript(session_id: str, student_id: str, n: int) -> str:
    """The last n recorded turns, formatted for a specialist's prompt."""
    buffer = await short_term.get_turn_buffer(session_id, student_id)
    recent = buffer[-n:]
    if not recent:
        return "No prior turns recorded yet this session."
    lines = [f"{turn['role']}: {turn['text']}" for turn in recent]
    return "Recent conversation:\n" + "\n".join(lines)
