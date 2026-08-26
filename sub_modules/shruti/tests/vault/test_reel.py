import pytest
from shruti.contracts.recording import Recording, SurfaceKind
from shruti.contracts.beat import Beat
from shruti.vault.reel import write_recording, write_beats, get_beats


@pytest.mark.asyncio
async def test_write_and_read_recording_and_beats(db_conn):
    rec = Recording(id="r_test_1", source_uri="gs://x", duration_s=60.0, fps=30.0,
                     surface_kind=SurfaceKind.BLACKBOARD)
    await write_recording(db_conn, rec)
    beat = Beat(id="b_test_1", recording_id=rec.id, idx=0, start_s=0.0, end_s=5.0,
                kind="explain", transcript="hello")
    await write_beats(db_conn, [beat])
    beats = await get_beats(db_conn, rec.id)
    assert len(beats) == 1
    assert beats[0].transcript == "hello"
