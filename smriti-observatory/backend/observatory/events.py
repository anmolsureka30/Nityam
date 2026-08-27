"""Re-exports the tutor app's own MemoryEvent — the Observatory must never
decode a real memory-layer event with a schema that could drift from the
one that published it (see the pyproject.toml path dependency on `app`)."""
from __future__ import annotations

from app.memory.instrumentation import MemoryEvent
from pydantic import BaseModel


class FieldChange(BaseModel):
    path: str
    kind: str  # "added" | "removed" | "changed"
    old: object = None
    new: object = None
    label: str


class EnrichedEvent(BaseModel):
    event: MemoryEvent
    diff: list[FieldChange] = []


__all__ = ["MemoryEvent", "FieldChange", "EnrichedEvent"]
