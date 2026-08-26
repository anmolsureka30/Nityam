import pytest
from shruti.contracts.recording import Recording, SurfaceKind
from shruti.vault.reel import write_recording


@pytest.mark.asyncio
async def test_write_recording_persists_slug(db_conn):
    rec = Recording(id="r_slug_1", slug="physics_projectile_2d_a1b2c3d4",
                     source_uri="gs://x/physics_projectile_2d.mp4",
                     duration_s=10.0, fps=30.0, surface_kind=SurfaceKind.BLACKBOARD)
    await write_recording(db_conn, rec)
    row = await db_conn.fetchrow("SELECT slug FROM recording WHERE id=$1", rec.id)
    assert row["slug"] == "physics_projectile_2d_a1b2c3d4"


@pytest.mark.asyncio
async def test_write_recording_allows_null_slug(db_conn):
    rec = Recording(id="r_slug_2", source_uri="gs://x/y.mp4",
                     duration_s=10.0, fps=30.0, surface_kind=SurfaceKind.BLACKBOARD)
    await write_recording(db_conn, rec)
    row = await db_conn.fetchrow("SELECT slug FROM recording WHERE id=$1", rec.id)
    assert row["slug"] is None
