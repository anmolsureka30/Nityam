import json
import uuid
from shruti.config import Models
from shruti.contracts.speech import Utterance, Deixis

_DEIXIS_PROMPT = """The teacher says: "{text}"

Watch this short clip. If the teacher points at, circles, underlines,
sweeps across, or writes on a specific region of the board while saying
this, report it. If there is no such gesture, report found=false.

Return JSON: {{"found": bool, "phrase": str, "board_region": [x, y, w, h]
(normalized 0-1), "kind": "point"|"circle"|"underline"|"sweep"|"write",
"confidence": float}}
"""


def resolve_deixis(client, clip_frames: list, utterance: Utterance) -> Deixis | None:
    response = client.models.generate_content(
        model=Models().reasoner,
        contents=[_DEIXIS_PROMPT.format(text=utterance.text), *clip_frames],
    )
    row = json.loads(response.text)
    if not row.get("found"):
        return None
    return Deixis(
        id=str(uuid.uuid4()),
        recording_id=utterance.recording_id,
        at_s=utterance.start_s,
        utterance_id=utterance.id,
        phrase=row["phrase"],
        board_region=tuple(row["board_region"]),
        kind=row["kind"],
        confidence=row.get("confidence"),
    )
