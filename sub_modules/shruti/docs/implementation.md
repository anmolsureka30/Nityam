# SHRUTI — Implementation Guide

Companion to *SHRUTI — Architecture, Research & Decisions*.
Everything here is meant to be typed into an editor. Version 0.1.

---

## 1. Repository layout

```
shruti/
├── pyproject.toml                    # uv-managed. Python 3.12+
├── justfile                          # task runner (see §8)
├── .env.example
├── README.md
│
├── docker/
│   ├── Dockerfile.conductor          # ADK orchestrator + FastAPI (CPU)
│   ├── Dockerfile.slate              # CV worker. CPU v1 → CUDA base when SAM 3 lands
│   └── compose.yaml                  # postgres+pgvector, gcs-emulator, both services
│
├── infra/
│   ├── terraform/                    # Cloud Run, Cloud SQL, GCS, Pub/Sub topics
│   └── migrations/                   # alembic
│       ├── 001_reel.sql
│       ├── 002_ledger.sql
│       ├── 003_atlas.sql
│       └── 004_index.sql
│
├── shruti/
│   ├── config.py                     # pydantic-settings. ALL model IDs live here.
│   │
│   ├── contracts/                    # ← pydantic models. The stage boundaries.
│   │   ├── recording.py              #   Recording, SurfaceKind
│   │   ├── timeline.py               #   Timeline, Shot, EraseEvent, SamplePlan
│   │   ├── board.py                  #   BoardState, BoardContent, Region
│   │   ├── speech.py                 #   Utterance, LanguageSpan, Deixis
│   │   ├── beat.py                   #   Beat, TimeSpan, BeatKind
│   │   └── atlas.py                  #   Concept, Edge, Misconception, BeatRef
│   │
│   ├── stages/                       # ← one package per pipeline stage
│   │   ├── gate/
│   │   │   ├── admit.py              #   resolve source, yt-dlp
│   │   │   ├── probe.py              #   ffprobe → Recording
│   │   │   ├── normalize.py          #   ffmpeg: CFR h264 + 16kHz mono wav
│   │   │   └── surface.py            #   flash-lite surface classifier
│   │   ├── pulse/
│   │   │   ├── shots.py              #   PySceneDetect wrappers
│   │   │   ├── ink.py                #   ink_curve, binarization, polarity
│   │   │   ├── erase.py              #   erase-event detection from ink curve
│   │   │   └── plan.py               #   adaptive sample plan
│   │   ├── slate/
│   │   │   ├── locate.py             #   board quad detection + voting
│   │   │   ├── rectify.py            #   homography → canonical board coords
│   │   │   ├── mask.py               #   V1 framediff · V2 yolo · V3 sam3
│   │   │   ├── composite.py          #   ★ the core algorithm (§4)
│   │   │   └── photometric.py        #   donor patch normalization
│   │   ├── echo/
│   │   │   ├── transcribe.py         #   gemini audio
│   │   │   └── subtitle_prior.py     #   vtt/srt parse + alignment
│   │   ├── point/
│   │   │   └── deixis.py             #   gesture clips → board regions
│   │   ├── weave/
│   │   │   ├── boundaries.py         #   3-signal merge
│   │   │   └── fuse.py               #   → Beat[]
│   │   ├── glyph/
│   │   │   └── read.py               #   board state → BoardContent
│   │   └── atlas/
│   │       ├── concepts.py
│   │       ├── relations.py
│   │       ├── misconceptions.py
│   │       └── canonicalize.py       #   dedup against curriculum spine
│   │
│   ├── vault/                        # ← storage. one module per layer.
│   │   ├── reel.py                   #   L1 immutable writes
│   │   ├── ledger.py                 #   L2 bitemporal board states
│   │   ├── atlas_store.py            #   L3 versioned graph
│   │   ├── index.py                  #   pgvector
│   │   ├── objects.py                #   GCS
│   │   └── mirror.py                 #   DuckDB analytics mirror + views
│   │
│   ├── lens/                         # ← retrieval, consumed by the tutor
│   │   ├── route.py                  #   intent classification
│   │   ├── retrievers.py             #   vector · graph · timeline · ledger
│   │   └── adk_tools.py              #   ★ the tools the Nityam tutor calls
│   │
│   ├── agents/                       # ← ADK
│   │   ├── pipeline.py               #   the SequentialAgent tree
│   │   ├── tools.py                  #   FunctionTool wrappers over stages/
│   │   ├── plugins.py                #   Provenance, CostGuard, Trace
│   │   └── state.py                  #   Stage state machine
│   │
│   ├── prompts/                      # ← plain .md files, hot-reloadable
│   │   ├── echo_transcript.md
│   │   ├── glyph_read_board.md
│   │   ├── point_deixis.md
│   │   ├── weave_beats.md
│   │   ├── atlas_concepts.md
│   │   ├── atlas_relations.md
│   │   └── atlas_misconceptions.md
│   │
│   ├── schemas/                      # ← JSON Schema for structured output
│   │   ├── board_content.json
│   │   ├── beats.json
│   │   ├── concepts.json
│   │   └── misconceptions.json
│   │
│   ├── gemini/
│   │   ├── client.py                 #   genai client, retries, cost accounting
│   │   ├── batch.py                  #   ★ Batch API submit/poll/collect
│   │   └── cache.py                  #   explicit context caching
│   │
│   └── cli.py                        # typer
│
├── evals/
│   ├── golden/
│   │   ├── board_states/             #   E1 — annotated CCs
│   │   ├── transcripts/              #   E2 — hand transcripts
│   │   └── graphs/                   #   E3 — gold concept graphs
│   ├── e1_board_recall.py
│   ├── e2_transcript_fidelity.py
│   ├── e3_extraction_f1.py
│   └── e4_provenance_invariant.py    #   runs in CI, fails the build
│
└── tests/
```

**Two conventions worth enforcing from commit one:**

1. **`contracts/` is the API between stages.** A stage imports contracts and nothing else from its siblings. This is what makes any stage independently re-runnable against cached upstream output.
2. **Model IDs live only in `config.py`.** Gemini shipped 3.5 Flash in May, 3.6 Flash in July, and `gemini-3.7-flash` appears in the docs already. Hardcode a model string anywhere else and you'll be grepping for it in three months.

---

## 2. Configuration

```python
# shruti/config.py
from pydantic_settings import BaseSettings

class Models(BaseSettings):
    reasoner:   str = "gemini-3.5-flash"        # semantics, extraction, ASR
    router:     str = "gemini-3.5-flash-lite"   # classification, dedup
    embedder:   str = "gemini-embedding-001"

class Budget(BaseSettings):
    max_cost_per_recording_usd: float = 2.00
    use_batch_api: bool = True                  # offline ⇒ always true
    cache_ttl_seconds: int = 3600

class SlateConfig(BaseSettings):
    mask_tier: str = "framediff"                # framediff | yolo | sam3
    board_vote_frames: int = 30
    composite_window_s: float = 45.0
    photometric_match: bool = True

class PulseConfig(BaseSettings):
    dense_fps: float = 1.0
    sparse_fps: float = 1/6
    erase_drop_ratio: float = 0.35              # ink loss that counts as an erase
    erase_window_s: float = 3.0
    scene_threshold: float = 27.0
```

---

## 3. Schema (Postgres)

```sql
-- ══════════════════════════ L1 · THE REEL ══════════════════════════
-- Immutable. Append-only. Ground truth. Nothing here is ever UPDATEd.

CREATE TABLE recording (
    id              TEXT PRIMARY KEY,           -- sha256 of normalized video
    source_uri      TEXT NOT NULL,
    title           TEXT,
    duration_s      REAL NOT NULL,
    fps             REAL NOT NULL,
    width           INT, height INT,
    surface_kind    TEXT NOT NULL,              -- blackboard|whiteboard|slides|mixed
    subject         TEXT, grade INT, chapter TEXT,
    ingested_at     TIMESTAMPTZ DEFAULT now(),
    reel_version    INT NOT NULL DEFAULT 1
);

CREATE TABLE utterance (
    id              TEXT PRIMARY KEY,
    recording_id    TEXT NOT NULL REFERENCES recording(id),
    span            TSTZRANGE NOT NULL,         -- or (start_s, end_s) REAL for simplicity
    start_s         REAL NOT NULL, end_s REAL NOT NULL,
    text            TEXT NOT NULL,
    speaker         TEXT NOT NULL,              -- TEACHER | STUDENT | UNKNOWN
    language_spans  JSONB,                      -- [{start,end,lang:"hi"|"en"}]
    confidence      REAL
);
CREATE INDEX ON utterance (recording_id, start_s);

CREATE TABLE deixis (
    id              TEXT PRIMARY KEY,
    recording_id    TEXT NOT NULL REFERENCES recording(id),
    at_s            REAL NOT NULL,
    utterance_id    TEXT REFERENCES utterance(id),
    phrase          TEXT,
    board_region    JSONB NOT NULL,             -- {x,y,w,h} normalized 0–1
    kind            TEXT,                       -- point|circle|underline|sweep|write
    referent_text   TEXT,                       -- back-filled after GLYPH
    confidence      REAL
);

CREATE TABLE beat (
    id              TEXT PRIMARY KEY,
    recording_id    TEXT NOT NULL REFERENCES recording(id),
    idx             INT NOT NULL,
    start_s         REAL NOT NULL, end_s REAL NOT NULL,
    kind            TEXT NOT NULL,              -- explain|derive|example|question|
                                                -- recap|aside|admin
    board_state_id  TEXT,
    board_delta     JSONB,
    salience        REAL,
    transcript      TEXT NOT NULL,              -- denormalized, for embedding
    UNIQUE (recording_id, idx)
);
CREATE INDEX ON beat (recording_id, start_s);

-- ══════════════════════════ L2 · THE LEDGER ════════════════════════
-- Board state over time. Bitemporal range queries.

CREATE TABLE board_state (
    id              TEXT PRIMARY KEY,
    recording_id    TEXT NOT NULL REFERENCES recording(id),
    idx             INT NOT NULL,
    valid_from_s    REAL NOT NULL,
    valid_to_s      REAL NOT NULL,
    composited_uri  TEXT NOT NULL,              -- gs://.../board/{id}.png
    unfilled_uri    TEXT,                       -- gs://.../board/{id}_holes.png
    ink_coverage    REAL,
    homography      JSONB,
    ended_by        TEXT,                       -- erase | shot_cut | end_of_video
    ledger_version  INT NOT NULL DEFAULT 1
);
CREATE INDEX ON board_state (recording_id, valid_from_s, valid_to_s);

CREATE TABLE board_region (
    id              TEXT PRIMARY KEY,
    board_state_id  TEXT NOT NULL REFERENCES board_state(id),
    bbox            JSONB NOT NULL,             -- normalized board coords
    kind            TEXT NOT NULL,              -- equation|text|figure|table|unreadable
    latex           TEXT,
    plain_text      TEXT,
    description     TEXT,                       -- for figures
    role            TEXT,                       -- problem_statement|derivation_step|
                                                -- definition|answer|worked_example
    step_index      INT,
    derives_from    TEXT REFERENCES board_region(id),
    confidence      REAL
);

-- ══════════════════════════ L3 · THE ATLAS ═════════════════════════
-- Semantic. Versioned. Cheap to rebuild. Every row cites the Reel.

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
    edge_type       TEXT NOT NULL,              -- REQUIRES|PART_OF|EXEMPLIFIES|
                                                -- CONTRASTS_WITH
    weight          REAL DEFAULT 1.0,
    atlas_version   INT NOT NULL DEFAULT 1
);
CREATE INDEX ON concept_edge (from_concept, edge_type);
CREATE INDEX ON concept_edge (to_concept,   edge_type);

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

-- ★ THE PROVENANCE TABLE. This is the invariant.
CREATE TABLE beat_ref (
    id              BIGSERIAL PRIMARY KEY,
    subject_kind    TEXT NOT NULL,              -- concept|edge|misconception
    subject_id      TEXT NOT NULL,
    beat_id         TEXT NOT NULL REFERENCES beat(id),
    relation        TEXT NOT NULL,              -- taught_in|mentioned_in|evidence_for
    atlas_version   INT NOT NULL DEFAULT 1
);
CREATE INDEX ON beat_ref (subject_kind, subject_id);

-- Enforced in CI by evals/e4_provenance_invariant.py:
--   every concept, edge and misconception row has ≥1 beat_ref.

-- Human corrections always win and survive every re-run.
CREATE TABLE human_override (
    id              TEXT PRIMARY KEY,
    target_table    TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    field           TEXT NOT NULL,
    value           JSONB NOT NULL,
    author          TEXT, note TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ══════════════════════════ THE INDEX ══════════════════════════════
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE embedding (
    id              TEXT PRIMARY KEY,
    kind            TEXT NOT NULL,              -- beat|concept|board_region
    ref_id          TEXT NOT NULL,
    recording_id    TEXT,
    vec             vector(3072) NOT NULL,
    text            TEXT NOT NULL
);
CREATE INDEX ON embedding USING hnsw (vec vector_cosine_ops);
```

---

## 4. The core algorithms

### 4.1 Ink curve and erase detection (PULSE)

```python
# shruti/stages/pulse/ink.py
import cv2, numpy as np

def binarize_ink(board_bgr: np.ndarray, polarity: str) -> np.ndarray:
    """polarity: 'bright_on_dark' (chalk) | 'dark_on_bright' (marker)"""
    g = cv2.cvtColor(board_bgr, cv2.COLOR_BGR2GRAY)
    g = cv2.GaussianBlur(g, (3, 3), 0)
    flag = (cv2.THRESH_BINARY if polarity == "bright_on_dark"
            else cv2.THRESH_BINARY_INV)
    ink = cv2.adaptiveThreshold(
        g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, flag,
        blockSize=25, C=-8 if polarity == "bright_on_dark" else 8,
    )
    # Chalk dust and marker ghosting are speckle. Opening removes them.
    return cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))


def ink_curve(sampled, quad, polarity) -> np.ndarray:
    return np.array([
        binarize_ink(rectify(f, quad), polarity).sum() / 255
        for f in sampled
    ])
```

```python
# shruti/stages/pulse/erase.py
def find_erase_events(curve, times, drop_ratio=0.35, window_s=3.0):
    """
    An erase is a sustained ink LOSS. A teacher standing in front of the
    board also drops the count — but transiently and it recovers. Require
    the low value to PERSIST past the window, which rejects occlusion.
    """
    events, dt = [], times[1] - times[0]
    w = max(2, int(window_s / dt))

    for i in range(w, len(curve) - w):
        before = curve[i - w : i].max()
        after  = curve[i : i + w].min()
        if before <= 0:
            continue
        if (before - after) / before < drop_ratio:
            continue
        # Persistence check — this is what separates erase from occlusion
        tail = curve[i + w : i + 3 * w]
        if len(tail) and tail.mean() > after * 1.6:
            continue                                    # recovered ⇒ occlusion
        events.append(EraseEvent(at_s=times[i], before=before, after=after))

    return dedupe_within(events, min_gap_s=10.0)
```

That persistence check is worth reading twice. Without it, every time the teacher walks in front of the board you create a spurious board state, and a 45-minute lecture yields 200 states instead of 15.

### 4.2 Board compositing (SLATE) — the heart of the system

```python
# shruti/stages/slate/composite.py
import numpy as np
from .photometric import match_local

def composite_board_state(frames, masks, target_idx, span_start, span_end,
                          photometric=True):
    """
    Recover the most complete view of one board state.

    Key property: within a state, board content only GROWS (it is only
    removed at an erase, which is where the state ends). So the target is
    the last frame before the erase, and later frames within the state are
    strict supersets — search forward first.

    Returns (composited_bgr, unfilled_mask).
    unfilled_mask is regions never visible. GLYPH must be told about them.
    """
    target   = frames[target_idx].copy()
    unfilled = masks[target_idx].astype(bool).copy()

    def donate(i):
        nonlocal unfilled, target
        can = unfilled & ~masks[i].astype(bool)
        if not can.any():
            return
        patch = frames[i]
        if photometric:
            patch = match_local(patch, target, can)   # kill lighting seams
        target[can] = patch[can]
        unfilled &= ~can

    for i in range(target_idx + 1, span_end):          # forward: supersets
        donate(i)
        if not unfilled.any(): break

    if unfilled.any():
        for i in range(target_idx - 1, span_start - 1, -1):   # backward fallback
            donate(i)
            if not unfilled.any(): break

    return target, unfilled
```

### 4.3 Person masking, tier V1 (CPU, no GPU)

```python
# shruti/stages/slate/mask.py
import cv2, numpy as np

def framediff_masks(frames, quad, dilate_px=12):
    """
    V1 masking. Static camera + planar board ⇒ a temporal median over the
    whole state is a good background estimate, and the teacher is the
    largest thing that deviates from it.

    ~80% quality for zero GPU. Ship this. SAM 3 is the upgrade, not the start.
    """
    rect = [rectify(f, quad) for f in frames]
    bg   = np.median(np.stack(rect[::3]), axis=0).astype(np.uint8)
    bg_g = cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY)

    masks = []
    for f in rect:
        d = cv2.absdiff(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), bg_g)
        _, m = cv2.threshold(d, 32, 255, cv2.THRESH_BINARY)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))

        # Keep only the largest blob — that's the teacher. New writing also
        # deviates from bg but is thin and fragmented, so it loses.
        n, lbl, stats, _ = cv2.connectedComponentsWithStats(m, 8)
        out = np.zeros_like(m, bool)
        if n > 1:
            k = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
            if stats[k, cv2.CC_STAT_AREA] > 0.01 * m.size:
                out = (lbl == k)
        masks.append(cv2.dilate(out.astype(np.uint8),
                                np.ones((dilate_px, dilate_px), np.uint8)).astype(bool))
    return masks
```

**Upgrade path to V3, when you have a GPU:**

```python
# shruti/stages/slate/mask.py  (tier: sam3)
from transformers import Sam3VideoModel, Sam3VideoProcessor

_model = Sam3VideoModel.from_pretrained("facebook/sam3").to("cuda", dtype=torch.bfloat16)
_proc  = Sam3VideoProcessor.from_pretrained("facebook/sam3")

def sam3_masks(frames):
    """Text prompt 'person'. PCS returns stable IDs tracked across frames —
       which is the 'occlusion mask over time' problem, solved directly."""
    sess = _proc.init_video_session(video=frames, device="cuda")
    return _proc.propagate(sess, text="person")
```

Same signature. Swap by config flag. No other code changes.

### 4.4 Beat boundaries (WEAVE)

```python
# shruti/stages/weave/boundaries.py
def candidate_boundaries(utterances, ink_curve, times, shots) -> list[float]:
    """Three independent signals, unioned, then merged within 2s."""
    b = set()

    # 1. Speech pauses > 1.5s
    for a, c in zip(utterances, utterances[1:]):
        if c.start_s - a.end_s > 1.5:
            b.add((a.end_s + c.start_s) / 2)

    # 2. Ink-curve inflections — writing starts or stops
    d = np.gradient(ink_curve)
    for i in range(1, len(d) - 1):
        if np.sign(d[i-1]) != np.sign(d[i+1]) and abs(d[i-1] - d[i+1]) > INFLECT:
            b.add(times[i])

    # 3. Shot boundaries
    b.update(s.start_s for s in shots)

    return merge_within(sorted(b), 2.0)
```

Then a Gemini pass merges over-segmented candidates into semantically coherent beats and labels `kind` and `salience`. Deterministic where possible, LLM only for judgement.

---

## 5. Prompts

### 5.1 `prompts/glyph_read_board.md`

```markdown
You are reading a photograph of a {surface_kind} from a {grade} {subject} lesson
on "{chapter}".

CONTEXT (use to resolve ambiguous handwriting, never to invent content)
Teacher said during this board state:
{transcript_excerpt}

CRITICAL — OCCLUSION
The second image is an occlusion mask. WHITE regions were never visible in the
source video because the teacher stood there the whole time.
For any region overlapping white: emit kind="unreadable" with a reason.
DO NOT infer, complete, or guess occluded content. A missing region is correct.
An invented region is a serious error.

TASK
Return the board as a list of layout regions with normalized coordinates
(0–1, origin top-left of the rectified board).

For each region:
- bbox        [x, y, w, h]
- kind        equation | text | figure | table | diagram | unreadable
- latex       LaTeX, for equations. Preserve the teacher's exact form.
              If they wrote (x+3)² − 9 + 5, do NOT simplify to (x+3)² − 4.
- plain_text  for text regions
- description for figures — what it depicts and what is labelled
- role        problem_statement | derivation_step | definition | answer |
              worked_example | side_note | heading
- step_index  for derivation_step, the order (1-based)
- derives_from  region id this step follows from, if visible
- confidence  0–1

RULES
1. Preserve the teacher's notation and their order of operations exactly.
2. Read top-to-bottom, left-to-right, then column by column.
3. Multi-line derivations are SEPARATE regions linked by derives_from,
   not one region.
4. If a symbol is genuinely ambiguous, pick the reading the context supports
   and lower confidence below 0.7.
```

### 5.2 `prompts/atlas_misconceptions.md`

```markdown
Find every point where the teacher PRE-EMPTED a student error.

Teachers do this constantly and explicitly. Signals include:
  "yahan sab galti karte hain"      "this is where everyone goes wrong"
  "don't confuse this with…"        "yaad rakhna, X is NOT Y"
  "common mistake"                   "मत भूलना"
  ...and any construction that names a wrong belief in order to correct it.

For each, return:
- statement              the wrong belief, stated plainly and generally
                         ("treats (a+b)² as a²+b²")
- teacher_phrasing       their exact words, in their script
- correct_understanding  the correction, as they gave it
- beat_id                where it happened
- board_region_id        if they pointed at something
- severity               high | medium | low

RULES
1. Only include errors the teacher NAMED. Do not infer likely errors.
2. `statement` must be general enough to test a student against later —
   not "he said not to write x²+9" but "treats (a+b)² as a²+b²".
3. Preserve `teacher_phrasing` verbatim, code-mixing intact. The tutor will
   reuse the teacher's own words when remediating, and that familiarity is
   the point.
```

### 5.3 Structured output binding

```python
# shruti/gemini/client.py
async def extract(prompt: str, schema: dict, parts: list, model: str):
    """Constrained decoding. The paper measured relation-extraction F1
       collapsing 76% → 18% without format enforcement. Schema is
       load-bearing, not decoration."""
    return await client.models.generate_content(
        model=model,
        contents=parts + [prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            cached_content=SCHEMA_CACHE_NAME,   # 10% of input rate
        ),
    )
```

---

## 6. Batch API

Every SHRUTI call is offline. There is never a user waiting. That's a free 50%.

```python
# shruti/gemini/batch.py
async def run_batch(requests: list[BatchRequest], model: str) -> list[dict]:
    """
    Collect a whole recording's LLM work into ONE batch job.
    A 45-min lecture is ~70 calls: 15 GLYPH, 40 POINT, 3 ATLAS, ~12 misc.
    One job, half price, minutes not hours in practice.
    """
    jsonl = "\n".join(r.to_jsonl() for r in requests)
    up  = await client.files.upload(jsonl, mime_type="application/jsonl")
    job = await client.batches.create(model=model, src=up.name)

    while (job := await client.batches.get(job.name)).state in ("PENDING", "RUNNING"):
        await asyncio.sleep(20)

    return await collect(job)
```

**Route by urgency:** ECHO, GLYPH, POINT, WEAVE, ATLAS → batch. Only GATE's surface classifier is synchronous, because the pipeline branches on it.

---

## 7. LENS — the handoff to the tutor

This is the seam between SHRUTI and the live Nityam tutor. Get it right and the two halves are one product.

```python
# shruti/lens/adk_tools.py
from google.adk.tools import FunctionTool

async def recall_lesson(concept: str, student_id: str) -> dict:
    """Retrieve how THIS student's own teacher taught this concept.
       Returns board image, teacher's exact words, timestamp, notation."""
    rec = await enrolled_recordings(student_id)
    beats = await lens.timeline_lookup(concept, recordings=rec)
    if not beats:
        return {"found": False, "fallback": "generic"}
    b = beats[0]
    return {
        "found": True,
        "recording_id": b.recording_id,
        "timestamp": b.start_s,
        "teacher_words": b.transcript,
        "board_image_uri": await ledger.image_at(b.recording_id, b.start_s),
        "board_regions": await ledger.regions_at(b.recording_id, b.start_s),
        "notation_style": b.notation_hints,
    }

async def prerequisites_of(concept: str, depth: int = 2) -> list[dict]:
    """Multi-hop REQUIRES traversal. Recursive CTE, single-digit ms."""
    return await lens.graph_traverse(concept, "REQUIRES", depth)

async def known_misconceptions(concept: str) -> list[dict]:
    """Errors THIS teacher explicitly warned about, with their phrasing.
       The tutor probes for these before the student makes them."""
    return await atlas_store.misconceptions_for(concept)

async def board_at(recording_id: str, t: float) -> dict:
    """What was written at second t. Bitemporal range query on the Ledger."""
    return await ledger.state_at(recording_id, t)

LESSON_TOOLS = [FunctionTool(f) for f in
                (recall_lesson, prerequisites_of, known_misconceptions, board_at)]
```

Register `LESSON_TOOLS` on the `TeachAgent` from the main architecture doc, and the tutor becomes classroom-grounded with no other change.

**`known_misconceptions` is the one to demo.** Every other AI tutor finds a misconception *after* the student trips on it. Nityam knows it beforehand, in the teacher's own words, because it watched the class.

---

## 8. Task runner

```makefile
# justfile
ingest url title:            # full pipeline from a URL
    uv run shruti ingest "{{url}}" --title "{{title}}"

stage recording_id name:     # re-run ONE stage against cached upstream
    uv run shruti stage {{name}} --recording {{recording_id}}

timeline recording_id:       # the sense-style debug view. Use it constantly.
    duckdb data/shruti.duckdb "SELECT * FROM v_timeline WHERE recording_id='{{recording_id}}'"

board recording_id idx:      # open a composited board state
    uv run shruti board {{recording_id}} {{idx}} --open

atlas recording_id:          # print the concept graph as a tree
    uv run shruti atlas {{recording_id}} --format tree

reatlas recording_id:        # rebuild L3 only. Cheap. Do this fifty times.
    uv run shruti stage atlas --recording {{recording_id}} --bump-version

cost recording_id:
    uv run shruti cost {{recording_id}}

eval:
    uv run pytest evals/ -v

up:
    docker compose -f docker/compose.yaml up -d
```

The DuckDB timeline view is the highest-leverage debugging tool in the repo — that's the one genuinely excellent idea in the `sense` skill file:

```sql
CREATE OR REPLACE VIEW v_timeline AS
SELECT
    b.recording_id,
    b.idx,
    printf('%02d:%05.2f', CAST(b.start_s/60 AS INT), b.start_s % 60) AS tc,
    b.kind,
    CASE WHEN bs.id IS NOT NULL THEN '📋' ELSE '  ' END ||
    CASE WHEN EXISTS (SELECT 1 FROM deixis d
                      WHERE d.at_s BETWEEN b.start_s AND b.end_s) THEN '👉' ELSE '  ' END
                                                                   AS signals,
    substr(b.transcript, 1, 70)                                    AS said,
    (SELECT string_agg(c.canonical_name, ', ')
       FROM beat_ref r JOIN concept c ON c.id = r.subject_id
      WHERE r.beat_id = b.id AND r.subject_kind = 'concept')       AS concepts
FROM beat b LEFT JOIN board_state bs ON bs.id = b.board_state_id
ORDER BY b.recording_id, b.start_s;
```

---

## 9. Build order

**Day 1 — the spine, on real footage.**
1. GATE: yt-dlp → ffprobe → ffmpeg normalize → sha256. Surface classifier.
2. PULSE: PySceneDetect + ink curve + erase detection.
3. **Plot the ink curve for a real Indian classroom video and look at it.**
   If erase events don't line up with actual erases, nothing downstream works.
   Tune here, not later.

**Day 2 — the board. Highest risk.**
4. SLATE locate + rectify. Verify the rectified board is square and stable.
5. SLATE V1 masking + compositing. **Look at the output images.**
6. GLYPH on one composited state. Compare against what you can see yourself.

**Day 3 — speech and fusion.**
7. ECHO with the code-mix prompt. Test on genuinely mixed audio, not clean English.
8. WEAVE. Print `v_timeline` and read it end to end. It should read like lecture notes.
9. POINT — deixis on ~20 gesture moments.

**Day 4 — semantics and storage.**
10. ATLAS: concepts → relations → misconceptions.
11. VAULT: all four layers, with the provenance invariant enforced.
12. LENS + the four ADK tools.

**Day 5 — orchestration and cost.**
13. Wire the ADK `SequentialAgent`; durable state; resume-from-stage.
14. Batch API for everything; context caching on schemas.
15. Cloud Run deploy via `agents-cli`.

**Day 6 — evidence.**
16. E1–E4. E4 (provenance) goes into CI.
17. The demo: upload a real lecture → watch beats appear → ask the tutor a question → it answers with the teacher's board image and the teacher's own words.

### If you're behind

Cut in this order: POINT (deixis) → misconception mining → SAM 3 → the graph layer (ship vector-only retrieval) → multi-lecture merge.

**Never cut:** the ink curve, board compositing with the `unfilled` mask, the code-mix transcript prompt, and the provenance invariant. Those four are what make this SHRUTI rather than a wrapper around a video model.

---

## 10. The demo, three minutes

| t | Beat | What the judge sees |
|---|---|---|
| 0:00 | Paste a real Class 9 maths lecture URL | Ordinary input |
| 0:15 | Pipeline runs, stages light up | Ink curve plotted live — erase events visibly correct |
| 0:45 | **Split screen: raw frame vs composited board** | Teacher standing in front of an equation on the left; the equation *fully visible* on the right. **This is the moment.** |
| 1:15 | The timeline view | Beats, code-mixed transcript, concepts per beat |
| 1:40 | The concept graph | Click a node → jumps to 23:14 in the video. Provenance, live. |
| 2:00 | **Switch to the tutor.** Student: *"Sir ne completing the square kaise kiya tha?"* | Tutor answers using **the teacher's board image and the teacher's own words** |
| 2:30 | Tutor: *"Ek cheez, sir ne warn kiya tha — (x+3)² is not x²+9. Let's check you're clear on that."* | Misconception mined from the lecture, probed before the student errs |
| 2:50 | The invariant | Every claim traces to a second of a real class |

---

*Draft v0.1. Start at Day 1 step 3 — plot the ink curve on real footage before writing anything else. That single graph tells you whether the rest of the pipeline will work.*