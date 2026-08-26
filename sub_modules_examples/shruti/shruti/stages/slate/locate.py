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
    """Vote the board quad across sampled frames — the board doesn't move;
    the teacher does. But not every sampled frame necessarily SHOWS the
    board: a video's coarse frame samples span its full duration, and can
    land on an intro/outro/title card with no board in view at all.
    Confirmed live: one such frame (a "Subscribe" outro card) produced a
    tiny, nonsense quad in a corner via the bright-region fallback above,
    and averaging it in with the real per-frame detections dragged the
    combined quad off the actual board entirely — which corrupted every
    frame's perspective rectification identically, so no amount of
    downstream occlusion-filling could recover it (composited_board.jpg
    came back pure black despite 0% of it being flagged "unfilled" — every
    rectified frame was equally wrong, so donating from one to another
    changed nothing). Two changes: drop any single frame's quad whose area
    is implausibly small for an actual board (a board being filmed should
    dominate the frame, not occupy a sliver), and combine what's left with
    the median rather than the mean — a robust central tendency that isn't
    dragged off by the rare bad detection that still slips through."""
    quads = [_largest_board_like_quad(f) for f in frames]
    frame_area = frames[0].shape[0] * frames[0].shape[1]
    plausible = [q for q in quads if cv2.contourArea(q) >= 0.15 * frame_area]
    if not plausible:
        plausible = quads
    combined = np.median(np.stack(plausible), axis=0)
    return tuple(tuple(p) for p in combined)
