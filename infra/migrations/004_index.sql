CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE embedding (
    id              TEXT PRIMARY KEY,
    kind            TEXT NOT NULL,
    ref_id          TEXT NOT NULL,
    recording_id    TEXT,
    vec             vector(3072) NOT NULL,
    text            TEXT NOT NULL
);
-- No ANN index (hnsw/ivfflat) yet: pgvector caps indexed columns at 2000
-- dimensions, but gemini-embedding-001 outputs 3072 — truncating the
-- embedding to fit an index would lose real information for no benefit at
-- hackathon scale (sequential scan over a few thousand rows is fast; see
-- shruti_platform_alignment.md's cost/scale notes). Revisit if the corpus
-- ever grows past a size where a full scan is measurably slow.
