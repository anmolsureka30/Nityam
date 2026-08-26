import pytest
from shruti.db import get_pool, apply_migrations


@pytest.mark.asyncio
async def test_migrations_create_all_tables():
    pool = await get_pool()
    await apply_migrations(pool)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
        )
        names = {r["table_name"] for r in rows}
        for expected in ("recording", "utterance", "deixis", "beat", "board_state",
                          "board_region", "concept", "concept_edge", "misconception",
                          "beat_ref", "human_override", "embedding"):
            assert expected in names
        ext = await conn.fetchval(
            "SELECT extname FROM pg_extension WHERE extname='vector'"
        )
        assert ext == "vector"
    await pool.close()
