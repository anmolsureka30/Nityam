import json
from shruti.config import Models
from shruti.contracts.atlas import Concept, BeatRef
from shruti.contracts.beat import Beat

_CONCEPTS_PROMPT = """Beats from a lesson:
{beats}

Curriculum spine (normalize concept names against this when given): {spine}

For each concept genuinely TAUGHT (introduced/explained), not merely
mentioned, return: canonical_name, aliases, taught_in_beat_ids.
Return a JSON array.
"""


def mine_concepts(client, beats: list[Beat], curriculum_spine: list[str] | None = None) -> list[Concept]:
    beats_text = "\n".join(f"[{b.id}] {b.transcript}" for b in beats)
    response = client.models.generate_content(
        model=Models().reasoner,
        contents=[_CONCEPTS_PROMPT.format(beats=beats_text, spine=curriculum_spine or [])],
        config={"response_mime_type": "application/json"},
    )
    rows = json.loads(response.text)
    concepts = []
    for row in rows:
        slug = row["canonical_name"].lower().replace(" ", "_")
        concepts.append(Concept(
            id=slug,
            canonical_name=row["canonical_name"],
            aliases=row.get("aliases", []),
            taught_in=[BeatRef(beat_id=bid, relation="taught_in")
                       for bid in row["taught_in_beat_ids"]],
        ))
    return concepts
