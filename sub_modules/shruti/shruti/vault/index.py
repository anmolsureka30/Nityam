def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(str(float(x)) for x in vec) + "]"


async def write_embedding(conn, kind: str, ref_id: str, recording_id: str | None,
                           vec: list[float], text: str) -> None:
    await conn.execute(
        """INSERT INTO embedding (id, kind, ref_id, recording_id, vec, text)
           VALUES ($1,$2,$3,$4,$5::vector,$6)
           ON CONFLICT (id) DO NOTHING""",
        f"{kind}:{ref_id}", kind, ref_id, recording_id, _vec_literal(vec), text,
    )


async def similarity_search(conn, query_vec: list[float], kind: str, k: int = 8) -> list[dict]:
    rows = await conn.fetch(
        """SELECT ref_id, text, vec <=> $1::vector AS distance FROM embedding
           WHERE kind=$2 ORDER BY vec <=> $1::vector LIMIT $3""",
        _vec_literal(query_vec), kind, k,
    )
    return [{"ref_id": r["ref_id"], "text": r["text"], "distance": r["distance"]} for r in rows]
