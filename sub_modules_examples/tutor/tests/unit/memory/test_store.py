import sqlite3
from datetime import datetime, timezone

import pytest

from app.memory import store
from app.memory.schemas import DPMProfile, GroundingChunk, SessionLog, TeachingMemory, Turn, Weakness


@pytest.fixture
def conn():
    c = store.connect(":memory:")
    yield c
    c.close()


def test_put_and_search_grounding_chunk(conn):
    chunk = GroundingChunk(
        chunk_id="horizontal_range_0340",
        source_type="lecture",
        source_ref="shruti:d_jnekwca6i_4c5411d0",
        location="3:40",
        concept_ids=["projectile.horizontal_range"],
        text="The total horizontal distance traveled by a projectile...",
    )
    store.put_grounding_chunk(conn, chunk)

    results = store.search_grounding(conn, ["projectile.horizontal_range"])
    assert len(results) == 1
    assert results[0].chunk_id == "horizontal_range_0340"
    assert results[0].text.startswith("The total horizontal distance")


def test_search_grounding_returns_nothing_for_unknown_concept(conn):
    assert store.search_grounding(conn, ["nonexistent.concept"]) == []


def test_search_grounding_respects_limit(conn):
    for i in range(3):
        store.put_grounding_chunk(conn, GroundingChunk(
            chunk_id=f"c{i}", source_type="lecture", source_ref="shruti:x",
            concept_ids=["projectile.range"], text=f"chunk {i}",
        ))
    assert len(store.search_grounding(conn, ["projectile.range"], limit=2)) == 2


def test_foreign_keys_are_enforced_on_grounding_chunk_concept(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO grounding_chunk_concept (concept_id, chunk_id) VALUES (?, ?)",
            ("projectile.range", "nonexistent_chunk_id"),
        )


def test_dpm_round_trip(conn):
    assert store.get_dpm(conn, "demo_student") is None

    profile = DPMProfile(
        student_id="demo_student",
        weaknesses={"projectile.range": Weakness(mastery="partial", strength="weak", evidence=["s1#1"])},
    )
    store.put_dpm(conn, profile)

    loaded = store.get_dpm(conn, "demo_student")
    assert loaded is not None
    assert loaded.weaknesses["projectile.range"].mastery == "partial"


def test_dpm_put_overwrites_by_student_id(conn):
    store.put_dpm(conn, DPMProfile(student_id="demo_student"))
    store.put_dpm(conn, DPMProfile(student_id="demo_student", weaknesses={
        "projectile.range": Weakness(mastery="known", strength="strong", evidence=["s2#1"])
    }))
    loaded = store.get_dpm(conn, "demo_student")
    assert loaded.weaknesses["projectile.range"].mastery == "known"


def test_teaching_memory_round_trip(conn):
    assert store.get_teaching_memory(conn, "demo_student") is None

    memory = TeachingMemory(student_id="demo_student", syllabus=["projectile.range"])
    store.put_teaching_memory(conn, memory)

    loaded = store.get_teaching_memory(conn, "demo_student")
    assert loaded.syllabus == ["projectile.range"]


def test_session_log_round_trip(conn):
    log = SessionLog(
        session_id="s1",
        student_id="demo_student",
        started_at=datetime.now(timezone.utc),
        turns=[Turn(turn=1, role="student", text="hi")],
    )
    store.put_session_log(conn, log)

    loaded = store.get_session_log(conn, "s1")
    assert loaded is not None
    assert loaded.turns[0].text == "hi"


def test_get_session_log_missing_returns_none(conn):
    assert store.get_session_log(conn, "nonexistent") is None
