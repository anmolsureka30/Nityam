# Google-Managed Storage — Research & Integration Plan (v1.0)

**Mandate this document answers:** no tier of SMRITI (Nityam's memory layer) stays in SQLite or
any other local/self-hosted database. Every tier moves onto a Google-managed service, with no
added latency on the live voice path, while every existing constraint in `memory_layer.md`
(citation provenance, validated-operations-only writes at `close_session`, three tiers) stays
exactly as designed. This document is the research record and the concrete "what changes in
which file" plan; `memory_layer.md` §5 carries the short version and is the one to re-read day to
day. `deferred.md`'s existing note on Memory Bank is superseded by the fuller verdict below.

**Scope boundary, stated explicitly because it wasn't asked but matters:** this covers SMRITI —
`grounding_chunk`, `dpm_profile`, `teaching_memory`, `session_log`, and the workflow-tier turn
buffer. It does **not** cover Shruti's own vault (its graph store, its own embedding index) —
`memory_layer.md` §2.1 already draws that boundary ("retrieval fusion... stays Shruti's own
implementation") and this document doesn't touch it. If "none of it stays local" was meant to
include Shruti's vault too, that's a separate, larger piece of work — flagging rather than
assuming.

---

## 1. The verdict, up front

| Service | Verdict | Used for |
|---|---|---|
| **Firestore** | **Adopt** | Episodic tier (`session_log`) + long-term tier (`grounding_chunk`, `dpm_profile`, `teaching_memory`), including vector search over `grounding_chunk` |
| **Cloud Storage (GCS)** | **Adopt** | Binary artifacts — `ArtifactAgent` outputs, any images/audio blobs, via ADK's built-in `GcsArtifactService` |
| **Memorystore (Redis)** | **Adopt** | Workflow tier — the live turn buffer, as a write-through mirror alongside ADK's own `session.state` |
| **Vertex AI Memory Bank** (`VertexAiMemoryBankService`) | **Decline** | LLM-consolidated facts have no mechanism to carry a `session_id#turn` evidence pointer through consolidation — the exact gap `memory_layer.md` §6 already found against Gemini Enterprise's Memory Bank. Confirmed again below against the current Vertex AI product. |
| **Vertex AI Search / Agent Search** (`VertexAiSearchTool`, Discovery Engine) | **Decline** | Built for coarse, unstructured-document retrieval via a managed GCS connector. `grounding_chunk` is already precisely chunked and metadata-tagged by Shruti; routing it through Discovery Engine would re-ingest content Shruti already processed, through a coarser pipeline, losing `concept_ids`/`location`. |
| **Vertex AI Vector Search 2.0** | **Decline** | Same reasoning as Agent Search, plus a KFP-pipeline + Collection infrastructure footprint that Firestore's native vector field makes unnecessary at our chunk volume. |

---

## 2. Auth and prerequisites — what actually needs to change

The project currently runs on **Vertex AI Express Mode**: `GOOGLE_GENAI_USE_VERTEXAI=TRUE`,
`GOOGLE_GENAI_USE_ENTERPRISE=TRUE`, `GOOGLE_API_KEY=<express-mode-key>`, no project/location
(`sub_modules_examples/tutor/.env` — moved from `sub_modules/tutor/` in a teammate's rename,
`c506af0`; file paths in this document use the current location throughout). Confirmed live,
three separate findings:

1. **`VertexAiSessionService` and `VertexAiMemoryBankService` both work under the existing
   Express Mode key as-is** — `adk.dev`'s own express-mode integration page states project and
   location are not required for either when initializing under Express Mode. (Moot for Memory
   Bank since we're declining it, but relevant if `VertexAiSessionService` is ever reconsidered —
   see `memory_layer.md` §5's note on why it isn't the default.) Quotas on the free tier: 10
   session create/delete/update ops/min, 30 append-to-session ops/min, 10 memory ops/min.
2. **Express Mode cannot deploy the agent itself to Agent Runtime** — that needs a billing
   account on the project, unrelated to which storage backend we pick.
3. **Firestore, Cloud Storage, and Memorystore are silent in Express Mode's own docs** — they are
   general-purpose GCP products, not "Agent Platform" services, and every reference implementation
   found (the ADK Firestore codelab, `GCSCredentialsConfig`, `GcsArtifactService`) authenticates
   via Application Default Credentials (`google.auth.default()`) or a service account — not the
   Express Mode API key. Treat this as **needing a live smoke test before committing**, not a
   settled fact either way.

**What this means concretely:** Express Mode already runs on a real (if hidden) GCP project — it
is not a separate, throwaway sandbox. Adding a billing account attaches to *that same project*
(confirmed: express-mode projects get migrated into an "express-mode" org folder on graduation,
keeping the same project identity), after which `serviceusage.services.enable` (available to the
project Owner) turns on the Firestore, Cloud Storage, and Memorystore APIs. **No new project, no
credential migration for the model-serving path** — the Express Mode key keeps working for
`VoiceAgent`/`TutorAgent`/`ArtifactAgent`'s Gemini calls unchanged. What's added is a *second*,
separate credential path — ADC or a service account key — used only by the storage clients
(`firestore.Client`, the GCS client underneath `GcsArtifactService`, and Memorystore's IAM/network
auth). Two auth mechanisms coexisting is normal here, not a sign of an inconsistent setup.

**Action before writing any storage code:**
```bash
gcloud auth application-default login
python3 -c "
from google.cloud import firestore
db = firestore.Client(project='<the express-mode project id>')
db.collection('_smoke_test').document('x').set({'ok': True})
print(db.collection('_smoke_test').document('x').get().to_dict())
"
```
If this fails on project/permissions, the Firestore/Storage/Memorystore APIs need enabling
(Console → APIs & Services, or `gcloud services enable firestore.googleapis.com
storage.googleapis.com redis.googleapis.com`) and billing needs to be attached first.

---

## 3. Firestore — episodic + long-term tiers

### 3.1 Why Firestore closes the gap Memory Bank couldn't

Confirmed directly from an official Google ADK codelab ("Personal Expense Assistant") doing
close to our exact shape: Firestore used as a **general application datastore for structured
records** (not just ADK session state), with **native vector-field support** for semantic search
over those same documents (`find_nearest()`, Euclidean/cosine distance). That combination —
structured records *and* embedding search, in one service, with strong consistency and per-field
`update()` — is what lets one service replace SQLite for all three of `grounding_chunk`,
`dpm_profile`, and `teaching_memory` without also needing a separate vector-search product.

### 3.2 Collection layout

Mirrors the existing SQLite tables 1:1 — flat collections, no unnecessary subcollection nesting
(nothing here needs it: every read is either a direct key lookup or a `where`/`find_nearest`
query, both of which flat collections serve fine):

| Firestore collection | Document ID | Mirrors (SQLite table) |
|---|---|---|
| `grounding_chunks` | `chunk_id` | `grounding_chunk` + `grounding_chunk_concept` (the join table collapses — `concept_ids` becomes a plain array field, queried via `array_contains_any`) |
| `dpm_profiles` | `student_id` | `dpm_profile` |
| `teaching_memories` | `student_id` | `teaching_memory` |
| `session_logs` | `session_id` | `session_log` |

### 3.3 The embedding-dimension conflict — must be resolved before `grounding_chunk` writes

**Found, not yet resolved:** Firestore's vector index caps embedding dimension at **2048**.
Shruti's embedder is `gemini-embedding-001`, and per `README.md`'s corrections log, the project
already live-tested and settled on **3072-dimensional** output for Shruti's own index. 3072 >
2048 — writing Shruti's existing embedding vector straight into `grounding_chunk.embedding`
will fail Firestore's vector index.

`gemini-embedding-001` supports an explicit `output_dimensionality` parameter (Matryoshka
representation learning — truncate-then-renormalize, not a lossy hack) with 768/1536/3072 as the
commonly-used values. Two ways to resolve, in order of preference:

1. **Compute a second, smaller-dimension embedding specifically for `grounding_chunk.embedding`**
   at the point SMRITI writes the chunk (`output_dimensionality=1536` is a reasonable balance of
   recall and Firestore's cap — reconfirm against Firestore's current limit before committing, it
   may move). Shruti's own 3072-dim index is untouched — this is purely SMRITI's copy.
2. Ask Shruti to additionally emit a 1536-dim embedding alongside its 3072-dim one, if the
   ingestion pipeline is the more natural place to compute it once rather than SMRITI re-embedding
   chunk text a second time.

**This is a decision for you, not decided here** — flagging per the same reasoning `memory_layer.md`
already applies to schema/storage calls: it's a real compatibility blocker, not a style choice.

### 3.4 Enabling vector search (one-time infra step)

```bash
gcloud firestore indexes composite create \
  --collection-group=grounding_chunks \
  --query-scope=COLLECTION \
  --field-config field-path=embedding,vector-config='{"dimension":"1536","flat":{}}' \
  --project=<PROJECT_ID>
```

### 3.5 Code — `store.py` rewritten against Firestore, function-for-function

`sub_modules_examples/tutor/app/memory/store.py` is the **only** file that needs a real rewrite. Every
call site (`app/memory/tools.py`, `app/session_close.py`) calls `store.*` functions by name and
never touches `sqlite3.Connection` directly — so the migration is contained to this one file, with
the connection-object type changing from `sqlite3.Connection` to `firestore.Client`.

```python
"""One shared Firestore backing store for the memory layer — replaces the
SQLite implementation 1:1. Same function names/signatures as before, so
app/memory/tools.py and app/session_close.py need no changes.
"""
from __future__ import annotations

from google.cloud import firestore
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector

from app.memory.schemas import DPMProfile, GroundingChunk, SessionLog, TeachingMemory

EMBEDDING_DIM = 1536  # see google_cloud_storage_integration.md §3.3 — must stay <= Firestore's cap


def connect(project: str | None = None) -> firestore.Client:
    return firestore.Client(project=project)


def put_grounding_chunk(db: firestore.Client, chunk: GroundingChunk, embedding: list[float]) -> None:
    payload = chunk.model_dump(mode="json")
    payload["embedding"] = Vector(embedding)
    db.collection("grounding_chunks").document(chunk.chunk_id).set(payload)


def search_grounding(db: firestore.Client, concept_ids: list[str], limit: int = 5) -> list[GroundingChunk]:
    if not concept_ids:
        return []
    docs = (
        db.collection("grounding_chunks")
        .where("concept_ids", "array_contains_any", concept_ids)
        .limit(limit)
        .get()
    )
    return [GroundingChunk.model_validate({k: v for k, v in d.to_dict().items() if k != "embedding"}) for d in docs]


def search_grounding_semantic(db: firestore.Client, query_embedding: list[float], concept_ids: list[str] | None = None, limit: int = 5) -> list[GroundingChunk]:
    """Vector-similarity variant — use when a plain concept_id filter isn't
    precise enough (query text doesn't map cleanly to one concept_id)."""
    q = db.collection("grounding_chunks")
    if concept_ids:
        q = q.where("concept_ids", "array_contains_any", concept_ids)
    docs = q.find_nearest(
        vector_field="embedding",
        query_vector=Vector(query_embedding),
        distance_measure=DistanceMeasure.COSINE,
        limit=limit,
    ).get()
    return [GroundingChunk.model_validate({k: v for k, v in d.to_dict().items() if k != "embedding"}) for d in docs]


def get_dpm(db: firestore.Client, student_id: str) -> DPMProfile | None:
    doc = db.collection("dpm_profiles").document(student_id).get()
    return DPMProfile.model_validate(doc.to_dict()) if doc.exists else None


def put_dpm(db: firestore.Client, profile: DPMProfile) -> None:
    db.collection("dpm_profiles").document(profile.student_id).set(profile.model_dump(mode="json"))


def get_teaching_memory(db: firestore.Client, student_id: str) -> TeachingMemory | None:
    doc = db.collection("teaching_memories").document(student_id).get()
    return TeachingMemory.model_validate(doc.to_dict()) if doc.exists else None


def put_teaching_memory(db: firestore.Client, memory: TeachingMemory) -> None:
    db.collection("teaching_memories").document(memory.student_id).set(memory.model_dump(mode="json"))


def put_session_log(db: firestore.Client, log: SessionLog) -> None:
    db.collection("session_logs").document(log.session_id).set(log.model_dump(mode="json"))


def get_session_log(db: firestore.Client, session_id: str) -> SessionLog | None:
    doc = db.collection("session_logs").document(session_id).get()
    return SessionLog.model_validate(doc.to_dict()) if doc.exists else None
```

Notes on what's different from SQLite, deliberately:

- `put_grounding_chunk` now takes an explicit `embedding` argument — SQLite never stored vectors,
  so this is a genuinely new parameter, not a refactor. Whatever calls this (Shruti/book ingestion,
  per `memory_layer.md` §2.1) needs to pass the 1536-dim embedding from §3.3 alongside the chunk.
- `search_grounding` keeps the exact-match-on-`concept_ids` behavior the SQLite version had
  (`array_contains_any` is Firestore's equivalent of the old join-table `IN` query).
  `search_grounding_semantic` is new — added, not required to replace the old path, for the case
  a query doesn't cleanly resolve to known `concept_ids`.
- `app/memory/tools.py`'s `_conn()` cache and every `store.*(_conn(), ...)` call site keep working
  unchanged — only the type flowing through `_conn()` changes from `sqlite3.Connection` to
  `firestore.Client`, and `store.connect()`'s signature drops the `db_path` argument in favor of
  `project` (or takes none, relying on ADC's default project).
- `ops.py` needs **zero changes** — it only ever operates on already-loaded `DPMProfile`/
  `TeachingMemory` Pydantic objects, never touches the connection/client directly.
- `app/session_close.py`'s `close_session` needs **zero changes** — it already takes `conn` as a
  generic first parameter and only calls `store.*` functions through it.

### 3.6 Retention

Firestore has no default TTL. `memory_layer.md`'s existing "forever, append-once" intent for
`session_log` (and the other three record types) carries over unchanged — no TTL policy needed
unless you decide otherwise. If one is wanted later, it's a config change
(`gcloud firestore fields ttls update`), not a code or schema change.

---

## 4. Cloud Storage (GCS) — binary artifacts

Confirmed distinct from the `GCSToolset`/`GCSAdminToolset` covered in the attached doc — those are
**agent-callable tools** for an agent that autonomously browses/manages a bucket (not our use
case). What we actually want is `GcsArtifactService`, ADK's own **runtime artifact layer** —
transparent to the agent, invoked via `tool_context.save_artifact(...)`, no tool-calling involved.

```python
# app/agents/artifact_agent.py or wherever the Runner is constructed
from google.adk.artifacts import GcsArtifactService

artifact_service = GcsArtifactService(bucket_name="nityam-artifacts")

runner = Runner(
    agent=voice_agent,
    app_name="nityam",
    session_service=session_service,
    artifact_service=artifact_service,
)
```

Inside `ArtifactAgent`'s own tool (wherever it currently returns a generated HTML/diagram
reference — the exact call site is `sub_modules_examples/tutor/app/agents/artifact_agent.py`, not yet
re-read as part of this pass):

```python
from google.genai.types import Blob, Part

async def save_generated_artifact(html: str, artifact_id: str, tool_context: ToolContext) -> dict:
    part = Part(inline_data=Blob(mime_type="text/html", data=html.encode("utf-8")))
    version = await tool_context.save_artifact(filename=f"{artifact_id}.html", artifact=part)
    return {"artifact_id": artifact_id, "version": version}
```

Auth: same ADC/service-account path as Firestore (`google.auth.default()` under the hood).
IAM needs `storage.objects.{create,get,list,delete}` on the target bucket.

---

## 5. Memorystore (Redis) — workflow tier

### 5.1 What "short-term memory" maps to today

The workflow tier is **already implemented** — it's `tool_context.state["turn_buffer"]` /
`tool_context.state["artifact_events"]` in `app/memory/tools.py`'s `log_turn` /
`log_artifact_evidence`, an in-process dict proxy over ADK's own `Session.state`. This is not a
database and was designed to be ephemeral (`memory_layer.md` §1: "One session, ephemeral"). The
question this section resolves is how Memorystore fits in given that it already works and is
already free.

### 5.2 Decision: write-through mirror, not a session-service swap

Two ways to bring Memorystore in were considered:

- **(a) Swap ADK's own `session_service` for a custom `RedisSessionService(BaseSessionService)`,**
  so every `tool_context.state` mutation transparently persists to Redis with zero changes to
  `tools.py`. `BaseSessionService`'s four abstract methods are confirmed
  (`create_session`, `get_session`, `list_sessions`, `delete_session` — all `async`), but the
  exact persistence hook inside `append_event`'s default (concrete, non-abstract) implementation
  was **not** verified against the installed `google-adk==2.7.1` source as part of this research
  pass. Given this is the framework's own event-sourcing internals for a live, latency-sensitive
  voice path, getting that wrong risks corrupting or losing live conversation state — a strictly
  worse outcome than today. Not recommended as the default without that verification first
  (`architecture.md`'s own precedent: verify against installed source before relying on ADK
  internals, don't infer from docs alone).
- **(b) Keep `session_service=InMemorySessionService()` untouched, and have `log_turn` /
  `log_artifact_evidence` additionally write-through to Memorystore directly** — a small,
  self-contained addition to files we already own, zero risk to ADK's own bookkeeping. **This is
  the recommendation.**

The write-through is fire-and-forget from the live turn's perspective (a `redis.asyncio` call is
sub-millisecond against Memorystore — see §5.4 — and doesn't block on the LLM response), and gives
three things `tool_context.state` alone doesn't: a copy that isn't tied to one process's memory
(survives a worker restart within the TTL window), an inspectable/debuggable buffer outside the
live process, and — if `close_session` is ever invoked from a different process/worker than the
one that ran the live conversation — a real source for `buffer` to be read back from instead of
requiring it to be passed in from the same process.

### 5.3 Code

```python
# app/memory/short_term.py — new file
from __future__ import annotations

import json

import redis.asyncio as redis

from app import config

_client: redis.Redis | None = None


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis(host=config.REDIS_HOST, port=6379, decode_responses=True)
    return _client


async def append_turn(session_id: str, turn: dict) -> None:
    key = f"session:{session_id}:turns"
    client = get_client()
    await client.rpush(key, json.dumps(turn))
    await client.expire(key, 60 * 60 * 6)  # 6h safety-net TTL — close_session should flush well before this


async def append_artifact_event(session_id: str, event: dict) -> None:
    key = f"session:{session_id}:artifact_events"
    client = get_client()
    await client.rpush(key, json.dumps(event))
    await client.expire(key, 60 * 60 * 6)


async def get_turn_buffer(session_id: str) -> list[dict]:
    client = get_client()
    raw = await client.lrange(f"session:{session_id}:turns", 0, -1)
    return [json.loads(r) for r in raw]


async def clear_session(session_id: str) -> None:
    client = get_client()
    await client.delete(f"session:{session_id}:turns", f"session:{session_id}:artifact_events")
```

`app/memory/tools.py` changes — `log_turn`/`log_artifact_evidence` gain a write-through call
(the existing `tool_context.state` write stays, so the live turn's own context-building is
untouched):

```python
async def log_turn(text: str, role: str, concept_id: str, artifact_id: str, tool_context: ToolContext) -> dict:
    buffer = tool_context.state.get("turn_buffer", [])
    turn = {
        "turn": len(buffer) + 1,
        "role": role,
        "text": text,
        "concept_id": concept_id or None,
        "artifact_id": artifact_id or None,
    }
    buffer.append(turn)
    tool_context.state["turn_buffer"] = buffer
    await short_term.append_turn(tool_context.state["session_id"], turn)  # new
    return {"buffer_length": len(buffer)}
```

(`log_turn` becomes `async` — it currently isn't. Its caller in the ADK tool-dispatch path already
supports async tool functions natively, so this is a mechanical change, not a design one.)

Wherever `close_session(...)` is currently invoked (the Live connection's session-end trigger —
not yet re-read as part of this pass), the `buffer` argument can now be sourced from
`short_term.get_turn_buffer(session_id)` instead of `tool_context.state["turn_buffer"]` directly,
if that call happens outside the live conversation's own process; otherwise `tool_context.state`
remains simplest and Redis is purely the durability mirror.

### 5.4 Networking — the one genuinely new operational piece

Unlike Firestore/GCS (reachable directly over the public internet with ADC), **Memorystore has no
public IP — it's VPC-internal only**, confirmed directly from Google's own connectivity docs.
This is a real, new piece of infrastructure, not a config flag:

- **Local dev:** Memorystore cannot be reached directly from a laptop. Run a local Redis
  (`docker run -p 6379:6379 redis`) for dev, pointed at via `REDIS_HOST=localhost`; Memorystore is
  only used in deployed environments. This is a standard, expected pattern for Memorystore — not a
  workaround unique to us.
- **Deployed (Cloud Run):** connect via **Direct VPC egress** (Google's current recommendation —
  lower latency and cost than the older Serverless VPC Access connector), same region and VPC as
  the Memorystore instance. `REDIS_HOST` becomes the instance's private IP.
- Instance choice: **Memorystore for Valkey** (GA, Redis-API-compatible, includes Private Service
  Connect and cross-region replication) or **Memorystore for Redis** — either satisfies the code
  above unchanged, since `redis.asyncio` talks to both over the same wire protocol.

### 5.5 Pricing note

Memorystore bills **provisioned capacity** (~$0.049/GB-hr Basic tier, ~$0.098/GB-hr Standard/HA),
not per-operation — you pay for the instance whether or not it's busy, unlike Firestore's
per-operation billing. For a single small instance sized to a turn-buffer workload this is a small,
predictable cost, but it's a different cost shape than everything else in this document and worth
knowing going in.

### 5.6 Considered and declined: `redis-developer/adk-redis`

A Redis-maintained package implementing `BaseSessionService`/`BaseMemoryService` against Redis
exists (`github.com/redis-developer/adk-redis`). It was not adopted here because its managed
backend (`redis-agent-memory`) is a *separate hosted product* — "Redis Agent Memory Server" — with
its own `api_base_url`/`api_key`/`store_id`, not a direct TCP connection to a Memorystore instance.
Adopting it would mean running or subscribing to an additional service beyond Memorystore itself,
which the direct `redis.asyncio` approach in §5.3 avoids. Its self-hosted `opensource-agent-memory`
backend is closer to what we want but still an extra abstraction layer over what §5.3 already does
directly. Worth revisiting if the write-through approach outgrows a hand-rolled client.

---

## 6. Sources

- [Session State Management using Firestore (Java) — attached context doc](../../google-memory-storage-context.md)
- [Memory: Long-term knowledge with MemoryService — attached context doc](../../google-memory-storage-context.md)
- [Google Cloud Storage integration — attached context doc](../../google-memory-storage-context.md)
- [Grounding with Search for agents — attached context doc](../../google-memory-storage-context.md)
- `adk-samples` `core/python/cross-session-memory`, `core/python/rag-agent-search`,
  `core/python/rag-vector-search` — `AGENTS.md` files, cloned and read in full
- [Extending Google ADK: Building a Custom Session Service with Firestore](https://medium.com/google-cloud/extending-google-adk-building-a-custom-session-service-with-firestore-0fc4b74354bf)
- [FirestoreSessionService/VertexAiSessionService gap with agent engine — adk-java#497](https://github.com/google/adk-java/issues/497)
- [Vertex AI Memory Bank in public preview — Google Cloud Blog](https://cloud.google.com/blog/products/ai-machine-learning/vertex-ai-memory-bank-in-public-preview)
- [Generate memories — Vertex AI docs](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/memory-bank/generate-memories)
- [Agent Memory Head to Head — Sascha Heyer](https://medium.com/google-cloud/agent-memory-head-to-head-469fd1cb71a0)
- [Google Cloud Agent Platform express mode for ADK](https://adk.dev/integrations/express-mode/)
- [Google Cloud express mode FAQs](https://cloud.google.com/resources/cloud-express-faqs)
- [Search with vector embeddings — Firestore docs](https://docs.cloud.google.com/firestore/native/docs/vector-search)
- [Get started with Firestore vector similarity search — Google Cloud Blog](https://cloud.google.com/blog/products/databases/get-started-with-firestore-vector-similarity-search)
- [Going Multimodal with ADK: Personal Expense Assistant — Google Codelabs](https://codelabs.developers.google.com/personal-expense-assistant-multimodal-adk)
- [Artifacts — Agent Development Kit (ADK) docs](https://google.github.io/adk-docs/artifacts/)
- [GcsArtifactService discussion — google/adk-python#1775](https://github.com/google/adk-python/discussions/1775)
- [redis-developer/adk-redis](https://github.com/redis-developer/adk-redis)
- [Connect to a Redis instance from a Cloud Run service — Memorystore docs](https://docs.cloud.google.com/memorystore/docs/redis/connect-redis-instance-cloud-run)
- [Announcing general availability of Memorystore for Valkey](https://cloud.google.com/blog/products/databases/announcing-general-availability-of-memorystore-for-valkey/)
- [Memorystore for Redis Cluster pricing](https://cloud.google.com/memorystore/cluster/pricing)
- `google/adk-python` `src/google/adk/sessions/base_session_service.py` — abstract method
  signatures, read directly from source

---

## 7. Open items before implementation starts

1. **Live smoke test** (§2) — confirm Firestore/GCS/Memorystore reach under ADC on the express-mode
   project, before writing real code against them.
2. **Embedding dimension** (§3.3) — decide 1536 vs. another value ≤ 2048, and where it's computed
   (SMRITI re-embeds, or Shruti emits a second vector).
3. **`BaseSessionService` internals** (§5.2) — if crash-resilience of ADK's *own* session bookkeeping
   (not just our buffer) is ever wanted, verify `append_event`'s persistence hook against installed
   source before building a custom `RedisSessionService`. Not needed for the recommended path.
4. **`close_session` call site** — confirm where it's invoked today (not re-read in this pass) before
   deciding whether it needs the Redis-buffer read path from §5.3.

---

*v1.0. New document — companion to `memory_layer.md` v2.0 (see that file's changelog for the
storage-tier decision this document backs). Supersedes `deferred.md`'s implicit "Memory Bank, not
revisited" status with an explicit verdict covering Memory Bank, Agent Search, and Vector Search
2.0 together.*
