import pytest
from shruti.contracts.recording import Recording, SurfaceKind
from shruti.contracts.beat import Beat
from shruti.contracts.board import BoardState
from shruti.contracts.atlas import Concept, Misconception, BeatRef
from shruti.vault.reel import write_recording, write_beats
from shruti.vault.ledger import write_board_state
from shruti.vault.atlas_store import write_concepts, write_misconceptions
from shruti.lens.adk_tools import _build_lesson_functions, build_lesson_tools


@pytest.mark.asyncio
async def test_recall_lesson_returns_teacher_words_and_board_image(db_conn):
    rec = Recording(id="r_tool_1", source_uri="gs://x", duration_s=10.0, fps=30.0,
                     surface_kind=SurfaceKind.BLACKBOARD)
    await write_recording(db_conn, rec)
    beat = Beat(id="b_tool_1", recording_id=rec.id, idx=0, start_s=2.0, end_s=6.0,
                kind="derive", transcript="sir taught completing the square here")
    await write_beats(db_conn, [beat])
    concept = Concept(id="cts_tool", canonical_name="completing the square",
                       taught_in=[BeatRef(beat_id=beat.id, relation="taught_in")])
    await write_concepts(db_conn, [concept])
    bs = BoardState(id="bs_tool_1", recording_id=rec.id, idx=0, valid_from_s=0.0,
                     valid_to_s=10.0, composited_uri="gs://x/bs.png", ended_by="erase")
    await write_board_state(db_conn, bs)

    tools = _build_lesson_functions(db_conn)
    result = await tools["recall_lesson"]("cts_tool", [rec.id])
    assert result["found"] is True
    assert "completing the square" in result["teacher_words"]
    assert result["board_image_uri"] == "gs://x/bs.png"


@pytest.mark.asyncio
async def test_known_misconceptions_returns_teacher_phrasing(db_conn):
    rec = Recording(id="r_tool_2", source_uri="gs://x", duration_s=10.0, fps=30.0,
                     surface_kind=SurfaceKind.BLACKBOARD)
    await write_recording(db_conn, rec)
    beat = Beat(id="b_tool_2", recording_id=rec.id, idx=0, start_s=0.0, end_s=1.0,
                kind="explain", transcript="x")
    await write_beats(db_conn, [beat])
    concept = Concept(id="cts_tool2", canonical_name="completing the square")
    await write_concepts(db_conn, [concept])
    misconception = Misconception(id="m_tool_1", concept_id="cts_tool2",
                                   statement="treats (a+b)^2 as a^2+b^2",
                                   teacher_phrasing="yeh sabse common galti hai",
                                   correct_understanding="(a+b)^2 = a^2+2ab+b^2",
                                   pre_empted_at_beat=beat.id)
    await write_misconceptions(db_conn, [misconception])

    tools = _build_lesson_functions(db_conn)
    result = await tools["known_misconceptions"]("cts_tool2")
    assert result[0]["teacher_phrasing"] == "yeh sabse common galti hai"


@pytest.mark.asyncio
async def test_build_lesson_tools_returns_four_tools(db_conn):
    tools = build_lesson_tools(db_conn)
    assert len(tools) == 4
