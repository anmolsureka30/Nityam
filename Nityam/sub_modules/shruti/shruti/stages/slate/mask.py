import cv2
import numpy as np


def framediff_masks(frames: list, dilate_px: int = 12) -> list:
    """V1 masking. Static camera + planar board => temporal median is a good
    background estimate; the teacher is the largest thing deviating from it.

    Deviation from the brief: each frame's background is the median of a
    *pool of other frames* rather than one median shared by every frame.

    History of this deviation, corrected here:
      - The brief's shared-median version computes one background from all
        frames and reuses it for every frame. If the occluder sits at the
        same pixel across a majority of the frames used to build it, the
        median absorbs the occluder into the "background" at that pixel,
        the diff silently goes to zero, and no downstream step (threshold,
        morphology, connected components) can recover it.
      - An earlier fix here only excluded each frame's own index from that
        same small, fixed ~10-frame stride subsample. That closes
        self-contamination (a frame can't out-vote itself) but not
        sample-majority contamination: for any frame whose index wasn't
        itself part of the stride grid, the pool was identical to every
        other such frame's pool — the *same* small ~10-frame sample — so an
        occluder dominating a majority of just that small sample (while
        being a clear minority of the whole span) still poisoned the
        estimate for most frames. That is a materially different failure
        mode from self-contamination, not a variant of it.

    This version draws each frame's pool from the FULL frame list, excluding
    a temporal window around that frame's own index (not just the index
    itself) sized to ~10% of the span. A lingering occluder covers several
    consecutive sampled frames, so frames immediately neighbouring `idx` are
    the ones most likely to share idx's own occlusion and shouldn't get a
    vote on whether idx itself is occluded; dropping them further improves
    the clean:contaminated ratio in borderline cases. Because the pool is
    now the (near-)full span rather than a ~10-frame subsample, an occluder
    has to dominate a majority of the entire board-state span — not an
    arbitrary small sample of it — before it can contaminate the estimate,
    which closes the realistic "dwells in one spot for a while, but still a
    minority of the whole span" gap.

    Fundamental V1 limit, NOT fixed by this or any median-based approach: if
    the occluder genuinely covers a majority of a frame's remaining pool —
    e.g. it dwells in the same spot for most of the whole board-state span —
    the median cannot distinguish it from the board. That case is out of
    scope for V1; it's exactly what the architecture doc's V3 (SAM3-based)
    masking upgrade exists to handle.

    Cost trade-off, deliberate: computing a near-full-span median per frame
    instead of reusing one ~10-frame median is materially slower (roughly
    3-4x more per-pixel median work at a typical ~45-frame span). This
    pipeline is offline/batch (no per-recording latency budget is defined
    anywhere in the config — `Budget` only tracks USD cost for the Gemini
    calls downstream), and this stage's failure mode — a masking false
    negative that flows into the compositor as if the occluder were
    legitimate board content — is treated elsewhere as equivalent to
    hallucinating board content, the worst failure mode this product has.
    Correctness was prioritized over the extra latency; if this becomes a
    real bottleneck, capping the pool well below `max_pool` (trading some
    robustness margin for speed) is the place to revisit it.
    """
    stacked = np.stack(frames)
    n_frames = len(frames)
    window = n_frames // 10
    # Safety valve for pathologically large inputs (board-state spans are
    # capped at ~45 sampled frames per the architecture doc, so this never
    # engages in practice and never reintroduces the small-sample bug above).
    max_pool = 300

    masks = []
    for idx, f in enumerate(frames):
        pool = [i for i in range(n_frames) if abs(i - idx) > window]
        if not pool:
            pool = [i for i in range(n_frames) if i != idx] or [idx]
        elif len(pool) > max_pool:
            pool = pool[:: len(pool) // max_pool + 1]
        bg = np.median(stacked[pool], axis=0).astype(np.uint8)
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
