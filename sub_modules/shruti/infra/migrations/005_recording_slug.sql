-- IF NOT EXISTS guards are required, not optional style: apply_migrations()
-- (shruti/db.py) only catches DuplicateTableError, and every db_conn test
-- fixture invocation re-runs every migration file against a persistent
-- (not per-test) database — so an unguarded ALTER here would raise
-- DuplicateColumnError and break every subsequent test in the session.
ALTER TABLE recording ADD COLUMN IF NOT EXISTS slug TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS recording_slug_idx ON recording (slug) WHERE slug IS NOT NULL;
