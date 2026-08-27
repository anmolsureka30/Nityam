from __future__ import annotations

from observatory.diff import diff_dpm, diff_teaching_memory


def test_diff_dpm_reports_new_weakness():
    old = {"student_id": "s1", "weaknesses": {}, "self_reflection": []}
    new = {
        "student_id": "s1",
        "weaknesses": {"projectile.range": {"mastery": "partial", "strength": "weak", "evidence": ["x#1"]}},
        "self_reflection": [],
    }
    changes = diff_dpm(old, new)
    assert len(changes) == 1
    assert changes[0].kind == "added"
    # No ".mastery" suffix here — that's the "changed" shape (see
    # test_diff_dpm_reports_mastery_transition below). Conflating the two
    # shapes was a real bug source elsewhere in this plan (Tasks 11/23).
    assert changes[0].path == "weaknesses.projectile.range"
    assert changes[0].label == "new weakness tracked: projectile.range (partial)"


def test_diff_dpm_reports_mastery_transition():
    old = {"student_id": "s1", "weaknesses": {
        "projectile.range": {"mastery": "partial", "strength": "weak", "evidence": ["x#1"]},
    }, "self_reflection": []}
    new = {"student_id": "s1", "weaknesses": {
        "projectile.range": {"mastery": "known", "strength": "strong", "evidence": ["x#1", "x#2"]},
    }, "self_reflection": []}
    changes = diff_dpm(old, new)
    labels = {c.path: c.label for c in changes}
    assert labels["weaknesses.projectile.range.mastery"] == "projectile.range.mastery: partial -> known"
    assert labels["weaknesses.projectile.range.strength"] == "projectile.range.strength: weak -> strong"


def test_diff_dpm_no_changes_when_identical():
    profile = {"student_id": "s1", "weaknesses": {
        "x": {"mastery": "known", "strength": "strong", "evidence": ["e1"]},
    }, "self_reflection": []}
    assert diff_dpm(profile, profile) == []


def test_diff_dpm_treats_missing_old_as_empty():
    new = {"student_id": "s1", "weaknesses": {}, "self_reflection": [{"note": "responds well to worked examples", "evidence": ["x#1"]}]}
    changes = diff_dpm(None, new)
    assert len(changes) == 1
    assert changes[0].kind == "added"
    assert changes[0].path == "self_reflection"
    assert changes[0].label == 'new self-reflection: "responds well to worked examples"' 


def test_diff_teaching_memory_reports_coverage_transition():
    old = {"student_id": "s1", "covered": {"projectile.range": {"status": "in_progress"}}, "open_doubts": []}
    new = {"student_id": "s1", "covered": {"projectile.range": {"status": "covered"}}, "open_doubts": []}
    changes = diff_teaching_memory(old, new)
    assert len(changes) == 1
    assert changes[0].label == "projectile.range coverage: in_progress -> covered"


def test_diff_teaching_memory_reports_doubt_lifecycle_transition():
    old = {"student_id": "s1", "covered": {}, "open_doubts": [
        {"concept_id": "projectile.range", "status": "active", "doubt": "d", "correct_understanding": "c", "evidence": ["x#1"]},
    ]}
    new = {"student_id": "s1", "covered": {}, "open_doubts": [
        {"concept_id": "projectile.range", "status": "resolved", "doubt": "d", "correct_understanding": "c", "evidence": ["x#1"]},
    ]}
    changes = diff_teaching_memory(old, new)
    assert len(changes) == 1
    assert changes[0].label == "doubt on projectile.range: active -> resolved"
