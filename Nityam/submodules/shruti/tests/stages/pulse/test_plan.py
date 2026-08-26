from shruti.stages.pulse.plan import build_sample_plan
from shruti.contracts.timeline import Shot, EraseEvent


def test_build_sample_plan_covers_full_duration_with_no_gaps():
    shots = [Shot(start_s=0.0, end_s=30.0)]
    erases = [EraseEvent(at_s=15.0, before=1000, after=50)]
    plan = build_sample_plan(shots, erases, duration_s=30.0, dense_fps=1.0, sparse_fps=1 / 6)
    assert plan[0].start_s == 0.0
    assert plan[-1].end_s == 30.0
    for a, b in zip(plan, plan[1:]):
        assert abs(a.end_s - b.start_s) < 1e-6


def test_build_sample_plan_samples_densely_near_erase_events():
    shots = [Shot(start_s=0.0, end_s=30.0)]
    erases = [EraseEvent(at_s=15.0, before=1000, after=50)]
    plan = build_sample_plan(shots, erases, duration_s=30.0, dense_fps=1.0, sparse_fps=1 / 6)
    near_erase = [r for r in plan if r.start_s <= 15.0 <= r.end_s]
    assert near_erase and near_erase[0].fps >= 1.0
