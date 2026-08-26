"""Publishes a structured MemoryEvent to Redis for every persisted memory
operation, so an external observer (the SMRITI Observatory) can watch
memory tiers change in real time without touching store.py/short_term.py's
own logic. Fire-and-forget: a Redis hiccup here must never break a real
memory write. One global channel/list, not per-session — several store.py
functions (get_dpm, put_dpm, get_teaching_memory, put_teaching_memory)
never receive a session_id at all, and a per-session scheme would silently
drop them (see google_cloud_storage_integration.md-adjacent design note in
docs/superpowers/specs/2026-08-27-smriti-observatory-design.md §5).
"""
from __future__ import annotations

import contextvars
import functools
import inspect
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Literal

import redis as redis_sync
import redis.asyncio as redis_async
from opentelemetry import trace
from pydantic import BaseModel

from app import config

_CHANNEL = "smriti:events:live"
_LIST_KEY = "smriti:events:recent"
_LIST_CAP = 2000

Tier = Literal["workflow", "episodic", "long_term"]
Operation = Literal["read", "write"]
RecordType = Literal[
    "grounding_chunk", "dpm_profile", "teaching_memory",
    "session_log", "turn_buffer", "artifact_event",
]

_session_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "smriti_session_id", default=None
)


def set_session_context(session_id: str | None) -> None:
    """Set the session id long-term-tier writes should carry when their own
    arguments don't include one (only session_close.py calls this — see
    Task 4)."""
    _session_ctx.set(session_id)


def get_session_context() -> str | None:
    return _session_ctx.get()


class MemoryEvent(BaseModel):
    event_id: str
    ts: str
    session_id: str | None
    student_id: str | None
    tier: Tier
    operation: Operation
    record_type: RecordType
    source_fn: str
    trace_id: str | None
    span_id: str | None
    payload: Any = None


_sync_client: redis_sync.Redis | None = None


def _get_sync_client() -> redis_sync.Redis:
    global _sync_client
    if _sync_client is None:
        _sync_client = redis_sync.Redis(
            host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True
        )
    return _sync_client


def _current_trace_ids() -> tuple[str | None, str | None]:
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return None, None
    return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")


def _to_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    return value


def _build_event(
    tier: Tier, record_type: RecordType, operation: Operation, fn_name: str,
    session_id: str | None, student_id: str | None, result: Any,
) -> MemoryEvent:
    trace_id, span_id = _current_trace_ids()
    return MemoryEvent(
        event_id=str(uuid.uuid4()),
        ts=datetime.now(timezone.utc).isoformat(),
        session_id=session_id,
        student_id=student_id,
        tier=tier,
        operation=operation,
        record_type=record_type,
        source_fn=fn_name,
        trace_id=trace_id,
        span_id=span_id,
        payload=_to_jsonable(result),
    )


def _publish_sync(event: MemoryEvent) -> None:
    if not event.session_id and not event.student_id:
        return
    try:
        client = _get_sync_client()
        body = event.model_dump_json()
        client.publish(_CHANNEL, body)
        client.rpush(_LIST_KEY, body)
        client.ltrim(_LIST_KEY, -_LIST_CAP, -1)
    except Exception:
        pass


async def _publish_async(event: MemoryEvent) -> None:
    if not event.session_id and not event.student_id:
        return
    try:
        client = redis_async.Redis(
            host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True
        )
        body = event.model_dump_json()
        await client.publish(_CHANNEL, body)
        await client.rpush(_LIST_KEY, body)
        await client.ltrim(_LIST_KEY, -_LIST_CAP, -1)
        await client.aclose()
    except Exception:
        pass


def emit_memory_event(
    tier: Tier,
    record_type: RecordType,
    operation: Operation,
    extract_ids: Callable[[tuple, dict, Any], tuple[str | None, str | None]],
):
    """extract_ids(args, kwargs, result) -> (session_id, student_id).

    Sync-wrapped functions (store.py) publish via a plain blocking
    redis.Redis client; async-wrapped functions (short_term.py) publish
    with await on their own redis.asyncio client — this split means the
    decorator never has to create an event loop from inside a sync call
    path, and never blocks an async caller on a second client's setup.
    """
    def decorator(fn):
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                result = await fn(*args, **kwargs)
                session_id, student_id = extract_ids(args, kwargs, result)
                event = _build_event(
                    tier, record_type, operation, fn.__name__, session_id, student_id, result
                )
                await _publish_async(event)
                return result
            return async_wrapper
        else:
            @functools.wraps(fn)
            def sync_wrapper(*args, **kwargs):
                result = fn(*args, **kwargs)
                session_id, student_id = extract_ids(args, kwargs, result)
                event = _build_event(
                    tier, record_type, operation, fn.__name__, session_id, student_id, result
                )
                _publish_sync(event)
                return result
            return sync_wrapper
    return decorator
