import numpy as np
from shruti.stages.slate.composite import composite_board_state


def test_composite_fills_target_holes_from_a_later_frame():
    size = 20
    frames = [np.full((size, size, 3), 100, dtype=np.uint8) for _ in range(3)]
    frames[1][5:10, 5:10] = 222  # new writing appears in frame 1, absent in frame 0
    masks = [np.zeros((size, size), dtype=bool) for _ in range(3)]
    masks[0][5:10, 5:10] = True  # frame 0's teacher occludes exactly that region

    composited, unfilled = composite_board_state(
        frames, masks, target_idx=0, span_start=0, span_end=3, photometric=False
    )
    assert not unfilled.any()
    assert (composited[5:10, 5:10] == 222).all()


def test_composite_falls_back_to_backward_frame_when_forward_is_also_occluded():
    size = 20
    frames = [np.full((size, size, 3), 100, dtype=np.uint8) for _ in range(3)]
    frames[0][5:10, 5:10] = 77  # earlier frame has the content visible

    masks = [np.zeros((size, size), dtype=bool) for _ in range(3)]
    masks[1][5:10, 5:10] = True  # target frame occludes it
    masks[2][5:10, 5:10] = True  # every later frame also occludes it

    composited, unfilled = composite_board_state(
        frames, masks, target_idx=1, span_start=0, span_end=3, photometric=False
    )
    assert not unfilled.any()
    assert (composited[5:10, 5:10] == 77).all()


def test_composite_returns_unfilled_when_no_frame_ever_shows_the_region():
    size = 20
    frames = [np.full((size, size, 3), 100, dtype=np.uint8) for _ in range(3)]
    masks = [np.zeros((size, size), dtype=bool) for _ in range(3)]
    for m in masks:
        m[5:10, 5:10] = True  # occluded in every single frame

    composited, unfilled = composite_board_state(
        frames, masks, target_idx=0, span_start=0, span_end=3, photometric=False
    )
    assert unfilled[5:10, 5:10].all()
