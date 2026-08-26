from datetime import datetime, timezone

from app.memory import store
from app.memory.schemas import DPMProfile, GroundingChunk, SessionLog, TeachingMemory, Turn, Weakness


def test_put_and_search_grounding_chunk(firestore_db):
    chunk = GroundingChunk(
        chunk_id="horizontal_range_0340",
        source_type="lecture",
        source_ref="shruti:d_jnekwca6i_4c5411d0",
        location="3:40",
        concept_ids=["projectile.horizontal_range"],
        text="The total horizontal distance traveled by a projectile...",
    )
    try:
        store.put_grounding_chunk(firestore_db, chunk)
        results = store.search_grounding(firestore_db, ["projectile.horizontal_range"])
        assert len(results) == 1
        assert results[0].chunk_id == "horizontal_range_0340"
        assert results[0].text.startswith("The total horizontal distance")
    finally:
        firestore_db.collection("grounding_chunks").document("horizontal_range_0340").delete()


def test_search_grounding_returns_nothing_for_unknown_concept(firestore_db):
    assert store.search_grounding(firestore_db, ["nonexistent.concept"]) == []


def test_search_grounding_respects_limit(firestore_db):
    chunk_ids = [f"test_c{i}" for i in range(3)]
    try:
        for i, chunk_id in enumerate(chunk_ids):
            store.put_grounding_chunk(firestore_db, GroundingChunk(
                chunk_id=chunk_id, source_type="lecture", source_ref="shruti:x",
                concept_ids=["test.projectile.range"], text=f"chunk {i}",
            ))
        assert len(store.search_grounding(firestore_db, ["test.projectile.range"], limit=2)) == 2
    finally:
        for chunk_id in chunk_ids:
            firestore_db.collection("grounding_chunks").document(chunk_id).delete()


def test_dpm_round_trip(firestore_db):
    assert store.get_dpm(firestore_db, "test_demo_student") is None
    try:
        profile = DPMProfile(
            student_id="test_demo_student",
            weaknesses={"projectile.range": Weakness(mastery="partial", strength="weak", evidence=["s1#1"])},
        )
        store.put_dpm(firestore_db, profile)

        loaded = store.get_dpm(firestore_db, "test_demo_student")
        assert loaded is not None
        assert loaded.weaknesses["projectile.range"].mastery == "partial"
    finally:
        firestore_db.collection("dpm_profiles").document("test_demo_student").delete()


def test_dpm_put_overwrites_by_student_id(firestore_db):
    try:
        store.put_dpm(firestore_db, DPMProfile(student_id="test_demo_student"))
        store.put_dpm(firestore_db, DPMProfile(student_id="test_demo_student", weaknesses={
            "projectile.range": Weakness(mastery="known", strength="strong", evidence=["s2#1"])
        }))
        loaded = store.get_dpm(firestore_db, "test_demo_student")
        assert loaded.weaknesses["projectile.range"].mastery == "known"
    finally:
        firestore_db.collection("dpm_profiles").document("test_demo_student").delete()


def test_teaching_memory_round_trip(firestore_db):
    assert store.get_teaching_memory(firestore_db, "test_demo_student") is None
    try:
        memory = TeachingMemory(student_id="test_demo_student", syllabus=["projectile.range"])
        store.put_teaching_memory(firestore_db, memory)

        loaded = store.get_teaching_memory(firestore_db, "test_demo_student")
        assert loaded.syllabus == ["projectile.range"]
    finally:
        firestore_db.collection("teaching_memories").document("test_demo_student").delete()


def test_session_log_round_trip(firestore_db):
    try:
        log = SessionLog(
            session_id="test_s1",
            student_id="test_demo_student",
            started_at=datetime.now(timezone.utc),
            turns=[Turn(turn=1, role="student", text="hi")],
        )
        store.put_session_log(firestore_db, log)

        loaded = store.get_session_log(firestore_db, "test_s1")
        assert loaded is not None
        assert loaded.turns[0].text == "hi"
    finally:
        firestore_db.collection("session_logs").document("test_s1").delete()


def test_get_session_log_missing_returns_none(firestore_db):
    assert store.get_session_log(firestore_db, "test_nonexistent") is None


def test_semantic_search_ranks_similar_chunk_first(firestore_db):
    """Uses synthetic embeddings — real Shruti-embedding compatibility is a
    still-open item (google_cloud_storage_integration.md §3.3)."""
    import random

    def _dummy_embedding(seed: int, dim: int = 1536) -> list[float]:
        rng = random.Random(seed)
        return [rng.uniform(-1, 1) for _ in range(dim)]

    base = _dummy_embedding(seed=42)
    similar = [v + 0.001 for v in base]
    different = _dummy_embedding(seed=999)

    ids = ["test_sem_a", "test_sem_b", "test_sem_c"]
    try:
        store.put_grounding_chunk(
            firestore_db,
            GroundingChunk(chunk_id="test_sem_a", source_type="lecture", source_ref="shruti:x", concept_ids=["test.range"], text="A"),
            base,
        )
        store.put_grounding_chunk(
            firestore_db,
            GroundingChunk(chunk_id="test_sem_b", source_type="lecture", source_ref="shruti:x", concept_ids=["test.range"], text="B (near-duplicate)"),
            similar,
        )
        store.put_grounding_chunk(
            firestore_db,
            GroundingChunk(chunk_id="test_sem_c", source_type="lecture", source_ref="shruti:x", concept_ids=["test.range"], text="C (unrelated)"),
            different,
        )
        results = store.search_grounding_semantic(firestore_db, base, limit=2)
        result_ids = [c.chunk_id for c in results]
        assert "test_sem_a" in result_ids
        assert "test_sem_b" in result_ids
    finally:
        for chunk_id in ids:
            firestore_db.collection("grounding_chunks").document(chunk_id).delete()


from app.memory import instrumentation


def test_put_dpm_publishes_event_scoped_by_context(firestore_db, redis_client):
    redis_client.delete("smriti:events:recent")
    instrumentation.set_session_context("test_store_sess_1")
    try:
        store.put_dpm(firestore_db, DPMProfile(student_id="test_instr_student"))
        raw = redis_client.lrange("smriti:events:recent", -1, -1)
        event = instrumentation.MemoryEvent.model_validate_json(raw[0])
        assert event.tier == "long_term"
        assert event.record_type == "dpm_profile"
        assert event.operation == "write"
        assert event.session_id == "test_store_sess_1"
        assert event.student_id == "test_instr_student"
    finally:
        instrumentation.set_session_context(None)
        firestore_db.collection("dpm_profiles").document("test_instr_student").delete()


def test_get_dpm_publishes_read_event_with_student_id_no_session(firestore_db, redis_client):
    redis_client.delete("smriti:events:recent")
    store.get_dpm(firestore_db, "test_instr_student_missing")
    raw = redis_client.lrange("smriti:events:recent", -1, -1)
    event = instrumentation.MemoryEvent.model_validate_json(raw[0])
    assert event.tier == "long_term"
    assert event.record_type == "dpm_profile"
    assert event.operation == "read"
    assert event.student_id == "test_instr_student_missing"
    assert event.session_id is None  # no context set in this test -> no publish check needed, but call must not raise


def test_put_session_log_publishes_event_scoped_by_log(firestore_db, redis_client):
    redis_client.delete("smriti:events:recent")
    log = SessionLog(
        session_id="test_store_sess_2", student_id="test_instr_student_2",
        started_at=datetime.now(timezone.utc), ended_at=datetime.now(timezone.utc), turns=[],
    )
    try:
        store.put_session_log(firestore_db, log)
        raw = redis_client.lrange("smriti:events:recent", -1, -1)
        event = instrumentation.MemoryEvent.model_validate_json(raw[0])
        assert event.tier == "episodic"
        assert event.record_type == "session_log"
        assert event.session_id == "test_store_sess_2"
        assert event.student_id == "test_instr_student_2"
    finally:
        firestore_db.collection("session_logs").document("test_store_sess_2").delete()


def test_existing_store_behavior_unaffected_by_instrumentation(firestore_db):
    """Sanity check: decoration must not change return values. Full coverage
    already lives in the tests above this one in the file."""
    assert store.get_dpm(firestore_db, "test_instr_student_missing") is None
