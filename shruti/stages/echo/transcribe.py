import json
import uuid
from shruti.config import Models
from shruti.contracts.speech import Utterance

_FIDELITY_PROMPT = """Transcribe this classroom recording exactly as spoken.

RULES
1. This is code-mixed Hindi-English classroom speech. Transcribe FAITHFULLY:
   Hindi words in Devanagari, English words in Latin script, in the order spoken.
   Do NOT translate. Do NOT normalize to one script.
2. Timestamp every utterance in seconds (start_s, end_s).
3. Label the speaker: TEACHER or STUDENT.
4. If audio is unintelligible, emit text "[inaudible]". Never guess.

Return a JSON array of objects: {start_s, end_s, text, speaker, confidence}.
"""


def transcribe_audio(client, audio_path: str, recording_id: str) -> list[Utterance]:
    response = client.models.generate_content(
        model=Models().reasoner,
        contents=[_FIDELITY_PROMPT, audio_path],
    )
    rows = json.loads(response.text)
    return [
        Utterance(
            id=str(uuid.uuid4()),
            recording_id=recording_id,
            start_s=row["start_s"],
            end_s=row["end_s"],
            text=row["text"],
            speaker=row["speaker"],
            confidence=row.get("confidence"),
        )
        for row in rows
    ]
