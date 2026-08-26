import json
import uuid
import cv2
from google.genai import types
from shruti.config import Models
from shruti.contracts.speech import Utterance, Deixis


def _encode_frame(frame) -> types.Part:
    """Bug fix: a raw numpy array is not accepted as Gemini content — encode
    to JPEG bytes and wrap as an inline Part."""
    _, buf = cv2.imencode(".jpg", frame)
    return types.Part.from_bytes(data=buf.tobytes(), mime_type="image/jpeg")

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
        contents=[_DEIXIS_PROMPT.format(text=utterance.text), *[_encode_frame(f) for f in clip_frames]],
        config={"response_mime_type": "application/json"},
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
