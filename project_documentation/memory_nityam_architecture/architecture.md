# Nityam — Architecture (v1.0 — simplified)

Supersedes `nityam_initial_architecture.md`. That version specified a five-plane architecture
with a tldraw canvas, an `Investigate → Teach` sequential pipeline, FSRS scheduling, and a
background plane of four proactive agents. This version cuts all of that for a first build:
one voice loop, one memory layer, one sub-agent. The full prior research — DeepTutor's eight
ideas, the tldraw canvas design, the background-plane pattern — is preserved in git history and
summarized in `deferred.md`; none of it is wrong, it's just not this pass.

---

## 1. What Nityam is

A voice-first tutor, grounded in the student's own classroom lecture (via Shruti) and uploaded
books, that remembers the student across sessions and can generate an interactive artifact —
a worked diagram, an explorable simulation, a quiz — when a visual representation teaches
better than words alone. The artifact appears in the canvas frontend (`sub_modules/canvas`);
an avatar inside that canvas is a visual layer only, out of scope for this architecture.

---

## 2. Three agents, one shared memory layer

```
Student's voice (PCM)
        │
┌───────▼─────────────────────────────────────────────────────┐
│  VoiceAgent — Gemini Live, native audio, run_live()          │
│  Fixed, minimal instruction. No memory of its own.           │
│  sub_agents=[TutorAgent]  (TutorAgent declares mode='single_turn')│
└───────┬─────────────────────────────────────────────────────┘
        │ tool call (framework-wrapped) — parent (VoiceAgent) stays
        │ in control, gets a result back, speaks it. Never a transfer.
┌───────▼─────────────────────────────────────────────────────┐
│  TutorAgent — the reasoning / intelligence layer             │
│  Tools: search_grounding, get_dpm, get_teaching_memory,      │
│         log_turn                                             │
│  sub_agents=[ArtifactAgent] (mode='single_turn')             │
└───────┬─────────────────────────────────────────────────────┘
        │ tool call, when a visual/interactive
        │ representation is the right pedagogical move
┌───────▼─────────────────────────────────────────────────────┐
│  ArtifactAgent — wraps sub_modules/artifact_generator        │
│  ArtifactSpec → Gemini → IR → validate → artifact reference  │
│  Same read tools as TutorAgent, to calibrate difficulty/theme│
└────────────────────────────────────────────────────────────┘
```

No "Ear/Brain" split — that framing described the same shape but named it in a way that read
as two competing brains rather than one voice layer handing off to one reasoning layer. `SMRITI`
stays as the memory layer's name.

**The exact ADK mechanism — verified against the installed `google-adk==2.7.1` source
(`sub_modules/shruti/.venv/.../google/adk/`), not a doc-page summary.** Three real options exist:
`sub_agents=[...]` with the child left in its default `mode='chat'` (LLM-driven *transfer* —
control permanently moves to the child), wrapping a child in `tools=[AgentTool(child)]` directly,
or `sub_agents=[...]` with `mode='single_turn'` declared **on the child**. The third is correct
here, and it isn't a style preference — `AgentTool`'s own docstring in the installed source says
plainly: *"Direct usage of `AgentTool` is discouraged... prefer setting `mode='single_turn'` on
the sub-agent and attaching it via `sub_agents=[...]` instead."* `LlmAgent.model_post_init` shows
why the two are equivalent in effect: a `mode='single_turn'` sub-agent is automatically wrapped
in a `_SingleTurnAgentTool` (a thin `AgentTool` subclass) and appended to the parent's own
`tools` list — so declaring `mode='single_turn'` on `TutorAgent` and attaching it via
`VoiceAgent(sub_agents=[tutor_agent])` produces exactly the "parent stays in control, gets a
result back" behavior `AgentTool` would, through the framework's currently-recommended path
rather than the discouraged one:

```python
tutor_agent = LlmAgent(
    name="TutorAgent",
    model="gemini-3.7-flash",
    mode="single_turn",          # ← runs as a callable tool, never takes over the session
    instruction=TUTOR_INSTRUCTION,
    tools=[search_grounding, get_dpm, get_teaching_memory, log_turn],
    sub_agents=[artifact_agent], # artifact_agent also declares mode="single_turn"
)

voice_agent = LlmAgent(
    name="VoiceAgent",
    model="gemini-3.1-flash-live-preview",
    instruction=VOICE_INSTRUCTION,   # small, fixed, no memory
    sub_agents=[tutor_agent],
)
```

`ArtifactAgent` is wired the same way one level down — `mode='single_turn'`, attached via
`TutorAgent`'s own `sub_agents=[...]`.

**This also resolves the transcription question, not just leaves it pending.** Reading
`flows/llm_flows/agent_transfer.py` directly: the LLM-driven transfer mechanism (the one that
needs input/output transcription for its bookkeeping) explicitly excludes `single_turn`- and
`task`-mode sub-agents from its transfer-target list — a `single_turn` child never goes through
`agent_transfer.py` at all, it's invoked purely as a tool call (`_SingleTurnAgentTool.run_async`
→ `tool_context.run_node(...)`). The forced-transcription behavior is real, but it belongs to
`mode='chat'` transfer, which this design doesn't use anywhere in the `VoiceAgent → TutorAgent →
ArtifactAgent` chain.

**A confirmed side benefit:** `before_model_callback` / `before_tool_callback` don't fire during
`run_live` — only on `run_async`. Because `TutorAgent` executes as a normal agent invocation
(triggered by a tool call, not running inside the Live model's own flow), any guardrails added
to it later get the full normal callback lifecycle. Nothing about mode-guarding or tool-scoping
needs a live-specific workaround.

---

## 3. Voice wiring — what stays load-bearing from prior research

- **Live bills all context tokens — including the system instruction — on every turn.** This is
  why `VoiceAgent`'s instruction has to stay small regardless of the delegation mechanism in §2:
  a memory-sized system instruction re-billing on ~60 turns of a session is real money and real
  latency, not a style preference. Memory belongs in `TutorAgent`, never in `VoiceAgent`'s
  instruction.
- **One `LiveRequestQueue` per WebSocket connection, never reused.** The close signal persists in
  the queue and terminates the next session's sender loop if reused. Construct it in the
  connection handler, close it in the `finally`.
- **One Live server event can carry multiple parts** (audio + transcript together). Code that
  reads `event.content.parts[0]` silently drops whichever part isn't first. Always iterate
  `parts`, route by type.
- **Long sessions need two independent clocks handled:** the WebSocket connection itself
  (`GoAway` arrives with a resumption handle before a ~10 minute timeout) and the Live session's
  own context window (`contextWindowCompression` with a sliding window, for anything past ~15
  minutes uncompressed). Compression on the Live side is safe specifically *because* memory
  never lived there to begin with — nothing important is in the window it might discard.

## 4. Model IDs

Don't hardcode a specific model version string in this document or in code without verifying it
live — this project has already been burned twice by a stale/hallucinated model id shipping
silently (a 404'ing embedding model, a product-name page translated into a non-existent API id;
see git history on `nityam_error_registory.md` if the detail is ever needed). Centralize model
ids in one config module, and confirm current ids by listing available models at build time
rather than trusting training data — the `google-agents-cli-adk-code` skill has the exact
command.

**Live-verified against `client.models.list()` on 2026-08-26, using the project's existing
`GOOGLE_API_KEY`** (not from training data — re-run the same listing before relying on these
again if much time has passed):

| Role | Model id | Notes |
|---|---|---|
| `VoiceAgent` (native audio, bidi) | `gemini-3.1-flash-live-preview` | The only general-purpose live model available; `gemini-3.5-live-translate-preview` also exists but is translation-specific |
| `TutorAgent` / `ArtifactAgent` (reasoning) | `gemini-3.7-flash` | Latest non-lite Flash tier confirmed available. `gemini-flash-latest` also exists as a floating alias — pin to the explicit version instead, for reproducible behavior |

Both are set in one `config.py`, never inlined at each call site.

---

## 5. Operational notes

- **`before_model_callback` must mutate in place and return `None`.** Returning an `LlmRequest`
  is a known crash on some ADK versions. Applies to every callback of this type.
- **Don't mutate `agent.tools` at runtime.** Not a supported path; agents are Pydantic models
  and one agent instance serves every session. Filter `llm_request.config.tools[*]` in a
  callback instead, if tool-scoping is ever added.
- **Use factory functions for sub-agents**, not module-level instances — passing an
  already-parented agent object into a second parent raises `"agent already has a parent"`.
- **Context caching** is a real, well-understood ADK feature (`ContextCacheConfig`, a
  generation-dependent minimum token floor) but isn't a v1 concern: nothing in this design puts
  a large, stable prefix in front of the model the way the old skill-catalog design did. Revisit
  once `TutorAgent`'s standing context is large enough for caching to matter.

---

## 6. Build order

1. `TutorAgent` alone, text mode (`run_async`), wired to the memory tools in `memory_layer.md`
   §3, against one hand-seeded student (`dpm_profile` + `teaching_memory` + a handful of
   `grounding_chunk` rows). Proves the memory shapes hold up in real use before voice is in the
   loop at all.
2. Wrap `ArtifactAgent` around the existing `sub_modules/artifact_generator` pipeline, declared
   `mode="single_turn"` and attached via `TutorAgent(sub_agents=[artifact_agent])`. Prove one
   artifact end to end from a text conversation, including the evidence callback (`onEvidence` in
   the artifact README) reaching `log_artifact_evidence`.
3. Add `VoiceAgent` on top (`run_live`), with `sub_agents=[tutor_agent]` (`TutorAgent` already
   declares `mode="single_turn"`). Prove the voice loop and check real latency.
4. `close_session` — the deterministic pass plus the one Reflect call. Confirm citations
   (`session_id#turn`) actually resolve against a written `session_log`.
5. Frontend: the canvas mounts an artifact by reference when `ArtifactAgent` returns one.

Nothing past step 5 is in scope for this pass — no spaced repetition, no background wake, no
multi-device locking, no curator. See `deferred.md`.

---

*v1.0. Supersedes `nityam_initial_architecture.md`. §2 (the three-agent topology and the
`mode='single_turn'` decision) and §3 (the load-bearing voice facts) are the parts that would break the
design if changed casually.*
