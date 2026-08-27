from __future__ import annotations

import json

import redis.asyncio as redis

_SAFETY_TTL_SECONDS = 60 * 60 * 6  # 6h - close_session should flush well before this


def _client(host: str, port: int) -> redis.Redis:
    return redis.Redis(host=host, port=port, decode_responses=True)


async def append_turn(session_id: str, turn: dict, host: str, port: int) -> None:
    client = _client(host, port)
    key = f"session:{session_id}:turns"
    await client.rpush(key, json.dumps(turn))
    await client.expire(key, _SAFETY_TTL_SECONDS)
    await client.aclose()


async def get_turn_buffer(session_id: str, host: str, port: int) -> list[dict]:
    client = _client(host, port)
    raw = await client.lrange(f"session:{session_id}:turns", 0, -1)
    await client.aclose()
    return [json.loads(r) for r in raw]


async def clear_session(session_id: str, host: str, port: int) -> None:
    client = _client(host, port)
    await client.delete(f"session:{session_id}:turns")
    await client.aclose()
