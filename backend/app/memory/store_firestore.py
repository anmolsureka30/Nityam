"""One shared Firestore backing store for the memory layer — the same tool
functions in app/memory/tools.py call these, so TutorAgent and ArtifactAgent
read through one physical store, not separate copies (memory_layer.md §3, §5).

Replaces the earlier SQLite implementation 1:1 by function name/shape — see
project_documentation/memory_nityam_architecture/google_cloud_storage_integration.md
§3.5 for the migration this was ported from.
"""
from __future__ import annotations

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector

from app import config
from app.memory.schemas import DPMProfile, GroundingChunk, SessionLog, TeachingMemory


def connect(project: str | None = None, database: str | None = None) -> firestore.Client:
    return firestore.Client(
        project=project or config.GCP_PROJECT,
        database=database or config.FIRESTORE_DATABASE,
    )


def put_grounding_chunk(
    db: firestore.Client, chunk: GroundingChunk, embedding: list[float] | None = None
) -> None:
    """`embedding` is optional: Shruti's own embedder currently emits 3072-dim
    vectors, over Firestore's 2048-dim vector-index cap (see
    google_cloud_storage_integration.md §3.3 — a companion, smaller-dimension
    embedding for this field is a still-open item). Concept-id search
    (search_grounding) works identically with or without it; semantic search
    (search_grounding_semantic) only returns a chunk once it has one."""
    payload = chunk.model_dump(mode="json")
    if embedding is not None:
        payload["embedding"] = Vector(embedding)
    db.collection("grounding_chunks").document(chunk.chunk_id).set(payload)


def search_grounding(db: firestore.Client, concept_ids: list[str], limit: int = 5) -> list[GroundingChunk]:
    if not concept_ids:
        return []
    docs = (
        db.collection("grounding_chunks")
        .where(filter=FieldFilter("concept_ids", "array_contains_any", concept_ids))
        .limit(limit)
        .get()
    )
    return [
        GroundingChunk.model_validate({k: v for k, v in d.to_dict().items() if k != "embedding"})
        for d in docs
    ]


def search_grounding_semantic(
    db: firestore.Client,
    query_embedding: list[float],
    concept_ids: list[str] | None = None,
    limit: int = 5,
) -> list[GroundingChunk]:
    """Vector-similarity variant — use when a query doesn't cleanly resolve to
    known concept_ids. Only returns chunks that were written with an
    embedding (see put_grounding_chunk)."""
    q = db.collection("grounding_chunks")
    if concept_ids:
        q = q.where(filter=FieldFilter("concept_ids", "array_contains_any", concept_ids))
    docs = q.find_nearest(
        vector_field="embedding",
        query_vector=Vector(query_embedding),
        distance_measure=DistanceMeasure.COSINE,
        limit=limit,
    ).get()
    return [
        GroundingChunk.model_validate({k: v for k, v in d.to_dict().items() if k != "embedding"})
        for d in docs
    ]


def get_dpm(db: firestore.Client, student_id: str) -> DPMProfile | None:
    doc = db.collection("dpm_profiles").document(student_id).get()
    return DPMProfile.model_validate(doc.to_dict()) if doc.exists else None


def put_dpm(db: firestore.Client, profile: DPMProfile) -> None:
    db.collection("dpm_profiles").document(profile.student_id).set(profile.model_dump(mode="json"))


def get_teaching_memory(db: firestore.Client, student_id: str) -> TeachingMemory | None:
    doc = db.collection("teaching_memories").document(student_id).get()
    return TeachingMemory.model_validate(doc.to_dict()) if doc.exists else None


def put_teaching_memory(db: firestore.Client, memory: TeachingMemory) -> None:
    db.collection("teaching_memories").document(memory.student_id).set(memory.model_dump(mode="json"))


def put_session_log(db: firestore.Client, log: SessionLog) -> None:
    db.collection("session_logs").document(log.session_id).set(log.model_dump(mode="json"))


def get_session_log(db: firestore.Client, session_id: str) -> SessionLog | None:
    doc = db.collection("session_logs").document(session_id).get()
    return SessionLog.model_validate(doc.to_dict()) if doc.exists else None
