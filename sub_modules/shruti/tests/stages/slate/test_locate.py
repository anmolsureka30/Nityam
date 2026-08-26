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
