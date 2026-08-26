# Nityam Tutor Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the v1.0 Nityam tutor — `VoiceAgent → TutorAgent → ArtifactAgent`, backed by one shared SQLite memory layer — as a working, incrementally-tested ADK project at `sub_modules/tutor/`.

**Architecture:** Three ADK `LlmAgent`s wired with the framework's `mode='single_turn'` sub-agent mechanism (verified against installed `google-adk==2.7.1` source, not `AgentTool` directly — see `architecture.md` §2). One SQLite-backed memory store exposes the same tool functions to every agent. `TutorAgent` and `ArtifactAgent` are built and tested first via text (`run_async`); `VoiceAgent` is added last, on top, once the reasoning layer is proven.

**Tech Stack:** Python ≥3.11,<3.14, `google-adk[gcp,otel-gcp]>=2.6.0,<3.0.0` (installed: 2.7.1), Pydantic v2, SQLite (stdlib `sqlite3`), `google-genai`, `agents-cli` (google-agents-cli v1.4.1), pytest + pytest-asyncio.

**Spec:**
- `project_documentation/memory_nityam_architecture/architecture.md`
- `project_documentation/memory_nityam_architecture/memory_layer.md`
- `project_documentation/memory_nityam_architecture/deferred.md` (what's deliberately NOT built here)

## Global Constraints

- ADK version pinned: `google-adk[gcp,otel-gcp]>=2.6.0,<3.0.0`, installed `2.7.1` — matches the version this plan's ADK source citations were verified against.
- Model ids live only in `sub_modules/tutor/app/config.py` — never inlined at a call site. Verified live on 2026-08-26: `LIVE_MODEL = "gemini-3.1-flash-live-preview"`, `REASONING_MODEL = "gemini-3.7-flash"` (architecture.md §4).
- Auth is Gemini API key (`GEMINI_API_KEY`), matching `sub_modules/shruti`'s existing pattern — not Vertex AI. No `gcloud`/ADC in this environment.
- Long-term memory (`dpm_profile`, `teaching_memory`) is **never** written mid-session — the only write path is `close_session` (memory_layer.md §3–§4). Tools exposed to `TutorAgent`/`ArtifactAgent` are read-only against long-term memory.
- Every `Weakness`, `SelfReflection`, and `OpenDoubt` record requires at least one `"session_id#turn"` evidence reference — enforced by the Pydantic schema itself, not just convention (memory_layer.md §2).
- Sub-agent delegation uses `sub_agents=[child]` with `mode="single_turn"` declared **on the child**, never raw `AgentTool(child)` — the installed ADK's own source discourages direct `AgentTool` use (architecture.md §2).
- Demo subject is projectile motion — grounding content is seeded from the real, already-ingested `sub_modules/shruti/vault/wiki/*.md` files, not invented.
- **Never assert on LLM response content in pytest.** Behavioral verification of an agent's actual output happens via `agents-cli run` / `agents-cli eval`, not pytest (`google-agents-cli-workflow` rule). pytest in this plan checks structure, config, and deterministic logic only.

## ⚠️ Known blocker, discovered during this plan's own research

The `GEMINI_API_KEY` currently configured (shared with `sub_modules/shruti`) returned `429 RESOURCE_EXHAUSTED — prepayment credits are depleted` on a real `generate_content` call during scaffolding verification. **Listing models still works** (used to verify the model ids above); **actual generation calls do not**, right now. Every task below is still fully buildable and its structural/deterministic tests are runnable today — each task's final "live verification" step is what's blocked, and is labeled as such. Before running any live-verification step: add credits at https://ai.studio/projects, or swap in a different working key in `sub_modules/tutor/.env`.

---

### Task 1: Config module — verified model ids

**Files:**
- Create: `sub_modules/tutor/app/config.py`
- Test: `sub_modules/tutor/tests/unit/test_config.py`

**Interfaces:**
- Produces: `config.LIVE_MODEL: str`, `config.REASONING_MODEL: str` — every later task imports these, never a literal model string.

- [ ] **Step 1: Write the failing test**

```python
# sub_modules/tutor/tests/unit/test_config.py
from app import config


def test_live_model_is_the_verified_live_preview_id():
    assert config.LIVE_MODEL == "gemini-3.1-flash-live-preview"


def test_reasoning_model_is_the_verified_flash_id():
    assert config.REASONING_MODEL == "gemini-3.7-flash"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sub_modules/tutor && uv run pytest tests/unit/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.config'`

- [ ] **Step 3: Write the implementation**

```python
# sub_modules/tutor/app/config.py
"""Centralized model configuration.

Model ids drift fast — this project has already shipped two silent
regressions from a stale/hallucinated id (see
project_documentation/memory_nityam_architecture/README.md's "Resolved via
LLM-as-judge review" section). Both ids below were verified live against
`client.models.list()` on 2026-08-26, not recalled from training data.
Re-run that listing before trusting them again if much time has passed:

    uv run --with google-genai python -c "
    from google import genai
    client = genai.Client()
    for m in client.models.list():
        print(m.name)
    "
"""

LIVE_MODEL = "gemini-3.1-flash-live-preview"
"""VoiceAgent — native audio, bidirectional (run_live) streaming."""

REASONING_MODEL = "gemini-3.7-flash"
"""TutorAgent and ArtifactAgent — text/tool reasoning, run via run_async
through the mode='single_turn' delegation path."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd sub_modules/tutor && uv run pytest tests/unit/test_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
cd sub_modules/tutor
git add app/config.py tests/unit/test_config.py
git commit -m "feat: add centralized, verified model-id config"
```

---

### Task 2: Memory schemas — the JSON Schemas as Pydantic models

**Files:**
- Create: `sub_modules/tutor/app/memory/__init__.py`
- Create: `sub_modules/tutor/app/memory/schemas.py`
- Test: `sub_modules/tutor/tests/unit/memory/test_schemas.py`
- Test: `sub_modules/tutor/tests/unit/memory/__init__.py` (empty, makes the dir a package for pytest rootdir resolution)

**Interfaces:**
- Consumes: nothing (foundational).
- Produces: `GroundingChunk`, `DPMProfile` (+ `Persona`, `Weakness`, `SelfReflection`), `TeachingMemory` (+ `CoveredConcept`, `OpenDoubt`, `TeachingStyle`), `SessionLog` (+ `Turn`) — all `pydantic.BaseModel` subclasses in `app/memory/schemas.py`. Every later task imports these exact class and field names; do not rename any of them without updating every task below.

- [ ] **Step 1: Write the failing tests**

```python
# sub_modules/tutor/tests/unit/memory/__init__.py
```

```python
# sub_modules/tutor/tests/unit/memory/test_schemas.py
import pytest
from pydantic import ValidationError

from app.memory.schemas import (
    CoveredConcept,
    DPMProfile,
    GroundingChunk,
    OpenDoubt,
    Persona,
    SelfReflection,
    SessionLog,
    TeachingMemory,
    TeachingStyle,
    Turn,
    Weakness,
)


def test_grounding_chunk_valid():
    chunk = GroundingChunk(
        chunk_id="horizontal_range_0340",
        source_type="lecture",
        source_ref="shruti:d_jnekwca6i_4c5411d0",
        location="3:40",
        concept_ids=["projectile.horizontal_range"],
        text="The total horizontal distance traveled by a projectile...",
    )
    assert chunk.source_type == "lecture"


def test_grounding_chunk_requires_at_least_one_concept_id():
    with pytest.raises(ValidationError):
        GroundingChunk(
            chunk_id="x", source_type="book", source_ref="book:ch1",
            concept_ids=[], text="...",
        )


def test_grounding_chunk_rejects_unknown_source_type():
    with pytest.raises(ValidationError):
        GroundingChunk(
            chunk_id="x", source_type="video", source_ref="x",
            concept_ids=["a"], text="...",
        )


def test_weakness_requires_evidence():
    with pytest.raises(ValidationError):
        Weakness(mastery="partial", strength="weak", evidence=[])


def test_dpm_profile_valid_with_nested_records():
    profile = DPMProfile(
        student_id="demo_student",
        persona=Persona(preferred_pace="moderate", language_mix="hi-en", interests=["cricket"]),
        weaknesses={
            "projectile.horizontal_range": Weakness(
                mastery="partial", strength="weak", evidence=["s1#4"],
            )
        },
        self_reflection=[
            SelfReflection(note="responds well to area models", evidence=["s1#6"])
        ],
    )
    assert profile.weaknesses["projectile.horizontal_range"].mastery == "partial"
    assert profile.self_reflection[0].status == "active"


def test_dpm_profile_defaults_are_empty_not_missing():
    profile = DPMProfile(student_id="demo_student")
    assert profile.weaknesses == {}
    assert profile.self_reflection == []


def test_open_doubt_requires_evidence():
    with pytest.raises(ValidationError):
        OpenDoubt(
            concept_id="projectile.horizontal_range",
            doubt="thinks range formula uses u instead of u*cos(theta)",
            correct_understanding="R = u^2 sin(2 theta) / g",
            evidence=[],
        )


def test_teaching_memory_valid():
    memory = TeachingMemory(
        student_id="demo_student",
        syllabus=["projectile.horizontal_range", "projectile.maximum_height"],
        covered={
            "projectile.horizontal_range": CoveredConcept(
                elements_used=["worked-example"], taught_at=["s1#4"], status="in_progress",
            )
        },
        open_doubts=[
            OpenDoubt(
                concept_id="projectile.horizontal_range",
                doubt="uses u instead of u*cos(theta)",
                correct_understanding="R = u^2 sin(2 theta) / g",
                evidence=["s1#4"],
            )
        ],
        teaching_style=TeachingStyle(current_mode="socratic"),
    )
    assert memory.open_doubts[0].status == "active"


def test_teaching_memory_defaults():
    memory = TeachingMemory(student_id="demo_student")
    assert memory.covered == {}
    assert memory.teaching_style.current_mode == "direct"


def test_session_log_valid():
    from datetime import datetime, timezone

    log = SessionLog(
        session_id="s1",
        student_id="demo_student",
        started_at=datetime.now(timezone.utc),
        turns=[
            Turn(turn=1, role="student", text="why does range peak at 45 degrees?"),
            Turn(turn=2, role="tutor", text="what happens to each component as angle increases?", concept_id="projectile.horizontal_range"),
        ],
    )
    assert log.turns[0].turn == 1
    assert log.turns[1].concept_id == "projectile.horizontal_range"


def test_turn_requires_positive_turn_number():
    with pytest.raises(ValidationError):
        Turn(turn=0, role="student", text="x")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd sub_modules/tutor && uv run pytest tests/unit/memory/test_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.memory'`

- [ ] **Step 3: Write the implementation**

```python
# sub_modules/tutor/app/memory/__init__.py
```

```python
# sub_modules/tutor/app/memory/schemas.py
"""Pydantic mirrors of the JSON Schemas in
project_documentation/memory_nityam_architecture/memory_layer.md §2.

These ARE the contract — every read/write against the memory store validates
against these classes, this isn't documentation of a separate format.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class GroundingChunk(BaseModel):
    """One retrievable, citable unit of static knowledge. Never written by the
    tutor — only by Shruti ingestion or book ingestion."""

    chunk_id: str
    source_type: Literal["lecture", "book"]
    source_ref: str
    location: Optional[str] = None
    concept_ids: list[str] = Field(min_length=1)
    text: str


class Weakness(BaseModel):
    mastery: Literal["unknown", "misconceived", "partial", "known", "durable"]
    strength: Literal["weak", "strong"]
    evidence: list[str] = Field(min_length=1)
    last_updated: Optional[datetime] = None


class SelfReflection(BaseModel):
    """Tutor-authored pedagogical notes about this student — DeepTutor's D_r."""

    note: str
    helpful_count: int = 0
    harmful_count: int = 0
    evidence: list[str] = Field(min_length=1)
    status: Literal["active", "superseded"] = "active"
    superseded_by: Optional[str] = None


class Persona(BaseModel):
    preferred_pace: Optional[Literal["fast", "moderate", "deliberate"]] = None
    language_mix: Optional[str] = None
    interests: list[str] = Field(default_factory=list)


class DPMProfile(BaseModel):
    """Persona-level view: who am I teaching. Coarse per-concept mastery.
    Updated only via validated operations at session close — never rewritten
    wholesale (memory_layer.md §2.2, §4)."""

    student_id: str
    persona: Persona = Field(default_factory=Persona)
    weaknesses: dict[str, Weakness] = Field(default_factory=dict)
    self_reflection: list[SelfReflection] = Field(default_factory=list)


class CoveredConcept(BaseModel):
    elements_used: list[str] = Field(default_factory=list)
    taught_at: list[str] = Field(default_factory=list)
    status: Literal["in_progress", "covered"] = "in_progress"


class OpenDoubt(BaseModel):
    """The detailed record DPMProfile.weaknesses only flags a summary of."""

    concept_id: str
    doubt: str
    correct_understanding: str
    status: Literal["active", "remediating", "resolved"] = "active"
    evidence: list[str] = Field(min_length=1)


class TeachingStyle(BaseModel):
    current_mode: Literal["socratic", "worked-example", "guided-practice", "direct"] = "direct"
    notes: list[str] = Field(default_factory=list)


class TeachingMemory(BaseModel):
    """Operational view: what's the state of teaching them, right now
    (memory_layer.md §2.3)."""

    student_id: str
    syllabus: list[str] = Field(default_factory=list)
    covered: dict[str, CoveredConcept] = Field(default_factory=dict)
    open_doubts: list[OpenDoubt] = Field(default_factory=list)
    teaching_style: TeachingStyle = Field(default_factory=TeachingStyle)


class Turn(BaseModel):
    turn: int = Field(ge=1)
    role: Literal["student", "tutor"]
    text: str
    concept_id: Optional[str] = None
    artifact_id: Optional[str] = None


class SessionLog(BaseModel):
    """Episodic tier. Every DPM/TeachingMemory evidence pointer
    ('session_id#turn') resolves against a turn here (memory_layer.md §2.4)."""

    session_id: str
    student_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    turns: list[Turn] = Field(default_factory=list)
    summary: str = ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd sub_modules/tutor && uv run pytest tests/unit/memory/test_schemas.py -v`
Expected: PASS (13 passed)

- [ ] **Step 5: Commit**

```bash
cd sub_modules/tutor
git add app/memory/__init__.py app/memory/schemas.py tests/unit/memory/
git commit -m "feat: add Pydantic schemas for the SMRITI memory layer"
```

---

### Task 3: Memory store — SQLite persistence

**Files:**
- Create: `sub_modules/tutor/app/memory/store.py`
- Test: `sub_modules/tutor/tests/unit/memory/test_store.py`

**Interfaces:**
- Consumes: `GroundingChunk`, `DPMProfile`, `TeachingMemory`, `SessionLog` from Task 2's `app/memory/schemas.py`.
- Produces: `connect(db_path=DB_PATH) -> sqlite3.Connection`, `put_grounding_chunk(conn, chunk)`, `search_grounding(conn, concept_ids, limit=5) -> list[GroundingChunk]`, `get_dpm(conn, student_id) -> DPMProfile | None`, `put_dpm(conn, profile)`, `get_teaching_memory(conn, student_id) -> TeachingMemory | None`, `put_teaching_memory(conn, memory)`, `put_session_log(conn, log)`, `get_session_log(conn, session_id) -> SessionLog | None`. Every later task that touches storage calls these exact names — do not rename.

- [ ] **Step 1: Write the failing tests**

```python
# sub_modules/tutor/tests/unit/memory/test_store.py
from datetime import datetime, timezone

import pytest

from app.memory import store
from app.memory.schemas import DPMProfile, GroundingChunk, SessionLog, TeachingMemory, Turn, Weakness


@pytest.fixture
def conn():
    c = store.connect(":memory:")
    yield c
    c.close()


def test_put_and_search_grounding_chunk(conn):
    chunk = GroundingChunk(
        chunk_id="horizontal_range_0340",
        source_type="lecture",
        source_ref="shruti:d_jnekwca6i_4c5411d0",
        location="3:40",
        concept_ids=["projectile.horizontal_range"],
        text="The total horizontal distance traveled by a projectile...",
    )
    store.put_grounding_chunk(conn, chunk)

    results = store.search_grounding(conn, ["projectile.horizontal_range"])
    assert len(results) == 1
    assert results[0].chunk_id == "horizontal_range_0340"
    assert results[0].text.startswith("The total horizontal distance")


def test_search_grounding_returns_nothing_for_unknown_concept(conn):
    assert store.search_grounding(conn, ["nonexistent.concept"]) == []


def test_search_grounding_respects_limit(conn):
    for i in range(3):
        store.put_grounding_chunk(conn, GroundingChunk(
            chunk_id=f"c{i}", source_type="lecture", source_ref="shruti:x",
            concept_ids=["projectile.range"], text=f"chunk {i}",
        ))
    assert len(store.search_grounding(conn, ["projectile.range"], limit=2)) == 2


def test_dpm_round_trip(conn):
    assert store.get_dpm(conn, "demo_student") is None

    profile = DPMProfile(
        student_id="demo_student",
        weaknesses={"projectile.range": Weakness(mastery="partial", strength="weak", evidence=["s1#1"])},
    )
    store.put_dpm(conn, profile)

    loaded = store.get_dpm(conn, "demo_student")
    assert loaded is not None
    assert loaded.weaknesses["projectile.range"].mastery == "partial"


def test_dpm_put_overwrites_by_student_id(conn):
    store.put_dpm(conn, DPMProfile(student_id="demo_student"))
    store.put_dpm(conn, DPMProfile(student_id="demo_student", weaknesses={
        "projectile.range": Weakness(mastery="known", strength="strong", evidence=["s2#1"])
    }))
    loaded = store.get_dpm(conn, "demo_student")
    assert loaded.weaknesses["projectile.range"].mastery == "known"


def test_teaching_memory_round_trip(conn):
    assert store.get_teaching_memory(conn, "demo_student") is None

    memory = TeachingMemory(student_id="demo_student", syllabus=["projectile.range"])
    store.put_teaching_memory(conn, memory)

    loaded = store.get_teaching_memory(conn, "demo_student")
    assert loaded.syllabus == ["projectile.range"]


def test_session_log_round_trip(conn):
    log = SessionLog(
        session_id="s1",
        student_id="demo_student",
        started_at=datetime.now(timezone.utc),
        turns=[Turn(turn=1, role="student", text="hi")],
    )
    store.put_session_log(conn, log)

    loaded = store.get_session_log(conn, "s1")
    assert loaded is not None
    assert loaded.turns[0].text == "hi"


def test_get_session_log_missing_returns_none(conn):
    assert store.get_session_log(conn, "nonexistent") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd sub_modules/tutor && uv run pytest tests/unit/memory/test_store.py -v`
Expected: FAIL with `AttributeError: module 'app.memory.store' has no attribute 'connect'` (or `ModuleNotFoundError`)

- [ ] **Step 3: Write the implementation**

```python
# sub_modules/tutor/app/memory/store.py
"""One shared SQLite backing store for the memory layer — the same tool
functions in app/memory/tools.py call these, so TutorAgent and ArtifactAgent
read through one physical store, not separate copies (memory_layer.md §3, §5).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from app.memory.schemas import DPMProfile, GroundingChunk, SessionLog, TeachingMemory

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "memory.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS grounding_chunk (
    chunk_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS grounding_chunk_concept (
    concept_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL REFERENCES grounding_chunk(chunk_id),
    PRIMARY KEY (concept_id, chunk_id)
);
CREATE TABLE IF NOT EXISTS dpm_profile (
    student_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS teaching_memory (
    student_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS session_log (
    session_id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_session_log_student ON session_log(student_id);
"""


def connect(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    return conn


def put_grounding_chunk(conn: sqlite3.Connection, chunk: GroundingChunk) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO grounding_chunk (chunk_id, payload) VALUES (?, ?)",
        (chunk.chunk_id, chunk.model_dump_json()),
    )
    conn.execute("DELETE FROM grounding_chunk_concept WHERE chunk_id = ?", (chunk.chunk_id,))
    conn.executemany(
        "INSERT INTO grounding_chunk_concept (concept_id, chunk_id) VALUES (?, ?)",
        [(cid, chunk.chunk_id) for cid in chunk.concept_ids],
    )
    conn.commit()


def search_grounding(conn: sqlite3.Connection, concept_ids: list[str], limit: int = 5) -> list[GroundingChunk]:
    if not concept_ids:
        return []
    placeholders = ",".join("?" * len(concept_ids))
    rows = conn.execute(
        f"""
        SELECT DISTINCT gc.payload FROM grounding_chunk gc
        JOIN grounding_chunk_concept gcc ON gcc.chunk_id = gc.chunk_id
        WHERE gcc.concept_id IN ({placeholders})
        LIMIT ?
        """,
        (*concept_ids, limit),
    ).fetchall()
    return [GroundingChunk.model_validate_json(r[0]) for r in rows]


def get_dpm(conn: sqlite3.Connection, student_id: str) -> DPMProfile | None:
    row = conn.execute(
        "SELECT payload FROM dpm_profile WHERE student_id = ?", (student_id,)
    ).fetchone()
    return DPMProfile.model_validate_json(row[0]) if row else None


def put_dpm(conn: sqlite3.Connection, profile: DPMProfile) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO dpm_profile (student_id, payload) VALUES (?, ?)",
        (profile.student_id, profile.model_dump_json()),
    )
    conn.commit()


def get_teaching_memory(conn: sqlite3.Connection, student_id: str) -> TeachingMemory | None:
    row = conn.execute(
        "SELECT payload FROM teaching_memory WHERE student_id = ?", (student_id,)
    ).fetchone()
    return TeachingMemory.model_validate_json(row[0]) if row else None


def put_teaching_memory(conn: sqlite3.Connection, memory: TeachingMemory) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO teaching_memory (student_id, payload) VALUES (?, ?)",
        (memory.student_id, memory.model_dump_json()),
    )
    conn.commit()


def put_session_log(conn: sqlite3.Connection, log: SessionLog) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO session_log (session_id, student_id, payload) VALUES (?, ?, ?)",
        (log.session_id, log.student_id, log.model_dump_json()),
    )
    conn.commit()


def get_session_log(conn: sqlite3.Connection, session_id: str) -> SessionLog | None:
    row = conn.execute(
        "SELECT payload FROM session_log WHERE session_id = ?", (session_id,)
    ).fetchone()
    return SessionLog.model_validate_json(row[0]) if row else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd sub_modules/tutor && uv run pytest tests/unit/memory/test_store.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
cd sub_modules/tutor
git add app/memory/store.py tests/unit/memory/test_store.py
git commit -m "feat: add SQLite-backed memory store"
```

---

### Task 4: Memory tools — the shared ADK tool catalog

**Files:**
- Create: `sub_modules/tutor/app/memory/tools.py`
- Test: `sub_modules/tutor/tests/unit/memory/test_tools.py`

**Interfaces:**
- Consumes: `app.memory.store` (Task 3), `app.memory.schemas` (Task 2).
- Produces: `search_grounding(concept_ids: list[str]) -> dict`, `get_dpm(tool_context) -> dict`, `get_teaching_memory(tool_context) -> dict`, `log_turn(text, role, concept_id, artifact_id, tool_context) -> dict`, `log_artifact_evidence(event, artifact_id, tool_context) -> dict`. Tasks 6 and 7 import these exact functions into their `tools=[...]` lists.

- [ ] **Step 1: Write the failing tests**

```python
# sub_modules/tutor/tests/unit/memory/test_tools.py
from unittest.mock import MagicMock

import pytest

from app.memory import store, tools
from app.memory.schemas import DPMProfile, GroundingChunk, TeachingMemory, Weakness


@pytest.fixture(autouse=True)
def isolated_store(monkeypatch):
    """Each test gets its own in-memory DB instead of the process-wide one."""
    conn = store.connect(":memory:")
    tools._conn.cache_clear()
    monkeypatch.setattr(tools, "_conn", lambda: conn)
    yield conn
    conn.close()


def make_tool_context(state: dict) -> MagicMock:
    ctx = MagicMock()
    ctx.state = state
    return ctx


def test_search_grounding_returns_chunks(isolated_store):
    store.put_grounding_chunk(isolated_store, GroundingChunk(
        chunk_id="c1", source_type="lecture", source_ref="shruti:x", location="0:00",
        concept_ids=["projectile.range"], text="range excerpt",
    ))
    result = tools.search_grounding(["projectile.range"])
    assert result["chunks"][0]["text"] == "range excerpt"
    assert result["chunks"][0]["chunk_id"] == "c1"


def test_search_grounding_empty_for_unknown_concept(isolated_store):
    assert tools.search_grounding(["nonexistent"]) == {"chunks": []}


def test_get_dpm_not_found(isolated_store):
    ctx = make_tool_context({"student_id": "demo_student"})
    assert tools.get_dpm(ctx) == {"found": False}


def test_get_dpm_found(isolated_store):
    store.put_dpm(isolated_store, DPMProfile(
        student_id="demo_student",
        weaknesses={"projectile.range": Weakness(mastery="partial", strength="weak", evidence=["s1#1"])},
    ))
    ctx = make_tool_context({"student_id": "demo_student"})
    result = tools.get_dpm(ctx)
    assert result["found"] is True
    assert result["weaknesses"]["projectile.range"]["mastery"] == "partial"


def test_get_teaching_memory_not_found(isolated_store):
    ctx = make_tool_context({"student_id": "demo_student"})
    assert tools.get_teaching_memory(ctx) == {"found": False}


def test_get_teaching_memory_found(isolated_store):
    store.put_teaching_memory(isolated_store, TeachingMemory(student_id="demo_student", syllabus=["projectile.range"]))
    ctx = make_tool_context({"student_id": "demo_student"})
    result = tools.get_teaching_memory(ctx)
    assert result["found"] is True
    assert result["syllabus"] == ["projectile.range"]


def test_log_turn_appends_to_buffer():
    ctx = make_tool_context({})
    tools.log_turn("why does range peak at 45?", "student", "", "", ctx)
    result = tools.log_turn("what happens to each component?", "tutor", "projectile.range", "", ctx)
    assert result["buffer_length"] == 2
    assert ctx.state["turn_buffer"][1]["role"] == "tutor"
    assert ctx.state["turn_buffer"][1]["concept_id"] == "projectile.range"
    assert ctx.state["turn_buffer"][0]["concept_id"] is None


def test_log_artifact_evidence_appends_to_buffer():
    ctx = make_tool_context({})
    result = tools.log_artifact_evidence("discovered_optimum", "artifact-abc123", ctx)
    assert result == {"logged": True}
    assert ctx.state["artifact_events"] == [{"event": "discovered_optimum", "artifact_id": "artifact-abc123"}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd sub_modules/tutor && uv run pytest tests/unit/memory/test_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.memory.tools'`

- [ ] **Step 3: Write the implementation**

```python
# sub_modules/tutor/app/memory/tools.py
"""ADK tool functions for the shared memory layer. Every agent (TutorAgent,
ArtifactAgent) is given these same tool objects — this is what "one memory
layer, shared across agents" means concretely (memory_layer.md §3).

Long-term memory (dpm_profile, teaching_memory) is read-only here. The only
write path is close_session (app/session_close.py), run once at session end.
"""
from __future__ import annotations

import functools

from google.adk.tools import ToolContext

from app.memory import store


@functools.cache
def _conn():
    return store.connect()


def search_grounding(concept_ids: list[str]) -> dict:
    """Retrieve citable knowledge chunks (lecture/book excerpts) for the given concepts.

    Args:
        concept_ids: Concept ids to search for, e.g. ["projectile.horizontal_range"].

    Returns:
        dict with a "chunks" key: a list of {chunk_id, source_ref, location, text}.
    """
    chunks = store.search_grounding(_conn(), concept_ids)
    return {
        "chunks": [
            c.model_dump(include={"chunk_id", "source_ref", "location", "text"})
            for c in chunks
        ]
    }


def get_dpm(tool_context: ToolContext) -> dict:
    """Read this session's student's Dynamic Personal Memory: persona, coarse
    per-concept mastery, and standing pedagogical reflections.

    Returns:
        dict with the DPM profile fields, or {"found": false} if none exists yet.
    """
    student_id = tool_context.state["student_id"]
    profile = store.get_dpm(_conn(), student_id)
    if profile is None:
        return {"found": False}
    return {"found": True, **profile.model_dump(mode="json")}


def get_teaching_memory(tool_context: ToolContext) -> dict:
    """Read this session's student's Teaching Memory: syllabus coverage, open
    doubts, and the current teaching mode.

    Returns:
        dict with the teaching memory fields, or {"found": false} if none exists yet.
    """
    student_id = tool_context.state["student_id"]
    memory = store.get_teaching_memory(_conn(), student_id)
    if memory is None:
        return {"found": False}
    return {"found": True, **memory.model_dump(mode="json")}


def log_turn(text: str, role: str, concept_id: str, artifact_id: str, tool_context: ToolContext) -> dict:
    """Append one turn to the in-session buffer. RAM only — never written to
    disk mid-session (memory_layer.md §3). Call this after every exchange.

    Args:
        text: What was said.
        role: "student" or "tutor".
        concept_id: The concept this turn is about. Pass "" if none.
        artifact_id: The artifact this turn references. Pass "" if none.

    Returns:
        dict with the new buffer length.
    """
    buffer = tool_context.state.get("turn_buffer", [])
    buffer.append({
        "turn": len(buffer) + 1,
        "role": role,
        "text": text,
        "concept_id": concept_id or None,
        "artifact_id": artifact_id or None,
    })
    tool_context.state["turn_buffer"] = buffer
    return {"buffer_length": len(buffer)}


def log_artifact_evidence(event: str, artifact_id: str, tool_context: ToolContext) -> dict:
    """Append an artifact interaction event (e.g. "discovered_optimum",
    "misconception_behavior" — see sub_modules/artifact_generator's probes)
    to the in-session buffer.

    Args:
        event: The event name the artifact reported.
        artifact_id: Which artifact reported it.

    Returns:
        dict confirming the event was buffered.
    """
    events = tool_context.state.get("artifact_events", [])
    events.append({"event": event, "artifact_id": artifact_id})
    tool_context.state["artifact_events"] = events
    return {"logged": True}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd sub_modules/tutor && uv run pytest tests/unit/memory/test_tools.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
cd sub_modules/tutor
git add app/memory/tools.py tests/unit/memory/test_tools.py
git commit -m "feat: add shared ADK memory tool functions"
```

---

### Task 5: Seed data — projectile motion, from Shruti's real vault

**Files:**
- Create: `sub_modules/tutor/scripts/seed_demo_data.py`
- Test: `sub_modules/tutor/tests/unit/test_seed_demo_data.py`

**Interfaces:**
- Consumes: `app.memory.store`, `app.memory.schemas` (Tasks 2–3); reads `sub_modules/shruti/vault/wiki/*.md`.
- Produces: `parse_wiki_file(path: Path) -> list[GroundingChunk]`, `seed(conn) -> None` (writes grounding chunks + one demo `DPMProfile` + one demo `TeachingMemory` for `student_id="demo_student"`). Task 6's live-verification step depends on this having been run once.

- [ ] **Step 1: Write the failing tests**

```python
# sub_modules/tutor/tests/unit/test_seed_demo_data.py
from pathlib import Path

from scripts.seed_demo_data import parse_wiki_file, seed
from app.memory import store

FIXTURE = """# Horizontal Range
`horizontal_range`


## Taught in shruti:d_jnekwca6i_4c5411d0 @3:40
The total horizontal distance traveled by a projectile from its launch point.

**Board:**
- [equation] R = u cos theta * t

## Taught in shruti:d_jnekwca6i_4c5411d0 @9:12
A second explanation, later in the same lecture.
"""


def test_parse_wiki_file_splits_on_taught_in_sections(tmp_path):
    wiki_file = tmp_path / "horizontal_range.md"
    wiki_file.write_text(FIXTURE)

    chunks = parse_wiki_file(wiki_file)

    assert len(chunks) == 2
    assert chunks[0].source_ref == "shruti:d_jnekwca6i_4c5411d0"
    assert chunks[0].location == "3:40"
    assert chunks[0].concept_ids == ["projectile.horizontal_range"]
    assert "total horizontal distance" in chunks[0].text
    assert chunks[1].location == "9:12"
    assert chunks[0].chunk_id != chunks[1].chunk_id


def test_seed_populates_grounding_and_demo_student():
    conn = store.connect(":memory:")
    seed(conn)

    results = store.search_grounding(conn, ["projectile.horizontal_range"])
    assert len(results) > 0

    profile = store.get_dpm(conn, "demo_student")
    assert profile is not None
    assert profile.student_id == "demo_student"

    memory = store.get_teaching_memory(conn, "demo_student")
    assert memory is not None
    assert "projectile.horizontal_range" in memory.syllabus
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd sub_modules/tutor && uv run pytest tests/unit/test_seed_demo_data.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts'`

- [ ] **Step 3: Write the implementation**

```python
# sub_modules/tutor/scripts/__init__.py
```

```python
# sub_modules/tutor/scripts/seed_demo_data.py
"""Seed one demo student against real, already-ingested projectile-motion
content from sub_modules/shruti/vault/wiki/ — not invented text
(architecture.md, "Demo subject" decision).

Run directly: `uv run python scripts/seed_demo_data.py`
"""
from __future__ import annotations

import re
from pathlib import Path

from app.memory import store
from app.memory.schemas import DPMProfile, GroundingChunk, Persona, TeachingMemory

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
WIKI_DIR = REPO_ROOT / "sub_modules" / "shruti" / "vault" / "wiki"

_SECTION = re.compile(
    r"## Taught in (?P<source_ref>shruti:\S+) @(?P<location>[\d:]+)\n"
    r"(?P<body>.*?)(?=\n## Taught in|\Z)",
    re.DOTALL,
)


def parse_wiki_file(path: Path) -> list[GroundingChunk]:
    """One GroundingChunk per '## Taught in ...' section — each carries its
    own real citation (recording id + timestamp) straight from Shruti."""
    text = path.read_text()
    slug = path.stem
    concept_id = f"projectile.{slug}"

    chunks = []
    for match in _SECTION.finditer(text):
        location = match.group("location")
        chunks.append(GroundingChunk(
            chunk_id=f"{slug}_{location.replace(':', '')}",
            source_type="lecture",
            source_ref=match.group("source_ref"),
            location=location,
            concept_ids=[concept_id],
            text=match.group("body").strip(),
        ))
    return chunks


def seed(conn) -> None:
    concept_ids = []
    for wiki_file in sorted(WIKI_DIR.glob("*.md")):
        chunks = parse_wiki_file(wiki_file)
        for chunk in chunks:
            store.put_grounding_chunk(conn, chunk)
        if chunks:
            concept_ids.append(chunks[0].concept_ids[0])

    store.put_dpm(conn, DPMProfile(
        student_id="demo_student",
        persona=Persona(preferred_pace="moderate", language_mix="en", interests=["cricket"]),
    ))
    store.put_teaching_memory(conn, TeachingMemory(
        student_id="demo_student",
        syllabus=concept_ids,
    ))


if __name__ == "__main__":
    conn = store.connect()
    seed(conn)
    print(f"Seeded demo_student against {WIKI_DIR}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd sub_modules/tutor && uv run pytest tests/unit/test_seed_demo_data.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Seed the real dev database, then commit**

```bash
cd sub_modules/tutor
uv run python scripts/seed_demo_data.py
# prints: Seeded demo_student against .../sub_modules/shruti/vault/wiki
git add scripts/ tests/unit/test_seed_demo_data.py
git commit -m "feat: seed demo student against real Shruti projectile-motion content"
```

---

### Task 6: TutorAgent

**Files:**
- Create: `sub_modules/tutor/app/agents/__init__.py`
- Create: `sub_modules/tutor/app/agents/tutor_agent.py`
- Modify: `sub_modules/tutor/app/agent.py` (replace the scaffold's demo weather/time agent)
- Test: `sub_modules/tutor/tests/unit/agents/test_tutor_agent.py`
- Test: `sub_modules/tutor/tests/unit/agents/__init__.py` (empty)

**Interfaces:**
- Consumes: `config.REASONING_MODEL` (Task 1), `search_grounding`, `get_dpm`, `get_teaching_memory`, `log_turn` (Task 4), `build_artifact_agent` (Task 7 — see note below on task ordering).
- Produces: `build_tutor_agent() -> LlmAgent` with `.name == "TutorAgent"`, `.mode == "single_turn"`. Task 9 (`VoiceAgent`) attaches this via `sub_agents=[build_tutor_agent()]`.

> **Ordering note:** `build_tutor_agent()` attaches `ArtifactAgent` as its own sub-agent, so it imports `app.agents.artifact_agent`. Do Task 7 (`ArtifactAgent`) immediately after this task's Steps 1–2 (write the failing test first, as normal), then come back and finish Steps 3–5 here — or read ahead and implement both files together. Either order is fine; what matters is neither task is considered done until both files exist and both test suites pass.

- [ ] **Step 1: Write the failing test**

```python
# sub_modules/tutor/tests/unit/agents/__init__.py
```

```python
# sub_modules/tutor/tests/unit/agents/test_tutor_agent.py
from app import config
from app.agents.tutor_agent import build_tutor_agent
from app.memory.tools import get_dpm, get_teaching_memory, log_turn, search_grounding


def test_tutor_agent_identity():
    agent = build_tutor_agent()
    assert agent.name == "TutorAgent"
    assert agent.mode == "single_turn"
    assert agent.model == config.REASONING_MODEL


def test_tutor_agent_has_a_description_for_delegation():
    # Required: with no input_schema set, ADK exposes this agent to its
    # parent as a tool taking one `request: str` field, described by
    # `agent.description` — verified against installed ADK source
    # (google/adk/tools/agent_tool.py::AgentTool._get_declaration).
    agent = build_tutor_agent()
    assert agent.description
    assert len(agent.description) > 10


def test_tutor_agent_has_the_memory_tools():
    agent = build_tutor_agent()
    assert search_grounding in agent.tools
    assert get_dpm in agent.tools
    assert get_teaching_memory in agent.tools
    assert log_turn in agent.tools


def test_tutor_agent_has_artifact_agent_as_a_single_turn_sub_agent():
    agent = build_tutor_agent()
    names = [a.name for a in agent.sub_agents]
    assert "ArtifactAgent" in names
    artifact_agent = next(a for a in agent.sub_agents if a.name == "ArtifactAgent")
    assert artifact_agent.mode == "single_turn"


def test_two_calls_to_build_tutor_agent_do_not_share_a_parent():
    # Regression guard for the "agent already has a parent" ValidationError —
    # factory functions must build fresh agent instances every call.
    a = build_tutor_agent()
    b = build_tutor_agent()
    assert a is not b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sub_modules/tutor && uv run pytest tests/unit/agents/test_tutor_agent.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.agents'`

- [ ] **Step 3: Write the implementation**

```python
# sub_modules/tutor/app/agents/__init__.py
```

```python
# sub_modules/tutor/app/agents/tutor_agent.py
"""TutorAgent — the reasoning / intelligence layer (architecture.md §2).

Holds all memory tools. Delegates artifact generation to ArtifactAgent via
ADK's mode='single_turn' sub-agent mechanism (never raw AgentTool — see
architecture.md §2 for why, verified against installed ADK source).
"""
from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext

from app import config
from app.agents.artifact_agent import build_artifact_agent
from app.memory.tools import get_dpm, get_teaching_memory, log_turn, search_grounding

TUTOR_INSTRUCTION = """You are Nityam, a tutor teaching projectile motion to one
student at a time.

Ground every factual claim in `search_grounding` — never state a formula or
fact you haven't retrieved from it. Call `get_dpm` and `get_teaching_memory`
at the start of a topic to see this student's mastery, open doubts, and
current teaching mode before deciding how to teach.

Rules:
1. Call `log_turn` after every exchange (yours and the student's) — this is
   the only way anything discussed becomes part of this student's permanent
   record.
2. When a diagram, an interactive simulation, or a worked example would teach
   better than words alone, delegate to ArtifactAgent with a clear
   pedagogical intent. You decide WHEN one is needed; it decides HOW to
   render it.
3. Never invent a mastery level, a doubt, or a fact about this student that
   didn't come from get_dpm or get_teaching_memory.
"""


async def _init_student(callback_context: CallbackContext) -> None:
    # Single-demo-student prototype (architecture.md "Demo subject" decision):
    # a real multi-student deployment would set this from the session's own
    # user_id instead of defaulting it here.
    callback_context.state.setdefault("student_id", "demo_student")


def build_tutor_agent() -> LlmAgent:
    return LlmAgent(
        name="TutorAgent",
        model=config.REASONING_MODEL,
        mode="single_turn",
        description=(
            "Handles any teaching moment for the projectile-motion student — "
            "call this whenever the student needs an explanation, wants to "
            "work through a problem, or their utterance needs more than a "
            "plain acknowledgement."
        ),
        instruction=TUTOR_INSTRUCTION,
        tools=[search_grounding, get_dpm, get_teaching_memory, log_turn],
        sub_agents=[build_artifact_agent()],
        before_agent_callback=_init_student,
    )
```

Now wire it as the app's `root_agent` for text-mode testing (`VoiceAgent` replaces this in Task 9):

```python
# sub_modules/tutor/app/agent.py
# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from google.adk.apps import App

from app.agents.tutor_agent import build_tutor_agent

root_agent = build_tutor_agent()

app = App(
    root_agent=root_agent,
    name="app",
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd sub_modules/tutor && uv run pytest tests/unit/agents/test_tutor_agent.py -v`
Expected: PASS (5 passed) — requires Task 7's `app/agents/artifact_agent.py` to exist first (see the ordering note above).

- [ ] **Step 5: Commit**

```bash
cd sub_modules/tutor
git add app/agents/__init__.py app/agents/tutor_agent.py app/agent.py tests/unit/agents/
git commit -m "feat: add TutorAgent, wire as root_agent for text-mode testing"
```

- [ ] **Step 6 (manual, blocked on API credits — see the top of this plan): live verification**

```bash
cd sub_modules/tutor
uv run python scripts/seed_demo_data.py   # if not already run in Task 5
agents-cli run "Why does the range peak at 45 degrees?"
```
Expected once credits are available: the agent calls `search_grounding`/`get_dpm`/`get_teaching_memory`/`log_turn` (confirm with `-v`), and responds grounded in the real Shruti excerpt rather than a generic textbook answer.

---

### Task 7: ArtifactAgent — wraps `sub_modules/artifact_generator`

**Files:**
- Create: `sub_modules/artifact_generator/generate/render.py` (extracted from `build.py`)
- Modify: `sub_modules/artifact_generator/build.py:101-134` (call the extracted function instead of inlining it)
- Create: `sub_modules/tutor/app/agents/artifact_agent.py`
- Test: `sub_modules/artifact_generator/tests/test_render.py` (Python; the existing `tests/*.js` are JS runtime tests and are untouched)
- Test: `sub_modules/tutor/tests/unit/agents/test_artifact_agent.py`

**Interfaces:**
- Consumes: `config.REASONING_MODEL` (Task 1), `get_dpm`, `get_teaching_memory`, `log_artifact_evidence` (Task 4).
- Produces: `render_html(ir: dict, theme_key: str, build_meta: dict) -> str` in `artifact_generator/generate/render.py`; `build_artifact_agent() -> LlmAgent` with `.name == "ArtifactAgent"`, `.mode == "single_turn"` in `tutor/app/agents/artifact_agent.py`. Task 6 imports `build_artifact_agent`.

- [ ] **Step 1: Write the failing test for the extracted render function**

```python
# sub_modules/artifact_generator/tests/test_render.py
"""Regression test for the render extraction — build.py must produce
byte-identical output to what render_html() now produces, since build.py's
own rendering logic is being replaced with a call to this function."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "generate"))

from render import render_html  # noqa: E402


def test_render_html_produces_self_contained_html():
    with open(os.path.join(ROOT, "examples", "lesson1_max_range.json")) as f:
        ir = json.load(f)

    html = render_html(ir, "plain", {"source": "test", "spec": "test"})

    assert html.startswith("<!doctype") or html.startswith("<!DOCTYPE")
    assert ir["artifact_id"] in html
    assert "__IR_JSON__" not in html  # placeholder must be substituted
    assert "__RUNTIME_JS__" not in html


def test_render_html_falls_back_to_plain_theme_for_unknown_theme():
    with open(os.path.join(ROOT, "examples", "lesson1_max_range.json")) as f:
        ir = json.load(f)

    html = render_html(ir, "nonexistent-theme", {"source": "test", "spec": "test"})
    assert ir["artifact_id"] in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sub_modules/artifact_generator && python3 -m pytest tests/test_render.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'render'`

- [ ] **Step 3: Extract `render_html`, update `build.py` to call it**

```python
# sub_modules/artifact_generator/generate/render.py
"""IR -> self-contained HTML. Extracted from build.py so both the CLI and
the ADK ArtifactAgent tool (sub_modules/tutor/app/agents/artifact_agent.py)
call the same rendering logic instead of duplicating it.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

RUNTIME_ORDER = ["kernel.js", "evaluate.js", "probes.js", "render.js", "mount.js"]


def render_html(ir: dict, theme_key: str, build_meta: dict) -> str:
    from kernel_py import parity_vectors  # sibling module in generate/

    with open(os.path.join(ROOT, "examples", "themes.json")) as f:
        themes = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    if theme_key not in themes:
        theme_key = "plain"
    build_meta = {**build_meta, "theme": theme_key}

    runtime = []
    for fn in RUNTIME_ORDER:
        with open(os.path.join(ROOT, "runtime", fn)) as f:
            runtime.append(f"/* ---- {fn} ---- */\n" + f.read())
    runtime_js = "\n\n".join(runtime)

    with open(os.path.join(ROOT, "shell", "template.html")) as f:
        html = f.read()

    return (
        html
        .replace("__TITLE__", ir["intent"].get("student_prompt", ir["artifact_id"])
                  .replace("{{theme.object}}", "it").replace("{{theme.protagonist}}", "they"))
        .replace("__ARTIFACT_ID__", ir["artifact_id"])
        .replace("__RUNTIME_JS__", runtime_js)
        .replace("__IR_JSON__", json.dumps(ir, ensure_ascii=False))
        .replace("__THEMES_JSON__", json.dumps(themes, ensure_ascii=False))
        .replace("__PARITY_JSON__", json.dumps(parity_vectors()))
        .replace("__BUILD_JSON__", json.dumps(build_meta))
    )
```

Now replace `build.py`'s inline stages 4–5 (the `# 4 ---- theme` and `# 5 ---- render` blocks) with a call to it. In `sub_modules/artifact_generator/build.py`, replace:

```python
    # 4 ------------------------------------------------------------- theme
    with open(os.path.join(HERE, "examples", "themes.json")) as f:
        themes = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    theme_key = args.theme or spec.interest
    if theme_key not in themes:
        theme_key = "plain"
    step("theme", f"{theme_key}  {DIM}(resolved at render, not baked into the IR){RESET}")

    # 5 ------------------------------------------------------------ render
    runtime = []
    for fn in RUNTIME_ORDER:
        with open(os.path.join(HERE, "runtime", fn)) as f:
            runtime.append(f"/* ---- {fn} ---- */\n" + f.read())
    runtime_js = "\n\n".join(runtime)

    with open(os.path.join(HERE, "shell", "template.html")) as f:
        html = f.read()

    build_meta = {
        "source": source,
        "theme": theme_key,
        "checks_passed": passed,
        "checks_total": len(report.checks),
        "spec": os.path.basename(args.spec),
    }

    html = (html
            .replace("__TITLE__", ir["intent"].get("student_prompt", ir["artifact_id"]).replace("{{theme.object}}", "it").replace("{{theme.protagonist}}", "they"))
            .replace("__ARTIFACT_ID__", ir["artifact_id"])
            .replace("__RUNTIME_JS__", runtime_js)
            .replace("__IR_JSON__", json.dumps(ir, ensure_ascii=False))
            .replace("__THEMES_JSON__", json.dumps(themes, ensure_ascii=False))
            .replace("__PARITY_JSON__", json.dumps(parity_vectors()))
            .replace("__BUILD_JSON__", json.dumps(build_meta)))
```

with:

```python
    # 4-5 --------------------------------------------------- theme + render
    theme_key = args.theme or spec.interest
    step("theme", f"{theme_key}  {DIM}(resolved at render, not baked into the IR){RESET}")
    build_meta = {
        "source": source,
        "checks_passed": passed,
        "checks_total": len(report.checks),
        "spec": os.path.basename(args.spec),
    }
    html = render.render_html(ir, theme_key, build_meta)
```

And add the import near the top of `build.py` (alongside the existing `from kernel_py import parity_vectors` line):

```python
import render                                      # noqa: E402
```

- [ ] **Step 4: Run tests to verify they pass, and confirm `build.py` still works unchanged**

```bash
cd sub_modules/artifact_generator
python3 -m pytest tests/test_render.py -v          # expect: 2 passed
python3 build.py --all                             # expect: unchanged CLI output, out/*.html still produced
node tests/smoke.js                                # expect: still passes — confirms render.py didn't change kernel/runtime behavior
```

- [ ] **Step 5: Commit the extraction**

```bash
cd sub_modules/artifact_generator
git add generate/render.py build.py tests/test_render.py
git commit -m "refactor: extract render_html() from build.py for reuse by ArtifactAgent"
```

- [ ] **Step 6: Write the failing test for ArtifactAgent**

```python
# sub_modules/tutor/tests/unit/agents/test_artifact_agent.py
from app import config
from app.agents.artifact_agent import build_artifact_agent, create_artifact
from app.memory.tools import get_dpm, get_teaching_memory, log_artifact_evidence


def test_artifact_agent_identity():
    agent = build_artifact_agent()
    assert agent.name == "ArtifactAgent"
    assert agent.mode == "single_turn"
    assert agent.model == config.REASONING_MODEL


def test_artifact_agent_has_a_description_for_delegation():
    agent = build_artifact_agent()
    assert agent.description
    assert len(agent.description) > 10


def test_artifact_agent_has_create_artifact_and_memory_read_tools():
    agent = build_artifact_agent()
    assert create_artifact in agent.tools
    assert get_dpm in agent.tools
    assert get_teaching_memory in agent.tools
    assert log_artifact_evidence in agent.tools


def test_two_calls_to_build_artifact_agent_do_not_share_a_parent():
    a = build_artifact_agent()
    b = build_artifact_agent()
    assert a is not b
```

Also add a non-live test of `create_artifact`'s validation/render/file-writing pipeline, using the artifact_generator's own golden IR — this needs no API call, matching `artifact_generator`'s own "mock path... offline, instant" precedent:

```python
# sub_modules/tutor/tests/unit/agents/test_artifact_agent_pipeline.py
"""Tests the parts of create_artifact() that don't need a live model call:
validation, rendering, file-writing, and the returned reference. The
generate_live() call itself is exercised only in the manual live-verification
step below, since it needs a working Gemini API key with quota."""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_TUTOR_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
_ARTIFACT_GEN = os.path.join(os.path.dirname(_TUTOR_ROOT), "artifact_generator")
sys.path.insert(0, os.path.join(_ARTIFACT_GEN, "generate"))

from render import render_html  # noqa: E402
from validate import validate  # noqa: E402


def test_golden_ir_validates_and_renders():
    with open(os.path.join(_ARTIFACT_GEN, "examples", "lesson1_max_range.json")) as f:
        ir = json.load(f)

    report = validate(ir, os.path.join(_ARTIFACT_GEN, "ir", "schema.json"))
    assert report.ok, report.errors

    html = render_html(ir, "plain", {"source": "test", "spec": "test"})
    assert ir["artifact_id"] in html
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `cd sub_modules/tutor && uv run pytest tests/unit/agents/test_artifact_agent.py tests/unit/agents/test_artifact_agent_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agents.artifact_agent'`

- [ ] **Step 8: Write the implementation**

```python
# sub_modules/tutor/app/agents/artifact_agent.py
"""ArtifactAgent — wraps sub_modules/artifact_generator's
spec -> IR -> validate -> render pipeline as a single_turn ADK sub-agent
(memory_layer.md §3, architecture.md §2).
"""
from __future__ import annotations

import os
import sys
import uuid

from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext

from app import config
from app.memory.tools import get_dpm, get_teaching_memory, log_artifact_evidence

_TUTOR_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ARTIFACT_GEN = os.path.join(os.path.dirname(_TUTOR_ROOT), "artifact_generator")
sys.path.insert(0, os.path.join(_ARTIFACT_GEN, "generate"))

ARTIFACTS_OUT = os.path.join(_TUTOR_ROOT, "app", "artifacts_out")


def create_artifact(
    intent: str,
    concept_ids: list[str],
    learning_outcome: str,
    target_misconception: str,
    interest: str,
    tool_context: ToolContext,
) -> dict:
    """Generate one interactive artifact (diagram, simulation, or quiz) for
    the student — the model configures it, it never writes the physics or
    the rendering code (sub_modules/artifact_generator/README.md).

    Args:
        intent: What pedagogical move this artifact makes, e.g. "let the
            student discover that range peaks at 45 degrees by exploring,
            not being told".
        concept_ids: Concept ids this artifact targets, e.g.
            ["projectile.horizontal_range"].
        learning_outcome: The one thing the student should walk away
            understanding.
        target_misconception: The specific wrong belief this artifact should
            surface and correct. Pass "" if there isn't one.
        interest: The student's theme to personalize with, e.g. "cricket".
            Pass "plain" if unknown.

    Returns:
        dict with "artifact_id" and "url" — the frontend mounts the artifact
        at this URL — or {"error": ...} if it failed validation.
    """
    import generator
    import validate
    from render import render_html
    from spec import ArtifactSpec

    artifact_spec = ArtifactSpec(
        intent=intent,
        concept_ids=concept_ids,
        learning_outcome=learning_outcome,
        target_misconception=target_misconception,
        student={"interest": interest},
    )
    schema_path = os.path.join(_ARTIFACT_GEN, "ir", "schema.json")
    ir, source = generator.generate_live(
        artifact_spec,
        lambda candidate: validate.validate(candidate, schema_path),
        model=config.REASONING_MODEL,
    )
    report = validate.validate(ir, schema_path)
    if not report.ok:
        return {"error": "artifact failed validation", "details": report.errors}

    artifact_id = ir.get("artifact_id") or f"artifact-{uuid.uuid4().hex[:8]}"
    html = render_html(ir, interest, {"source": source, "spec": intent})

    os.makedirs(ARTIFACTS_OUT, exist_ok=True)
    with open(os.path.join(ARTIFACTS_OUT, f"{artifact_id}.html"), "w", encoding="utf-8") as f:
        f.write(html)

    generated = tool_context.state.get("artifacts_generated", [])
    generated.append(artifact_id)
    tool_context.state["artifacts_generated"] = generated

    return {"artifact_id": artifact_id, "url": f"/artifacts/{artifact_id}.html"}


ARTIFACT_INSTRUCTION = """You turn a pedagogical need into one interactive artifact.

Read get_dpm and get_teaching_memory to calibrate: a student who is "partial"
on a concept needs a more scaffolded artifact than one who is "known". Call
create_artifact exactly once with a clear intent, then report back only the
artifact_id and url — do not describe the artifact in prose, the visual IS
the explanation.
"""


def build_artifact_agent() -> LlmAgent:
    return LlmAgent(
        name="ArtifactAgent",
        model=config.REASONING_MODEL,
        mode="single_turn",
        description=(
            "Generates one interactive artifact (diagram, simulation, or "
            "quiz) for a specific pedagogical need. Call with a clear "
            "description of what the student should discover or practice."
        ),
        instruction=ARTIFACT_INSTRUCTION,
        tools=[create_artifact, get_dpm, get_teaching_memory, log_artifact_evidence],
    )
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd sub_modules/tutor && uv run pytest tests/unit/agents/test_artifact_agent.py tests/unit/agents/test_artifact_agent_pipeline.py -v`
Expected: PASS (6 passed)

Then re-run Task 6's test, which depends on this file existing:

Run: `cd sub_modules/tutor && uv run pytest tests/unit/agents/test_tutor_agent.py -v`
Expected: PASS (5 passed)

- [ ] **Step 10: Commit**

```bash
cd sub_modules/tutor
git add app/agents/artifact_agent.py tests/unit/agents/test_artifact_agent.py tests/unit/agents/test_artifact_agent_pipeline.py
git commit -m "feat: add ArtifactAgent wrapping artifact_generator's IR pipeline"
```

- [ ] **Step 11 (manual, blocked on API credits): live verification**

```bash
cd sub_modules/tutor
agents-cli run "I want to understand why the range peaks at 45 degrees, can you show me something I can play with?"
```
Expected once credits are available: `TutorAgent` delegates to `ArtifactAgent`, which calls `create_artifact`, producing a real file at `app/artifacts_out/<artifact_id>.html`; check it renders by opening it directly in a browser.

---

### Task 8: Session close — write-back with validated operations

**Files:**
- Create: `sub_modules/tutor/app/memory/ops.py`
- Create: `sub_modules/tutor/app/session_close.py`
- Test: `sub_modules/tutor/tests/unit/memory/test_ops.py`
- Test: `sub_modules/tutor/tests/unit/test_session_close.py`

**Interfaces:**
- Consumes: `app.memory.schemas`, `app.memory.store` (Tasks 2–3).
- Produces: `ops.append_self_reflection`, `ops.set_mastery`, `ops.open_doubt`, `ops.close_doubt`, `ops.update_coverage`; `session_close.build_session_log(...) -> SessionLog`, `session_close.apply_operations(profile, memory, result) -> tuple[DPMProfile, TeachingMemory]`, `session_close.reflect(client, log) -> ReflectResult`, `session_close.close_session(conn, session_id, student_id, started_at, buffer, client) -> SessionLog`.

- [ ] **Step 1: Write the failing tests for `ops.py`**

```python
# sub_modules/tutor/tests/unit/memory/test_ops.py
from app.memory import ops
from app.memory.schemas import DPMProfile, TeachingMemory


def test_set_mastery_adds_a_weakness_entry():
    profile = DPMProfile(student_id="demo_student")
    ops.set_mastery(profile, "projectile.range", "partial", "weak", ["s1#4"])
    assert profile.weaknesses["projectile.range"].mastery == "partial"
    assert profile.weaknesses["projectile.range"].evidence == ["s1#4"]


def test_append_self_reflection_adds_a_note():
    profile = DPMProfile(student_id="demo_student")
    ops.append_self_reflection(profile, "responds well to area models", ["s1#6"])
    assert profile.self_reflection[0].note == "responds well to area models"
    assert profile.self_reflection[0].status == "active"


def test_open_doubt_adds_an_active_doubt():
    memory = TeachingMemory(student_id="demo_student")
    ops.open_doubt(memory, "projectile.range", "uses u instead of u*cos(theta)", "R = u^2 sin(2theta)/g", ["s1#4"])
    assert memory.open_doubts[0].status == "active"
    assert memory.open_doubts[0].concept_id == "projectile.range"


def test_close_doubt_only_affects_matching_concept():
    memory = TeachingMemory(student_id="demo_student")
    ops.open_doubt(memory, "projectile.range", "d1", "c1", ["s1#1"])
    ops.open_doubt(memory, "projectile.height", "d2", "c2", ["s1#2"])
    ops.close_doubt(memory, "projectile.range")
    assert memory.open_doubts[0].status == "resolved"
    assert memory.open_doubts[1].status == "active"


def test_update_coverage_merges_elements_used():
    memory = TeachingMemory(student_id="demo_student")
    ops.update_coverage(memory, "projectile.range", ["worked-example"], "s1#4", "in_progress")
    ops.update_coverage(memory, "projectile.range", ["diagram"], "s2#3", "covered")
    entry = memory.covered["projectile.range"]
    assert set(entry.elements_used) == {"worked-example", "diagram"}
    assert entry.taught_at == ["s1#4", "s2#3"]
    assert entry.status == "covered"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd sub_modules/tutor && uv run pytest tests/unit/memory/test_ops.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.memory.ops'`

- [ ] **Step 3: Write `ops.py`**

```python
# sub_modules/tutor/app/memory/ops.py
"""Validated operations applied to DPMProfile/TeachingMemory at session close.
Never a raw overwrite (memory_layer.md §4) — each function mutates one
specific field, in place, and returns the record for chaining.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.memory.schemas import CoveredConcept, DPMProfile, OpenDoubt, SelfReflection, TeachingMemory, Weakness


def append_self_reflection(profile: DPMProfile, note: str, evidence: list[str]) -> DPMProfile:
    profile.self_reflection.append(SelfReflection(note=note, evidence=evidence))
    return profile


def set_mastery(profile: DPMProfile, concept_id: str, mastery: str, strength: str, evidence: list[str]) -> DPMProfile:
    profile.weaknesses[concept_id] = Weakness(
        mastery=mastery, strength=strength, evidence=evidence,
        last_updated=datetime.now(timezone.utc),
    )
    return profile


def open_doubt(memory: TeachingMemory, concept_id: str, doubt: str, correct_understanding: str, evidence: list[str]) -> TeachingMemory:
    memory.open_doubts.append(OpenDoubt(
        concept_id=concept_id, doubt=doubt, correct_understanding=correct_understanding,
        status="active", evidence=evidence,
    ))
    return memory


def close_doubt(memory: TeachingMemory, concept_id: str) -> TeachingMemory:
    """Only call this after evidence of a SPACED re-check — never on one
    correct answer in the same session (memory_layer.md §2.3)."""
    for doubt in memory.open_doubts:
        if doubt.concept_id == concept_id and doubt.status != "resolved":
            doubt.status = "resolved"
    return memory


def update_coverage(memory: TeachingMemory, concept_id: str, elements_used: list[str], taught_at: str, status: str) -> TeachingMemory:
    entry = memory.covered.get(concept_id)
    if entry is None:
        entry = CoveredConcept()
        memory.covered[concept_id] = entry
    entry.elements_used = sorted(set(entry.elements_used) | set(elements_used))
    entry.taught_at = [*entry.taught_at, taught_at]
    entry.status = status
    return memory
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd sub_modules/tutor && uv run pytest tests/unit/memory/test_ops.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
cd sub_modules/tutor
git add app/memory/ops.py tests/unit/memory/test_ops.py
git commit -m "feat: add validated memory-update operations for session close"
```

- [ ] **Step 6: Write the failing tests for `session_close.py`**

```python
# sub_modules/tutor/tests/unit/test_session_close.py
"""apply_operations and build_session_log need no API call — tested here
directly. reflect() itself calls the live model and is exercised only in the
manual live-verification step below."""
from datetime import datetime, timezone

from app.memory import store
from app.memory.schemas import DPMProfile, TeachingMemory
from app.session_close import ReflectOp, ReflectResult, apply_operations, build_session_log


def test_build_session_log_is_deterministic():
    started = datetime.now(timezone.utc)
    buffer = [
        {"turn": 1, "role": "student", "text": "why 45 degrees?", "concept_id": None, "artifact_id": None},
        {"turn": 2, "role": "tutor", "text": "what happens to each component?", "concept_id": "projectile.range", "artifact_id": None},
    ]
    log = build_session_log("s1", "demo_student", started, buffer)

    assert log.session_id == "s1"
    assert len(log.turns) == 2
    assert log.turns[1].concept_id == "projectile.range"
    assert log.ended_at is not None


def test_apply_operations_runs_known_ops_and_skips_unknown():
    profile = DPMProfile(student_id="demo_student")
    memory = TeachingMemory(student_id="demo_student")
    result = ReflectResult(
        summary="student worked through range formula",
        operations=[
            ReflectOp(op="set_mastery", args={
                "concept_id": "projectile.range", "mastery": "partial",
                "strength": "weak", "evidence": ["s1#2"],
            }),
            ReflectOp(op="open_doubt", args={
                "concept_id": "projectile.range", "doubt": "uses u not u*cos(theta)",
                "correct_understanding": "R = u^2 sin(2theta)/g", "evidence": ["s1#2"],
            }),
            ReflectOp(op="some_future_op_this_version_does_not_know", args={"x": 1}),
        ],
    )

    profile, memory = apply_operations(profile, memory, result)

    assert profile.weaknesses["projectile.range"].mastery == "partial"
    assert memory.open_doubts[0].concept_id == "projectile.range"


def test_apply_operations_drops_malformed_args_without_raising():
    profile = DPMProfile(student_id="demo_student")
    memory = TeachingMemory(student_id="demo_student")
    result = ReflectResult(
        summary="",
        operations=[ReflectOp(op="set_mastery", args={"concept_id": "x"})],  # missing required args
    )

    # Must not raise — a malformed op is dropped, not a crash (memory_layer.md §4).
    profile, memory = apply_operations(profile, memory, result)
    assert profile.weaknesses == {}
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `cd sub_modules/tutor && uv run pytest tests/unit/test_session_close.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.session_close'`

- [ ] **Step 8: Write `session_close.py`**

```python
# sub_modules/tutor/app/session_close.py
"""Session close: buffer -> session_log (deterministic) + one Reflect call
proposing validated ops against dpm_profile/teaching_memory (memory_layer.md
§4). Triggered by the current session ending — not a background agent
(deferred.md).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from google import genai
from pydantic import BaseModel

from app import config
from app.memory import ops, store
from app.memory.schemas import DPMProfile, SessionLog, TeachingMemory, Turn


def build_session_log(session_id: str, student_id: str, started_at: datetime, buffer: list[dict]) -> SessionLog:
    """Deterministic. No model call."""
    return SessionLog(
        session_id=session_id,
        student_id=student_id,
        started_at=started_at,
        ended_at=datetime.now(timezone.utc),
        turns=[Turn(**t) for t in buffer],
    )


class ReflectOp(BaseModel):
    op: str
    args: dict[str, Any]


class ReflectResult(BaseModel):
    operations: list[ReflectOp]
    summary: str


REFLECT_PROMPT = """You did not teach this session. Read it as an observer.

Session log:
{session_json}

Propose operations against this student's memory. Use ONLY these op names:
  set_mastery(concept_id, mastery, strength, evidence)
  open_doubt(concept_id, doubt, correct_understanding, evidence)
  close_doubt(concept_id)   -- only if the log shows a SPACED re-check succeeding,
                               never from one correct answer in this same session
  update_coverage(concept_id, elements_used, taught_at, status)
  append_self_reflection(note, evidence)

Every evidence value must be a "{{session_id}}#turn" reference to a real turn
number in the session log above. Do not invent turns that aren't there.
"""


def reflect(client: genai.Client, log: SessionLog) -> ReflectResult:
    response = client.models.generate_content(
        model=config.REASONING_MODEL,
        contents=REFLECT_PROMPT.format(session_json=log.model_dump_json(indent=2)),
        config={"response_mime_type": "application/json", "response_schema": ReflectResult},
    )
    return ReflectResult.model_validate_json(response.text)


def apply_operations(profile: DPMProfile, memory: TeachingMemory, result: ReflectResult) -> tuple[DPMProfile, TeachingMemory]:
    """Validated ops only — an unknown op name or malformed args is dropped,
    never raised (memory_layer.md §4)."""
    handlers = {
        "set_mastery": lambda a: ops.set_mastery(profile, **a),
        "append_self_reflection": lambda a: ops.append_self_reflection(profile, **a),
        "open_doubt": lambda a: ops.open_doubt(memory, **a),
        "close_doubt": lambda a: ops.close_doubt(memory, **a),
        "update_coverage": lambda a: ops.update_coverage(memory, **a),
    }
    for operation in result.operations:
        handler = handlers.get(operation.op)
        if handler is None:
            continue
        try:
            handler(operation.args)
        except TypeError:
            continue
    return profile, memory


def close_session(
    conn: sqlite3.Connection,
    session_id: str,
    student_id: str,
    started_at: datetime,
    buffer: list[dict],
    client: genai.Client,
) -> SessionLog:
    log = build_session_log(session_id, student_id, started_at, buffer)
    store.put_session_log(conn, log)

    profile = store.get_dpm(conn, student_id) or DPMProfile(student_id=student_id)
    memory = store.get_teaching_memory(conn, student_id) or TeachingMemory(student_id=student_id)

    result = reflect(client, log)
    profile, memory = apply_operations(profile, memory, result)

    store.put_dpm(conn, profile)
    store.put_teaching_memory(conn, memory)
    return log
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd sub_modules/tutor && uv run pytest tests/unit/test_session_close.py -v`
Expected: PASS (3 passed)

- [ ] **Step 10: Commit**

```bash
cd sub_modules/tutor
git add app/session_close.py tests/unit/test_session_close.py
git commit -m "feat: add session-close write-back with the Reflect step"
```

- [ ] **Step 11 (manual, blocked on API credits): live verification**

```bash
cd sub_modules/tutor
uv run python -c "
from datetime import datetime, timezone
from google import genai
from app.memory import store
from app.session_close import close_session

conn = store.connect()
client = genai.Client()
buffer = [
    {'turn': 1, 'role': 'student', 'text': 'why 45 degrees?', 'concept_id': None, 'artifact_id': None},
    {'turn': 2, 'role': 'tutor', 'text': 'because both components matter equally there', 'concept_id': 'projectile.horizontal_range', 'artifact_id': None},
]
log = close_session(conn, 'manual-test-1', 'demo_student', datetime.now(timezone.utc), buffer, client)
print(log.model_dump_json(indent=2))
print(store.get_teaching_memory(conn, 'demo_student').model_dump_json(indent=2))
"
```
Expected once credits are available: a `session_log` row is written, and `teaching_memory` shows a real coverage/doubt update citing `manual-test-1#2`.

---

### Task 9: VoiceAgent — Live wiring

**Files:**
- Create: `sub_modules/tutor/app/agents/voice_agent.py`
- Modify: `sub_modules/tutor/app/agent.py` (swap `root_agent` from `TutorAgent` to `VoiceAgent`)
- Test: `sub_modules/tutor/tests/unit/agents/test_voice_agent.py`

**Interfaces:**
- Consumes: `config.LIVE_MODEL` (Task 1), `build_tutor_agent` (Task 6).
- Produces: `build_voice_agent() -> LlmAgent` with `.name == "VoiceAgent"`, `.model == config.LIVE_MODEL`.

> **No custom WebSocket/`LiveRequestQueue` code in this task, on purpose.** The
> scaffold's `app/fast_api_app.py` already serves `get_fast_api_app(web=True)`,
> ADK's own dev server — it owns `LiveRequestQueue` creation, audio streaming,
> and `runner.run_live()` internally, and `agents-cli playground` drives it
> with a real microphone in the browser. `architecture.md` §3's operational
> facts (one queue per connection, multi-part events, the two reconnect
> clocks) are about that server's internals, not code this plan writes — they
> matter again only if/when a dedicated production WebSocket bridge for the
> canvas frontend is built later, which is `deferred.md` territory, not v1.

- [ ] **Step 1: Write the failing test**

```python
# sub_modules/tutor/tests/unit/agents/test_voice_agent.py
from app import config
from app.agents.voice_agent import build_voice_agent


def test_voice_agent_identity():
    agent = build_voice_agent()
    assert agent.name == "VoiceAgent"
    assert agent.model == config.LIVE_MODEL


def test_voice_agent_has_tutor_agent_as_single_turn_sub_agent():
    agent = build_voice_agent()
    names = [a.name for a in agent.sub_agents]
    assert "TutorAgent" in names
    tutor = next(a for a in agent.sub_agents if a.name == "TutorAgent")
    assert tutor.mode == "single_turn"


def test_voice_agent_instruction_is_small():
    # Live bills the full system instruction on every turn (architecture.md
    # §3) — this is a regression guard against memory creeping back into it.
    agent = build_voice_agent()
    assert len(agent.instruction) < 800
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sub_modules/tutor && uv run pytest tests/unit/agents/test_voice_agent.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.agents.voice_agent'`

- [ ] **Step 3: Write the implementation**

```python
# sub_modules/tutor/app/agents/voice_agent.py
"""VoiceAgent — native-audio bidirectional streaming layer (architecture.md
§2, §3). Deliberately thin: no memory, no reasoning. Its only job is deciding
whether an utterance needs TutorAgent or is a plain acknowledgement.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent

from app import config
from app.agents.tutor_agent import build_tutor_agent

VOICE_INSTRUCTION = """You are the voice of Nityam, a tutor. Speak naturally
in the student's language mix; never translate technical terms they or their
teacher used.

You do not teach. For anything beyond a plain acknowledgement ("okay",
"haan", a greeting), delegate to TutorAgent and speak back exactly what it
returns."""


def build_voice_agent() -> LlmAgent:
    return LlmAgent(
        name="VoiceAgent",
        model=config.LIVE_MODEL,
        instruction=VOICE_INSTRUCTION,
        sub_agents=[build_tutor_agent()],
    )
```

```python
# sub_modules/tutor/app/agent.py  (replace the Task 6 version)
# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from google.adk.apps import App

from app.agents.voice_agent import build_voice_agent

root_agent = build_voice_agent()

app = App(
    root_agent=root_agent,
    name="app",
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd sub_modules/tutor && uv run pytest tests/unit/agents/test_voice_agent.py -v`
Expected: PASS (3 passed)

Also re-run the full unit suite once more to confirm nothing broke from swapping `root_agent`:

Run: `cd sub_modules/tutor && uv run pytest tests/unit -v`
Expected: all still PASS (agent identity tests for `TutorAgent`/`ArtifactAgent` don't depend on what `app.agent.root_agent` points to).

- [ ] **Step 5: Commit**

```bash
cd sub_modules/tutor
git add app/agents/voice_agent.py app/agent.py tests/unit/agents/test_voice_agent.py
git commit -m "feat: add VoiceAgent, wire as root_agent for the live voice loop"
```

- [ ] **Step 6 (manual, blocked on API credits): live verification**

```bash
cd sub_modules/tutor
agents-cli playground
```
In the browser UI: use the microphone toggle, say "Why does the range peak at 45 degrees?", and confirm audio comes back. Watch for the operational gotchas from `architecture.md` §3 while testing: one `LiveRequestQueue` per connection, multi-part events (audio + transcript together), and whether `cached_content_token_count`/transcription behaves as `architecture.md` §2 predicts for a `mode='single_turn'` sub-agent (the one thing that document flags as not yet empirically confirmed).

---

### Task 10: Frontend artifact serving

**Files:**
- Modify: `sub_modules/tutor/app/fast_api_app.py`
- Test: `sub_modules/tutor/tests/integration/test_artifact_serving.py`

**Interfaces:**
- Consumes: `ARTIFACTS_OUT` (Task 7), the FastAPI `app` object already built by the scaffold.
- Produces: `GET /artifacts/<artifact_id>.html` serves whatever `ArtifactAgent.create_artifact` wrote — this is the URL a real canvas frontend embeds (architecture.md §1, out of scope beyond this reference — see `deferred.md` for the canvas/avatar integration itself).

- [ ] **Step 1: Write the failing test**

```python
# sub_modules/tutor/tests/integration/test_artifact_serving.py
import os

from fastapi.testclient import TestClient

from app.agents.artifact_agent import ARTIFACTS_OUT
from app.fast_api_app import app


def test_generated_artifact_is_servable():
    os.makedirs(ARTIFACTS_OUT, exist_ok=True)
    marker_path = os.path.join(ARTIFACTS_OUT, "test-artifact-123.html")
    with open(marker_path, "w") as f:
        f.write("<!doctype html><title>test artifact</title>")

    try:
        client = TestClient(app)
        response = client.get("/artifacts/test-artifact-123.html")
        assert response.status_code == 200
        assert "test artifact" in response.text
    finally:
        os.remove(marker_path)


def test_missing_artifact_is_a_404():
    client = TestClient(app)
    response = client.get("/artifacts/does-not-exist.html")
    assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sub_modules/tutor && uv run pytest tests/integration/test_artifact_serving.py -v`
Expected: FAIL with 404 on the first test (no `/artifacts` route mounted yet)

- [ ] **Step 3: Mount the static route**

In `sub_modules/tutor/app/fast_api_app.py`, add near the top (with the other imports):

```python
from fastapi.staticfiles import StaticFiles
```

and after the `app: FastAPI = get_fast_api_app(...)` block (after the existing `app.description = ...` line), add:

```python
_ARTIFACTS_DIR = os.path.join(AGENT_DIR, "app", "artifacts_out")
os.makedirs(_ARTIFACTS_DIR, exist_ok=True)
app.mount("/artifacts", StaticFiles(directory=_ARTIFACTS_DIR), name="artifacts")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd sub_modules/tutor && uv run pytest tests/integration/test_artifact_serving.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the full test suite one more time**

Run: `cd sub_modules/tutor && uv run pytest tests/unit tests/integration -v`
Expected: all PASS. This is everything buildable and testable without live model credits — see the blocker note at the top of this plan for what's left.

- [ ] **Step 6: Commit**

```bash
cd sub_modules/tutor
git add app/fast_api_app.py tests/integration/test_artifact_serving.py
git commit -m "feat: serve generated artifacts at /artifacts/<id>.html"
```

---

## After this plan

Once API credits are restored, work through the "manual, blocked on API credits" steps in Tasks 6, 7, 8, and 9 in order — each proves one more piece of `architecture.md` §6's build order is real, not just structurally correct. Wiring a real canvas frontend around the `/artifacts/<id>.html` reference (rather than this plan's bare integration test) is `sub_modules/canvas`'s own scope, not this plan's — see `deferred.md` for what's deliberately not built here yet.
