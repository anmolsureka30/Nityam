import pytest
from shruti.contracts.recording import Recording, SurfaceKind
from shruti.contracts.beat import Beat
from shruti.contracts.atlas import Concept, BeatRef
from shruti.vault.reel import write_recording, write_beats
from shruti.vault.atlas_store import write_concepts
from evals.e4_provenance_invariant import e4_check


@pytest.mark.asyncio
async def test_e4_check_passes_when_every_concept_has_a_beat_ref(db_conn):
    rec = Recording(id="r_e4_1", source_uri="gs://x", duration_s=10.0, fps=30.0,
                     surface_kind=SurfaceKind.BLACKBOARD)
    await write_recording(db_conn, rec)
    beat = Beat(id="b_e4_1", recording_id=rec.id, idx=0, start_s=0.0, end_s=1.0,
                kind="explain", transcript="x")
    await write_beats(db_conn, [beat])
    concept = Concept(id="c_e4_1", canonical_name="ok concept",
                       taught_in=[BeatRef(beat_id=beat.id, relation="taught_in")])
    await write_concepts(db_conn, [concept])
    await e4_check(db_conn)  # must not raise


@pytest.mark.asyncio
async def test_e4_check_raises_on_orphan_concept(db_conn):
    await db_conn.execute(
        "INSERT INTO concept (id, canonical_name) VALUES ('c_e4_bad', 'orphan')"
    )
    with pytest.raises(AssertionError):
        await e4_check(db_conn)
