# Gemini Enterprise Agent Platform — Build pillar

Last verified: 2026-08-25, via live fetch of `docs.cloud.google.com/gemini-enterprise-agent-platform/*`, `adk.dev`, PyPI, and GitHub.

## The pillar's own framing

The [Build overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build) positions Build as "ADK/open-source frameworks (LangChain, LangGraph, AG2, LlamaIndex) + supporting managed services" — Vector Search, RAG Engine, Skill Registry, an Authentication Manager (3-legged OAuth, 2-legged OAuth, API key) — running on Gemini or third-party Model Garden models. Plain GCP primitives (Cloud SQL, pgvector, Pub/Sub) sit outside this pillar's vocabulary entirely — a design that only uses those is, by Google's own taxonomy, not "in" the Build pillar even if it's using ADK.

## Agent Development Kit (ADK)

The [ADK overview page](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/adk) itself is pure marketing — no code, no class names. Real technical detail lives at `build/runtime/quickstart-adk` and `build/runtime/create-an-adk-agent`, and at the OSS docs (`adk.dev`, redirected from the old `google.github.io/adk-docs`).

**Ground-truth check, all confirmed real and current (`google-adk` v2.7.1, released 2026-08-17, per [PyPI](https://pypi.org/project/google-adk/)):**

| Name | Status |
|---|---|
| `google.adk.agents.Agent` | Real — an alias that resolves directly to `LlmAgent` ([GitHub issue #1158](https://github.com/google/adk-python/issues/1158), [adk.dev/agents/llm-agents](https://adk.dev/agents/llm-agents/)) |
| `LlmAgent`, `SequentialAgent`, `ParallelAgent`, `LoopAgent` | Real, current "workflow agent" family for deterministic pipelines vs. LLM-driven dynamic routing ([adk.dev/agents/workflow-agents/parallel-agents](https://adk.dev/agents/workflow-agents/parallel-agents/)) |
| `google.adk.tools.FunctionTool`, `LongRunningFunctionTool` | Real. `LongRunningFunctionTool` is for tools that start async work and let the runner pause/resume on client polling of an operation id — directly relevant to any long CPU/GPU stage |
| `ToolContext` | Real — auto-injected into tool functions, exposes `state`, `actions`, `function_call_id` |
| `BasePlugin` (+ `before_model_callback`/`after_model_callback`) | Real. Caveat: **not invoked on the streaming path** — ADK only runs model callbacks on `run_async`, so a voice/streaming tutor agent can't rely on these for guardrails |
| `google.adk.models.Gemini` | Real — seen directly in Google's own sample: `model=Gemini(model="gemini-3.5-flash")` |
| `google.adk.sessions.DatabaseSessionService` | Real — SQLAlchemy-backed over SQLite/MySQL/**PostgreSQL**. Self-hosted, you own the infra |
| `google.adk.sessions.VertexAiSessionService` | Real — the managed counterpart; delegates storage to Agent Platform Sessions. **Interchangeable with `DatabaseSessionService` via a one-line constructor swap in the `Runner`/`AdkApp` setup** — no lock-in either direction |

**Deprecation/rename flags to check code against before the hackathon:**
- `vertexai.generative_models`, `.language_models`, `.vision_models`, `.tuning`, `.caching` — deprecated 2025-06-24, **removal date 2026-06-24 has already passed** as of today. Replace with the `google-genai` SDK.
- `vertexai.Client` → superseded by `agentplatform.Client`; `vertexai.rag` → superseded by `agentplatform.Client().rag`. Confirmed via [therouter.ai](https://therouter.ai/news/vertex-ai-sdk-migration-gemini-enterprise-agent-platform/) and [gcpstudyhub.com](https://gcpstudyhub.com/blog/vertex-ai-replaced-by-gemini-enterprise-agent-platform), consistent with the April 2026 rebrand.
- `vertexai.agent_engines` → slated to become `runtimes` in an upcoming major release ("not before 2026-07-31" — may already have shipped). Treat as short-lived naming; don't build against it long-term.
- Google's own current quickstarts still mix old and new import paths (mid-rebrand) — treat exact imports in official samples as correct-but-transitional, not stable API.

**CLI / deployment, confirmed real with exact syntax** (sources: [adk.dev/deploy/agent-runtime/agents-cli](https://adk.dev/deploy/agent-runtime/agents-cli/), [quickstart-adk](https://docs.cloud.google.com/gemini-enterprise-agent-platform/agents/quickstart-adk)):

```
agents-cli create caveman-agent --prototype --yes
agents-cli install
agents-cli run "..."
agents-cli eval run
agents-cli scaffold enhance --deployment-target cloud_run   # or: agent_engine | gke
agents-cli deploy
agents-cli infra single-project
```

`--deployment-target cloud_run` is an **officially documented, first-class path — not a workaround** — but it means the agent never touches Agent Runtime, managed Sessions, or platform telemetry. `--deployment-target agent_engine` is the one-flag change that puts the exact same agent code onto the actual managed Agent Runtime. Separately, plain OSS ADK also ships its own `adk deploy cloud_run` command (no `agents-cli`), a more "vanilla" route documented at `google.github.io/adk-docs/deploy/cloud-run`.

**Real deploy code** (from `build/runtime/quickstart-adk`):
```python
import vertexai
client = vertexai.Client(project="PROJECT_ID", location="LOCATION")

from google.adk.agents import Agent
from vertexai import agent_engines

agent = Agent(model="gemini-3.5-flash", name='currency_exchange_agent', tools=[get_exchange_rate])
app = agent_engines.AdkApp(agent=agent)

from vertexai import types
remote_agent = client.agent_engines.create(
    agent=app,
    config={
        "requirements": ["google-cloud-aiplatform[agent_engines,adk]"],
        "staging_bucket": "STAGING_BUCKET",
        "identity_type": types.IdentityType.AGENT_IDENTITY,
    }
)
```
Memory wiring shown on the same page: `google.adk.tools.preload_memory_tool.PreloadMemoryTool()` + `app.async_add_session_to_memory(session=...)`.

## Agent Studio

[Overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/agent-studio) — a console-based no/low-code visual builder: dual-pane code+preview canvas, NL system-instruction generation, prompt comparison, slash-command tool management. Model picker includes Gemini 3.1, "Nano Banana 2," Veo 3.1. Grounding options in the UI: RAG Engine, Agent Search, Elasticsearch, Google Search, Google Maps, Vertex AI Search. **No code samples or class names anywhere on the page — UI-only.** This is an authoring surface for conversational/chat agents, not a runtime; not a fit for a code-first CV/video batch pipeline.

## Agent Garden

[Overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/agent-garden) — a curated library of prebuilt agent samples. Only one template category is described in depth on the page: **RAG** ("factually grounded Q&A systems"). Deploy flow: pick a sample → configure project/region/model (example: Gemini 3 Flash) → Deploy via **Agents CLI** (direct, deploys to Agent Runtime), **Application Design Center** (low-code, full infra stack with dashboards/security), or **Agents CLI + Gemini Enterprise Registration** (deploys + registers for governance).

GitHub samples at [GoogleCloudPlatform/generative-ai/tree/main/gemini/agents](https://github.com/GoogleCloudPlatform/generative-ai/tree/main/gemini/agents) include `always-on-memory-agent` and `genai-experience-concierge` — both conversational patterns. **Nothing in the discoverable inventory matches a video/CV-ETL batch workload** — Agent Garden's RAG template assumes a text corpus already exists; it's downstream of what a video-extraction pipeline produces, not a substitute for it.

## Model Garden

[Explore models](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/model-garden/explore-models) — the model catalog/serving layer, which any Gemini-calling code already sits on regardless of the rest of the stack. Relevant entries: **Gemini Omni Flash** (explicitly audio/video-capable), **Gemini Robotics ER 2** (spatial reasoning + video understanding — potentially useful for board/gesture spatial tracking), Gemini 2.5 Flash Live API (real-time streaming — relevant to a live tutor, not a batch pipeline). Provisioned Throughput tiers: **Standard PayGo, Priority PayGo, Flex PayGo** — Flex is plausibly the right tier for a non-latency-sensitive batch workload; no rate figures were published on the page itself.

## RAG Engine

[Overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/rag-engine/rag-overview) — a managed six-stage pipeline: ingest → transform/chunk → embed → index (into a "corpus") → retrieve → generate. **It is a pipeline orchestrator, not a single proprietary vector store** — it can point its index at `RagManagedDb` (its own Spanner-backed default), Agent Platform Vector Search 2.0 ("Agent Retrieval"), Vector Search 1.0 (legacy), Feature Store, Weaviate, or Pinecone. So "RAG Engine vs. rolling your own pgvector" isn't apples-to-apples: RAG Engine replaces the *ETL/orchestration code* around a vector store (chunking config, embedding wiring, retrieval config, reranking, metadata filters), not necessarily the storage engine itself.

Real code (from `rag-quickstart`):
```python
import agentplatform
from agentplatform import types
client = agentplatform.Client(project=PROJECT_ID, location="us-east4")

rag_corpus = client.rag.create_corpus(rag_corpus=types.RagCorpus(
    display_name=display_name,
    rag_vector_db_config=types.RagVectorDbConfig(
        rag_embedding_model_config=types.RagEmbeddingModelConfig(
            vertex_prediction_endpoint=types.RagEmbeddingModelConfigVertexPredictionEndpoint(
                endpoint="publishers/google/models/text-embedding-005"))),
))
client.rag.import_files(name=rag_corpus.name, import_config=types.ImportRagFilesConfig(
    gcs_source=genai_types.GcsSource(uris=[gcs_path]),
    rag_file_transformation_config=types.RagFileTransformationConfig(
        rag_file_chunking_config=types.RagFileChunkingConfig(chunk_size=512, chunk_overlap=100)),
))
```
GA regions (allowlist required): `us-central1`, `us-east4`, `europe-west3`, `europe-west4`. Data residency/AXT not supported. **Pricing**: provisions a customer-specific Spanner backend — Basic tier 100 processing units, Scaled tier 1,000–10,000 units autoscaling; embedding/reranking/Document-AI calls billed at their own standard rates; default parsing + fixed-size chunking is free. ([billing page](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/rag-engine/rag-engine-billing))

**Fit note**: built for text Q&A grounding, chunk-shaped. Not a natural fit for frame-level/timestamp-ranged video segments carrying rich CV provenance (bounding boxes, confidence, extraction method, speaker id) — see the alignment doc for the actual recommendation on where this applies (if anywhere) in Nityam.

## Vector Search — two generations, not one product

**Vector Search 1.0** ([overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/vector-search/overview)) is confirmed to be the same ScaNN-based ANN engine previously branded "Vertex AI Vector Search"/Matching Engine — the page still surfaces legacy class names `MatchingEngineIndex`/`MatchingEngineIndexEndpoint`. Just re-branded under the new URL namespace, not rebuilt. Pricing: VM-hosting cost for deployed indexes, "even a minimal setup under **$100/month**."

**Agent Retrieval** (formerly "Vector Search 2.0") ([overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/vector-search-2/overview)) is **architecturally distinct**: "Collections" work like relational tables (with a schema, strict or relaxed validation) holding "Data Objects" (individual JSON records), and a Collection can carry multiple ANN indexes. Positioned as a unified document store *plus* vector index — "removing the need for auxiliary data storage." Supports autogenerated embeddings or bring-your-own-embeddings (BYOE), native metadata filtering, ETags for optimistic concurrency, reranking. The [migration guide](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/vector-search-2/migration-from-vs-1_0) confirms this is real migration work, not a rename: `restricts` format changes from a flat array to a hierarchical object, a new `ImportDataObjects` API, and Collections must be pre-created with a matching schema. Only **9 regions** currently: `asia-east1, asia-northeast1, asia-southeast1, europe-north1, europe-west2, europe-west4, us-central1, us-east4, us-west1`.

**Fit note**: Agent Retrieval's Collections/Data-Objects model maps naturally onto "one JSON record per timestamped, provenance-tagged knowledge unit" — better than either Vector Search 1.0 or RAG Engine's chunk model. But it's the newest, least battle-tested, smallest-footprint product surveyed, mid-rename itself. Treat as a stretch-goal spike, not a dependency, under any real deadline pressure.

## Managed Agents API

[Overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/managed-agents) — a **Preview** product, architecturally separate from ADK/Agent Runtime: single-API-call autonomous agents running in an isolated sandbox on what the docs call the **"Antigravity harness"** (`base_agent: "antigravity-preview-05-2026"` — currently the *only* supported value). Two APIs: **Agents API** (control plane — create/configure, manage sandbox envs, mount sources) and **Interactions API** (data plane — runtime request/response). Tools: `code_execution`, `filesystem`, `google_search`, `url_context`, plus MCP-server tools. No network access by default; must explicitly allowlist outbound domains.

**Fit note**: built for "one autonomous task with code exec/search/files," not for orchestrating a deterministic multi-stage CV/video ETL DAG. Not a fit for a batch pipeline with defined stages.

## Cross-cutting pricing (gathered via WebSearch, since the main pricing page fetch truncated — verify exact figures live before budgeting)

- Agent Runtime/Agent Engine compute: **~$0.0864/vCPU-hour**, **~$0.0090/GB-hour** memory (effective 2025-12-16).
- Related managed-compute categories (Memory Bank, Sessions, Skill Registry, Agent Gateway): **~$0.085/vCPU-hour**.
- **Free tier per account per month**: first 50 vCPU-hours of Agent Compute, first 100 GiB-hours of Agent Memory, first 1 GiB-month of Agent Storage — a small hackathon-scale pipeline plausibly fits inside this.
- Source page: [cloud.google.com/products/gemini-enterprise-agent-platform/pricing](https://cloud.google.com/products/gemini-enterprise-agent-platform/pricing) — direct fetch was truncated; figures above are WebSearch-corroborated from secondary sources citing the same page, not independently confirmed by reading the page itself.
