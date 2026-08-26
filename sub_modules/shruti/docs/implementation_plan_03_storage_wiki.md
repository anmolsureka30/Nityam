# Shruti knowledge storage: per-recording narratives + per-concept wiki — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop ATLAS from throwing away almost everything it extracts.
Today `Concept.definition` exists on the contract but is never filled in —
the stored result is a bare name and a timestamp, none of the actual
explanation, derivation, or board content survives past the beat it was
mined from. This plan adds a deterministic per-recording narrative
(board content + transcript interleaved, no extra LLM call) and an
append-only per-concept wiki page that accumulates real explanation and
citations every time any recording teaches that concept — the Markdown
knowledge layer approved in `shruti_storage_and_pipeline_redesign_design.md`
§2. This is Plan 2 of 3 from that design doc (Plan 1, pipeline correctness
fixes, is complete — see `shruti_implementation_plan_pipeline_fixes.md`).
Plan 3 (ECHO's Gemini→Whisper swap) is separate and independent of this one.

**Architecture:** Postgres VAULT is unchanged by this plan — it stays the
structural/citation/provenance backbone exactly as it is today. Two new
kinds of git-tracked file get added: `vault/notes/<recording_slug>.md`
(one per-recording narrative, generated deterministically) and
`vault/wiki/<concept_id>.md` (one per concept, append-only, growing every
time any recording teaches it — the primary knowledge artifact). A new
small shared helper (`render_board_content_for_beat`) lives in
`shruti/stages/weave/` since it's about the beat↔board-state linkage WEAVE
already owns; both the narrative builder (`shruti/vault/`) and the widened
ATLAS concept-miner (`shruti/stages/atlas/`) consume it, rather than
either importing from the other.

**Tech Stack:** Python 3.12, pytest + pytest-asyncio, existing
FakeResponse/FakeClient test-double pattern (`tests/stages/atlas/*.py`),
pytest's built-in `tmp_path` fixture for the two file-writing modules
(neither needs a database — see Task 4's design note on why the wiki
writer doesn't need one).

**Spec:** `shruti_storage_and_pipeline_redesign_design.md` §2 (storage
architecture) and §3's `concepts.py` bullet (definition widening).

## Global Constraints

- The full test suite must stay green after every task:
  `uv run --env-file .env python -m pytest -q` from the repo root. It is
  119/119 passing before this plan starts (on top of Plan 1's work,
  commit `60000ef`).
- `vault/notes/` and `vault/wiki/` are real, persistent, git-tracked
  knowledge artifacts — NOT debug/observability output. Do not write them
  under `.local/` (that stays exactly what it is: per-run scratch for
  inspecting how a run worked mechanically).
- Follow the existing `FakeResponse`/`FakeClient` test-double pattern
  already used in `tests/stages/atlas/*.py` for any test touching a
  `client.models.generate_content` call.
- Per-concept wiki pages are append-only — never rewrite existing content
  in an already-written page. Same principle as the student-facing concept
  pages in `memory_layer.md` §3.4: a rewrite trades a specific insight for
  tidier prose and degrades over repeated edits.
- No new LLM calls are added by this plan. The wiki page's explanation text
  reuses `Concept.definition`, which Task 3 makes `mine_concepts` (an
  *existing* call) return — deliberately not a second call, to keep this
  plan's token cost at zero marginal increase.
- Commit after each task, not each step within a task.

---

### Task 1: `render_board_content_for_beat` — shared beat↔board-content renderer

**Files:**
- Create: `shruti/stages/weave/render.py`
- Test: `tests/stages/weave/test_render.py`

**Interfaces:**
- Produces: `render_board_content_for_beat(beat: Beat, board_states: list[BoardState]) -> str` in `shruti/stages/weave/render.py`. Task 2 (narrative builder), Task 3 (widened `mine_concepts`), and Task 4 (wiki writer) all import and call this — same name, same module, same signature for all three.

- [ ] **Step 1: Write the failing tests**

Create `tests/stages/weave/test_render.py`:

```python
from shruti.contracts.beat import Beat
from shruti.contracts.board import BoardContent, BoardState, Region
from shruti.stages.weave.render import render_board_content_for_beat


def test_renders_readable_regions_from_the_linked_board_state():
    beat = Beat(id="b1", recording_id="r1", idx=0, start_s=0.0, end_s=10.0,
                kind="explain", transcript="x", board_state_id="bs1")
    board_states = [
        BoardState(
            id="bs1", recording_id="r1", idx=0, valid_from_s=0.0, valid_to_s=10.0,
            composited_uri="gs://x", ended_by="shot_cut",
            content=BoardContent(regions=[
                Region(id="r1", bbox=(0, 0, 0.1, 0.1), kind="text", plain_text="Horizontal Range"),
                Region(id="r2", bbox=(0.1, 0, 0.1, 0.1), kind="equation", latex="R = u \\cos\\theta \\times t"),
                Region(id="r3", bbox=(0.2, 0, 0.1, 0.1), kind="unreadable"),
            ]),
        ),
    ]
    rendered = render_board_content_for_beat(beat, board_states)
    assert "Horizontal Range" in rendered
    assert "R = u \\cos\\theta \\times t" in rendered
    assert "unreadable" not in rendered.lower()


def test_empty_string_when_beat_has_no_linked_board_state():
    beat = Beat(id="b1", recording_id="r1", idx=0, start_s=0.0, end_s=10.0,
                kind="explain", transcript="x", board_state_id=None)
    assert render_board_content_for_beat(beat, board_states=[]) == ""


def test_empty_string_when_linked_board_state_has_no_content():
    beat = Beat(id="b1", recording_id="r1", idx=0, start_s=0.0, end_s=10.0,
                kind="explain", transcript="x", board_state_id="bs1")
    board_states = [
        BoardState(id="bs1", recording_id="r1", idx=0, valid_from_s=0.0, valid_to_s=10.0,
                    composited_uri="gs://x", ended_by="shot_cut", content=None),
    ]
    assert render_board_content_for_beat(beat, board_states) == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --env-file .env python -m pytest tests/stages/weave/test_render.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shruti.stages.weave.render'`

- [ ] **Step 3: Implement `render_board_content_for_beat`**

Create `shruti/stages/weave/render.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --env-file .env python -m pytest tests/stages/weave/test_render.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full suite**

Run: `uv run --env-file .env python -m pytest -q`
Expected: 122 passed (119 + 3 new).

- [ ] **Step 6: Commit**

```bash
git add shruti/stages/weave/render.py tests/stages/weave/test_render.py
git commit -m "feat: add render_board_content_for_beat, shared beat-to-board-text renderer"
```

---

### Task 2: Per-recording narrative builder

**Files:**
- Create: `shruti/vault/narrative.py`
- Test: `tests/vault/test_narrative.py`

**Interfaces:**
- Consumes: `render_board_content_for_beat` (Task 1, `shruti.stages.weave.render`); `format_citation(slug: str, seconds: float) -> str` (`shruti.lens.citations`, already exists).
- Produces: `build_recording_narrative(recording: Recording, beats: list[Beat], board_states: list[BoardState]) -> str` in `shruti/vault/narrative.py`. Task 5 (ingest.py wiring) calls this and writes the result to `vault/notes/<recording.slug>.md`.

- [ ] **Step 1: Write the failing tests**

Create `tests/vault/test_narrative.py`:

```python
from shruti.contracts.beat import Beat
from shruti.contracts.board import BoardContent, BoardState, Region
from shruti.contracts.recording import Recording, SurfaceKind
from shruti.vault.narrative import build_recording_narrative


def test_narrative_includes_recording_header_and_beat_transcripts():
    rec = Recording(id="r" * 64, slug="physics_01", source_uri="gs://x",
                     duration_s=120.0, fps=30.0, surface_kind=SurfaceKind.SLIDES,
                     subject="Physics", grade=10, chapter="Projectile Motion")
    beats = [
        Beat(id="b1", recording_id=rec.id, idx=0, start_s=0.0, end_s=10.0,
             kind="explain", transcript="Today we cover projectile motion."),
        Beat(id="b2", recording_id=rec.id, idx=1, start_s=10.0, end_s=20.0,
             kind="derive", transcript="Deriving the range formula."),
    ]
    narrative = build_recording_narrative(rec, beats, board_states=[])
    assert "physics_01" in narrative
    assert "Physics" in narrative and "10" in narrative and "Projectile Motion" in narrative
    assert "Today we cover projectile motion." in narrative
    assert "Deriving the range formula." in narrative
    # Beats appear in chronological order
    assert narrative.index("Today we cover") < narrative.index("Deriving the range")


def test_narrative_interleaves_board_content_when_present():
    rec = Recording(id="r" * 64, slug="physics_01", source_uri="gs://x",
                     duration_s=60.0, fps=30.0, surface_kind=SurfaceKind.SLIDES)
    beats = [
        Beat(id="b1", recording_id=rec.id, idx=0, start_s=0.0, end_s=10.0,
             kind="explain", transcript="Here's the formula.", board_state_id="bs1"),
    ]
    board_states = [
        BoardState(id="bs1", recording_id=rec.id, idx=0, valid_from_s=0.0, valid_to_s=10.0,
                    composited_uri="gs://x", ended_by="shot_cut",
                    content=BoardContent(regions=[
                        Region(id="r1", bbox=(0, 0, 0.1, 0.1), kind="equation", latex="R = ut"),
                    ])),
    ]
    narrative = build_recording_narrative(rec, beats, board_states)
    assert "R = ut" in narrative
    assert narrative.index("Here's the formula.") < narrative.index("R = ut")


def test_narrative_includes_each_beats_citation():
    rec = Recording(id="r" * 64, slug="physics_01", source_uri="gs://x",
                     duration_s=60.0, fps=30.0, surface_kind=SurfaceKind.SLIDES)
    beats = [
        Beat(id="b1", recording_id=rec.id, idx=0, start_s=65.0, end_s=70.0,
             kind="explain", transcript="x"),
    ]
    narrative = build_recording_narrative(rec, beats, board_states=[])
    assert "shruti:physics_01 @1:05" in narrative
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --env-file .env python -m pytest tests/vault/test_narrative.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shruti.vault.narrative'`

- [ ] **Step 3: Implement `build_recording_narrative`**

Create `shruti/vault/narrative.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --env-file .env python -m pytest tests/vault/test_narrative.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full suite**

Run: `uv run --env-file .env python -m pytest -q`
Expected: 125 passed (122 + 3 new).

- [ ] **Step 6: Commit**

```bash
git add shruti/vault/narrative.py tests/vault/test_narrative.py
git commit -m "feat: add build_recording_narrative, the per-recording notes artifact"
```

---

### Task 3: Widen `mine_concepts` to capture a real definition and use board content

**Files:**
- Modify: `shruti/stages/atlas/concepts.py`
- Modify: `tests/stages/atlas/test_concepts.py`

**Interfaces:**
- Consumes: `render_board_content_for_beat` (Task 1, `shruti.stages.weave.render`).
- Produces: `mine_concepts(client, beats: list[Beat], curriculum_spine: list[str] | None = None, board_states: list[BoardState] | None = None) -> list[Concept]` — same name, widened signature (two new trailing params, both default `None`/backward-compatible). `Concept.definition` (already exists on the contract, currently always `None`) is now populated when the model returns one. Task 5 (ingest.py wiring) calls this with `board_states=board_states`.

**Context for the implementer:** the existing test
(`test_mine_concepts_parses_taught_in_refs`) must keep passing unchanged —
its fake payload has no `definition` key, so `definition` must be parsed
with `.get()`, defaulting to `None`, not a required field.

- [ ] **Step 1: Write the failing tests**

Add to `tests/stages/atlas/test_concepts.py` (it already has `FakeResponse`/`FakeClient` — reuse them, do not redefine):

```python
from shruti.contracts.board import BoardContent, BoardState, Region


def test_mine_concepts_captures_definition_when_the_model_returns_one():
    payload = [{"canonical_name": "completing the square", "aliases": [],
                "taught_in_beat_ids": ["b1"],
                "definition": "Rewriting a quadratic as a squared binomial plus a constant."}]
    client = FakeClient(payload)
    beats = [Beat(id="b1", recording_id="r1", idx=0, start_s=0.0, end_s=5.0,
                  kind="derive", transcript="we complete the square by...")]
    concepts = mine_concepts(client, beats)
    assert concepts[0].definition == "Rewriting a quadratic as a squared binomial plus a constant."


def test_mine_concepts_includes_board_content_in_the_prompt_when_given():
    captured_contents = []

    class CapturingClient(FakeClient):
        class _Models(FakeClient._Models):
            def generate_content(self, model, contents, config=None):
                captured_contents.append(contents)
                return super().generate_content(model, contents, config)

        @property
        def models(self):
            return CapturingClient._Models(self)

    payload = [{"canonical_name": "range formula", "aliases": [],
                "taught_in_beat_ids": ["b1"], "definition": "d"}]
    client = CapturingClient(payload)
    beats = [Beat(id="b1", recording_id="r1", idx=0, start_s=0.0, end_s=5.0,
                  kind="derive", transcript="here's the range formula", board_state_id="bs1")]
    board_states = [
        BoardState(id="bs1", recording_id="r1", idx=0, valid_from_s=0.0, valid_to_s=5.0,
                    composited_uri="gs://x", ended_by="shot_cut",
                    content=BoardContent(regions=[
                        Region(id="r1", bbox=(0, 0, 0.1, 0.1), kind="equation", latex="R = ut"),
                    ])),
    ]
    mine_concepts(client, beats, board_states=board_states)
    assert any("R = ut" in str(c) for c in captured_contents)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --env-file .env python -m pytest tests/stages/atlas/test_concepts.py -v`
Expected: FAIL — `test_mine_concepts_captures_definition_when_the_model_returns_one` fails because `concepts[0].definition` is `None` (never set); `test_mine_concepts_includes_board_content_in_the_prompt_when_given` fails because `mine_concepts` doesn't accept a `board_states` keyword argument yet (`TypeError`).

- [ ] **Step 3: Widen `mine_concepts`**

In `shruti/stages/atlas/concepts.py`, replace the whole file:

```python
import json
from shruti.config import Models
from shruti.contracts.atlas import Concept, BeatRef
from shruti.contracts.beat import Beat
from shruti.contracts.board import BoardState
from shruti.stages.weave.render import render_board_content_for_beat

_CONCEPTS_PROMPT = """Beats from a lesson, each with any board content
visible during it:
{beats}

Curriculum spine (normalize concept names against this when given): {spine}

For each concept genuinely TAUGHT (introduced/explained), not merely
mentioned, return: canonical_name, aliases, taught_in_beat_ids, and
definition (a 2-4 sentence explanation grounded in what was actually said
and shown — the derivation, the equation, the example given, not a generic
textbook definition).
Return a JSON array.
"""


def _beat_line(beat: Beat, board_states: list[BoardState] | None) -> str:
    line = f"[{beat.id}] {beat.transcript}"
    if board_states:
        board_text = render_board_content_for_beat(beat, board_states)
        if board_text:
            line += f"\n  Board:\n{board_text}"
    return line


def mine_concepts(
    client, beats: list[Beat], curriculum_spine: list[str] | None = None,
    board_states: list[BoardState] | None = None,
) -> list[Concept]:
    beats_text = "\n".join(_beat_line(b, board_states) for b in beats)
    response = client.models.generate_content(
        model=Models().reasoner,
        contents=[_CONCEPTS_PROMPT.format(beats=beats_text, spine=curriculum_spine or [])],
        config={"response_mime_type": "application/json"},
    )
    rows = json.loads(response.text)
    concepts = []
    for row in rows:
        slug = row["canonical_name"].lower().replace(" ", "_")
        concepts.append(Concept(
            id=slug,
            canonical_name=row["canonical_name"],
            aliases=row.get("aliases", []),
            definition=row.get("definition"),
            taught_in=[BeatRef(beat_id=bid, relation="taught_in")
                       for bid in row["taught_in_beat_ids"]],
        ))
    return concepts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --env-file .env python -m pytest tests/stages/atlas/test_concepts.py -v`
Expected: PASS (3 tests: the original + 2 new)

- [ ] **Step 5: Run the full suite**

Run: `uv run --env-file .env python -m pytest -q`
Expected: 127 passed (125 + 2 new).

- [ ] **Step 6: Commit**

```bash
git add shruti/stages/atlas/concepts.py tests/stages/atlas/test_concepts.py
git commit -m "feat: mine_concepts captures a real definition grounded in board content"
```

---

### Task 4: Per-concept wiki page writer

**Files:**
- Create: `shruti/vault/wiki.py`
- Test: `tests/vault/test_wiki.py`

**Interfaces:**
- Consumes: `render_board_content_for_beat` (Task 1); `format_citation` (`shruti.lens.citations`).
- Produces: `write_concept_wiki_page(wiki_dir: Path, concept: Concept, beats: list[Beat], board_states: list[BoardState], recording_slug: str) -> None` in `shruti/vault/wiki.py`. Task 5 (ingest.py wiring) calls this once per concept after `write_concepts` succeeds.

**Design note for the implementer — why this needs no database access:**
a concept's full citation history *is* the accumulated wiki file itself —
each call only needs to know which of *this run's* citations (from
`concept.taught_in`, already fully in memory) aren't in the file yet, and
append those. There's no need to query `beat_ref` for prior recordings'
citations; they're already rendered on the page from when they were
written. This makes the function pure file I/O plus string logic, no
`db_conn` fixture, no async.

- [ ] **Step 1: Write the failing tests**

Create `tests/vault/test_wiki.py`:

```python
from shruti.contracts.atlas import BeatRef, Concept
from shruti.contracts.beat import Beat
from shruti.contracts.board import BoardContent, BoardState, Region
from shruti.vault.wiki import write_concept_wiki_page


def test_creates_a_new_page_with_header_and_first_entry(tmp_path):
    concept = Concept(id="range_formula", canonical_name="Range Formula",
                       subject="Physics", grade=10, chapter="Projectile Motion",
                       definition="How far a projectile travels horizontally.",
                       taught_in=[BeatRef(beat_id="b1", relation="taught_in")])
    beats = [Beat(id="b1", recording_id="r1", idx=0, start_s=65.0, end_s=70.0,
                  kind="derive", transcript="x")]
    write_concept_wiki_page(tmp_path, concept, beats, board_states=[], recording_slug="physics_01")
    page = (tmp_path / "range_formula.md").read_text()
    assert "# Range Formula" in page
    assert "range_formula" in page
    assert "Physics" in page and "10" in page and "Projectile Motion" in page
    assert "shruti:physics_01 @1:05" in page
    assert "How far a projectile travels horizontally." in page


def test_appending_a_new_citation_does_not_erase_the_first_entry(tmp_path):
    concept = Concept(id="range_formula", canonical_name="Range Formula",
                       definition="def 1",
                       taught_in=[BeatRef(beat_id="b1", relation="taught_in")])
    beats = [Beat(id="b1", recording_id="r1", idx=0, start_s=0.0, end_s=5.0,
                  kind="derive", transcript="x")]
    write_concept_wiki_page(tmp_path, concept, beats, board_states=[], recording_slug="physics_01")

    concept_2 = concept.model_copy(update={
        "taught_in": [BeatRef(beat_id="b2", relation="taught_in")],
        "definition": "def 2",
    })
    beats_2 = [Beat(id="b2", recording_id="r2", idx=0, start_s=30.0, end_s=35.0,
                    kind="derive", transcript="y")]
    write_concept_wiki_page(tmp_path, concept_2, beats_2, board_states=[], recording_slug="physics_02")

    page = (tmp_path / "range_formula.md").read_text()
    assert "shruti:physics_01 @0:00" in page
    assert "shruti:physics_02 @0:30" in page
    assert "def 1" in page
    assert "def 2" in page


def test_re_adding_the_same_citation_does_not_duplicate_the_entry(tmp_path):
    concept = Concept(id="range_formula", canonical_name="Range Formula", definition="def 1",
                       taught_in=[BeatRef(beat_id="b1", relation="taught_in")])
    beats = [Beat(id="b1", recording_id="r1", idx=0, start_s=0.0, end_s=5.0,
                  kind="derive", transcript="x")]
    write_concept_wiki_page(tmp_path, concept, beats, board_states=[], recording_slug="physics_01")
    write_concept_wiki_page(tmp_path, concept, beats, board_states=[], recording_slug="physics_01")
    page = (tmp_path / "range_formula.md").read_text()
    assert page.count("shruti:physics_01 @0:00") == 1


def test_includes_board_content_for_the_specific_citation(tmp_path):
    concept = Concept(id="range_formula", canonical_name="Range Formula", definition="def",
                       taught_in=[BeatRef(beat_id="b1", relation="taught_in")])
    beats = [Beat(id="b1", recording_id="r1", idx=0, start_s=0.0, end_s=5.0,
                  kind="derive", transcript="x", board_state_id="bs1")]
    board_states = [
        BoardState(id="bs1", recording_id="r1", idx=0, valid_from_s=0.0, valid_to_s=5.0,
                    composited_uri="gs://x", ended_by="shot_cut",
                    content=BoardContent(regions=[
                        Region(id="r1", bbox=(0, 0, 0.1, 0.1), kind="equation", latex="R = ut"),
                    ])),
    ]
    write_concept_wiki_page(tmp_path, concept, beats, board_states, recording_slug="physics_01")
    page = (tmp_path / "range_formula.md").read_text()
    assert "R = ut" in page
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --env-file .env python -m pytest tests/vault/test_wiki.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shruti.vault.wiki'`

- [ ] **Step 3: Implement `write_concept_wiki_page`**

Create `shruti/vault/wiki.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --env-file .env python -m pytest tests/vault/test_wiki.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full suite**

Run: `uv run --env-file .env python -m pytest -q`
Expected: 131 passed (127 + 4 new).

- [ ] **Step 6: Commit**

```bash
git add shruti/vault/wiki.py tests/vault/test_wiki.py
git commit -m "feat: add write_concept_wiki_page, append-only per-concept knowledge accumulation"
```

---

### Task 5: Wire the narrative and wiki writers into `ingest.py`

**Files:**
- Modify: `shruti/ingest.py`

**Interfaces:**
- No new interfaces produced — this task only wires Tasks 2, 3, and 4's already-tested functions into the orchestrator. `mine_concepts`'s call site gets the new `board_states=board_states` argument (Task 3); `build_recording_narrative` (Task 2) and `write_concept_wiki_page` (Task 4) get called for the first time anywhere in the codebase.

- [ ] **Step 1: Add imports and directory constants**

In `shruti/ingest.py`'s import block, add:
```python
from shruti.vault.narrative import build_recording_narrative
from shruti.vault.wiki import write_concept_wiki_page
```

Near the top of the file, next to the existing constants (locate by
content — prior plans in this repo found stated line numbers drift):
```python
POINT_CAP = 6  # cap deixis calls to bound API cost — see module docstring
SLIDE_SAMPLE_INTERVAL_S = 25.0  # see compute_slide_sample_spans's docstring
MAX_SLIDE_SAMPLES = 60  # bounds GLYPH calls for long videos — see below
```
add:
```python
NOTES_DIR = Path("vault/notes")  # per-recording narrative, git-tracked knowledge, not .local/ scratch
WIKI_DIR = Path("vault/wiki")  # per-concept pages, git-tracked knowledge, not .local/ scratch
```
(`Path` is already imported at the top of this file — confirm, don't add a
second import.)

- [ ] **Step 2: Write the narrative after WEAVE, before ATLAS**

Find (locate by content, it's right after WEAVE's beat-printing loop and
before the blank-line-plus-"ATLAS"-header block):
```python
    print(f"Beats fused: {len(beats)}")
    for b in beats:
        print(f"  [{b.start_s:6.1f}-{b.end_s:6.1f}s] {b.kind:8s} salience={b.salience}: {b.transcript[:70]}")

    print()
    print("=" * 70)
    print("ATLAS")
```
Replace with:
```python
    print(f"Beats fused: {len(beats)}")
    for b in beats:
        print(f"  [{b.start_s:6.1f}-{b.end_s:6.1f}s] {b.kind:8s} salience={b.salience}: {b.transcript[:70]}")

    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    narrative_path = NOTES_DIR / f"{recording.slug}.md"
    narrative_path.write_text(build_recording_narrative(recording, beats, board_states))
    print(f"Recording narrative written to {narrative_path}")

    print()
    print("=" * 70)
    print("ATLAS")
```

- [ ] **Step 3: Pass board content into `mine_concepts`**

Find:
```python
    concepts_raw = mine_concepts(client, beats, curriculum_spine=[chapter] if chapter else None)
```
Replace with:
```python
    concepts_raw = mine_concepts(client, beats, curriculum_spine=[chapter] if chapter else None,
                                  board_states=board_states)
```

- [ ] **Step 4: Update wiki pages after concepts are written**

Find (locate by content — this is right after the per-concept print loop
in the ATLAS section, and right before the `beat_ids = {b.id for b in beats}`
line that starts the relations/edges section):
```python
    art.save_json("07_atlas", "concepts", [c.model_dump() for c in concepts])
    print(f"Concepts mined: {len(concepts)}")
    for c in concepts:
        cites = [format_citation(recording.slug, next(
            (b.start_s for b in beats if b.id == ref.beat_id), 0.0
        )) for ref in c.taught_in[:1]]
        print(f"  - {c.canonical_name}  [{', '.join(cites)}]")

    beat_ids = {b.id for b in beats}
```
Replace with:
```python
    art.save_json("07_atlas", "concepts", [c.model_dump() for c in concepts])
    print(f"Concepts mined: {len(concepts)}")
    for c in concepts:
        cites = [format_citation(recording.slug, next(
            (b.start_s for b in beats if b.id == ref.beat_id), 0.0
        )) for ref in c.taught_in[:1]]
        print(f"  - {c.canonical_name}  [{', '.join(cites)}]")

    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    for c in concepts:
        write_concept_wiki_page(WIKI_DIR, c, beats, board_states, recording.slug)
    print(f"Wiki pages updated in {WIKI_DIR}")

    beat_ids = {b.id for b in beats}
```

- [ ] **Step 5: Run the full suite**

Run: `uv run --env-file .env python -m pytest -q`
Expected: 131 passed — this task wires existing tested functions in, no
new unit tests of its own (matches this codebase's established convention
for `ingest.py` wiring steps — see Plan 1's Tasks 1-3, which followed the
same pattern: the pure logic is unit-tested, `run_ingest`'s own body is
verified by the full suite staying green plus a real end-to-end smoke run).

- [ ] **Step 6: Commit**

```bash
git add shruti/ingest.py
git commit -m "feat: wire per-recording narrative and per-concept wiki writers into ingest.py"
```

---

## After this plan

Update `memory_nityam_architecture/README.md`'s "Resolved" section: the
`Concept.definition`-is-never-set gap this plan closes isn't currently
listed as its own numbered gap (it was described in prose during the
design review, not filed as a numbered item) — add an entry describing
the fix and pointing at `vault/wiki/` and `vault/notes/` as the new
storage layer.

Then re-run the full pipeline once against one of the two already-
downloaded test videos (`.local/videos/d_jnEkwCA6I.mp4` or
`.local/videos/b6c87594bb.mp4`) via
`uv run --env-file .env python scripts/ingest_video.py <path>` and
directly inspect: a real `vault/notes/<slug>.md` file with interleaved
board content, and real `vault/wiki/<concept_id>.md` pages with an actual
definition (not blank) and a real citation. This is the same LLM-as-judge
verification discipline used throughout this project — read the actual
generated files, don't just trust the printed summary.
