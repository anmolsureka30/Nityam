import json
from shruti.config import Models
from shruti.contracts.atlas import Concept, BeatRef
from shruti.contracts.beat import Beat
from shruti.contracts.board import BoardState
from shruti.stages.weave.render import render_board_content_for_beat

_CONCEPTS_PROMPT = """Beats from a lesson, each with any board content
visible during it:
{beats}

Curriculum spine (normalize concept names against this when given): {spine}

For each concept genuinely TAUGHT (introduced/explained), not merely
mentioned, return: canonical_name, aliases, taught_in_beat_ids, and
definition — a 2-4 sentence explanation grounded in what was actually said
and shown (the derivation, the equation, the example given), written so a
student reviewing this later, who did not watch the video, can understand
it standalone. Do not compress away the specific numbers, variable names,
or steps that were used — a generic textbook definition that could apply
to any lecture on this topic is a failure; this must read like notes from
THIS particular class.
Return a JSON array.
"""


def _beat_line(beat: Beat, board_states: list[BoardState] | None) -> str:
    line = f"[{beat.id}] {beat.transcript}"
    if board_states:
        board_text = render_board_content_for_beat(beat, board_states)
        if board_text:
            line += f"\n  Board:\n{board_text}"
    return line


def mine_concepts(
    client, beats: list[Beat], curriculum_spine: list[str] | None = None,
    board_states: list[BoardState] | None = None,
) -> list[Concept]:
    beats_text = "\n".join(_beat_line(b, board_states) for b in beats)
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
            definition=row.get("definition"),
            taught_in=[BeatRef(beat_id=bid, relation="taught_in")
                       for bid in row["taught_in_beat_ids"]],
        ))
    return concepts
