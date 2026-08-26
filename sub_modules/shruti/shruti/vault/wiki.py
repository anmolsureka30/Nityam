from pathlib import Path

from shruti.contracts.atlas import Concept
from shruti.contracts.beat import Beat
from shruti.contracts.board import BoardState
from shruti.lens.citations import format_citation
from shruti.stages.weave.render import render_board_content_for_beat


def write_concept_wiki_page(
    wiki_dir: Path, concept: Concept, beats: list[Beat],
    board_states: list[BoardState], recording_slug: str,
) -> None:
    """Per-concept wiki page — one file per concept, accumulating an entry
    every time any recording teaches it. Append-only, never rewritten (same
    principle as the student-facing concept pages in memory_layer.md §3.4):
    each rewrite trades a specific insight for tidier prose and degrades
    over repeated edits. Idempotent per citation: a citation already
    present in the file is not appended twice — see this module's own
    design note in the plan that introduced it for why no database query
    is needed to check prior-recording history."""
    wiki_dir.mkdir(parents=True, exist_ok=True)
    path = wiki_dir / f"{concept.id}.md"
    if not path.exists():
        meta = " · ".join(
            str(v) for v in (
                f"`{concept.id}`", concept.subject,
                f"Grade {concept.grade}" if concept.grade else None, concept.chapter,
            ) if v
        )
        path.write_text(f"# {concept.canonical_name}\n{meta}\n\n")

    existing = path.read_text()
    beats_by_id = {b.id: b for b in beats}
    new_entries = []
    added_this_call = set()
    for ref in concept.taught_in:
        beat = beats_by_id.get(ref.beat_id)
        if beat is None:
            continue
        citation = format_citation(recording_slug, beat.start_s)
        if citation in existing or citation in added_this_call:
            continue
        added_this_call.add(citation)
        entry = [f"## Taught in {citation}"]
        if concept.definition:
            entry.append(concept.definition)
        board_text = render_board_content_for_beat(beat, board_states)
        if board_text:
            entry.append("")
            entry.append("**Board:**")
            entry.append(board_text)
        entry.append("")
        new_entries.append("\n".join(entry))

    if new_entries:
        with path.open("a") as f:
            f.write("\n" + "\n".join(new_entries))
