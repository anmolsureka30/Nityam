from unittest.mock import MagicMock

import pytest

from app.memory import store, tools
from app.memory.schemas import DPMProfile, GroundingChunk, TeachingMemory, Weakness


@pytest.fixture(autouse=True)
def isolated_store(firestore_db, monkeypatch):
    """Points tools._conn() at the same real Firestore client the test uses,
    so writes made via store.* are visible to tools.* calls in the same test
    (mirrors the old in-memory-SQLite isolation, but against real Firestore
    with real cleanup instead)."""
    tools._conn.cache_clear()
    monkeypatch.setattr(tools, "_conn", lambda: firestore_db)
    yield firestore_db


def make_tool_context(state: dict, session_id: str = "test_session_tools_1") -> MagicMock:
    ctx = MagicMock()
    ctx.state = state
    ctx.session.id = session_id
    return ctx


def test_search_grounding_returns_chunks(isolated_store):
    try:
        store.put_grounding_chunk(isolated_store, GroundingChunk(
            chunk_id="test_tools_c1", source_type="lecture", source_ref="shruti:x", location="0:00",
            concept_ids=["test.projectile.range"], text="range excerpt",
        ))
        result = tools.search_grounding(["test.projectile.range"])
        assert result["chunks"][0]["text"] == "range excerpt"
        assert result["chunks"][0]["chunk_id"] == "test_tools_c1"
    finally:
        isolated_store.collection("grounding_chunks").document("test_tools_c1").delete()


def test_search_grounding_empty_for_unknown_concept(isolated_store):
    assert tools.search_grounding(["test.nonexistent"]) == {"chunks": []}


def test_list_concepts_returns_real_vocabulary(isolated_store):
    try:
        store.put_grounding_chunk(isolated_store, GroundingChunk(
            chunk_id="test_tools_c2", source_type="lecture", source_ref="shruti:x",
            concept_ids=["test.projectile.range"], text="range excerpt",
        ))
        result = tools.list_concepts()
        assert "test.projectile.range" in result["concept_ids"]
    finally:
        isolated_store.collection("grounding_chunks").document("test_tools_c2").delete()


def test_get_dpm_not_found(isolated_store):
    ctx = make_tool_context({"student_id": "test_tools_student_nonexistent"})
    assert tools.get_dpm(ctx) == {"found": False}


def test_get_dpm_found(isolated_store):
    try:
        store.put_dpm(isolated_store, DPMProfile(
            student_id="test_tools_student_1",
            weaknesses={"projectile.range": Weakness(mastery="partial", strength="weak", evidence=["s1#1"])},
        ))
        ctx = make_tool_context({"student_id": "test_tools_student_1"})
        result = tools.get_dpm(ctx)
        assert result["found"] is True
        assert result["weaknesses"]["projectile.range"]["mastery"] == "partial"
    finally:
        isolated_store.collection("dpm_profiles").document("test_tools_student_1").delete()


def test_get_teaching_memory_not_found(isolated_store):
    ctx = make_tool_context({"student_id": "test_tools_student_nonexistent"})
    assert tools.get_teaching_memory(ctx) == {"found": False}


def test_get_teaching_memory_found(isolated_store):
    try:
        store.put_teaching_memory(isolated_store, TeachingMemory(student_id="test_tools_student_1", syllabus=["projectile.range"]))
        ctx = make_tool_context({"student_id": "test_tools_student_1"})
        result = tools.get_teaching_memory(ctx)
        assert result["found"] is True
        assert result["syllabus"] == ["projectile.range"]
    finally:
        isolated_store.collection("teaching_memories").document("test_tools_student_1").delete()


@pytest.mark.asyncio
async def test_log_turn_appends_to_buffer(redis_client):
    ctx = make_tool_context({}, session_id="test_session_log_turn")
    try:
        await tools.log_turn("why does range peak at 45?", "student", "", "", ctx)
        result = await tools.log_turn("what happens to each component?", "tutor", "projectile.range", "", ctx)
        assert result["buffer_length"] == 2
        assert ctx.state["turn_buffer"][1]["role"] == "tutor"
        assert ctx.state["turn_buffer"][1]["concept_id"] == "projectile.range"
        assert ctx.state["turn_buffer"][0]["concept_id"] is None
    finally:
        redis_client.delete("session:test_session_log_turn:turns")


@pytest.mark.asyncio
async def test_log_artifact_evidence_appends_to_buffer(redis_client):
    ctx = make_tool_context({}, session_id="test_session_artifact_evidence")
    try:
        result = await tools.log_artifact_evidence("discovered_optimum", "artifact-abc123", ctx)
        assert result == {"logged": True}
        assert ctx.state["artifact_events"] == [{"event": "discovered_optimum", "artifact_id": "artifact-abc123"}]
    finally:
        redis_client.delete("session:test_session_artifact_evidence:artifact_events")
