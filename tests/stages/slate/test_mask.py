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
