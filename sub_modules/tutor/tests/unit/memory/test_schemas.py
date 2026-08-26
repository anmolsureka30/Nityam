import pytest
from pydantic import ValidationError

from app.memory.schemas import (
    CoveredConcept,
    DPMProfile,
    GroundingChunk,
    OpenDoubt,
    Persona,
    SelfReflection,
    SessionLog,
    TeachingMemory,
    TeachingStyle,
    Turn,
    Weakness,
)


def test_grounding_chunk_valid():
    chunk = GroundingChunk(
        chunk_id="horizontal_range_0340",
        source_type="lecture",
        source_ref="shruti:d_jnekwca6i_4c5411d0",
        location="3:40",
        concept_ids=["projectile.horizontal_range"],
        text="The total horizontal distance traveled by a projectile...",
    )
    assert chunk.source_type == "lecture"


def test_grounding_chunk_requires_at_least_one_concept_id():
    with pytest.raises(ValidationError):
        GroundingChunk(
            chunk_id="x", source_type="book", source_ref="book:ch1",
            concept_ids=[], text="...",
        )


def test_grounding_chunk_rejects_unknown_source_type():
    with pytest.raises(ValidationError):
        GroundingChunk(
            chunk_id="x", source_type="video", source_ref="x",
            concept_ids=["a"], text="...",
        )


def test_weakness_requires_evidence():
    with pytest.raises(ValidationError):
        Weakness(mastery="partial", strength="weak", evidence=[])


def test_dpm_profile_valid_with_nested_records():
    profile = DPMProfile(
        student_id="demo_student",
        persona=Persona(preferred_pace="moderate", language_mix="hi-en", interests=["cricket"]),
        weaknesses={
            "projectile.horizontal_range": Weakness(
                mastery="partial", strength="weak", evidence=["s1#4"],
            )
        },
        self_reflection=[
            SelfReflection(note="responds well to area models", evidence=["s1#6"])
        ],
    )
    assert profile.weaknesses["projectile.horizontal_range"].mastery == "partial"
    assert profile.self_reflection[0].status == "active"


def test_dpm_profile_defaults_are_empty_not_missing():
    profile = DPMProfile(student_id="demo_student")
    assert profile.weaknesses == {}
    assert profile.self_reflection == []


def test_open_doubt_requires_evidence():
    with pytest.raises(ValidationError):
        OpenDoubt(
            concept_id="projectile.horizontal_range",
            doubt="thinks range formula uses u instead of u*cos(theta)",
            correct_understanding="R = u^2 sin(2 theta) / g",
            evidence=[],
        )


def test_teaching_memory_valid():
    memory = TeachingMemory(
        student_id="demo_student",
        syllabus=["projectile.horizontal_range", "projectile.maximum_height"],
        covered={
            "projectile.horizontal_range": CoveredConcept(
                elements_used=["worked-example"], taught_at=["s1#4"], status="in_progress",
            )
        },
        open_doubts=[
            OpenDoubt(
                concept_id="projectile.horizontal_range",
                doubt="uses u instead of u*cos(theta)",
                correct_understanding="R = u^2 sin(2 theta) / g",
                evidence=["s1#4"],
            )
        ],
        teaching_style=TeachingStyle(current_mode="socratic"),
    )
    assert memory.open_doubts[0].status == "active"


def test_teaching_memory_defaults():
    memory = TeachingMemory(student_id="demo_student")
    assert memory.covered == {}
    assert memory.teaching_style.current_mode == "direct"


def test_session_log_valid():
    from datetime import datetime, timezone

    log = SessionLog(
        session_id="s1",
        student_id="demo_student",
        started_at=datetime.now(timezone.utc),
        turns=[
            Turn(turn=1, role="student", text="why does range peak at 45 degrees?"),
            Turn(turn=2, role="tutor", text="what happens to each component as angle increases?", concept_id="projectile.horizontal_range"),
        ],
    )
    assert log.turns[0].turn == 1
    assert log.turns[1].concept_id == "projectile.horizontal_range"


def test_turn_requires_positive_turn_number():
    with pytest.raises(ValidationError):
        Turn(turn=0, role="student", text="x")
