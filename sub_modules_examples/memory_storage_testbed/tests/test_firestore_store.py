import random

from testbed import firestore_store
from testbed.schemas import Chunk, Profile, SessionLog, Turn


def _dummy_embedding(seed: int, dim: int = 1536) -> list[float]:
    rng = random.Random(seed)
    return [rng.uniform(-1, 1) for _ in range(dim)]


def test_chunk_roundtrip(firestore_db):
    chunk = Chunk(
        chunk_id="test_chunk_1",
        concept_ids=["kinematics.projectile"],
        text="Range = u^2 sin(2 theta) / g",
    )
    try:
        firestore_store.put_chunk(firestore_db, chunk, _dummy_embedding(seed=1))
        results = firestore_store.search_chunks(firestore_db, ["kinematics.projectile"])
        assert any(c.chunk_id == "test_chunk_1" for c in results)
    finally:
        firestore_db.collection("grounding_chunks").document("test_chunk_1").delete()


def test_dpm_roundtrip(firestore_db):
    profile = Profile(student_id="test_student_1", note="prefers worked examples")
    try:
        firestore_store.put_dpm(firestore_db, profile)
        fetched = firestore_store.get_dpm(firestore_db, "test_student_1")
        assert fetched is not None
        assert fetched.note == "prefers worked examples"
    finally:
        firestore_db.collection("dpm_profiles").document("test_student_1").delete()


def test_teaching_memory_roundtrip(firestore_db):
    memory = Profile(student_id="test_student_1", note="covered projectile motion")
    try:
        firestore_store.put_teaching_memory(firestore_db, memory)
        fetched = firestore_store.get_teaching_memory(firestore_db, "test_student_1")
        assert fetched is not None
        assert fetched.note == "covered projectile motion"
    finally:
        firestore_db.collection("teaching_memories").document("test_student_1").delete()


def test_session_log_roundtrip(firestore_db):
    log = SessionLog(
        session_id="test_session_1",
        student_id="test_student_1",
        turns=[Turn(turn=1, role="student", text="What is range?")],
    )
    try:
        firestore_store.put_session_log(firestore_db, log)
        fetched = firestore_store.get_session_log(firestore_db, "test_session_1")
        assert fetched is not None
        assert fetched.turns[0].text == "What is range?"
    finally:
        firestore_db.collection("session_logs").document("test_session_1").delete()


def test_semantic_search_finds_similar(firestore_db):
    base = _dummy_embedding(seed=42)
    similar = [v + 0.001 for v in base]
    different = _dummy_embedding(seed=999)

    chunk_a = Chunk(chunk_id="test_sem_a", concept_ids=["kinematics.range"], text="chunk A")
    chunk_b = Chunk(chunk_id="test_sem_b", concept_ids=["kinematics.range"], text="chunk B (near-duplicate of A)")
    chunk_c = Chunk(chunk_id="test_sem_c", concept_ids=["kinematics.range"], text="chunk C (unrelated)")

    firestore_store.put_chunk(firestore_db, chunk_a, base)
    firestore_store.put_chunk(firestore_db, chunk_b, similar)
    firestore_store.put_chunk(firestore_db, chunk_c, different)

    try:
        results = firestore_store.search_chunks_semantic(firestore_db, base, limit=2)
        result_ids = [c.chunk_id for c in results]
        assert "test_sem_a" in result_ids
        assert "test_sem_b" in result_ids
    finally:
        for cid in ["test_sem_a", "test_sem_b", "test_sem_c"]:
            firestore_db.collection("grounding_chunks").document(cid).delete()
