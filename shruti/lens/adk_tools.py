from shruti.lens.retrievers import graph_traverse, timeline_lookup
from shruti.vault.ledger import board_state_at


def _build_lesson_functions(conn) -> dict:
    async def recall_lesson(concept_id: str, recording_ids: list[str]) -> dict:
        """Retrieve how this student's own teacher taught this concept."""
        beats = await timeline_lookup(conn, concept_id, recording_ids)
        if not beats:
            return {"found": False, "fallback": "generic"}
        b = beats[0]
        bs = await board_state_at(conn, b.recording_id, b.start_s)
        return {
            "found": True,
            "recording_id": b.recording_id,
            "timestamp": b.start_s,
            "teacher_words": b.transcript,
            "board_image_uri": bs.composited_uri if bs else None,
        }

    async def prerequisites_of(concept_id: str, depth: int = 2) -> list[dict]:
        """Multi-hop REQUIRES traversal — recursive CTE, single-digit ms."""
        return await graph_traverse(conn, concept_id, "REQUIRES", depth)

    async def known_misconceptions(concept_id: str) -> list[dict]:
        """Errors this teacher explicitly warned about, with their phrasing."""
        rows = await conn.fetch(
            """SELECT statement, teacher_phrasing, correct_understanding
               FROM misconception WHERE concept_id=$1""",
            concept_id,
        )
        return [dict(r) for r in rows]

    async def board_at(recording_id: str, t: float) -> dict:
        """What was written at second t — bitemporal range query on the Ledger."""
        bs = await board_state_at(conn, recording_id, t)
        return bs.model_dump() if bs else {"found": False}

    return {
        "recall_lesson": recall_lesson,
        "prerequisites_of": prerequisites_of,
        "known_misconceptions": known_misconceptions,
        "board_at": board_at,
    }


def build_lesson_tools(conn) -> list:
    from google.adk.tools import FunctionTool
    return [FunctionTool(f) for f in _build_lesson_functions(conn).values()]
