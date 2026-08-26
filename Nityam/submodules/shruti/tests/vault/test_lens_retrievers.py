import pytest
from shruti.contracts.recording import Recording, SurfaceKind
from shruti.contracts.beat import Beat
from shruti.contracts.atlas import Concept, Edge, BeatRef
from shruti.vault.reel import write_recording, write_beats
from shruti.vault.atlas_store import write_concepts, write_edges
from shruti.lens.retrievers import graph_traverse, timeline_lookup


@pytest.mark.asyncio
async def test_graph_traverse_follows_requires_chain(db_conn):
    rec = Recording(id="r_lens_1", source_uri="gs://x", duration_s=10.0, fps=30.0,
                     surface_kind=SurfaceKind.BLACKBOARD)
    await write_recording(db_conn, rec)
    beat = Beat(id="b_lens_1", recording_id=rec.id, idx=0, start_s=0.0, end_s=1.0,
                kind="explain", transcript="x")
    await write_beats(db_conn, [beat])
    concepts = [
        Concept(id="quadratic_formula", canonical_name="quadratic formula",
                taught_in=[BeatRef(beat_id=beat.id, relation="taught_in")]),
        Concept(id="completing_the_square", canonical_name="completing the square",
                taught_in=[BeatRef(beat_id=beat.id, relation="taught_in")]),
        Concept(id="factoring", canonical_name="factoring",
                taught_in=[BeatRef(beat_id=beat.id, relation="taught_in")]),
    ]
    await write_concepts(db_conn, concepts)
    edges = [
        Edge(id="e1", from_concept="quadratic_formula", to_concept="completing_the_square",
             edge_type="REQUIRES", evidence=[BeatRef(beat_id=beat.id, relation="evidence_for")]),
        Edge(id="e2", from_concept="completing_the_square", to_concept="factoring",
             edge_type="REQUIRES", evidence=[BeatRef(beat_id=beat.id, relation="evidence_for")]),
    ]
    await write_edges(db_conn, edges)

    result = await graph_traverse(db_conn, "quadratic_formula", "REQUIRES", depth=2)
    depth_by_id = {r["concept_id"]: r["depth"] for r in result}
    assert depth_by_id["completing_the_square"] == 1
    assert depth_by_id["factoring"] == 2


@pytest.mark.asyncio
async def test_timeline_lookup_returns_beats_for_concept(db_conn):
    rec = Recording(id="r_lens_2", source_uri="gs://x", duration_s=10.0, fps=30.0,
                     surface_kind=SurfaceKind.BLACKBOARD)
    await write_recording(db_conn, rec)
    beat = Beat(id="b_lens_2", recording_id=rec.id, idx=0, start_s=3.0, end_s=8.0,
                kind="derive", transcript="here is completing the square")
    await write_beats(db_conn, [beat])
    concept = Concept(id="cts_lens", canonical_name="completing the square",
                       taught_in=[BeatRef(beat_id=beat.id, relation="taught_in")])
    await write_concepts(db_conn, [concept])

    beats = await timeline_lookup(db_conn, "cts_lens", recording_ids=[rec.id])
    assert len(beats) == 1
    assert beats[0].id == beat.id
