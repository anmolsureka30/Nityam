CREATE TABLE board_state (
    id              TEXT PRIMARY KEY,
    recording_id    TEXT NOT NULL REFERENCES recording(id),
    idx             INT NOT NULL,
    valid_from_s    REAL NOT NULL,
    valid_to_s      REAL NOT NULL,
    composited_uri  TEXT NOT NULL,
    unfilled_uri    TEXT,
    ink_coverage    REAL,
    homography      JSONB,
    ended_by        TEXT,
    ledger_version  INT NOT NULL DEFAULT 1
);
CREATE INDEX ON board_state (recording_id, valid_from_s, valid_to_s);

CREATE TABLE board_region (
    id              TEXT PRIMARY KEY,
    board_state_id  TEXT NOT NULL REFERENCES board_state(id),
    bbox            JSONB NOT NULL,
    kind            TEXT NOT NULL,
    latex           TEXT,
    plain_text      TEXT,
    description     TEXT,
    role            TEXT,
    step_index      INT,
    derives_from    TEXT REFERENCES board_region(id),
    confidence      REAL
);
