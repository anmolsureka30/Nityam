from shruti.contracts.beat import Beat
from shruti.contracts.board import BoardContent, BoardState, Region
from shruti.stages.weave.render import render_board_content_for_beat


def test_renders_readable_regions_from_the_linked_board_state():
    beat = Beat(id="b1", recording_id="r1", idx=0, start_s=0.0, end_s=10.0,
                kind="explain", transcript="x", board_state_id="bs1")
    board_states = [
        BoardState(
            id="bs1", recording_id="r1", idx=0, valid_from_s=0.0, valid_to_s=10.0,
            composited_uri="gs://x", ended_by="shot_cut",
            content=BoardContent(regions=[
                Region(id="r1", bbox=(0, 0, 0.1, 0.1), kind="text", plain_text="Horizontal Range"),
                Region(id="r2", bbox=(0.1, 0, 0.1, 0.1), kind="equation", latex="R = u \\cos\\theta \\times t"),
                Region(id="r3", bbox=(0.2, 0, 0.1, 0.1), kind="unreadable"),
            ]),
        ),
    ]
    rendered = render_board_content_for_beat(beat, board_states)
    assert "Horizontal Range" in rendered
    assert "R = u \\cos\\theta \\times t" in rendered
    assert "unreadable" not in rendered.lower()


def test_empty_string_when_beat_has_no_linked_board_state():
    beat = Beat(id="b1", recording_id="r1", idx=0, start_s=0.0, end_s=10.0,
                kind="explain", transcript="x", board_state_id=None)
    assert render_board_content_for_beat(beat, board_states=[]) == ""


def test_empty_string_when_linked_board_state_has_no_content():
    beat = Beat(id="b1", recording_id="r1", idx=0, start_s=0.0, end_s=10.0,
                kind="explain", transcript="x", board_state_id="bs1")
    board_states = [
        BoardState(id="bs1", recording_id="r1", idx=0, valid_from_s=0.0, valid_to_s=10.0,
                    composited_uri="gs://x", ended_by="shot_cut", content=None),
    ]
    assert render_board_content_for_beat(beat, board_states) == ""
