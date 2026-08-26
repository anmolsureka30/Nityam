import pytest
from pydantic import ValidationError

from app.memory import ops
from app.memory.schemas import DPMProfile, TeachingMemory


def test_set_mastery_adds_a_weakness_entry():
    profile = DPMProfile(student_id="demo_student")
    ops.set_mastery(profile, "projectile.range", "partial", "weak", ["s1#4"])
    assert profile.weaknesses["projectile.range"].mastery == "partial"
    assert profile.weaknesses["projectile.range"].evidence == ["s1#4"]


def test_append_self_reflection_adds_a_note():
    profile = DPMProfile(student_id="demo_student")
    ops.append_self_reflection(profile, "responds well to area models", ["s1#6"])
    assert profile.self_reflection[0].note == "responds well to area models"
    assert profile.self_reflection[0].status == "active"


def test_open_doubt_adds_an_active_doubt():
    memory = TeachingMemory(student_id="demo_student")
    ops.open_doubt(memory, "projectile.range", "uses u instead of u*cos(theta)", "R = u^2 sin(2theta)/g", ["s1#4"])
    assert memory.open_doubts[0].status == "active"
    assert memory.open_doubts[0].concept_id == "projectile.range"


def test_close_doubt_only_affects_matching_concept():
    memory = TeachingMemory(student_id="demo_student")
    ops.open_doubt(memory, "projectile.range", "d1", "c1", ["s1#1"])
    ops.open_doubt(memory, "projectile.height", "d2", "c2", ["s1#2"])
    ops.close_doubt(memory, "projectile.range")
    assert memory.open_doubts[0].status == "resolved"
    assert memory.open_doubts[1].status == "active"


def test_update_coverage_merges_elements_used():
    memory = TeachingMemory(student_id="demo_student")
    ops.update_coverage(memory, "projectile.range", ["worked-example"], "s1#4", "in_progress")
    ops.update_coverage(memory, "projectile.range", ["diagram"], "s2#3", "covered")
    entry = memory.covered["projectile.range"]
    assert set(entry.elements_used) == {"worked-example", "diagram"}
    assert entry.taught_at == ["s1#4", "s2#3"]
    assert entry.status == "covered"


def test_update_coverage_rejects_an_invalid_status():
    """pydantic v2 does not validate plain attribute assignment, so mutating
    an existing CoveredConcept in place (entry.status = status) would let a
    bad status silently through instead of raising. update_coverage must go
    through the schema's constructor so this is validated."""
    memory = TeachingMemory(student_id="demo_student")
    with pytest.raises(ValidationError):
        ops.update_coverage(memory, "projectile.range", ["worked-example"], "s1#4", "not_a_real_status")


def test_update_coverage_leaves_existing_entry_untouched_when_new_status_is_invalid():
    memory = TeachingMemory(student_id="demo_student")
    ops.update_coverage(memory, "projectile.range", ["worked-example"], "s1#4", "in_progress")
    with pytest.raises(ValidationError):
        ops.update_coverage(memory, "projectile.range", ["diagram"], "s2#3", "not_a_real_status")
    entry = memory.covered["projectile.range"]
    assert entry.status == "in_progress"
    assert entry.elements_used == ["worked-example"]
    assert entry.taught_at == ["s1#4"]
