import json
import uuid
from shruti.config import Models
from shruti.contracts.atlas import Misconception
from shruti.contracts.beat import Beat

_MISCONCEPTIONS_PROMPT = """Find every point where the teacher PRE-EMPTED a
student error (signals: "everyone gets this wrong", "don't confuse this
with...", "yaad rakhna, X is NOT Y", or any construction naming a wrong
belief to correct it).

Beats: {beats}

For each, return: concept_id, statement (general, testable), teacher_phrasing
(verbatim, code-mixing intact), correct_understanding, pre_empted_at_beat.
Only include errors the teacher NAMED. Return a JSON array.
"""


def mine_misconceptions(client, beats: list[Beat]) -> list[Misconception]:
    beats_text = "\n".join(f"[{b.id}] {b.transcript}" for b in beats)
    response = client.models.generate_content(
        model=Models().reasoner,
        contents=[_MISCONCEPTIONS_PROMPT.format(beats=beats_text)],
        config={"response_mime_type": "application/json"},
    )
    rows = json.loads(response.text)
    return [
        Misconception(
            id=str(uuid.uuid4()),
            concept_id=row["concept_id"],
            statement=row["statement"],
            teacher_phrasing=row.get("teacher_phrasing"),
            correct_understanding=row["correct_understanding"],
            pre_empted_at_beat=row["pre_empted_at_beat"],
        )
        for row in rows
    ]
