from shruti.contracts.atlas import Concept, BeatRef
from shruti.stages.atlas.canonicalize import canonicalize


def test_canonicalize_merges_near_duplicate_names():
    concepts = [
        Concept(id="c1", canonical_name="completing the square",
                taught_in=[BeatRef(beat_id="b1", relation="taught_in")]),
        Concept(id="c2", canonical_name="complete the square",
                taught_in=[BeatRef(beat_id="b2", relation="taught_in")]),
        Concept(id="c3", canonical_name="quadratic formula",
                taught_in=[BeatRef(beat_id="b3", relation="taught_in")]),
    ]
    merged = canonicalize(concepts, similarity_threshold=0.85)
    assert len(merged) == 2
    square_concept = next(c for c in merged if "square" in c.canonical_name)
    assert {ref.beat_id for ref in square_concept.taught_in} == {"b1", "b2"}
