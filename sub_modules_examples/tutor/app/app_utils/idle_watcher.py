"""Idle-timeout safety net for close_session — mirrors the same
safety-net-TTL philosophy already used for the Redis turn buffer
(app/memory/short_term.py's _SAFETY_TTL_SECONDS). A session that never gets
explicitly closed (Task 6's endpoint) still gets reflected into long-term
memory once its heartbeat key (app/memory/short_term.py:refresh_heartbeat)
expires. See docs/superpowers/specs/2026-08-27-smriti-observatory-design.md
§6.2.

Managed Memorystore may restrict runtime CONFIG SET — if so, configure
notify-keyspace-events via the instance's parameter group instead; this
module's own CONFIG SET call is a no-op-if-already-set convenience for
local dev, not a hard dependency of the watch loop itself.
"""
from __future__ import annotations

import logging
import time

import redis.asyncio as redis

from app import config
from app.app_utils.memory_routes import perform_close_session

logger = logging.getLogger(__name__)


async def run_one_expiry_cycle(pubsub: redis.client.PubSub, timeout: float | None = 5.0) -> str | None:
    """Waits up to `timeout` seconds (total) for one expiry notification.

    redis-py's get_message() reads exactly one raw frame per call. Right
    after psubscribe(), the first frame on the wire is always the PSUBSCRIBE
    confirmation itself; with ignore_subscribe_messages=True that frame is
    suppressed and the call returns None immediately — it does *not* keep
    reading within the same call to find a real message, even though
    `timeout` budget remains. A single get_message() call (as a naive
    implementation might do) would therefore spuriously return None on the
    very first invocation after subscribing, regardless of whether a real
    expiry notification was waiting right behind it on the socket. This
    loops past those protocol-level confirmations, spending only the
    remaining timeout budget on each subsequent read, so the result reflects
    the first real message (or true timeout) rather than a subscribe ack.

    Returns the session id it closed, or None if the message wasn't a
    session heartbeat key (or nothing arrived in time)."""
    deadline = None if timeout is None else time.monotonic() + timeout
    while True:
        remaining = timeout if deadline is None else max(0.0, deadline - time.monotonic())
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=remaining)
        if message is None:
            if deadline is not None and time.monotonic() >= deadline:
                return None
            continue
        if message.get("type") != "pmessage":
            continue
        key = message["data"]
        if not (key.startswith("session:") and key.endswith(":heartbeat")):
            return None
        session_id = key.split(":")[1]
        try:
            await perform_close_session(session_id)
        except Exception:
            logger.exception("idle-timeout close_session failed for session_id=%s", session_id)
            return None
        return session_id


async def watch_idle_sessions() -> None:
    client = redis.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
    try:
        await client.config_set("notify-keyspace-events", "Ex")
    except Exception:
        logger.warning("could not set notify-keyspace-events at runtime; configure it on the Redis instance directly")
    pubsub = client.pubsub()
    await pubsub.psubscribe("__keyevent@0__:expired")
    try:
        while True:
            await run_one_expiry_cycle(pubsub, timeout=None)
    finally:
        await pubsub.aclose()
        await client.aclose()
