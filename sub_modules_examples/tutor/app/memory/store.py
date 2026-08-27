"""One shared Firestore backing store for the memory layer — the same tool
functions in app/memory/tools.py call these, so TutorAgent and ArtifactAgent
read through one physical store, not separate copies (memory_layer.md §3, §5).

Replaces the earlier SQLite implementation 1:1 by function name/shape — see
project_documentation/memory_nityam_architecture/google_cloud_storage_integration.md
§3.5 for the migration this was ported from.

Every function below is instrumented (docs/superpowers/specs/2026-08-27-smriti-observatory-design.md
§5) — the decorator is a transparent pass-through, return values are unchanged.
"""
from __future__ import annotations

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector

from app import config
from app.memory import instrumentation
from app.memory.schemas import DPMProfile, GroundingChunk, SessionLog, TeachingMemory


def connect(project: str | None = None, database: str | None = None) -> firestore.Client:
    return firestore.Client(
        project=project or config.GCP_PROJECT,
        database=database or config.FIRESTORE_DATABASE,
    )


def _ids_none(args, kwargs, result):
    return None, None


def _ids_context_session_only(args, kwargs, result):
    """search_grounding/search_grounding_semantic have no student_id
    (grounding_chunk isn't per-student) but DO happen mid-session, called by
    tools.py with a live session's tool_context — which sets the context
    var before calling in (see app/memory/tools.py's search_grounding)."""
    return instrumentation.get_session_context(), None


def _ids_student_from_arg1(args, kwargs, result):
    student_id = kwargs.get("student_id", args[1] if len(args) > 1 else None)
    return instrumentation.get_session_context(), student_id


def _ids_from_profile(args, kwargs, result):
    profile = kwargs.get("profile", args[1] if len(args) > 1 else None)
    return instrumentation.get_session_context(), getattr(profile, "student_id", None)


def _ids_from_memory(args, kwargs, result):
    memory = kwargs.get("memory", args[1] if len(args) > 1 else None)
    return instrumentation.get_session_context(), getattr(memory, "student_id", None)


def _ids_from_log(args, kwargs, result):
    log = kwargs.get("log", args[1] if len(args) > 1 else None)
    return getattr(log, "session_id", None), getattr(log, "student_id", None)


def _ids_session_from_arg1(args, kwargs, result):
    session_id = kwargs.get("session_id", args[1] if len(args) > 1 else None)
    return session_id, None


@instrumentation.emit_memory_event(
    tier="long_term", record_type="grounding_chunk", operation="write", extract_ids=_ids_none,
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


@instrumentation.emit_memory_event(
    tier="long_term", record_type="grounding_chunk", operation="read", extract_ids=_ids_context_session_only,
)
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


@instrumentation.emit_memory_event(
    tier="long_term", record_type="grounding_chunk", operation="read", extract_ids=_ids_context_session_only,
)
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


@instrumentation.emit_memory_event(
    tier="long_term", record_type="dpm_profile", operation="read", extract_ids=_ids_student_from_arg1,
)
def get_dpm(db: firestore.Client, student_id: str) -> DPMProfile | None:
    doc = db.collection("dpm_profiles").document(student_id).get()
    return DPMProfile.model_validate(doc.to_dict()) if doc.exists else None


@instrumentation.emit_memory_event(
    tier="long_term", record_type="dpm_profile", operation="write", extract_ids=_ids_from_profile,
)
def put_dpm(db: firestore.Client, profile: DPMProfile) -> None:
    db.collection("dpm_profiles").document(profile.student_id).set(profile.model_dump(mode="json"))


@instrumentation.emit_memory_event(
    tier="long_term", record_type="teaching_memory", operation="read", extract_ids=_ids_student_from_arg1,
)
def get_teaching_memory(db: firestore.Client, student_id: str) -> TeachingMemory | None:
    doc = db.collection("teaching_memories").document(student_id).get()
    return TeachingMemory.model_validate(doc.to_dict()) if doc.exists else None


@instrumentation.emit_memory_event(
    tier="long_term", record_type="teaching_memory", operation="write", extract_ids=_ids_from_memory,
)
def put_teaching_memory(db: firestore.Client, memory: TeachingMemory) -> None:
    db.collection("teaching_memories").document(memory.student_id).set(memory.model_dump(mode="json"))


@instrumentation.emit_memory_event(
    tier="episodic", record_type="session_log", operation="write", extract_ids=_ids_from_log,
)
def put_session_log(db: firestore.Client, log: SessionLog) -> None:
    db.collection("session_logs").document(log.session_id).set(log.model_dump(mode="json"))


@instrumentation.emit_memory_event(
    tier="episodic", record_type="session_log", operation="read", extract_ids=_ids_session_from_arg1,
)
def get_session_log(db: firestore.Client, session_id: str) -> SessionLog | None:
    doc = db.collection("session_logs").document(session_id).get()
    return SessionLog.model_validate(doc.to_dict()) if doc.exists else None
