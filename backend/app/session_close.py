"""Session close: buffer -> session_log (deterministic) + one Reflect call
proposing validated ops against dpm_profile/teaching_memory (memory_layer.md
§4). Triggered by the current session ending — not a background agent
(deferred.md).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from google import genai
from pydantic import BaseModel, Field, ValidationError

from app import config
from app.memory import ops, store
from app.memory.schemas import DPMProfile, SessionLog, TeachingMemory, Turn


def build_session_log(session_id: str, student_id: str, started_at: datetime, buffer: list[dict]) -> SessionLog:
    """Deterministic. No model call."""
    return SessionLog(
        session_id=session_id,
        student_id=student_id,
        started_at=started_at,
        ended_at=datetime.now(timezone.utc),
        turns=[Turn(**t) for t in buffer],
    )


class ReflectOp(BaseModel):
    op: str
    args: dict[str, Any]


class ReflectResult(BaseModel):
    operations: list[ReflectOp]
    summary: str


REFLECT_PROMPT = """You did not teach this session. Read it as an observer.

Session log:
{session_json}

Propose operations against this student's memory. Use ONLY these op names,
and ONLY these exact field values -- any value outside these sets is
rejected and the whole operation is dropped:

  set_mastery(concept_id, mastery, strength, evidence)
    mastery must be exactly one of: unknown, misconceived, partial, known, durable
    strength must be exactly one of: weak, strong

  open_doubt(concept_id, doubt, correct_understanding, evidence)

  close_doubt(concept_id)   -- only if the log shows a SPACED re-check succeeding,
                               never from one correct answer in this same session

  update_coverage(concept_id, elements_used, taught_at, status)
    taught_at must be exactly this session's id: "{session_id}"
    status must be exactly one of: in_progress, covered

  append_self_reflection(note, evidence)

Every evidence value must cite a real turn number from the session log
above, written literally as "{session_id}#" followed by the turn number,
e.g. "{session_id}#3". Do not invent turns that aren't there.
"""


class _ReflectOpWire(BaseModel):
    """The shape actually handed to Gemini's structured output.

    `ReflectOp.args` is `dict[str, Any]` — a JSON schema for that has no
    field names for the model to fill in, and live testing (in the
    sub_modules_examples/tutor sibling of this file) confirmed Gemini
    reliably returns `args: {}` for every operation as a result (silently
    dropped by apply_operations' TypeError guard, so close_session looked
    like it worked but never wrote anything). This flat, fully-typed
    struct gives every field a concrete schema; _to_reflect_op() below
    picks out only the fields that matter for each op's `op` value.
    """
    op: str
    concept_id: str | None = None
    mastery: str | None = None
    strength: str | None = None
    doubt: str | None = None
    correct_understanding: str | None = None
    elements_used: list[str] = Field(default_factory=list)
    taught_at: str | None = None
    status: str | None = None
    note: str | None = None
    evidence: list[str] = Field(default_factory=list)


class _ReflectResultWire(BaseModel):
    operations: list[_ReflectOpWire]
    summary: str


_OP_FIELDS = {
    "set_mastery": ("concept_id", "mastery", "strength", "evidence"),
    "open_doubt": ("concept_id", "doubt", "correct_understanding", "evidence"),
    "close_doubt": ("concept_id",),
    "update_coverage": ("concept_id", "elements_used", "taught_at", "status"),
    "append_self_reflection": ("note", "evidence"),
}


def _to_reflect_op(wire: _ReflectOpWire) -> ReflectOp:
    fields = _OP_FIELDS.get(wire.op, ())
    args = {f: getattr(wire, f) for f in fields if getattr(wire, f) is not None}
    return ReflectOp(op=wire.op, args=args)


def reflect(client: genai.Client, log: SessionLog) -> ReflectResult:
    response = client.models.generate_content(
        model=config.REASONING_MODEL,
        contents=REFLECT_PROMPT.format(session_json=log.model_dump_json(indent=2), session_id=log.session_id),
        config={"response_mime_type": "application/json", "response_schema": _ReflectResultWire},
    )
    wire = _ReflectResultWire.model_validate_json(response.text)
    return ReflectResult(
        summary=wire.summary,
        operations=[_to_reflect_op(op) for op in wire.operations],
    )


def apply_operations(profile: DPMProfile, memory: TeachingMemory, result: ReflectResult) -> tuple[DPMProfile, TeachingMemory]:
    """Validated ops only — an unknown op name or malformed args is dropped,
    never raised (memory_layer.md §4)."""
    handlers = {
        "set_mastery": lambda a: ops.set_mastery(profile, **a),
        "append_self_reflection": lambda a: ops.append_self_reflection(profile, **a),
        "open_doubt": lambda a: ops.open_doubt(memory, **a),
        "close_doubt": lambda a: ops.close_doubt(memory, **a),
        "update_coverage": lambda a: ops.update_coverage(memory, **a),
    }
    for operation in result.operations:
        handler = handlers.get(operation.op)
        if handler is None:
            continue
        try:
            handler(operation.args)
        except (TypeError, ValidationError):
            # TypeError: wrong/missing/extra keyword args for the op.
            # ValidationError: args can be well-typed but still violate the
            # target schema, e.g. an out-of-enum mastery value or an empty
            # evidence list. Either way: drop this one op, never crash the
            # whole close_session run over it (memory_layer.md §4).
            #
            # Deliberately NOT a bare `ValueError` catch: that would also
            # swallow a genuine unrelated ValueError from some future op
            # doing manual parsing (int(...), datetime.fromisoformat(...),
            # an enum lookup) and silently misfile it as "just a malformed
            # op" forever. ValidationError is pydantic's specific type for
            # exactly the case this is meant to handle.
            continue
    return profile, memory


def close_session(
    conn: sqlite3.Connection,
    session_id: str,
    student_id: str,
    started_at: datetime,
    buffer: list[dict],
    client: genai.Client,
) -> SessionLog:
    log = build_session_log(session_id, student_id, started_at, buffer)
    store.put_session_log(conn, log)

    profile = store.get_dpm(conn, student_id) or DPMProfile(student_id=student_id)
    memory = store.get_teaching_memory(conn, student_id) or TeachingMemory(student_id=student_id)

    result = reflect(client, log)
    profile, memory = apply_operations(profile, memory, result)

    store.put_dpm(conn, profile)
    store.put_teaching_memory(conn, memory)
    return log
