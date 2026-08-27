"""One shared SQLite backing store for the memory layer — the same tool
functions in app/memory/tools.py call these, so TutorAgent and ArtifactAgent
read through one physical store, not separate copies (memory_layer.md §3, §5).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from app.memory.schemas import DPMProfile, GroundingChunk, SessionLog, TeachingMemory

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "memory.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS grounding_chunk (
    chunk_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS grounding_chunk_concept (
    concept_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL REFERENCES grounding_chunk(chunk_id),
    PRIMARY KEY (concept_id, chunk_id)
);
CREATE TABLE IF NOT EXISTS dpm_profile (
    student_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS teaching_memory (
    student_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS session_log (
    session_id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_session_log_student ON session_log(student_id);
"""


def connect(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def put_grounding_chunk(conn: sqlite3.Connection, chunk: GroundingChunk) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO grounding_chunk (chunk_id, payload) VALUES (?, ?)",
        (chunk.chunk_id, chunk.model_dump_json()),
    )
    conn.execute("DELETE FROM grounding_chunk_concept WHERE chunk_id = ?", (chunk.chunk_id,))
    conn.executemany(
        "INSERT INTO grounding_chunk_concept (concept_id, chunk_id) VALUES (?, ?)",
        [(cid, chunk.chunk_id) for cid in chunk.concept_ids],
    )
    conn.commit()


def search_grounding(conn: sqlite3.Connection, concept_ids: list[str], limit: int = 5) -> list[GroundingChunk]:
    if not concept_ids:
        return []
    placeholders = ",".join("?" * len(concept_ids))
    rows = conn.execute(
        f"""
        SELECT DISTINCT gc.payload FROM grounding_chunk gc
        JOIN grounding_chunk_concept gcc ON gcc.chunk_id = gc.chunk_id
        WHERE gcc.concept_id IN ({placeholders})
        LIMIT ?
        """,
        (*concept_ids, limit),
    ).fetchall()
    return [GroundingChunk.model_validate_json(r[0]) for r in rows]


def list_concept_ids(conn: sqlite3.Connection) -> list[str]:
    """Every concept the grounding index actually holds.

    Needed to turn a session plan's human topic name ("Maximum range") into
    real concept ids before the first turn, so the voice layer can be briefed on
    the topic without guessing an id that would return nothing.

    store.py already looks for this by getattr, so adding it here is all that is
    required for both backends to expose it.
    """
    rows = conn.execute(
        "SELECT DISTINCT concept_id FROM grounding_chunk_concept ORDER BY concept_id"
    ).fetchall()
    return [r[0] for r in rows]


def get_dpm(conn: sqlite3.Connection, student_id: str) -> DPMProfile | None:
    row = conn.execute(
        "SELECT payload FROM dpm_profile WHERE student_id = ?", (student_id,)
    ).fetchone()
    return DPMProfile.model_validate_json(row[0]) if row else None


def put_dpm(conn: sqlite3.Connection, profile: DPMProfile) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO dpm_profile (student_id, payload) VALUES (?, ?)",
        (profile.student_id, profile.model_dump_json()),
    )
    conn.commit()


def get_teaching_memory(conn: sqlite3.Connection, student_id: str) -> TeachingMemory | None:
    row = conn.execute(
        "SELECT payload FROM teaching_memory WHERE student_id = ?", (student_id,)
    ).fetchone()
    return TeachingMemory.model_validate_json(row[0]) if row else None


def put_teaching_memory(conn: sqlite3.Connection, memory: TeachingMemory) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO teaching_memory (student_id, payload) VALUES (?, ?)",
        (memory.student_id, memory.model_dump_json()),
    )
    conn.commit()


def put_session_log(conn: sqlite3.Connection, log: SessionLog) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO session_log (session_id, student_id, payload) VALUES (?, ?, ?)",
        (log.session_id, log.student_id, log.model_dump_json()),
    )
    conn.commit()


def get_session_log(conn: sqlite3.Connection, session_id: str) -> SessionLog | None:
    row = conn.execute(
        "SELECT payload FROM session_log WHERE session_id = ?", (session_id,)
    ).fetchone()
    return SessionLog.model_validate_json(row[0]) if row else None
