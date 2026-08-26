# Nityam × Gemini Enterprise Agent Platform — What We Use, What We Don't

Which pieces of Google's managed "Gemini Enterprise Agent Platform" (the April 2026 rebrand of Vertex AI — same REST resources, same `reasoningEngines/*` API, new name) Nityam actually adopts, and which stay self-built. Companion to *SMRITI v0.2* and *Harness Integration*. Version 0.1.

> **The one-line summary.** We lean into the platform for deployment, compute, and session durability — and stay self-built for everything the citation invariant depends on. Every service below was evaluated against a real design decision already made, not adopted by default because Google offers it.

---

## 0. Why this document exists

"Lean into the managed platform" doesn't mean "replace our own components with Google's." It means: use the platform where it's genuinely better than what we'd hand-build, and know precisely why we're declining it where we don't. Six services were evaluated. Two are adopted narrowly. Four are declined, each for a specific, checkable reason — not by default.

| Service | Verdict | One-line why |
|---|---|---|
| **Agent Engine** (deployment/runtime) | **Adopt** | Managed autoscaling, Cloud Trace, Agent Registry listing — no reason to self-host compute |
| **Sessions** (`VertexAiSessionService`) | **Adopt, narrowly** | Durable event history — but never the source of truth for pedagogical memory |
| **Memory Bank** | **Decline as primary; adopt Profiles narrowly** | No citation/provenance mechanism, in either mode |
| **RAG Engine** | **Decline** | Solves unstructured document-chunk RAG; Shruti's Atlas is a typed graph with evidence pointers, a different shape of problem |
| **Vector Search 2** ("Agent Retrieval") | **Decline, revisit later** | Adds a network hop and a second source of truth for retrieval volumes (~2,000 nodes/subject) nowhere near where it would pay off |
| **Skill Registry** (hosted) | **Decline; use `SkillToolset` locally instead** | Breaks progressive disclosure (forces search-first, not cheap standing catalog) — but the *open-source* ADK runtime it's paired with is exactly right |
| **Feedback Service** | **Decline as canonical; optional mirror** | No aggregation/group-by API — doesn't solve the actual hard problem (cross-student mining) |
| **Sandbox / Code Execution** | **Decline for live turns; maybe for offline enrichment** | Built for batch data-science workflows, not a sub-2s voice-turn budget |

---

## 1. Deployment & Sessions

**Adopt Agent Engine as the runtime.** Managed autoscaling, Cloud Trace spans on by default, and a listing in the Agent Registry — this is the actual substance of "built on Google's agentic enterprise stack," and there's no real cost or control tradeoff in declining it.

**Adopt `VertexAiSessionService` for session/event durability — narrowly.** Confirmed directly against the installed `google-adk 2.7.1` source: `VertexAiSessionService.get_user_state()` still raises `NotImplementedError` (*"the Vertex AI Agent Engine API does [not support get_user_state]"*) — there is no user-level state independent of a session, only `list_sessions` + per-session enumeration. This is unchanged from the ADK-source research and confirmed live in the docs. It doesn't block us: session reads are genuinely zero-I/O once the `Session` object is prefetched at session-open and held resident for the turn loop, which is already the design. Writes (`AppendEvent`) are a real network call with no documented latency SLA — acceptable for the deferred write-back path (buffer in RAM, flush at session close), not something to put on the per-turn hot path regardless of which session backend is used.

**The `schedule` table and the wiki stay outside ADK's session/state abstractions entirely** — both `DatabaseSessionService` and `VertexAiSessionService` are just two interchangeable implementations of the same `BaseSessionService` interface; nothing about picking the managed one couples session durability to where pedagogical memory lives. This is the design already in place — the platform confirms it, doesn't require it.

**SDK layering, for the harness code:** three layers, not one. `google-adk` → depends unconditionally on `google-genai` (model calls) → optionally depends on `google-cloud-aiplatform`'s `vertexai.Client` (Sessions/Memory Bank/deployment), pulled in only via the `[gcp]`/`[all]` extras. Install `google-adk[gcp]` once we wire up `VertexAiSessionService`; plain `google-adk` is enough for everything self-hosted.

**Cost is not the deciding factor anywhere in this document.** Sessions/Memory Bank storage and Agent Runtime compute are cheap in absolute terms next to Gemini token costs for the tutoring conversation itself (pricing is also mid-transition to a new "Agent Storage" model effective **2026-09-01** — five days from today, worth re-checking before finalizing a cost model). Every recommendation below is decided on latency control and the citation invariant, not price.

---

## 2. Memory Bank — evaluated in full, including the new capability

Memory Bank has two modes now, and both were checked specifically for whether they close the citation gap.

**Free-text memories** (`GenerateMemories`/consolidation): LLM-extracted `{scope, fact}` records with real CREATE/UPDATE/DELETE consolidation logic. `revisions` gives an immutable history of *edits to the memory itself* — never an automatic pointer to the source event/timestamp that justified a fact. `ingest-events` supports an `event_id` for dedup, but that ID does not propagate into the resulting memory record.

**Memory Profiles** (new since the original ADK-source pass — worth genuine attention): a typed, schema-customizable alternative. You register a Pydantic-derived JSON schema; Memory Bank maintains one structured record per `(schema_id, scope)`, consolidated field-by-field. Explicitly pitched for the prefetch-at-session-open pattern we already use (*"immediate, low-latency access to evolving information without the need for expensive search operations during a session"*). This closes the "opaque black box" objection — you can now bring your own schema. **It does not close the citation gap**: fields update via LLM-judged consolidation with no evidence pointer back to a lecture/session moment, in either mode.

**Decision:** the pedagogical learner model — mastery claims, misconceptions, anything the citation invariant protects — stays entirely in the git-backed wiki + FSRS table. Never Memory Bank, in either mode. **New, narrow addition**: use Memory Profiles for soft personalization facts where citation was never going to apply and staleness risk is low — stated name, preferred explanation style, self-reported grade/track. This is an accepted convenience cache, not a reversal of the core call.

---

## 3. Grounding retrieval — RAG Engine & Vector Search 2 ("Agent Retrieval")

Two separate retrieval problems, evaluated independently, because the right answer could plausibly differ.

**Shruti's SKG (Atlas graph + the currently-orphaned embedding index).** RAG Engine is a document-chunk RAG framework (`RagCorpus` → chunk → embed → retrieve) — built for unstructured files, not for embedding typed `Concept`/`Misconception` nodes that already exist as rows with evidence pointers into `beat`/`concept_edge`. It cannot do the multi-hop typed-edge graph traversal Atlas's recursive CTEs already do, so adopting it wouldn't remove that code, only add a service around the part that was never the hard problem. Vector Search 2 (rebranded **Agent Retrieval** — a genuine architectural rewrite: object-centric Collections/Data Objects, a built-in reciprocal-rank-fusion ranker, but capped at 100,000 objects per Collection via KNN before ANN is required) is a closer conceptual fit, but its fusion ranker only fuses *within* Vector Search 2 (dense+sparse+text) — it would not replace the graph-plus-embedding fusion logic our design needs, and Shruti's Atlas sits at roughly 2,000 nodes per subject, nowhere near where this would pay for the network hop and the second service to operate. **Decline both. Keep pgvector, colocated with Reel/Ledger/Atlas in one transaction boundary.** One concrete bug found regardless of this decision: Shruti's configured embedder (`gemini-embedding-001`) is stale — the current model is **Gemini Embedding 2** — fix this whenever the embedding wiring work resumes.

**SMRITI's per-student memory (`recall()`).** Checked specifically for anything that would undercut the existing "no hosted vector DB" reasoning — a colocated/embedded low-latency mode, a per-tenant isolation tier. Neither exists: Vector Search 2 is exclusively a public regional REST API with no embedded/edge mode, "per-tenant isolation" means metadata-filtered rows in a shared Collection (not physical or latency isolation), and its 9 GA regions don't include India — directly relevant given Nityam's students. Adopting it would also reintroduce the exact two-sources-of-truth problem the wiki-as-canonical design exists to avoid. **Decline. Keep FTS5 + optional local embeddings, incrementally reindexed by content hash.**

---

## 4. Skill system — the hosted registry vs. the runtime that actually matters

This one has a real subtlety: **there are two different Google things here, and only one is directly relevant.**

**The GCP "Skill Registry"** is a hosted governance/catalog product, bundled into the broader **Agent Registry** alongside AI Agents (A2A cards) and MCP servers — an org-wide inventory and discovery tool, not a context-loading mechanism. It does use the `SKILL.md` + Agent Skills Specification format (so it's format-compatible), but the documented consumption path is a *static mount* of up to 100 skills into a sandbox filesystem at deploy time, or a `search_skills()` call that requires the agent to already know what it's looking for. Critically: pointing `SkillToolset` at the hosted registry (`SkillToolset(skills=[], registry=GCPSkillRegistry(...))`) switches to a **search-first discovery pattern** — the docs are explicit that this deliberately replaces "statically injecting every available skill into your agent's context window" — which breaks the cheap, ~100-tokens-per-skill standing catalog our design depends on. It also has no user-initiated promote/publish/review workflow — "publishers" are a Google-internal identity-verification construct, not an EduHub-style sharing gate. We'd still have to build that human-review gate ourselves either way.

**The open-source `google-adk` `SkillToolset`** is the actual runtime that matters, and it's a *separate* component from the marketing-tier docs above. Pointed at a **local directory** (`load_skill_from_dir()`), it implements the exact three-tier progressive disclosure our design assumes: L1 name+description (~100 tokens, all skills, always loaded), L2 full `SKILL.md` body (loaded via an auto-generated `load_skill(name)` tool, only on trigger), L3 bundled resources (`load_skill_resource()`, on demand). This drops straight into an `LlmAgent`'s `tools=[...]` list with zero cloud dependency.

**Decision:** keep the local, git-backed `SKILL.md` library, consumed through `SkillToolset(skills=[...])` in local-directory mode. This is not a workaround relative to Google's offering — it's the same runtime mechanism Google's own ADK team ships for this exact use case, just not routed through the hosted catalog. **Bank, don't build**: `SkillToolset` is backend-agnostic, so a future curator-promotion pipeline could write "promoted" shared skills into the hosted registry later without changing how any tutor agent consumes them day to day — worth knowing the door is open, not worth walking through it now.

---

## 5. Feedback capture

The Feedback Service is a binary thumbs-up/down store tied to one session+event, with optional labels (a suggested, not enforced, vocabulary) and free text. There is **no aggregation, group-by, or count endpoint**, and the one field flexible enough to tag a teaching-method-skill or concept (`custom_metadata`) **is not filterable**. This is the same shape as generic model-quality telemetry (à la a chat app's response rating), not a longitudinal pedagogical-effectiveness system — it does nothing for the actual hard problem, which is cross-student aggregation by skill/concept to find what's worth promoting.

**Decision:** `tutor-notes.md` (and eventually a proper curator-mined store) stays the canonical source the promotion pipeline reads. Optionally mirror explicit feedback (the pinned canvas Feedback shape) into the Feedback Service purely for console-side debugging visibility next to Agent Runtime traces — never as the mining source.

---

## 6. Sandbox / Code Execution — does it reopen the "skip Manim" call?

No. The service is real and useful for what it's built for — safe arbitrary Python execution without hand-rolling gVisor/Firecracker isolation, pre-installed data-science libraries, a 300-second ceiling, single-region (`us-central1` only), no custom pip installs. Every page frames it around data-science/batch workflows; none discuss real-time interactive latency or streaming partial output. The "under a second" sandbox-creation claim, even taken at face value, covers boot + code hand-off only — it says nothing about Manim's own render time, which was always the actual bottleneck, plus cross-region RTT and video encode/transfer back to the client. None of that fits a sub-2-second voice-turn budget.

**Decision:** the original call holds — self-contained HTML/CSS/SVG/JS in a `sandbox="allow-scripts"` iframe stays the live, in-turn canvas mechanism. If richer Manim-quality visuals are wanted later, Code Execution is a reasonable **out-of-band enrichment** — pre-render or lazily generate clips during lesson authoring, cache and reuse across students on the same concept, never block a live turn on it.

---

## 7. What this changes in the rest of the design

- **Nothing about SMRITI's core memory design changes.** Every service evaluated against it came back "keep the current approach" — this section exists to make that an evidence-based decision, not an assumption.
- **Two narrow additions**: Memory Profiles for non-citable soft personalization (§2); optional Feedback Service mirroring for console debugging (§5).
- **One bug to fix, independent of any of this**: Shruti's `gemini-embedding-001` → **Gemini Embedding 2** (§3), whenever the embedding-wiring work in Phase 0 resumes.
- **The Agent Registry listing (§1) is the real "built on Google's platform" story** for anything demo/pitch-facing — not a reason to route core functionality through services that don't fit.

---

*v0.1. Every recommendation above was checked against a specific existing design decision and a specific service capability — not decided by "Google offers X, so we should use X." Where a service earned a narrow role (Memory Profiles, optional Feedback Service mirroring, future skill-registry migration path), that's noted explicitly rather than left implicit.*
