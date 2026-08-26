# A2UI, ADK ground-truth, and the source video

Last verified: 2026-08-25, via `WebFetch`/`WebSearch` against a2ui.org, GitHub, Google Developers Blog, PyPI, adk.dev, and YouTube's oEmbed endpoint.

## A2UI is real — and the artifact-catalog design's schema assumption needs one correction

**Confirmed real, named, versioned Google protocol**, not a talk/blog-only concept:
- Original announcement: [Google Developers Blog, "Introducing A2UI"](https://developers.googleblog.com/introducing-a2ui-an-open-project-for-agent-driven-interfaces/), **2025-12-15**. *"A2UI is an open-source project, complete with a format optimized for representing updateable, agent-generated UIs and an initial set of renderers."* Released at v0.8, "early, but working."
- Follow-up: [Google Developers Blog, "A2UI v0.9"](https://developers.googleblog.com/a2ui-v0-9-generative-ui/), **2026-04-17**. *"A2UI v0.9 is our answer; a framework-agnostic standard for declaring UI intent."*
- Canonical spec: [a2ui.org](https://a2ui.org/) / [a2ui.org/introduction/what-is-a2ui](https://a2ui.org/introduction/what-is-a2ui/) — *"A2UI (Agent to UI) is a declarative UI protocol for agent-driven interfaces"* that render natively (web/mobile/desktop) *"without executing arbitrary code."* Explicitly: *"Not a framework (it is a protocol)."* Current: **v0.9.1** (production), **v1.0** (release candidate); v0.8 is legacy.
- Repo: `github.com/google/A2UI` now redirects to **[github.com/a2ui-project/a2ui](https://github.com/a2ui-project/a2ui)** (16.2k stars at fetch time) — mirrors how A2A moved to the Linux Foundation. Apache 2.0, "created by Google with contributions from CopilotKit and the open source community." Self-described: *"Early stage public preview... functional but still evolving."*
- Relationship to A2A/MCP: A2UI is a **payload format**; A2A is one **transport**. Confirmed by [Google Cloud's blog, "Guide to Gemini Enterprise and A2UI integration"](https://cloud.google.com/blog/topics/developers-practitioners/guide-to-gemini-enterprise-and-a2ui-integration) (**2026-05-30**): *"A2UI rides inside the A2A protocol as DataPart objects with the MIME type `application/json+a2ui`."* It is a **separate, competing standard from MCP-UI/MCP Apps**, not built on MCP — Google contrasts A2UI's native-component approach against MCP Apps' iframe-sandboxed approach ([The New Stack](https://thenewstack.io/agent-ui-standards-multiply-mcp-apps-and-googles-a2ui/), [CopilotKit](https://www.copilotkit.ai/blog/the-state-of-agentic-ui-comparing-ag-ui-mcp-ui-and-a2ui-protocols)), though an "A2UI + MCP" interop guide exists.
- [AG-UI](https://docs.ag-ui.com/agentic-protocols) *"fully supports the A2UI spec for rich declarative generative UIs."*

**The message shape — correction needed for the Nityam artifact-catalog design.** The design's working assumption (a flat `{component: "projectile_motion_sim", params: {...}}` emission) is **not** the real shape. Confirmed from a2ui.org's v0.9.1 docs:
```json
{
  "version": "v0.9.1",
  "createSurface": {
    "surfaceId": "booking",
    "catalogId": "https://a2ui.org/specification/v0_9_1/catalogs/basic/catalog.json"
  }
}
```
Actual component content is then sent via a separate **`updateComponents`** message as a flat list of components with ID references (not a nested tree) — plus `updateDataModel` and `deleteSurface` message types (per [atamel.dev, 2026-03-30](https://atamel.dev/posts/2026/03-30_a2ui_with_adk/)). **A2UI's unit of reference is a catalog-scoped component instance within a surface, not a bare `{component, params}` RPC call.** Update the artifact-catalog design to model `createSurface`(catalogId) + `updateComponents`(component IDs drawn from that catalog) rather than a flat object.

**Reference code exists, and it does integrate with ADK specifically**:
```
git clone https://github.com/google/A2UI.git
cd A2UI/samples/agent/adk/restaurant_finder
uv run .
```
Real code from that sample ([atamel.dev](https://atamel.dev/posts/2026/03-30_a2ui_with_adk/)):
```python
restaurant_prompt = A2uiSchemaManager(
    version, catalogs=[BasicCatalog.get_config(...)], schema_modifiers=[remove_strict_validation],
).generate_system_prompt(role_description=ROLE_DESCRIPTION, ui_description=UI_DESCRIPTION,
                          include_schema=True, include_examples=True, validate_examples=True)
...
return LlmAgent(model=LiteLlm(model=LITELLM_MODEL), name="restaurant_agent",
                description="An agent that finds restaurants and helps book tables.",
                instruction=instruction, tools=[get_restaurants])
```
The `A2uiSchemaManager` helper injects the catalog schema into the ADK `LlmAgent`'s system prompt — this is the actual mechanism a Nityam tutor agent would use to constrain itself to the artifact catalog. Client renderers exist for `renderers/lit`, plus React, Angular, and a Flutter GenUI SDK.

**Directly relevant to this platform choice**: [Google Cloud's blog](https://cloud.google.com/blog/topics/developers-practitioners/guide-to-gemini-enterprise-and-a2ui-integration) (2026-05-30) states **Gemini Enterprise ships with a built-in A2UI renderer** — the agent emits A2UI JSON, "GE receives the JSON, validates it against its catalog, and renders the widget natively in GE's own design language," interactions serialize back as the next A2A turn. Since Nityam is targeting this platform, this built-in renderer is a real option to evaluate for the artifact-catalog canvas, not just a protocol to hand-implement a renderer for.

## ADK ground-truth check

**Current version**: `google-adk` **2.7.1**, released **2026-08-17** ([PyPI](https://pypi.org/project/google-adk/); JSON API cross-checked directly). Recent history: 2.7.1 (Aug 17) → 2.7.0 (Aug 13) → 2.6.3 (Aug 7) → 2.6.2 (Aug 4) → 2.6.1 (Jul 31) → 2.6.0 (Jul 30, 2026). ADK's "2.0" line introduced breaking changes to the agent API/event model/session schema; sessions from 2.0 remain backward-readable by 1.28+.

**Docs domain moved**: `google.github.io/adk-docs/` now **301-redirects to `https://adk.dev/`** (same for sub-pages). Not a deprecation signal — content unchanged, just a hosting move. Update citations to `adk.dev` for durability. `adk.dev` shows ADK is now multi-language: Python, TypeScript, Go (2.0 GA, "graph workflows and collaborative agents"), Java, Kotlin.

**Class/API existence — all confirmed real, current, none deprecated/renamed/hallucinated** (as of ADK 2.7.1, checked against `adk.dev` and the ADK GitHub repo):

| Name | Confirmed via |
|---|---|
| `LlmAgent` (and its `Agent` alias) | adk.dev/agents/llm-agents; [adk-python#1158](https://github.com/google/adk-python/issues/1158) |
| `SequentialAgent`, `ParallelAgent`, `LoopAgent` | adk.dev/agents/custom-agents, /workflow-agents/parallel-agents |
| `FunctionTool` | adk.dev/tools-custom/function-tools |
| `LongRunningFunctionTool` | same area; [adk-samples#169](https://github.com/google/adk-samples/issues/169), [adk-python discussion #2739](https://github.com/google/adk-python/discussions/2739) |
| `BasePlugin` + `before_model_callback`/`after_model_callback` | adk.dev/plugins — exact signature: `async def before_model_callback(self, *, callback_context: CallbackContext, llm_request: LlmRequest) -> None:`. **Caveat confirmed**: not invoked on the streaming path — only on `run_async` |
| `DatabaseSessionService` / `VertexAiSessionService` | adk.dev/sessions/session; [Google Developer forum thread](https://discuss.google.dev/t/using-databasesessionservice/287292). Gotcha: direct state mutation isn't persisted — must go through `append_event` |

**Overall conclusion**: every class/API name referenced in the existing SHRUTI design doc is real and current. Nothing hallucinated. Only correction needed: update any `google.github.io/adk-docs` citations to `adk.dev` (old links still resolve via redirect, so not urgent).

## The source YouTube video

Direct `WebFetch` of `youtube.com/watch?v=j8qW5poBkEU` returned only the static nav/footer shell — YouTube's watch page is JS-hydrated and not retrievable via plain fetch. Identity confirmed instead via YouTube's oEmbed endpoint (`noembed.com/embed?url=...`), which is authoritative for title/channel:

- **Title**: *"What is Gemini Enterprise Agent Platform?"*
- **Channel**: **Google Cloud Tech** (`youtube.com/@googlecloudtech`)
- **Publish date**: **2026-04-22** — corroborated by two independent WebSearch result summaries (not a page I read directly, so treat as search-corroborated rather than fetched-and-quoted), and tightly aligned with the confirmed Cloud Next '26 rebrand announcement date of 2026-04-22/23.

**Could not confirm**: an actual transcript, description text, or chapter/timestamp markers — every transcript-fetch attempt failed (`youtubetotranscript.com` and `youtubetranscript.com` both returned HTTP 403; the watch-page fetch had no hydrated content; a guessed Wikipedia URL 404'd). So the video's actual minute-by-minute content and any spoken claims **remain unverified** — what follows is inference from the surrounding launch material (the accompanying blog posts), not something read from the video itself:

- Platform = evolution of Vertex AI, unifying "model selection, model building, and agent building" with "new features for agent integration, DevOps, orchestration, and security" ([launch blog](https://cloud.google.com/blog/products/ai-machine-learning/introducing-gemini-enterprise-agent-platform)).
- Includes Agent Studio (no-code), Colab Enterprise Notebooks, ADK for code-based building, 200+ models via Model Garden, Agent Identity for governance.
- The Gemini Enterprise app itself got Agent Designer, Inbox, long-running agents, Skills, and Projects (per [release notes](https://docs.cloud.google.com/gemini-enterprise-agent-platform/release-notes) search summary).

**Do not cite this video for any specific claim, quote, or timestamp** until a transcript is actually retrieved — everything sourced from it in this wiki is channel/title/date only.
