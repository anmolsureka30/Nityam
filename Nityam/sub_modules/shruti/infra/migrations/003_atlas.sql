CREATE TABLE concept (
    id              TEXT PRIMARY KEY,
    canonical_name  TEXT NOT NULL,
    aliases         TEXT[],
    subject         TEXT, grade INT, chapter TEXT,
    definition      TEXT,
    atlas_version   INT NOT NULL DEFAULT 1,
    UNIQUE (canonical_name, subject, grade, atlas_version)
);

CREATE TABLE concept_edge (
    id              TEXT PRIMARY KEY,
    from_concept    TEXT NOT NULL REFERENCES concept(id),
    to_concept      TEXT NOT NULL REFERENCES concept(id),
    edge_type       TEXT NOT NULL,
    weight          REAL DEFAULT 1.0,
    atlas_version   INT NOT NULL DEFAULT 1
);
CREATE INDEX ON concept_edge (from_concept, edge_type);
CREATE INDEX ON concept_edge (to_concept, edge_type);

CREATE TABLE misconception (
    id                    TEXT PRIMARY KEY,
    concept_id            TEXT NOT NULL REFERENCES concept(id),
    statement             TEXT NOT NULL,
    teacher_phrasing      TEXT,
    correct_understanding TEXT NOT NULL,
    pre_empted_at_beat    TEXT NOT NULL REFERENCES beat(id),
    board_region_id       TEXT REFERENCES board_region(id),
    atlas_version         INT NOT NULL DEFAULT 1
);

CREATE TABLE beat_ref (
    id              BIGSERIAL PRIMARY KEY,
    subject_kind    TEXT NOT NULL,
    subject_id      TEXT NOT NULL,
    beat_id         TEXT NOT NULL REFERENCES beat(id),
    relation        TEXT NOT NULL,
    atlas_version   INT NOT NULL DEFAULT 1
);
CREATE INDEX ON beat_ref (subject_kind, subject_id);

CREATE TABLE human_override (
    id              TEXT PRIMARY KEY,
    target_table    TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    field           TEXT NOT NULL,
    value           JSONB NOT NULL,
    author          TEXT, note TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);
