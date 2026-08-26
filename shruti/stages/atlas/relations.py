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
    return [
        Edge(
            id=str(uuid.uuid4()),
            from_concept=row["from_concept"],
            to_concept=row["to_concept"],
            edge_type=row["edge_type"],
            evidence=[BeatRef(beat_id=bid, relation="evidence_for")
                      for bid in row["evidence_beat_ids"]],
        )
        for row in rows
    ]
