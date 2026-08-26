import numpy as np
from shruti.stages.weave.boundaries import candidate_boundaries, merge_within
from shruti.contracts.speech import Utterance
from shruti.contracts.timeline import Shot


def test_candidate_boundaries_detects_speech_pause():
    utterances = [
        Utterance(id="u1", recording_id="r1", start_s=0.0, end_s=5.0, text="a", speaker="TEACHER"),
        Utterance(id="u2", recording_id="r1", start_s=8.0, end_s=10.0, text="b", speaker="TEACHER"),
    ]
    times = np.arange(0, 10, 1.0)
    ink_curve = np.zeros_like(times)
    boundaries = candidate_boundaries(utterances, ink_curve, times, shots=[])
    assert any(5.5 <= b <= 7.5 for b in boundaries)


def test_merge_within_collapses_close_boundaries():
    merged = merge_within([1.0, 1.5, 1.9, 10.0], merge_s=2.0)
    assert merged == [1.0, 10.0]


def test_extra_boundaries_are_included_and_merged():
    utterances = []
    times = np.arange(0, 10, 1.0)
    ink_curve = np.array([])  # empty, as it is for non-board content
    boundaries = candidate_boundaries(
        utterances, ink_curve, times, shots=[], extra_boundaries=[3.0, 3.5, 8.0],
    )
    # 3.0 and 3.5 are within merge_s=2.0 of each other and collapse to one;
    # 8.0 survives as its own boundary.
    assert boundaries == [3.0, 8.0]


def test_no_extra_boundaries_is_a_true_no_op():
    utterances = [
        Utterance(id="u1", recording_id="r1", start_s=0.0, end_s=5.0, text="a", speaker="TEACHER"),
        Utterance(id="u2", recording_id="r1", start_s=8.0, end_s=10.0, text="b", speaker="TEACHER"),
    ]
    times = np.arange(0, 10, 1.0)
    ink_curve = np.zeros_like(times)
    without_extra = candidate_boundaries(utterances, ink_curve, times, shots=[])
    with_none = candidate_boundaries(utterances, ink_curve, times, shots=[], extra_boundaries=None)
    with_empty = candidate_boundaries(utterances, ink_curve, times, shots=[], extra_boundaries=[])
    assert without_extra == with_none == with_empty
