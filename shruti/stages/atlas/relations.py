import json
import uuid
from shruti.config import Models
from shruti.contracts.atlas import Concept, Edge, BeatRef
from shruti.contracts.beat import Beat

_RELATIONS_PROMPT = """Concepts taught in this lesson: {concepts}

Beats: {beats}

Identify edges between concepts. Edge types: REQUIRES (prerequisite),
PART_OF (sub-concept), EXEMPLIFIES (worked example -> concept),
CONTRASTS_WITH (commonly confused pair). Return a JSON array of
{{from_concept, to_concept, edge_type, evidence_beat_ids}}.
"""


def extract_relations(client, concepts: list[Concept], beats: list[Beat]) -> list[Edge]:
    concept_names = [c.canonical_name for c in concepts]
    beats_text = "\n".join(f"[{b.id}] {b.transcript}" for b in beats)
    response = client.models.generate_content(
        model=Models().reasoner,
        contents=[_RELATIONS_PROMPT.format(concepts=concept_names, beats=beats_text)],
        config={"response_mime_type": "application/json"},
    )
    rows = json.loads(response.text)
    # concept_edge.from_concept/to_concept are FKs into concept.id, which is
    # a slugified canonical_name (see concepts.py's mine_concepts) — but the
    # model is prompted with, and returns, human-readable canonical_name
    # values, not ids. Resolve by name (case-insensitive) rather than
    # assuming the model's returned string already matches the id; every
    # real run before this fix produced "Relations extracted: 0" for
    # exactly this reason (ingest.py's own valid_ids filter silently
    # dropped every edge since a raw name never equals its own slug).
    name_to_id = {c.canonical_name.lower(): c.id for c in concepts}
    edges = []
    for row in rows:
        from_id = name_to_id.get(row["from_concept"].lower())
        to_id = name_to_id.get(row["to_concept"].lower())
        if from_id is None or to_id is None:
            continue
        edges.append(Edge(
            id=str(uuid.uuid4()),
            from_concept=from_id,
            to_concept=to_id,
            edge_type=row["edge_type"],
            evidence=[BeatRef(beat_id=bid, relation="evidence_for")
                      for bid in row["evidence_beat_ids"]],
        ))
    return edges
