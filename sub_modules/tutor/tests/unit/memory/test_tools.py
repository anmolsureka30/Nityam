from unittest.mock import MagicMock

import pytest

from app.memory import store, tools
from app.memory.schemas import DPMProfile, GroundingChunk, TeachingMemory, Weakness


@pytest.fixture(autouse=True)
def isolated_store(monkeypatch):
    """Each test gets its own in-memory DB instead of the process-wide one."""
    conn = store.connect(":memory:")
    tools._conn.cache_clear()
    monkeypatch.setattr(tools, "_conn", lambda: conn)
    yield conn
    conn.close()


def make_tool_context(state: dict) -> MagicMock:
    ctx = MagicMock()
    ctx.state = state
    return ctx


def test_search_grounding_returns_chunks(isolated_store):
    store.put_grounding_chunk(isolated_store, GroundingChunk(
        chunk_id="c1", source_type="lecture", source_ref="shruti:x", location="0:00",
        concept_ids=["projectile.range"], text="range excerpt",
    ))
    result = tools.search_grounding(["projectile.range"])
    assert result["chunks"][0]["text"] == "range excerpt"
    assert result["chunks"][0]["chunk_id"] == "c1"


def test_search_grounding_empty_for_unknown_concept(isolated_store):
    assert tools.search_grounding(["nonexistent"]) == {"chunks": []}


def test_get_dpm_not_found(isolated_store):
    ctx = make_tool_context({"student_id": "demo_student"})
    assert tools.get_dpm(ctx) == {"found": False}


def test_get_dpm_found(isolated_store):
    store.put_dpm(isolated_store, DPMProfile(
        student_id="demo_student",
        weaknesses={"projectile.range": Weakness(mastery="partial", strength="weak", evidence=["s1#1"])},
    ))
    ctx = make_tool_context({"student_id": "demo_student"})
    result = tools.get_dpm(ctx)
    assert result["found"] is True
    assert result["weaknesses"]["projectile.range"]["mastery"] == "partial"


def test_get_teaching_memory_not_found(isolated_store):
    ctx = make_tool_context({"student_id": "demo_student"})
    assert tools.get_teaching_memory(ctx) == {"found": False}


def test_get_teaching_memory_found(isolated_store):
    store.put_teaching_memory(isolated_store, TeachingMemory(student_id="demo_student", syllabus=["projectile.range"]))
    ctx = make_tool_context({"student_id": "demo_student"})
    result = tools.get_teaching_memory(ctx)
    assert result["found"] is True
    assert result["syllabus"] == ["projectile.range"]


def test_log_turn_appends_to_buffer():
    ctx = make_tool_context({})
    tools.log_turn("why does range peak at 45?", "student", "", "", ctx)
    result = tools.log_turn("what happens to each component?", "tutor", "projectile.range", "", ctx)
    assert result["buffer_length"] == 2
    assert ctx.state["turn_buffer"][1]["role"] == "tutor"
    assert ctx.state["turn_buffer"][1]["concept_id"] == "projectile.range"
    assert ctx.state["turn_buffer"][0]["concept_id"] is None


def test_log_artifact_evidence_appends_to_buffer():
    ctx = make_tool_context({})
    result = tools.log_artifact_evidence("discovered_optimum", "artifact-abc123", ctx)
    assert result == {"logged": True}
    assert ctx.state["artifact_events"] == [{"event": "discovered_optimum", "artifact_id": "artifact-abc123"}]
