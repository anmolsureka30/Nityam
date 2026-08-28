"""Write-through mirror of the workflow tier's turn buffer into Redis
(Memorystore in deployment). Deliberately NOT a swap of ADK's own
SessionService — brain._record/log_artifact_evidence keep writing to
tool_context.state first (free, in-process, unchanged), and additionally
write through here so the buffer survives outside one process's memory.
Keys are namespaced `session:{student_id}:{session_id}:*`, so a session_id on
its own — the client picks it, and nothing validates it against the connecting
user — is never enough to read or clear another student's buffer.
See project_documentation/memory_nityam_architecture/google_cloud_storage_integration.md
§5.2 for why this is a mirror, not a session-service swap.
"""
from __future__ import annotations

import json

import redis.asyncio as redis

from app import config
from app.memory import instrumentation

_SAFETY_TTL_SECONDS = 60 * 60 * 6  # 6h - close_session should flush well before this
_HEARTBEAT_TTL_SECONDS = 60
"""Not student-namespaced (session:{id}:heartbeat, no data payload -- just a
liveness flag) -- matches the exact key shape
smriti-observatory/backend's routes_rest.py checks (`client.exists(...)`)
to report a session's status as "live" for the Observatory frontend's
auto-select. A short TTL, refreshed on every real turn, reflects "a
conversation is happening right now" more accurately than a long
idle-timeout window would -- unlike sub_modules_examples/tutor, backend/
already knows exactly when a session ends (a real WebSocket disconnect
triggers close_session directly), so this key exists purely for
observability, not for backend/'s own session lifecycle."""


def _client(host: str | None = None, port: int | None = None) -> redis.Redis:
    return redis.Redis(
        host=host or config.REDIS_HOST,
        port=port or config.REDIS_PORT,
        decode_responses=True,
    )


async def _refresh_heartbeat(client: redis.Redis, session_id: str) -> None:
    await client.set(f"session:{session_id}:heartbeat", "1", ex=_HEARTBEAT_TTL_SECONDS)


def _ids_from_args01(args, kwargs, result):
    session_id = kwargs.get("session_id", args[0] if len(args) > 0 else None)
    student_id = kwargs.get("student_id", args[1] if len(args) > 1 else None)
    return session_id, student_id


@instrumentation.emit_memory_event(
    tier="workflow", record_type="turn_buffer", operation="write", extract_ids=_ids_from_args01,
)
async def append_turn(session_id: str, student_id: str, turn: dict) -> None:
    client = _client()
    key = f"session:{student_id}:{session_id}:turns"
    await client.rpush(key, json.dumps(turn))
    await client.expire(key, _SAFETY_TTL_SECONDS)
    await _refresh_heartbeat(client, session_id)
    await client.aclose()


@instrumentation.emit_memory_event(
    tier="workflow", record_type="artifact_event", operation="write", extract_ids=_ids_from_args01,
)
async def append_artifact_event(session_id: str, student_id: str, event: dict) -> None:
    client = _client()
    key = f"session:{student_id}:{session_id}:artifact_events"
    await client.rpush(key, json.dumps(event))
    await client.expire(key, _SAFETY_TTL_SECONDS)
    await _refresh_heartbeat(client, session_id)
    await client.aclose()


@instrumentation.emit_memory_event(
    tier="workflow", record_type="turn_buffer", operation="read", extract_ids=_ids_from_args01,
)
async def get_turn_buffer(session_id: str, student_id: str) -> list[dict]:
    client = _client()
    raw = await client.lrange(f"session:{student_id}:{session_id}:turns", 0, -1)
    await client.aclose()
    return [json.loads(r) for r in raw]


@instrumentation.emit_memory_event(
    tier="workflow", record_type="turn_buffer", operation="write", extract_ids=_ids_from_args01,
)
async def clear_session(session_id: str, student_id: str) -> None:
    client = _client()
    await client.delete(
        f"session:{student_id}:{session_id}:turns",
        f"session:{student_id}:{session_id}:artifact_events",
        f"session:{session_id}:heartbeat",
    )
    await client.aclose()
