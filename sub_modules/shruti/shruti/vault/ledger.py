import json
from shruti.contracts.board import BoardState


async def write_board_state(conn, board_state: BoardState) -> None:
    await conn.execute(
        """INSERT INTO board_state (id, recording_id, idx, valid_from_s, valid_to_s,
                                     composited_uri, unfilled_uri, ink_coverage, ended_by,
                                     ledger_version)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
           ON CONFLICT (id) DO NOTHING""",
        board_state.id, board_state.recording_id, board_state.idx,
        board_state.valid_from_s, board_state.valid_to_s, board_state.composited_uri,
        board_state.unfilled_uri, board_state.ink_coverage, board_state.ended_by,
        board_state.ledger_version,
    )
    if board_state.content:
        for region in board_state.content.regions:
            # derives_from is informational text now (migration 006), not an
            # enforced FK — GLYPH's model can legitimately name multiple
            # prior derivation steps.
            derives_from = (
                ", ".join(region.derives_from) if isinstance(region.derives_from, list)
                else region.derives_from
            )
            # GLYPH's model names region.id independently per board state
            # (e.g. "r1", "eq1") with no awareness of other slides, so the
            # raw label collides across slides and across re-runs of the
            # same video. board_region.id is a global PRIMARY KEY, so an
            # unqualified label caused later slides' regions to silently
            # vanish under ON CONFLICT DO NOTHING (confirmed: slide 4's
            # r1/r2/r3 were dropped because slide 1 had already claimed
            # them). Namespacing by board_state.id makes the row id globally
            # unique while leaving region.id itself as the model's natural
            # per-slide label.
            row_id = f"{board_state.id}::{region.id}"
            await conn.execute(
                """INSERT INTO board_region (id, board_state_id, bbox, kind, latex,
                                              plain_text, description, role, step_index,
                                              derives_from, confidence)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                   ON CONFLICT (id) DO NOTHING""",
                row_id, board_state.id, json.dumps(region.bbox), region.kind,
                region.latex, region.plain_text, region.description, region.role,
                region.step_index, derives_from, region.confidence,
            )


async def board_state_at(conn, recording_id: str, t: float) -> BoardState | None:
    row = await conn.fetchrow(
        """SELECT * FROM board_state
           WHERE recording_id=$1 AND valid_from_s <= $2 AND valid_to_s > $2
           ORDER BY idx LIMIT 1""",
        recording_id, t,
    )
    if row is None:
        return None
    return BoardState(
        id=row["id"], recording_id=row["recording_id"], idx=row["idx"],
        valid_from_s=row["valid_from_s"], valid_to_s=row["valid_to_s"],
        composited_uri=row["composited_uri"], unfilled_uri=row["unfilled_uri"],
        ink_coverage=row["ink_coverage"], ended_by=row["ended_by"],
        ledger_version=row["ledger_version"],
    )
