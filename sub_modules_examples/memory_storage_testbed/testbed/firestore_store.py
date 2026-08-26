from __future__ import annotations

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector

from testbed.schemas import Chunk, Profile, SessionLog


def connect(project: str, database: str) -> firestore.Client:
    return firestore.Client(project=project, database=database)


def put_chunk(db: firestore.Client, chunk: Chunk, embedding: list[float]) -> None:
    payload = chunk.model_dump(mode="json")
    payload["embedding"] = Vector(embedding)
    db.collection("grounding_chunks").document(chunk.chunk_id).set(payload)


def search_chunks(db: firestore.Client, concept_ids: list[str], limit: int = 5) -> list[Chunk]:
    if not concept_ids:
        return []
    docs = (
        db.collection("grounding_chunks")
        .where(filter=FieldFilter("concept_ids", "array_contains_any", concept_ids))
        .limit(limit)
        .get()
    )
    return [
        Chunk.model_validate({k: v for k, v in d.to_dict().items() if k != "embedding"})
        for d in docs
    ]


def search_chunks_semantic(
    db: firestore.Client,
    query_embedding: list[float],
    concept_ids: list[str] | None = None,
    limit: int = 5,
) -> list[Chunk]:
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
        Chunk.model_validate({k: v for k, v in d.to_dict().items() if k != "embedding"})
        for d in docs
    ]


def get_dpm(db: firestore.Client, student_id: str) -> Profile | None:
    doc = db.collection("dpm_profiles").document(student_id).get()
    return Profile.model_validate(doc.to_dict()) if doc.exists else None


def put_dpm(db: firestore.Client, profile: Profile) -> None:
    db.collection("dpm_profiles").document(profile.student_id).set(profile.model_dump(mode="json"))


def get_teaching_memory(db: firestore.Client, student_id: str) -> Profile | None:
    doc = db.collection("teaching_memories").document(student_id).get()
    return Profile.model_validate(doc.to_dict()) if doc.exists else None


def put_teaching_memory(db: firestore.Client, memory: Profile) -> None:
    db.collection("teaching_memories").document(memory.student_id).set(memory.model_dump(mode="json"))


def put_session_log(db: firestore.Client, log: SessionLog) -> None:
    db.collection("session_logs").document(log.session_id).set(log.model_dump(mode="json"))


def get_session_log(db: firestore.Client, session_id: str) -> SessionLog | None:
    doc = db.collection("session_logs").document(session_id).get()
    return SessionLog.model_validate(doc.to_dict()) if doc.exists else None
