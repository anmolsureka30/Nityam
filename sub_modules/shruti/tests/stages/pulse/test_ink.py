import numpy as np
from shruti.stages.pulse.ink import binarize_ink


def test_binarize_ink_chalk_polarity_finds_bright_marks():
    board = np.zeros((40, 40, 3), dtype=np.uint8)  # dark board
    board[10:30, 10:30] = 255  # bright chalk mark
    ink = binarize_ink(board, polarity="bright_on_dark")
    assert ink[15, 15] > 0
    assert ink[2, 2] == 0


def test_binarize_ink_marker_polarity_finds_dark_marks():
    board = np.full((40, 40, 3), 255, dtype=np.uint8)  # bright whiteboard
    board[10:30, 10:30] = 0  # dark marker mark
    ink = binarize_ink(board, polarity="dark_on_bright")
    assert ink[15, 15] > 0
    assert ink[2, 2] == 0
