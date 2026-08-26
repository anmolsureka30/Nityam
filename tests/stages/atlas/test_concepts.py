import json
from shruti.stages.atlas.concepts import mine_concepts
from shruti.contracts.beat import Beat
from shruti.contracts.board import BoardContent, BoardState, Region


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeClient:
    def __init__(self, payload):
        self._payload = payload

    class _Models:
        def __init__(self, outer):
            self._outer = outer

        def generate_content(self, model, contents, config=None):
            return FakeResponse(json.dumps(self._outer._payload))

    @property
    def models(self):
        return FakeClient._Models(self)


def test_mine_concepts_parses_taught_in_refs():
    payload = [{"canonical_name": "completing the square", "aliases": [],
                "taught_in_beat_ids": ["b1"]}]
    client = FakeClient(payload)
    beats = [Beat(id="b1", recording_id="r1", idx=0, start_s=0.0, end_s=5.0,
                  kind="derive", transcript="we complete the square by...")]
    concepts = mine_concepts(client, beats)
    assert concepts[0].canonical_name == "completing the square"
    assert concepts[0].taught_in[0].beat_id == "b1"
    assert concepts[0].taught_in[0].relation == "taught_in"


def test_mine_concepts_captures_definition_when_the_model_returns_one():
    payload = [{"canonical_name": "completing the square", "aliases": [],
                "taught_in_beat_ids": ["b1"],
                "definition": "Rewriting a quadratic as a squared binomial plus a constant."}]
    client = FakeClient(payload)
    beats = [Beat(id="b1", recording_id="r1", idx=0, start_s=0.0, end_s=5.0,
                  kind="derive", transcript="we complete the square by...")]
    concepts = mine_concepts(client, beats)
    assert concepts[0].definition == "Rewriting a quadratic as a squared binomial plus a constant."


def test_mine_concepts_includes_board_content_in_the_prompt_when_given():
    captured_contents = []

    class CapturingClient(FakeClient):
        class _Models(FakeClient._Models):
            def generate_content(self, model, contents, config=None):
                captured_contents.append(contents)
                return super().generate_content(model, contents, config)

        @property
        def models(self):
            return CapturingClient._Models(self)

    payload = [{"canonical_name": "range formula", "aliases": [],
                "taught_in_beat_ids": ["b1"], "definition": "d"}]
    client = CapturingClient(payload)
    beats = [Beat(id="b1", recording_id="r1", idx=0, start_s=0.0, end_s=5.0,
                  kind="derive", transcript="here's the range formula", board_state_id="bs1")]
    board_states = [
        BoardState(id="bs1", recording_id="r1", idx=0, valid_from_s=0.0, valid_to_s=5.0,
                    composited_uri="gs://x", ended_by="shot_cut",
                    content=BoardContent(regions=[
                        Region(id="r1", bbox=(0, 0, 0.1, 0.1), kind="equation", latex="R = ut"),
                    ])),
    ]
    mine_concepts(client, beats, board_states=board_states)
    assert any("R = ut" in str(c) for c in captured_contents)
