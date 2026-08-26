from shruti.contracts.beat import Beat


async def graph_traverse(conn, concept_id: str, edge_type: str, depth: int = 2) -> list[dict]:
    rows = await conn.fetch(
        """WITH RECURSIVE prereqs AS (
               SELECT to_concept AS concept_id, 1 AS depth
               FROM concept_edge WHERE from_concept=$1 AND edge_type=$2
               UNION ALL
               SELECT ce.to_concept, p.depth + 1
               FROM concept_edge ce
               JOIN prereqs p ON ce.from_concept = p.concept_id
               WHERE ce.edge_type=$2 AND p.depth < $3
           )
           SELECT concept_id, MIN(depth) AS depth FROM prereqs
           GROUP BY concept_id ORDER BY depth""",
        concept_id, edge_type, depth,
    )
    return [{"concept_id": r["concept_id"], "depth": r["depth"]} for r in rows]


async def timeline_lookup(conn, concept_id: str, recording_ids: list[str] | None = None) -> list[Beat]:
    query = """SELECT b.id, b.recording_id, b.idx, b.start_s, b.end_s, b.kind,
                      b.board_state_id, b.salience, b.transcript
               FROM beat b
               JOIN beat_ref r ON r.beat_id = b.id
               WHERE r.subject_kind='concept' AND r.subject_id=$1"""
    params = [concept_id]
    if recording_ids:
        query += " AND b.recording_id = ANY($2)"
        params.append(recording_ids)
    query += " ORDER BY b.start_s"
    rows = await conn.fetch(query, *params)
    return [
        Beat(id=r["id"], recording_id=r["recording_id"], idx=r["idx"], start_s=r["start_s"],
             end_s=r["end_s"], kind=r["kind"], board_state_id=r["board_state_id"],
             salience=r["salience"], transcript=r["transcript"])
        for r in rows
    ]
