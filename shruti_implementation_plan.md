# SHRUTI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build SHRUTI — the batch pipeline that turns a lecture video into a timestamped, provenance-tracked knowledge base (Reel/Ledger/Atlas) — deployed on the managed Gemini Enterprise Agent Platform, demo-ready inside a 48-hour window.

**Architecture:** A `SequentialAgent` tree (Gate → Pulse → Perceive[Slate‖Echo‖Point] → Weave → Glyph → Atlas → Vault) built on Google ADK, with deterministic CV/math for timing and geometry, Gemini for semantics, and Postgres+pgvector+GCS for storage. Deployed to Agent Runtime (not plain Cloud Run) so it gets automatic Agent Registry registration; instrumented with OpenTelemetry for real trace/observability.

**Tech Stack:** Python 3.12+, `google-adk` 2.7.1 (pinned), `google-genai` SDK (not the deprecated `vertexai.*` submodules), `asyncpg` + Postgres 16 + `pgvector`, `google-cloud-storage`, OpenCV, PySceneDetect, `pytest` + `pytest-asyncio`, `uv` for dependency management, `agents-cli` for deploy.

**Spec:** `shruti_architecture.md` (v0.1, pipeline design D1–D3) + `shruti_platform_alignment.md` (v0.2, platform decisions D4–D9) + `shruti_implementation.md` (v0.1, original code sketches — this plan supersedes its task ordering with TDD steps, and its D4-era assumptions are corrected per the alignment doc). Research backing every platform claim: `wiki/`.

## Global Constraints

- Python 3.12+, dependency-managed with `uv`, not `pip` directly.
- `google-adk==2.7.1` pinned exactly (see `wiki/adk-and-a2ui.md` — ADK 2.0 changed the session schema; know which side of the line you're on).
- Never import `vertexai.generative_models`, `.language_models`, `.vision_models`, `.tuning`, or `.caching` for content generation — these are past their removal date. Use `google-genai` (`from google import genai`) for every extraction/generation call. **Exception**: `vertexai.Client` + `.agent_engines.*` remains the current, documented path specifically for Agent Engine/Runtime *deployment management* (create/get/delete) — see `wiki/platform-build.md`. Task 21's verification script uses it for exactly that narrow purpose; no other task should import `vertexai` at all.
- Model IDs live only in `shruti/config.py` — never hardcode a model string in a stage module.
- Every stage is independently re-runnable against cached upstream output — a stage module only imports from `shruti/contracts/` plus its own stage, never a sibling stage's internals. **Narrow exception**: PULSE's `ink_curve` (Task 5) may import SLATE's pure, stateless `rectify()` (Task 7) — geometry rectification is shared infrastructure, not stage-specific state, and importing a pure function doesn't break either stage's independent re-runnability against cached data. No other cross-stage import is permitted without the same justification.
- Cost ceiling: **$2.00 per recording** (enforced by `CostGuardPlugin`, Task 18).
- Batch API (Task 17: `submit_batch`/`poll_batch`/`collect_batch`) exists and must be used at the *orchestration* level once a full end-to-end run is wired up — collecting a whole recording's GLYPH/POINT/ATLAS calls into one job, per `shruti_architecture.md` §8. Individual stage functions (Tasks 9, 10, 11, 12, 13) correctly call `client.models.generate_content` directly and are tested that way — restructuring them to defer into a batch job is an orchestration-level integration explicitly **out of scope for the 48-hour build** (no task currently owns it; costs ~2x list price without the 50% batch discount, which does not change demo feasibility against the $2/recording ceiling). Do not treat a stage's direct call as a defect against this line.
- SLATE must never invent occluded board content — the `unfilled` mask is always passed to GLYPH as an explicit no-guess instruction (Task 12).
- Every `Concept`, `Edge`, and `Misconception` row must resolve ≥1 valid `BeatRef` to a real span — enforced as a CI-failing check (E4, Task 19), not just a quality metric.
- Deployment target is `agent_engine`, not `cloud_run` (D4) — this is a config value in Task 21, not a late add-on; don't write deploy scripts that assume Cloud Run is final.
- All Gemini-calling stage modules take a `client` parameter (dependency injection) so tests run against a fake client, never real network calls.

---

## Task 1: Repo scaffolding

**Files:**
- Create: `pyproject.toml`, `.env.example`, `.gitignore`
- Create: `shruti/__init__.py`, `shruti/config.py`
- Create: `docker/compose.yaml`
- Create: `justfile`

**Interfaces:**
- Produces: `shruti.config.Models` (fields: `reasoner: str`, `router: str`, `embedder: str`), `shruti.config.Budget` (fields: `max_cost_per_recording_usd: float`, `use_batch_api: bool`, `cache_ttl_seconds: int`), `shruti.config.SlateConfig` (fields: `mask_tier: str`, `board_vote_frames: int`, `composite_window_s: float`, `photometric_match: bool`), `shruti.config.PulseConfig` (fields: `dense_fps: float`, `sparse_fps: float`, `erase_drop_ratio: float`, `erase_window_s: float`, `scene_threshold: float`).

- [ ] **Step 1: Initialize the project**

```bash
mkdir -p "shruti" && cd "$(dirname "$0" 2>/dev/null || pwd)"
git init
uv init --python 3.12 --no-readme
uv add "google-adk==2.7.1" "google-genai>=1.0" pydantic pydantic-settings asyncpg \
       "google-cloud-storage" opencv-python-headless numpy scenedetect typer \
       python-ffmpeg-normalize 2>/dev/null || true
uv add --dev pytest pytest-asyncio pytest-cov ruff
```

- [ ] **Step 2: Write `shruti/config.py`**

```python
# shruti/config.py
from pydantic_settings import BaseSettings


class Models(BaseSettings):
    reasoner: str = "gemini-3.5-flash"
    router: str = "gemini-3.5-flash-lite"
    embedder: str = "gemini-embedding-001"


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

- [ ] **Step 3: Write the smoke test**

```python
# tests/test_config.py
from shruti.config import Models, Budget, SlateConfig, PulseConfig


def test_config_defaults_load():
    assert Models().reasoner == "gemini-3.5-flash"
    assert Budget().max_cost_per_recording_usd == 2.00
    assert SlateConfig().mask_tier == "framediff"
    assert PulseConfig().dense_fps == 1.0
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (this is scaffolding, not TDD-first — the config module has no behavior to fail against, so write-then-verify is correct here)

- [ ] **Step 5: Write `docker/compose.yaml`**

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: shruti
      POSTGRES_PASSWORD: shruti
      POSTGRES_DB: shruti
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]
  gcs-emulator:
    image: fsouza/fake-gcs-server:latest
    command: ["-scheme", "http", "-port", "4443"]
    ports: ["4443:4443"]
volumes:
  pgdata:
```

- [ ] **Step 6: Write `.env.example`**

```
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
DATABASE_URL=postgresql://shruti:shruti@localhost:5432/shruti
GCS_BUCKET=your-bucket
STORAGE_EMULATOR_HOST=http://localhost:4443
```

- [ ] **Step 7: Write `.gitignore`**

```
.venv/
__pycache__/
*.pyc
.env
data/
.pytest_cache/
.superpowers/
```

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .env.example .gitignore shruti/ docker/ justfile tests/
git commit -m "chore: scaffold SHRUTI project structure"
```

---

## Task 2: Contracts — pydantic models

**Files:**
- Create: `shruti/contracts/__init__.py`
- Create: `shruti/contracts/recording.py`
- Create: `shruti/contracts/timeline.py`
- Create: `shruti/contracts/board.py`
- Create: `shruti/contracts/speech.py`
- Create: `shruti/contracts/beat.py`
- Create: `shruti/contracts/atlas.py`
- Test: `tests/contracts/test_contracts.py`

**Interfaces:**
- Produces (every later task imports these, exact names): `Recording`, `SurfaceKind` (`recording.py`); `Shot`, `EraseEvent`, `SamplePlanRegion`, `Timeline` (`timeline.py`); `Region`, `BoardContent`, `BoardState` (`board.py`); `LanguageSpan`, `Utterance`, `Deixis` (`speech.py`); `Beat` (`beat.py`); `BeatRef`, `Concept`, `Edge`, `Misconception` (`atlas.py`).

- [ ] **Step 1: Write the failing test**

```python
# tests/contracts/test_contracts.py
import pytest
from pydantic import ValidationError
from shruti.contracts.recording import Recording, SurfaceKind
from shruti.contracts.timeline import Shot, EraseEvent, SamplePlanRegion, Timeline
from shruti.contracts.board import Region, BoardContent, BoardState
from shruti.contracts.speech import LanguageSpan, Utterance, Deixis
from shruti.contracts.beat import Beat
from shruti.contracts.atlas import BeatRef, Concept, Edge, Misconception


def test_recording_requires_surface_kind():
    with pytest.raises(ValidationError):
        Recording(id="a" * 64, source_uri="gs://x", duration_s=1.0, fps=30.0)
    r = Recording(id="a" * 64, source_uri="gs://x", duration_s=1.0, fps=30.0,
                   surface_kind=SurfaceKind.BLACKBOARD)
    assert r.reel_version == 1


def test_beat_carries_speech_and_deixis():
    u = Utterance(id="u1", recording_id="r1", start_s=0.0, end_s=1.0, text="hi",
                   speaker="TEACHER")
    d = Deixis(id="d1", recording_id="r1", at_s=0.5, board_region=(0.1, 0.1, 0.2, 0.2),
               kind="point")
    b = Beat(id="b1", recording_id="r1", idx=0, start_s=0.0, end_s=1.0, kind="explain",
             speech=[u], deixis=[d], transcript="hi")
    assert b.speech[0].text == "hi"
    assert b.deixis[0].kind == "point"


def test_concept_and_edge_require_atlas_fields():
    c = Concept(id="c1", canonical_name="completing the square",
                taught_in=[BeatRef(beat_id="b1", relation="taught_in")])
    e = Edge(id="e1", from_concept="c0", to_concept="c1", edge_type="REQUIRES",
              evidence=[BeatRef(beat_id="b1", relation="evidence_for")])
    m = Misconception(id="m1", concept_id="c1", statement="treats (a+b)^2 as a^2+b^2",
                       correct_understanding="(a+b)^2 = a^2+2ab+b^2",
                       pre_empted_at_beat="b1")
    assert c.taught_in[0].relation == "taught_in"
    assert e.edge_type == "REQUIRES"
    assert m.pre_empted_at_beat == "b1"


def test_board_state_unreadable_region_has_reason():
    region = Region(id="r1", bbox=(0.0, 0.0, 0.1, 0.1), kind="unreadable",
                     reason="occluded throughout state")
    content = BoardContent(regions=[region])
    bs = BoardState(id="bs1", recording_id="r1", idx=0, valid_from_s=0.0,
                     valid_to_s=10.0, composited_uri="gs://x", ended_by="erase",
                     content=content)
    assert bs.content.regions[0].reason == "occluded throughout state"


def test_timeline_shapes():
    t = Timeline(recording_id="r1", shots=[Shot(start_s=0.0, end_s=5.0)],
                 ink_curve=[0.0, 1.0], ink_curve_times=[0.0, 1.0],
                 erase_events=[EraseEvent(at_s=5.0, before=10.0, after=1.0)],
                 sample_plan=[SamplePlanRegion(start_s=0.0, end_s=5.0, fps=1.0,
                                               pixel_diff_threshold=3.0)])
    assert t.erase_events[0].after == 1.0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/contracts/test_contracts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shruti.contracts'`

- [ ] **Step 3: Write the contract modules**

```python
# shruti/contracts/__init__.py
```

```python
# shruti/contracts/recording.py
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
# shruti/contracts/timeline.py
from pydantic import BaseModel


class Shot(BaseModel):
    start_s: float
    end_s: float


class EraseEvent(BaseModel):
    at_s: float
    before: float
    after: float


class SamplePlanRegion(BaseModel):
    start_s: float
    end_s: float
    fps: float
    pixel_diff_threshold: float


class Timeline(BaseModel):
    recording_id: str
    shots: list[Shot] = []
    ink_curve: list[float] = []
    ink_curve_times: list[float] = []
    erase_events: list[EraseEvent] = []
    sample_plan: list[SamplePlanRegion] = []
```

```python
# shruti/contracts/board.py
from typing import Literal
from pydantic import BaseModel

RegionKind = Literal["equation", "text", "figure", "table", "diagram", "unreadable"]


class Region(BaseModel):
    id: str
    bbox: tuple[float, float, float, float]
    kind: RegionKind
    latex: str | None = None
    plain_text: str | None = None
    description: str | None = None
    role: str | None = None
    step_index: int | None = None
    derives_from: str | None = None
    confidence: float | None = None
    reason: str | None = None


class BoardContent(BaseModel):
    regions: list[Region] = []


class BoardState(BaseModel):
    id: str
    recording_id: str
    idx: int
    valid_from_s: float
    valid_to_s: float
    composited_uri: str
    unfilled_uri: str | None = None
    ink_coverage: float | None = None
    ended_by: Literal["erase", "shot_cut", "end_of_video"]
    content: BoardContent | None = None
    ledger_version: int = 1
```

```python
# shruti/contracts/speech.py
from typing import Literal
from pydantic import BaseModel


class LanguageSpan(BaseModel):
    start_s: float
    end_s: float
    lang: str


class Utterance(BaseModel):
    id: str
    recording_id: str
    start_s: float
    end_s: float
    text: str
    speaker: Literal["TEACHER", "STUDENT", "UNKNOWN"]
    language_spans: list[LanguageSpan] = []
    confidence: float | None = None


class Deixis(BaseModel):
    id: str
    recording_id: str
    at_s: float
    utterance_id: str | None = None
    phrase: str | None = None
    board_region: tuple[float, float, float, float]
    kind: Literal["point", "circle", "underline", "sweep", "write"]
    referent_text: str | None = None
    confidence: float | None = None
```

```python
# shruti/contracts/beat.py
from typing import Literal
from pydantic import BaseModel
from shruti.contracts.speech import Utterance, Deixis

BeatKind = Literal["explain", "derive", "example", "question", "recap", "aside", "admin"]


class Beat(BaseModel):
    id: str
    recording_id: str
    idx: int
    start_s: float
    end_s: float
    kind: BeatKind
    speech: list[Utterance] = []
    board_state_id: str | None = None
    board_delta: tuple[float, float, float, float] | None = None
    deixis: list[Deixis] = []
    concepts: list[str] = []
    salience: float | None = None
    transcript: str
```

```python
# shruti/contracts/atlas.py
from typing import Literal
from pydantic import BaseModel

EdgeType = Literal["REQUIRES", "PART_OF", "EXEMPLIFIES", "CONTRASTS_WITH"]


class BeatRef(BaseModel):
    beat_id: str
    relation: Literal["taught_in", "mentioned_in", "evidence_for"]


class Concept(BaseModel):
    id: str
    canonical_name: str
    aliases: list[str] = []
    subject: str | None = None
    grade: int | None = None
    chapter: str | None = None
    definition: str | None = None
    atlas_version: int = 1
    taught_in: list[BeatRef] = []


class Edge(BaseModel):
    id: str
    from_concept: str
    to_concept: str
    edge_type: EdgeType
    weight: float = 1.0
    atlas_version: int = 1
    evidence: list[BeatRef] = []


class Misconception(BaseModel):
    id: str
    concept_id: str
    statement: str
    teacher_phrasing: str | None = None
    correct_understanding: str
    pre_empted_at_beat: str
    board_region_id: str | None = None
    atlas_version: int = 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/contracts/test_contracts.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add shruti/contracts/ tests/contracts/
git commit -m "feat: add pydantic contracts for all pipeline stage boundaries"
```

---

## Task 3: Database — migrations, pool, and the provenance-invariant schema

**Files:**
- Create: `infra/migrations/001_reel.sql`
- Create: `infra/migrations/002_ledger.sql`
- Create: `infra/migrations/003_atlas.sql`
- Create: `infra/migrations/004_index.sql`
- Create: `shruti/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `docker/compose.yaml` Postgres service (Task 1) must be running (`docker compose -f docker/compose.yaml up -d postgres`).
- Produces: `shruti.db.get_pool() -> asyncpg.Pool`, `shruti.db.apply_migrations(pool: asyncpg.Pool, migrations_dir: str = "infra/migrations") -> None`. Later Vault tasks (13, 14) call `get_pool()` and query the tables created here directly by name (`recording`, `utterance`, `deixis`, `beat`, `board_state`, `board_region`, `concept`, `concept_edge`, `misconception`, `beat_ref`, `human_override`, `embedding`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db.py
import pytest
from shruti.db import get_pool, apply_migrations


@pytest.mark.asyncio
async def test_migrations_create_all_tables():
    pool = await get_pool()
    await apply_migrations(pool)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
        )
        names = {r["table_name"] for r in rows}
        for expected in ("recording", "utterance", "deixis", "beat", "board_state",
                          "board_region", "concept", "concept_edge", "misconception",
                          "beat_ref", "human_override", "embedding"):
            assert expected in names
        ext = await conn.fetchval(
            "SELECT extname FROM pg_extension WHERE extname='vector'"
        )
        assert ext == "vector"
    await pool.close()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `docker compose -f docker/compose.yaml up -d postgres && uv run pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shruti.db'`

- [ ] **Step 3: Write the migration files**

```sql
-- infra/migrations/001_reel.sql
CREATE TABLE recording (
    id              TEXT PRIMARY KEY,
    source_uri      TEXT NOT NULL,
    title           TEXT,
    duration_s      REAL NOT NULL,
    fps             REAL NOT NULL,
    width           INT, height INT,
    surface_kind    TEXT NOT NULL,
    subject         TEXT, grade INT, chapter TEXT,
    ingested_at     TIMESTAMPTZ DEFAULT now(),
    reel_version    INT NOT NULL DEFAULT 1
);

CREATE TABLE utterance (
    id              TEXT PRIMARY KEY,
    recording_id    TEXT NOT NULL REFERENCES recording(id),
    start_s         REAL NOT NULL, end_s REAL NOT NULL,
    text            TEXT NOT NULL,
    speaker         TEXT NOT NULL,
    language_spans  JSONB,
    confidence      REAL
);
CREATE INDEX ON utterance (recording_id, start_s);

CREATE TABLE deixis (
    id              TEXT PRIMARY KEY,
    recording_id    TEXT NOT NULL REFERENCES recording(id),
    at_s            REAL NOT NULL,
    utterance_id    TEXT REFERENCES utterance(id),
    phrase          TEXT,
    board_region    JSONB NOT NULL,
    kind            TEXT,
    referent_text   TEXT,
    confidence      REAL
);

CREATE TABLE beat (
    id              TEXT PRIMARY KEY,
    recording_id    TEXT NOT NULL REFERENCES recording(id),
    idx             INT NOT NULL,
    start_s         REAL NOT NULL, end_s REAL NOT NULL,
    kind            TEXT NOT NULL,
    board_state_id  TEXT,
    board_delta     JSONB,
    salience        REAL,
    transcript      TEXT NOT NULL,
    UNIQUE (recording_id, idx)
);
CREATE INDEX ON beat (recording_id, start_s);
```

```sql
-- infra/migrations/002_ledger.sql
CREATE TABLE board_state (
    id              TEXT PRIMARY KEY,
    recording_id    TEXT NOT NULL REFERENCES recording(id),
    idx             INT NOT NULL,
    valid_from_s    REAL NOT NULL,
    valid_to_s      REAL NOT NULL,
    composited_uri  TEXT NOT NULL,
    unfilled_uri    TEXT,
    ink_coverage    REAL,
    homography      JSONB,
    ended_by        TEXT,
    ledger_version  INT NOT NULL DEFAULT 1
);
CREATE INDEX ON board_state (recording_id, valid_from_s, valid_to_s);

CREATE TABLE board_region (
    id              TEXT PRIMARY KEY,
    board_state_id  TEXT NOT NULL REFERENCES board_state(id),
    bbox            JSONB NOT NULL,
    kind            TEXT NOT NULL,
    latex           TEXT,
    plain_text      TEXT,
    description     TEXT,
    role            TEXT,
    step_index      INT,
    derives_from    TEXT REFERENCES board_region(id),
    confidence      REAL
);
```

```sql
-- infra/migrations/003_atlas.sql
CREATE TABLE concept (
    id              TEXT PRIMARY KEY,
    canonical_name  TEXT NOT NULL,
    aliases         TEXT[],
    subject         TEXT, grade INT, chapter TEXT,
    definition      TEXT,
    atlas_version   INT NOT NULL DEFAULT 1,
    UNIQUE (canonical_name, subject, grade, atlas_version)
);

CREATE TABLE concept_edge (
    id              TEXT PRIMARY KEY,
    from_concept    TEXT NOT NULL REFERENCES concept(id),
    to_concept      TEXT NOT NULL REFERENCES concept(id),
    edge_type       TEXT NOT NULL,
    weight          REAL DEFAULT 1.0,
    atlas_version   INT NOT NULL DEFAULT 1
);
CREATE INDEX ON concept_edge (from_concept, edge_type);
CREATE INDEX ON concept_edge (to_concept, edge_type);

CREATE TABLE misconception (
    id                    TEXT PRIMARY KEY,
    concept_id            TEXT NOT NULL REFERENCES concept(id),
    statement             TEXT NOT NULL,
    teacher_phrasing      TEXT,
    correct_understanding TEXT NOT NULL,
    pre_empted_at_beat    TEXT NOT NULL REFERENCES beat(id),
    board_region_id       TEXT REFERENCES board_region(id),
    atlas_version         INT NOT NULL DEFAULT 1
);

CREATE TABLE beat_ref (
    id              BIGSERIAL PRIMARY KEY,
    subject_kind    TEXT NOT NULL,
    subject_id      TEXT NOT NULL,
    beat_id         TEXT NOT NULL REFERENCES beat(id),
    relation        TEXT NOT NULL,
    atlas_version   INT NOT NULL DEFAULT 1
);
CREATE INDEX ON beat_ref (subject_kind, subject_id);

CREATE TABLE human_override (
    id              TEXT PRIMARY KEY,
    target_table    TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    field           TEXT NOT NULL,
    value           JSONB NOT NULL,
    author          TEXT, note TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);
```

```sql
-- infra/migrations/004_index.sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE embedding (
    id              TEXT PRIMARY KEY,
    kind            TEXT NOT NULL,
    ref_id          TEXT NOT NULL,
    recording_id    TEXT,
    vec             vector(3072) NOT NULL,
    text            TEXT NOT NULL
);
CREATE INDEX ON embedding USING hnsw (vec vector_cosine_ops);
```

```python
# shruti/db.py
import os
from pathlib import Path
import asyncpg

_DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://shruti:shruti@localhost:5432/shruti"
)


async def get_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(_DATABASE_URL)


async def apply_migrations(pool: asyncpg.Pool, migrations_dir: str = "infra/migrations") -> None:
    files = sorted(Path(migrations_dir).glob("*.sql"))
    async with pool.acquire() as conn:
        for f in files:
            sql = f.read_text()
            try:
                await conn.execute(sql)
            except asyncpg.exceptions.DuplicateTableError:
                continue
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add infra/migrations/ shruti/db.py tests/test_db.py
git commit -m "feat: add Reel/Ledger/Atlas/Index schema and migration runner"
```

---

## Task 4: GATE — admit the recording

**Files:**
- Create: `shruti/stages/gate/__init__.py`, `admit.py`, `probe.py`, `normalize.py`, `surface.py`
- Test: `tests/stages/gate/test_gate.py`

**Interfaces:**
- Consumes: `shruti.contracts.recording.Recording`, `SurfaceKind` (Task 2).
- Produces: `fingerprint(path: str) -> str`, `probe_video(path: str) -> dict` (keys: `duration_s`, `fps`, `width`, `height`, `has_audio`), `normalize_video(path: str, out_dir: str) -> tuple[str, str]` (returns `(video_path, audio_path)`), `classify_surface(client, frames: list) -> SurfaceKind`, `admit(source_uri: str, client, workdir: str) -> Recording` — later tasks (Task 6 Pulse, and the pipeline wiring in Task 18) call `admit()` and consume its returned `Recording`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/stages/gate/test_gate.py
import hashlib
import shutil
import subprocess
import pytest
from shruti.contracts.recording import SurfaceKind
from shruti.stages.gate.probe import fingerprint
from shruti.stages.gate.surface import classify_surface
from shruti.stages.gate.admit import admit


def test_fingerprint_is_stable_sha256(tmp_path):
    f = tmp_path / "clip.bin"
    f.write_bytes(b"hello world")
    expected = hashlib.sha256(b"hello world").hexdigest()
    assert fingerprint(str(f)) == expected


class FakeGeminiResponse:
    def __init__(self, text):
        self.text = text


class FakeGeminiClient:
    def __init__(self, reply_text):
        self._reply_text = reply_text
        self.calls = []

    class _Models:
        def __init__(self, outer):
            self._outer = outer

        def generate_content(self, model, contents, config=None):
            self._outer.calls.append((model, contents))
            return FakeGeminiResponse(self._outer._reply_text)

    @property
    def models(self):
        return FakeGeminiClient._Models(self)


def test_classify_surface_parses_blackboard():
    client = FakeGeminiClient(reply_text="blackboard")
    result = classify_surface(client, frames=[b"fake-frame-bytes"])
    assert result == SurfaceKind.BLACKBOARD
    assert len(client.calls) == 1


def test_classify_surface_rejects_unknown_label():
    client = FakeGeminiClient(reply_text="chalkboard-ish maybe?")
    with pytest.raises(ValueError):
        classify_surface(client, frames=[b"fake-frame-bytes"])


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_admit_end_to_end(tmp_path):
    clip = tmp_path / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=2",
         "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "2",
         "-c:v", "libx264", "-c:a", "aac", str(clip)],
        check=True, capture_output=True,
    )
    client = FakeGeminiClient(reply_text="blackboard")
    recording = admit(str(clip), client, workdir=str(tmp_path))
    assert recording.duration_s > 0
    assert recording.surface_kind == SurfaceKind.BLACKBOARD
    assert len(recording.id) == 64
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/stages/gate/test_gate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shruti.stages'`

- [ ] **Step 3: Write the implementation**

```python
# shruti/stages/gate/__init__.py
```

```python
# shruti/stages/gate/probe.py
import hashlib
import json
import subprocess


def fingerprint(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def probe_video(path: str) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format",
         "-show_streams", path],
        check=True, capture_output=True, text=True,
    )
    data = json.loads(out.stdout)
    v_stream = next(s for s in data["streams"] if s["codec_type"] == "video")
    has_audio = any(s["codec_type"] == "audio" for s in data["streams"])
    num, den = (v_stream.get("r_frame_rate", "30/1")).split("/")
    return {
        "duration_s": float(data["format"]["duration"]),
        "fps": float(num) / float(den),
        "width": int(v_stream["width"]),
        "height": int(v_stream["height"]),
        "has_audio": has_audio,
    }
```

```python
# shruti/stages/gate/normalize.py
import subprocess
from pathlib import Path


def normalize_video(path: str, out_dir: str) -> tuple[str, str]:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    video_path = str(Path(out_dir) / "normalized.mp4")
    audio_path = str(Path(out_dir) / "audio.wav")
    subprocess.run(
        ["ffmpeg", "-y", "-i", path, "-c:v", "libx264", "-r", "30",
         "-an", video_path],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", path, "-vn", "-ac", "1", "-ar", "16000",
         audio_path],
        check=True, capture_output=True,
    )
    return video_path, audio_path
```

```python
# shruti/stages/gate/surface.py
from shruti.contracts.recording import SurfaceKind
from shruti.config import Models

_PROMPT = (
    "Classify the writing surface visible in these lecture frames as exactly "
    "one of: blackboard, whiteboard, slides, mixed, talking_head. "
    "Reply with only that one word."
)


def classify_surface(client, frames: list) -> SurfaceKind:
    response = client.models.generate_content(
        model=Models().router,
        contents=[_PROMPT, *frames],
    )
    label = response.text.strip().lower()
    try:
        return SurfaceKind(label)
    except ValueError as e:
        raise ValueError(f"classify_surface: model returned unrecognized label {label!r}") from e
```

```python
# shruti/stages/gate/admit.py
from shruti.contracts.recording import Recording
from shruti.stages.gate.probe import probe_video, fingerprint
from shruti.stages.gate.normalize import normalize_video
from shruti.stages.gate.surface import classify_surface


def admit(source_uri: str, client, workdir: str) -> Recording:
    meta = probe_video(source_uri)
    video_path, _audio_path = normalize_video(source_uri, workdir)
    rec_id = fingerprint(video_path)
    surface_kind = classify_surface(client, frames=[])
    return Recording(
        id=rec_id,
        source_uri=source_uri,
        duration_s=meta["duration_s"],
        fps=meta["fps"],
        width=meta["width"],
        height=meta["height"],
        surface_kind=surface_kind,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/stages/gate/test_gate.py -v`
Expected: PASS (3 tests always run; the `test_admit_end_to_end` test runs only if `ffmpeg` is on `PATH`, otherwise it's reported as skipped, not failed)

- [ ] **Step 5: Commit**

```bash
git add shruti/stages/gate/ tests/stages/gate/
git commit -m "feat: implement GATE stage (probe, normalize, fingerprint, surface classify)"
```

---

## Task 5: PULSE — ink curve and erase detection

**Files:**
- Create: `shruti/stages/pulse/__init__.py`, `ink.py`, `erase.py`
- Test: `tests/stages/pulse/test_ink.py`, `tests/stages/pulse/test_erase.py`

**Interfaces:**
- Consumes: `shruti.contracts.timeline.EraseEvent` (Task 2).
- Produces: `binarize_ink(board_bgr: np.ndarray, polarity: str) -> np.ndarray`, `ink_curve(sampled: list[np.ndarray], quad, polarity: str) -> np.ndarray`, `find_erase_events(curve: np.ndarray, times: np.ndarray, drop_ratio: float = 0.35, window_s: float = 3.0) -> list[EraseEvent]`, `dedupe_within(events: list[EraseEvent], min_gap_s: float = 10.0) -> list[EraseEvent]` — Task 6 (sample plan) and Task 11 (WEAVE boundaries) both consume `find_erase_events`'s output shape.

- [ ] **Step 1: Write the failing tests**

```python
# tests/stages/pulse/test_ink.py
import numpy as np
from shruti.stages.pulse.ink import binarize_ink


def test_binarize_ink_chalk_polarity_finds_bright_marks():
    board = np.zeros((40, 40, 3), dtype=np.uint8)  # dark board
    board[10:30, 10:30] = 255  # bright chalk mark
    ink = binarize_ink(board, polarity="bright_on_dark")
    assert ink[15, 15] > 0
    assert ink[2, 2] == 0


def test_binarize_ink_marker_polarity_finds_dark_marks():
    board = np.full((40, 40, 3), 255, dtype=np.uint8)  # bright whiteboard
    board[10:30, 10:30] = 0  # dark marker mark
    ink = binarize_ink(board, polarity="dark_on_bright")
    assert ink[15, 15] > 0
    assert ink[2, 2] == 0
```

```python
# tests/stages/pulse/test_erase.py
import numpy as np
from shruti.stages.pulse.erase import find_erase_events, dedupe_within
from shruti.contracts.timeline import EraseEvent


def test_find_erase_events_detects_sustained_drop():
    times = np.arange(0, 20, 0.5)
    curve = np.concatenate([
        np.linspace(0, 1000, 10),   # writing builds up, t=0..4.5
        np.full(10, 1000.0),        # holds steady, t=5..9.5
        np.full(10, 50.0),          # erased and stays low, t=10..14.5
        np.full(10, 60.0),          # still low, t=15..19.5
    ])
    events = find_erase_events(curve, times, drop_ratio=0.35, window_s=3.0)
    assert len(events) == 1
    assert 9.0 <= events[0].at_s <= 11.0


def test_find_erase_events_ignores_transient_occlusion():
    times = np.arange(0, 20, 0.5)
    curve = np.full(40, 1000.0)
    curve[16:20] = 50.0  # a brief dip (teacher walks in front) that recovers
    events = find_erase_events(curve, times, drop_ratio=0.35, window_s=3.0)
    assert events == []


def test_dedupe_within_merges_close_events():
    events = [
        EraseEvent(at_s=10.0, before=1000, after=50),
        EraseEvent(at_s=10.5, before=1000, after=50),
        EraseEvent(at_s=30.0, before=1000, after=50),
    ]
    deduped = dedupe_within(events, min_gap_s=10.0)
    assert [e.at_s for e in deduped] == [10.0, 30.0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/stages/pulse/ -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shruti.stages.pulse'`

- [ ] **Step 3: Write the implementation**

```python
# shruti/stages/pulse/__init__.py
```

```python
# shruti/stages/pulse/ink.py
import cv2
import numpy as np


def binarize_ink(board_bgr: np.ndarray, polarity: str) -> np.ndarray:
    """polarity: 'bright_on_dark' (chalk) | 'dark_on_bright' (marker)"""
    g = cv2.cvtColor(board_bgr, cv2.COLOR_BGR2GRAY)
    g = cv2.GaussianBlur(g, (3, 3), 0)
    flag = cv2.THRESH_BINARY if polarity == "bright_on_dark" else cv2.THRESH_BINARY_INV
    ink = cv2.adaptiveThreshold(
        g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, flag,
        blockSize=25, C=-8 if polarity == "bright_on_dark" else 8,
    )
    return cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))


def ink_curve(sampled: list, quad, polarity: str) -> np.ndarray:
    from shruti.stages.slate.rectify import rectify
    return np.array([
        binarize_ink(rectify(f, quad), polarity).sum() / 255
        for f in sampled
    ])
```

```python
# shruti/stages/pulse/erase.py
import numpy as np
from shruti.contracts.timeline import EraseEvent


def find_erase_events(curve, times, drop_ratio: float = 0.35, window_s: float = 3.0) -> list[EraseEvent]:
    events = []
    dt = times[1] - times[0]
    w = max(2, int(window_s / dt))

    for i in range(w, len(curve) - w):
        before = curve[i - w:i].max()
        after = curve[i:i + w].min()
        if before <= 0:
            continue
        if (before - after) / before < drop_ratio:
            continue
        tail = curve[i + w:i + 3 * w]
        if len(tail) and tail.mean() > after * 1.6:
            continue
        events.append(EraseEvent(at_s=float(times[i]), before=float(before), after=float(after)))

    return dedupe_within(events, min_gap_s=10.0)


def dedupe_within(events: list[EraseEvent], min_gap_s: float = 10.0) -> list[EraseEvent]:
    """Keep the median-low event of each cluster of events within min_gap_s
    of each other — not the first. A sustained drop typically fires this
    detector at many consecutive sample points (once ratio/persistence
    conditions are met, they stay met until the curve moves again), so
    "first" lands at the drop's onset while the true erase timestamp is
    closer to the cluster's middle."""
    if not events:
        return []
    events = sorted(events, key=lambda e: e.at_s)
    deduped = []
    i = 0
    while i < len(events):
        j = i
        while j < len(events) and events[j].at_s - events[i].at_s < min_gap_s:
            j += 1
        mid_idx = (i + j - 1) // 2
        deduped.append(events[mid_idx])
        i = j
    return deduped
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/stages/pulse/test_ink.py tests/stages/pulse/test_erase.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add shruti/stages/pulse/ink.py shruti/stages/pulse/erase.py shruti/stages/pulse/__init__.py tests/stages/pulse/test_ink.py tests/stages/pulse/test_erase.py
git commit -m "feat: implement PULSE ink-curve and erase-event detection"
```

---

## Task 6: PULSE — shot detection and adaptive sample plan

**Files:**
- Create: `shruti/stages/pulse/shots.py`, `plan.py`
- Test: `tests/stages/pulse/test_shots.py`, `tests/stages/pulse/test_plan.py`

**Interfaces:**
- Consumes: `shruti.contracts.timeline.Shot`, `SamplePlanRegion`, `EraseEvent` (Task 2); `find_erase_events` (Task 5).
- Produces: `detect_shots(video_path: str, threshold: float = 27.0) -> list[Shot]`, `build_sample_plan(shots: list[Shot], erase_events: list[EraseEvent], duration_s: float, dense_fps: float, sparse_fps: float) -> list[SamplePlanRegion]` — Task 4's normalized video path and Task 5's erase events feed directly into these; their output (`list[SamplePlanRegion]`) is what Task 8 (SLATE) and Task 9 (ECHO) read to decide sampling density.

- [ ] **Step 1: Write the failing tests**

```python
# tests/stages/pulse/test_shots.py
import shutil
import subprocess
import pytest
from shruti.stages.pulse.shots import detect_shots


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_detect_shots_on_synthetic_two_scene_clip(tmp_path):
    clip = tmp_path / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-y",
         "-f", "lavfi", "-i", "color=c=black:s=64x64:d=2:r=10",
         "-f", "lavfi", "-i", "color=c=white:s=64x64:d=2:r=10",
         "-filter_complex", "concat=n=2:v=1:a=0", "-c:v", "libx264", str(clip)],
        check=True, capture_output=True,
    )
    shots = detect_shots(str(clip), threshold=27.0)
    assert len(shots) >= 1
    assert shots[0].start_s == 0.0
```

```python
# tests/stages/pulse/test_plan.py
from shruti.stages.pulse.plan import build_sample_plan
from shruti.contracts.timeline import Shot, EraseEvent


def test_build_sample_plan_covers_full_duration_with_no_gaps():
    shots = [Shot(start_s=0.0, end_s=30.0)]
    erases = [EraseEvent(at_s=15.0, before=1000, after=50)]
    plan = build_sample_plan(shots, erases, duration_s=30.0, dense_fps=1.0, sparse_fps=1 / 6)
    assert plan[0].start_s == 0.0
    assert plan[-1].end_s == 30.0
    for a, b in zip(plan, plan[1:]):
        assert abs(a.end_s - b.start_s) < 1e-6


def test_build_sample_plan_samples_densely_near_erase_events():
    shots = [Shot(start_s=0.0, end_s=30.0)]
    erases = [EraseEvent(at_s=15.0, before=1000, after=50)]
    plan = build_sample_plan(shots, erases, duration_s=30.0, dense_fps=1.0, sparse_fps=1 / 6)
    near_erase = [r for r in plan if r.start_s <= 15.0 <= r.end_s]
    assert near_erase and near_erase[0].fps >= 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/stages/pulse/test_shots.py tests/stages/pulse/test_plan.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shruti.stages.pulse.shots'`

- [ ] **Step 3: Write the implementation**

```python
# shruti/stages/pulse/shots.py
from scenedetect import open_video, SceneManager
from scenedetect.detectors import AdaptiveDetector
from shruti.contracts.timeline import Shot


def detect_shots(video_path: str, threshold: float = 27.0) -> list[Shot]:
    video = open_video(video_path)
    manager = SceneManager()
    manager.add_detector(AdaptiveDetector(adaptive_threshold=threshold))
    manager.detect_scenes(video)
    scene_list = manager.get_scene_list()
    if not scene_list:
        return [Shot(start_s=0.0, end_s=video.duration.get_seconds())]
    return [Shot(start_s=s.get_seconds(), end_s=e.get_seconds()) for s, e in scene_list]
```

```python
# shruti/stages/pulse/plan.py
from shruti.contracts.timeline import Shot, EraseEvent, SamplePlanRegion

_ERASE_WINDOW_S = 5.0


def build_sample_plan(
    shots: list[Shot],
    erase_events: list[EraseEvent],
    duration_s: float,
    dense_fps: float,
    sparse_fps: float,
) -> list[SamplePlanRegion]:
    boundaries = sorted({0.0, duration_s} | {e.at_s for e in erase_events})
    erase_times = [e.at_s for e in erase_events]
    regions = []
    for start, end in zip(boundaries, boundaries[1:]):
        near_erase = any(abs(start - t) <= _ERASE_WINDOW_S or abs(end - t) <= _ERASE_WINDOW_S
                          for t in erase_times)
        fps = max(dense_fps, 2.0) if near_erase else sparse_fps
        threshold = 3.0 if near_erase else 10.0
        regions.append(SamplePlanRegion(start_s=start, end_s=end, fps=fps,
                                         pixel_diff_threshold=threshold))
    return regions
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/stages/pulse/test_shots.py tests/stages/pulse/test_plan.py -v`
Expected: PASS (`test_detect_shots_on_synthetic_two_scene_clip` skips if `ffmpeg` is missing; the two `test_build_sample_plan_*` tests always run)

- [ ] **Step 5: Commit**

```bash
git add shruti/stages/pulse/shots.py shruti/stages/pulse/plan.py tests/stages/pulse/test_shots.py tests/stages/pulse/test_plan.py
git commit -m "feat: implement PULSE shot detection and adaptive sample plan"
```

---

## Task 7: SLATE — locate the board and rectify

**Files:**
- Create: `shruti/stages/slate/__init__.py`, `locate.py`, `rectify.py`
- Test: `tests/stages/slate/test_locate.py`, `tests/stages/slate/test_rectify.py`

**Interfaces:**
- Produces: `locate_board(frames: list[np.ndarray]) -> tuple[tuple[float, float], ...]` (4 corner points, voted across frames), `rectify(frame: np.ndarray, quad, out_size: tuple[int, int] = (800, 600)) -> np.ndarray` — Task 5's `ink_curve` already imports `rectify` from this module; Task 8 (masking/compositing) and Task 12 (GLYPH) both operate on `rectify()`'s output.

- [ ] **Step 1: Write the failing tests**

```python
# tests/stages/slate/test_locate.py
import numpy as np
from shruti.stages.slate.locate import locate_board


def _frame_with_white_board_on_black(w=200, h=150, board_box=(30, 20, 170, 130)):
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    x0, y0, x1, y1 = board_box
    frame[y0:y1, x0:x1] = 255
    return frame


def test_locate_board_finds_the_bright_rectangle():
    frames = [_frame_with_white_board_on_black() for _ in range(5)]
    quad = locate_board(frames)
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    assert min(xs) < 40 and max(xs) > 160
    assert min(ys) < 30 and max(ys) > 120
```

```python
# tests/stages/slate/test_rectify.py
import numpy as np
from shruti.stages.slate.rectify import rectify


def test_rectify_maps_quad_to_full_canonical_frame():
    frame = np.zeros((150, 200, 3), dtype=np.uint8)
    frame[20:130, 30:170] = (10, 20, 30)  # the "board" region, one flat color
    quad = ((30, 20), (170, 20), (170, 130), (30, 130))
    rectified = rectify(frame, quad, out_size=(100, 100))
    assert rectified.shape[:2] == (100, 100)
    center = rectified[50, 50]
    assert tuple(int(c) for c in center) == (10, 20, 30)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/stages/slate/ -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shruti.stages.slate'`

- [ ] **Step 3: Write the implementation**

```python
# shruti/stages/slate/__init__.py
```

```python
# shruti/stages/slate/locate.py
import cv2
import numpy as np


def _largest_board_like_quad(frame: np.ndarray):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    best_area = 0
    for c in contours:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) != 4:
            continue
        area = cv2.contourArea(approx)
        if area > best_area:
            best_area = area
            best = approx.reshape(4, 2)
    if best is None:
        # Fallback: thresholded bright region's bounding box as a quad.
        _, mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        ys, xs = np.where(mask > 0)
        if len(xs) == 0:
            h, w = gray.shape
            return np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
        x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
        best = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float32)
    return best.astype(np.float32)


def locate_board(frames: list) -> tuple:
    """Vote the board quad across sampled frames — the board doesn't move; the teacher does."""
    quads = [_largest_board_like_quad(f) for f in frames]
    avg = np.mean(np.stack(quads), axis=0)
    return tuple(tuple(p) for p in avg)
```

```python
# shruti/stages/slate/rectify.py
import cv2
import numpy as np


def rectify(frame: np.ndarray, quad, out_size: tuple = (800, 600)) -> np.ndarray:
    src = np.array(quad, dtype=np.float32)
    w, h = out_size
    dst = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(frame, matrix, (w, h))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/stages/slate/test_locate.py tests/stages/slate/test_rectify.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add shruti/stages/slate/__init__.py shruti/stages/slate/locate.py shruti/stages/slate/rectify.py tests/stages/slate/test_locate.py tests/stages/slate/test_rectify.py
git commit -m "feat: implement SLATE board localization and rectification"
```

---

## Task 8: SLATE — masking and the compositing algorithm

This is the highest-risk stage in the whole pipeline per the architecture doc — get the tests right before moving on.

**Files:**
- Create: `shruti/stages/slate/mask.py`, `photometric.py`, `composite.py`
- Test: `tests/stages/slate/test_mask.py`, `tests/stages/slate/test_composite.py`

**Interfaces:**
- Consumes: `rectify()` output shape (Task 7).
- Produces: `framediff_masks(frames: list, dilate_px: int = 12) -> list[np.ndarray]`, `match_local(donor_patch: np.ndarray, target: np.ndarray, mask: np.ndarray) -> np.ndarray`, `composite_board_state(frames: list, masks: list, target_idx: int, span_start: int, span_end: int, photometric: bool = True) -> tuple[np.ndarray, np.ndarray]` (returns `(composited_bgr, unfilled_mask)`) — Task 12 (GLYPH) consumes both the composited image and the `unfilled_mask` from this function directly.

- [ ] **Step 1: Write the failing tests**

```python
# tests/stages/slate/test_mask.py
import numpy as np
from shruti.stages.slate.mask import framediff_masks


def _frame_with_blob(size=60, blob_xy=(10, 10), blob_wh=(15, 15)):
    frame = np.full((size, size, 3), 200, dtype=np.uint8)  # static board background
    x, y = blob_xy
    w, h = blob_wh
    frame[y:y + h, x:x + w] = 40  # the "teacher" — a dark blob that moves between frames
    return frame


def test_framediff_masks_flags_the_moving_blob_not_the_background():
    frames = [
        _frame_with_blob(blob_xy=(5, 5)),
        _frame_with_blob(blob_xy=(30, 30)),
        _frame_with_blob(blob_xy=(5, 5)),
    ]
    masks = framediff_masks(frames, dilate_px=2)
    assert masks[0][10, 10]  # first frame's blob position is masked
    assert not masks[0][50, 50]  # far corner, never touched by the blob, stays unmasked
```

```python
# tests/stages/slate/test_composite.py
import numpy as np
from shruti.stages.slate.composite import composite_board_state


def test_composite_fills_target_holes_from_a_later_frame():
    size = 20
    frames = [np.full((size, size, 3), 100, dtype=np.uint8) for _ in range(3)]
    frames[1][5:10, 5:10] = 222  # new writing appears in frame 1, absent in frame 0
    masks = [np.zeros((size, size), dtype=bool) for _ in range(3)]
    masks[0][5:10, 5:10] = True  # frame 0's teacher occludes exactly that region

    composited, unfilled = composite_board_state(
        frames, masks, target_idx=0, span_start=0, span_end=3, photometric=False
    )
    assert not unfilled.any()
    assert (composited[5:10, 5:10] == 222).all()


def test_composite_falls_back_to_backward_frame_when_forward_is_also_occluded():
    size = 20
    frames = [np.full((size, size, 3), 100, dtype=np.uint8) for _ in range(3)]
    frames[0][5:10, 5:10] = 77  # earlier frame has the content visible

    masks = [np.zeros((size, size), dtype=bool) for _ in range(3)]
    masks[1][5:10, 5:10] = True  # target frame occludes it
    masks[2][5:10, 5:10] = True  # every later frame also occludes it

    composited, unfilled = composite_board_state(
        frames, masks, target_idx=1, span_start=0, span_end=3, photometric=False
    )
    assert not unfilled.any()
    assert (composited[5:10, 5:10] == 77).all()


def test_composite_returns_unfilled_when_no_frame_ever_shows_the_region():
    size = 20
    frames = [np.full((size, size, 3), 100, dtype=np.uint8) for _ in range(3)]
    masks = [np.zeros((size, size), dtype=bool) for _ in range(3)]
    for m in masks:
        m[5:10, 5:10] = True  # occluded in every single frame

    composited, unfilled = composite_board_state(
        frames, masks, target_idx=0, span_start=0, span_end=3, photometric=False
    )
    assert unfilled[5:10, 5:10].all()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/stages/slate/test_mask.py tests/stages/slate/test_composite.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shruti.stages.slate.mask'`

- [ ] **Step 3: Write the implementation**

```python
# shruti/stages/slate/mask.py
import cv2
import numpy as np


def framediff_masks(frames: list, dilate_px: int = 12) -> list:
    """V1 masking. Static camera + planar board => temporal median is a good
    background estimate; the teacher is the largest thing deviating from it."""
    stacked = np.stack(frames)
    bg = np.median(stacked[::max(1, len(frames) // 10 or 1)], axis=0).astype(np.uint8)
    bg_g = cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY)

    masks = []
    for f in frames:
        d = cv2.absdiff(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), bg_g)
        _, m = cv2.threshold(d, 32, 255, cv2.THRESH_BINARY)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))

        n, lbl, stats, _ = cv2.connectedComponentsWithStats(m, 8)
        out = np.zeros_like(m, dtype=bool)
        if n > 1:
            k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
            if stats[k, cv2.CC_STAT_AREA] > 0.01 * m.size:
                out = (lbl == k)
        dilated = cv2.dilate(out.astype(np.uint8), np.ones((dilate_px, dilate_px), np.uint8))
        masks.append(dilated.astype(bool))
    return masks
```

```python
# shruti/stages/slate/photometric.py
import numpy as np


def match_local(donor_patch: np.ndarray, target: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Match donor pixels' mean/std to the target's local neighbourhood so
    donated patches don't leave visible seams that confuse OCR."""
    result = donor_patch.copy().astype(np.float32)
    for c in range(donor_patch.shape[-1]):
        donor_vals = donor_patch[..., c][mask].astype(np.float32)
        target_vals = target[..., c][~mask].astype(np.float32) if (~mask).any() else donor_vals
        if donor_vals.size == 0 or target_vals.size == 0:
            continue
        d_mean, d_std = donor_vals.mean(), donor_vals.std() + 1e-6
        t_mean, t_std = target_vals.mean(), target_vals.std() + 1e-6
        result[..., c] = (result[..., c] - d_mean) / d_std * t_std + t_mean
    return np.clip(result, 0, 255).astype(np.uint8)
```

```python
# shruti/stages/slate/composite.py
import numpy as np
from shruti.stages.slate.photometric import match_local


def composite_board_state(frames, masks, target_idx, span_start, span_end, photometric=True):
    """Recover the most complete view of one board state. Within a state,
    content only grows (removed only at the erase that ends the state), so
    later frames are supersets — search forward first, backward as fallback."""
    target = frames[target_idx].copy()
    unfilled = masks[target_idx].astype(bool).copy()

    def donate(i):
        nonlocal unfilled, target
        can = unfilled & ~masks[i].astype(bool)
        if not can.any():
            return
        patch = frames[i]
        if photometric:
            patch = match_local(patch, target, can)
        target[can] = patch[can]
        unfilled &= ~can

    for i in range(target_idx + 1, span_end):
        donate(i)
        if not unfilled.any():
            break

    if unfilled.any():
        for i in range(target_idx - 1, span_start - 1, -1):
            donate(i)
            if not unfilled.any():
                break

    return target, unfilled
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/stages/slate/test_mask.py tests/stages/slate/test_composite.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add shruti/stages/slate/mask.py shruti/stages/slate/photometric.py shruti/stages/slate/composite.py tests/stages/slate/test_mask.py tests/stages/slate/test_composite.py
git commit -m "feat: implement SLATE V1 masking and the board-compositing algorithm"
```

---

## Task 9: ECHO — transcribe speech and align the subtitle prior

**Files:**
- Create: `shruti/stages/echo/__init__.py`, `transcribe.py`, `subtitle_prior.py`
- Test: `tests/stages/echo/test_transcribe.py`, `tests/stages/echo/test_subtitle_prior.py`

**Interfaces:**
- Consumes: `shruti.contracts.speech.Utterance` (Task 2).
- Produces: `transcribe_audio(client, audio_path: str, recording_id: str) -> list[Utterance]`, `parse_subtitle_file(path: str) -> list[dict]` (each: `{"start_s": float, "end_s": float, "text": str}`), `align_subtitle_prior(utterances: list[Utterance], subtitle_segments: list[dict]) -> list[Utterance]` — Task 11 (WEAVE) consumes the `list[Utterance]` this task produces.

- [ ] **Step 1: Write the failing tests**

```python
# tests/stages/echo/test_transcribe.py
import json
from shruti.stages.echo.transcribe import transcribe_audio


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeClient:
    def __init__(self, payload):
        self._payload = payload

    class _Models:
        def __init__(self, outer):
            self._outer = outer

        def generate_content(self, model, contents, config=None):
            return FakeResponse(json.dumps(self._outer._payload))

    @property
    def models(self):
        return FakeClient._Models(self)


def test_transcribe_audio_parses_structured_utterances():
    payload = [
        {"start_s": 0.0, "end_s": 2.0, "text": "अब हम iska derivative nikalenge",
         "speaker": "TEACHER", "confidence": 0.92},
    ]
    client = FakeClient(payload)
    utterances = transcribe_audio(client, audio_path="fake.wav", recording_id="r1")
    assert len(utterances) == 1
    assert utterances[0].text == "अब हम iska derivative nikalenge"
    assert utterances[0].speaker == "TEACHER"
    assert utterances[0].recording_id == "r1"
```

```python
# tests/stages/echo/test_subtitle_prior.py
from shruti.stages.echo.subtitle_prior import parse_subtitle_file, align_subtitle_prior
from shruti.contracts.speech import Utterance


def test_parse_subtitle_file_reads_basic_vtt(tmp_path):
    vtt = tmp_path / "captions.vtt"
    vtt.write_text(
        "WEBVTT\n\n"
        "1\n00:00:01.000 --> 00:00:03.500\nHello there\n\n"
        "2\n00:00:04.000 --> 00:00:06.000\nSecond line\n"
    )
    segments = parse_subtitle_file(str(vtt))
    assert segments[0] == {"start_s": 1.0, "end_s": 3.5, "text": "Hello there"}
    assert segments[1]["start_s"] == 4.0


def test_align_subtitle_prior_prefers_subtitle_timing_keeps_model_text():
    utterances = [Utterance(id="u1", recording_id="r1", start_s=0.8, end_s=3.6,
                             text="Hello there (model transcription)", speaker="TEACHER")]
    segments = [{"start_s": 1.0, "end_s": 3.5, "text": "Hello there"}]
    aligned = align_subtitle_prior(utterances, segments)
    assert aligned[0].start_s == 1.0
    assert aligned[0].end_s == 3.5
    assert aligned[0].text == "Hello there (model transcription)"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/stages/echo/ -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shruti.stages.echo'`

- [ ] **Step 3: Write the implementation**

```python
# shruti/stages/echo/__init__.py
```

```python
# shruti/stages/echo/transcribe.py
import json
import uuid
from shruti.config import Models
from shruti.contracts.speech import Utterance

_FIDELITY_PROMPT = """Transcribe this classroom recording exactly as spoken.

RULES
1. This is code-mixed Hindi-English classroom speech. Transcribe FAITHFULLY:
   Hindi words in Devanagari, English words in Latin script, in the order spoken.
   Do NOT translate. Do NOT normalize to one script.
2. Timestamp every utterance in seconds (start_s, end_s).
3. Label the speaker: TEACHER or STUDENT.
4. If audio is unintelligible, emit text "[inaudible]". Never guess.

Return a JSON array of objects: {start_s, end_s, text, speaker, confidence}.
"""


def transcribe_audio(client, audio_path: str, recording_id: str) -> list[Utterance]:
    response = client.models.generate_content(
        model=Models().reasoner,
        contents=[_FIDELITY_PROMPT, audio_path],
    )
    rows = json.loads(response.text)
    return [
        Utterance(
            id=str(uuid.uuid4()),
            recording_id=recording_id,
            start_s=row["start_s"],
            end_s=row["end_s"],
            text=row["text"],
            speaker=row["speaker"],
            confidence=row.get("confidence"),
        )
        for row in rows
    ]
```

```python
# shruti/stages/echo/subtitle_prior.py
import re
from shruti.contracts.speech import Utterance

_TIME_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[.,](\d{3})")


def _to_seconds(h, m, s, ms) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_subtitle_file(path: str) -> list[dict]:
    text = open(path, encoding="utf-8").read()
    blocks = re.split(r"\n\s*\n", text.strip())
    segments = []
    for block in blocks:
        match = _TIME_RE.search(block)
        if not match:
            continue
        h1, m1, s1, ms1, h2, m2, s2, ms2 = match.groups()
        lines = block[match.end():].strip().splitlines()
        segment_text = " ".join(line.strip() for line in lines if line.strip())
        segments.append({
            "start_s": _to_seconds(h1, m1, s1, ms1),
            "end_s": _to_seconds(h2, m2, s2, ms2),
            "text": segment_text,
        })
    return segments


def align_subtitle_prior(utterances: list[Utterance], subtitle_segments: list[dict]) -> list[Utterance]:
    aligned = []
    for u in utterances:
        best = None
        best_overlap = 0.0
        for seg in subtitle_segments:
            overlap = min(u.end_s, seg["end_s"]) - max(u.start_s, seg["start_s"])
            if overlap > best_overlap:
                best_overlap = overlap
                best = seg
        if best is not None:
            aligned.append(u.model_copy(update={"start_s": best["start_s"], "end_s": best["end_s"]}))
        else:
            aligned.append(u)
    return aligned
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/stages/echo/ -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add shruti/stages/echo/ tests/stages/echo/
git commit -m "feat: implement ECHO transcription and subtitle-prior alignment"
```

---

## Task 10: POINT — resolve deixis

**Files:**
- Create: `shruti/stages/point/__init__.py`, `deixis.py`
- Test: `tests/stages/point/test_deixis.py`

**Interfaces:**
- Consumes: `shruti.contracts.speech.Utterance`, `Deixis` (Task 2).
- Produces: `resolve_deixis(client, clip_frames: list, utterance: Utterance) -> Deixis | None` (returns `None` if the model reports no gesture found) — Task 11 (WEAVE) attaches this task's `Deixis` objects onto `Beat.deixis`.

- [ ] **Step 1: Write the failing test**

```python
# tests/stages/point/test_deixis.py
import json
from shruti.stages.point.deixis import resolve_deixis
from shruti.contracts.speech import Utterance


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeClient:
    def __init__(self, payload):
        self._payload = payload

    class _Models:
        def __init__(self, outer):
            self._outer = outer

        def generate_content(self, model, contents, config=None):
            return FakeResponse(json.dumps(self._outer._payload))

    @property
    def models(self):
        return FakeClient._Models(self)


def test_resolve_deixis_parses_pointed_region():
    payload = {"found": True, "phrase": "yeh term", "board_region": [0.3, 0.4, 0.1, 0.1],
               "kind": "point", "confidence": 0.81}
    client = FakeClient(payload)
    utterance = Utterance(id="u1", recording_id="r1", start_s=10.0, end_s=12.0,
                           text="ab yeh term yahan cancel ho jayega", speaker="TEACHER")
    deixis = resolve_deixis(client, clip_frames=[b"frame"], utterance=utterance)
    assert deixis is not None
    assert deixis.phrase == "yeh term"
    assert deixis.board_region == (0.3, 0.4, 0.1, 0.1)
    assert deixis.utterance_id == "u1"


def test_resolve_deixis_returns_none_when_no_gesture_found():
    client = FakeClient({"found": False})
    utterance = Utterance(id="u2", recording_id="r1", start_s=0.0, end_s=1.0,
                           text="so today we begin", speaker="TEACHER")
    assert resolve_deixis(client, clip_frames=[b"frame"], utterance=utterance) is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/stages/point/ -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shruti.stages.point'`

- [ ] **Step 3: Write the implementation**

```python
# shruti/stages/point/__init__.py
```

```python
# shruti/stages/point/deixis.py
import json
import uuid
from shruti.config import Models
from shruti.contracts.speech import Utterance, Deixis

_DEIXIS_PROMPT = """The teacher says: "{text}"

Watch this short clip. If the teacher points at, circles, underlines,
sweeps across, or writes on a specific region of the board while saying
this, report it. If there is no such gesture, report found=false.

Return JSON: {{"found": bool, "phrase": str, "board_region": [x, y, w, h]
(normalized 0-1), "kind": "point"|"circle"|"underline"|"sweep"|"write",
"confidence": float}}
"""


def resolve_deixis(client, clip_frames: list, utterance: Utterance) -> Deixis | None:
    response = client.models.generate_content(
        model=Models().reasoner,
        contents=[_DEIXIS_PROMPT.format(text=utterance.text), *clip_frames],
    )
    row = json.loads(response.text)
    if not row.get("found"):
        return None
    return Deixis(
        id=str(uuid.uuid4()),
        recording_id=utterance.recording_id,
        at_s=utterance.start_s,
        utterance_id=utterance.id,
        phrase=row["phrase"],
        board_region=tuple(row["board_region"]),
        kind=row["kind"],
        confidence=row.get("confidence"),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/stages/point/ -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add shruti/stages/point/ tests/stages/point/
git commit -m "feat: implement POINT deixis resolution"
```

---

## Task 11: WEAVE — beat boundaries and fusion

**Files:**
- Create: `shruti/stages/weave/__init__.py`, `boundaries.py`, `fuse.py`
- Test: `tests/stages/weave/test_boundaries.py`, `tests/stages/weave/test_fuse.py`

**Interfaces:**
- Consumes: `Utterance`, `Shot` (Task 2/6), `Deixis` (Task 10), `BoardState` (Task 2).
- Produces: `candidate_boundaries(utterances: list[Utterance], ink_curve, times, shots: list) -> list[float]`, `merge_within(boundaries: list[float], merge_s: float) -> list[float]`, `fuse_beats(client, recording_id: str, boundaries: list[float], utterances: list[Utterance], board_states: list, deixis: list[Deixis]) -> list[Beat]` — Task 12 (GLYPH) and Task 13 (ATLAS) both consume the `list[Beat]` this task produces.

- [ ] **Step 1: Write the failing tests**

```python
# tests/stages/weave/test_boundaries.py
import numpy as np
from shruti.stages.weave.boundaries import candidate_boundaries, merge_within
from shruti.contracts.speech import Utterance
from shruti.contracts.timeline import Shot


def test_candidate_boundaries_detects_speech_pause():
    utterances = [
        Utterance(id="u1", recording_id="r1", start_s=0.0, end_s=5.0, text="a", speaker="TEACHER"),
        Utterance(id="u2", recording_id="r1", start_s=8.0, end_s=10.0, text="b", speaker="TEACHER"),
    ]
    times = np.arange(0, 10, 1.0)
    ink_curve = np.zeros_like(times)
    boundaries = candidate_boundaries(utterances, ink_curve, times, shots=[])
    assert any(5.5 <= b <= 7.5 for b in boundaries)


def test_merge_within_collapses_close_boundaries():
    merged = merge_within([1.0, 1.5, 1.9, 10.0], merge_s=2.0)
    assert merged == [1.0, 10.0]
```

```python
# tests/stages/weave/test_fuse.py
import json
from shruti.stages.weave.fuse import fuse_beats
from shruti.contracts.speech import Utterance


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeClient:
    def __init__(self, payload):
        self._payload = payload

    class _Models:
        def __init__(self, outer):
            self._outer = outer

        def generate_content(self, model, contents, config=None):
            return FakeResponse(json.dumps(self._outer._payload))

    @property
    def models(self):
        return FakeClient._Models(self)


def test_fuse_beats_labels_kind_and_salience():
    payload = [{"idx": 0, "start_s": 0.0, "end_s": 8.0, "kind": "explain", "salience": 0.7}]
    client = FakeClient(payload)
    utterances = [Utterance(id="u1", recording_id="r1", start_s=0.0, end_s=8.0,
                             text="so today we look at derivatives", speaker="TEACHER")]
    beats = fuse_beats(client, recording_id="r1", boundaries=[0.0, 8.0],
                        utterances=utterances, board_states=[], deixis=[])
    assert len(beats) == 1
    assert beats[0].kind == "explain"
    assert beats[0].salience == 0.7
    assert "derivatives" in beats[0].transcript
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/stages/weave/ -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shruti.stages.weave'`

- [ ] **Step 3: Write the implementation**

```python
# shruti/stages/weave/__init__.py
```

```python
# shruti/stages/weave/boundaries.py
import numpy as np
from shruti.contracts.speech import Utterance
from shruti.contracts.timeline import Shot

_INFLECT = 5.0


def candidate_boundaries(utterances: list[Utterance], ink_curve, times, shots: list[Shot]) -> list[float]:
    boundaries = set()

    for a, b in zip(utterances, utterances[1:]):
        if b.start_s - a.end_s > 1.5:
            boundaries.add((a.end_s + b.start_s) / 2)

    if len(ink_curve) > 2:
        d = np.gradient(ink_curve)
        for i in range(1, len(d) - 1):
            if np.sign(d[i - 1]) != np.sign(d[i + 1]) and abs(d[i - 1] - d[i + 1]) > _INFLECT:
                boundaries.add(float(times[i]))

    boundaries.update(s.start_s for s in shots)

    return merge_within(sorted(boundaries), 2.0)


def merge_within(boundaries: list[float], merge_s: float) -> list[float]:
    if not boundaries:
        return []
    merged = [boundaries[0]]
    for b in boundaries[1:]:
        if b - merged[-1] >= merge_s:
            merged.append(b)
    return merged
```

```python
# shruti/stages/weave/fuse.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/stages/weave/ -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add shruti/stages/weave/ tests/stages/weave/
git commit -m "feat: implement WEAVE boundary detection and beat fusion"
```

---

## Task 12: GLYPH — read the board

**Files:**
- Create: `shruti/stages/glyph/__init__.py`, `read.py`
- Test: `tests/stages/glyph/test_read.py`

**Interfaces:**
- Consumes: `BoardContent`, `Region` (Task 2); the `(composited_image, unfilled_mask)` pair produced by Task 8's `composite_board_state`.
- Produces: `read_board_state(client, board_image, unfilled_mask, context: dict) -> BoardContent` — `context` keys: `surface_kind`, `grade`, `subject`, `chapter`, `transcript_excerpt`. Task 13 (ATLAS) consumes the `BoardContent` this returns.

- [ ] **Step 1: Write the failing test**

```python
# tests/stages/glyph/test_read.py
import json
from shruti.stages.glyph.read import read_board_state


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeClient:
    def __init__(self, payload):
        self._payload = payload
        self.last_contents = None

    class _Models:
        def __init__(self, outer):
            self._outer = outer

        def generate_content(self, model, contents, config=None):
            self._outer.last_contents = contents
            return FakeResponse(json.dumps(self._outer._payload))

    @property
    def models(self):
        return FakeClient._Models(self)


def test_read_board_state_parses_regions():
    payload = {"regions": [
        {"id": "r1", "bbox": [0.05, 0.1, 0.4, 0.2], "kind": "equation",
         "latex": "x^2 + 6x + 5", "role": "problem_statement", "confidence": 0.94},
        {"id": "r2", "bbox": [0.5, 0.6, 0.3, 0.1], "kind": "unreadable",
         "reason": "occluded throughout state"},
    ]}
    client = FakeClient(payload)
    content = read_board_state(
        client, board_image=b"fake-image", unfilled_mask=b"fake-mask",
        context={"surface_kind": "blackboard", "grade": 9, "subject": "math",
                 "chapter": "completing the square", "transcript_excerpt": "..."},
    )
    assert len(content.regions) == 2
    assert content.regions[0].latex == "x^2 + 6x + 5"
    assert content.regions[1].kind == "unreadable"
    assert content.regions[1].reason == "occluded throughout state"


def test_read_board_state_prompt_includes_no_guess_instruction():
    client = FakeClient({"regions": []})
    read_board_state(client, board_image=b"img", unfilled_mask=b"mask",
                      context={"surface_kind": "blackboard", "grade": 9, "subject": "math",
                               "chapter": "x", "transcript_excerpt": "y"})
    prompt = client.last_contents[0]
    assert "DO NOT" in prompt.upper() or "do not" in prompt
    assert "unreadable" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/stages/glyph/ -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shruti.stages.glyph'`

- [ ] **Step 3: Write the implementation**

```python
# shruti/stages/glyph/__init__.py
```

```python
# shruti/stages/glyph/read.py
import json
from shruti.config import Models
from shruti.contracts.board import BoardContent

_READ_PROMPT = """You are reading a photograph of a {surface_kind} from a
{grade} {subject} lesson on "{chapter}".

CONTEXT (use to resolve ambiguous handwriting, never to invent content)
Teacher said during this board state: {transcript_excerpt}

CRITICAL - OCCLUSION
The second image is an occlusion mask. Shaded regions were never visible in
the source video because the teacher stood there the whole time.
For any region overlapping the shaded mask: emit kind="unreadable" with a
reason. DO NOT infer, complete, or guess occluded content.

TASK
Return the board as a JSON object {{"regions": [...]}} of layout regions
with normalized coordinates (0-1). Each region: id, bbox [x,y,w,h], kind
(equation|text|figure|table|diagram|unreadable), latex (preserve the
teacher's exact form), plain_text, description, role, step_index,
derives_from, confidence, reason (for unreadable).
"""


def read_board_state(client, board_image, unfilled_mask, context: dict) -> BoardContent:
    prompt = _READ_PROMPT.format(**context)
    response = client.models.generate_content(
        model=Models().reasoner,
        contents=[prompt, board_image, unfilled_mask],
    )
    data = json.loads(response.text)
    return BoardContent(**data)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/stages/glyph/ -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add shruti/stages/glyph/ tests/stages/glyph/
git commit -m "feat: implement GLYPH board reading with occlusion no-guess rule"
```

---

## Task 13: ATLAS — concepts, relations, misconceptions, canonicalization

**Files:**
- Create: `shruti/stages/atlas/__init__.py`, `concepts.py`, `relations.py`, `misconceptions.py`, `canonicalize.py`
- Test: `tests/stages/atlas/test_concepts.py`, `test_relations.py`, `test_misconceptions.py`, `test_canonicalize.py`

**Interfaces:**
- Consumes: `Beat` (Task 11), `Concept`, `Edge`, `Misconception`, `BeatRef` (Task 2).
- Produces: `mine_concepts(client, beats: list[Beat], curriculum_spine: list[str] | None = None) -> list[Concept]`, `extract_relations(client, concepts: list[Concept], beats: list[Beat]) -> list[Edge]`, `mine_misconceptions(client, beats: list[Beat]) -> list[Misconception]`, `canonicalize(concepts: list[Concept], similarity_threshold: float = 0.92) -> list[Concept]` — Task 15 (VAULT atlas_store) writes the `list[Concept]`/`list[Edge]`/`list[Misconception]` this task produces.

- [ ] **Step 1: Write the failing tests**

```python
# tests/stages/atlas/test_concepts.py
import json
from shruti.stages.atlas.concepts import mine_concepts
from shruti.contracts.beat import Beat


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeClient:
    def __init__(self, payload):
        self._payload = payload

    class _Models:
        def __init__(self, outer):
            self._outer = outer

        def generate_content(self, model, contents, config=None):
            return FakeResponse(json.dumps(self._outer._payload))

    @property
    def models(self):
        return FakeClient._Models(self)


def test_mine_concepts_parses_taught_in_refs():
    payload = [{"canonical_name": "completing the square", "aliases": [],
                "taught_in_beat_ids": ["b1"]}]
    client = FakeClient(payload)
    beats = [Beat(id="b1", recording_id="r1", idx=0, start_s=0.0, end_s=5.0,
                  kind="derive", transcript="we complete the square by...")]
    concepts = mine_concepts(client, beats)
    assert concepts[0].canonical_name == "completing the square"
    assert concepts[0].taught_in[0].beat_id == "b1"
    assert concepts[0].taught_in[0].relation == "taught_in"
```

```python
# tests/stages/atlas/test_relations.py
import json
from shruti.stages.atlas.relations import extract_relations
from shruti.contracts.atlas import Concept, BeatRef
from shruti.contracts.beat import Beat


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeClient:
    def __init__(self, payload):
        self._payload = payload

    class _Models:
        def __init__(self, outer):
            self._outer = outer

        def generate_content(self, model, contents, config=None):
            return FakeResponse(json.dumps(self._outer._payload))

    @property
    def models(self):
        return FakeClient._Models(self)


def test_extract_relations_builds_requires_edges():
    payload = [{"from_concept": "factoring", "to_concept": "completing_the_square",
                "edge_type": "REQUIRES", "evidence_beat_ids": ["b1"]}]
    client = FakeClient(payload)
    concepts = [
        Concept(id="factoring", canonical_name="factoring",
                taught_in=[BeatRef(beat_id="b0", relation="taught_in")]),
        Concept(id="completing_the_square", canonical_name="completing the square",
                taught_in=[BeatRef(beat_id="b1", relation="taught_in")]),
    ]
    beats = [Beat(id="b1", recording_id="r1", idx=1, start_s=5.0, end_s=10.0,
                  kind="derive", transcript="this needs factoring first")]
    edges = extract_relations(client, concepts, beats)
    assert edges[0].edge_type == "REQUIRES"
    assert edges[0].evidence[0].beat_id == "b1"
    assert edges[0].evidence[0].relation == "evidence_for"
```

```python
# tests/stages/atlas/test_misconceptions.py
import json
from shruti.stages.atlas.misconceptions import mine_misconceptions
from shruti.contracts.beat import Beat


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeClient:
    def __init__(self, payload):
        self._payload = payload

    class _Models:
        def __init__(self, outer):
            self._outer = outer

        def generate_content(self, model, contents, config=None):
            return FakeResponse(json.dumps(self._outer._payload))

    @property
    def models(self):
        return FakeClient._Models(self)


def test_mine_misconceptions_preserves_teacher_phrasing():
    payload = [{"concept_id": "completing_the_square",
                "statement": "treats (a+b)^2 as a^2+b^2",
                "teacher_phrasing": "yeh sabse common galti hai",
                "correct_understanding": "(a+b)^2 = a^2 + 2ab + b^2",
                "pre_empted_at_beat": "b1"}]
    client = FakeClient(payload)
    beats = [Beat(id="b1", recording_id="r1", idx=0, start_s=0.0, end_s=5.0,
                  kind="explain", transcript="yeh sabse common galti hai...")]
    misconceptions = mine_misconceptions(client, beats)
    assert misconceptions[0].teacher_phrasing == "yeh sabse common galti hai"
    assert misconceptions[0].pre_empted_at_beat == "b1"
```

```python
# tests/stages/atlas/test_canonicalize.py
from shruti.contracts.atlas import Concept, BeatRef
from shruti.stages.atlas.canonicalize import canonicalize


def test_canonicalize_merges_near_duplicate_names():
    concepts = [
        Concept(id="c1", canonical_name="completing the square",
                taught_in=[BeatRef(beat_id="b1", relation="taught_in")]),
        Concept(id="c2", canonical_name="complete the square",
                taught_in=[BeatRef(beat_id="b2", relation="taught_in")]),
        Concept(id="c3", canonical_name="quadratic formula",
                taught_in=[BeatRef(beat_id="b3", relation="taught_in")]),
    ]
    merged = canonicalize(concepts, similarity_threshold=0.85)
    assert len(merged) == 2
    square_concept = next(c for c in merged if "square" in c.canonical_name)
    assert {ref.beat_id for ref in square_concept.taught_in} == {"b1", "b2"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/stages/atlas/ -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shruti.stages.atlas'`

- [ ] **Step 3: Write the implementation**

```python
# shruti/stages/atlas/__init__.py
```

```python
# shruti/stages/atlas/concepts.py
import json
from shruti.config import Models
from shruti.contracts.atlas import Concept, BeatRef
from shruti.contracts.beat import Beat

_CONCEPTS_PROMPT = """Beats from a lesson:
{beats}

Curriculum spine (normalize concept names against this when given): {spine}

For each concept genuinely TAUGHT (introduced/explained), not merely
mentioned, return: canonical_name, aliases, taught_in_beat_ids.
Return a JSON array.
"""


def mine_concepts(client, beats: list[Beat], curriculum_spine: list[str] | None = None) -> list[Concept]:
    beats_text = "\n".join(f"[{b.id}] {b.transcript}" for b in beats)
    response = client.models.generate_content(
        model=Models().reasoner,
        contents=[_CONCEPTS_PROMPT.format(beats=beats_text, spine=curriculum_spine or [])],
    )
    rows = json.loads(response.text)
    concepts = []
    for row in rows:
        slug = row["canonical_name"].lower().replace(" ", "_")
        concepts.append(Concept(
            id=slug,
            canonical_name=row["canonical_name"],
            aliases=row.get("aliases", []),
            taught_in=[BeatRef(beat_id=bid, relation="taught_in")
                       for bid in row["taught_in_beat_ids"]],
        ))
    return concepts
```

```python
# shruti/stages/atlas/relations.py
import json
import uuid
from shruti.config import Models
from shruti.contracts.atlas import Concept, Edge, BeatRef
from shruti.contracts.beat import Beat

_RELATIONS_PROMPT = """Concepts taught in this lesson: {concepts}

Beats: {beats}

Identify edges between concepts. Edge types: REQUIRES (prerequisite),
PART_OF (sub-concept), EXEMPLIFIES (worked example -> concept),
CONTRASTS_WITH (commonly confused pair). Return a JSON array of
{{from_concept, to_concept, edge_type, evidence_beat_ids}}.
"""


def extract_relations(client, concepts: list[Concept], beats: list[Beat]) -> list[Edge]:
    concept_names = [c.canonical_name for c in concepts]
    beats_text = "\n".join(f"[{b.id}] {b.transcript}" for b in beats)
    response = client.models.generate_content(
        model=Models().reasoner,
        contents=[_RELATIONS_PROMPT.format(concepts=concept_names, beats=beats_text)],
    )
    rows = json.loads(response.text)
    return [
        Edge(
            id=str(uuid.uuid4()),
            from_concept=row["from_concept"],
            to_concept=row["to_concept"],
            edge_type=row["edge_type"],
            evidence=[BeatRef(beat_id=bid, relation="evidence_for")
                      for bid in row["evidence_beat_ids"]],
        )
        for row in rows
    ]
```

```python
# shruti/stages/atlas/misconceptions.py
import json
import uuid
from shruti.config import Models
from shruti.contracts.atlas import Misconception
from shruti.contracts.beat import Beat

_MISCONCEPTIONS_PROMPT = """Find every point where the teacher PRE-EMPTED a
student error (signals: "everyone gets this wrong", "don't confuse this
with...", "yaad rakhna, X is NOT Y", or any construction naming a wrong
belief to correct it).

Beats: {beats}

For each, return: concept_id, statement (general, testable), teacher_phrasing
(verbatim, code-mixing intact), correct_understanding, pre_empted_at_beat.
Only include errors the teacher NAMED. Return a JSON array.
"""


def mine_misconceptions(client, beats: list[Beat]) -> list[Misconception]:
    beats_text = "\n".join(f"[{b.id}] {b.transcript}" for b in beats)
    response = client.models.generate_content(
        model=Models().reasoner,
        contents=[_MISCONCEPTIONS_PROMPT.format(beats=beats_text)],
    )
    rows = json.loads(response.text)
    return [
        Misconception(
            id=str(uuid.uuid4()),
            concept_id=row["concept_id"],
            statement=row["statement"],
            teacher_phrasing=row.get("teacher_phrasing"),
            correct_understanding=row["correct_understanding"],
            pre_empted_at_beat=row["pre_empted_at_beat"],
        )
        for row in rows
    ]
```

```python
# shruti/stages/atlas/canonicalize.py
import difflib
from shruti.contracts.atlas import Concept


def canonicalize(concepts: list[Concept], similarity_threshold: float = 0.92) -> list[Concept]:
    merged: list[Concept] = []
    for c in concepts:
        match = next(
            (m for m in merged
             if difflib.SequenceMatcher(None, m.canonical_name, c.canonical_name).ratio()
             >= similarity_threshold),
            None,
        )
        if match is None:
            merged.append(c)
            continue
        merged[merged.index(match)] = match.model_copy(update={
            "aliases": list(set(match.aliases) | set(c.aliases) | {c.canonical_name}),
            "taught_in": match.taught_in + c.taught_in,
        })
    return merged
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/stages/atlas/ -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add shruti/stages/atlas/ tests/stages/atlas/
git commit -m "feat: implement ATLAS concept mining, relations, misconceptions, canonicalization"
```

---

## Task 14: VAULT — Reel and Ledger writers

**Files:**
- Create: `shruti/vault/__init__.py`, `reel.py`, `ledger.py`
- Create: `tests/vault/__init__.py`, `tests/conftest.py`
- Test: `tests/vault/test_reel.py`, `tests/vault/test_ledger.py`

**Interfaces:**
- Consumes: `get_pool`, `apply_migrations` (Task 3); `Recording`, `Beat`, `BoardState` (Task 2).
- Produces: `write_recording(conn, recording: Recording) -> None`, `write_utterances(conn, utterances: list[Utterance]) -> None`, `write_beats(conn, beats: list[Beat]) -> None`, `get_beats(conn, recording_id: str) -> list[Beat]` (`reel.py`); `write_board_state(conn, board_state: BoardState) -> None`, `board_state_at(conn, recording_id: str, t: float) -> BoardState | None` (`ledger.py`). `conn` accepts either an `asyncpg.Pool` or `asyncpg.Connection` — both expose `execute`/`fetch`/`fetchrow`. Task 16 (LENS) calls `board_state_at` directly for the `board_at` ADK tool.

- [ ] **Step 1: Write the shared test fixture and the failing tests**

```python
# tests/vault/__init__.py
```

```python
# tests/conftest.py — top-level so it's shared by tests/vault/, tests/evals/, and any other suite that needs a live, rolled-back Postgres connection
import pytest_asyncio
from shruti.db import get_pool, apply_migrations


@pytest_asyncio.fixture
async def db_conn():
    pool = await get_pool()
    await apply_migrations(pool)
    conn = await pool.acquire()
    tx = conn.transaction()
    await tx.start()
    try:
        yield conn
    finally:
        await tx.rollback()
        await pool.release(conn)
        await pool.close()
```

```python
# tests/vault/test_reel.py
import pytest
from shruti.contracts.recording import Recording, SurfaceKind
from shruti.contracts.beat import Beat
from shruti.vault.reel import write_recording, write_beats, get_beats


@pytest.mark.asyncio
async def test_write_and_read_recording_and_beats(db_conn):
    rec = Recording(id="r_test_1", source_uri="gs://x", duration_s=60.0, fps=30.0,
                     surface_kind=SurfaceKind.BLACKBOARD)
    await write_recording(db_conn, rec)
    beat = Beat(id="b_test_1", recording_id=rec.id, idx=0, start_s=0.0, end_s=5.0,
                kind="explain", transcript="hello")
    await write_beats(db_conn, [beat])
    beats = await get_beats(db_conn, rec.id)
    assert len(beats) == 1
    assert beats[0].transcript == "hello"
```

```python
# tests/vault/test_ledger.py
import pytest
from shruti.contracts.recording import Recording, SurfaceKind
from shruti.contracts.board import BoardState
from shruti.vault.reel import write_recording
from shruti.vault.ledger import write_board_state, board_state_at


@pytest.mark.asyncio
async def test_board_state_at_returns_state_valid_at_time(db_conn):
    rec = Recording(id="r_test_2", source_uri="gs://x", duration_s=60.0, fps=30.0,
                     surface_kind=SurfaceKind.BLACKBOARD)
    await write_recording(db_conn, rec)
    bs = BoardState(id="bs_test_1", recording_id=rec.id, idx=0, valid_from_s=0.0,
                     valid_to_s=20.0, composited_uri="gs://x/bs1.png", ended_by="erase")
    await write_board_state(db_conn, bs)
    found = await board_state_at(db_conn, rec.id, t=10.0)
    assert found is not None
    assert found.id == "bs_test_1"
    assert await board_state_at(db_conn, rec.id, t=25.0) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose -f docker/compose.yaml up -d postgres && uv run pytest tests/vault/test_reel.py tests/vault/test_ledger.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shruti.vault'`

- [ ] **Step 3: Write the implementation**

```python
# shruti/vault/__init__.py
```

```python
# shruti/vault/reel.py
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
```

```python
# shruti/vault/ledger.py
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
            await conn.execute(
                """INSERT INTO board_region (id, board_state_id, bbox, kind, latex,
                                              plain_text, description, role, step_index,
                                              derives_from, confidence)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                   ON CONFLICT (id) DO NOTHING""",
                region.id, board_state.id, json.dumps(region.bbox), region.kind,
                region.latex, region.plain_text, region.description, region.role,
                region.step_index, region.derives_from, region.confidence,
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/vault/test_reel.py tests/vault/test_ledger.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add shruti/vault/__init__.py shruti/vault/reel.py shruti/vault/ledger.py tests/conftest.py tests/vault/
git commit -m "feat: implement VAULT Reel and Ledger writers"
```

---

## Task 15: VAULT — Atlas store, vector index, object storage, and the provenance invariant

**Files:**
- Create: `shruti/vault/atlas_store.py`, `index.py`, `objects.py`
- Test: `tests/vault/test_atlas_store.py`, `tests/vault/test_index.py`, `tests/vault/test_objects.py`

**Interfaces:**
- Consumes: `Concept`, `Edge`, `Misconception`, `BeatRef` (Task 2); `write_recording`, `write_beats` (Task 14, needed to set up FK-valid test fixtures).
- Produces: `write_concepts(conn, concepts: list[Concept]) -> None`, `write_edges(conn, edges: list[Edge]) -> None`, `write_misconceptions(conn, misconceptions: list[Misconception]) -> None`, `check_provenance_invariant(conn) -> list[str]` (empty list = pass — this **is** E4, Task 19 imports it directly); `write_embedding(conn, kind: str, ref_id: str, recording_id: str | None, vec: list[float], text: str) -> None`, `similarity_search(conn, query_vec: list[float], kind: str, k: int = 8) -> list[dict]`; `class ObjectStore` with `upload(local_path: str, dest_path: str) -> str` and `download(uri: str, local_path: str) -> None`, constructed as `ObjectStore(bucket_name: str, client=None)` so tests inject a fake client.

- [ ] **Step 1: Write the failing tests**

```python
# tests/vault/test_atlas_store.py
import pytest
from shruti.contracts.recording import Recording, SurfaceKind
from shruti.contracts.beat import Beat
from shruti.contracts.atlas import Concept, BeatRef
from shruti.vault.reel import write_recording, write_beats
from shruti.vault.atlas_store import write_concepts, check_provenance_invariant


@pytest.mark.asyncio
async def test_provenance_invariant_flags_orphan_concept_and_clears_on_proper_write(db_conn):
    rec = Recording(id="r_test_3", source_uri="gs://x", duration_s=10.0, fps=30.0,
                     surface_kind=SurfaceKind.BLACKBOARD)
    await write_recording(db_conn, rec)
    beat = Beat(id="b_test_3", recording_id=rec.id, idx=0, start_s=0.0, end_s=1.0,
                kind="explain", transcript="x")
    await write_beats(db_conn, [beat])

    # Simulates a bug: a concept inserted directly, bypassing write_concepts's
    # beat_ref insert — this is exactly the case the invariant must catch.
    await db_conn.execute(
        "INSERT INTO concept (id, canonical_name) VALUES ('c_bad', 'orphan concept')"
    )
    violations = await check_provenance_invariant(db_conn)
    assert any("c_bad" in v for v in violations)

    good = Concept(id="c_good", canonical_name="good concept",
                    taught_in=[BeatRef(beat_id=beat.id, relation="taught_in")])
    await write_concepts(db_conn, [good])
    violations_after = await check_provenance_invariant(db_conn)
    assert not any("c_good" in v for v in violations_after)
```

```python
# tests/vault/test_index.py
import pytest
from shruti.vault.index import write_embedding, similarity_search


@pytest.mark.asyncio
async def test_similarity_search_orders_by_distance(db_conn):
    close_vec = [1.0] * 3072
    far_vec = [0.0] * 3072
    await write_embedding(db_conn, "concept", "c1", None, close_vec, "completing the square")
    await write_embedding(db_conn, "concept", "c2", None, far_vec, "unrelated concept")
    results = await similarity_search(db_conn, close_vec, "concept", k=2)
    assert results[0]["ref_id"] == "c1"
```

```python
# tests/vault/test_objects.py
from shruti.vault.objects import ObjectStore


class FakeBlob:
    def __init__(self, store, path):
        self._store, self._path = store, path

    def upload_from_filename(self, local_path):
        with open(local_path, "rb") as f:
            self._store[self._path] = f.read()

    def download_to_filename(self, local_path):
        with open(local_path, "wb") as f:
            f.write(self._store[self._path])


class FakeBucket:
    def __init__(self, store):
        self._store = store

    def blob(self, path):
        return FakeBlob(self._store, path)


class FakeGcsClient:
    def __init__(self):
        self._store = {}

    def bucket(self, name):
        return FakeBucket(self._store)


def test_object_store_roundtrip(tmp_path):
    store = ObjectStore(bucket_name="test-bucket", client=FakeGcsClient())
    src = tmp_path / "in.png"
    src.write_bytes(b"pixel-data")

    uri = store.upload(str(src), "board/bs1.png")
    assert uri == "gs://test-bucket/board/bs1.png"

    dest = tmp_path / "out.png"
    store.download(uri, str(dest))
    assert dest.read_bytes() == b"pixel-data"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/vault/test_atlas_store.py tests/vault/test_index.py tests/vault/test_objects.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shruti.vault.atlas_store'`

- [ ] **Step 3: Write the implementation**

```python
# shruti/vault/atlas_store.py
from shruti.contracts.atlas import Concept, Edge, Misconception


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


async def check_provenance_invariant(conn) -> list[str]:
    violations = []
    for table, kind in (("concept", "concept"), ("concept_edge", "edge"),
                         ("misconception", "misconception")):
        rows = await conn.fetch(
            f"""SELECT t.id FROM {table} t
                LEFT JOIN beat_ref r ON r.subject_kind=$1 AND r.subject_id=t.id
                WHERE r.id IS NULL""",
            kind,
        )
        violations += [f"{kind} {r['id']} has no beat_ref" for r in rows]
    return violations
```

```python
# shruti/vault/index.py

def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(str(float(x)) for x in vec) + "]"


async def write_embedding(conn, kind: str, ref_id: str, recording_id: str | None,
                           vec: list[float], text: str) -> None:
    await conn.execute(
        """INSERT INTO embedding (id, kind, ref_id, recording_id, vec, text)
           VALUES ($1,$2,$3,$4,$5::vector,$6)
           ON CONFLICT (id) DO NOTHING""",
        f"{kind}:{ref_id}", kind, ref_id, recording_id, _vec_literal(vec), text,
    )


async def similarity_search(conn, query_vec: list[float], kind: str, k: int = 8) -> list[dict]:
    rows = await conn.fetch(
        """SELECT ref_id, text, vec <=> $1::vector AS distance FROM embedding
           WHERE kind=$2 ORDER BY vec <=> $1::vector LIMIT $3""",
        _vec_literal(query_vec), kind, k,
    )
    return [{"ref_id": r["ref_id"], "text": r["text"], "distance": r["distance"]} for r in rows]
```

```python
# shruti/vault/objects.py
from google.cloud import storage


class ObjectStore:
    def __init__(self, bucket_name: str, client=None):
        self._bucket_name = bucket_name
        self._client = client or storage.Client()

    def upload(self, local_path: str, dest_path: str) -> str:
        bucket = self._client.bucket(self._bucket_name)
        bucket.blob(dest_path).upload_from_filename(local_path)
        return f"gs://{self._bucket_name}/{dest_path}"

    def download(self, uri: str, local_path: str) -> None:
        prefix = f"gs://{self._bucket_name}/"
        assert uri.startswith(prefix), f"{uri} is not in bucket {self._bucket_name}"
        dest_path = uri[len(prefix):]
        bucket = self._client.bucket(self._bucket_name)
        bucket.blob(dest_path).download_to_filename(local_path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/vault/test_atlas_store.py tests/vault/test_index.py tests/vault/test_objects.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add shruti/vault/atlas_store.py shruti/vault/index.py shruti/vault/objects.py tests/vault/test_atlas_store.py tests/vault/test_index.py tests/vault/test_objects.py
git commit -m "feat: implement VAULT Atlas store, vector index, object storage, provenance invariant"
```

---

## Task 16: LENS — retrieval routing and the ADK tools handed to the tutor

**Convention this task fixes**: for a `concept_edge` row `(from_concept=X, to_concept=Y, edge_type="REQUIRES")`, read it as "X requires Y" — Y is the prerequisite. `graph_traverse` follows `from_concept -> to_concept` recursively from the query concept.

**Files:**
- Create: `shruti/lens/__init__.py`, `route.py`, `retrievers.py`, `adk_tools.py`
- Test: `tests/vault/test_lens_retrievers.py`, `tests/stages/test_route.py`, `tests/vault/test_adk_tools.py`

**Interfaces:**
- Consumes: `board_state_at` (Task 14), `write_concepts`/`write_edges`/`write_misconceptions` (Task 15, for test fixtures), `Beat` (Task 2).
- Produces: `classify_intent(client, query: str) -> str`, `graph_traverse(conn, concept_id: str, edge_type: str, depth: int = 2) -> list[dict]` (each: `{"concept_id": str, "depth": int}`), `timeline_lookup(conn, concept_id: str, recording_ids: list[str] | None = None) -> list[Beat]`, `_build_lesson_functions(conn) -> dict[str, Callable]`, `build_lesson_tools(conn) -> list` (of ADK `FunctionTool`) — this is the handoff seam to the (not-yet-built) live tutor: whatever agent embeds SHRUTI's LENS tools calls `build_lesson_tools(conn)` and passes the result as its `tools=[...]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/stages/test_route.py
from shruti.lens.route import classify_intent


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeClient:
    def __init__(self, label):
        self._label = label

    class _Models:
        def __init__(self, outer):
            self._outer = outer

        def generate_content(self, model, contents, config=None):
            return FakeResponse(self._outer._label)

    @property
    def models(self):
        return FakeClient._Models(self)


def test_classify_intent_recognizes_known_label():
    assert classify_intent(FakeClient("prerequisite"), "what do I need before this?") == "prerequisite"


def test_classify_intent_defaults_to_other_for_unknown_label():
    assert classify_intent(FakeClient("gibberish-label"), "asdf") == "other"
```

```python
# tests/vault/test_lens_retrievers.py
import pytest
from shruti.contracts.recording import Recording, SurfaceKind
from shruti.contracts.beat import Beat
from shruti.contracts.atlas import Concept, Edge, BeatRef
from shruti.vault.reel import write_recording, write_beats
from shruti.vault.atlas_store import write_concepts, write_edges
from shruti.lens.retrievers import graph_traverse, timeline_lookup


@pytest.mark.asyncio
async def test_graph_traverse_follows_requires_chain(db_conn):
    rec = Recording(id="r_lens_1", source_uri="gs://x", duration_s=10.0, fps=30.0,
                     surface_kind=SurfaceKind.BLACKBOARD)
    await write_recording(db_conn, rec)
    beat = Beat(id="b_lens_1", recording_id=rec.id, idx=0, start_s=0.0, end_s=1.0,
                kind="explain", transcript="x")
    await write_beats(db_conn, [beat])
    concepts = [
        Concept(id="quadratic_formula", canonical_name="quadratic formula",
                taught_in=[BeatRef(beat_id=beat.id, relation="taught_in")]),
        Concept(id="completing_the_square", canonical_name="completing the square",
                taught_in=[BeatRef(beat_id=beat.id, relation="taught_in")]),
        Concept(id="factoring", canonical_name="factoring",
                taught_in=[BeatRef(beat_id=beat.id, relation="taught_in")]),
    ]
    await write_concepts(db_conn, concepts)
    edges = [
        Edge(id="e1", from_concept="quadratic_formula", to_concept="completing_the_square",
             edge_type="REQUIRES", evidence=[BeatRef(beat_id=beat.id, relation="evidence_for")]),
        Edge(id="e2", from_concept="completing_the_square", to_concept="factoring",
             edge_type="REQUIRES", evidence=[BeatRef(beat_id=beat.id, relation="evidence_for")]),
    ]
    await write_edges(db_conn, edges)

    result = await graph_traverse(db_conn, "quadratic_formula", "REQUIRES", depth=2)
    depth_by_id = {r["concept_id"]: r["depth"] for r in result}
    assert depth_by_id["completing_the_square"] == 1
    assert depth_by_id["factoring"] == 2


@pytest.mark.asyncio
async def test_timeline_lookup_returns_beats_for_concept(db_conn):
    rec = Recording(id="r_lens_2", source_uri="gs://x", duration_s=10.0, fps=30.0,
                     surface_kind=SurfaceKind.BLACKBOARD)
    await write_recording(db_conn, rec)
    beat = Beat(id="b_lens_2", recording_id=rec.id, idx=0, start_s=3.0, end_s=8.0,
                kind="derive", transcript="here is completing the square")
    await write_beats(db_conn, [beat])
    concept = Concept(id="cts_lens", canonical_name="completing the square",
                       taught_in=[BeatRef(beat_id=beat.id, relation="taught_in")])
    await write_concepts(db_conn, [concept])

    beats = await timeline_lookup(db_conn, "cts_lens", recording_ids=[rec.id])
    assert len(beats) == 1
    assert beats[0].id == beat.id
```

```python
# tests/vault/test_adk_tools.py
import pytest
from shruti.contracts.recording import Recording, SurfaceKind
from shruti.contracts.beat import Beat
from shruti.contracts.board import BoardState
from shruti.contracts.atlas import Concept, Misconception, BeatRef
from shruti.vault.reel import write_recording, write_beats
from shruti.vault.ledger import write_board_state
from shruti.vault.atlas_store import write_concepts, write_misconceptions
from shruti.lens.adk_tools import _build_lesson_functions, build_lesson_tools


@pytest.mark.asyncio
async def test_recall_lesson_returns_teacher_words_and_board_image(db_conn):
    rec = Recording(id="r_tool_1", source_uri="gs://x", duration_s=10.0, fps=30.0,
                     surface_kind=SurfaceKind.BLACKBOARD)
    await write_recording(db_conn, rec)
    beat = Beat(id="b_tool_1", recording_id=rec.id, idx=0, start_s=2.0, end_s=6.0,
                kind="derive", transcript="sir taught completing the square here")
    await write_beats(db_conn, [beat])
    concept = Concept(id="cts_tool", canonical_name="completing the square",
                       taught_in=[BeatRef(beat_id=beat.id, relation="taught_in")])
    await write_concepts(db_conn, [concept])
    bs = BoardState(id="bs_tool_1", recording_id=rec.id, idx=0, valid_from_s=0.0,
                     valid_to_s=10.0, composited_uri="gs://x/bs.png", ended_by="erase")
    await write_board_state(db_conn, bs)

    tools = _build_lesson_functions(db_conn)
    result = await tools["recall_lesson"]("cts_tool", [rec.id])
    assert result["found"] is True
    assert "completing the square" in result["teacher_words"]
    assert result["board_image_uri"] == "gs://x/bs.png"


@pytest.mark.asyncio
async def test_known_misconceptions_returns_teacher_phrasing(db_conn):
    rec = Recording(id="r_tool_2", source_uri="gs://x", duration_s=10.0, fps=30.0,
                     surface_kind=SurfaceKind.BLACKBOARD)
    await write_recording(db_conn, rec)
    beat = Beat(id="b_tool_2", recording_id=rec.id, idx=0, start_s=0.0, end_s=1.0,
                kind="explain", transcript="x")
    await write_beats(db_conn, [beat])
    concept = Concept(id="cts_tool2", canonical_name="completing the square")
    await write_concepts(db_conn, [concept])
    misconception = Misconception(id="m_tool_1", concept_id="cts_tool2",
                                   statement="treats (a+b)^2 as a^2+b^2",
                                   teacher_phrasing="yeh sabse common galti hai",
                                   correct_understanding="(a+b)^2 = a^2+2ab+b^2",
                                   pre_empted_at_beat=beat.id)
    await write_misconceptions(db_conn, [misconception])

    tools = _build_lesson_functions(db_conn)
    result = await tools["known_misconceptions"]("cts_tool2")
    assert result[0]["teacher_phrasing"] == "yeh sabse common galti hai"


@pytest.mark.asyncio
async def test_build_lesson_tools_returns_four_tools(db_conn):
    tools = build_lesson_tools(db_conn)
    assert len(tools) == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/stages/test_route.py tests/vault/test_lens_retrievers.py tests/vault/test_adk_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shruti.lens'`

- [ ] **Step 3: Write the implementation**

```python
# shruti/lens/__init__.py
```

```python
# shruti/lens/route.py
from shruti.config import Models

_VALID_INTENTS = {"definition", "explanation", "prerequisite", "why_stuck",
                   "learning_path", "show_me_where", "what_did_sir_say",
                   "what_was_on_board", "other"}

_PROMPT = """Classify this student question into exactly one label: definition,
explanation, prerequisite, why_stuck, learning_path, show_me_where,
what_did_sir_say, what_was_on_board, other.

Question: {query}
Reply with only the label.
"""


def classify_intent(client, query: str) -> str:
    response = client.models.generate_content(
        model=Models().router,
        contents=[_PROMPT.format(query=query)],
    )
    label = response.text.strip().lower()
    return label if label in _VALID_INTENTS else "other"
```

```python
# shruti/lens/retrievers.py
from shruti.contracts.beat import Beat


async def graph_traverse(conn, concept_id: str, edge_type: str, depth: int = 2) -> list[dict]:
    rows = await conn.fetch(
        """WITH RECURSIVE prereqs AS (
               SELECT to_concept AS concept_id, 1 AS depth
               FROM concept_edge WHERE from_concept=$1 AND edge_type=$2
               UNION ALL
               SELECT ce.to_concept, p.depth + 1
               FROM concept_edge ce
               JOIN prereqs p ON ce.from_concept = p.concept_id
               WHERE ce.edge_type=$2 AND p.depth < $3
           )
           SELECT concept_id, MIN(depth) AS depth FROM prereqs
           GROUP BY concept_id ORDER BY depth""",
        concept_id, edge_type, depth,
    )
    return [{"concept_id": r["concept_id"], "depth": r["depth"]} for r in rows]


async def timeline_lookup(conn, concept_id: str, recording_ids: list[str] | None = None) -> list[Beat]:
    query = """SELECT b.id, b.recording_id, b.idx, b.start_s, b.end_s, b.kind,
                      b.board_state_id, b.salience, b.transcript
               FROM beat b
               JOIN beat_ref r ON r.beat_id = b.id
               WHERE r.subject_kind='concept' AND r.subject_id=$1"""
    params = [concept_id]
    if recording_ids:
        query += " AND b.recording_id = ANY($2)"
        params.append(recording_ids)
    query += " ORDER BY b.start_s"
    rows = await conn.fetch(query, *params)
    return [
        Beat(id=r["id"], recording_id=r["recording_id"], idx=r["idx"], start_s=r["start_s"],
             end_s=r["end_s"], kind=r["kind"], board_state_id=r["board_state_id"],
             salience=r["salience"], transcript=r["transcript"])
        for r in rows
    ]
```

```python
# shruti/lens/adk_tools.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/stages/test_route.py tests/vault/test_lens_retrievers.py tests/vault/test_adk_tools.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add shruti/lens/ tests/stages/test_route.py tests/vault/test_lens_retrievers.py tests/vault/test_adk_tools.py
git commit -m "feat: implement LENS retrieval routing and the tutor-facing ADK tools"
```

---

## Task 17: Gemini client infrastructure — structured extraction, cost tracking, Batch API, caching

**Files:**
- Create: `shruti/gemini/__init__.py`, `client.py`, `batch.py`, `cache.py`
- Test: `tests/gemini/__init__.py`, `test_client.py`, `test_batch.py`, `test_cache.py`

**Interfaces:**
- Produces: `async def extract(client, prompt: str, schema: dict, parts: list, model: str, cached_content: str | None = None) -> dict`, `class CostTracker` with `record(invocation_id: str, cost_usd: float) -> None` and `total_for(invocation_id: str) -> float`, `async def submit_batch(client, requests: list[dict], model: str) -> str`, `async def poll_batch(client, job_name: str, poll_interval_s: float = 20.0) -> str`, `async def collect_batch(client, job_name: str) -> list[dict]`, `async def create_cache(client, model: str, content: list, ttl_seconds: int, display_name: str) -> str`. Task 18's `CostGuardPlugin` consumes `CostTracker` directly.

- [ ] **Step 1: Write the failing tests**

```python
# tests/gemini/__init__.py
```

```python
# tests/gemini/test_client.py
import json
import pytest
from shruti.gemini.client import extract, CostTracker


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeClient:
    def __init__(self, payload):
        self._payload = payload
        self.last_config = None

    class _Models:
        def __init__(self, outer):
            self._outer = outer

        async def generate_content(self, model, contents, config=None):
            self._outer.last_config = config
            return FakeResponse(json.dumps(self._outer._payload))

    @property
    def models(self):
        return FakeClient._Models(self)


@pytest.mark.asyncio
async def test_extract_parses_json_and_sets_schema_config():
    client = FakeClient({"regions": []})
    result = await extract(client, prompt="read this", schema={"type": "object"},
                            parts=[b"img"], model="gemini-3.5-flash")
    assert result == {"regions": []}
    assert client.last_config["response_schema"] == {"type": "object"}
    assert client.last_config["response_mime_type"] == "application/json"


def test_cost_tracker_accumulates_per_invocation():
    tracker = CostTracker()
    tracker.record("inv1", 0.10)
    tracker.record("inv1", 0.05)
    tracker.record("inv2", 1.00)
    assert tracker.total_for("inv1") == pytest.approx(0.15)
    assert tracker.total_for("inv2") == pytest.approx(1.00)
    assert tracker.total_for("unknown") == 0.0
```

```python
# tests/gemini/test_batch.py
import pytest
from shruti.gemini.batch import submit_batch, poll_batch, collect_batch


class FakeUpload:
    name = "files/abc"


class FakeJob:
    def __init__(self, name, state):
        self.name = name
        self.state = state


class FakeFilesApi:
    async def upload(self, jsonl, mime_type):
        return FakeUpload()


class FakeBatchesApi:
    def __init__(self, states):
        self._states = list(states)
        self._job_name = "batches/1"

    async def create(self, model, src):
        return FakeJob(self._job_name, self._states[0])

    async def get(self, job_name):
        state = self._states.pop(0) if len(self._states) > 1 else self._states[0]
        return FakeJob(job_name, state)

    async def collect(self, job):
        return [{"result": "ok"}]


class FakeClient:
    def __init__(self, states):
        self.files = FakeFilesApi()
        self.batches = FakeBatchesApi(states)


@pytest.mark.asyncio
async def test_submit_batch_returns_job_name():
    client = FakeClient(states=["SUCCEEDED"])
    job_name = await submit_batch(client, requests=[{"a": 1}], model="gemini-3.5-flash")
    assert job_name == "batches/1"


@pytest.mark.asyncio
async def test_poll_batch_waits_through_pending_then_returns_final_state():
    client = FakeClient(states=["PENDING", "RUNNING", "SUCCEEDED"])
    state = await poll_batch(client, job_name="batches/1", poll_interval_s=0.01)
    assert state == "SUCCEEDED"


@pytest.mark.asyncio
async def test_collect_batch_returns_results():
    client = FakeClient(states=["SUCCEEDED"])
    results = await collect_batch(client, job_name="batches/1")
    assert results == [{"result": "ok"}]
```

```python
# tests/gemini/test_cache.py
import pytest
from shruti.gemini.cache import create_cache


class FakeCache:
    name = "cachedContents/abc"


class FakeCachesApi:
    async def create(self, model, contents, ttl, display_name):
        return FakeCache()


class FakeClient:
    def __init__(self):
        self.caches = FakeCachesApi()


@pytest.mark.asyncio
async def test_create_cache_returns_cache_name():
    client = FakeClient()
    name = await create_cache(client, model="gemini-3.5-flash", content=["schema text"],
                               ttl_seconds=3600, display_name="extraction-schema")
    assert name == "cachedContents/abc"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/gemini/ -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shruti.gemini'`

- [ ] **Step 3: Write the implementation**

```python
# shruti/gemini/__init__.py
```

```python
# shruti/gemini/client.py
import json


async def extract(client, prompt: str, schema: dict, parts: list, model: str,
                    cached_content: str | None = None) -> dict:
    """Constrained decoding. The paper measured relation-extraction F1 collapsing
    76% -> 18% without format enforcement — schema is load-bearing, not decoration."""
    config = {"response_mime_type": "application/json", "response_schema": schema}
    if cached_content:
        config["cached_content"] = cached_content
    response = await client.models.generate_content(
        model=model, contents=[*parts, prompt], config=config,
    )
    return json.loads(response.text)


class CostTracker:
    def __init__(self):
        self._spend: dict[str, float] = {}

    def record(self, invocation_id: str, cost_usd: float) -> None:
        self._spend[invocation_id] = self._spend.get(invocation_id, 0.0) + cost_usd

    def total_for(self, invocation_id: str) -> float:
        return self._spend.get(invocation_id, 0.0)
```

```python
# shruti/gemini/batch.py
import asyncio
import json


async def submit_batch(client, requests: list[dict], model: str) -> str:
    jsonl = "\n".join(json.dumps(r) for r in requests)
    upload = await client.files.upload(jsonl, mime_type="application/jsonl")
    job = await client.batches.create(model=model, src=upload.name)
    return job.name


async def poll_batch(client, job_name: str, poll_interval_s: float = 20.0) -> str:
    while True:
        job = await client.batches.get(job_name)
        if job.state not in ("PENDING", "RUNNING"):
            return job.state
        await asyncio.sleep(poll_interval_s)


async def collect_batch(client, job_name: str) -> list[dict]:
    job = await client.batches.get(job_name)
    return await client.batches.collect(job)
```

```python
# shruti/gemini/cache.py

async def create_cache(client, model: str, content: list, ttl_seconds: int,
                        display_name: str) -> str:
    cache = await client.caches.create(
        model=model, contents=content, ttl=f"{ttl_seconds}s", display_name=display_name,
    )
    return cache.name
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/gemini/ -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add shruti/gemini/ tests/gemini/
git commit -m "feat: implement Gemini client infra — extraction, cost tracking, Batch API, caching"
```

---

## Task 18: ADK orchestration — pipeline wiring, tools, plugins, stage state machine

**Scope note**: this task tests *wiring*, not live LLM behavior — constructing `LlmAgent`/`SequentialAgent`/`ParallelAgent` objects is pure object construction with no network call, so these tests run with the real `google-adk` package and no fakes for the agent classes themselves. Only `BasePlugin` callback arguments are faked, since those are simple data-carrying objects at the callback boundary.

**Files:**
- Create: `shruti/agents/__init__.py`, `pipeline.py`, `tools.py`, `plugins.py`, `state.py`
- Test: `tests/agents/__init__.py`, `test_pipeline.py`, `test_tools.py`, `test_plugins.py`, `test_state.py`

**Interfaces:**
- Consumes: `Models` (Task 1); `probe_video`, `normalize_video`, `fingerprint` (Task 4); `detect_shots`, `build_sample_plan` (Task 6); `CostTracker` (Task 17).
- Produces: `build_pipeline() -> SequentialAgent` (the top-level `Shruti` agent — this is what gets deployed in Task 21), `GATE_TOOLS`, `PULSE_TOOLS` (lists of ADK `FunctionTool`), `class ProvenancePlugin(BasePlugin)`, `class CostGuardPlugin(BasePlugin)`, `class Stage(str, Enum)` + `next_stage(current: Stage) -> Stage` + `is_before(a: Stage, b: Stage) -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/agents/__init__.py
```

```python
# tests/agents/test_pipeline.py
from google.adk.agents import SequentialAgent, ParallelAgent
from shruti.agents.pipeline import build_pipeline


def test_build_pipeline_wires_stages_in_order():
    pipeline = build_pipeline()
    assert isinstance(pipeline, SequentialAgent)
    assert [a.name for a in pipeline.sub_agents] == \
        ["Gate", "Pulse", "Perceive", "Weave", "Glyph", "Atlas"]


def test_perceive_runs_slate_echo_point_in_parallel():
    pipeline = build_pipeline()
    perceive = next(a for a in pipeline.sub_agents if a.name == "Perceive")
    assert isinstance(perceive, ParallelAgent)
    assert [a.name for a in perceive.sub_agents] == ["Slate", "Echo", "Point"]
```

```python
# tests/agents/test_tools.py
from shruti.agents.tools import GATE_TOOLS, PULSE_TOOLS


def test_gate_tools_wraps_three_functions():
    assert len(GATE_TOOLS) == 3


def test_pulse_tools_wraps_two_functions():
    assert len(PULSE_TOOLS) == 2
```

```python
# tests/agents/test_state.py
import pytest
from shruti.agents.state import Stage, next_stage, is_before


def test_next_stage_advances_in_order():
    assert next_stage(Stage.ADMITTED) == Stage.SPINED
    assert next_stage(Stage.PERCEIVED) == Stage.WOVEN


def test_next_stage_raises_at_terminal_stage():
    with pytest.raises(ValueError):
        next_stage(Stage.SHELVED)


def test_is_before_orders_correctly():
    assert is_before(Stage.ADMITTED, Stage.SHELVED)
    assert not is_before(Stage.SHELVED, Stage.ADMITTED)
```

```python
# tests/agents/test_plugins.py
import pytest
from shruti.agents.plugins import ProvenancePlugin, CostGuardPlugin
from shruti.gemini.client import CostTracker


class FakeCallbackContext:
    def __init__(self, agent_name="Glyph", invocation_id="inv1"):
        self.agent_name = agent_name
        self.invocation_id = invocation_id


class FakeLlmResponse:
    def __init__(self, model_version="gemini-3.5-flash", id="resp1"):
        self.model_version = model_version
        self.id = id


@pytest.mark.asyncio
async def test_provenance_plugin_records_every_model_call():
    recorded = []

    async def recorder(**kwargs):
        recorded.append(kwargs)

    plugin = ProvenancePlugin(recorder)
    await plugin.after_model_callback(callback_context=FakeCallbackContext(),
                                       llm_response=FakeLlmResponse())
    assert recorded[0]["stage"] == "Glyph"
    assert recorded[0]["model"] == "gemini-3.5-flash"


@pytest.mark.asyncio
async def test_cost_guard_allows_calls_under_budget():
    tracker = CostTracker()
    tracker.record("inv1", 0.50)
    plugin = CostGuardPlugin(tracker, max_cost_per_recording_usd=2.00)
    result = await plugin.before_model_callback(callback_context=FakeCallbackContext(), llm_request=None)
    assert result is None


@pytest.mark.asyncio
async def test_cost_guard_blocks_calls_over_budget():
    tracker = CostTracker()
    tracker.record("inv1", 2.50)
    plugin = CostGuardPlugin(tracker, max_cost_per_recording_usd=2.00)
    result = await plugin.before_model_callback(callback_context=FakeCallbackContext(), llm_request=None)
    assert result is not None
    assert result.error == "cost_ceiling_exceeded"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/agents/ -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shruti.agents'`

- [ ] **Step 3: Write the implementation**

```python
# shruti/agents/__init__.py
```

```python
# shruti/agents/pipeline.py
from google.adk.agents import SequentialAgent, ParallelAgent, LlmAgent
from google.adk.models import Gemini
from shruti.config import Models


def build_pipeline() -> SequentialAgent:
    router = Models().router
    reasoner = Models().reasoner

    gate = LlmAgent(name="Gate", model=Gemini(model=router),
                     instruction="Admit the recording: probe, normalize, fingerprint, "
                                 "classify the writing surface.",
                     output_key="recording")
    pulse = LlmAgent(name="Pulse", model=Gemini(model=router),
                      instruction="Build the temporal spine: shots, ink curve, erase "
                                  "events, adaptive sample plan.",
                      output_key="timeline")
    slate = LlmAgent(name="Slate", model=Gemini(model=router),
                      instruction="Recover clean board states for each interval. "
                                  "Degrade gracefully and report unrecoverable states.",
                      output_key="board_states")
    echo = LlmAgent(name="Echo", model=Gemini(model=reasoner),
                     instruction="Transcribe the audio faithfully, preserving code-mixing.",
                     output_key="utterances")
    point = LlmAgent(name="Point", model=Gemini(model=reasoner),
                      instruction="Resolve deictic references at gesture moments.",
                      output_key="deixis")
    perceive = ParallelAgent(name="Perceive", sub_agents=[slate, echo, point])
    weave = LlmAgent(name="Weave", model=Gemini(model=reasoner),
                      instruction="Fuse timeline, speech, and board signals into Beats.",
                      output_key="beats")
    glyph = LlmAgent(name="Glyph", model=Gemini(model=reasoner),
                      instruction="Read each board state into structured layout regions. "
                                  "Never guess occluded content.",
                      output_key="board_content")
    atlas = LlmAgent(name="Atlas", model=Gemini(model=reasoner),
                      instruction="Mine concepts, relations, and misconceptions.",
                      output_key="concept_graph")

    return SequentialAgent(name="Shruti",
                            sub_agents=[gate, pulse, perceive, weave, glyph, atlas])
```

```python
# shruti/agents/tools.py
from google.adk.tools import FunctionTool
from shruti.stages.gate.probe import probe_video, fingerprint
from shruti.stages.gate.normalize import normalize_video
from shruti.stages.pulse.shots import detect_shots
from shruti.stages.pulse.plan import build_sample_plan

GATE_TOOLS = [FunctionTool(f) for f in (probe_video, normalize_video, fingerprint)]
PULSE_TOOLS = [FunctionTool(f) for f in (detect_shots, build_sample_plan)]
```

```python
# shruti/agents/state.py
from enum import Enum

_ORDER = ["ADMITTED", "SPINED", "PERCEIVED", "WOVEN", "READ", "MAPPED", "SHELVED"]


class Stage(str, Enum):
    ADMITTED = "ADMITTED"
    SPINED = "SPINED"
    PERCEIVED = "PERCEIVED"
    WOVEN = "WOVEN"
    READ = "READ"
    MAPPED = "MAPPED"
    SHELVED = "SHELVED"


def next_stage(current: Stage) -> Stage:
    idx = _ORDER.index(current.value)
    if idx == len(_ORDER) - 1:
        raise ValueError(f"{current} is the terminal stage")
    return Stage(_ORDER[idx + 1])


def is_before(a: Stage, b: Stage) -> bool:
    return _ORDER.index(a.value) < _ORDER.index(b.value)
```

```python
# shruti/agents/plugins.py
from google.adk.plugins import BasePlugin
from shruti.config import Budget


class ProvenancePlugin(BasePlugin):
    """Every LLM call that produces a semantic object records its inputs —
    reproducibility is not optional in an education knowledge base."""

    def __init__(self, recorder):
        super().__init__()
        self._recorder = recorder

    async def after_model_callback(self, *, callback_context, llm_response):
        await self._recorder(
            stage=callback_context.agent_name,
            model=getattr(llm_response, "model_version", None),
            output_ref=getattr(llm_response, "id", None),
        )
        return None


class CostGuardPlugin(BasePlugin):
    """Hard ceiling per recording — the budget is finite."""

    def __init__(self, cost_tracker, max_cost_per_recording_usd: float | None = None):
        super().__init__()
        self._cost_tracker = cost_tracker
        self._max_cost = max_cost_per_recording_usd or Budget().max_cost_per_recording_usd

    async def before_model_callback(self, *, callback_context, llm_request):
        spent = self._cost_tracker.total_for(callback_context.invocation_id)
        if spent > self._max_cost:
            from google.adk.models import LlmResponse
            return LlmResponse(error="cost_ceiling_exceeded")
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/agents/ -v`
Expected: PASS (9 tests). If `BasePlugin` or `LlmResponse` import paths differ from `google.adk.plugins`/`google.adk.models` in the installed `google-adk==2.7.1`, fix the import to match — the test behavior (not the import path) is the source of truth.

- [ ] **Step 5: Commit**

```bash
git add shruti/agents/ tests/agents/
git commit -m "feat: wire ADK SequentialAgent/ParallelAgent pipeline, plugins, and stage state machine"
```

---

## Task 19: Evals E1–E4, with E4 as the CI-failing provenance gate

**Files:**
- Create: `evals/__init__.py`, `e1_board_recall.py`, `e2_transcript_fidelity.py`, `e3_extraction_f1.py`, `e4_provenance_invariant.py`
- Test: `tests/evals/__init__.py`, `test_e1_board_recall.py`, `test_e2_transcript_fidelity.py`, `test_e3_extraction_f1.py`, `test_e4_provenance_invariant.py`

**Interfaces:**
- Consumes: `check_provenance_invariant` (Task 15), the `db_conn` fixture (Task 14, now at `tests/conftest.py`).
- Produces: `board_recovery_recall(predicted_mask, ground_truth_mask, iou_threshold=0.5) -> float`, `word_error_rate(hypothesis: str, reference: str) -> float`, `script_fidelity(hypothesis: str, reference: str) -> float`, `concept_f1(predicted: list[str], gold: list[str]) -> float`, `edge_precision(predicted: list[tuple], gold: list[tuple]) -> float`, `async def e4_check(conn) -> None` (raises `AssertionError` on any violation — this is the function CI calls).

- [ ] **Step 1: Write the failing tests**

```python
# tests/evals/__init__.py
```

```python
# tests/evals/test_e1_board_recall.py
import numpy as np
from evals.e1_board_recall import board_recovery_recall


def test_recall_is_one_for_identical_masks():
    mask = np.zeros((30, 30), dtype=np.uint8)
    mask[5:10, 5:10] = 1
    mask[20:25, 20:25] = 1
    assert board_recovery_recall(mask, mask) == 1.0


def test_recall_is_half_when_one_of_two_components_is_missing():
    gt = np.zeros((30, 30), dtype=np.uint8)
    gt[5:10, 5:10] = 1
    gt[20:25, 20:25] = 1
    predicted = np.zeros((30, 30), dtype=np.uint8)
    predicted[5:10, 5:10] = 1
    assert board_recovery_recall(predicted, gt) == 0.5
```

```python
# tests/evals/test_e2_transcript_fidelity.py
from evals.e2_transcript_fidelity import word_error_rate, script_fidelity


def test_word_error_rate_zero_for_identical_transcripts():
    assert word_error_rate("hello world", "hello world") == 0.0


def test_word_error_rate_counts_substitutions():
    assert word_error_rate("hello there", "hello world") == 0.5


def test_script_fidelity_penalizes_transliteration():
    reference = "अब हम iska derivative nikalenge"
    faithful = "अब हम iska derivative nikalenge"
    transliterated = "अब हम इसका डेरिवेटिव निकालेंगे"
    assert script_fidelity(faithful, reference) == 1.0
    assert script_fidelity(transliterated, reference) < 1.0
```

```python
# tests/evals/test_e3_extraction_f1.py
from evals.e3_extraction_f1 import concept_f1, edge_precision


def test_concept_f1_perfect_match():
    assert concept_f1(["a", "b"], ["a", "b"]) == 1.0


def test_concept_f1_partial_overlap():
    f1 = concept_f1(["a", "b", "c"], ["a", "b"])
    assert 0.7 < f1 < 0.9


def test_edge_precision_counts_only_correct_predictions():
    predicted = [("a", "b", "REQUIRES"), ("c", "d", "REQUIRES")]
    gold = [("a", "b", "REQUIRES")]
    assert edge_precision(predicted, gold) == 0.5
```

```python
# tests/evals/test_e4_provenance_invariant.py
import pytest
from shruti.contracts.recording import Recording, SurfaceKind
from shruti.contracts.beat import Beat
from shruti.contracts.atlas import Concept, BeatRef
from shruti.vault.reel import write_recording, write_beats
from shruti.vault.atlas_store import write_concepts
from evals.e4_provenance_invariant import e4_check


@pytest.mark.asyncio
async def test_e4_check_passes_when_every_concept_has_a_beat_ref(db_conn):
    rec = Recording(id="r_e4_1", source_uri="gs://x", duration_s=10.0, fps=30.0,
                     surface_kind=SurfaceKind.BLACKBOARD)
    await write_recording(db_conn, rec)
    beat = Beat(id="b_e4_1", recording_id=rec.id, idx=0, start_s=0.0, end_s=1.0,
                kind="explain", transcript="x")
    await write_beats(db_conn, [beat])
    concept = Concept(id="c_e4_1", canonical_name="ok concept",
                       taught_in=[BeatRef(beat_id=beat.id, relation="taught_in")])
    await write_concepts(db_conn, [concept])
    await e4_check(db_conn)  # must not raise


@pytest.mark.asyncio
async def test_e4_check_raises_on_orphan_concept(db_conn):
    await db_conn.execute(
        "INSERT INTO concept (id, canonical_name) VALUES ('c_e4_bad', 'orphan')"
    )
    with pytest.raises(AssertionError):
        await e4_check(db_conn)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/evals/ -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'evals'`

- [ ] **Step 3: Write the implementation**

```python
# evals/__init__.py
```

```python
# evals/e1_board_recall.py
import cv2
import numpy as np


def board_recovery_recall(predicted_mask: np.ndarray, ground_truth_mask: np.ndarray,
                           iou_threshold: float = 0.5) -> float:
    """AccessMath-style connected-component recall: fraction of ground-truth
    ink components that have a matching (IoU >= threshold) predicted component."""
    gt_n, gt_labels = cv2.connectedComponents(ground_truth_mask.astype(np.uint8))
    pred_n, pred_labels = cv2.connectedComponents(predicted_mask.astype(np.uint8))

    if gt_n <= 1:
        return 1.0

    matched = 0
    for gt_id in range(1, gt_n):
        gt_component = gt_labels == gt_id
        best_iou = 0.0
        for pred_id in range(1, pred_n):
            pred_component = pred_labels == pred_id
            intersection = np.logical_and(gt_component, pred_component).sum()
            union = np.logical_or(gt_component, pred_component).sum()
            if union > 0:
                best_iou = max(best_iou, intersection / union)
        if best_iou >= iou_threshold:
            matched += 1
    return matched / (gt_n - 1)
```

```python
# evals/e2_transcript_fidelity.py
import re

_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")


def word_error_rate(hypothesis: str, reference: str) -> float:
    hyp_words, ref_words = hypothesis.split(), reference.split()
    m, n = len(hyp_words), len(ref_words)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if hyp_words[i - 1] == ref_words[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    return dp[m][n] / max(1, n)


def _script_of(word: str) -> str:
    return "devanagari" if _DEVANAGARI_RE.search(word) else "latin"


def script_fidelity(hypothesis: str, reference: str) -> float:
    """Fraction of reference words whose script (Latin vs Devanagari) the
    hypothesis preserves at the same position — a transcript that
    transliterates everything into one script scores low here even if the
    words are individually 'correct'."""
    hyp_words, ref_words = hypothesis.split(), reference.split()
    if not ref_words:
        return 1.0
    matches = sum(1 for h, r in zip(hyp_words, ref_words) if _script_of(h) == _script_of(r))
    return matches / len(ref_words)
```

```python
# evals/e3_extraction_f1.py

def concept_f1(predicted: list[str], gold: list[str]) -> float:
    pred_set, gold_set = set(predicted), set(gold)
    if not pred_set and not gold_set:
        return 1.0
    tp = len(pred_set & gold_set)
    precision = tp / len(pred_set) if pred_set else 0.0
    recall = tp / len(gold_set) if gold_set else 0.0
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def edge_precision(predicted: list[tuple], gold: list[tuple]) -> float:
    if not predicted:
        return 1.0 if not gold else 0.0
    gold_set = set(gold)
    correct = sum(1 for e in predicted if e in gold_set)
    return correct / len(predicted)
```

```python
# evals/e4_provenance_invariant.py
from shruti.vault.atlas_store import check_provenance_invariant


async def e4_check(conn) -> None:
    """The correctness assertion, not a quality metric — this should fail the
    build. 100% of Concept/Edge/Misconception rows must resolve >=1 BeatRef."""
    violations = await check_provenance_invariant(conn)
    assert not violations, (
        f"Provenance invariant violated — {len(violations)} row(s) have no "
        f"BeatRef: {violations}"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/evals/ -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add evals/ tests/evals/
git commit -m "feat: implement E1-E4 evaluations, with E4 as the CI-failing provenance gate"
```

---

## Task 20: CLI and task runner

**Files:**
- Create: `shruti/cli.py`
- Modify: `justfile` (created empty-ish in Task 1; fill in real recipes now)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `apply_migrations`, `get_pool` (Task 3); `check_provenance_invariant` (Task 15).
- Produces: a `typer` app in `shruti/cli.py` exposing `migrate`, `cost` (stub reading `CostTracker`-style output), and `provenance-check` commands — the `justfile` recipes shell out to these.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
from typer.testing import CliRunner
from shruti.cli import app

runner = CliRunner()


def test_cli_exposes_migrate_and_provenance_check_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "migrate" in result.output
    assert "provenance-check" in result.output
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shruti.cli'`

- [ ] **Step 3: Write the implementation**

```python
# shruti/cli.py
import asyncio
import typer
from shruti.db import get_pool, apply_migrations
from shruti.vault.atlas_store import check_provenance_invariant

app = typer.Typer()


@app.command()
def migrate():
    """Apply all pending SQL migrations in infra/migrations/."""
    async def _run():
        pool = await get_pool()
        await apply_migrations(pool)
        await pool.close()
    asyncio.run(_run())
    typer.echo("migrations applied")


@app.command(name="provenance-check")
def provenance_check():
    """Run the E4 provenance invariant against the live database and exit
    non-zero if any Concept/Edge/Misconception row lacks a BeatRef."""
    async def _run():
        pool = await get_pool()
        violations = await check_provenance_invariant(pool)
        await pool.close()
        return violations
    violations = asyncio.run(_run())
    if violations:
        typer.echo(f"{len(violations)} violation(s): {violations}")
        raise typer.Exit(code=1)
    typer.echo("provenance invariant holds")


if __name__ == "__main__":
    app()
```

```makefile
# justfile
up:
    docker compose -f docker/compose.yaml up -d

migrate:
    uv run shruti migrate

provenance-check:
    uv run shruti provenance-check

test:
    uv run pytest -v

test-fast:
    uv run pytest -v -m "not asyncio"

timeline recording_id:
    echo "SELECT * FROM v_timeline WHERE recording_id='{{recording_id}}'" | uv run python -c "import sys; print(sys.stdin.read())"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add shruti/cli.py justfile tests/test_cli.py
git commit -m "feat: add CLI (migrate, provenance-check) and justfile task runner"
```

---

## Task 21: Platform alignment — deploy to Agent Runtime, confirm Agent Registry, add OpenTelemetry

This is D4 + D5 + D6 from `shruti_platform_alignment.md`. There is no new pipeline logic in this task — it is entirely configuration and one verification script, because that's the point: the highest-leverage platform-alignment change is a config flip, not a rewrite.

**Files:**
- Create: `shruti/agent.py`
- Create: `docker/Dockerfile.conductor`
- Create: `opentelemetry.env`
- Create: `scripts/verify_platform_deployment.py`
- Modify: `pyproject.toml` (add OTel dependencies)

**Interfaces:**
- Consumes: `build_pipeline()` (Task 18).
- Produces: `shruti/agent.py` exposing module-level `root_agent = build_pipeline()` — this is the file `adk web`, `agents-cli`, and `agent_engines.AdkApp(agent=...)` all discover by ADK's standard convention (an `agent.py` exposing `root_agent`). No earlier task created this entrypoint file; without it, `agents-cli deploy` has nothing to package. A deployed Agent Runtime instance (external to the repo — the "test" for the deploy steps is the live verification script below, not a pytest unit test, since it depends on real GCP infrastructure).

- [ ] **Step 0: Write the ADK entrypoint module**

```python
# shruti/agent.py
from shruti.agents.pipeline import build_pipeline

root_agent = build_pipeline()
```

Run: `uv run pytest -k "test_build_pipeline" -v` (re-runs Task 18's existing tests as a smoke check that `build_pipeline()` still constructs cleanly before wrapping it here)
Expected: PASS — this step adds no new test of its own; it exposes an existing, already-tested object under the name ADK's tooling expects.

- [ ] **Step 1: Add the OpenTelemetry dependencies**

```bash
uv add 'opentelemetry-instrumentation-google-genai>=0.4b0' \
       'opentelemetry-instrumentation-sqlite3' \
       'opentelemetry-exporter-gcp-logging' \
       'opentelemetry-exporter-otlp-proto-grpc' \
       'opentelemetry-instrumentation-vertexai>=2.0b0'
```

- [ ] **Step 2: Write `opentelemetry.env`**

```
OTEL_SERVICE_NAME=shruti
OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED=true
OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=true
```

- [ ] **Step 3: Write the deploy Dockerfile**

```dockerfile
# docker/Dockerfile.conductor
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen
COPY shruti/ ./shruti/
COPY infra/ ./infra/
ENV OTEL_SERVICE_NAME=shruti
ENTRYPOINT ["uv", "run", "--env-file", "opentelemetry.env", "adk", "web", "--otel_to_cloud"]
```

- [ ] **Step 4: Flip the deployment target (D4) and deploy**

```bash
agents-cli scaffold enhance --deployment-target agent_engine
agents-cli deploy
```

Record the printed `AGENT_ENGINE_ID` — later steps and the tutor's future `AgentRegistry` lookup both need it.

- [ ] **Step 5: Write the verification script**

```python
# scripts/verify_platform_deployment.py
"""Not a pytest test — this hits real GCP infrastructure. Run manually
after `agents-cli deploy` to confirm D4/D5/D6 actually landed."""
import os
import sys
import vertexai

PROJECT = os.environ["GOOGLE_CLOUD_PROJECT"]
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
AGENT_ENGINE_ID = os.environ["AGENT_ENGINE_ID"]


def main():
    client = vertexai.Client(project=PROJECT, location=LOCATION)
    agent = client.agent_engines.get(AGENT_ENGINE_ID)
    print(f"[D4] Agent Runtime resource state: {agent.state}")
    assert agent.state == "ACTIVE", "agent is not deployed to Agent Runtime"

    # D5: Agent Registry auto-registration.
    import subprocess
    result = subprocess.run(
        ["gcloud", "agent-registry", "agents", "list",
         f"--project={PROJECT}", f"--location={LOCATION}"],
        capture_output=True, text=True,
    )
    print(f"[D5] Agent Registry listing:\n{result.stdout}")
    assert AGENT_ENGINE_ID in result.stdout, "agent did not auto-register in Agent Registry"

    print("[D6] Reminder: open Cloud Trace / the platform's Unified Trace Viewer "
          "and confirm spans are arriving for a real invocation — this script "
          "cannot assert that without making a live, billed call.")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Run the verification script against the real deployment**

Run: `GOOGLE_CLOUD_PROJECT=... AGENT_ENGINE_ID=... uv run python scripts/verify_platform_deployment.py`
Expected: both asserted checks pass; manually confirm the D6 trace reminder by triggering one real pipeline run and checking the platform's Observability tab for a populated trace DAG.

- [ ] **Step 7: Commit**

```bash
git add shruti/agent.py docker/Dockerfile.conductor opentelemetry.env scripts/verify_platform_deployment.py pyproject.toml uv.lock
git commit -m "feat: deploy to Agent Runtime, verify Agent Registry auto-registration, add OTel instrumentation"
```

---

## Task 22 (stretch — do only if Task 1–21 are done with time remaining): Custom Code Metrics for the Evaluation Service

This is D7. Skip it under real time pressure — E1–E4 already run and gate CI without it; this only adds a second, platform-native rendering of the same checks.

**Files:**
- Create: `shruti/optimize/__init__.py`, `metrics.py`
- Test: `tests/optimize/test_metrics.py`

**Interfaces:**
- Consumes: `board_recovery_recall`, `word_error_rate`, `concept_f1` (Task 19).
- Produces: `build_custom_metrics() -> list` (a list of `types.CodeExecutionMetric`-shaped configs, one per E1–E3 check — E4 stays a CI gate, not a scored metric, since it's a pass/fail invariant rather than a quality score).

- [ ] **Step 1: Write the failing test**

```python
# tests/optimize/test_metrics.py
from shruti.optimize.metrics import build_custom_metrics


def test_build_custom_metrics_returns_one_metric_per_eval():
    metrics = build_custom_metrics()
    names = {m["name"] for m in metrics}
    assert names == {"board_recovery_recall", "transcript_word_error_rate", "concept_extraction_f1"}
    for m in metrics:
        assert "def evaluate(instance: dict)" in m["custom_function"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/optimize/test_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shruti.optimize'`

- [ ] **Step 3: Write the implementation**

```python
# shruti/optimize/__init__.py
```

```python
# shruti/optimize/metrics.py

_BOARD_RECALL_FN = '''
def evaluate(instance: dict) -> float:
    from evals.e1_board_recall import board_recovery_recall
    import numpy as np
    predicted = np.array(instance["predicted_mask"])
    ground_truth = np.array(instance["ground_truth_mask"])
    return board_recovery_recall(predicted, ground_truth)
'''

_WER_FN = '''
def evaluate(instance: dict) -> float:
    from evals.e2_transcript_fidelity import word_error_rate
    return 1.0 - word_error_rate(instance["hypothesis"], instance["reference"])
'''

_CONCEPT_F1_FN = '''
def evaluate(instance: dict) -> float:
    from evals.e3_extraction_f1 import concept_f1
    return concept_f1(instance["predicted_concepts"], instance["gold_concepts"])
'''


def build_custom_metrics() -> list[dict]:
    return [
        {"name": "board_recovery_recall", "custom_function": _BOARD_RECALL_FN},
        {"name": "transcript_word_error_rate", "custom_function": _WER_FN},
        {"name": "concept_extraction_f1", "custom_function": _CONCEPT_F1_FN},
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/optimize/test_metrics.py -v`
Expected: PASS

- [ ] **Step 5: Register the metrics with the Evaluation Service and commit**

```python
# one-off, run manually against a real client — not part of the test suite
from google import genai
from google.genai import types
from shruti.optimize.metrics import build_custom_metrics

client = genai.Client(vertexai=True)
for m in build_custom_metrics():
    client.evals.metrics.create(types.CodeExecutionMetric(**m))
```

```bash
git add shruti/optimize/ tests/optimize/
git commit -m "feat: expose E1-E3 as Custom Code Metrics in the platform Evaluation Service"
```

---

## Self-review notes

- **Spec coverage**: D1–D3 (Gemini-native extraction, three-layer storage, staged CV) are implemented across Tasks 4–15. D4–D6 (deployment target, Agent Registry, observability correction) are Task 21. D7 (Custom Code Metrics) is Task 22, explicitly marked stretch. D8's rejected components (RAG Engine, Vector Search 1.0/2.0, Agent Garden, Managed Agents API, Agent Studio, Agent Gateway, governance/optimize extras) correctly have **no task** — that's the point of D8. D9 is forward-looking for the not-yet-built tutor and correctly has no task here.
- **Placeholder scan**: no task contains "TBD," "add error handling," or an unshown test — every step has real, runnable code.
- **Type consistency checked**: `Beat.kind`, `Region.kind`, `Edge.edge_type`, `Deixis.kind` use the same `Literal` string values everywhere they're constructed or read (Tasks 2, 9, 11, 12, 13, 14). `conn` is used consistently to mean "either `asyncpg.Pool` or `asyncpg.Connection`" from Task 14 onward — no task introduces a different parameter name for the same thing.
- **Known open risk, called out rather than silently assumed**: Task 18's `from google.adk.plugins import BasePlugin` and `from google.adk.models import LlmResponse` import paths are the plan's best inference from the research in `wiki/adk-and-a2ui.md`, which confirmed the class and its callback signatures but not their exact module path. If the installed `google-adk==2.7.1` uses a different path, Task 18 Step 4 says explicitly: fix the import, the test behavior is the source of truth — this is flagged so whoever executes the task isn't surprised by it.

---

**Cut order under real time pressure** (mirrors `shruti_platform_alignment.md` §5): if hours run out, cut in this order — Task 22 (Custom Code Metrics) → Task 10 (POINT/deixis) → misconception mining depth in Task 13 → Task 21 downgrades to demoing on plain `cloud_run` with the platform alignment narrated rather than deployed. **Never cut**: Task 5 (ink curve/erase detection), Task 8 (board compositing with the `unfilled` mask), Task 9's code-mix transcript prompt, Task 19's E4 provenance gate.

