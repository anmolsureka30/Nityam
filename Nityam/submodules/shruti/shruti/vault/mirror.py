"""DuckDB local analytics mirror.

Per shruti_architecture.md §5.4: "the one thing `sense` got completely
right: CREATE VIEW v_timeline with formatted timecodes makes debugging a
pipeline enormously faster." This was specified but never built — this
module builds it.

No ETL: DuckDB's postgres scanner extension ATTACHes the live Postgres
database directly, so `v_timeline` always reflects current data with zero
sync/copy code to maintain or go stale.
"""
import os

import duckdb

_DEFAULT_DUCKDB_PATH = ".local/shruti.duckdb"


def connect(duckdb_path: str = _DEFAULT_DUCKDB_PATH, pg_dsn: str | None = None) -> duckdb.DuckDBPyConnection:
    pg_dsn = pg_dsn or _dsn_from_database_url(os.environ.get(
        "DATABASE_URL", "postgresql://shruti:shruti@localhost:5434/shruti"
    ))
    con = duckdb.connect(duckdb_path)
    con.execute("INSTALL postgres; LOAD postgres;")
    already_attached = con.execute(
        "SELECT count(*) FROM duckdb_databases() WHERE database_name = 'pg'"
    ).fetchone()[0]
    if not already_attached:
        con.execute(f"ATTACH '{pg_dsn}' AS pg (TYPE postgres)")
    _create_views(con)
    return con


def _dsn_from_database_url(url: str) -> str:
    """postgresql://user:pass@host:port/db -> libpq keyword/value DSN."""
    rest = url.split("://", 1)[1]
    creds, hostpart = rest.split("@", 1)
    user, password = creds.split(":", 1)
    hostport, dbname = hostpart.split("/", 1)
    host, port = hostport.split(":", 1)
    return f"dbname={dbname} user={user} password={password} host={host} port={port}"


_V_TIMELINE = """
CREATE OR REPLACE VIEW v_timeline AS
SELECT
    b.recording_id,
    b.idx,
    printf('%02d:%05.2f', CAST(FLOOR(b.start_s / 60) AS INT), b.start_s % 60) AS tc,
    b.kind,
    (CASE WHEN bs.id IS NOT NULL THEN '[board]' ELSE '       ' END ||
     CASE WHEN EXISTS (
         SELECT 1 FROM pg.public.deixis d
         WHERE d.recording_id = b.recording_id AND d.at_s BETWEEN b.start_s AND b.end_s
     ) THEN ' [gesture]' ELSE '' END) AS signals,
    substr(b.transcript, 1, 70) AS said,
    (SELECT string_agg(c.canonical_name, ', ')
       FROM pg.public.beat_ref r JOIN pg.public.concept c ON c.id = r.subject_id
      WHERE r.beat_id = b.id AND r.subject_kind = 'concept') AS concepts
FROM pg.public.beat b LEFT JOIN pg.public.board_state bs ON bs.id = b.board_state_id
ORDER BY b.recording_id, b.start_s;
"""

_V_BOARD_STATES = """
CREATE OR REPLACE VIEW v_board_states AS
SELECT
    bs.recording_id, bs.idx,
    printf('%02d:%05.2f', CAST(FLOOR(bs.valid_from_s / 60) AS INT), bs.valid_from_s % 60) AS from_tc,
    printf('%02d:%05.2f', CAST(FLOOR(bs.valid_to_s / 60) AS INT), bs.valid_to_s % 60) AS to_tc,
    bs.ended_by, bs.ink_coverage, bs.composited_uri,
    (SELECT count(*) FROM pg.public.board_region r WHERE r.board_state_id = bs.id) AS region_count,
    (SELECT count(*) FROM pg.public.board_region r
      WHERE r.board_state_id = bs.id AND r.kind = 'unreadable') AS unreadable_count
FROM pg.public.board_state bs
ORDER BY bs.recording_id, bs.idx;
"""

_V_CONCEPTS = """
CREATE OR REPLACE VIEW v_concepts AS
SELECT
    c.id, c.canonical_name, c.subject, c.grade, c.chapter,
    (SELECT min(bt.start_s) FROM pg.public.beat_ref r
       JOIN pg.public.beat bt ON bt.id = r.beat_id
      WHERE r.subject_kind = 'concept' AND r.subject_id = c.id) AS first_taught_at_s,
    (SELECT count(*) FROM pg.public.misconception m WHERE m.concept_id = c.id) AS misconception_count
FROM pg.public.concept c
ORDER BY first_taught_at_s;
"""


def _create_views(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(_V_TIMELINE)
    con.execute(_V_BOARD_STATES)
    con.execute(_V_CONCEPTS)
