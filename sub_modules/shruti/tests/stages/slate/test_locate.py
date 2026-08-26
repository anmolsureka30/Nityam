import numpy as np
from shruti.stages.slate.locate import locate_board


def _frame_with_white_board_on_black(w=200, h=150, board_box=(30, 20, 170, 130)):
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    x0, y0, x1, y1 = board_box
    frame[y0:y1, x0:x1] = 255
    return frame


def test_locate_board_finds_the_bright_rectangle():
    frames = [_frame_with_white_board_on_black() for _ in range(5)]
    quad = locate_board(frames)
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    assert min(xs) < 40 and max(xs) > 160
    assert min(ys) < 30 and max(ys) > 120


def test_locate_board_ignores_a_minority_of_frames_with_no_real_board():
    # Confirmed live: a video's coarse-sampled frames can land on a
    # non-board frame (an intro/outro/title card) whose only "bright
    # region" is a tiny corner of text or a logo. This must not drag the
    # combined quad off the real board that the other frames clearly show
    # — that's exactly what produced a pure-black composited board on a
    # real run (see locate_board's own docstring for the full story).
    board_frames = [_frame_with_white_board_on_black() for _ in range(8)]
    noise_frame = np.zeros((150, 200, 3), dtype=np.uint8)
    noise_frame[10:20, 160:190] = 255  # small bright corner, nowhere near the real board
    frames = board_frames + [noise_frame]
    quad = locate_board(frames)
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    assert min(xs) < 40 and max(xs) > 160
    assert min(ys) < 30 and max(ys) > 120
