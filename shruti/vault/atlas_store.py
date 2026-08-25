from shruti.contracts.atlas import Concept, Edge, Misconception


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


async def check_provenance_invariant(conn) -> list[str]:
    violations = []
    for table, kind in (("concept", "concept"), ("concept_edge", "edge"),
                         ("misconception", "misconception")):
        rows = await conn.fetch(
            f"""SELECT t.id FROM {table} t
                LEFT JOIN beat_ref r ON r.subject_kind=$1 AND r.subject_id=t.id
                WHERE r.id IS NULL""",
            kind,
        )
        violations += [f"{kind} {r['id']} has no beat_ref" for r in rows]
    return violations
