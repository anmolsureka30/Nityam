import pytest
from shruti.contracts.recording import Recording, SurfaceKind
from shruti.contracts.board import BoardState, BoardContent, Region
from shruti.vault.reel import write_recording
from shruti.vault.ledger import write_board_state, board_state_at


@pytest.mark.asyncio
async def test_board_state_at_returns_state_valid_at_time(db_conn):
    rec = Recording(id="r_test_2", source_uri="gs://x", duration_s=60.0, fps=30.0,
                     surface_kind=SurfaceKind.BLACKBOARD)
    await write_recording(db_conn, rec)
    bs = BoardState(id="bs_test_1", recording_id=rec.id, idx=0, valid_from_s=0.0,
                     valid_to_s=20.0, composited_uri="gs://x/bs1.png", ended_by="erase")
    await write_board_state(db_conn, bs)
    found = await board_state_at(db_conn, rec.id, t=10.0)
    assert found is not None
    assert found.id == "bs_test_1"
    assert await board_state_at(db_conn, rec.id, t=25.0) is None


@pytest.mark.asyncio
async def test_write_board_state_accepts_a_region_derived_from_multiple_priors(db_conn):
    """Regression guard: derives_from used to be an enforced single-string FK
    (board_region.id), but GLYPH's model can legitimately name several prior
    derivation steps, and doesn't always copy a sibling region's literal id.
    Migration 006 relaxed the FK; this confirms a list writes cleanly."""
    rec = Recording(id="r_test_derives", source_uri="gs://x", duration_s=60.0, fps=30.0,
                     surface_kind=SurfaceKind.SLIDES)
    await write_recording(db_conn, rec)
    content = BoardContent(regions=[
        Region(id="r1", bbox=(0.0, 0.0, 0.1, 0.1), kind="equation", latex="a"),
        Region(id="r2", bbox=(0.1, 0.0, 0.1, 0.1), kind="equation", latex="b"),
        Region(id="r3", bbox=(0.2, 0.0, 0.1, 0.1), kind="equation", latex="a+b",
               derives_from=["eq_a_label", "eq_b_label"]),
    ])
    bs = BoardState(id="bs_test_derives", recording_id=rec.id, idx=0, valid_from_s=0.0,
                     valid_to_s=20.0, composited_uri="gs://x/bs.png", ended_by="shot_cut",
                     content=content)
    await write_board_state(db_conn, bs)  # must not raise
    row = await db_conn.fetchrow(
        "SELECT derives_from FROM board_region WHERE id='bs_test_derives::r3'"
    )
    assert row["derives_from"] == "eq_a_label, eq_b_label"


@pytest.mark.asyncio
async def test_write_board_state_namespaces_region_ids_to_avoid_cross_slide_collisions(db_conn):
    """Regression guard: GLYPH names region.id independently per slide (e.g.
    "r1"), so two different board states in the same recording can both
    produce a region called "r1". board_region.id is a global PRIMARY KEY, so
    without namespacing, the second slide's "r1" silently vanished under
    ON CONFLICT DO NOTHING — confirmed with real pipeline output where a
    later slide's regions were dropped because an earlier slide had already
    claimed the same short id."""
    rec = Recording(id="r_test_collide", source_uri="gs://x", duration_s=60.0, fps=30.0,
                     surface_kind=SurfaceKind.SLIDES)
    await write_recording(db_conn, rec)
    for idx in (0, 1):
        bs = BoardState(
            id=f"bs_collide_{idx}", recording_id=rec.id, idx=idx,
            valid_from_s=float(idx * 10), valid_to_s=float(idx * 10 + 10),
            composited_uri=f"gs://x/bs{idx}.png", ended_by="shot_cut",
            content=BoardContent(regions=[
                Region(id="r1", bbox=(0.0, 0.0, 0.1, 0.1), kind="text",
                       plain_text=f"slide {idx} title"),
            ]),
        )
        await write_board_state(db_conn, bs)
    rows = await db_conn.fetch(
        "SELECT board_state_id, plain_text FROM board_region "
        "WHERE board_state_id IN ('bs_collide_0', 'bs_collide_1') ORDER BY board_state_id"
    )
    assert [r["plain_text"] for r in rows] == ["slide 0 title", "slide 1 title"]
