from shruti.contracts.beat import Beat
from shruti.contracts.board import BoardState
from shruti.contracts.recording import Recording
from shruti.lens.citations import format_citation
from shruti.stages.weave.render import render_board_content_for_beat


def build_recording_narrative(
    recording: Recording, beats: list[Beat], board_states: list[BoardState],
) -> str:
    """Deterministic (no LLM call) per-lecture narrative: beats in
    chronological order, each with its transcript and any linked board
    content interleaved. This is the readable "what happened in this
    lecture" artifact — a standalone document, and the staging text ATLAS's
    concept-miner (Task 3) reads for real board+narration context instead
    of bare transcript alone."""
    lines = [
        f"# {recording.slug}",
        "",
        f"Subject: {recording.subject or 'unspecified'} | "
        f"Grade: {recording.grade or 'unspecified'} | "
        f"Chapter: {recording.chapter or 'unspecified'} | "
        f"Duration: {recording.duration_s:.0f}s",
        "",
    ]
    for beat in sorted(beats, key=lambda b: b.start_s):
        citation = format_citation(recording.slug, beat.start_s)
        lines.append(f"## [{citation}] {beat.kind}")
        lines.append("")
        lines.append(beat.transcript)
        board_text = render_board_content_for_beat(beat, board_states)
        if board_text:
            lines.append("")
            lines.append("**Board:**")
            lines.append(board_text)
        lines.append("")
    return "\n".join(lines)
