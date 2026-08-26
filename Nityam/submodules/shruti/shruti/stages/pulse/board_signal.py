from dataclasses import dataclass, field

import numpy as np

from shruti.contracts.recording import is_physical_board
from shruti.contracts.timeline import EraseEvent, SamplePlanRegion, Shot
from shruti.stages.pulse.erase import find_erase_events
from shruti.stages.pulse.ink import ink_curve
from shruti.stages.pulse.plan import build_sample_plan
from shruti.stages.slate.locate import locate_board


@dataclass
class BoardSignal:
    quad: object | None
    curve: np.ndarray
    erase_events: list[EraseEvent] = field(default_factory=list)
    sample_plan: list[SamplePlanRegion] = field(default_factory=list)


def _empty_signal() -> BoardSignal:
    return BoardSignal(quad=None, curve=np.array([]), erase_events=[], sample_plan=[])


def compute_board_signal(
    surface_kind: str,
    shots: list[Shot],
    coarse_frames: list,
    coarse_times: list[float],
    duration_s: float,
    drop_ratio: float,
    window_s: float,
    dense_fps: float,
    sparse_fps: float,
) -> BoardSignal:
    """Board-quad location, ink-curve tracking, and erase-event detection
    only make sense for a physical chalkboard/whiteboard. For slides or
    talking-head content there's nothing to rectify or erase — running this
    unconditionally wasted real compute and produced a misleading "erase
    events" signal on content that was never a board (confirmed on a real
    slides-video run). Skip the whole sub-path for non-board surface kinds."""
    if not is_physical_board(surface_kind) or not coarse_frames:
        return _empty_signal()
    quad = locate_board(coarse_frames)
    if quad is None:
        return _empty_signal()
    polarity = "bright_on_dark" if surface_kind == "blackboard" else "dark_on_bright"
    curve = ink_curve(coarse_frames, quad, polarity)
    erase_events = find_erase_events(curve, coarse_times, drop_ratio=drop_ratio, window_s=window_s)
    sample_plan = build_sample_plan(shots, erase_events, duration_s, dense_fps, sparse_fps)
    return BoardSignal(quad=quad, curve=curve, erase_events=erase_events, sample_plan=sample_plan)
