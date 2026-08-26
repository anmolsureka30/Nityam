import cv2
import numpy as np


def binarize_ink(board_bgr: np.ndarray, polarity: str) -> np.ndarray:
    """polarity: 'bright_on_dark' (chalk) | 'dark_on_bright' (marker)"""
    g = cv2.cvtColor(board_bgr, cv2.COLOR_BGR2GRAY)
    g = cv2.GaussianBlur(g, (3, 3), 0)
    flag = cv2.THRESH_BINARY if polarity == "bright_on_dark" else cv2.THRESH_BINARY_INV
    ink = cv2.adaptiveThreshold(
        g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, flag,
        blockSize=25, C=-8 if polarity == "bright_on_dark" else 8,
    )
    return cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))


def ink_curve(sampled: list, quad, polarity: str) -> np.ndarray:
    from shruti.stages.slate.rectify import rectify
    return np.array([
        binarize_ink(rectify(f, quad), polarity).sum() / 255
        for f in sampled
    ])
