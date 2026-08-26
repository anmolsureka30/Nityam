import json
from shruti.config import Models
from shruti.contracts.beat import Beat
from shruti.contracts.speech import Utterance

_FUSE_PROMPT = """These are candidate beat boundaries (seconds) and the
utterances spoken within them: {boundaries}

Utterances:
{utterances}

Merge over-segmented candidates into semantically coherent teaching beats.
For each final beat return: idx, start_s, end_s, kind (one of explain,
derive, example, question, recap, aside, admin), salience (0-1, teaching
value; admin beats get low salience). Return a JSON array.
"""


def fuse_beats(client, recording_id: str, boundaries: list[float],
               utterances: list[Utterance], board_states: list, deixis: list) -> list[Beat]:
    utterance_text = "\n".join(f"[{u.start_s:.1f}-{u.end_s:.1f}] {u.text}" for u in utterances)
    response = client.models.generate_content(
        model=Models().reasoner,
        contents=[_FUSE_PROMPT.format(boundaries=boundaries, utterances=utterance_text)],
        config={"response_mime_type": "application/json"},
    )
    rows = json.loads(response.text)
    beats = []
    for row in rows:
        span_utterances = [u for u in utterances if u.start_s >= row["start_s"] and u.end_s <= row["end_s"]]
        span_deixis = [d for d in deixis if row["start_s"] <= d.at_s <= row["end_s"]]
        transcript = " ".join(u.text for u in span_utterances)
        beats.append(Beat(
            id=f"{recording_id}_beat_{row['idx']:04d}",
            recording_id=recording_id,
            idx=row["idx"],
            start_s=row["start_s"],
            end_s=row["end_s"],
            kind=row["kind"],
            speech=span_utterances,
            deixis=span_deixis,
            salience=row.get("salience"),
            transcript=transcript,
        ))
    return beats
