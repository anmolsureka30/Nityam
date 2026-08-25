import cv2
import numpy as np


def rectify(frame: np.ndarray, quad, out_size: tuple = (800, 600)) -> np.ndarray:
    src = np.array(quad, dtype=np.float32)
    w, h = out_size
    dst = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(frame, matrix, (w, h))
