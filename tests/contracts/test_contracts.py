import pytest
from pydantic import ValidationError
from shruti.contracts.recording import Recording, SurfaceKind
from shruti.contracts.timeline import Shot, EraseEvent, SamplePlanRegion, Timeline
from shruti.contracts.board import Region, BoardContent, BoardState
from shruti.contracts.speech import LanguageSpan, Utterance, Deixis
from shruti.contracts.beat import Beat
from shruti.contracts.atlas import BeatRef, Concept, Edge, Misconception


def test_recording_requires_surface_kind():
    with pytest.raises(ValidationError):
        Recording(id="a" * 64, source_uri="gs://x", duration_s=1.0, fps=30.0)
    r = Recording(id="a" * 64, source_uri="gs://x", duration_s=1.0, fps=30.0,
                   surface_kind=SurfaceKind.BLACKBOARD)
    assert r.reel_version == 1


def test_beat_carries_speech_and_deixis():
    u = Utterance(id="u1", recording_id="r1", start_s=0.0, end_s=1.0, text="hi",
                   speaker="TEACHER")
    d = Deixis(id="d1", recording_id="r1", at_s=0.5, board_region=(0.1, 0.1, 0.2, 0.2),
               kind="point")
    b = Beat(id="b1", recording_id="r1", idx=0, start_s=0.0, end_s=1.0, kind="explain",
             speech=[u], deixis=[d], transcript="hi")
    assert b.speech[0].text == "hi"
    assert b.deixis[0].kind == "point"


def test_concept_and_edge_require_atlas_fields():
    c = Concept(id="c1", canonical_name="completing the square",
                taught_in=[BeatRef(beat_id="b1", relation="taught_in")])
    e = Edge(id="e1", from_concept="c0", to_concept="c1", edge_type="REQUIRES",
              evidence=[BeatRef(beat_id="b1", relation="evidence_for")])
    m = Misconception(id="m1", concept_id="c1", statement="treats (a+b)^2 as a^2+b^2",
                       correct_understanding="(a+b)^2 = a^2+2ab+b^2",
                       pre_empted_at_beat="b1")
    assert c.taught_in[0].relation == "taught_in"
    assert e.edge_type == "REQUIRES"
    assert m.pre_empted_at_beat == "b1"


def test_board_state_unreadable_region_has_reason():
    region = Region(id="r1", bbox=(0.0, 0.0, 0.1, 0.1), kind="unreadable",
                     reason="occluded throughout state")
    content = BoardContent(regions=[region])
    bs = BoardState(id="bs1", recording_id="r1", idx=0, valid_from_s=0.0,
                     valid_to_s=10.0, composited_uri="gs://x", ended_by="erase",
                     content=content)
    assert bs.content.regions[0].reason == "occluded throughout state"


def test_timeline_shapes():
    t = Timeline(recording_id="r1", shots=[Shot(start_s=0.0, end_s=5.0)],
                 ink_curve=[0.0, 1.0], ink_curve_times=[0.0, 1.0],
                 erase_events=[EraseEvent(at_s=5.0, before=10.0, after=1.0)],
                 sample_plan=[SamplePlanRegion(start_s=0.0, end_s=5.0, fps=1.0,
                                               pixel_diff_threshold=3.0)])
    assert t.erase_events[0].after == 1.0
