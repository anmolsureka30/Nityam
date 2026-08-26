_RRF_K = 60  # standard reciprocal-rank-fusion damping constant


def reciprocal_rank_fusion(*ranked_id_lists: list[str], k: int = _RRF_K) -> list[tuple[str, float]]:
    """score(item) = sum over lists it appears in of 1 / (k + rank_in_that_list).
    An item near the top of several lists outranks one that's #1 in only one —
    this is the standard RRF formula, not a bespoke weighting."""
    scores: dict[str, float] = {}
    for ranked_ids in ranked_id_lists:
        for rank, item_id in enumerate(ranked_ids, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)


async def related_concepts(conn, concept_id: str, query_vec: list[float], k: int = 8) -> list[dict]:
    """The dual-index retrieval SMRITI's grounding needs: graph structure
    (REQUIRES prerequisites) fused with semantic similarity, so a query
    doesn't have to choose one retrieval mode over the other."""
    from shruti.lens.retrievers import graph_traverse
    from shruti.vault.index import similarity_search

    graph_hits = await graph_traverse(conn, concept_id, "REQUIRES", depth=2)
    graph_ids = [h["concept_id"] for h in graph_hits]
    semantic_hits = await similarity_search(conn, query_vec, "concept", k=k)
    semantic_ids = [h["ref_id"] for h in semantic_hits]
    fused = reciprocal_rank_fusion(graph_ids, semantic_ids)
    return [{"concept_id": item_id, "score": score} for item_id, score in fused[:k]]
