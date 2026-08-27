# Memory Storage Testbed — Design Spec

**Status:** Cloud infrastructure provisioned and live-verified. Code not yet written — this spec
is what the implementation plan (`docs/superpowers/plans/`) will be built from.

**Spec this argues from:** `project_documentation/memory_nityam_architecture/memory_layer.md`
(v2.0) and `project_documentation/memory_nityam_architecture/google_cloud_storage_integration.md`
(v1.0) — the storage-tier decisions and per-service code patterns this testbed proves out. This
document doesn't re-litigate those decisions; it plans how to validate them in isolation before
`sub_modules_examples/tutor/app/memory/store.py` is rewritten for real.

---

## 1. Purpose

Prove, against **real** Google Cloud resources (not mocks, not unit-test doubles), that the
storage pattern documented in `google_cloud_storage_integration.md` actually works end to end —
Firestore for structured records + vector search, GCS for binary artifacts, Redis (standing in
for Memorystore) for the workflow-tier write-through — **before** touching the real `tutor`
module. This is explicitly a standalone proving ground: "if that is done properly, then I will be
integrating this with my main sub-modules" (your words). Nothing in `sub_modules_examples/tutor/`
changes as part of this work.

## 2. What's already done (cloud infrastructure)

Completed and live-verified in this session, ahead of any code:

| Resource | Value |
|---|---|
| GCP project | `nityam-506707` (billing already enabled, no new billing setup needed) |
| Firestore database | `smriti-testbed` — Native mode, `us-central1`, deliberately a **named, non-default** database so this testbed's data never mixes with whatever the real system creates in `(default)` later |
| GCS bucket | `gs://nityam-506707-memory-testbed` |
| IAM | Owner (`anmolsureka006@gmail.com`) — no permission gaps |
| Local Redis | Installed via Homebrew, running (`redis-cli ping` → `PONG`) — stands in for Memorystore per the "local dev, real Memorystore later" decision in `google_cloud_storage_integration.md` §5.4 |
| Live smoke test | A real document written to and read back from Firestore, a real object written to and read back from GCS, both via ADC — both services confirmed reachable, closing the open item in `google_cloud_storage_integration.md` §2/§7.1 |

APIs already enabled on the project (found during setup, not something this work turned on):
`firestore.googleapis.com`, `storage.googleapis.com`, `storage-api.googleapis.com`,
`storage-component.googleapis.com`, `aiplatform.googleapis.com`. `redis.googleapis.com`
(Memorystore itself) is **not** enabled — deliberately deferred per the design decision to test
against local Redis first.

## 3. Scope

**In scope**, three independent modules plus one combined demo:

| Module | Proves | Backing |
|---|---|---|
| `firestore_store.py` | CRUD for chunk/profile/memory/log-shaped documents; `array_contains_any` filtering; native vector field + `find_nearest()` semantic search | Real Firestore (`smriti-testbed` database) |
| `gcs_artifacts.py` | Save/read a binary blob via ADK's `GcsArtifactService` — the same mechanism `ArtifactAgent` will use for real | Real GCS (`nityam-506707-memory-testbed`) |
| `redis_shortterm.py` | The write-through turn-buffer pattern from `google_cloud_storage_integration.md` §5.3 — append, read-back, TTL, clear | Local Redis |
| `demo_end_to_end.py` | The real sequence: log turns → close session → write `session_log` + apply validated ops to a profile/memory record in Firestore → save an artifact to GCS → read everything back | All three together |

**Explicitly out of scope for this pass** (per the answered clarifying questions):
- Real Memorystore instance / VPC networking — local Redis is the stand-in; Memorystore itself is
  validated once there's a real Cloud Run deployment to attach it to.
- Vertex AI Search / Agent Search / Discovery Engine — the design already declined this for
  `grounding_chunk` retrieval (wrong grain); not being re-tested here.
- Real Shruti embeddings. The vector-search module uses **synthetic 1536-dimension test vectors**,
  not Shruti's real 3072-dim output — this testbed proves the Firestore vector-search *mechanism*,
  not compatibility with Shruti's actual embedder. The dimension-mismatch question
  (`google_cloud_storage_integration.md` §3.3) stays open, tracked separately, resolved when the
  real integration happens.
- Any change to `sub_modules_examples/tutor/`.

## 4. Package layout

```
sub_modules_examples/memory_storage_testbed/
├── AGENTS.md                    # what this proves, how to run it — same spirit as adk-samples' AGENTS.md
├── pyproject.toml               # own venv, own deps — no dependency on tutor's package
├── .env.example                 # GCP_PROJECT, FIRESTORE_DATABASE, GCS_BUCKET, REDIS_HOST
├── testbed/
│   ├── __init__.py
│   ├── schemas.py                # minimal standalone Pydantic shapes — NOT imported from
│   │                              #   tutor/app/memory/schemas.py; this package proves the
│   │                              #   storage pattern, not the exact production schema
│   ├── firestore_store.py
│   ├── gcs_artifacts.py
│   ├── redis_shortterm.py
│   └── demo_end_to_end.py
└── tests/
    ├── conftest.py                # fixtures: skip cleanly (not fail) when credentials/local
    │                              #   Redis aren't reachable, so `uv run pytest` never hard-fails
    │                              #   in an environment without cloud access
    ├── test_firestore_store.py
    ├── test_gcs_artifacts.py
    ├── test_redis_shortterm.py
    └── test_demo_end_to_end.py
```

Standalone, not imported into `tutor` — matches how `sub_modules_examples/` already holds
reference/example modules (`adk`, `shruti`, `artifact_generator`, `canvas`) alongside the real
`tutor` build.

## 5. Design decisions carried in from `google_cloud_storage_integration.md`

- **`firestore_store.py`'s function shapes mirror `store.py`'s real functions** (`put_grounding_chunk`,
  `search_grounding`, `search_grounding_semantic`, `get_dpm`, `put_dpm`, `get_teaching_memory`,
  `put_teaching_memory`, `put_session_log`, `get_session_log`) — same names, same call shape —
  so that porting this into the real `store.py` later is closer to a copy than a rewrite.
- **`gcs_artifacts.py` uses `GcsArtifactService` + `tool_context.save_artifact`**, not a raw GCS
  client — proving the actual ADK-native mechanism `ArtifactAgent` will use, not just "GCS works."
- **`redis_shortterm.py` is the write-through mirror pattern**, not a `BaseSessionService` swap —
  same reasoning as `google_cloud_storage_integration.md` §5.2 (lower risk, doesn't touch ADK's
  own session bookkeeping).
- **Every module's tests skip (not fail) when their backing resource is unreachable** — this
  testbed is meant to be run against real cloud resources by hand as the primary signal, with
  `pytest` as a repeatable regression check for whoever has credentials configured, not a CI gate
  that assumes cloud access always exists.

## 6. What "done" looks like

- `uv run pytest` passes (or cleanly skips where credentials aren't present) in the testbed's own venv.
- `uv run python -m testbed.demo_end_to_end` run by hand against the real `nityam-506707`
  resources, printing each step's result — a session log actually appears in the Firestore console,
  an artifact actually appears in the GCS bucket, the Redis buffer actually round-trips.
- A short `AGENTS.md` in the testbed package stating what was proven, what wasn't (the embedding
  dimension question, real Memorystore), and what to change when porting into `store.py` for real.

## 7. Self-review

- **Placeholders:** none — every module/file above has a concrete purpose, not a "TBD."
- **Internal consistency:** the module list in §3 and the file tree in §4 match 1:1.
- **Scope:** deliberately narrow — three storage backends, synthetic data, no agent framework
  wiring beyond `GcsArtifactService`. Matches "don't do unnecessary things."
- **Ambiguity resolved:** "agentic vector search" (originally ambiguous between Firestore's native
  vector field and Vertex AI Search) was explicitly disambiguated via clarifying question — Firestore
  native, confirmed.
