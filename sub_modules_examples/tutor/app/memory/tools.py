"""ADK tool functions for the shared memory layer. Every agent (TutorAgent,
ArtifactAgent) is given these same tool objects — this is what "one memory
layer, shared across agents" means concretely (memory_layer.md §3).

Long-term memory (dpm_profile, teaching_memory) is read-only here. The only
write path is close_session (app/session_close.py), run once at session end.
"""
from __future__ import annotations

import functools

from google.adk.tools import ToolContext

from app.memory import store


@functools.cache
def _conn():
    return store.connect()


def search_grounding(concept_ids: list[str]) -> dict:
    """Retrieve citable knowledge chunks (lecture/book excerpts) for the given concepts.

    Args:
        concept_ids: Concept ids to search for, e.g. ["projectile.horizontal_range"].

    Returns:
        dict with a "chunks" key: a list of {chunk_id, source_ref, location, text}.
    """
    chunks = store.search_grounding(_conn(), concept_ids)
    return {
        "chunks": [
            c.model_dump(include={"chunk_id", "source_ref", "location", "text"})
            for c in chunks
        ]
    }


def get_dpm(tool_context: ToolContext) -> dict:
    """Read this session's student's Dynamic Personal Memory: persona, coarse
    per-concept mastery, and standing pedagogical reflections.

    Returns:
        dict with the DPM profile fields, or {"found": false} if none exists yet.
    """
    student_id = tool_context.state["student_id"]
    profile = store.get_dpm(_conn(), student_id)
    if profile is None:
        return {"found": False}
    return {"found": True, **profile.model_dump(mode="json")}


def get_teaching_memory(tool_context: ToolContext) -> dict:
    """Read this session's student's Teaching Memory: syllabus coverage, open
    doubts, and the current teaching mode.

    Returns:
        dict with the teaching memory fields, or {"found": false} if none exists yet.
    """
    student_id = tool_context.state["student_id"]
    memory = store.get_teaching_memory(_conn(), student_id)
    if memory is None:
        return {"found": False}
    return {"found": True, **memory.model_dump(mode="json")}


def log_turn(text: str, role: str, concept_id: str, artifact_id: str, tool_context: ToolContext) -> dict:
    """Append one turn to the in-session buffer. RAM only — never written to
    disk mid-session (memory_layer.md §3). Call this after every exchange.

    Args:
        text: What was said.
        role: "student" or "tutor".
        concept_id: The concept this turn is about. Pass "" if none.
        artifact_id: The artifact this turn references. Pass "" if none.

    Returns:
        dict with the new buffer length.
    """
    buffer = tool_context.state.get("turn_buffer", [])
    buffer.append({
        "turn": len(buffer) + 1,
        "role": role,
        "text": text,
        "concept_id": concept_id or None,
        "artifact_id": artifact_id or None,
    })
    tool_context.state["turn_buffer"] = buffer
    return {"buffer_length": len(buffer)}


def log_artifact_evidence(event: str, artifact_id: str, tool_context: ToolContext) -> dict:
    """Append an artifact interaction event (e.g. "discovered_optimum",
    "misconception_behavior" — see sub_modules/artifact_generator's probes)
    to the in-session buffer.

    Args:
        event: The event name the artifact reported.
        artifact_id: Which artifact reported it.

    Returns:
        dict confirming the event was buffered.
    """
    events = tool_context.state.get("artifact_events", [])
    events.append({"event": event, "artifact_id": artifact_id})
    tool_context.state["artifact_events"] = events
    return {"logged": True}
