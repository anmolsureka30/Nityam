from pathlib import Path

from shruti.contracts.atlas import Concept, Misconception
from shruti.contracts.beat import Beat
from shruti.contracts.board import BoardState
from shruti.lens.citations import format_citation
from shruti.stages.weave.render import render_board_content_for_beat


def write_concept_wiki_page(
    wiki_dir: Path, concept: Concept, beats: list[Beat],
    board_states: list[BoardState], recording_slug: str,
    misconceptions: list[Misconception] | None = None,
) -> None:
    """Per-concept wiki page — one file per concept, accumulating an entry
    every time any recording teaches it. Append-only, never rewritten (same
    principle as the student-facing concept pages in memory_layer.md §3.4):
    each rewrite trades a specific insight for tidier prose and degrades
    over repeated edits. Idempotent per citation: a citation already
    present in the file is not appended twice — see this module's own
    design note in the plan that introduced it for why no database query
    is needed to check prior-recording history.

    Misconceptions whose concept_id matches this concept fold their
    verbatim teacher_phrasing into the entry — this is the one place in
    the whole pipeline that preserves the teacher's exact words (see
    memory_layer.md §3.2: "the teacher's own phrasing is preserved and
    cited back to SHRUTI — nobody else can do this, because nobody else
    watched the class"), so it belongs on the page a student would
    actually read, not just in the raw JSON/DB. When a misconception's
    pre_empted_at_beat is also one of the concept's own taught_in beats,
    it's folded into that same entry; otherwise it gets its own entry,
    since the citation has to point at the real beat where the correction
    actually happened."""
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
    own_misconceptions = [m for m in (misconceptions or []) if m.concept_id == concept.id]
    misconceptions_by_beat: dict[str, list[Misconception]] = {}
    for m in own_misconceptions:
        misconceptions_by_beat.setdefault(m.pre_empted_at_beat, []).append(m)

    taught_in_beat_ids = [ref.beat_id for ref in concept.taught_in]
    all_beat_ids = list(dict.fromkeys(taught_in_beat_ids + list(misconceptions_by_beat.keys())))

    new_entries = []
    added_this_call = set()
    for beat_id in all_beat_ids:
        beat = beats_by_id.get(beat_id)
        if beat is None:
            continue
        citation = format_citation(recording_slug, beat.start_s)
        if citation in existing or citation in added_this_call:
            continue
        added_this_call.add(citation)
        entry = [f"## Taught in {citation}"]
        if beat_id in taught_in_beat_ids and concept.definition:
            entry.append(concept.definition)
        board_text = render_board_content_for_beat(beat, board_states)
        if board_text:
            entry.append("")
            entry.append("**Board:**")
            entry.append(board_text)
        for m in misconceptions_by_beat.get(beat_id, []):
            entry.append("")
            entry.append("**Common mistake (in the teacher's own words):**")
            if m.teacher_phrasing:
                entry.append(f'> "{m.teacher_phrasing}"')
            entry.append("")
            entry.append(f"{m.statement} **Correct understanding:** {m.correct_understanding}")
        entry.append("")
        new_entries.append("\n".join(entry))

    if new_entries:
        with path.open("a") as f:
            f.write("\n" + "\n".join(new_entries))
