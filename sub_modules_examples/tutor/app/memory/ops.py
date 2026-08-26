"""Validated operations applied to DPMProfile/TeachingMemory at session close.
Never a raw overwrite (memory_layer.md §4) — each function mutates one
specific field, in place, and returns the record for chaining.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.memory.schemas import CoveredConcept, DPMProfile, OpenDoubt, SelfReflection, TeachingMemory, Weakness


def append_self_reflection(profile: DPMProfile, note: str, evidence: list[str]) -> DPMProfile:
    profile.self_reflection.append(SelfReflection(note=note, evidence=evidence))
    return profile


def set_mastery(profile: DPMProfile, concept_id: str, mastery: str, strength: str, evidence: list[str]) -> DPMProfile:
    profile.weaknesses[concept_id] = Weakness(
        mastery=mastery, strength=strength, evidence=evidence,
        last_updated=datetime.now(timezone.utc),
    )
    return profile


def open_doubt(memory: TeachingMemory, concept_id: str, doubt: str, correct_understanding: str, evidence: list[str]) -> TeachingMemory:
    memory.open_doubts.append(OpenDoubt(
        concept_id=concept_id, doubt=doubt, correct_understanding=correct_understanding,
        status="active", evidence=evidence,
    ))
    return memory


def close_doubt(memory: TeachingMemory, concept_id: str) -> TeachingMemory:
    """Only call this after evidence of a SPACED re-check — never on one
    correct answer in the same session (memory_layer.md §2.3).

    Rebuilds each matching doubt via the OpenDoubt constructor rather than
    mutating `doubt.status` in place, for the same reason update_coverage
    does (pydantic v2 does not validate plain attribute assignment). The
    "resolved" literal here is always hardcoded, never LLM-supplied, so
    there's no live bug today — this is purely for consistency with that
    fix's rationale, so a later edit here doesn't quietly reopen it. Note
    `model_copy(update=...)` was considered but confirmed (live, this
    pydantic version) to also skip validation on the updated fields, so it
    would not actually provide that guarantee — the constructor is used
    instead.
    """
    memory.open_doubts = [
        OpenDoubt(**{**doubt.model_dump(), "status": "resolved"})
        if doubt.concept_id == concept_id and doubt.status != "resolved"
        else doubt
        for doubt in memory.open_doubts
    ]
    return memory


def update_coverage(memory: TeachingMemory, concept_id: str, elements_used: list[str], taught_at: str, status: str) -> TeachingMemory:
    """Builds the merged entry via the CoveredConcept constructor rather than
    mutating an existing entry's attributes in place. Pydantic v2 does not
    validate plain attribute assignment, so `entry.status = status` would let
    an out-of-enum status silently through instead of raising; constructing
    a fresh instance validates it and leaves the existing entry untouched if
    that validation fails."""
    existing = memory.covered.get(concept_id)
    merged_elements = sorted(set(existing.elements_used if existing else []) | set(elements_used))
    merged_taught_at = [*(existing.taught_at if existing else []), taught_at]
    memory.covered[concept_id] = CoveredConcept(
        elements_used=merged_elements, taught_at=merged_taught_at, status=status,
    )
    return memory
