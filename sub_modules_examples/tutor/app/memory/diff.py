"""Schema-aware diffing for DPMProfile/TeachingMemory writes — walks the
four fields memory_layer.md §2.2-2.3 actually documents as evolving
(weaknesses.*.mastery/strength, self_reflection, covered.*.status,
open_doubts.*.status), not a generic recursive dict differ. Keeps the UI's
language schema-literate ("mastery: partial -> known") instead of
JSON-Pointer-literate.

Ported from the standalone SMRITI Observatory (smriti-observatory/backend/
observatory/diff.py) so the tutor app's own memory endpoints — the ones ADK
web now reads from directly — can compute diffs without depending on that
app.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.memory.instrumentation import MemoryEvent


class FieldChange(BaseModel):
    path: str
    kind: str  # "added" | "removed" | "changed"
    old: object = None
    new: object = None
    label: str


class EnrichedEvent(BaseModel):
    event: MemoryEvent
    diff: list[FieldChange] = []


def diff_dpm(old: dict | None, new: dict) -> list[FieldChange]:
    old = old or {}
    changes: list[FieldChange] = []
    old_weaknesses = old.get("weaknesses", {})
    for concept_id, weakness in new.get("weaknesses", {}).items():
        prev = old_weaknesses.get(concept_id)
        if prev is None:
            changes.append(FieldChange(
                path=f"weaknesses.{concept_id}", kind="added", new=weakness,
                label=f"new weakness tracked: {concept_id} ({weakness.get('mastery')})",
            ))
            continue
        for field in ("mastery", "strength"):
            if prev.get(field) != weakness.get(field):
                changes.append(FieldChange(
                    path=f"weaknesses.{concept_id}.{field}", kind="changed",
                    old=prev.get(field), new=weakness.get(field),
                    label=f"{concept_id}.{field}: {prev.get(field)} -> {weakness.get(field)}",
                ))

    old_notes = {n["note"] for n in old.get("self_reflection", [])}
    for note in new.get("self_reflection", []):
        if note["note"] not in old_notes:
            changes.append(FieldChange(
                path="self_reflection", kind="added", new=note["note"],
                label=f"new self-reflection: \"{note['note']}\"",
            ))
    return changes


def diff_teaching_memory(old: dict | None, new: dict) -> list[FieldChange]:
    old = old or {}
    changes: list[FieldChange] = []

    old_covered = old.get("covered", {})
    for concept_id, covered in new.get("covered", {}).items():
        prev = old_covered.get(concept_id)
        prev_status = prev.get("status") if prev else None
        if prev_status != covered.get("status"):
            changes.append(FieldChange(
                path=f"covered.{concept_id}.status", kind="changed" if prev else "added",
                old=prev_status, new=covered.get("status"),
                label=f"{concept_id} coverage: {prev_status or 'not started'} -> {covered.get('status')}",
            ))

    old_doubts = {d["concept_id"]: d for d in old.get("open_doubts", [])}
    for doubt in new.get("open_doubts", []):
        prev = old_doubts.get(doubt["concept_id"])
        prev_status = prev.get("status") if prev else None
        if prev_status != doubt.get("status"):
            changes.append(FieldChange(
                path=f"open_doubts.{doubt['concept_id']}.status", kind="changed" if prev else "added",
                old=prev_status, new=doubt.get("status"),
                label=f"doubt on {doubt['concept_id']}: {prev_status or 'new'} -> {doubt.get('status')}",
            ))
    return changes
