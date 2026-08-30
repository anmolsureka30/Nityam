"""MemoryEvent — a local re-declaration of the same wire shape
sub_modules_examples/tutor's (and backend/'s) app.memory.instrumentation.
MemoryEvent publishes. Deliberately not imported from either app's package:
this service can point at either one purely via config (AGENT_BASE_URL/
REDIS_HOST), and importing one specific app's `app` package here would
prevent it from ever pointing at the other (both ship a top-level module
literally named `app`). See docs/superpowers/specs/
2026-08-28-backend-memory-observatory-design.md §3.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

Tier = Literal["workflow", "episodic", "long_term"]
Operation = Literal["read", "write"]
RecordType = Literal[
    "grounding_chunk", "dpm_profile", "teaching_memory",
    "session_log", "turn_buffer", "artifact_event",
]
ToolActor = Literal["voice_agent", "board_agent", "artifact_agent", "quiz_agent", "textbook_agent"]
ToolCallPhase = Literal["started", "done", "error", "busy"]


class MemoryEvent(BaseModel):
    event_id: str
    ts: str
    session_id: str | None
    student_id: str | None
    tier: Tier
    operation: Operation
    record_type: RecordType
    source_fn: str
    trace_id: str | None
    span_id: str | None
    payload: Any = None


class ToolCallEvent(BaseModel):
    kind: Literal["tool_call"] = "tool_call"
    event_id: str
    ts: str
    session_id: str | None
    student_id: str | None
    trace_id: str | None
    span_id: str | None
    actor: ToolActor
    tool_name: str
    phase: ToolCallPhase
    args_summary: str | None = None
    result_summary: str | None = None
    duration_ms: int | None = None


class FieldChange(BaseModel):
    path: str
    kind: str  # "added" | "removed" | "changed"
    old: object = None
    new: object = None
    label: str


class EnrichedEvent(BaseModel):
    kind: Literal["memory"] = "memory"
    event: MemoryEvent
    diff: list[FieldChange] = []


class EnrichedToolCallEvent(BaseModel):
    kind: Literal["tool_call"] = "tool_call"
    event: ToolCallEvent


__all__ = [
    "MemoryEvent", "FieldChange", "EnrichedEvent",
    "ToolCallEvent", "EnrichedToolCallEvent",
]
