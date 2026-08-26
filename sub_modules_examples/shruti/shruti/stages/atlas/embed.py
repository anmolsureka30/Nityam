from shruti.config import Models
from shruti.contracts.atlas import Concept, Misconception
from shruti.vault.index import write_embedding

# Verified against the installed google-genai==2.19.0 SDK: client.aio.models
# .embed_content(model=..., contents=str) is a real async method (both
# params are keyword-only) returning EmbedContentResponse(embeddings=
# list[ContentEmbedding]), and ContentEmbedding.values is a list[float].
# So response.embeddings[0].values below matches the real SDK shape, not
# just the FakeEmbedClient's.
#
# output_dimensionality is pinned to 3072 explicitly rather than relying on
# the model's default, to match the `vector(3072)` column in
# infra/migrations/004_index.sql — EmbedContentConfig.output_dimensionality
# is a real parameter on the installed SDK (see google/genai/types.py).
#
# Known follow-up: this issues one embed_content call per item and doesn't
# use the Batch API, despite Budget.use_batch_api defaulting to True
# (shruti/config.py) — batching the embedding path is not yet wired up.


async def embed_concepts(client, conn, concepts: list[Concept]) -> None:
    """Embeds each concept's definition (falling back to its canonical name
    if no definition was mined) and writes it into the vector index. Call
    this after write_concepts persists the same concepts to the graph —
    the two indexes (graph, semantic) are meant to be fused at query time
    (Task 6), not kept in sync automatically."""
    for c in concepts:
        text = c.definition or c.canonical_name
        response = await client.aio.models.embed_content(
            model=Models().embedder, contents=text,
            config={"output_dimensionality": 3072},
        )
        vec = response.embeddings[0].values
        await write_embedding(conn, "concept", c.id, None, vec, text)


async def embed_misconceptions(client, conn, misconceptions: list[Misconception]) -> None:
    for m in misconceptions:
        text = f"{m.statement} {m.correct_understanding}"
        response = await client.aio.models.embed_content(
            model=Models().embedder, contents=text,
            config={"output_dimensionality": 3072},
        )
        vec = response.embeddings[0].values
        await write_embedding(conn, "misconception", m.id, None, vec, text)
