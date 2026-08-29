"""One shared Firestore backing store for the memory layer — the same tool
functions in app/memory/tools.py call these, so TutorAgent and ArtifactAgent
read through one physical store, not separate copies (memory_layer.md §3, §5).

Replaces the earlier SQLite implementation 1:1 by function name/shape — see
project_documentation/memory_nityam_architecture/google_cloud_storage_integration.md
§3.5 for the migration this was ported from.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector

from app import config
from app.memory.schemas import DPMProfile, GroundingChunk, SessionLog, TeachingMemory

log = logging.getLogger("nityam.store")

_STOPWORDS = {"of", "the", "a", "an", "in", "on", "for", "to", "and"}


def _tokenize(concept_id: str) -> set[str]:
    """'projectile.trajectory_equation_in_two-dimensional_motion' ->
    {trajectory, equation, two, dimensional, motion} (drops the fixed
    'projectile.' domain prefix, splits on non-alphanumeric, drops
    stopwords). Used for token-overlap fuzzy matching, not any indexed
    field — see search_grounding's fallback."""
    body = concept_id.split(".", 1)[-1]
    tokens = {t for t in re.split(r"[^a-z0-9]+", body.lower()) if t}
    return tokens - _STOPWORDS


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


def list_concept_ids(db: firestore.Client) -> list[str]:
    """Every distinct concept_id actually present in the corpus. Fetches all
    chunks and unions their concept_ids in Python - fine at this corpus's
    scale (dozens of chunks); a real-scale corpus should back this with a
    dedicated metadata collection updated at ingestion time instead of a
    full-corpus scan on every call."""
    concept_ids: set[str] = set()
    for doc in db.collection("grounding_chunks").stream():
        concept_ids.update(doc.to_dict().get("concept_ids", []))
    return sorted(concept_ids)


def _exact_match(db: firestore.Client, concept_ids: list[str], limit: int) -> list[GroundingChunk]:
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


def search_grounding(db: firestore.Client, concept_ids: list[str], limit: int = 5) -> list[GroundingChunk]:
    """Concept ids come from an LLM tool call, not a fixed enum - the
    corpus's real ids come from Shruti's own ingestion naming
    ("trajectory_equation_in_two-dimensional_motion"), not phrasing a tutor
    would naturally invent from conversation context. Confirmed live
    against a real multi-persona eval (memory_layer_eval_report.md §2.1):
    roughly two-thirds of real search_grounding calls returned nothing
    because the guessed id didn't exactly match, even for concepts that
    genuinely exist in the corpus. The primary fix is proactive -
    app/memory/tools.py's list_concepts() lets the model see the real
    vocabulary before guessing. This is the reactive safety net for
    whenever it still doesn't: on an empty exact match, fuzzy-match each
    queried id against the real vocabulary by token overlap (handles
    reordering - "equation_of_trajectory" vs
    "trajectory_equation_in_two-dimensional_motion" - which plain
    substring/edit-distance matching handles poorly), and retry with
    whatever real ids clear the threshold."""
    if not concept_ids:
        return []
    exact = _exact_match(db, concept_ids, limit)
    if exact:
        return exact

    vocabulary = list_concept_ids(db)
    if not vocabulary:
        return []
    vocab_tokens = {cid: _tokenize(cid) for cid in vocabulary}
    matched: list[str] = []
    for guess in concept_ids:
        guess_tokens = _tokenize(guess)
        if not guess_tokens:
            continue
        best_cid, best_score = None, 0.0
        for cid, tokens in vocab_tokens.items():
            if not tokens:
                continue
            overlap = len(guess_tokens & tokens)
            score = overlap / len(guess_tokens | tokens)  # Jaccard similarity
            if score > best_score:
                best_cid, best_score = cid, score
        # >=1/3 token overlap is deliberately lenient - the guesses observed
        # in the reference eval run are often only partially related to the
        # real id (e.g. "staircase_problem" vs "staircase_projectile_problem")
        if best_cid and best_score >= 1 / 3:
            matched.append(best_cid)
    if not matched:
        return []
    return _exact_match(db, matched, limit)


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


def latest_session_log(db: firestore.Client, student_id: str, with_summary: bool = False) -> SessionLog | None:
    """The student's most recently ENDED session, for the continuity line.

    Session logs have been written since the memory layer existed and never
    read back — the tutor knew a student's distilled mastery but not that they
    had stopped halfway through a derivation last time, which is most of what
    "last time we…" is made of.

    Ordered by ended_at rather than started_at: a session that ran long is the
    later one regardless of when it opened.
    """
    # NO order_by. Filtering on student_id and ordering by ended_at is a
    # composite index in Firestore, and an uncreated one is a hard
    # FAILED_PRECONDITION with a console link — a manual setup step standing
    # between a fresh project and a working continuity line. One student has
    # tens of sessions, not thousands, so the sort is free in Python and the
    # single-field index this needs is created automatically.
    try:
        logs = [
            SessionLog.model_validate(doc.to_dict())
            for doc in db.collection("session_logs")
            .where(filter=FieldFilter("student_id", "==", student_id))
            .stream()
        ]
    except Exception:  # noqa: BLE001 - never block a lesson on continuity
        log.warning("could not read this student's session logs", exc_info=True)
        return None
    if with_summary:
        logs = [entry for entry in logs if (entry.summary or "").strip()]
    if not logs:
        return None
    # ended_at is optional on the schema; a log without one sorts oldest
    # rather than crashing the comparison.
    return max(logs, key=lambda entry: entry.ended_at or datetime.min.replace(
        tzinfo=timezone.utc))


def get_session_log(db: firestore.Client, session_id: str) -> SessionLog | None:
    doc = db.collection("session_logs").document(session_id).get()
    return SessionLog.model_validate(doc.to_dict()) if doc.exists else None
