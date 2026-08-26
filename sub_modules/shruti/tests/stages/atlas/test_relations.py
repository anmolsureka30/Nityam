import json
from shruti.stages.atlas.relations import extract_relations, filter_valid_edges
from shruti.contracts.atlas import Concept, Edge, BeatRef
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


def test_extract_relations_resolves_canonical_names_to_concept_ids():
    # The model is prompted with, and returns, human-readable
    # canonical_name values (see _RELATIONS_PROMPT) — not the slugified
    # concept.id used as the FK target in concept_edge.
    payload = [{"from_concept": "factoring", "to_concept": "completing the square",
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
    assert len(edges) == 1
    assert edges[0].from_concept == "factoring"
    assert edges[0].to_concept == "completing_the_square"
    assert edges[0].edge_type == "REQUIRES"
    assert edges[0].evidence[0].beat_id == "b1"
    assert edges[0].evidence[0].relation == "evidence_for"


def test_extract_relations_is_case_insensitive_on_name_matching():
    payload = [{"from_concept": "Factoring", "to_concept": "Completing The Square",
                "edge_type": "REQUIRES", "evidence_beat_ids": []}]
    client = FakeClient(payload)
    concepts = [
        Concept(id="factoring", canonical_name="factoring"),
        Concept(id="completing_the_square", canonical_name="completing the square"),
    ]
    edges = extract_relations(client, concepts, [])
    assert edges[0].from_concept == "factoring"
    assert edges[0].to_concept == "completing_the_square"


def test_extract_relations_skips_edges_naming_an_unknown_concept():
    # The model can hallucinate a name that isn't in the concepts it was
    # given — skip that edge rather than write a dangling reference.
    payload = [{"from_concept": "factoring", "to_concept": "a concept never mined",
                "edge_type": "REQUIRES", "evidence_beat_ids": []}]
    client = FakeClient(payload)
    concepts = [Concept(id="factoring", canonical_name="factoring")]
    edges = extract_relations(client, concepts, [])
    assert edges == []


def test_filter_valid_edges_drops_edges_citing_an_unknown_beat_id():
    edges = [
        Edge(id="e1", from_concept="a", to_concept="b", edge_type="REQUIRES",
             evidence=[BeatRef(beat_id="b_real", relation="evidence_for")]),
        Edge(id="e2", from_concept="a", to_concept="b", edge_type="REQUIRES",
             evidence=[BeatRef(beat_id="b_hallucinated", relation="evidence_for")]),
    ]
    kept = filter_valid_edges(edges, concept_ids={"a", "b"}, beat_ids={"b_real"})
    assert [e.id for e in kept] == ["e1"]


def test_filter_valid_edges_drops_edges_with_no_evidence_or_unknown_concept():
    edges = [
        Edge(id="e1", from_concept="a", to_concept="unknown", edge_type="REQUIRES",
             evidence=[BeatRef(beat_id="b1", relation="evidence_for")]),
        Edge(id="e2", from_concept="a", to_concept="b", edge_type="REQUIRES", evidence=[]),
    ]
    kept = filter_valid_edges(edges, concept_ids={"a", "b"}, beat_ids={"b1"})
    assert kept == []
