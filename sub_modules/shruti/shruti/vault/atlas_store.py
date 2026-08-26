from shruti.contracts.atlas import Concept, Edge, Misconception


class ProvenanceViolation(Exception):
    """A Concept/Edge was about to be written with no beat_ref pointing at
    it. This must fail loudly and immediately — see check_provenance_invariant's
    own framing: the correctness assertion, not a quality metric."""


async def write_concepts(conn, concepts: list[Concept]) -> None:
    """Validates provenance BEFORE inserting anything: if any concept has no
    taught_in beat_ref, the whole batch is rejected and nothing is written.
    This makes the check all-or-nothing for the provenance case specifically.

    Note for callers: this function does not otherwise manage its own
    transaction. A mid-batch database error unrelated to provenance (e.g. a
    genuine FK violation on a beat_id that doesn't exist) can still leave a
    partial write behind. If you need the write itself rolled back on any
    failure, wrap the call in your own `async with conn.transaction():` block."""
    missing = [c.id for c in concepts if not c.taught_in]
    if missing:
        raise ProvenanceViolation([f"concept {cid} has no beat_ref" for cid in missing])
    for c in concepts:
        await conn.execute(
            """INSERT INTO concept (id, canonical_name, aliases, subject, grade, chapter,
                                     definition, atlas_version)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
               ON CONFLICT (id) DO NOTHING""",
            c.id, c.canonical_name, c.aliases, c.subject, c.grade, c.chapter,
            c.definition, c.atlas_version,
        )
        for ref in c.taught_in:
            await conn.execute(
                """INSERT INTO beat_ref (subject_kind, subject_id, beat_id, relation, atlas_version)
                   VALUES ('concept', $1, $2, $3, $4)""",
                c.id, ref.beat_id, ref.relation, c.atlas_version,
            )


async def write_edges(conn, edges: list[Edge]) -> None:
    """Validates provenance BEFORE inserting anything: if any edge has no
    evidence beat_ref, the whole batch is rejected and nothing is written.
    See write_concepts's docstring for the transaction caveat that still
    applies to non-provenance failures."""
    missing = [e.id for e in edges if not e.evidence]
    if missing:
        raise ProvenanceViolation([f"edge {eid} has no beat_ref" for eid in missing])
    for e in edges:
        await conn.execute(
            """INSERT INTO concept_edge (id, from_concept, to_concept, edge_type, weight,
                                          atlas_version)
               VALUES ($1,$2,$3,$4,$5,$6)
               ON CONFLICT (id) DO NOTHING""",
            e.id, e.from_concept, e.to_concept, e.edge_type, e.weight, e.atlas_version,
        )
        for ref in e.evidence:
            await conn.execute(
                """INSERT INTO beat_ref (subject_kind, subject_id, beat_id, relation, atlas_version)
                   VALUES ('edge', $1, $2, $3, $4)""",
                e.id, ref.beat_id, ref.relation, e.atlas_version,
            )


async def write_misconceptions(conn, misconceptions: list[Misconception]) -> None:
    """No provenance pre-check here, unlike write_concepts/write_edges: an
    orphan misconception is structurally impossible, not just checked-for.
    Misconception.pre_empted_at_beat is a required (non-optional) str, so
    every misconception always carries exactly one beat_ref candidate, and
    the beat_ref.beat_id REFERENCES beat(id) FK constraint means an invalid
    beat id fails the insert itself (asyncpg.exceptions.ForeignKeyViolationError)
    rather than silently landing as an orphan row. There is nothing left for
    a pre-insert check to catch. See write_concepts's docstring for the
    transaction caveat that still applies to non-provenance failures."""
    for m in misconceptions:
        await conn.execute(
            """INSERT INTO misconception (id, concept_id, statement, teacher_phrasing,
                                           correct_understanding, pre_empted_at_beat,
                                           board_region_id, atlas_version)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
               ON CONFLICT (id) DO NOTHING""",
            m.id, m.concept_id, m.statement, m.teacher_phrasing, m.correct_understanding,
            m.pre_empted_at_beat, m.board_region_id, m.atlas_version,
        )
        await conn.execute(
            """INSERT INTO beat_ref (subject_kind, subject_id, beat_id, relation, atlas_version)
               VALUES ('misconception', $1, $2, 'evidence_for', $3)""",
            m.id, m.pre_empted_at_beat, m.atlas_version,
        )


async def check_provenance_invariant(conn, *, only: dict[str, list[str]] | None = None) -> list[str]:
    """With `only=None` (the original behavior, still used by the CLI's
    provenance-check command and the E4 CI gate): checks every row in the
    database. With `only={"concept": [...]}` etc.: checks just those ids,
    without paying the cost of a full-table scan. The writers above no
    longer call this (they validate provenance before inserting instead —
    see their docstrings); the `only=` mode remains available for callers
    that want a scoped check after the fact."""
    violations = []
    for table, kind in (("concept", "concept"), ("concept_edge", "edge"),
                         ("misconception", "misconception")):
        if only is not None:
            ids = only.get(kind, [])
            if not ids:
                continue
            rows = await conn.fetch(
                f"""SELECT t.id FROM {table} t
                    LEFT JOIN beat_ref r ON r.subject_kind=$1 AND r.subject_id=t.id
                    WHERE r.id IS NULL AND t.id = ANY($2)""",
                kind, ids,
            )
        else:
            rows = await conn.fetch(
                f"""SELECT t.id FROM {table} t
                    LEFT JOIN beat_ref r ON r.subject_kind=$1 AND r.subject_id=t.id
                    WHERE r.id IS NULL""",
                kind,
            )
        violations += [f"{kind} {r['id']} has no beat_ref" for r in rows]
    return violations
