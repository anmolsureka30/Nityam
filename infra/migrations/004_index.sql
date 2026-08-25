CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE embedding (
    id              TEXT PRIMARY KEY,
    kind            TEXT NOT NULL,
    ref_id          TEXT NOT NULL,
    recording_id    TEXT,
    vec             vector(2000) NOT NULL,
    text            TEXT NOT NULL
);
CREATE INDEX ON embedding USING ivfflat (vec vector_cosine_ops);
