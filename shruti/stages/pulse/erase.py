import numpy as np
from shruti.contracts.timeline import EraseEvent


def find_erase_events(curve, times, drop_ratio: float = 0.35, window_s: float = 3.0) -> list[EraseEvent]:
    events = []
    dt = times[1] - times[0]
    w = max(2, int(window_s / dt))

    for i in range(w, len(curve) - w):
        before = curve[i - w:i].max()
        after = curve[i:i + w].min()
        if before <= 0:
            continue
        if (before - after) / before < drop_ratio:
            continue
        tail = curve[i + w:i + 3 * w]
        if len(tail) and tail.mean() > after * 1.6:
            continue
        events.append(EraseEvent(at_s=float(times[i]), before=float(before), after=float(after)))

    return dedupe_within(events, min_gap_s=10.0)


def dedupe_within(events: list[EraseEvent], min_gap_s: float = 10.0) -> list[EraseEvent]:
    if not events:
        return []
    events = sorted(events, key=lambda e: e.at_s)
    deduped = []
    i = 0
    while i < len(events):
        # Find all events within min_gap_s of current event
        j = i + 1  # Always advance at least one position
        while j < len(events) and events[j].at_s - events[i].at_s < min_gap_s:
            j += 1
        # Keep the median event in this gap
        mid_idx = (i + j - 1) // 2
        deduped.append(events[mid_idx])
        i = j
    return deduped
