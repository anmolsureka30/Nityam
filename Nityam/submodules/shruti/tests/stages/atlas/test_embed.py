import pytest
from shruti.contracts.atlas import Concept, Misconception
from shruti.stages.atlas.embed import embed_concepts, embed_misconceptions
from shruti.vault.index import similarity_search


class _FakeEmbedding:
    def __init__(self, values):
        self.values = values


class _FakeEmbedResponse:
    def __init__(self, values):
        self.embeddings = [_FakeEmbedding(values)]


class FakeEmbedClient:
    """Deterministic: returns a vector derived from the text's length, so
    two different texts get two different (but reproducible) embeddings."""

    class _Models:
        async def embed_content(self, model: str, contents: str, config=None):
            seed = float(len(contents) % 7 + 1)
            return _FakeEmbedResponse([seed] * 3072)

    def __init__(self):
        self.aio = type("Aio", (), {"models": self._Models()})()


@pytest.mark.asyncio
async def test_embed_concepts_writes_a_retrievable_embedding(db_conn):
    concept = Concept(id="c_embed_1", canonical_name="projectile range",
                       definition="the horizontal distance a projectile travels")
    await embed_concepts(FakeEmbedClient(), db_conn, [concept])
    results = await similarity_search(
        db_conn, [float(len(concept.definition) % 7 + 1)] * 3072, "concept", k=1
    )
    assert results[0]["ref_id"] == "c_embed_1"
    assert results[0]["text"] == concept.definition


@pytest.mark.asyncio
async def test_embed_concepts_falls_back_to_canonical_name_when_no_definition(db_conn):
    concept = Concept(id="c_embed_no_def", canonical_name="projectile motion", definition=None)
    await embed_concepts(FakeEmbedClient(), db_conn, [concept])
    results = await similarity_search(
        db_conn, [float(len(concept.canonical_name) % 7 + 1)] * 3072, "concept", k=1
    )
    assert results[0]["ref_id"] == "c_embed_no_def"
    assert results[0]["text"] == concept.canonical_name


@pytest.mark.asyncio
async def test_embed_misconceptions_writes_a_retrievable_embedding(db_conn):
    misconception = Misconception(
        id="m_embed_1", concept_id="c_embed_1",
        statement="treats (a+b)^2 as a^2+b^2",
        correct_understanding="(a+b)^2 = a^2 + 2ab + b^2",
        pre_empted_at_beat="b_unused",
    )
    await embed_misconceptions(FakeEmbedClient(), db_conn, [misconception])
    text = f"{misconception.statement} {misconception.correct_understanding}"
    results = await similarity_search(
        db_conn, [float(len(text) % 7 + 1)] * 3072, "misconception", k=1
    )
    assert results[0]["ref_id"] == "m_embed_1"
