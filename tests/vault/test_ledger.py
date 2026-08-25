import pytest
from shruti.contracts.recording import Recording, SurfaceKind
from shruti.contracts.board import BoardState
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
