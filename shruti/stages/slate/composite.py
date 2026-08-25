import numpy as np
from shruti.stages.slate.photometric import match_local


def composite_board_state(frames, masks, target_idx, span_start, span_end, photometric=True):
    """Recover the most complete view of one board state. Within a state,
    content only grows (removed only at the erase that ends the state), so
    later frames are supersets — search forward first, backward as fallback."""
    target = frames[target_idx].copy()
    unfilled = masks[target_idx].astype(bool).copy()

    def donate(i):
        nonlocal unfilled, target
        can = unfilled & ~masks[i].astype(bool)
        if not can.any():
            return
        patch = frames[i]
        if photometric:
            patch = match_local(patch, target, can)
        target[can] = patch[can]
        unfilled &= ~can

    for i in range(target_idx + 1, span_end):
        donate(i)
        if not unfilled.any():
            break

    if unfilled.any():
        for i in range(target_idx - 1, span_start - 1, -1):
            donate(i)
            if not unfilled.any():
                break

    return target, unfilled
