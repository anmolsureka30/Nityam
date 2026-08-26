from shruti.contracts.timeline import Shot, EraseEvent, SamplePlanRegion

_ERASE_WINDOW_S = 5.0


def build_sample_plan(
    shots: list[Shot],
    erase_events: list[EraseEvent],
    duration_s: float,
    dense_fps: float,
    sparse_fps: float,
) -> list[SamplePlanRegion]:
    boundaries = sorted({0.0, duration_s} | {e.at_s for e in erase_events})
    erase_times = [e.at_s for e in erase_events]
    regions = []
    for start, end in zip(boundaries, boundaries[1:]):
        near_erase = any(abs(start - t) <= _ERASE_WINDOW_S or abs(end - t) <= _ERASE_WINDOW_S
                          for t in erase_times)
        fps = max(dense_fps, 2.0) if near_erase else sparse_fps
        threshold = 3.0 if near_erase else 10.0
        regions.append(SamplePlanRegion(start_s=start, end_s=end, fps=fps,
                                         pixel_diff_threshold=threshold))
    return regions
