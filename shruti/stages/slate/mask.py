import cv2
import numpy as np


def framediff_masks(frames: list, dilate_px: int = 12) -> list:
    """V1 masking. Static camera + planar board => temporal median is a good
    background estimate; the teacher is the largest thing deviating from it.

    Deviation from the brief: each frame's background excludes that frame
    itself (leave-one-out), instead of reusing a single median computed from
    all frames for every frame. Reusing one shared median is vulnerable to
    "ghosting" — if the occluder sits at the same pixel in a majority of the
    sampled frames (e.g. a teacher pausing in place), the median absorbs the
    occluder into the "background" at that pixel, the diff silently goes to
    zero, and no downstream step (threshold, morphology, connected
    components) can recover it. Leaving each frame out of its own estimate
    fixes that without changing the algorithm's spirit, and — because the
    existing stride already caps the sample at ~10 frames regardless of
    input size — costs no more asymptotically than the shared-background
    version.
    """
    stacked = np.stack(frames)
    n_frames = len(frames)
    step = max(1, n_frames // 10 or 1)

    masks = []
    for idx, f in enumerate(frames):
        other = [i for i in range(0, n_frames, step) if i != idx]
        if not other:
            other = [i for i in range(n_frames) if i != idx] or [idx]
        bg = np.median(stacked[other], axis=0).astype(np.uint8)
        bg_g = cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY)

        d = cv2.absdiff(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), bg_g)
        _, m = cv2.threshold(d, 32, 255, cv2.THRESH_BINARY)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))

        n_labels, lbl, stats, _ = cv2.connectedComponentsWithStats(m, 8)
        out = np.zeros_like(m, dtype=bool)
        if n_labels > 1:
            k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
            if stats[k, cv2.CC_STAT_AREA] > 0.01 * m.size:
                out = (lbl == k)
        dilated = cv2.dilate(out.astype(np.uint8), np.ones((dilate_px, dilate_px), np.uint8))
        masks.append(dilated.astype(bool))
    return masks
