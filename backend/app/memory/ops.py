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


def close_doubt(
    memory: TeachingMemory, concept_id: str, session_id: str | None = None
) -> TeachingMemory:
    """Resolve a doubt — but only on a SPACED re-check, and that is now
    enforced rather than requested.

    The rule (memory_layer.md §2.3) is that one correct answer in the same
    session is not evidence a misconception is gone; getting it right ten
    minutes after being told is what a misconception looks like on its way
    back. Until now the rule lived in this docstring and in the reflect
    prompt, and nothing stopped the model closing a doubt it had opened forty
    minutes earlier in the same conversation — which silently erases the one
    thing the next session most needed to know.

    So: a doubt whose evidence all points at THIS session is left open, and
    `session_id` is passed by the only caller that has one. Every other memory
    rule is schema-enforced; this one had been on the honour system.

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
    def _same_session_only(doubt: OpenDoubt) -> bool:
        """Every citation is from the session being closed, so nothing here
        is a re-check — it is the same conversation agreeing with itself."""
        if not session_id or not doubt.evidence:
            return False
        return all(str(e).startswith(f"{session_id}#") for e in doubt.evidence)

    kept = []
    for doubt in memory.open_doubts:
        closeable = (
            doubt.concept_id == concept_id
            and doubt.status != "resolved"
            and not _same_session_only(doubt)
        )
        kept.append(
            OpenDoubt(**{**doubt.model_dump(), "status": "resolved"})
            if closeable else doubt
        )
    memory.open_doubts = kept
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
