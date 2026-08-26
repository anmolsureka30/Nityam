from shruti.vault.atlas_store import check_provenance_invariant


async def e4_check(conn) -> None:
    """The correctness assertion, not a quality metric — this should fail the
    build. 100% of Concept/Edge/Misconception rows must resolve >=1 BeatRef."""
    violations = await check_provenance_invariant(conn)
    assert not violations, (
        f"Provenance invariant violated — {len(violations)} row(s) have no "
        f"BeatRef: {violations}"
    )
