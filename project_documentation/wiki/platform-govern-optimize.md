# Gemini Enterprise Agent Platform — Govern & Optimize pillars

Last verified: 2026-08-25, via live fetch of `docs.cloud.google.com/agent-registry/*` and `docs.cloud.google.com/gemini-enterprise-agent-platform/{govern,optimize}/*`.

Framed around one question: which of these are cheap and worth doing for a 48-hour hackathon build, vs. enterprise-scale features to explicitly skip.

## Agent Registry — a real invocation mechanism, not just a catalog

[Overview](https://docs.cloud.google.com/agent-registry/overview) — a centralized catalog managing six resource types: `Agent`, `McpServer`, `Endpoint`, `Skill`, `SkillRevision`, `Publisher`. **Not just documentation-and-discovery**: ADK ships an `AgentRegistry` client that resolves a registered agent to a live, callable A2A endpoint at runtime:
```python
my_remote_agent = registry.get_remote_a2a_agent(agent_name=agent_name, httpx_client=httpx_client)
# then: sub_agents=[my_remote_agent]
```
([resolve-endpoints-and-build-orchestrators](https://docs.cloud.google.com/agent-registry/resolve-endpoints-and-build-orchestrators)) — this is the literal mechanism for two independently-deployed agents (e.g., SHRUTI and a future live-tutor agent) to call each other's tools without hardcoded URLs.

**Registration cost**: manual registration is ~8 console steps (enable API, get `roles/agentregistry.editor`, paste a JSON Agent Card). **But if you deploy via Agent Runtime, registration is automatic** — "registration in Agent Registry is automatic," updates/deletes sync automatically too ([automatic-registration](https://docs.cloud.google.com/agent-registry/automatic-registration)). Agent Gateway looks up Registry metadata to enforce access policies, so Registry underpins governance too, not just discovery.

**Verdict: core, and effectively free** if deployment already targets Agent Runtime (see the Build pillar page) — this is the connective tissue for any future multi-agent story, not an optional add-on.

## Agent Gateway

[Overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/gateways/agent-gateway-overview) — network layer securing agent↔user, agent↔tool, agent↔agent traffic. Ingress + egress for agents on Agent Runtime; egress-only for Gemini Enterprise. Protocol mediation for MCP/A2A/REST/gRPC; integrates Model Armor for MCP prompt-injection defense. Surface: `gcloud network-services agent-gateways`, REST `projects.locations.agentGateways`.

**Verdict: skip for SHRUTI** (no external ingress to secure — it's a batch pipeline). Plausible nice-to-have for a future live-tutor demo of "enterprise-grade governance," but requires real gateway provisioning — moderate cost, not a 5-minute add.

## Policies

Two distinct types ([overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/overview)):
- **IAM policies** — standard allow/deny via Identity-Aware Proxy, enforced by Agent Gateway. Skip for hackathon MVP (not platform-specific).
- **Semantic Governance** ([overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/semantic-governance-overview)) — natural-language policies ("Natural Language Constraints") checked against every proposed tool call; returns `ALLOW`/`DENY` + rationale. Setup cost is real: "approximately 2 to 3 minutes for policy engine enablement (**up to 20 minutes** if refilling warmup pool), plus networking setup," requires Agent Gateway + VPC integration, **no VPC-SC support**.

**Verdict**: skip for SHRUTI (no live tool-call surface to police). For a future live tutor: cheap-if-time-allows, visually strong demo moment ("the agent refuses an out-of-scope request in plain English") — but budget for the 20-minute warmup + gateway/VPC prerequisite before committing to it live.

## Security Command Center findings

[Overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/view-security-findings) — aggregates AI Protection, Agent Platform Vulnerability Assessment, compliance monitoring, sensitive-data discovery, Model Armor violations, AI Discovery. **Requires onboarding to Security Command Center Premium or Enterprise** — a paid, org-level entitlement. **Verdict: skip entirely** — not implementable in hackathon time, irrelevant to MVP-scale judging.

## AI Content Detection API

[Overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/ai-content-detection) — the actual page title is "Detect AI-generated images." A SynthID-based watermark **detector for images** (was this image made/edited by Google's AI models), **Private Preview**, small partner cohort. **Verdict: skip — wrong tool entirely.** Has nothing to do with verifying lecture-video authenticity or fact provenance, and is preview-gated.

## Agent Evaluation

[Overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/agent-evaluation) — the "Quality Flywheel": scenario/user simulation, **Multi-Turn AutoRaters** (score entire conversation histories), environment simulation (mocked tool errors), reference-based (Exact Match) vs. reference-free (Helpfulness) metrics. SDK: `client.evals.evaluate()`; CLI: `agents-cli eval`. Explicitly built around "entire conversation histories" and traces — targets ADK, LangChain/LangGraph, LlamaIndex, AG2, A2A, custom frameworks, but with a conversational-agent-first data model.

**The escape hatch**: three metric classes — predefined, **Custom LLM Metrics**, and **Custom Code Metrics** (arbitrary Python via `types.CodeExecutionMetric`, taking an `instance: dict`):
```python
accuracy_metric_code = """
def evaluate(instance: dict) -> float:
    agent_data = instance.get('agent_eval_data', {})
    ...
"""
accuracy_metric = types.CodeExecutionMetric(name="multi_turn_accuracy", custom_function=accuracy_metric_code)
```
([manage-metrics](https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/manage-metrics)) — a Custom Code Metric *can* implement board-recovery recall, WER, concept-F1, or a provenance-traceability check, since the function just receives an arbitrary `instance` dict. It's a real fit, just an awkward one — you're pushing batch-extraction ground-truth checks through a data model built for traces/sessions.

**Verdict: cheap and worth doing (targeted), not core** — repackage SHRUTI's own E1–E4 checks (see `shruti_architecture.md` §7) as Custom Code Metrics so they render in the platform's own evaluation dashboard instead of a bespoke pytest script's stdout.

## Evaluate simulated (simulated-user evaluation)

[Overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/evaluate-simulated) — an LLM-powered "user simulator" drives multi-turn conversations against the agent; two phases (scenario generation with a hidden "Conversation Plan," then simulation producing an immutable trace). SDK:
```python
eval_dataset = client.evals.generate_conversation_scenarios(
    agent_info=agent_info,
    config={"count": 5, "generation_instruction": "...", "environment_context": "..."},
)
eval_dataset_with_traces = client.evals.run_inference(
    agent=agent, src=eval_dataset, config={"user_simulator_config": {"max_turn": 5}}
)
```
Unambiguously built for live conversational agents — no batch/offline framing anywhere on the page.

**Verdict: skip for SHRUTI. Core to the pitch for a future live tutor** — cheap, purpose-built, narratively perfect: auto-generate N simulated student personas, run multi-turn sessions, get quality/safety/hallucination scores out of the box.

## Observability — the "on by default" claim is false

[Overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/observability/overview): *"To populate these observability dashboards, topologies, and traces, your agents must be configured to send telemetry data in the OpenTelemetry format... your own agent code does not [emit telemetry automatically], regardless of deployment target."* **This directly contradicts `shruti_architecture.md`'s §6.5 claim of "Cloud Trace (on by default via agents-cli)" — that line is wrong and needs correcting.**

Real instrumentation recipe, confirmed via the [ADK instrumentation guide](https://docs.cloud.google.com/stackdriver/docs/instrumentation/ai-agent-adk):
```
uv add 'google-adk>=1.17.0' \
      'opentelemetry-instrumentation-google-genai>=0.4b0' \
      'opentelemetry-instrumentation-sqlite3' \
      'opentelemetry-exporter-gcp-logging' \
      'opentelemetry-exporter-otlp-proto-grpc' \
      'opentelemetry-instrumentation-vertexai>=2.0b0'
```
plus an `opentelemetry.env` (`OTEL_SERVICE_NAME`, `OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED`, `OTEL_SEMCONV_STABILITY_OPT_IN`, `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`, `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS`), launched as `uv run --env-file opentelemetry.env adk web --otel_to_cloud`. "ADK 1.17.0+ includes built-in support for OpenTelemetry" — but it's **opt-in configuration, not automatic**; `adk deploy`/`agents-cli deploy` alone does not give you tracing, on Agent Runtime or anywhere else.

Once instrumented, the platform gives real dashboards under Agent Registry's Observability tab: Overview (sessions, turns, invocations, tokens, p50/p95/p99 latency, error rates), Evaluation (online monitors: quality/safety/hallucination/tool-use), Models, Tools, Usage, Logs, and a Traces tab with DAGs of spans. Standard is OpenTelemetry Semantic Conventions for generative AI (vendor-agnostic by design).

**Verdict: cheap and worth doing, for both SHRUTI and a future live tutor** — a handful of package installs + an env file, not automatic, but genuinely low-cost once you know the recipe — and it's the single most visually persuasive "we used the platform properly" artifact (a real trace DAG + latency dashboard).

## Optimize agent (prompt optimization / GEPA)

[Overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/optimize-agent) — `adk optimize` applies the **GEPA algorithm** to iteratively refine root system instructions against a test suite, on top of an evaluation harness you must already have working. Not restricted to conversational agents in wording, but presupposes the eval pipeline (above) as its scoring signal.

**Verdict: skip for hackathon MVP, both subsystems.** Real capability, too much required scaffolding (working eval harness + test suite + GEPA loop) to stand up *and demo convincingly* in the time available. Good "future work enabled by our evaluation setup" line for a pitch deck.

## Agents overview / common use cases

[Overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/agents) — customer support, information discovery, business ops, sales/marketing, software dev are the named use cases. Vocabulary throughout is conversational (Sessions/Memory Bank framing), and multi-agent/A2A composition via Agent Gateway ("calls to tools or other agents") is called out as a first-class use case — corroborating the Agent Registry finding above. No explicit split between conversational and batch/offline agents anywhere on the page — the platform's mental model is conversational-session-first, and a batch pipeline like SHRUTI is somewhat off its beaten path (which is exactly why evaluation/observability required the workarounds documented above).

## Ranked shortlist

**SHRUTI (batch pipeline):**
1. OpenTelemetry/Cloud Trace instrumentation — cheapest, most visual proof of real platform usage.
2. Agent Registry registration as an A2A agent — near-zero cost if on Agent Runtime (automatic); the piece judges will ask about the moment a second agent exists.
3. Custom Code Metrics in the Evaluation Service — repackage existing WER/F1/provenance checks to render in the platform's own dashboard.
4. *Skip*: Agent Gateway, IAM/Semantic Governance, Security Command Center findings, AI Content Detection, `adk optimize`/GEPA.

**Live tutor agent (future subsystem):**
1. Simulated-user evaluation — cheap, purpose-built, narratively perfect.
2. OpenTelemetry/Cloud Trace instrumentation — same low cost, now over real conversational spans.
3. Agent Registry + Agent Gateway — demonstrates the platform's marquee "governed multi-agent architecture" use case.
4. One Semantic Governance policy, only if time remains after the above.
