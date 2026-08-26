CREATE TABLE recording (
    id              TEXT PRIMARY KEY,
    source_uri      TEXT NOT NULL,
    title           TEXT,
    duration_s      REAL NOT NULL,
    fps             REAL NOT NULL,
    width           INT, height INT,
    surface_kind    TEXT NOT NULL,
    subject         TEXT, grade INT, chapter TEXT,
    ingested_at     TIMESTAMPTZ DEFAULT now(),
    reel_version    INT NOT NULL DEFAULT 1
);

CREATE TABLE utterance (
    id              TEXT PRIMARY KEY,
    recording_id    TEXT NOT NULL REFERENCES recording(id),
    start_s         REAL NOT NULL, end_s REAL NOT NULL,
    text            TEXT NOT NULL,
    speaker         TEXT NOT NULL,
    language_spans  JSONB,
    confidence      REAL
);
CREATE INDEX ON utterance (recording_id, start_s);

CREATE TABLE deixis (
    id              TEXT PRIMARY KEY,
    recording_id    TEXT NOT NULL REFERENCES recording(id),
    at_s            REAL NOT NULL,
    utterance_id    TEXT REFERENCES utterance(id),
    phrase          TEXT,
    board_region    JSONB NOT NULL,
    kind            TEXT,
    referent_text   TEXT,
    confidence      REAL
);

CREATE TABLE beat (
    id              TEXT PRIMARY KEY,
    recording_id    TEXT NOT NULL REFERENCES recording(id),
    idx             INT NOT NULL,
    start_s         REAL NOT NULL, end_s REAL NOT NULL,
    kind            TEXT NOT NULL,
    board_state_id  TEXT,
    board_delta     JSONB,
    salience        REAL,
    transcript      TEXT NOT NULL,
    UNIQUE (recording_id, idx)
);
CREATE INDEX ON beat (recording_id, start_s);
