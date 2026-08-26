# SHRUTI Phase 0 — Citation, Provenance & Semantic Retrieval — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every Concept/Edge/Misconception in VAULT a human-readable, resolvable citation back to a real video timestamp, enforce the provenance invariant at write time instead of only at CI-eval time, and wire the currently-dead semantic embedding index into actual fused (graph + semantic) retrieval — the three things SMRITI's memory layer directly depends on Shruti for.

**Architecture:** Six self-contained additions to the existing VAULT/LENS/stages/atlas layers, each built and tested exactly the way the rest of this codebase already is — direct fixture construction against a real, transaction-rolled-back Postgres connection (the `db_conn` fixture), no mocked database. No task in this plan touches `agents/pipeline.py`, ADK tool-calling, or the Runner — that's a distinct, larger, deliberately separate effort (see Constraints below).

**Tech Stack:** Python 3.12, `google-adk==2.7.1`, `asyncpg`, PostgreSQL + pgvector, `google-genai`, pytest + pytest-asyncio, `uv`.

**Spec:** This plan implements the Phase 0 scope agreed in `memory_nityam_architecture/README.md`'s master build order, refines the stale-embedder-model correction documented in that same file's "Resolved via LLM-as-judge review" section, and is a direct continuation of `shruti_implementation_plan.md` (the original 22-task plan this codebase was built from — read that first for full context on every file this plan touches). It does **not** revise or re-execute any task in that plan.

## Global Constraints

- Pin `google-adk==2.7.1` — do not assume a different version's API surface.
- Follow the existing codebase's async convention: VAULT/LENS functions are `async def` over `asyncpg` connections; stage functions that call Gemini are currently synchronous (`def`, not `async def`) — this plan's new Gemini-calling code (Task 5) uses `async def` and `await`, matching `shruti/gemini/client.py`'s own convention, not the stage functions' — this is a **known existing inconsistency in the codebase**, not something this plan resolves; flagged in Task 5.
- Embedding vectors are `vector(3072)` in Postgres (see `infra/migrations/004_index.sql`) — `gemini-embedding-2`'s default output dimensionality is 3072, so no schema change is needed for the model swap.
- Every new SQL migration file goes in `infra/migrations/`, named `NNN_<name>.sql` continuing from `004_index.sql` (this plan adds `005_recording_slug.sql`), applied via the existing `apply_migrations()` in `shruti/db.py`.
- Match existing test conventions exactly: `@pytest.mark.asyncio`, the shared `db_conn` fixture from `tests/conftest.py` (real Postgres, wrapped in a rolled-back transaction — no separate cleanup needed), and construct fixtures the same way `tests/vault/test_atlas_store.py` / `tests/vault/test_lens_retrievers.py` / `tests/vault/test_adk_tools.py` already do (a `Recording`, `write_recording`, a `Beat`, `write_beats`, then the thing under test).
- **Out of scope, deliberately** (do not touch, do not fix in passing, even if noticed): wiring `GATE_TOOLS`/`PULSE_TOOLS` into `agents/pipeline.py`'s `LlmAgent`s; composing Pulse/Slate/Echo/Point/Weave/Glyph/Atlas into single orchestration functions; attaching `ProvenancePlugin`/`CostGuardPlugin` to a real `Runner`; an `ingest` CLI command; making `CostTracker` compute real costs; the `extract()` wrapper's inconsistent use across stages; `Beat.board_state_id`/`board_delta`/`concepts` never being populated; `Timeline`'s missing vault writer; `canonicalize.py`'s string-only similarity. All of these are real, separately confirmed gaps — they belong to the next plan ("Phase 0.5 — pipeline integration"), not this one.

---

### Task 1: Citation module — format and resolve `shruti:<slug> @mm:ss`

**Files:**
- Create: `shruti/lens/citations.py`
- Test: `tests/lens/test_citations.py`

**Interfaces:**
- Consumes: nothing (pure functions, no DB, no Gemini).
- Produces: `seconds_to_mmss(seconds: float) -> str`, `mmss_to_seconds(mmss: str) -> float`, `format_citation(slug: str, seconds: float) -> str`, `resolve_citation(citation: str) -> tuple[str, float]`. Task 3 consumes `format_citation`.

- [ ] **Step 1: Write the failing test**

```python
# tests/lens/__init__.py
```

```python
# tests/lens/test_citations.py
import pytest
from shruti.lens.citations import seconds_to_mmss, mmss_to_seconds, format_citation, resolve_citation


def test_seconds_to_mmss_pads_seconds_under_ten():
    assert seconds_to_mmss(23) == "0:23"
    assert seconds_to_mmss(83) == "1:23"


def test_seconds_to_mmss_handles_over_an_hour():
    assert seconds_to_mmss(3661) == "61:01"


def test_mmss_to_seconds_is_the_inverse():
    assert mmss_to_seconds("1:23") == 83.0
    assert mmss_to_seconds("61:01") == 3661.0


def test_format_citation_produces_expected_shape():
    assert format_citation("physics_projectile_01", 83) == "shruti:physics_projectile_01 @1:23"


def test_resolve_citation_round_trips_with_format_citation():
    citation = format_citation("kinematics_lecture_04", 725)
    slug, seconds = resolve_citation(citation)
    assert slug == "kinematics_lecture_04"
    assert seconds == 725.0


def test_resolve_citation_rejects_malformed_input():
    with pytest.raises(ValueError):
        resolve_citation("not a citation")
    with pytest.raises(ValueError):
        resolve_citation("shruti:missing-timestamp")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/lens/test_citations.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shruti.lens.citations'`

- [ ] **Step 3: Write the implementation**

```python
# shruti/lens/citations.py
import re

_CITATION_RE = re.compile(r"^shruti:(?P<slug>\S+) @(?P<mmss>\d+:\d{2})$")


def seconds_to_mmss(seconds: float) -> str:
    total = int(round(seconds))
    minutes, secs = divmod(total, 60)
    return f"{minutes}:{secs:02d}"


def mmss_to_seconds(mmss: str) -> float:
    minutes, secs = mmss.split(":")
    return float(minutes) * 60 + float(secs)


def format_citation(slug: str, seconds: float) -> str:
    """The one canonical citation shape SMRITI cites, e.g.
    '[-> shruti:physics_projectile_01 @1:23]'. Keep the space before '@' —
    it's what makes the regex below unambiguous to parse back."""
    return f"shruti:{slug} @{seconds_to_mmss(seconds)}"


def resolve_citation(citation: str) -> tuple[str, float]:
    """Inverse of format_citation. Raises ValueError on anything that isn't
    exactly the format this module produces — a citation that can't be
    resolved is worse than one that's obviously rejected."""
    match = _CITATION_RE.match(citation)
    if not match:
        raise ValueError(f"not a valid shruti citation: {citation!r}")
    return match.group("slug"), mmss_to_seconds(match.group("mmss"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/lens/test_citations.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add shruti/lens/citations.py tests/lens/__init__.py tests/lens/test_citations.py
git commit -m "feat: add shruti:<slug> @mm:ss citation formatter and resolver"
```

---

### Task 2: Recording gets a human-readable slug

**Files:**
- Create: `infra/migrations/005_recording_slug.sql`
- Modify: `shruti/contracts/recording.py`, `shruti/vault/reel.py:write_recording`, `shruti/stages/gate/admit.py`
- Test: `tests/vault/test_reel_slug.py`, `tests/stages/gate/test_admit_slug.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Recording.slug: str | None`; `_slugify(source_uri: str, rec_id: str) -> str` (in `admit.py`); `write_recording` now persists `slug`. Task 3 consumes the persisted `slug` column directly via SQL.

- [ ] **Step 1: Write the failing tests**

```python
# tests/vault/test_reel_slug.py
import pytest
from shruti.contracts.recording import Recording, SurfaceKind
from shruti.vault.reel import write_recording


@pytest.mark.asyncio
async def test_write_recording_persists_slug(db_conn):
    rec = Recording(id="r_slug_1", slug="physics_projectile_2d_a1b2c3d4",
                     source_uri="gs://x/physics_projectile_2d.mp4",
                     duration_s=10.0, fps=30.0, surface_kind=SurfaceKind.BLACKBOARD)
    await write_recording(db_conn, rec)
    row = await db_conn.fetchrow("SELECT slug FROM recording WHERE id=$1", rec.id)
    assert row["slug"] == "physics_projectile_2d_a1b2c3d4"


@pytest.mark.asyncio
async def test_write_recording_allows_null_slug(db_conn):
    rec = Recording(id="r_slug_2", source_uri="gs://x/y.mp4",
                     duration_s=10.0, fps=30.0, surface_kind=SurfaceKind.BLACKBOARD)
    await write_recording(db_conn, rec)
    row = await db_conn.fetchrow("SELECT slug FROM recording WHERE id=$1", rec.id)
    assert row["slug"] is None
```

```python
# tests/stages/gate/test_admit_slug.py
from shruti.stages.gate.admit import _slugify


def test_slugify_sanitizes_filename_and_appends_short_id():
    slug = _slugify("gs://bucket/Physics Projectile 2D!!.mp4", "a1b2c3d4e5f6")
    assert slug == "physics_projectile_2d_a1b2c3d4"


def test_slugify_strips_extension_and_lowercases():
    slug = _slugify("/local/path/Kinematics-Lecture_04.MOV", "ffffffffffff")
    assert slug.startswith("kinematics_lecture_04_")
    assert slug == slug.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/vault/test_reel_slug.py tests/stages/gate/test_admit_slug.py -v`
Expected: FAIL — `column "slug" of relation "recording" does not exist` (first file) and `ImportError: cannot import name '_slugify'` (second file)

- [ ] **Step 3: Write the implementation**

```sql
-- infra/migrations/005_recording_slug.sql
ALTER TABLE recording ADD COLUMN slug TEXT;
CREATE UNIQUE INDEX recording_slug_idx ON recording (slug) WHERE slug IS NOT NULL;
```

```python
# shruti/contracts/recording.py — add one field to the existing Recording model
# (full file, since the diff is small and this is the whole contract)
from enum import Enum
from pydantic import BaseModel


class SurfaceKind(str, Enum):
    BLACKBOARD = "blackboard"
    WHITEBOARD = "whiteboard"
    SLIDES = "slides"
    MIXED = "mixed"
    TALKING_HEAD = "talking_head"


class Recording(BaseModel):
    id: str
    slug: str | None = None
    source_uri: str
    title: str | None = None
    duration_s: float
    fps: float
    width: int | None = None
    height: int | None = None
    surface_kind: SurfaceKind
    subject: str | None = None
    grade: int | None = None
    chapter: str | None = None
    reel_version: int = 1
```

```python
# shruti/vault/reel.py — modify write_recording only, rest of the file unchanged
async def write_recording(conn, recording: Recording) -> None:
    await conn.execute(
        """INSERT INTO recording (id, slug, source_uri, title, duration_s, fps, width, height,
                                   surface_kind, subject, grade, chapter, reel_version)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
           ON CONFLICT (id) DO NOTHING""",
        recording.id, recording.slug, recording.source_uri, recording.title,
        recording.duration_s, recording.fps, recording.width, recording.height,
        recording.surface_kind.value, recording.subject, recording.grade,
        recording.chapter, recording.reel_version,
    )
```

```python
# shruti/stages/gate/admit.py — add _slugify and use it in admit()
import re
from shruti.contracts.recording import Recording
from shruti.stages.gate.probe import probe_video, fingerprint
from shruti.stages.gate.normalize import normalize_video
from shruti.stages.gate.surface import classify_surface


def _slugify(source_uri: str, rec_id: str) -> str:
    """Human-readable, stable, collision-resistant: sanitized filename plus
    an 8-char disambiguator from the content hash. Doesn't need subject/
    chapter — admit() doesn't have those yet, and the slug must not block
    on metadata that arrives later."""
    name = source_uri.rsplit("/", 1)[-1]
    name = re.sub(r"\.[^.]+$", "", name)
    name = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    return f"{name}_{rec_id[:8]}"


def admit(source_uri: str, client, workdir: str) -> Recording:
    meta = probe_video(source_uri)
    video_path, _audio_path = normalize_video(source_uri, workdir)
    rec_id = fingerprint(video_path)
    surface_kind = classify_surface(client, frames=[])
    return Recording(
        id=rec_id,
        slug=_slugify(source_uri, rec_id),
        source_uri=source_uri,
        duration_s=meta["duration_s"],
        fps=meta["fps"],
        width=meta["width"],
        height=meta["height"],
        surface_kind=surface_kind,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/vault/test_reel_slug.py tests/stages/gate/test_admit_slug.py -v`
Expected: PASS (4 tests). Also re-run the full existing suite to confirm nothing broke: `uv run pytest -v`

- [ ] **Step 5: Commit**

```bash
git add infra/migrations/005_recording_slug.sql shruti/contracts/recording.py \
        shruti/vault/reel.py shruti/stages/gate/admit.py \
        tests/vault/test_reel_slug.py tests/stages/gate/test_admit_slug.py
git commit -m "feat: give Recording a human-readable slug, populated at admit time"
```

---

### Task 3: `recall_lesson` returns a resolvable citation

**Files:**
- Modify: `shruti/lens/adk_tools.py`
- Test: `tests/vault/test_adk_tools.py`

**Interfaces:**
- Consumes: `format_citation` (Task 1), the `recording.slug` column (Task 2).
- Produces: `recall_lesson(...)`'s return dict now includes a `citation` key (formatted string, or `None` if the recording has no slug).

- [ ] **Step 1: Write the failing test**

Add to the existing `tests/vault/test_adk_tools.py` (do not remove or modify the two existing tests in that file — this is a new test alongside them):

```python
@pytest.mark.asyncio
async def test_recall_lesson_includes_a_resolvable_citation(db_conn):
    rec = Recording(id="r_tool_3", slug="physics_projectile_2d_a1b2c3d4",
                     source_uri="gs://x", duration_s=10.0, fps=30.0,
                     surface_kind=SurfaceKind.BLACKBOARD)
    await write_recording(db_conn, rec)
    beat = Beat(id="b_tool_3", recording_id=rec.id, idx=0, start_s=23.0, end_s=30.0,
                kind="derive", transcript="range formula for projectile motion")
    await write_beats(db_conn, [beat])
    concept = Concept(id="proj_range_tool", canonical_name="projectile range",
                       taught_in=[BeatRef(beat_id=beat.id, relation="taught_in")])
    await write_concepts(db_conn, [concept])

    tools = _build_lesson_functions(db_conn)
    result = await tools["recall_lesson"]("proj_range_tool", [rec.id])
    assert result["citation"] == "shruti:physics_projectile_2d_a1b2c3d4 @0:23"


@pytest.mark.asyncio
async def test_recall_lesson_citation_is_none_without_a_slug(db_conn):
    rec = Recording(id="r_tool_4", source_uri="gs://x", duration_s=10.0, fps=30.0,
                     surface_kind=SurfaceKind.BLACKBOARD)
    await write_recording(db_conn, rec)
    beat = Beat(id="b_tool_4", recording_id=rec.id, idx=0, start_s=1.0, end_s=2.0,
                kind="explain", transcript="x")
    await write_beats(db_conn, [beat])
    concept = Concept(id="no_slug_concept", canonical_name="no slug concept",
                       taught_in=[BeatRef(beat_id=beat.id, relation="taught_in")])
    await write_concepts(db_conn, [concept])

    tools = _build_lesson_functions(db_conn)
    result = await tools["recall_lesson"]("no_slug_concept", [rec.id])
    assert result["citation"] is None
```

(These two tests need `Recording`, `SurfaceKind`, `Beat`, `Concept`, `BeatRef`, `write_recording`, `write_beats`, `write_concepts`, `_build_lesson_functions` imported — all already imported at the top of `tests/vault/test_adk_tools.py` per the existing file.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/vault/test_adk_tools.py -v -k citation`
Expected: FAIL — `KeyError: 'citation'`

- [ ] **Step 3: Write the implementation**

```python
# shruti/lens/adk_tools.py — full file, since recall_lesson's body changes
from shruti.lens.retrievers import graph_traverse, timeline_lookup
from shruti.lens.citations import format_citation
from shruti.vault.ledger import board_state_at


def _build_lesson_functions(conn) -> dict:
    async def recall_lesson(concept_id: str, recording_ids: list[str]) -> dict:
        """Retrieve how this student's own teacher taught this concept."""
        beats = await timeline_lookup(conn, concept_id, recording_ids)
        if not beats:
            return {"found": False, "fallback": "generic"}
        b = beats[0]
        bs = await board_state_at(conn, b.recording_id, b.start_s)
        slug_row = await conn.fetchrow(
            "SELECT slug FROM recording WHERE id=$1", b.recording_id
        )
        citation = (
            format_citation(slug_row["slug"], b.start_s)
            if slug_row and slug_row["slug"] else None
        )
        return {
            "found": True,
            "recording_id": b.recording_id,
            "timestamp": b.start_s,
            "citation": citation,
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/vault/test_adk_tools.py -v`
Expected: PASS (5 tests — the 2 new plus the 3 already there)

- [ ] **Step 5: Commit**

```bash
git add shruti/lens/adk_tools.py tests/vault/test_adk_tools.py
git commit -m "feat: recall_lesson returns a resolvable shruti:<slug> @mm:ss citation"
```

---

### Task 4: Enforce the provenance invariant at write time

**Files:**
- Modify: `shruti/vault/atlas_store.py`
- Test: `tests/vault/test_atlas_store.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `class ProvenanceViolation(Exception)`; `check_provenance_invariant(conn, *, only: dict[str, list[str]] | None = None)` (backward-compatible — existing callers that pass no `only` keep checking the whole table, exactly as today); `write_concepts`/`write_edges`/`write_misconceptions` now raise `ProvenanceViolation` if any row they just wrote has no `beat_ref`.

- [ ] **Step 1: Write the failing test**

Add to the existing `tests/vault/test_atlas_store.py` (the existing test in that file stays unchanged):

```python
@pytest.mark.asyncio
async def test_write_concepts_raises_on_a_concept_with_no_evidence(db_conn):
    from shruti.vault.atlas_store import ProvenanceViolation
    bad = Concept(id="c_no_evidence", canonical_name="no evidence concept", taught_in=[])
    with pytest.raises(ProvenanceViolation):
        await write_concepts(db_conn, [bad])


@pytest.mark.asyncio
async def test_write_concepts_with_evidence_does_not_raise(db_conn):
    rec = Recording(id="r_test_4", source_uri="gs://x", duration_s=10.0, fps=30.0,
                     surface_kind=SurfaceKind.BLACKBOARD)
    await write_recording(db_conn, rec)
    beat = Beat(id="b_test_4", recording_id=rec.id, idx=0, start_s=0.0, end_s=1.0,
                kind="explain", transcript="x")
    await write_beats(db_conn, [beat])
    good = Concept(id="c_has_evidence", canonical_name="has evidence concept",
                    taught_in=[BeatRef(beat_id=beat.id, relation="taught_in")])
    await write_concepts(db_conn, [good])  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/vault/test_atlas_store.py -v -k evidence`
Expected: FAIL — `ImportError: cannot import name 'ProvenanceViolation'`, then (after adding the import) the first test fails because nothing raises yet.

- [ ] **Step 3: Write the implementation**

```python
# shruti/vault/atlas_store.py — full file, since check_provenance_invariant's
# signature changes and all three writers gain a call at the end
from shruti.contracts.atlas import Concept, Edge, Misconception


class ProvenanceViolation(Exception):
    """A Concept/Edge/Misconception was written with no beat_ref pointing at
    it. This must fail loudly and immediately — see check_provenance_invariant's
    own framing: the correctness assertion, not a quality metric.

    Note for callers: this function does not manage its own transaction.
    If you need the write itself rolled back on violation (not just detected),
    wrap the call to write_concepts/write_edges/write_misconceptions in your
    own `async with conn.transaction():` block."""


async def write_concepts(conn, concepts: list[Concept]) -> None:
    for c in concepts:
        await conn.execute(
            """INSERT INTO concept (id, canonical_name, aliases, subject, grade, chapter,
                                     definition, atlas_version)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
               ON CONFLICT (id) DO NOTHING""",
            c.id, c.canonical_name, c.aliases, c.subject, c.grade, c.chapter,
            c.definition, c.atlas_version,
        )
        for ref in c.taught_in:
            await conn.execute(
                """INSERT INTO beat_ref (subject_kind, subject_id, beat_id, relation, atlas_version)
                   VALUES ('concept', $1, $2, $3, $4)""",
                c.id, ref.beat_id, ref.relation, c.atlas_version,
            )
    violations = await check_provenance_invariant(conn, only={"concept": [c.id for c in concepts]})
    if violations:
        raise ProvenanceViolation(violations)


async def write_edges(conn, edges: list[Edge]) -> None:
    for e in edges:
        await conn.execute(
            """INSERT INTO concept_edge (id, from_concept, to_concept, edge_type, weight,
                                          atlas_version)
               VALUES ($1,$2,$3,$4,$5,$6)
               ON CONFLICT (id) DO NOTHING""",
            e.id, e.from_concept, e.to_concept, e.edge_type, e.weight, e.atlas_version,
        )
        for ref in e.evidence:
            await conn.execute(
                """INSERT INTO beat_ref (subject_kind, subject_id, beat_id, relation, atlas_version)
                   VALUES ('edge', $1, $2, $3, $4)""",
                e.id, ref.beat_id, ref.relation, e.atlas_version,
            )
    violations = await check_provenance_invariant(conn, only={"edge": [e.id for e in edges]})
    if violations:
        raise ProvenanceViolation(violations)


async def write_misconceptions(conn, misconceptions: list[Misconception]) -> None:
    for m in misconceptions:
        await conn.execute(
            """INSERT INTO misconception (id, concept_id, statement, teacher_phrasing,
                                           correct_understanding, pre_empted_at_beat,
                                           board_region_id, atlas_version)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
               ON CONFLICT (id) DO NOTHING""",
            m.id, m.concept_id, m.statement, m.teacher_phrasing, m.correct_understanding,
            m.pre_empted_at_beat, m.board_region_id, m.atlas_version,
        )
        await conn.execute(
            """INSERT INTO beat_ref (subject_kind, subject_id, beat_id, relation, atlas_version)
               VALUES ('misconception', $1, $2, 'evidence_for', $3)""",
            m.id, m.pre_empted_at_beat, m.atlas_version,
        )
    violations = await check_provenance_invariant(
        conn, only={"misconception": [m.id for m in misconceptions]}
    )
    if violations:
        raise ProvenanceViolation(violations)


async def check_provenance_invariant(conn, *, only: dict[str, list[str]] | None = None) -> list[str]:
    """With `only=None` (the original behavior, still used by the CLI's
    provenance-check command and the E4 CI gate): checks every row in the
    database. With `only={"concept": [...]}` etc.: checks just those ids —
    used by the writers above so a single insert doesn't pay the cost of a
    full-table scan."""
    violations = []
    for table, kind in (("concept", "concept"), ("concept_edge", "edge"),
                         ("misconception", "misconception")):
        if only is not None:
            ids = only.get(kind, [])
            if not ids:
                continue
            rows = await conn.fetch(
                f"""SELECT t.id FROM {table} t
                    LEFT JOIN beat_ref r ON r.subject_kind=$1 AND r.subject_id=t.id
                    WHERE r.id IS NULL AND t.id = ANY($2)""",
                kind, ids,
            )
        else:
            rows = await conn.fetch(
                f"""SELECT t.id FROM {table} t
                    LEFT JOIN beat_ref r ON r.subject_kind=$1 AND r.subject_id=t.id
                    WHERE r.id IS NULL""",
                kind,
            )
        violations += [f"{kind} {r['id']} has no beat_ref" for r in rows]
    return violations
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/vault/test_atlas_store.py -v`
Expected: PASS (3 tests — the original plus the 2 new). Also confirm the CLI's `provenance-check` command and the E4 eval still work unchanged, since `check_provenance_invariant(conn)` with no `only` argument is unaffected: `uv run pytest tests/evals/test_e4_provenance_invariant.py tests/test_cli.py -v`

- [ ] **Step 5: Commit**

```bash
git add shruti/vault/atlas_store.py tests/vault/test_atlas_store.py
git commit -m "feat: enforce the provenance invariant at write time, scoped to the written batch"
```

---

### Task 5: Embed concepts and misconceptions into the (currently dead) vector index

**Files:**
- Modify: `shruti/config.py`
- Create: `shruti/stages/atlas/embed.py`
- Test: `tests/stages/atlas/test_embed.py`

**Interfaces:**
- Consumes: `write_embedding` (`shruti/vault/index.py`, unchanged), `Models().embedder` (Task 5 fixes its value).
- Produces: `embed_concepts(client, conn, concepts: list[Concept]) -> None`, `embed_misconceptions(client, conn, misconceptions: list[Misconception]) -> None`. Task 6 consumes the embeddings these write via `similarity_search`.

**Note on the exact Gemini embedding call**: this plan writes `await client.aio.models.embed_content(model=..., contents=text)` returning `response.embeddings[0].values`, matching the async style `shruti/gemini/client.py`'s own `extract()` already uses for `generate_content`. If the installed `google-genai` SDK's actual embedding method differs (different method name, sync vs. async, or response shape), **fix the call to match reality — the test's behavior (via the fake client below) defines the contract this module honors; the real SDK call in Step 3 is this plan's best-available inference and should be corrected against the installed package if it doesn't match.** This mirrors exactly how the original plan flagged the same kind of risk for `BasePlugin`'s import path in Task 18, and how that got resolved in practice.

- [ ] **Step 1: Write the failing test**

```python
# tests/stages/atlas/test_embed.py
import pytest
from shruti.contracts.atlas import Concept, Misconception
from shruti.stages.atlas.embed import embed_concepts, embed_misconceptions
from shruti.vault.index import similarity_search


class _FakeEmbedding:
    def __init__(self, values):
        self.values = values


class _FakeEmbedResponse:
    def __init__(self, values):
        self.embeddings = [_FakeEmbedding(values)]


class FakeEmbedClient:
    """Deterministic: returns a vector derived from the text's length, so
    two different texts get two different (but reproducible) embeddings."""

    class _Models:
        async def embed_content(self, model: str, contents: str):
            seed = float(len(contents) % 7 + 1)
            return _FakeEmbedResponse([seed] * 3072)

    def __init__(self):
        self.aio = type("Aio", (), {"models": self._Models()})()


@pytest.mark.asyncio
async def test_embed_concepts_writes_a_retrievable_embedding(db_conn):
    concept = Concept(id="c_embed_1", canonical_name="projectile range",
                       definition="the horizontal distance a projectile travels")
    await embed_concepts(FakeEmbedClient(), db_conn, [concept])
    results = await similarity_search(
        db_conn, [float(len(concept.definition) % 7 + 1)] * 3072, "concept", k=1
    )
    assert results[0]["ref_id"] == "c_embed_1"


@pytest.mark.asyncio
async def test_embed_misconceptions_writes_a_retrievable_embedding(db_conn):
    misconception = Misconception(
        id="m_embed_1", concept_id="c_embed_1",
        statement="treats (a+b)^2 as a^2+b^2",
        correct_understanding="(a+b)^2 = a^2 + 2ab + b^2",
        pre_empted_at_beat="b_unused",
    )
    await embed_misconceptions(FakeEmbedClient(), db_conn, [misconception])
    text = f"{misconception.statement} {misconception.correct_understanding}"
    results = await similarity_search(
        db_conn, [float(len(text) % 7 + 1)] * 3072, "misconception", k=1
    )
    assert results[0]["ref_id"] == "m_embed_1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/stages/atlas/test_embed.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shruti.stages.atlas.embed'`

- [ ] **Step 3: Write the implementation**

```python
# shruti/config.py — one-line change, rest of the file unchanged
# (per memory_nityam_architecture/README.md: gemini-embedding-001 is superseded;
# gemini-embedding-2 is current, GA, and defaults to the same 3072
# dimensionality already in infra/migrations/004_index.sql, so no schema
# change is required alongside this fix.)
from pydantic_settings import BaseSettings


class Models(BaseSettings):
    reasoner: str = "gemini-3.5-flash"
    router: str = "gemini-3.5-flash-lite"
    embedder: str = "gemini-embedding-2"


class Budget(BaseSettings):
    max_cost_per_recording_usd: float = 2.00
    use_batch_api: bool = True
    cache_ttl_seconds: int = 3600


class SlateConfig(BaseSettings):
    mask_tier: str = "framediff"
    board_vote_frames: int = 30
    composite_window_s: float = 45.0
    photometric_match: bool = True


class PulseConfig(BaseSettings):
    dense_fps: float = 1.0
    sparse_fps: float = 1 / 6
    erase_drop_ratio: float = 0.35
    erase_window_s: float = 3.0
    scene_threshold: float = 27.0
```

```python
# shruti/stages/atlas/embed.py
from shruti.config import Models
from shruti.contracts.atlas import Concept, Misconception
from shruti.vault.index import write_embedding


async def embed_concepts(client, conn, concepts: list[Concept]) -> None:
    """Embeds each concept's definition (falling back to its canonical name
    if no definition was mined) and writes it into the vector index. Call
    this after write_concepts persists the same concepts to the graph —
    the two indexes (graph, semantic) are meant to be fused at query time
    (Task 6), not kept in sync automatically."""
    for c in concepts:
        text = c.definition or c.canonical_name
        response = await client.aio.models.embed_content(model=Models().embedder, contents=text)
        vec = response.embeddings[0].values
        await write_embedding(conn, "concept", c.id, None, vec, text)


async def embed_misconceptions(client, conn, misconceptions: list[Misconception]) -> None:
    for m in misconceptions:
        text = f"{m.statement} {m.correct_understanding}"
        response = await client.aio.models.embed_content(model=Models().embedder, contents=text)
        vec = response.embeddings[0].values
        await write_embedding(conn, "misconception", m.id, None, vec, text)
```

```python
# tests/stages/atlas/__init__.py — if this file doesn't already exist from Task 13
# of the original plan, create it empty; if it exists, leave it untouched.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/stages/atlas/test_embed.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add shruti/config.py shruti/stages/atlas/embed.py tests/stages/atlas/test_embed.py
git commit -m "feat: embed concepts and misconceptions into the vector index; fix stale embedder model (E21)"
```

---

### Task 6: Fuse graph traversal and semantic search (reciprocal rank fusion)

**Files:**
- Create: `shruti/lens/fusion.py`
- Modify: `shruti/lens/adk_tools.py`
- Test: `tests/lens/test_fusion.py`, `tests/vault/test_adk_tools.py`

**Interfaces:**
- Consumes: `graph_traverse` (`shruti/lens/retrievers.py`, unchanged), `similarity_search` (`shruti/vault/index.py`, unchanged), the embeddings Task 5 writes.
- Produces: `reciprocal_rank_fusion(*ranked_id_lists, k=60) -> list[tuple[str, float]]` (pure function), `related_concepts(conn, concept_id, query_vec, k=8) -> list[dict]`. Exposed as a fifth ADK tool from `build_lesson_tools`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/lens/test_fusion.py
from shruti.lens.fusion import reciprocal_rank_fusion


def test_fusion_ranks_items_present_in_both_lists_above_single_list_items():
    fused = reciprocal_rank_fusion(["a", "b", "c"], ["b", "a", "d"])
    ranked_ids = [item_id for item_id, _score in fused]
    # "a" and "b" each appear near the top of both lists; "c" and "d" each
    # appear in only one list — the fused-in-both items must rank higher.
    assert set(ranked_ids[:2]) == {"a", "b"}
    assert set(ranked_ids[2:]) == {"c", "d"}


def test_fusion_handles_a_single_list_unchanged_in_relative_order():
    fused = reciprocal_rank_fusion(["x", "y", "z"])
    assert [item_id for item_id, _score in fused] == ["x", "y", "z"]


def test_fusion_handles_no_lists():
    assert reciprocal_rank_fusion() == []
```

Add to the existing `tests/vault/test_adk_tools.py`:

```python
@pytest.mark.asyncio
async def test_build_lesson_tools_returns_five_tools(db_conn):
    tools = build_lesson_tools(db_conn)
    assert len(tools) == 5
```

(This replaces the existing `test_build_lesson_tools_returns_four_tools` test — update the assertion from 4 to 5 rather than adding a duplicate test, since it's testing the same thing with the corrected expected count.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/lens/test_fusion.py tests/vault/test_adk_tools.py -v -k "fusion or five_tools"`
Expected: FAIL — `ModuleNotFoundError: No module named 'shruti.lens.fusion'`, and the tool-count test fails with `assert 4 == 5`

- [ ] **Step 3: Write the implementation**

```python
# shruti/lens/fusion.py
_RRF_K = 60  # standard reciprocal-rank-fusion damping constant


def reciprocal_rank_fusion(*ranked_id_lists: list[str], k: int = _RRF_K) -> list[tuple[str, float]]:
    """score(item) = sum over lists it appears in of 1 / (k + rank_in_that_list).
    An item near the top of several lists outranks one that's #1 in only one —
    this is the standard RRF formula, not a bespoke weighting."""
    scores: dict[str, float] = {}
    for ranked_ids in ranked_id_lists:
        for rank, item_id in enumerate(ranked_ids, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)


async def related_concepts(conn, concept_id: str, query_vec: list[float], k: int = 8) -> list[dict]:
    """The dual-index retrieval SMRITI's grounding needs: graph structure
    (REQUIRES prerequisites) fused with semantic similarity, so a query
    doesn't have to choose one retrieval mode over the other."""
    from shruti.lens.retrievers import graph_traverse
    from shruti.vault.index import similarity_search

    graph_hits = await graph_traverse(conn, concept_id, "REQUIRES", depth=2)
    graph_ids = [h["concept_id"] for h in graph_hits]
    semantic_hits = await similarity_search(conn, query_vec, "concept", k=k)
    semantic_ids = [h["ref_id"] for h in semantic_hits]
    fused = reciprocal_rank_fusion(graph_ids, semantic_ids)
    return [{"concept_id": item_id, "score": score} for item_id, score in fused[:k]]
```

```python
# shruti/lens/adk_tools.py — add related_concepts_semantic as a fifth tool.
# Full file since _build_lesson_functions gains an entry.
from shruti.lens.retrievers import graph_traverse, timeline_lookup
from shruti.lens.citations import format_citation
from shruti.lens.fusion import related_concepts
from shruti.vault.ledger import board_state_at


def _build_lesson_functions(conn) -> dict:
    async def recall_lesson(concept_id: str, recording_ids: list[str]) -> dict:
        """Retrieve how this student's own teacher taught this concept."""
        beats = await timeline_lookup(conn, concept_id, recording_ids)
        if not beats:
            return {"found": False, "fallback": "generic"}
        b = beats[0]
        bs = await board_state_at(conn, b.recording_id, b.start_s)
        slug_row = await conn.fetchrow(
            "SELECT slug FROM recording WHERE id=$1", b.recording_id
        )
        citation = (
            format_citation(slug_row["slug"], b.start_s)
            if slug_row and slug_row["slug"] else None
        )
        return {
            "found": True,
            "recording_id": b.recording_id,
            "timestamp": b.start_s,
            "citation": citation,
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

    async def related_concepts_semantic(concept_id: str, query_embedding: list[float]) -> list[dict]:
        """Graph structure (REQUIRES) fused with semantic similarity — the
        dual-index SKG retrieval, not graph-only or embedding-only."""
        return await related_concepts(conn, concept_id, query_embedding)

    return {
        "recall_lesson": recall_lesson,
        "prerequisites_of": prerequisites_of,
        "known_misconceptions": known_misconceptions,
        "board_at": board_at,
        "related_concepts_semantic": related_concepts_semantic,
    }


def build_lesson_tools(conn) -> list:
    from google.adk.tools import FunctionTool
    return [FunctionTool(f) for f in _build_lesson_functions(conn).values()]
```

Update the existing test in `tests/vault/test_adk_tools.py` — change:
```python
async def test_build_lesson_tools_returns_four_tools(db_conn):
    tools = build_lesson_tools(db_conn)
    assert len(tools) == 4
```
to:
```python
async def test_build_lesson_tools_returns_five_tools(db_conn):
    tools = build_lesson_tools(db_conn)
    assert len(tools) == 5
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/lens/test_fusion.py tests/vault/test_adk_tools.py -v`
Expected: PASS (3 new fusion tests + 5 adk_tools tests, all passing)

- [ ] **Step 5: Run the full test suite**

Run: `uv run pytest -v`
Expected: PASS, no regressions anywhere in the suite.

- [ ] **Step 6: Commit**

```bash
git add shruti/lens/fusion.py shruti/lens/adk_tools.py tests/lens/test_fusion.py tests/vault/test_adk_tools.py
git commit -m "feat: fuse graph traversal and semantic search via reciprocal rank fusion"
```

---

## Self-review notes

- **Spec coverage**: the three things `memory_nityam_architecture/README.md`'s Phase 0 row names — citation resolver + human-readable recording IDs (Tasks 1–3), write-time provenance enforcement (Task 4), the embedding index wired into fused retrieval (Tasks 5–6) — each has a task. E21 (stale embedder model) is folded into Task 5 rather than a separate task, since fixing it is a one-line prerequisite of the same change.
- **Placeholder scan**: no task contains "TBD," "add error handling," or an unshown test — every step has real, complete code, matching the level of detail `shruti_implementation_plan.md`'s own 22 tasks were written at.
- **Type consistency checked**: `Concept`/`Edge`/`Misconception`/`BeatRef`/`Recording` field names and types match `shruti/contracts/atlas.py` and `shruti/contracts/recording.py` exactly as they exist today (verified by reading those files directly, not from memory). `conn` means "an `asyncpg` connection or pool" consistently, matching every existing VAULT/LENS function. `client` in Task 5 means a `google.genai` client object, matching every existing stage function's parameter name.
- **Known open risk, called out rather than silently assumed** (matching how the original plan flagged its own `BasePlugin` import-path risk in Task 18): Task 5's exact embedding API call (`client.aio.models.embed_content`) is inferred from `shruti/gemini/client.py`'s existing async convention, not verified against the installed `google-genai` package's actual method signature. Fix the call in Task 5 Step 3 if it doesn't match — the fake-client test contract, not this plan's guess at the real SDK shape, is the source of truth for what `embed_concepts`/`embed_misconceptions` must do.
- **Explicitly not attempted**: any change to `agents/pipeline.py`, `agents/tools.py`'s `GATE_TOOLS`/`PULSE_TOOLS` wiring, the Runner, or an `ingest` CLI command — confirmed (by reading `shruti_implementation_plan.md`'s Task 18 test suite directly) that the original plan never wired these either, so this is a real, separate, pre-existing gap and not something this plan's scope silently expanded to cover. That work is Phase 0.5, planned separately.

---

**Cut order under time pressure**: Task 6 (fusion) depends on Task 5 (embeddings) existing but is otherwise the most deferrable — Tasks 1–4 alone already deliver a working, resolvable citation system and write-time provenance enforcement, which is most of the value. **Never cut**: Task 4 — write-time provenance enforcement is the difference between "the citation invariant is real" and "the citation invariant is a CI check someone can forget to run."
