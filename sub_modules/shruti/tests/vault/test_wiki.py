from shruti.contracts.atlas import BeatRef, Concept, Misconception
from shruti.contracts.beat import Beat
from shruti.contracts.board import BoardContent, BoardState, Region
from shruti.vault.wiki import write_concept_wiki_page


def test_creates_a_new_page_with_header_and_first_entry(tmp_path):
    concept = Concept(id="range_formula", canonical_name="Range Formula",
                       subject="Physics", grade=10, chapter="Projectile Motion",
                       definition="How far a projectile travels horizontally.",
                       taught_in=[BeatRef(beat_id="b1", relation="taught_in")])
    beats = [Beat(id="b1", recording_id="r1", idx=0, start_s=65.0, end_s=70.0,
                  kind="derive", transcript="x")]
    write_concept_wiki_page(tmp_path, concept, beats, board_states=[], recording_slug="physics_01")
    page = (tmp_path / "range_formula.md").read_text()
    assert "# Range Formula" in page
    assert "range_formula" in page
    assert "Physics" in page and "10" in page and "Projectile Motion" in page
    assert "shruti:physics_01 @1:05" in page
    assert "How far a projectile travels horizontally." in page


def test_appending_a_new_citation_does_not_erase_the_first_entry(tmp_path):
    concept = Concept(id="range_formula", canonical_name="Range Formula",
                       definition="def 1",
                       taught_in=[BeatRef(beat_id="b1", relation="taught_in")])
    beats = [Beat(id="b1", recording_id="r1", idx=0, start_s=0.0, end_s=5.0,
                  kind="derive", transcript="x")]
    write_concept_wiki_page(tmp_path, concept, beats, board_states=[], recording_slug="physics_01")

    concept_2 = concept.model_copy(update={
        "taught_in": [BeatRef(beat_id="b2", relation="taught_in")],
        "definition": "def 2",
    })
    beats_2 = [Beat(id="b2", recording_id="r2", idx=0, start_s=30.0, end_s=35.0,
                    kind="derive", transcript="y")]
    write_concept_wiki_page(tmp_path, concept_2, beats_2, board_states=[], recording_slug="physics_02")

    page = (tmp_path / "range_formula.md").read_text()
    assert "shruti:physics_01 @0:00" in page
    assert "shruti:physics_02 @0:30" in page
    assert "def 1" in page
    assert "def 2" in page


def test_re_adding_the_same_citation_does_not_duplicate_the_entry(tmp_path):
    concept = Concept(id="range_formula", canonical_name="Range Formula", definition="def 1",
                       taught_in=[BeatRef(beat_id="b1", relation="taught_in")])
    beats = [Beat(id="b1", recording_id="r1", idx=0, start_s=0.0, end_s=5.0,
                  kind="derive", transcript="x")]
    write_concept_wiki_page(tmp_path, concept, beats, board_states=[], recording_slug="physics_01")
    write_concept_wiki_page(tmp_path, concept, beats, board_states=[], recording_slug="physics_01")
    page = (tmp_path / "range_formula.md").read_text()
    assert page.count("shruti:physics_01 @0:00") == 1


def test_includes_board_content_for_the_specific_citation(tmp_path):
    concept = Concept(id="range_formula", canonical_name="Range Formula", definition="def",
                       taught_in=[BeatRef(beat_id="b1", relation="taught_in")])
    beats = [Beat(id="b1", recording_id="r1", idx=0, start_s=0.0, end_s=5.0,
                  kind="derive", transcript="x", board_state_id="bs1")]
    board_states = [
        BoardState(id="bs1", recording_id="r1", idx=0, valid_from_s=0.0, valid_to_s=5.0,
                    composited_uri="gs://x", ended_by="shot_cut",
                    content=BoardContent(regions=[
                        Region(id="r1", bbox=(0, 0, 0.1, 0.1), kind="equation", latex="R = ut"),
                    ])),
    ]
    write_concept_wiki_page(tmp_path, concept, beats, board_states, recording_slug="physics_01")
    page = (tmp_path / "range_formula.md").read_text()
    assert "R = ut" in page


def test_folds_a_misconception_into_its_taught_in_beat_with_verbatim_phrasing(tmp_path):
    concept = Concept(id="range_formula", canonical_name="Range Formula", definition="def",
                       taught_in=[BeatRef(beat_id="b1", relation="taught_in")])
    beats = [Beat(id="b1", recording_id="r1", idx=0, start_s=0.0, end_s=5.0,
                  kind="derive", transcript="x")]
    misconception = Misconception(
        id="m1", concept_id="range_formula",
        statement="Students often use absolute velocity instead of relative velocity.",
        teacher_phrasing="galti se log absolute velocity le lete hain, relative nahi",
        correct_understanding="Use velocity relative to the moving frame, not ground velocity.",
        pre_empted_at_beat="b1",
    )
    write_concept_wiki_page(tmp_path, concept, beats, board_states=[],
                             recording_slug="physics_01", misconceptions=[misconception])
    page = (tmp_path / "range_formula.md").read_text()
    assert page.count("shruti:physics_01 @0:00") == 1  # folded into the same entry, not duplicated
    assert '"galti se log absolute velocity le lete hain, relative nahi"' in page
    assert "Use velocity relative to the moving frame, not ground velocity." in page
    assert "def" in page  # the definition is still there alongside the misconception


def test_misconception_at_a_different_beat_gets_its_own_entry(tmp_path):
    concept = Concept(id="range_formula", canonical_name="Range Formula", definition="def",
                       taught_in=[BeatRef(beat_id="b1", relation="taught_in")])
    beats = [
        Beat(id="b1", recording_id="r1", idx=0, start_s=0.0, end_s=5.0, kind="derive", transcript="x"),
        Beat(id="b2", recording_id="r1", idx=1, start_s=40.0, end_s=45.0, kind="recap", transcript="y"),
    ]
    misconception = Misconception(
        id="m1", concept_id="range_formula", statement="s", teacher_phrasing="verbatim quote here",
        correct_understanding="c", pre_empted_at_beat="b2",
    )
    write_concept_wiki_page(tmp_path, concept, beats, board_states=[],
                             recording_slug="physics_01", misconceptions=[misconception])
    page = (tmp_path / "range_formula.md").read_text()
    assert "shruti:physics_01 @0:00" in page
    assert "shruti:physics_01 @0:40" in page
    assert '"verbatim quote here"' in page


def test_misconceptions_for_a_different_concept_are_not_included(tmp_path):
    concept = Concept(id="range_formula", canonical_name="Range Formula", definition="def",
                       taught_in=[BeatRef(beat_id="b1", relation="taught_in")])
    beats = [Beat(id="b1", recording_id="r1", idx=0, start_s=0.0, end_s=5.0,
                  kind="derive", transcript="x")]
    other_misconception = Misconception(
        id="m1", concept_id="a_different_concept", statement="s", teacher_phrasing="not this one",
        correct_understanding="c", pre_empted_at_beat="b1",
    )
    write_concept_wiki_page(tmp_path, concept, beats, board_states=[],
                             recording_slug="physics_01", misconceptions=[other_misconception])
    page = (tmp_path / "range_formula.md").read_text()
    assert "not this one" not in page
