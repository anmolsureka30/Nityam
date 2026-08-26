from shruti.contracts.atlas import Concept, Edge, Misconception


class ProvenanceViolation(Exception):
    """A Concept/Edge/Misconception was written with no beat_ref pointing at
    it. This must fail loudly and immediately — see check_provenance_invariant's
    own framing: the correctness assertion, not a quality metric.

    Note for callers: this function does not manage its own transaction.
    If you need the write itself rolled back on violation (not just detected),
    wrap the call to write_concepts/write_edges/write_misconceptions in your
    own `async with conn.transaction():` block."""


async def write_concepts(conn, concepts: list[Concept]) -> None:
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
    violations = await check_provenance_invariant(conn, only={"concept": [c.id for c in concepts]})
    if violations:
        raise ProvenanceViolation(violations)


async def write_edges(conn, edges: list[Edge]) -> None:
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
    violations = await check_provenance_invariant(conn, only={"edge": [e.id for e in edges]})
    if violations:
        raise ProvenanceViolation(violations)


async def write_misconceptions(conn, misconceptions: list[Misconception]) -> None:
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
    violations = await check_provenance_invariant(
        conn, only={"misconception": [m.id for m in misconceptions]}
    )
    if violations:
        raise ProvenanceViolation(violations)


async def check_provenance_invariant(conn, *, only: dict[str, list[str]] | None = None) -> list[str]:
    """With `only=None` (the original behavior, still used by the CLI's
    provenance-check command and the E4 CI gate): checks every row in the
    database. With `only={"concept": [...]}` etc.: checks just those ids —
    used by the writers above so a single insert doesn't pay the cost of a
    full-table scan."""
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
