from shruti.contracts.beat import Beat
from shruti.contracts.board import BoardState


def render_board_content_for_beat(beat: Beat, board_states: list[BoardState]) -> str:
    """Beat.board_state_id links a beat to the board content visible during
    it (see WEAVE's temporal match in ingest.py) — but that's just an id.
    This renders the actual regions (equations, text, diagrams) as short
    readable text, for use in the per-recording narrative (Task 2), the
    widened ATLAS concept-miner (Task 3), and the per-concept wiki page
    (Task 4). Returns "" if the beat has no linked board state, or the
    board state has no content, or every region is unreadable."""
    if not beat.board_state_id:
        return ""
    board_state = next((bs for bs in board_states if bs.id == beat.board_state_id), None)
    if board_state is None or board_state.content is None:
        return ""
    lines = []
    for region in board_state.content.regions:
        if region.kind == "unreadable":
            continue
        label = region.latex or region.plain_text or region.description
        if label:
            lines.append(f"- [{region.kind}] {label}")
    return "\n".join(lines)
