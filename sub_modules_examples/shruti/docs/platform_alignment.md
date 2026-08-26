# SHRUTI × Gemini Enterprise Agent Platform — Alignment Decisions

v0.2 addendum to *SHRUTI — Architecture, Research & Decisions* (v0.1). Read that document first — this one only covers what changes about **where SHRUTI runs and how it proves it's using the platform**, given the hackathon's hard requirement to use managed Gemini Enterprise Agent Platform services, not just the open-source ADK library. It does not revisit D1–D3 (Gemini-native extraction, Reel/Ledger/Atlas layering, staged CV) — that pipeline design is unaffected and stays as designed.

Every decision below is backed by live research in [`wiki/`](wiki/index.md) — follow the links if you want the primary source rather than the summary.

**Constraint this addendum is written against: under 48 hours to demo-ready.** Every decision below was filtered through "does this buy real platform credit for its cost," not "is this the most complete possible integration." Enterprise-scale governance features are deliberately cut — see D8.

**Open question, still unresolved**: is there already a GCP project provisioned with billing and access to Agent Runtime (it may be preview/allowlisted)? If not, provisioning + access approval is step zero and could itself eat into the 48 hours. Confirm before starting the build-order in §5.

---

## D4 — Deployment target: `agent_engine`, not `cloud_run`

**Decision**: change the implementation guide's deploy step from
```
agents-cli scaffold enhance --deployment-target cloud_run
```
to
```
agents-cli scaffold enhance --deployment-target agent_engine
agents-cli deploy
```
No other code changes. Same `SequentialAgent` tree, same stages, same contracts.

**Why**: `--deployment-target cloud_run` is a real, first-class, officially documented path — not a workaround — but it means the pipeline never touches Agent Runtime, managed Sessions, or platform telemetry, i.e. it gets zero "managed platform" credit despite using the ADK framework. `agent_engine` is the one-flag change that puts the identical agent code onto the actual managed Agent Runtime. This is the single highest-leverage change in this whole document: near-zero implementation cost, and it's very likely what a hackathon judge means by "using the platform." ([wiki/platform-build.md](wiki/platform-build.md), §CLI/deployment)

**Free-tier note**: Agent Runtime compute has a documented free tier (first 50 vCPU-hours, first 100 GiB-hours memory, first 1 GiB-month storage per account per month) that a hackathon-scale pipeline plausibly fits inside — verify against your actual project's quota once provisioned. ([wiki/platform-build.md](wiki/platform-build.md), pricing section)

**Consequence — this is automatic, not extra work**: deploying to Agent Runtime **automatically registers SHRUTI in Agent Registry**, with no separate registration step. That's D5 solved for free. ([wiki/platform-govern-optimize.md](wiki/platform-govern-optimize.md), Agent Registry)

---

## D5 — Agent Registry: accept the automatic registration, don't build anything extra

**Decision**: no additional work. D4's deployment target change auto-registers SHRUTI as an A2A-discoverable agent.

**Why it matters beyond a checkbox**: `AgentRegistry.get_remote_a2a_agent(agent_name=...)` is the real, intended mechanism for a *second* agent (the future live tutor) to discover and call SHRUTI's LENS tools without a hardcoded URL — `sub_agents=[my_remote_agent]` in ADK. When the live-tutor subsystem gets built, this is the interop seam to use. Worth one sentence in the hackathon pitch: "SHRUTI and the tutor discover each other through Agent Registry, not hardcoded endpoints." ([wiki/platform-govern-optimize.md](wiki/platform-govern-optimize.md), Agent Registry)

---

## D6 — Correct the observability claim, then do the cheap real version

**Correction to `shruti_architecture.md` §6.5**: the line *"Cloud Trace (on by default via `agents-cli`)"* is **wrong**. Confirmed directly from the platform's own observability docs: *"your agents must be configured to send telemetry... your own agent code does not [emit it automatically], regardless of deployment target."* ([wiki/platform-govern-optimize.md](wiki/platform-govern-optimize.md), Observability)

**Decision**: add explicit OpenTelemetry instrumentation. Concretely:
```bash
uv add 'google-adk>=1.17.0' \
      'opentelemetry-instrumentation-google-genai>=0.4b0' \
      'opentelemetry-instrumentation-sqlite3' \
      'opentelemetry-exporter-gcp-logging' \
      'opentelemetry-exporter-otlp-proto-grpc' \
      'opentelemetry-instrumentation-vertexai>=2.0b0'
```
plus an `opentelemetry.env` (`OTEL_SERVICE_NAME`, `OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED`, `OTEL_SEMCONV_STABILITY_OPT_IN`, `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`, `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS`), and launch with the `--otel_to_cloud` equivalent for however SHRUTI's runner starts.

**Why it's worth the (small) cost**: this is the single most visually persuasive "we used the platform properly" artifact — a real trace DAG over Gate→Pulse→Perceive→Weave→Glyph→Atlas with per-stage latency and error rates, in the platform's own Unified Trace Viewer, not a bespoke log line. Cheap: a handful of package installs and an env file, not a code rewrite.

---

## D7 — Fold E1–E4 into the platform's Evaluation Service as Custom Code Metrics

**Decision**: keep `evals/e1_board_recall.py` … `e4_provenance_invariant.py` exactly as designed in `shruti_architecture.md` §7, but also register each as a `types.CodeExecutionMetric` against the Agent Platform Evaluation Service:
```python
board_recall_metric = types.CodeExecutionMetric(
    name="board_recovery_recall",
    custom_function=open("evals/e1_board_recall.py").read(),  # adapted to the evaluate(instance: dict) -> float signature
)
```

**Why**: Agent Evaluation (Multi-Turn AutoRaters, simulated-user eval) is built around conversation traces and is a poor structural fit for a batch extraction pipeline's ground-truth checks — but Custom Code Metrics accept an arbitrary `instance: dict`, so SHRUTI's own WER/F1/recall/provenance functions can be wrapped without redesigning them, and the *results render in the platform's own evaluation dashboard* instead of a pytest stdout dump. This is "cheap and worth doing," not core — do D4–D6 first; do this if time remains. ([wiki/platform-govern-optimize.md](wiki/platform-govern-optimize.md), Agent Evaluation)

**E4 (the provenance invariant) still also runs as a CI gate exactly as designed** — the platform integration is additive, not a replacement for the correctness assertion.

---

## D8 — What NOT to re-platform, and why (the expensive-and-wrong-fit list)

Each of these was seriously evaluated in the research and rejected for SHRUTI specifically. Don't relitigate these under time pressure — the reasoning is settled:

| Component | Verdict | Why |
|---|---|---|
| **RAG Engine** | Skip for SHRUTI | It's a text-chunking-and-retrieval orchestrator (`chunk_size`/`chunk_overlap`, corpus abstraction) built for document Q&A grounding. SHRUTI's hard problem — timestamped, CV-provenance-tagged records with bounding boxes/confidence/speaker metadata — is richer than and upstream of what RAG Engine's transformation config expresses. Relevant later to the *live tutor's* Q&A grounding, not to SHRUTI's extraction pipeline — don't conflate the two subsystems. |
| **Vector Search 1.0** | Skip | Confirmed to be the same ScaNN/Matching-Engine product, just re-branded — not a capability upgrade over a tuned pgvector/HNSW index at hackathon scale, and it has a real cost floor (~$100/month) plus index/endpoint migration effort. A lateral move, not an upgrade. |
| **Agent Retrieval (Vector Search 2.0)** | Optional stretch goal only, never a dependency | Its Collections/Data-Objects model is a genuinely better conceptual fit for "one JSON record per timestamped, provenance-tagged unit" than pgvector or RAG Engine's chunking — but it's the newest, least battle-tested, 9-region-only product surveyed, mid-rename itself (2.0 → "Agent Retrieval"). Keep pgvector as the source of truth for the demo; attempt this only as a "we also validated it on the real managed product" addendum if time remains. |
| **Agent Garden** | Skip | Its only documented template category (RAG) is conversational Q&A; its GitHub samples (`always-on-memory-agent`, `genai-experience-concierge`) are chat patterns. Nothing in its inventory matches a video/CV-ETL batch DAG — there's no closer-fitting template to adopt than what's already designed. |
| **Managed Agents API** | Skip | Single-API-call autonomous agent in an isolated sandbox (the "Antigravity harness"), built for one-shot tasks with code-exec/search/files — not for orchestrating a deterministic multi-stage pipeline. Forcing SHRUTI's DAG into this shape would be a regression from `SequentialAgent`/`ParallelAgent`, not an upgrade. |
| **Agent Studio** | Skip | No-code conversational-agent authoring console, UI-only, no code/class surface. Not applicable to a code-first CV/video pipeline. |
| **Agent Gateway, Semantic Governance, Security Command Center findings, AI Content Detection, `adk optimize`/GEPA** | Skip | Enterprise-scale (paid SCC Premium/Enterprise tier), preview-gated (AI Content Detection is an image-watermark detector, unrelated to lecture-video correctness), or require scaffolding (GEPA needs a working eval harness first) disproportionate to hackathon time. See [wiki/platform-govern-optimize.md](wiki/platform-govern-optimize.md) for the full reasoning per item. |

---

## D9 — Forward notes for the not-yet-designed live-tutor subsystem

These aren't SHRUTI action items — SHRUTI has no live conversation and no UI — but they're decisions the research already resolved, worth recording now so the next brainstorming pass on the tutor doesn't re-derive them:

1. **The structured learner model belongs in Postgres, not Memory Bank.** Memory Bank's only structured primitive ("Memory Profiles") is one flat schema per user, not a per-concept dynamic collection, and every write is an LLM judgment call, not a deterministic update — wrong tool for an auditable spaced-repetition decay computation. Memory Bank's genuine fit is the fuzzy "how this student likes to be taught" layer (managed topics: `USER_PREFERENCES`, `EXPLICIT_INSTRUCTIONS`, `KEY_CONVERSATION_DETAILS`), fed from session transcripts, retrieved by similarity search to season tone — never in the path that decides what to review next. ([wiki/platform-scale.md](wiki/platform-scale.md), Memory Bank)
2. **The background "wakes on a schedule, re-checks decay, pushes a nudge" agent has no native Agent Runtime primitive.** Google's own reference architecture for exactly this pattern is DIY: `DatabaseSessionService` + an external trigger. Plan for **Cloud Scheduler → Pub/Sub → an Agent-Runtime event-driven invocation** as its own infra component — it is not something Sessions or Memory Bank provide. ([wiki/platform-scale.md](wiki/platform-scale.md), Agent Runtime — deployment mechanics and the scheduling gap)
3. **Sessions**: `VertexAiSessionService` and `DatabaseSessionService` are interchangeable via a one-line constructor swap — no urgency to pick one over the other now, and no lock-in either way when the tutor's session model is designed.
4. **The A2UI artifact-catalog message shape is `createSurface`(pointing at a `catalogId`) + `updateComponents`(component IDs from that catalog) — not a flat `{component, params}` object.** Also: **Gemini Enterprise ships a built-in A2UI renderer** — evaluate using it directly for the canvas rather than building a custom renderer, given the platform-requirement constraint. ([wiki/adk-and-a2ui.md](wiki/adk-and-a2ui.md), A2UI)
5. **ADK's model/tool callbacks (`before_model_callback`/`after_model_callback`) do not fire on the streaming path** — only on `run_async`. Any guardrail or provenance-logging plugin designed for SHRUTI (see `shruti_architecture.md` §6.4, `ProvenancePlugin`/`CostGuardPlugin`) will need a different mechanism for the tutor's voice-streaming path. Flag this explicitly when that subsystem is designed — it's an easy thing to assume "just works" and have it silently not fire.

---

## Code-hygiene flags (apply during implementation, not a design decision)

- If any SHRUTI code imports `vertexai.generative_models`, `.language_models`, `.vision_models`, `.tuning`, or `.caching` — these were deprecated 2025-06-24 and their **removal date (2026-06-24) has already passed**. Use the `google-genai` SDK instead.
- `vertexai.agent_engines` is slated to become `runtimes` in an upcoming release ("not before 2026-07-31" — may have shipped already). Don't build long-lived code against the `agent_engines` name if avoidable; if the current quickstart samples are the only reference, treat the import path as transitional.
- Pin the `google-adk` version explicitly (currently 2.7.1) — ADK 2.0 changed the session schema; know which side of that line the pinned version sits on.

---

## §5 — Revised build order for the 48-hour window

This replaces `shruti_implementation.md` §9's "Day 1–6" plan (written for a leisurely week) with a sequence compressed to the actual deadline. Ordering logic: **the pipeline has to work before the platform integration matters** — a beautifully-instrumented pipeline that doesn't extract anything correctly is worse than a working pipeline with no telemetry. Platform-alignment work (D4–D7) is deliberately pushed late and scoped small so it never blocks the core demo.

1. **Hours 0–1 — unblock, don't build.** Confirm GCP project + billing + Agent Runtime access (the open question above). If access is preview-gated and not yet approved, request it *immediately* and build against plain `cloud_run` in parallel so D4 is a config flip whenever access lands, not a blocker.
2. **Hours 1–8 — the spine, on real footage** (per `shruti_implementation.md` §9 Day 1): GATE, PULSE, ink curve + erase detection, tuned against real classroom video, not synthetic test clips.
3. **Hours 8–20 — the board** (Day 2): SLATE locate/rectify/mask V1/composite. Highest-risk stage — look at actual output images before moving on.
4. **Hours 20–30 — speech and fusion** (Day 3): ECHO with the code-mix prompt, WEAVE, POINT.
5. **Hours 30–38 — semantics and storage** (Days 4): ATLAS, VAULT (Reel/Ledger/Atlas + provenance invariant), LENS + ADK tools.
6. **Hours 38–42 — platform alignment (D4–D6 only)**: flip the deployment target to `agent_engine`, confirm automatic Agent Registry registration, add OpenTelemetry instrumentation. Skip D7 (Custom Code Metrics) unless comfortably ahead of schedule — it's real value but the least urgent of the four.
7. **Hours 42–46 — evidence**: run E1–E4 against whatever footage is available; fix anything E4 (provenance) flags, since that one should fail the build if broken.
8. **Hours 46–48 — the demo.** Rehearse the exact three-minute flow in `shruti_implementation.md` §10, now narrating the platform pieces explicitly: "deployed on Agent Runtime, auto-registered in Agent Registry, traced end-to-end" alongside the original board-recovery/misconception-mining beats.

**If behind schedule**, cut in this order (unchanged from the original doc, platform items added at the end since they're the newest and least load-bearing): POINT (deixis) → misconception mining → SAM 3 → graph layer (ship vector-only retrieval) → multi-lecture merge → **D7 (Custom Code Metrics) → D6 (OTel instrumentation) → D4 (deployment target flip, fall back to demoing on plain Cloud Run and narrating "designed for Agent Runtime, deployed to Cloud Run for the demo window" if truly out of runway).**

**Never cut**: the ink curve, board compositing with the `unfilled` mask, the code-mix transcript prompt, the provenance invariant — unchanged from the original doc, and true regardless of platform target.
