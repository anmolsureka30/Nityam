"""ADK tool functions for the shared memory layer. Every agent (TutorAgent,
ArtifactAgent) is given these same tool objects — this is what "one memory
layer, shared across agents" means concretely (memory_layer.md §3).

Long-term memory (dpm_profile, teaching_memory) is read-only here. The only
write path is close_session (app/session_close.py), run once at session end.
"""
from __future__ import annotations

import functools
import logging

from google.adk.tools import ToolContext

from app.memory import short_term, store

log = logging.getLogger("nityam.memory")


@functools.cache
def _conn():
    return store.connect()


def list_concepts() -> dict:
    """List every concept_id that actually exists in the grounding corpus.

    Call this once near the start of a session, or whenever the topic
    shifts to something not yet covered, BEFORE calling search_grounding —
    then pass concept_ids EXACTLY as they appear here, never a guess from
    the conversation's own wording. The corpus uses source-ingestion naming
    (e.g. "trajectory_equation_in_two-dimensional_motion"), which is often
    not how a student or tutor would naturally phrase the same topic —
    confirmed live, roughly two-thirds of invented concept_ids didn't match
    anything real (memory_layer_eval_report.md §2.1).

    Returns:
        dict with a "concept_ids" key: every real concept_id in the corpus.

        Both stores implement this now — store_sqlite.list_concept_ids reads
        them out of grounding_chunk_concept — so the empty-list fallback below
        is a genuine safety net rather than the sqlite path it used to be.
    """
    if store.list_concept_ids is None:
        return {"concept_ids": []}
    return {"concept_ids": store.list_concept_ids(_conn())}


def search_grounding(concept_ids: list[str]) -> dict:
    """Retrieve citable knowledge chunks (lecture/book excerpts) for the given concepts.

    Args:
        concept_ids: Concept ids to search for — use exact ids from
            list_concepts, e.g. ["projectile.horizontal_range"]. An id that
            doesn't exactly match still gets a fuzzy-matched retry (Firestore
            store only), but calling list_concepts first is far more reliable.

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


async def log_artifact_evidence(event: str, artifact_id: str, tool_context: ToolContext) -> dict:
    """Append an artifact interaction event (e.g. "discovered_optimum",
    "misconception_behavior" — see sub_modules/artifact_generator's probes)
    to the in-session buffer, and write through to Memorystore.

    Args:
        event: The event name the artifact reported.
        artifact_id: Which artifact reported it.

    Returns:
        dict confirming the event was buffered.
    """
    events = tool_context.state.get("artifact_events", [])
    entry = {"event": event, "artifact_id": artifact_id}
    events.append(entry)
    tool_context.state["artifact_events"] = events
    session_id = tool_context.state.get("session_id")
    if session_id:
        try:
            await short_term.append_artifact_event(session_id, entry)
        except Exception:  # noqa: BLE001 - a Redis outage must not break a live turn
            log.warning("artifact-event write-through to Redis failed", exc_info=True)
    return {"logged": True}
