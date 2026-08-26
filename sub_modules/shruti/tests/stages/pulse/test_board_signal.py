import numpy as np
from shruti.contracts.timeline import Shot
from shruti.stages.pulse.board_signal import compute_board_signal


def test_compute_board_signal_skips_board_detection_for_slides():
    shots = [Shot(start_s=0.0, end_s=100.0)]
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    signal = compute_board_signal(
        "slides", shots, coarse_frames=[frame], coarse_times=[0.0],
        duration_s=100.0, drop_ratio=0.35, window_s=3.0,
        dense_fps=1.0, sparse_fps=1 / 6,
    )
    assert signal.quad is None
    assert signal.curve.size == 0
    assert signal.erase_events == []
    assert signal.sample_plan == []


def test_compute_board_signal_skips_for_mixed_and_talking_head_too():
    shots = [Shot(start_s=0.0, end_s=10.0)]
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    for kind in ("mixed", "talking_head"):
        signal = compute_board_signal(
            kind, shots, coarse_frames=[frame], coarse_times=[0.0],
            duration_s=10.0, drop_ratio=0.35, window_s=3.0,
            dense_fps=1.0, sparse_fps=1 / 6,
        )
        assert signal.quad is None
        assert signal.sample_plan == []


def test_compute_board_signal_returns_empty_when_no_frames_sampled():
    shots = [Shot(start_s=0.0, end_s=10.0)]
    signal = compute_board_signal(
        "blackboard", shots, coarse_frames=[], coarse_times=[],
        duration_s=10.0, drop_ratio=0.35, window_s=3.0,
        dense_fps=1.0, sparse_fps=1 / 6,
    )
    assert signal.quad is None
    assert signal.curve.size == 0
    assert signal.sample_plan == []
