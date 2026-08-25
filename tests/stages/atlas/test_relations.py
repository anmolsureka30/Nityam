import json
from shruti.stages.atlas.relations import extract_relations
from shruti.contracts.atlas import Concept, BeatRef
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


def test_extract_relations_builds_requires_edges():
    payload = [{"from_concept": "factoring", "to_concept": "completing_the_square",
                "edge_type": "REQUIRES", "evidence_beat_ids": ["b1"]}]
    client = FakeClient(payload)
    concepts = [
        Concept(id="factoring", canonical_name="factoring",
                taught_in=[BeatRef(beat_id="b0", relation="taught_in")]),
        Concept(id="completing_the_square", canonical_name="completing the square",
                taught_in=[BeatRef(beat_id="b1", relation="taught_in")]),
    ]
    beats = [Beat(id="b1", recording_id="r1", idx=1, start_s=5.0, end_s=10.0,
                  kind="derive", transcript="this needs factoring first")]
    edges = extract_relations(client, concepts, beats)
    assert edges[0].edge_type == "REQUIRES"
    assert edges[0].evidence[0].beat_id == "b1"
    assert edges[0].evidence[0].relation == "evidence_for"
