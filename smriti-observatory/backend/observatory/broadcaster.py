"""In-process WebSocket fan-out registry. One queue per connected client;
publish() delivers to that client's session-scoped queue (if any) and to
every global-feed queue (subscribed with session_id=None)."""
from __future__ import annotations

import asyncio

from observatory.events import EnrichedEvent


class Broadcaster:
    def __init__(self) -> None:
        self._session_queues: dict[str, list[asyncio.Queue]] = {}
        self._global_queues: list[asyncio.Queue] = []

    def subscribe(self, session_id: str | None) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        if session_id is None:
            self._global_queues.append(queue)
        else:
            self._session_queues.setdefault(session_id, []).append(queue)
        return queue

    def unsubscribe(self, session_id: str | None, queue: asyncio.Queue) -> None:
        if session_id is None:
            if queue in self._global_queues:
                self._global_queues.remove(queue)
        elif session_id in self._session_queues and queue in self._session_queues[session_id]:
            self._session_queues[session_id].remove(queue)

    def publish(self, enriched: EnrichedEvent) -> None:
        session_id = enriched.event.session_id
        if session_id and session_id in self._session_queues:
            for queue in self._session_queues[session_id]:
                queue.put_nowait(enriched)
        for queue in self._global_queues:
            queue.put_nowait(enriched)
