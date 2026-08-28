from __future__ import annotations

from observatory.events import EnrichedEvent, MemoryEvent


def test_a_real_tutor_published_event_parses_under_the_local_model():
    """Wire-compatibility, not class identity: the Observatory's own
    MemoryEvent must be able to decode JSON produced by either agent app's
    instrumentation.py, without importing either one's package."""
    from app.memory.instrumentation import MemoryEvent as TutorMemoryEvent

    tutor_event = TutorMemoryEvent(
        event_id="e1", ts="2026-08-27T00:00:00Z", session_id="s1", student_id="stu1",
        tier="long_term", operation="write", record_type="dpm_profile",
        source_fn="put_dpm", trace_id=None, span_id=None, payload={"student_id": "stu1"},
    )
    parsed = MemoryEvent.model_validate_json(tutor_event.model_dump_json())
    assert parsed.model_dump() == tutor_event.model_dump()


def test_enriched_event_wraps_a_memory_event_with_an_optional_diff():
    event = MemoryEvent(
        event_id="e1", ts="2026-08-27T00:00:00Z", session_id="s1", student_id="stu1",
        tier="long_term", operation="write", record_type="dpm_profile",
        source_fn="put_dpm", trace_id=None, span_id=None, payload={"student_id": "stu1"},
    )
    enriched = EnrichedEvent(event=event, diff=[])
    assert enriched.event.session_id == "s1"
    assert enriched.diff == []
