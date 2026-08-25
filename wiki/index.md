# Nityam / SHRUTI Research Wiki

Durable, source-cited research notes on the Google stack Nityam and SHRUTI are being built on. Plain markdown, hand-maintained — not run through any auto-ingestion pipeline. Pages get edited in place as research deepens; each carries a "Last verified" date so staleness is visible at a glance. Every factual claim is cited to the URL it came from — if a page says something without a link next to it, treat it as synthesis/opinion, not a sourced fact.

This wiki answers "what does the platform actually do" — for "what did we decide to build," see [`../shruti_platform_alignment.md`](../shruti_platform_alignment.md), which is the decisions document that *consumes* this research.

## Pages

| Page | Covers | Last verified |
|---|---|---|
| [platform-build.md](platform-build.md) | ADK, Agent Studio, Agent Garden, Model Garden, RAG Engine, Vector Search (1.0 and Agent Retrieval / 2.0), Managed Agents API | 2026-08-25 |
| [platform-scale.md](platform-scale.md) | Agent Runtime, Sessions, Memory Bank, Code Execution sandbox, Agent Identity, the Agent Engine → Agent Runtime rename | 2026-08-25 |
| [platform-govern-optimize.md](platform-govern-optimize.md) | Agent Registry, Agent Gateway, IAM & Semantic Governance policies, Security Command Center findings, AI Content Detection, Agent Evaluation, Observability, prompt optimization | 2026-08-25 |
| [adk-and-a2ui.md](adk-and-a2ui.md) | A2UI protocol (real spec, versions, message shape), ADK class/API ground-truth check, the source YouTube video's identity | 2026-08-25 |

## How this was built

Populated in one pass (2026-08-25) by four parallel research agents, each doing live `WebFetch`/`WebSearch` against the actual `docs.cloud.google.com/gemini-enterprise-agent-platform/*` pages, `adk.dev`, PyPI, and GitHub — not from training-data memory. The platform rebranded from "Vertex AI" in April 2026, so anything recalled from memory pre-dates the current naming and API surface; treat un-cited claims made without a fresh fetch as suspect until re-verified here.

## Maintenance rule

When a page's claim is re-checked and confirmed unchanged, bump its "Last verified" date. When it's found to have changed, edit in place and note what changed and when at the top of the affected section — don't just silently overwrite. Don't let this file's table go stale relative to the pages it indexes.
