import pytest

from testbed import redis_shortterm
from testbed.config import REDIS_HOST, REDIS_PORT


@pytest.mark.asyncio
async def test_turn_buffer_roundtrip(redis_client):
    session_id = "test_session_redis_1"
    await redis_shortterm.clear_session(session_id, REDIS_HOST, REDIS_PORT)

    await redis_shortterm.append_turn(
        session_id, {"turn": 1, "role": "student", "text": "hi"}, REDIS_HOST, REDIS_PORT
    )
    await redis_shortterm.append_turn(
        session_id, {"turn": 2, "role": "tutor", "text": "hello"}, REDIS_HOST, REDIS_PORT
    )

    buffer = await redis_shortterm.get_turn_buffer(session_id, REDIS_HOST, REDIS_PORT)
    assert len(buffer) == 2
    assert buffer[0]["text"] == "hi"
    assert buffer[1]["role"] == "tutor"

    await redis_shortterm.clear_session(session_id, REDIS_HOST, REDIS_PORT)
    assert await redis_shortterm.get_turn_buffer(session_id, REDIS_HOST, REDIS_PORT) == []
