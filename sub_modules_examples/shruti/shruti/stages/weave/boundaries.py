import numpy as np
from shruti.contracts.speech import Utterance
from shruti.contracts.timeline import Shot

_INFLECT = 5.0


def candidate_boundaries(
    utterances: list[Utterance], ink_curve, times, shots: list[Shot],
    extra_boundaries: list[float] | None = None,
) -> list[float]:
    boundaries = set()

    for a, b in zip(utterances, utterances[1:]):
        if b.start_s - a.end_s > 1.5:
            boundaries.add((a.end_s + b.start_s) / 2)

    if len(ink_curve) > 2:
        d = np.gradient(ink_curve)
        for i in range(1, len(d) - 1):
            if np.sign(d[i - 1]) != np.sign(d[i + 1]) and abs(d[i - 1] - d[i + 1]) > _INFLECT:
                boundaries.add(float(times[i]))

    boundaries.update(s.start_s for s in shots)
    # For non-board content, ink_curve is intentionally empty (see
    # board_signal.py) — extra_boundaries carries the replacement content-
    # change signal (slide-sample points) so WEAVE's fusion still gets a
    # real boundary source instead of relying on speech gaps and shot cuts
    # alone. Empty/None for board content, where ink_curve already covers
    # this — must stay a true no-op there (no behavior change).
    boundaries.update(extra_boundaries or [])

    return merge_within(sorted(boundaries), 2.0)


def merge_within(boundaries: list[float], merge_s: float) -> list[float]:
    if not boundaries:
        return []
    merged = [boundaries[0]]
    for b in boundaries[1:]:
        if b - merged[-1] >= merge_s:
            merged.append(b)
    return merged
