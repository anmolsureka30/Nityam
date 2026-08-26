# Nityam — Error Register

Every mistake I can find across the four architecture documents, with evidence and a fix.
Ordered by how much damage it does. Version 0.1.

**How to use this:** E1–E6 change the architecture and should be resolved before you write code. E7–E12 are implementation traps that cost you a debugging night each. E13–E17 are gaps — things nothing currently handles.

---

## Critical — these change the design

### E1 · `TutorPipeline` runs Investigate → Teach on every turn. Fatal for voice.

**Where:** Technical Architecture §4.2, §3.2 step 3.

**The problem.** `SequentialAgent(investigate, teach)` is two sequential `gemini-3.5-flash` calls per student utterance. Investigate also does tool calls (File Search + trace search), so realistically 2.5–4 seconds before the tutor says a word. A voice turn budget is under a second to first audio. This design cannot produce a usable voice product.

It's also conceptually wrong: DeepTutor's Stage ① runs **once per task** to produce a plan of sub-goals, not once per conversational turn. Re-diagnosing from scratch on every utterance discards the plan you just made.

**Fix.** Investigate runs **once per concept**, ahead of need:
- at session open, for the planned concept (the student is still connecting)
- via `agent.schedule()` when a new concept is broached mid-session, so it runs *behind* the current turn
- never on the critical path

Its output lives in `state["plan"]`. The per-turn path is **Teach only** — one call, cached prefix, `thinkingLevel: minimal`.

**Cost of not fixing:** the demo feels laggy and judges notice within ten seconds.

---

### E2 · Two documents disagree about where the learner model lives.

**Where:** Technical Architecture §3.3 defines `LearnerProfile` as a Pydantic object in `session.state`. SMRITI v0.2 §2 defines it as a markdown wiki.

Both are current. Whoever codes first picks one and the other doc becomes a lie.

**Fix — explicit resolution:**

| Layer | Format | Why |
|---|---|---|
| In `session.state`, hot path | **rendered markdown string** + scalars (`mode`, `attempts`, `concept_id`) | It's what goes into the prompt. No serialization step. |
| On disk | **markdown wiki** | Readable, editable, versionable, auditable |
| In the write-back job | **Pydantic** | Validates the *operations* being applied — `append_note`, `set_status`, `open_confusion`. Never the profile itself. |

Pydantic validates *changes*, not *state*. Delete `LearnerProfile` from §3.3 and replace it with a pointer to SMRITI §3.

---

### E3 · Two different things are both called "mode."

**Where:** Technical Architecture §5.5 has tldraw canvas modes (`diagnosing` / `teaching` / `probing` / `reviewing`). SMRITI §5 has teaching modes (`socratic` / `worked-example` / `guided-practice` / `productive-failure` / `review-probe` / `direct`).

They will collide in code, in `session.state`, and in every conversation you have about this system.

**Fix.** One is authoritative, the other is derived.

```python
mode: TeachingMode                              # ← the source of truth

CANVAS_SCOPE = {                                # ← derived, never set directly
    "socratic":        "probing",
    "worked-example":  "teaching",
    "guided-practice": "teaching",
    "productive-failure": "probing",
    "review-probe":    "probing",
    "direct":          "teaching",
}
canvas_scope = CANVAS_SCOPE[mode]
```

Rename the state key to `canvas_scope` everywhere. One dial, not two.

---

### E4 · "Build the TraceStore over Postgres + pgvector" contradicts the wiki decision.

**Where:** Technical Architecture §4.5 recommends ~200 lines over Postgres + pgvector. SMRITI v0.2 §2 decided markdown + one six-column table.

**Fix.** The wiki *is* the trace store. Retrieval is:
- **BM25 via SQLite FTS5** over the markdown, plus
- optional local embeddings, fused with reciprocal rank fusion,
- **incrementally reindexed by content hash**, so only changed sections are re-embedded.

That's the LLM Wiki retrieval design, it runs locally, and it needs no pgvector, no hosted embedding service, and no second database. Markdown stays canonical; the index is a disposable cache you can delete and rebuild.

Delete the pgvector recommendation.

---

### E5 · The memory block is below Gemini's caching floor. Explicit caching silently never engages.

**Where:** SMRITI v0.2 §6 budgets ~3,050 tokens of standing context.

**The problem.** Gemini enforces a **hard 4,096-token minimum** for explicit context caching. At 3,050 tokens, `ContextCacheConfig(min_tokens=4096)` never fires — no error, no warning, you just pay full input price on every Brain call and wonder why the cost model was wrong.

**Fix.** Put the **full skill catalog in the cached prefix** — ~40 skills × ~80 tokens of name+description ≈ 3,200 tokens. Prefix becomes ~4,600 and caching engages.

This is a happy accident: the skill catalog *should* be in the prefix anyway (it's the most stable content you have), and including it is what makes the caching economics work. Cached input reads at 10% of the standard rate.

**Second-order trap:** ADK's cache manager fingerprints content and only creates a cache once it's *stable*. Anything that mutates per turn must sit after the prefix, or you thrash — repeatedly paying cache-creation cost with zero hits. See Harness Integration §2.1 for the exact ordering.

---

### E6 · Putting memory in the Live model's system instruction is a cost bomb.

**Where:** implied by every version of the architecture until now.

**The problem.** Live API billing: *"During each turn, the API bills for all context tokens, which encompasses both the conversation history and the system instruction provided by the user."*

A 3,000-token memory block, re-billed across ~60 turns, is 180,000 tokens of memory alone. On top of native audio accumulating at ~25 tokens/second (45,000 tokens for a 30-minute session), against a 128k Live context window.

**Fix.** Thin Live agent. Memory never enters the Live session. Full argument in Harness Integration §1.

---

## Implementation traps — one debugging night each

### E7 · `before_model_callback` returning an `LlmRequest` crashes on Agent Engine.

Known bug (`adk-python` #3798): type confusion at `_nl_planning.py:79` when a callback returns an `LlmRequest`. Reported with no workaround other than disabling the callback entirely.

**Fix.** **Mutate `llm_request` in place and return `None`.** Never return the request object. Applies to every `before_model_callback` you write, including the mode-scoping filter.

---

### E8 · Mutating `agent.tools` at runtime is unsupported.

Open question (`adk-python` #3647): whether assigning `ctx.agent.tools` in a callback is the supported path. It isn't documented as such, and agents are Pydantic models where attribute assignment has surprising semantics.

**Fix.** Filter `llm_request.config.tools[*].function_declarations` in `before_model_callback` instead. Same effect, documented mechanism, no shared-mutable-agent hazard across concurrent sessions — which is the real danger, since one agent object serves all students.

---

### E9 · Enabling context compaction with a `SequentialAgent` root crashes at run time.

`AttributeError: 'SequentialAgent' object has no attribute 'canonical_model'` — compaction needs a model to summarize with, and workflow agents don't have one.

**Fix, in order of preference:**
1. **Don't enable compaction on the Brain.** Its context is rebuilt from memory each invocation rather than accumulated, so there's nothing to compact. This is the right answer.
2. If you must, pass an explicit `LlmEventSummarizer` with its own model.

---

### E10 · `LiveRequestQueue` reuse corrupts the next session.

The close signal persists in the queue and terminates the next session's sender loop. This is documented and it still catches people.

**Fix.** One fresh `LiveRequestQueue` per WebSocket connection. Construct it in the connection handler, close it in the `finally`. Never hold one at module scope.

---

### E11 · One Live server event can contain multiple parts.

Audio and transcript arrive together in a single event. Code that does `event.content.parts[0]` silently drops the transcript, which means your journal buffer is missing half its content and you won't notice until write-back produces nonsense.

**Fix.** Always iterate `parts`. Route by part type, never by index.

---

### E12 · Barge-in cannot be classified at the moment it happens.

**Where:** Technical Architecture §6.5 treats barge-in as a signal meaning "I already know this" or "you lost me."

Both are real, and **you cannot tell which one from the barge-in itself.** Classifying in real time gives you a coin flip written into a child's learner model.

**Fix.** Record the barge-in with its timestamp and what the tutor was mid-sentence about. **Classify at write-back**, from the utterance that followed:

| What they said next | Classification |
|---|---|
| Correct completion of the tutor's sentence | `already_knew` → concept was under-estimated |
| A question about the same step | `lost` → explanation too dense |
| Change of subject | `disengaged` → pacing or motivation |

This generalises: **any signal whose meaning depends on what follows it must be classified offline.** That's most of them.

---

## Gaps — nothing currently handles these

### E13 · Nothing defines "session end," and the write-back is the entire memory system.

If the student closes the tab — the normal case — no memory is written. Everything SMRITI does depends on a trigger that doesn't exist.

**Fix.** Three triggers, all idempotent, keyed on session id:

```python
END_TRIGGERS = [
    "explicit",          # student taps "done"
    "idle_90s",          # 90s with no audio in either direction
    "sweeper",           # cron: any session with no event in 10 min
]
```

The sweeper is the one that matters. The other two are optimisations on top of it.

---

### E14 · An unwritten buffer blocks the next session.

Student closes, immediately reopens. Write-back hasn't run. The new session loads stale memory and the previous 20 minutes vanish.

**Fix.** The buffer is already durable — it's in `session.state`, persisted as `state_delta`. On session open:

```python
pending = await sessions.find_unwritten(student_id)
if pending:
    if pending.size < FAST_THRESHOLD:
        await write_back(pending)             # ~2 s, blocking, acceptable
    else:
        state["recent_unconsolidated"] = pending.summary   # inject as raw context
```

The second branch matters: an unconsolidated buffer is still *usable* as context even before it's been distilled into the wiki.

---

### E15 · Evidence citations have no resolver.

`[→ 2026-08-24 #12]` appears throughout SMRITI as the mechanism that makes claims auditable. Nothing turns it into a real location. Without a resolver it's decorative, the "why do you think that about me?" button doesn't work, and the M3 provenance test can't run.

**Fix.** Two columns:

```sql
CREATE TABLE citation (
    ref        TEXT PRIMARY KEY,   -- "2026-08-24#12"
    student_id TEXT NOT NULL,
    file_path  TEXT NOT NULL,      -- students/anmol/sessions/2026-08-24.md
    line       INT NOT NULL
);
```

Written by the same job that writes the session page. Ten lines of code, and it's the difference between a claim you can defend to a parent and one you can't.

---

### E16 · Skill *bodies* need loading mid-turn, which is I/O in the hot path.

Progressive disclosure means the body loads when the skill triggers. That's a file read during a turn — exactly what §3 of the integration doc forbids.

**Fix.** Split by type:
- **Method skills** — exactly one active at a time, and mode changes are already a known event. Preload at session open, swap on `switch_mode`. Never fetched mid-turn.
- **Artifact skills** — fetched by the artifact tool, which is already an async operation the student is visibly waiting through. Acceptable.

---

### E17 · Background agents have no defined memory access, and the obvious approach breaks on Vertex.

The Scheduler, PrepAgent and Curator run with no session. Nothing says how they read memory.

**Fix.** They read the wiki directly (I/O is free when nobody's waiting) and seed a synthetic session with `state_delta`.

⚠️ **Do not reach for ADK user state here.** `VertexAiSessionService.get_user_state()` raises `NotImplementedError` — the Agent Runtime API doesn't expose user state independently of a session, and the documented workaround is to enumerate sessions with `list_sessions` and fetch each one. Use `DatabaseSessionService` over Cloud SQL, and keep the `schedule` table (not ADK state) as the source of truth for due dates. The table is queryable by a cron job without instantiating a single agent, which is exactly what you want.

---

## Corrections from external verification (v0.2 additions)

A full research pass (ADK source, official docs, the DeepTutor paper/repo, tldraw, learning-science citations, and the Gemini Enterprise Agent Platform docs — all fetched and cross-checked directly, not recalled from training) found the original four documents unusually accurate. These five corrections are what didn't hold up exactly as written.

### E18 · Model names are stale

**Where:** every doc, throughout. `gemini-3.5-flash` is real but now "legacy" — superseded twice. `gemini-3.1-flash-image-preview` / `gemini-3-pro-image-preview` don't exist under those exact IDs.

**Fix.** Current lineup as of 2026-08-26: `gemini-3.7-flash` is the flagship reasoning/teaching model; `gemini-3.5-flash-lite` or `gemini-3.1-flash-lite` for the cheap routing tier; `gemini-3.1-flash-live-preview` is still correct for voice; image generation is `gemini-3.1-flash-image` and `gemini-3-pro-image` — both GA, neither carries a `-preview` suffix. Centralize model IDs in one config module (this was already R7 in the original risk list — now confirmed as live, not hypothetical).

---

### E19 · The tool-scoping fix names the wrong callback

**Where:** Harness Integration §5.1, citing adk-python issue #3647 as justification for filtering `llm_request.config.tools[*].function_declarations` inside `before_model_callback`.

**The problem.** Verified directly against the issue: the unsupported-mutation part is correct (`agent.tools` resolves during preprocessing, before callbacks run), but the maintainers' actual endorsed fix in #3647 is overriding `ctx.agent.tools` in **`before_agent_callback`**, not filtering declarations in `before_model_callback`.

**Fix.** Move the mode-scoping logic to `before_agent_callback`. The `function_declarations`-filtering technique is real ADK API surface elsewhere, but it isn't what this specific issue endorsed — don't cite it as the source for that technique.

---

### E20 · The `SequentialAgent` + compaction crash is already patched

**Where:** Error Register E9, Session Lifecycle §6.3 — both cite an `AttributeError: 'SequentialAgent' object has no attribute 'canonical_model'`.

**The problem.** This was accurate from roughly Nov 2025 through early Feb 2026. A guard shipped between commits `a88e8647`→`485fcb84` and is live in the current `google-adk` release (2.7.1, 2026-08-17): a non-`LlmAgent` root now raises a clean `ValueError` ("No LlmAgent model available for event compaction summarizer") instead of the bare `AttributeError`.

**Fix.** The underlying advice is unchanged — don't enable compaction on the Brain, its context is rebuilt from memory each invocation, not accumulated — just don't design defensively around a crash mode that no longer occurs. Update any error-handling code that pattern-matches on the old `AttributeError` string.

---

### E21 · Shruti's configured embedding model is stale — CORRECTION: this entry was itself wrong, and applying its fix broke a real, working pipeline

**Where:** `shruti/config.py`'s `Models().embedder`.

**The original problem (as filed).** The Gemini Enterprise Agent Platform's embeddings page lists the *product name* "Gemini Embedding 2" as current, and this entry proposed updating `Models().embedder` to match — from `gemini-embedding-001` to (implicitly) `gemini-embedding-2`.

**What actually happened.** That literal translation was applied at some point without live verification, and `gemini-embedding-2` is not a real API model id — every embedding call failed with a 404, silently, on every single Shruti run once the embedding stage was actually wired up in Phase 0.5. Confirmed 2026-08-26 by calling `client.aio.models.embed_content` directly against four candidate ids: `gemini-embedding-2` → 404. `gemini-embedding-001` → **succeeds**, returns a real 3072-dim vector. `text-embedding-004`/`text-embedding-005` → 400 (don't support `output_dimensionality=3072`, a separate incompatibility, not the fix). The original `gemini-embedding-001` this entry called "stale" was correct the entire time — product-name pages and API model ids are not the same namespace, and this is exactly the failure mode `memory_nityam_architecture/README.md`'s Phase 0.5 gap notes had already flagged as a risk before it was confirmed as a real regression.

**Fix (applied, live-verified, not hypothetical).** `Models().embedder` is `"gemini-embedding-001"` again. **Never translate a product-name doc page into an API model id without a live call to confirm it** — `client.models.list()` or a direct `embed_content`/`generate_content` probe, the same way this correction was found.

---

### E22 · The context-caching floor is model-generation-dependent, not a flat 4,096

**Where:** Harness Integration §2.1, E5 — states a hard 4,096-token minimum for explicit caching.

**The problem.** ADK's `ContextCacheConfig.min_tokens` itself defaults to 0 (a user-configurable gate, not a hardcoded number). The 4,096-token floor is Gemini's own model-level minimum, and it's specific to the **Gemini 3** family — Gemini 2.5 models floor at **2,048** tokens instead.

**Fix.** No change to E5's actual recommendation — Nityam targets the Gemini 3 family (E18), so 4,096 is the correct number to design against, and pushing the cached prefix to ~4,600 by including the skill catalog is still exactly right. Just cite it as "the Gemini 3 floor," not a universal constant, so the reasoning doesn't mislead if a future model swap changes the generation.

---

## Two things that are right and worth defending

**Barge-in as a signal is a genuinely good idea** — it's free from the Live API, it means something, and nobody uses it. Just classify it offline (E12).

**The citation invariant is the strongest thing in the whole design.** Every behavioural claim resolving to a real session turn is what separates a learner model from a horoscope, and it's the demo beat with the most weight for a school or a parent. E15 is what makes it real; do it early.

---

## Resolution checklist

| | Owner | Blocks |
|---|---|---|
| E1 — move Investigate off the per-turn path | architecture | voice latency |
| E2 — delete `LearnerProfile` from §3.3, point to SMRITI §3 | docs | ambiguity |
| E3 — rename canvas modes to `canvas_scope`, derive from `mode` | architecture | code collisions |
| E4 — delete the pgvector recommendation | docs | scope creep |
| E5 — skill catalog into the cached prefix | implementation | cost model |
| E6 — thin Live agent | architecture | cost + context window |
| E7–E11 | implementation | debugging time |
| E12 — barge-in classified at write-back | implementation | model quality |
| E13–E17 | implementation | correctness |
| E18 — centralize and update model IDs | docs + implementation | cost, model availability |
| E19 — move tool-scoping to `before_agent_callback` | implementation | correctness, avoids an unsupported pattern |
| E20 — drop defensive handling for the patched compaction crash | implementation | dead code, minor |
| E21 — update Shruti's embedder to Gemini Embedding 2 | implementation | blocks nothing today, fix alongside Phase 0 |
| E22 — cite the cache floor as Gemini-3-specific | docs | avoids misleading future model swaps |

*v0.2. E1, E5 and E6 are the three that would have shipped as real bugs in the original design. E18–E22 are corrections found by direct verification against ADK source, official docs, and the platform docs, added 2026-08-26 — see `google_platform_integration.md` for the platform-service evaluation this verification pass also produced.*