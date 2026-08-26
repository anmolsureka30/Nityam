import pytest
from shruti.contracts.recording import Recording, SurfaceKind
from shruti.contracts.beat import Beat
from shruti.contracts.atlas import Concept, BeatRef
from shruti.vault.reel import write_recording, write_beats
from shruti.vault.atlas_store import write_concepts, check_provenance_invariant


@pytest.mark.asyncio
async def test_provenance_invariant_flags_orphan_concept_and_clears_on_proper_write(db_conn):
    rec = Recording(id="r_test_3", source_uri="gs://x", duration_s=10.0, fps=30.0,
                     surface_kind=SurfaceKind.BLACKBOARD)
    await write_recording(db_conn, rec)
    beat = Beat(id="b_test_3", recording_id=rec.id, idx=0, start_s=0.0, end_s=1.0,
                kind="explain", transcript="x")
    await write_beats(db_conn, [beat])

    # Simulates a bug: a concept inserted directly, bypassing write_concepts's
    # beat_ref insert — this is exactly the case the invariant must catch.
    await db_conn.execute(
        "INSERT INTO concept (id, canonical_name) VALUES ('c_bad', 'orphan concept')"
    )
    violations = await check_provenance_invariant(db_conn)
    assert any("c_bad" in v for v in violations)

    good = Concept(id="c_good", canonical_name="good concept",
                    taught_in=[BeatRef(beat_id=beat.id, relation="taught_in")])
    await write_concepts(db_conn, [good])
    violations_after = await check_provenance_invariant(db_conn)
    assert not any("c_good" in v for v in violations_after)


@pytest.mark.asyncio
async def test_write_concepts_raises_on_a_concept_with_no_evidence(db_conn):
    from shruti.vault.atlas_store import ProvenanceViolation
    bad = Concept(id="c_no_evidence", canonical_name="no evidence concept", taught_in=[])
    with pytest.raises(ProvenanceViolation):
        await write_concepts(db_conn, [bad])


@pytest.mark.asyncio
async def test_write_concepts_with_evidence_does_not_raise(db_conn):
    rec = Recording(id="r_test_4", source_uri="gs://x", duration_s=10.0, fps=30.0,
                     surface_kind=SurfaceKind.BLACKBOARD)
    await write_recording(db_conn, rec)
    beat = Beat(id="b_test_4", recording_id=rec.id, idx=0, start_s=0.0, end_s=1.0,
                kind="explain", transcript="x")
    await write_beats(db_conn, [beat])
    good = Concept(id="c_has_evidence", canonical_name="has evidence concept",
                    taught_in=[BeatRef(beat_id=beat.id, relation="taught_in")])
    await write_concepts(db_conn, [good])  # must not raise
