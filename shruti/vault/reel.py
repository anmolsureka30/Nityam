import json
from shruti.contracts.recording import Recording
from shruti.contracts.speech import Utterance
from shruti.contracts.beat import Beat


async def write_recording(conn, recording: Recording) -> None:
    await conn.execute(
        """INSERT INTO recording (id, source_uri, title, duration_s, fps, width, height,
                                   surface_kind, subject, grade, chapter, reel_version)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
           ON CONFLICT (id) DO NOTHING""",
        recording.id, recording.source_uri, recording.title, recording.duration_s,
        recording.fps, recording.width, recording.height, recording.surface_kind.value,
        recording.subject, recording.grade, recording.chapter, recording.reel_version,
    )


async def write_utterances(conn, utterances: list[Utterance]) -> None:
    for u in utterances:
        await conn.execute(
            """INSERT INTO utterance (id, recording_id, start_s, end_s, text, speaker,
                                       language_spans, confidence)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
               ON CONFLICT (id) DO NOTHING""",
            u.id, u.recording_id, u.start_s, u.end_s, u.text, u.speaker,
            json.dumps([ls.model_dump() for ls in u.language_spans]), u.confidence,
        )


async def write_beats(conn, beats: list[Beat]) -> None:
    for b in beats:
        await conn.execute(
            """INSERT INTO beat (id, recording_id, idx, start_s, end_s, kind,
                                  board_state_id, board_delta, salience, transcript)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
               ON CONFLICT (id) DO NOTHING""",
            b.id, b.recording_id, b.idx, b.start_s, b.end_s, b.kind,
            b.board_state_id, json.dumps(b.board_delta) if b.board_delta else None,
            b.salience, b.transcript,
        )


async def get_beats(conn, recording_id: str) -> list[Beat]:
    rows = await conn.fetch(
        """SELECT id, recording_id, idx, start_s, end_s, kind, board_state_id, salience,
                  transcript FROM beat WHERE recording_id=$1 ORDER BY idx""",
        recording_id,
    )
    return [
        Beat(id=r["id"], recording_id=r["recording_id"], idx=r["idx"], start_s=r["start_s"],
             end_s=r["end_s"], kind=r["kind"], board_state_id=r["board_state_id"],
             salience=r["salience"], transcript=r["transcript"])
        for r in rows
    ]
