from shruti.contracts.beat import Beat
from shruti.contracts.board import BoardContent, BoardState, Region
from shruti.contracts.recording import Recording, SurfaceKind
from shruti.vault.narrative import build_recording_narrative


def test_narrative_includes_recording_header_and_beat_transcripts():
    rec = Recording(id="r" * 64, slug="physics_01", source_uri="gs://x",
                     duration_s=120.0, fps=30.0, surface_kind=SurfaceKind.SLIDES,
                     subject="Physics", grade=10, chapter="Projectile Motion")
    beats = [
        Beat(id="b1", recording_id=rec.id, idx=0, start_s=0.0, end_s=10.0,
             kind="explain", transcript="Today we cover projectile motion."),
        Beat(id="b2", recording_id=rec.id, idx=1, start_s=10.0, end_s=20.0,
             kind="derive", transcript="Deriving the range formula."),
    ]
    narrative = build_recording_narrative(rec, beats, board_states=[])
    assert "physics_01" in narrative
    assert "Physics" in narrative and "10" in narrative and "Projectile Motion" in narrative
    assert "Today we cover projectile motion." in narrative
    assert "Deriving the range formula." in narrative
    # Beats appear in chronological order
    assert narrative.index("Today we cover") < narrative.index("Deriving the range")


def test_narrative_interleaves_board_content_when_present():
    rec = Recording(id="r" * 64, slug="physics_01", source_uri="gs://x",
                     duration_s=60.0, fps=30.0, surface_kind=SurfaceKind.SLIDES)
    beats = [
        Beat(id="b1", recording_id=rec.id, idx=0, start_s=0.0, end_s=10.0,
             kind="explain", transcript="Here's the formula.", board_state_id="bs1"),
    ]
    board_states = [
        BoardState(id="bs1", recording_id=rec.id, idx=0, valid_from_s=0.0, valid_to_s=10.0,
                    composited_uri="gs://x", ended_by="shot_cut",
                    content=BoardContent(regions=[
                        Region(id="r1", bbox=(0, 0, 0.1, 0.1), kind="equation", latex="R = ut"),
                    ])),
    ]
    narrative = build_recording_narrative(rec, beats, board_states)
    assert "R = ut" in narrative
    assert narrative.index("Here's the formula.") < narrative.index("R = ut")


def test_narrative_includes_each_beats_citation():
    rec = Recording(id="r" * 64, slug="physics_01", source_uri="gs://x",
                     duration_s=60.0, fps=30.0, surface_kind=SurfaceKind.SLIDES)
    beats = [
        Beat(id="b1", recording_id=rec.id, idx=0, start_s=65.0, end_s=70.0,
             kind="explain", transcript="x"),
    ]
    narrative = build_recording_narrative(rec, beats, board_states=[])
    assert "shruti:physics_01 @1:05" in narrative
