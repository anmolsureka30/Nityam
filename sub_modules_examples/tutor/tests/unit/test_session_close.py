"""apply_operations and build_session_log need no API call — tested here
directly. reflect() itself calls the live model and is exercised only in the
manual live-verification step below. close_session's orchestration is
covered by monkeypatching reflect() with a canned ReflectResult, so no API
call happens there either — only the plumbing (build -> persist -> reflect ->
apply -> persist) is under test."""
from datetime import datetime, timezone

import app.session_close as session_close
from app.memory import instrumentation, store
from app.memory.schemas import DPMProfile, TeachingMemory
from app.session_close import (
    ReflectOp,
    ReflectResult,
    _ReflectOpWire,
    _to_reflect_op,
    apply_operations,
    build_session_log,
    close_session,
)


def test_build_session_log_is_deterministic():
    started = datetime.now(timezone.utc)
    buffer = [
        {"turn": 1, "role": "student", "text": "why 45 degrees?", "concept_id": None, "artifact_id": None},
        {"turn": 2, "role": "tutor", "text": "what happens to each component?", "concept_id": "projectile.range", "artifact_id": None},
    ]
    log = build_session_log("s1", "demo_student", started, buffer)

    assert log.session_id == "s1"
    assert len(log.turns) == 2
    assert log.turns[1].concept_id == "projectile.range"
    assert log.ended_at is not None


def test_to_reflect_op_extracts_only_the_fields_that_op_uses():
    """The wire schema (what Gemini's structured output actually fills in)
    is flat with every field on every op — _to_reflect_op must pick out
    only the fields relevant to `op` so downstream ops.* calls don't choke
    on unexpected keyword args."""
    wire = _ReflectOpWire(
        op="set_mastery", concept_id="projectile.range", mastery="known",
        strength="strong", evidence=["s1#2"],
        # fields belonging to other ops, populated because the wire schema
        # has no way to omit them — must not leak into set_mastery's args.
        doubt="unrelated", note="unrelated", status="covered",
    )
    result = _to_reflect_op(wire)
    assert result.op == "set_mastery"
    assert result.args == {
        "concept_id": "projectile.range", "mastery": "known",
        "strength": "strong", "evidence": ["s1#2"],
    }


def test_to_reflect_op_omits_unset_fields_entirely():
    """A field the model left unset (None) must be absent from args, not
    passed through as a literal None — set_mastery's evidence is required,
    so a missing key (not evidence=None) is what makes apply_operations'
    TypeError guard correctly drop this as a malformed op."""
    wire = _ReflectOpWire(op="close_doubt", concept_id="projectile.range")
    result = _to_reflect_op(wire)
    assert result.args == {"concept_id": "projectile.range"}


def test_apply_operations_runs_known_ops_and_skips_unknown():
    profile = DPMProfile(student_id="demo_student")
    memory = TeachingMemory(student_id="demo_student")
    result = ReflectResult(
        summary="student worked through range formula",
        operations=[
            ReflectOp(op="set_mastery", args={
                "concept_id": "projectile.range", "mastery": "partial",
                "strength": "weak", "evidence": ["s1#2"],
            }),
            ReflectOp(op="open_doubt", args={
                "concept_id": "projectile.range", "doubt": "uses u not u*cos(theta)",
                "correct_understanding": "R = u^2 sin(2theta)/g", "evidence": ["s1#2"],
            }),
            ReflectOp(op="some_future_op_this_version_does_not_know", args={"x": 1}),
        ],
    )

    profile, memory = apply_operations(profile, memory, result)

    assert profile.weaknesses["projectile.range"].mastery == "partial"
    assert memory.open_doubts[0].concept_id == "projectile.range"


def test_apply_operations_drops_malformed_args_without_raising():
    profile = DPMProfile(student_id="demo_student")
    memory = TeachingMemory(student_id="demo_student")
    result = ReflectResult(
        summary="",
        operations=[ReflectOp(op="set_mastery", args={"concept_id": "x"})],  # missing required args
    )

    # Must not raise — a malformed op is dropped, not a crash (memory_layer.md §4).
    profile, memory = apply_operations(profile, memory, result)
    assert profile.weaknesses == {}


def test_apply_operations_drops_schema_violating_args_without_raising():
    """args can be well-typed (right keyword names) but still violate the
    target schema's own constraints — e.g. an out-of-enum mastery value, or
    an empty evidence list where Weakness/OpenDoubt require min_length=1.
    Pydantic raises ValidationError (a ValueError subclass) for these, not
    TypeError, so apply_operations must also swallow that — one bad op
    dropped, not a crash for the whole close_session run."""
    profile = DPMProfile(student_id="demo_student")
    memory = TeachingMemory(student_id="demo_student")
    result = ReflectResult(
        summary="",
        operations=[
            ReflectOp(op="set_mastery", args={
                "concept_id": "x", "mastery": "not_a_real_status",
                "strength": "weak", "evidence": ["s1#1"],
            }),
            ReflectOp(op="open_doubt", args={
                "concept_id": "y", "doubt": "d", "correct_understanding": "c",
                "evidence": [],  # violates min_length=1
            }),
        ],
    )

    profile, memory = apply_operations(profile, memory, result)
    assert profile.weaknesses == {}
    assert memory.open_doubts == []


def test_close_session_runs_build_persist_reflect_apply_persist_in_order(firestore_db, monkeypatch):
    """Covers close_session's own orchestration, which none of the other
    tests touch: build the log, persist it, load profile/memory, call
    reflect(), apply the result, persist profile/memory, and return the log.
    reflect() is monkeypatched to a canned ReflectResult so this needs no
    live API call — only the plumbing around it is under test."""
    conn = firestore_db

    stub_result = ReflectResult(
        summary="student worked through the range formula",
        operations=[
            ReflectOp(op="set_mastery", args={
                "concept_id": "projectile.range", "mastery": "partial",
                "strength": "weak", "evidence": ["s1#2"],
            }),
            ReflectOp(op="open_doubt", args={
                "concept_id": "projectile.range", "doubt": "uses u not u*cos(theta)",
                "correct_understanding": "R = u^2 sin(2theta)/g", "evidence": ["s1#2"],
            }),
        ],
    )
    monkeypatch.setattr(session_close, "reflect", lambda client, log: stub_result)

    started = datetime.now(timezone.utc)
    buffer = [
        {"turn": 1, "role": "student", "text": "why 45 degrees?", "concept_id": None, "artifact_id": None},
        {"turn": 2, "role": "tutor", "text": "range formula", "concept_id": "projectile.range", "artifact_id": None},
    ]

    try:
        returned_log = close_session(conn, "test_s1", "test_demo_student", started, buffer, client=None)

        # Returned SessionLog is the same one build_session_log would produce.
        assert returned_log.session_id == "test_s1"
        assert returned_log.student_id == "test_demo_student"
        assert len(returned_log.turns) == 2
        assert returned_log.turns[1].concept_id == "projectile.range"

        # session_log row landed in the store.
        stored_log = store.get_session_log(conn, "test_s1")
        assert stored_log is not None
        assert stored_log.model_dump() == returned_log.model_dump()

        # dpm_profile updated per the stubbed set_mastery op.
        profile = store.get_dpm(conn, "test_demo_student")
        assert profile is not None
        assert profile.weaknesses["projectile.range"].mastery == "partial"
        assert profile.weaknesses["projectile.range"].evidence == ["s1#2"]

        # teaching_memory updated per the stubbed open_doubt op.
        memory = store.get_teaching_memory(conn, "test_demo_student")
        assert memory is not None
        assert memory.open_doubts[0].concept_id == "projectile.range"
        assert memory.open_doubts[0].status == "active"
    finally:
        conn.collection("session_logs").document("test_s1").delete()
        conn.collection("dpm_profiles").document("test_demo_student").delete()
        conn.collection("teaching_memories").document("test_demo_student").delete()


def test_close_session_scopes_long_term_writes_to_session_context(firestore_db, monkeypatch, redis_client):
    """The whole point of Task 4: put_dpm/put_teaching_memory don't receive
    a session_id argument, so close_session must set the context var itself
    before calling them."""
    redis_client.delete("smriti:events:recent")
    stub_result = ReflectResult(
        summary="", operations=[ReflectOp(op="set_mastery", args={
            "concept_id": "projectile.range", "mastery": "partial",
            "strength": "weak", "evidence": ["s1#2"],
        })],
    )
    monkeypatch.setattr(session_close, "reflect", lambda client, log: stub_result)

    try:
        close_session(
            firestore_db, "test_s_ctx_1", "test_demo_student_ctx", datetime.now(timezone.utc),
            [{"turn": 1, "role": "student", "text": "x", "concept_id": None, "artifact_id": None}],
            client=None,
        )
        events = [
            instrumentation.MemoryEvent.model_validate_json(raw)
            for raw in redis_client.lrange("smriti:events:recent", 0, -1)
        ]
        dpm_writes = [e for e in events if e.record_type == "dpm_profile" and e.operation == "write"]
        assert len(dpm_writes) == 1
        assert dpm_writes[0].session_id == "test_s_ctx_1"
    finally:
        firestore_db.collection("session_logs").document("test_s_ctx_1").delete()
        firestore_db.collection("dpm_profiles").document("test_demo_student_ctx").delete()
        firestore_db.collection("teaching_memories").document("test_demo_student_ctx").delete()
