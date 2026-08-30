"""Publishes a structured MemoryEvent to Redis for every persisted memory
operation, so an external observer (the SMRITI Observatory) can watch
memory tiers change in real time without touching store.py/short_term.py's
own logic. Fire-and-forget: a Redis hiccup here must never break a real
memory write. One global channel/list, not per-session — some store.py
functions (get_dpm, put_dpm, get_teaching_memory, put_teaching_memory)
never receive a session_id at all, and a per-session scheme would silently
drop them.

Direct port of sub_modules_examples/tutor/app/memory/instrumentation.py —
same wire shape, same Redis keys — so smriti-observatory/backend's ingest
loop can decode events from either app identically. See
docs/superpowers/specs/2026-08-28-backend-memory-observatory-design.md.
"""
from __future__ import annotations

import asyncio
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
    arguments don't include one (only session_close.py calls this)."""
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


ToolActor = Literal["voice_agent", "board_agent", "artifact_agent", "quiz_agent", "textbook_agent"]
ToolCallPhase = Literal["started", "done", "error", "busy"]


class ToolCallEvent(BaseModel):
    kind: Literal["tool_call"] = "tool_call"
    event_id: str
    ts: str
    session_id: str | None
    student_id: str | None
    trace_id: str | None
    span_id: str | None
    actor: ToolActor
    tool_name: str
    phase: ToolCallPhase
    args_summary: str | None = None
    result_summary: str | None = None
    duration_ms: int | None = None


_sync_client: redis_sync.Redis | None = None


def _get_sync_client() -> redis_sync.Redis:
    global _sync_client
    if _sync_client is None:
        _sync_client = redis_sync.Redis(
            host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True,
            # Bounds the worst case: without this, a stalled Redis connection
            # blocks whichever thread/event-loop turn is publishing forever.
            # Both _publish_sync (MemoryEvent) and publish_tool_call_event
            # (ToolCallEvent) share this client, so both get hardened here.
            socket_timeout=2.0, socket_connect_timeout=2.0,
        )
    return _sync_client


def _truncate(text: str, max_len: int = 200) -> str:
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def build_tool_call_event(
    actor: ToolActor,
    tool_name: str,
    phase: ToolCallPhase,
    session_id: str | None,
    student_id: str | None,
    args_summary: str | None = None,
    result_summary: str | None = None,
    duration_ms: int | None = None,
) -> ToolCallEvent:
    trace_id, span_id = _current_trace_ids()
    return ToolCallEvent(
        event_id=str(uuid.uuid4()),
        ts=datetime.now(timezone.utc).isoformat(),
        session_id=session_id,
        student_id=student_id,
        trace_id=trace_id,
        span_id=span_id,
        actor=actor,
        tool_name=tool_name,
        phase=phase,
        args_summary=_truncate(args_summary) if args_summary else None,
        result_summary=_truncate(result_summary) if result_summary else None,
        duration_ms=duration_ms,
    )


def publish_tool_call_event(event: ToolCallEvent) -> None:
    """Fire-and-forget, same contract as _publish_sync: a Redis hiccup here
    must never break a real tool call.

    Sync, blocking form — kept for callers outside the event loop (and for
    tests). All three real call sites (main.py's trace(), specialist_runner's
    _log_tool_activity and delegate()) run on the event loop and use
    publish_tool_call_event_async instead, scheduled via
    asyncio.create_task so a slow Redis write never adds latency to the
    tool-call/turn logic itself — see that function's docstring.
    """
    try:
        client = _get_sync_client()
        body = event.model_dump_json()
        client.publish(_CHANNEL, body)
        client.rpush(_LIST_KEY, body)
        client.ltrim(_LIST_KEY, -_LIST_CAP, -1)
    except Exception:
        pass


_tool_call_publish_lock = asyncio.Lock()
"""Serializes publish_tool_call_event_async's actual Redis writes.

Without this, a "started" event and its later "done" event were each their
own independent asyncio.create_task(...), each opening its OWN fresh
connection — and whichever one happened to finish its connect+auth
handshake first won, regardless of which was scheduled first. Confirmed live
(not theoretical): a started/done pair reordered in smriti:events:recent
roughly 1 time in 3 against local Redis, and the frontend never sorts this
list by ts, so a reordering rendered as "done" before "started" and could
split one delegation across two apparent moments in the timeline — directly
undoing the trace-correlation work this event type exists for.

A single global lock (not per-session) is deliberate: asyncio.create_task
schedules a task's first step via the event loop's own FIFO-ordered
call_soon, so two publishes issued in application-code order acquire this
lock in that same order — the first task to run always wins the
uncontended acquire and starts its Redis I/O; the second blocks until the
first releases it. That is enough to guarantee real ordering, and tool-call
event volume (a handful of publishes per specialist call) is nowhere near
where one process-wide lock could become a bottleneck.
"""


async def publish_tool_call_event_async(event: ToolCallEvent) -> None:
    """Async mirror of publish_tool_call_event, same shape as
    _publish_async: constructs a fresh async client, publishes, closes it.

    This is what the three real call sites use — main.py's trace() (on the
    run_live stream), specialist_runner's _log_tool_activity (inside the
    per-specialist run_async loop) and delegate() (itself an async
    generator) — all run on the event loop, and a synchronous, unbounded
    Redis call there would stall the whole live audio session. Callers wrap
    this in asyncio.create_task(...) rather than awaiting it directly, so a
    slow publish never adds latency to the tool-call/turn logic itself —
    same fire-and-forget philosophy as _publish_async, just off the event
    loop's own thread instead of a background one.
    """
    async with _tool_call_publish_lock:
        client = None
        try:
            client = redis_async.Redis(
                host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True,
                socket_timeout=2.0, socket_connect_timeout=2.0,
            )
            body = event.model_dump_json()
            await client.publish(_CHANNEL, body)
            await client.rpush(_LIST_KEY, body)
            await client.ltrim(_LIST_KEY, -_LIST_CAP, -1)
        except Exception:
            pass
        finally:
            if client is not None:
                try:
                    await client.aclose()
                except Exception:
                    pass


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


def _payload_source(operation: Operation, args: tuple, result: Any) -> Any:
    """Write functions (put_dpm, put_teaching_memory, put_session_log,
    put_grounding_chunk, append_turn, append_artifact_event) all return
    None or an ack — the data actually written is the object passed in.
    By convention every one of these takes the connection/session id as
    args[0] and the written object/dict as args[1]. Reads use the return
    value as-is (including a legitimate None for "not found")."""
    if operation == "read":
        return result
    return args[1] if len(args) > 1 else result


def _build_event(
    tier: Tier, record_type: RecordType, operation: Operation, fn_name: str,
    session_id: str | None, student_id: str | None, payload_source: Any,
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
        payload=_to_jsonable(payload_source),
    )


def _publish_sync(event: MemoryEvent) -> None:
    try:
        client = _get_sync_client()
        body = event.model_dump_json()
        client.publish(_CHANNEL, body)
        client.rpush(_LIST_KEY, body)
        client.ltrim(_LIST_KEY, -_LIST_CAP, -1)
    except Exception:
        pass


async def _publish_async(event: MemoryEvent) -> None:
    try:
        client = redis_async.Redis(
            host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True,
            socket_timeout=2.0, socket_connect_timeout=2.0,
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
    """extract_ids(args, kwargs, result) -> (session_id, student_id)."""
    def decorator(fn):
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                result = await fn(*args, **kwargs)
                try:
                    session_id, student_id = extract_ids(args, kwargs, result)
                    event = _build_event(
                        tier, record_type, operation, fn.__name__, session_id, student_id,
                        _payload_source(operation, args, result),
                    )
                    await _publish_async(event)
                except Exception:
                    pass
                return result
            return async_wrapper
        else:
            @functools.wraps(fn)
            def sync_wrapper(*args, **kwargs):
                result = fn(*args, **kwargs)
                try:
                    session_id, student_id = extract_ids(args, kwargs, result)
                    event = _build_event(
                        tier, record_type, operation, fn.__name__, session_id, student_id,
                        _payload_source(operation, args, result),
                    )
                    _publish_sync(event)
                except Exception:
                    pass
                return result
            return sync_wrapper
    return decorator
