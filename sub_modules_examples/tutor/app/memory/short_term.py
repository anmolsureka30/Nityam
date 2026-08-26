"""Write-through mirror of the workflow tier's turn buffer into Redis
(Memorystore in deployment). Deliberately NOT a swap of ADK's own
SessionService — log_turn/log_artifact_evidence keep writing to
tool_context.state first (free, in-process, unchanged), and additionally
write through here so the buffer survives outside one process's memory.
See project_documentation/memory_nityam_architecture/google_cloud_storage_integration.md
§5.2 for why this is a mirror, not a session-service swap.

Every function below is instrumented (docs/superpowers/specs/2026-08-27-smriti-observatory-design.md
§5) — the decorator is a transparent pass-through, return values are unchanged.
"""
from __future__ import annotations

import json

import redis.asyncio as redis

from app import config
from app.memory import instrumentation

_SAFETY_TTL_SECONDS = 60 * 60 * 6  # 6h - close_session should flush well before this


def _client(host: str | None = None, port: int | None = None) -> redis.Redis:
    return redis.Redis(
        host=host or config.REDIS_HOST,
        port=port or config.REDIS_PORT,
        decode_responses=True,
    )


def _ids_from_session_id_arg(args, kwargs, result):
    session_id = kwargs.get("session_id", args[0] if len(args) > 0 else None)
    return session_id, None


@instrumentation.emit_memory_event(
    tier="workflow", record_type="turn_buffer", operation="write",
    extract_ids=_ids_from_session_id_arg,
)
async def append_turn(session_id: str, turn: dict) -> None:
    client = _client()
    key = f"session:{session_id}:turns"
    await client.rpush(key, json.dumps(turn))
    await client.expire(key, _SAFETY_TTL_SECONDS)
    await client.aclose()


@instrumentation.emit_memory_event(
    tier="workflow", record_type="artifact_event", operation="write",
    extract_ids=_ids_from_session_id_arg,
)
async def append_artifact_event(session_id: str, event: dict) -> None:
    client = _client()
    key = f"session:{session_id}:artifact_events"
    await client.rpush(key, json.dumps(event))
    await client.expire(key, _SAFETY_TTL_SECONDS)
    await client.aclose()


@instrumentation.emit_memory_event(
    tier="workflow", record_type="turn_buffer", operation="read",
    extract_ids=_ids_from_session_id_arg,
)
async def get_turn_buffer(session_id: str) -> list[dict]:
    client = _client()
    raw = await client.lrange(f"session:{session_id}:turns", 0, -1)
    await client.aclose()
    return [json.loads(r) for r in raw]


@instrumentation.emit_memory_event(
    tier="workflow", record_type="turn_buffer", operation="write",
    extract_ids=_ids_from_session_id_arg,
)
async def clear_session(session_id: str) -> None:
    client = _client()
    await client.delete(f"session:{session_id}:turns", f"session:{session_id}:artifact_events")
    await client.aclose()
