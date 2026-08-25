import json
from shruti.stages.atlas.concepts import mine_concepts
from shruti.contracts.beat import Beat


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
