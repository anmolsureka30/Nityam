import cv2
import numpy as np


def _largest_board_like_quad(frame: np.ndarray):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    best_area = 0
    for c in contours:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) != 4:
            continue
        area = cv2.contourArea(approx)
        if area > best_area:
            best_area = area
            best = approx.reshape(4, 2)
    if best is None:
        # Fallback: thresholded bright region's bounding box as a quad.
        _, mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        ys, xs = np.where(mask > 0)
        if len(xs) == 0:
            h, w = gray.shape
            return np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
        x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
        best = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float32)
    return best.astype(np.float32)


def locate_board(frames: list) -> tuple:
    """Vote the board quad across sampled frames — the board doesn't move; the teacher does."""
    quads = [_largest_board_like_quad(f) for f in frames]
    avg = np.mean(np.stack(quads), axis=0)
    return tuple(tuple(p) for p in avg)
