from __future__ import annotations

from observatory.events import EnrichedEvent, MemoryEvent


def test_memory_event_is_the_tutor_apps_own_class():
    from app.memory.instrumentation import MemoryEvent as TutorMemoryEvent
    assert MemoryEvent is TutorMemoryEvent


def test_enriched_event_wraps_a_memory_event_with_an_optional_diff():
    event = MemoryEvent(
        event_id="e1", ts="2026-08-27T00:00:00Z", session_id="s1", student_id="stu1",
        tier="long_term", operation="write", record_type="dpm_profile",
        source_fn="put_dpm", trace_id=None, span_id=None, payload={"student_id": "stu1"},
    )
    enriched = EnrichedEvent(event=event, diff=[])
    assert enriched.event.session_id == "s1"
    assert enriched.diff == []
