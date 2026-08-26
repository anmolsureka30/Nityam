import pytest
from shruti.vault.index import write_embedding, similarity_search


@pytest.mark.asyncio
async def test_similarity_search_orders_by_distance(db_conn):
    close_vec = [1.0] * 3072
    far_vec = [0.0] * 3072
    await write_embedding(db_conn, "concept", "c1", None, close_vec, "completing the square")
    await write_embedding(db_conn, "concept", "c2", None, far_vec, "unrelated concept")
    results = await similarity_search(db_conn, close_vec, "concept", k=2)
    assert results[0]["ref_id"] == "c1"
