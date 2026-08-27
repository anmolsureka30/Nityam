"""Runs one persona's full multi-session scenario against the real TutorAgent,
capturing a structured trace of every turn (text + tool calls) and driving
close_session between sessions - standing in for the live session-end
trigger that doesn't exist yet (see the eval design spec §1).

Every signature used here (Runner.run_async, Event.is_final_response/
get_function_calls/get_function_responses, InMemorySessionService.
create_session) was confirmed against the installed google-adk==2.7.1
source before this file was written, not assumed from docs.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Any

from google import genai
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agents.tutor_agent import build_tutor_agent
from app.memory import short_term, store
from app.memory.schemas import CoveredConcept, DPMProfile, TeachingMemory, Weakness
from app.session_close import close_session
from tests.eval.memory_eval.personas import Persona


@dataclasses.dataclass
class ToolCallRecord:
    name: str
    args: dict[str, Any]
    result: dict[str, Any] | None


@dataclasses.dataclass
class TurnRecord:
    role: str  # "student" | "tutor"
    text: str
    tool_calls: list[ToolCallRecord] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class SessionTrace:
    session_id: str
    label: str
    turns: list[TurnRecord]
    post_close_dpm: DPMProfile
    post_close_teaching_memory: TeachingMemory
    """Snapshots of long-term memory immediately after this session's
    close_session call - not just the final state at the end of the whole
    scenario. Needed to check that mastery/doubt-status transitions happen
    in the right session, and that mastery doesn't move in an unjustified
    direction between sessions - the exact temporal-instability failure
    mode the eval design's research pass found in LLM-based (vs.
    specialized) learner models."""


@dataclasses.dataclass
class PersonaResult:
    persona: Persona
    session_traces: list[SessionTrace]
    baseline_reply: str | None = None
    """Session 2's opening line, replayed against a fresh unseeded student
    with the same persona traits but zero history - computed here (still
    inside the agent-execution phase) rather than inside the judging phase,
    where a direct genai.Client() call runs. Confirmed live across three
    attempts: running an ADK agent turn and a separate raw genai call in the
    same async context breaks the genai SDK's connector lifecycle (a sync
    Client -> "client has been closed"; the async Client -> aiohttp
    "self._connector is not None" AssertionError). Keeping all agent
    execution in one phase and all raw judge calls in a separate,
    agent-free phase (judges.py) sidesteps it structurally rather than by
    chasing the exact SDK bug further."""


def _apply_pre_seed(persona: Persona, db) -> None:
    """Writes Rohan's pre-existing history directly to Firestore, before any
    live session - simulating a student with real history this eval didn't
    create, not a live-session artifact (eval design spec §3, Rohan row)."""
    if persona.pre_seed is None:
        return
    weaknesses = {
        cid: Weakness(**w) for cid, w in persona.pre_seed.get("weaknesses", {}).items()
    }
    store.put_dpm(db, DPMProfile(student_id=persona.student_id, weaknesses=weaknesses))
    covered = {
        cid: CoveredConcept(**c) for cid, c in persona.pre_seed.get("covered", {}).items()
    }
    store.put_teaching_memory(
        db, TeachingMemory(student_id=persona.student_id, covered=covered)
    )


async def run_turn(runner: InMemoryRunner, user_id: str, session_id: str, text: str) -> TurnRecord:
    """Collects the FULL trace (every tool call across the whole invocation,
    including nested single_turn sub-agents like ArtifactAgent), but only
    the root agent's own final text as the "reply" - a nested sub-agent's
    own final_response=True event (confirmed live: ArtifactAgent emits one,
    e.g. its own "**Artifact ID:** ..." text) is that sub-agent's return
    value as a tool result, not part of what the root agent actually said to
    the student. Collecting every final_response event regardless of author
    silently concatenated ArtifactAgent's own artifact-id text in front of
    TutorAgent's real reply - caught by inspecting a raw event dump, not
    assumed from the API shape."""
    message = types.Content(role="user", parts=[types.Part.from_text(text=text)])
    tool_calls: list[ToolCallRecord] = []
    pending_calls: dict[str, ToolCallRecord] = {}
    final_text_parts: list[str] = []
    root_agent_name = runner.agent.name

    async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=message):
        for call in event.get_function_calls():
            record = ToolCallRecord(name=call.name, args=dict(call.args or {}), result=None)
            tool_calls.append(record)
            pending_calls[call.id] = record
        for response in event.get_function_responses():
            if response.id in pending_calls:
                pending_calls[response.id].result = dict(response.response or {})
        if event.author == root_agent_name and event.is_final_response() and event.content and event.content.parts:
            final_text_parts.extend(p.text for p in event.content.parts if p.text)

    return TurnRecord(role="tutor", text="".join(final_text_parts), tool_calls=tool_calls)


async def run_persona_scenario(persona: Persona) -> PersonaResult:
    db = store.connect()
    _apply_pre_seed(persona, db)

    agent = build_tutor_agent()
    runner = InMemoryRunner(agent=agent, app_name="memory_eval")
    genai_client = genai.Client()

    session_traces: list[SessionTrace] = []

    for session in persona.sessions:
        session_id = f"{persona.student_id}__{session.label}"
        await runner.session_service.create_session(
            app_name="memory_eval",
            user_id=persona.student_id,
            session_id=session_id,
            state={"student_id": persona.student_id},
        )

        started_at = datetime.now(timezone.utc)
        turns: list[TurnRecord] = []
        for student_text in session.student_turns:
            turns.append(TurnRecord(role="student", text=student_text))
            tutor_turn = await run_turn(runner, persona.student_id, session_id, student_text)
            turns.append(tutor_turn)

        # Read the buffer back from Redis - proves the write-through mirror
        # actually worked (not just that tool_context.state held it), and is
        # exactly the source close_session would read from in a process where
        # the live conversation and the session-close trigger are different
        # processes (google_cloud_storage_integration.md §5.3).
        buffer = await short_term.get_turn_buffer(session_id)
        close_session(db, session_id, persona.student_id, started_at, buffer, client=genai_client)
        await short_term.clear_session(session_id)

        post_close_dpm = store.get_dpm(db, persona.student_id) or DPMProfile(student_id=persona.student_id)
        post_close_memory = store.get_teaching_memory(db, persona.student_id) or TeachingMemory(student_id=persona.student_id)
        session_traces.append(SessionTrace(
            session_id=session_id, label=session.label, turns=turns,
            post_close_dpm=post_close_dpm, post_close_teaching_memory=post_close_memory,
        ))

    baseline_reply = None
    if len(session_traces) >= 2:
        opening_line = next(t.text for t in session_traces[1].turns if t.role == "student")
        baseline_agent = build_tutor_agent()
        baseline_runner = InMemoryRunner(agent=baseline_agent, app_name="memory_eval_baseline")
        baseline_student_id = f"{persona.student_id}_noeval_baseline"
        baseline_session_id = f"{baseline_student_id}__baseline"
        await baseline_runner.session_service.create_session(
            app_name="memory_eval_baseline", user_id=baseline_student_id,
            session_id=baseline_session_id, state={"student_id": baseline_student_id},
        )
        baseline_turn = await run_turn(baseline_runner, baseline_student_id, baseline_session_id, opening_line)
        await short_term.clear_session(baseline_session_id)
        baseline_reply = baseline_turn.text

    return PersonaResult(persona=persona, session_traces=session_traces, baseline_reply=baseline_reply)


async def cleanup_persona(persona: Persona, db) -> None:
    """Deletes every Firestore document and Redis key this persona's run
    created - same discipline as the testbed and the ported unit tests
    (eval design spec §7)."""
    db.collection("dpm_profiles").document(persona.student_id).delete()
    db.collection("teaching_memories").document(persona.student_id).delete()
    for session in persona.sessions:
        session_id = f"{persona.student_id}__{session.label}"
        db.collection("session_logs").document(session_id).delete()
        await short_term.clear_session(session_id)
