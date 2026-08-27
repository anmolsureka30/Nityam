"""In-memory per-(student_id, record_type) last-seen state, so ingest.py can
diff a new long-term write against what came before it without an extra
Firestore round-trip on every event. Seeded lazily via `loader` on first
miss for a given key.
"""
from __future__ import annotations

from typing import Callable


class SnapshotCache:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], dict | None] = {}

    def get_and_set(
        self, student_id: str, record_type: str, new_value: dict,
        loader: Callable[[], dict | None],
    ) -> dict | None:
        key = (student_id, record_type)
        if key not in self._store:
            self._store[key] = loader()
        previous = self._store[key]
        self._store[key] = new_value
        return previous

    def set(self, student_id: str, record_type: str, value: dict | None) -> None:
        self._store[(student_id, record_type)] = value
