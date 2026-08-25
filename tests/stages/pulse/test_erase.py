import numpy as np
from shruti.stages.pulse.erase import find_erase_events, dedupe_within
from shruti.contracts.timeline import EraseEvent


def test_find_erase_events_detects_sustained_drop():
    times = np.arange(0, 20, 0.5)
    curve = np.concatenate([
        np.linspace(0, 1000, 10),   # writing builds up, t=0..4.5
        np.full(10, 1000.0),        # holds steady, t=5..9.5
        np.full(10, 50.0),          # erased and stays low, t=10..14.5
        np.full(10, 60.0),          # still low, t=15..19.5
    ])
    events = find_erase_events(curve, times, drop_ratio=0.35, window_s=3.0)
    assert len(events) == 1
    assert 9.0 <= events[0].at_s <= 11.0


def test_find_erase_events_ignores_transient_occlusion():
    times = np.arange(0, 20, 0.5)
    curve = np.full(40, 1000.0)
    curve[16:20] = 50.0  # a brief dip (teacher walks in front) that recovers
    events = find_erase_events(curve, times, drop_ratio=0.35, window_s=3.0)
    assert events == []


def test_dedupe_within_merges_close_events():
    events = [
        EraseEvent(at_s=10.0, before=1000, after=50),
        EraseEvent(at_s=10.5, before=1000, after=50),
        EraseEvent(at_s=30.0, before=1000, after=50),
    ]
    deduped = dedupe_within(events, min_gap_s=10.0)
    assert [e.at_s for e in deduped] == [10.0, 30.0]
