import numpy as np
from shruti.stages.slate.mask import framediff_masks


def _frame_with_blob(size=60, blob_xy=(10, 10), blob_wh=(15, 15)):
    frame = np.full((size, size, 3), 200, dtype=np.uint8)  # static board background
    x, y = blob_xy
    w, h = blob_wh
    frame[y:y + h, x:x + w] = 40  # the "teacher" — a dark blob that moves between frames
    return frame


def test_framediff_masks_flags_the_moving_blob_not_the_background():
    frames = [
        _frame_with_blob(blob_xy=(5, 5)),
        _frame_with_blob(blob_xy=(30, 30)),
        _frame_with_blob(blob_xy=(5, 5)),
    ]
    masks = framediff_masks(frames, dilate_px=2)
    assert masks[0][10, 10]  # first frame's blob position is masked
    assert not masks[0][50, 50]  # far corner, never touched by the blob, stays unmasked


def test_framediff_masks_flags_occluder_that_dwells_in_one_spot_across_a_realistic_span():
    """Regression test for a masking gap found in review: with a realistic
    frame count (a board-state span can hold up to ~45 sampled frames per
    the architecture doc), a background estimate built from only a small,
    fixed subsample of frames can see the occluder as a *majority within
    that small subsample* even though it's a clear minority (6 of 20, 30%)
    of the whole span. Here the occluder sits at the same board position in
    frames 0, 2, 4, 8, 12, 16, and 1 — a realistic "teacher pauses in one
    spot for a while" pattern. Frame 1 is deliberately never aligned to any
    fixed stride grid, so this only passes if the background estimate for
    frame 1 is drawn from (close to) the full span rather than a small fixed
    sample of it."""
    n = 20
    frames = []
    for i in range(n):
        if i in (0, 2, 4, 8, 12, 16):
            frames.append(_frame_with_blob(blob_xy=(5, 5)))
        else:
            frames.append(_frame_with_blob(blob_xy=(30, 30)))
    frames[1] = _frame_with_blob(blob_xy=(5, 5))  # genuinely occluded, never stride-aligned

    masks = framediff_masks(frames, dilate_px=2)
    assert masks[1][10, 10]  # occluder is genuinely present in frame 1
    assert not masks[1][50, 50]  # far corner, never touched by the blob, stays unmasked
