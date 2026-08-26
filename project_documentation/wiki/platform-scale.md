# Gemini Enterprise Agent Platform — Scale pillar

Last verified: 2026-08-25, via live fetch of `docs.cloud.google.com/gemini-enterprise-agent-platform/scale/*` and cross-checks against ADK docs and Google's developer blog.

This is the pillar that matters most for Nityam's core requirement — "stateful, multi-turn dialogue with persistent memory" and a "background agent that wakes on a schedule." The findings below directly shaped the learner-model and scheduling decisions in `../../sub_modules/shruti/docs/platform_alignment.md`.

## Pillar overview

[`/scale`](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale) bundles seven sub-products: **Agent Runtime** (deploy/operate/scale), **Sessions**, **Memory Bank**, **Feedback Service**, **Code Execution (Sandbox)**, **Agent Identity**, **Agent Gateway Integration**. Compliance: Agent Runtime, Agent evaluation, Sessions, Memory Bank, and Code Execution all support VPC-SC, CMEK, and data residency-at-rest (only "Example Store" is excluded). Notable: **"Memory Bank uses Generative AI models to generate memories"** — processing happens in the region of the model endpoint, relevant if data residency for learner data matters.

## Sessions

[`/scale/sessions`](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/sessions) definitions (verbatim): **Session** = "the chronological sequence of messages and actions (events) for a single, ongoing interaction." **Event** = "the content of the conversation... and actions taken... such as function calls." **State** = "temporary data relevant only during the current conversation." **Memory** = "personalized information... accessed across multiple sessions." The docs draw the Session/Memory line exactly where you'd expect: Sessions = ephemeral-per-conversation, Memory = cross-session.

REST surface (base: `https://LOCATION-aiplatform.googleapis.com/v1beta1/projects/PROJECT_ID/locations/LOCATION/reasoningEngines/AGENT_ENGINE_ID`, from [`manage-with-api`](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/sessions/manage-with-api)):

```
GET    /sessions                          # list, optional ?filter=user_id="USER_ID"
POST   /sessions                          # create, body: {"userId": "USER_ID"}
GET    /sessions/SESSION_ID               # get
DELETE /sessions/SESSION_ID               # delete
GET    /sessions/SESSION_ID/events        # list events
POST   /sessions/SESSION_ID/events:append # append event
```

Note the path segment is literally `reasoningEngines`, not `agentRuntimes` — see the rename note below. Default TTL: **365 days**, configurable via `ttl`/`expire_time`.

ADK integration ([`manage-with-adk`](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/sessions/manage-with-adk)):
```python
session_service = VertexAiSessionService(project="PROJECT_ID", location="LOCATION", agent_engine_id="AGENT_ENGINE_ID")
runner = Runner(agent=agent.root_agent, app_name=app_name, session_service=session_service)
```
Confirmed independently from ADK's own docs ([adk.dev/sessions/session](https://adk.dev/sessions/session/)): `SessionService` is an abstract interface with three concrete implementations — `InMemorySessionService` (dev/test, no persistence), `DatabaseSessionService(db_url=...)` (self-hosted Postgres/MySQL/SQLite — "applications needing reliable, persistent storage that you manage yourself"), `VertexAiSessionService` (managed, "data is managed reliably and scalably via Agent Runtime"). **These are interchangeable via a one-line constructor swap in the `Runner` setup — swapping is not required to use other platform features.** A gotcha worth remembering: "changes made to state directly will likely NOT be saved... they rely on `append_event` to trigger saving" for both persistent implementations.

## Memory Bank

Sources: [`/scale/memory-bank`](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank), [`generate-memories`](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/generate-memories), [`fetch-memories`](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/fetch-memories), [`ingest-events`](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/ingest-events), [`profiles`](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/profiles)

API surface (`client.agent_engines.memories.*`):
- `generate()` — wraps `GenerateMemories`: synchronous extraction from a batch of conversation events, returns memories tagged `action: CREATED|UPDATED|DELETED`.
- `ingest_events()` — wraps `IngestEvents`: continuous streaming ingestion into a `stream_id`; generation fires on a trigger rule (`event_count`, `idle_duration`, fixed `interval`, or manual `force_flush`); untriggered streams auto-flush **24 hours** after the last event. Dedup by `event_id`; `overlap_event_count` re-includes prior events for cross-window coherence.
- `retrieve()` — wraps `RetrieveMemories`: bulk-by-scope, or `similarity_search_params: {search_query, top_k (default 3)}` ranked by Euclidean embedding distance; supports an EBNF `filter` over `create_time/update_time/fact/topics` and DNF `filter_groups` over metadata.
- `retrieve_profiles()` — returns a populated Memory Profile.

**Two distinct object types — this is the key finding for the learner-model decision:**

1. **Plain memories**: unstructured, LLM-extracted `fact` strings, optionally tagged with typed `metadata` and a `topics` label (built-ins: `USER_PERSONAL_INFO`, `USER_PREFERENCES`, `KEY_CONVERSATION_DETAILS`, `EXPLICIT_INSTRUCTIONS`, or custom). Retrieval is similarity-search-shaped.
2. **Memory Profiles** (newer — called out in Google's 2026-07-30 "What's new" post): "data structures with static schemas populated and updated using LLMs." You define a Pydantic model, upload its JSON schema, and Memory Bank maintains **one profile per scope as a single source of truth**, updated via LLM-judged consolidation ("An LLM will judge how to update the existing content"). Example schema shown in the docs is flat: `name, technical_stack, primary_goal, expertise_level, job_status`. You can retrieve it directly via `retrieve_profiles(scope=...)`, or disable plain memories entirely and use only the profile.

**What's missing, decisively**: no documented way to hold a *dynamic, per-concept-keyed* collection (e.g., "for each of N concepts, track mastery, last-seen, misconception tags") — Profiles are one flat schema instance per scope, not a growing collection. And every write is an **LLM judgment pass**, not a deterministic numeric update — there's no way to run a deterministic Ebbinghaus/SM-2 decay computation *inside* Memory Bank; that math has to live in your own code.

Plain-memory object shape:
```json
{
  "name": "projects/.../reasoningEngines/.../memories/...",
  "scope": {"agent_name": "My agent", "user": "my user ID"},
  "fact": "I use Memory Bank to manage my memories."
}
```

## Code Execution (Sandbox)

[`/scale/sandbox/code-execution-overview`](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/sandbox/code-execution-overview) — Python-only, no custom library installs, sub-second create/execute. Execution state persists **up to 14 days** (configurable TTL) — a sandbox filesystem/kernel TTL, not conversation memory. File I/O capped at **100MB** per request/response. **Region-locked to `us-central1` only.** No network access. Decoupled from Agent Runtime — "you aren't required to deploy your agent to Agent Platform to use Code Execution."

## Agent Runtime — deployment mechanics and the scheduling gap

[`/scale/runtime/deploy-an-agent`](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/deploy-an-agent): five deploy paths via `client.agent_engines.create(...)` — in-memory agent object, Developer Connect (git) source, source files (`entrypoint_module`/`entrypoint_object`), Dockerfile, or prebuilt image. Scaling knobs: `min_instances`, `max_instances` (capped at **10**), `resource_limits`, `container_concurrency` (default 9). **The page never names the underlying compute substrate.** No cold-start numbers, no max-duration figure. **Zero occurrences of "schedule," "cron," "trigger," "background," "Cloud Scheduler," "Cloud Tasks," or "Pub/Sub" anywhere in the deploy/manage/scale runtime docs** — every documented invocation pattern (`query`, `streamQuery`, all five deploy variants) is inbound-request-driven.

[`/scale/runtime/optimize-and-scale`](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/optimize-and-scale) — the real numbers, which **contradict the marketing tagline**:
- Default (`min_instances=1`): **~4.7s average cold start**, **~0.4s warm**.
- With `min_instances=10` (the max) pre-provisioned: cold start drops to **~1.4s**.
- Sustained load (1,500 QPM/60s): **~1.6s average latency**.
- At 300 concurrent requests with `min_instances=10, container_concurrency=36`: max latency drops from 60s to ~7s.

**"Sub-second cold starts" is a best-case/warm-pool marketing framing**, not what the default config delivers, and there's no published SLA percentage anywhere in these pages.

**Is there genuine scheduled/background execution?** Not natively in Agent Runtime as documented. There *is* a scheduling feature, but it lives in a different product — **Agent Designer**, the no-code builder inside the *end-user Gemini Enterprise app* ([`gemini/enterprise/docs/agent-designer/schedule-agent`](https://docs.cloud.google.com/gemini/enterprise/docs/agent-designer/schedule-agent)) — genuine cron-like scheduling (hourly/daily/weekly/monthly/annual, timezone-aware, fixed prompt per run), but it **never cross-references Agent Runtime, ADK, or developer-deployed agents**. Separately, Google's launch blog (marketing, not technical docs) claims Agent Runtime supports **"Batch & Event-driven agents... activate your data in BigQuery and Pub/Sub... run massive, asynchronous tasks... in the background"** ([launch blog](https://cloud.google.com/blog/products/ai-machine-learning/introducing-gemini-enterprise-agent-platform)) — event-driven (a Pub/Sub message triggers invocation), not literally calendar/cron. To get "wakes every N hours" out of this you still need **Cloud Scheduler → Pub/Sub → Agent Runtime event-driven invocation** — asserted in the blog, not documented as a how-to with a request/response schema in the technical reference set.

Reinforcing this: Google's own reference pattern for "long-running agents that pause, resume, and never lose context" ([developer blog](https://developers.googleblog.com/build-long-running-ai-agents-that-pause-resume-and-never-lose-context-with-adk/), 2026-05-12) implements wake-on-event via **your own webhook endpoint + `DatabaseSessionService`** (SQLite locally / Cloud SQL in production) — *not* any platform-native scheduler. Quote: "The agent needs to sleep – truly sleep – and wake up only when an external event arrives." This is architecturally identical to a hand-rolled Postgres state machine — Google's own reference architecture for this exact pattern is DIY-on-ADK, not a managed feature.

**"Long-running agents... up to 7 days"** appears in secondary/marketing sources but no technical reference page states a hard max-duration, resumability mechanism, or pricing model for it — flag as vendor-claimed-but-undocumented-in-detail.

## Agent Identity

[`/scale/runtime/agent-identity`](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/agent-identity) — each deployed agent gets a per-agent SPIFFE-style identity: `principal://agents.global.org-ORGANIZATION_ID.system.id.goog/resources/aiplatform/projects/PROJECT_NUMBER/locations/LOCATION/reasoningEngines/AGENT_ENGINE_ID`. Certificate-bound via Context-Aware Access/mTLS — "stolen credentials un-replayable... (for example, a Cloud Run container)." **That parenthetical is the only place across all Scale-pillar pages that names the actual compute substrate** — strong indirect evidence Agent Runtime is built on Cloud Run, never stated as a flat fact. Default roles: `roles/aiplatform.agentContextEditor`, `roles/aiplatform.agentDefaultAccess`; recommended addition: `roles/aiplatform.expressUser` for inference/sessions/memory.

## The Agent Engine / Reasoning Engine rename

Confirmed directly from the [Agent Runtime overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime): *"Because the name of Agent Runtime changed over time, the name of the resource in the API reference is `ReasoningEngine` to maintain backwards compatibility."* This is why every Sessions/Memory Bank/Identity path still reads `reasoningEngines/AGENT_ENGINE_ID` even though the product is now "Agent Runtime" — **old tutorials/SDK snippets referencing "Vertex AI Agent Engine" or "Reasoning Engine" are still technically accurate at the API/SDK layer**; only the product-facing name changed.

Timeline: **2026-04-23** — Cloud Next, Vertex AI folded into Gemini Enterprise Agent Platform ([launch blog](https://cloud.google.com/blog/products/ai-machine-learning/introducing-gemini-enterprise-agent-platform)); Agent Engine → **Agent Runtime** + Sessions + Memory Bank as Scale-pillar sub-products. **~2026-05-21** (secondary sources) — Vertex AI branding fully removed from the Cloud Console. **2026-07-30** — "What's new" post adds Memory Profiles, long-running agents ("up to 7 days"), Agent Identity/Gateway/Registry, eval/observability updates. ADK itself was **not** renamed — it's the open-source, code-first framework that "survived the rename untouched"; only the managed cloud-hosted counterpart and adjacent managed services were renamed.

## Recommendation this research supports (see the alignment doc for the actual decision)

**Structured learner model (per-concept mastery, misconceptions, decay state) → Postgres, not Memory Bank.** Reasons: no per-concept dynamic structure in Memory Bank (Profiles are one flat schema per scope); every Memory Bank write is an LLM judgment call, not a deterministic update (wrong for auditable decay math); retrieval is similarity/filter-shaped, not the relational range query ("mastery < 0.6 AND review_due <= now()") a nudge-agent needs. **Memory Bank's genuine fit**: the qualitative "how this student likes to be taught" signal (managed topics: `USER_PREFERENCES`, `EXPLICIT_INSTRUCTIONS`, `KEY_CONVERSATION_DETAILS`) — feed session transcripts in via `ingest_events`/`generate`, retrieve via similarity search to season tone, but never let it decide *what* to review next. **Scheduled background agent** needs Cloud Scheduler → Pub/Sub → event-driven Agent Runtime invocation regardless of where the learner-model data lives — there's no scheduling-side reason to prefer Memory Bank either.
