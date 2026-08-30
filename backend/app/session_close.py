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
from app.memory import instrumentation, ops, store
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
    doubt: how the confusion actually showed up — quote or closely
    paraphrase what the student said or did. Not a generic label like
    "confused about signs".
    correct_understanding: the specific idea that resolves it, detailed
    enough that a tutor reading only this, next session, knows exactly
    what to say. Not a one-line label either.

  close_doubt(concept_id)   -- only if the log shows a SPACED re-check succeeding,
                               never from one correct answer in this same session

  update_coverage(concept_id, elements_used, taught_at, status)
    taught_at must be exactly this session's id: "{session_id}"
    status must be exactly one of: in_progress, covered

  append_self_reflection(note, evidence)
    note: one specific, concrete observation about what worked or didn't
    for THIS student in THIS session. "Showed the area model before the
    algebra and it landed immediately" is useful. "Explain things clearly"
    or "be patient" is not — it says nothing a tutor didn't already know.

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


def apply_operations(
    profile: DPMProfile,
    memory: TeachingMemory,
    result: ReflectResult,
    session_id: str | None = None,
) -> tuple[DPMProfile, TeachingMemory]:
    """Validated ops only — an unknown op name or malformed args is dropped,
    never raised (memory_layer.md §4)."""
    handlers = {
        "set_mastery": lambda a: ops.set_mastery(profile, **a),
        "append_self_reflection": lambda a: ops.append_self_reflection(profile, **a),
        "open_doubt": lambda a: ops.open_doubt(memory, **a),
        # session_id, so close_doubt can refuse to resolve a doubt whose
        # only evidence is this same conversation — see its docstring.
        "close_doubt": lambda a: ops.close_doubt(memory, session_id=session_id, **a),
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
    topic: str = "",
    mode: str = "",
    board: dict | None = None,
) -> SessionLog:
    instrumentation.set_session_context(session_id)
    log = build_session_log(session_id, student_id, started_at, buffer)
    log.topic, log.mode = topic, mode
    log.board = board
    store.put_session_log(conn, log)

    profile = store.get_dpm(conn, student_id) or DPMProfile(student_id=student_id)
    memory = store.get_teaching_memory(conn, student_id) or TeachingMemory(student_id=student_id)

    # Deep copies, taken BEFORE apply_operations mutates them in place. This
    # is the whole recap: without a snapshot of the far side there is nothing
    # to compare against later, because the live documents have moved on.
    log.dpm_before = profile.model_copy(deep=True)
    log.teaching_before = memory.model_copy(deep=True)

    result = reflect(client, log)
    profile, memory = apply_operations(profile, memory, result, session_id)

    # Keep the summary reflect() already produced. It was being discarded:
    # SessionLog.summary has existed all along, every log written by this
    # function had it empty, and the next session's brief therefore had
    # nothing to say about where the last one got to.
    if result.summary and not log.summary:
        log.summary = result.summary.strip()

    log.dpm_after = profile.model_copy(deep=True)
    log.teaching_after = memory.model_copy(deep=True)
    log.operations = _describe_operations(result, log.dpm_before, profile)
    store.put_session_log(conn, log)

    store.put_dpm(conn, profile)
    store.put_teaching_memory(conn, memory)
    return log


def _describe_operations(
    result: ReflectResult, before: DPMProfile, after: DPMProfile
) -> list[dict]:
    """Every operation Reflect proposed, and whether it survived.

    A DROPPED operation is as worth showing as an accepted one — it is the
    validation gate visibly doing its job, and "the model asked to mark this
    durable and the rules refused" is a more convincing demonstration of a
    memory layer than a list of writes that all succeeded.

    Applied-ness is inferred by comparing the two snapshots rather than
    instrumented inside apply_operations, which drops ops silently by design
    and should keep doing so.
    """
    described: list[dict] = []
    for operation in result.operations:
        concept = (operation.args or {}).get("concept_id", "")
        applied = True
        if operation.op == "set_mastery" and concept:
            was = before.weaknesses.get(concept)
            now = after.weaknesses.get(concept)
            applied = now is not None and (was is None or was != now)
        described.append({
            "op": operation.op,
            "concept_id": concept,
            "args": {k: v for k, v in (operation.args or {}).items()
                     if k != "concept_id"},
            "applied": applied,
        })
    return described
