import pytest

from shruti.contracts.timeline import Shot
from shruti.stages.pulse.slide_sampling import compute_slide_sample_spans


def test_single_long_shot_gets_periodic_samples_not_just_two_points():
    # This is the exact real-world case that motivated the fix: an 18-minute
    # (1129.7s) lecture with continuous screen recording registered as a
    # single PULSE shot, so the old shot-cut-only logic sampled only 2
    # points (start + one midpoint) for the whole video.
    shots = [Shot(start_s=0.0, end_s=1129.7)]
    spans = compute_slide_sample_spans(shots, duration_s=1129.7, interval_s=25.0)
    assert len(spans) >= 40  # 1129.7 / 25 ~= 45
    assert spans[0][0] == 0.0
    assert spans[-1][1] == 1129.7
    for start, end in spans:
        assert end - start <= 25.0 + 1e-6
        assert end > start


def test_short_shots_keep_one_sample_each_no_extra_periodic_points():
    shots = [Shot(start_s=0.0, end_s=5.0), Shot(start_s=5.0, end_s=12.0)]
    spans = compute_slide_sample_spans(shots, duration_s=12.0, interval_s=25.0)
    assert [start for start, _ in spans] == [0.0, 5.0]
    assert spans[-1] == (5.0, 12.0)


def test_spans_are_contiguous_and_cover_the_full_duration():
    shots = [Shot(start_s=0.0, end_s=60.0)]
    spans = compute_slide_sample_spans(shots, duration_s=60.0, interval_s=25.0)
    for (_, end), (next_start, _) in zip(spans, spans[1:]):
        assert end == next_start
    assert spans[0][0] == 0.0
    assert spans[-1][1] == 60.0


def test_non_positive_interval_raises_instead_of_hanging():
    shots = [Shot(start_s=0.0, end_s=10.0)]
    with pytest.raises(ValueError):
        compute_slide_sample_spans(shots, duration_s=10.0, interval_s=0.0)
