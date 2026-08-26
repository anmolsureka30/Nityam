-- derives_from was a self-referencing FK (board_region.id), but GLYPH's
-- model naturally emits descriptive derivation labels (e.g.
-- "eq_range_basic") rather than copying a sibling region's literal id, and
-- can legitimately name more than one prior region a step derives from.
-- Confirmed by a real run: the FK constraint rejected valid multi-source
-- derivation output. Relaxing to a plain informational text field (comma
-- joined if GLYPH returns a list) rather than an enforced single reference.
ALTER TABLE board_region DROP CONSTRAINT IF EXISTS board_region_derives_from_fkey;
