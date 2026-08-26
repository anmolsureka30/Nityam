from shruti.contracts.timeline import Shot


def compute_slide_sample_spans(
    shots: list[Shot], duration_s: float, interval_s: float = 25.0,
) -> list[tuple[float, float]]:
    """Sample points for reading slide/talking-head content directly (no
    physical board to rectify — see is_physical_board). Shot cuts alone
    under-sample real content: a continuous screen recording with no hard
    scene cuts registers as a single shot regardless of how many times the
    visible slide actually changed. Confirmed on a real 1129.7s lecture: 1
    detected shot, which the old shot-cut-only logic turned into 2 samples
    for the whole video. Merge shot-cut points with periodic samples every
    `interval_s` seconds so a long continuous shot still gets real
    coverage."""
    points = {0.0} | {s.start_s for s in shots}
    for s in shots:
        t = s.start_s
        while t + interval_s < s.end_s:
            t += interval_s
            points.add(t)
    sample_points = sorted(points)
    return list(zip(sample_points, sample_points[1:] + [duration_s]))
