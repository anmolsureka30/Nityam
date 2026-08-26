# SMRITI × Harness — Runtime Integration

How the memory layer binds into the ADK agent at run time.
Companion to *SMRITI v0.2* and *Nityam — Technical Architecture*. Version 0.1.

> **Scope.** The memory design is settled (markdown wiki + one schedule table + mode skills). This document is only about *wiring it into a live voice agent without breaking it.* Errors found in the existing architecture are in the companion `Errors_and_Fixes` doc; timing and operations are in `Session_Lifecycle`.

---

## 1. The decision everything else follows from

> **The Live model is a mouth, not a brain. Memory never enters the Live session.**

Four facts from the Live API docs force this, and any one of them alone would be enough:

| Fact | Consequence |
|---|---|
| Live bills **all context tokens including the system instruction, on every turn** | A 3,000-token memory block re-bills on all ~60 turns of a session — 180k tokens of pure memory |
| Native audio accumulates at **~25 tokens/second** | A 30-minute session is ~45,000 tokens of audio before anything else |
| Live models have a **128k context window** | Audio + memory + history collide fast |
| Compression **discards the oldest turns** (`SlidingWindow`) | Anything the tutor established at minute 2 is gone by minute 25 |

And separately: Live models are a different model family from `gemini-3.5-flash`, so the reasoning has to happen somewhere else regardless.

### 1.1 The split

```
   student's voice
        │  PCM 16 kHz
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  EAR & MOUTH        gemini-3.1-flash-live-preview               │
│                                                                  │
│  system instruction: ~300 tokens, FIXED for the session          │
│    · persona + language rule (code-mix, never translate)         │
│    · one hard rule: "you do not teach — call tutor()"            │
│    · 3 tools: tutor() · acknowledge() · end_session()            │
│                                                                  │
│  Decides ONE thing per turn: is this a teaching turn?            │
│    no  → answers directly            (~350 ms, no Brain call)    │
│    yes → calls tutor(utterance)      (Brain runs)                │
└──────────────────────────┬───────────────────────────────────────┘
                           │ tutor(utterance)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  BRAIN              gemini-3.5-flash  ·  runner.run_async()      │
│                                                                  │
│  Holds ALL of memory. Rebuilt from state on every invocation —   │
│  never accumulated, so compaction cannot erode it.               │
│                                                                  │
│  · cached prefix: identity + skill catalog + LEARNER.md + mode   │
│  · volatile: concept page + session state + last 3 turns         │
│  · tools: filtered by mode                                       │
│                                                                  │
│  Returns: { say: str, canvas_ops: [...], mode_change?: str }     │
└─────────────────────────────────────────────────────────────────┘
```

**Why this is the right architecture and not a workaround:**

1. Compression can't hurt you if the Live model wasn't carrying the important state.
2. Mode-scoped tools are impossible on the Live side (tools are declared in the setup message and the connection is stateful). They're trivial on the Brain side.
3. It removes the "sub-agents + Live forces transcription" problem entirely — the Live agent has no sub-agents.
4. It's the same shape as DeepTutor's own design, where every entry point converges on a single orchestrator rather than each surface holding its own model.

**The one thing the Live model must be told about memory:** nothing. Not the student's name, not their weaknesses. If it needs to sound personal, the Brain gives it the words.

---

## 2. Memory Context Assembly

One function, called once per Brain invocation. Its job is to produce the exact prompt in the exact order.

### 2.1 The order is not cosmetic

```
┌── CACHED PREFIX ── stable for the session ────────────────  ~4,600 tok
│  ① Tutor identity + the four hard rules                          300
│  ② Skill catalog: name + description × ~40 skills              3,200
│  ③ LEARNER.md (verbatim)                                         400
│  ④ Active method skill body (socratic / worked-example / …)      700
├── VOLATILE SUFFIX ── changes per turn ──────────────────────    ~900 tok
│  ⑤ Active concept page (its status line mutates)                 250
│  ⑥ Session state: mode, attempts, plan step, canvas refs         200
│  ⑦ Last 3 turns, transcript only                                 450
└── TOOLS ── filtered by mode
```

Two hard constraints set this layout:

**Gemini enforces a 4,096-token minimum for explicit context caching.** SMRITI v0.2's ~3,050-token standing budget is *below the floor* — explicit caching would silently never engage and you'd pay full price on every Brain call. Including the whole skill catalog in the prefix pushes it to ~4,600 and turns caching on. (See `Errors_and_Fixes` E5.)

**ADK's cache manager fingerprints content and only creates a remote cache once it's stable.** Anything that changes per turn must sit *after* the prefix, or you thrash — repeatedly creating and discarding caches, paying creation cost with no hit.

```python
app = App(
    name="nityam",
    root_agent=brain,
    context_cache_config=ContextCacheConfig(
        min_tokens=4096,      # Gemini's hard floor. Below this, no cache.
        ttl_seconds=1800,     # a session
        cache_intervals=10,   # refresh after 10 invocations
    ),
)
```

### 2.2 What invalidates the cache, and how often

| Change | Frequency | Cache impact |
|---|---|---|
| Concept page status line | 1–3× per session | none — it's in the suffix |
| Session state | every turn | none — suffix |
| **Method skill body (mode switch)** | 2–3× per session | **invalidates** |
| LEARNER.md | never mid-session | none |

Mode switching is the only thing that breaks the cache, and it happens two or three times an hour. That's an acceptable trade for the ~90% discount on cached input the rest of the time.

**Do not put the concept page in the prefix**, however tempting. Its status line is exactly the thing that changes when the student makes progress.

### 2.3 The assembler

```python
def assemble(state: dict) -> tuple[str, str]:
    """Returns (cached_prefix, volatile_suffix). Pure function. No I/O."""
    prefix = "\n\n".join([
        IDENTITY,                                   # ① constant
        state["skill_catalog"],                     # ② loaded at session open
        state["learner_md"],                        # ③ loaded at session open
        state["method_skill_body"],                 # ④ swapped on mode change
    ])
    suffix = "\n\n".join([
        state["concept_page"],                      # ⑤
        render_session_state(state),                # ⑥
        render_recent_turns(state["buffer"][-3:]),  # ⑦
    ])
    return prefix, suffix
```

Note the signature: **no I/O**. Everything it reads is already in `session.state`. That property is the whole point of §3.

---

## 3. The read path — zero I/O in the hot path

> **Rule: by the time the student finishes speaking, everything the Brain needs is already in RAM.**

Reading a markdown file from GCS costs 50–200 ms. A Postgres round trip costs 5–20 ms. Neither is affordable inside a voice turn, and both are avoidable, because a tutoring session is about *one topic* — you know almost everything you'll need before it starts.

### 3.1 Session open (the only time memory is read from disk)

```python
async def open_session(student_id: str, intent: SessionIntent) -> dict:
    """~400 ms, all parallel, happens while the student is still connecting."""
    learner, due, catalog = await asyncio.gather(
        wiki.read(f"students/{student_id}/LEARNER.md"),
        schedule.due_for(student_id),                # SQL, indexed on (student, due)
        skills.catalog(),                            # cached process-wide
    )

    concept_ids = pick_concepts(intent, due)         # 1 planned + up to 2 due
    concept_ids += prerequisites_of(concept_ids)     # ← the likely pivots

    pages = await wiki.read_many(
        f"students/{student_id}/concepts/{c}.md" for c in concept_ids[:5]
    )

    mode = select_mode(pages[0], SessionState.fresh(), learner)

    return {
        "learner_md":        learner,
        "skill_catalog":     catalog,
        "concept_pages":     {c: p for c, p in zip(concept_ids, pages)},
        "concept_page":      pages[0],
        "mode":              mode,
        "method_skill_body": skills.body(f"methods/{mode}"),
        "due_concepts":      due,
        "buffer":            [],
    }
```

**Prefetching prerequisites is the highest-value line here.** When a student gets stuck on completing the square, the next thing they ask about is almost always a prerequisite — expanding brackets, or the meaning of a square. Having those pages already loaded turns the most likely pivot into a zero-latency one.

### 3.2 Per turn

Read from `session.state`. Nothing else. The filesystem and the database are untouched for the entire duration of a turn.

### 3.3 The one sanctioned exception

```python
async def recall(query: str, tool_context: ToolContext) -> dict:
    """Search the student's own history. Model-invoked only, never automatic."""
    hits = await wiki_index.search(
        query, student=tool_context.state["student_id"], k=5
    )
    return {"results": [h.excerpt for h in hits]}
```

This does I/O — ~80 ms against a local SQLite index — and that's fine, because the model *chose* to call it and the student is already waiting on a tool. The index is FTS5 + optional local embeddings, fused, rebuilt incrementally by content hash. No pgvector, no hosted vector service; the wiki files remain canonical.

**Never make this automatic.** Preloading past sessions is the single fastest way to blow the context budget on material that is almost never relevant.

---

## 4. The write path — buffer in RAM, write on close

> **Rule: nothing writes to the wiki during a session. Ever.**

Two reasons. First, latency — you cannot afford a file write inside a turn. Second, and more important: **you don't know what a turn meant until you see what followed it.** A student going quiet might be thinking or might be lost. A barge-in might be "I've got it" or "you lost me." Writing your interpretation immediately means writing it wrong.

### 4.1 During the session

```python
class JournalPlugin(BasePlugin):
    """Append to RAM. No disk. No LLM. No embedding."""
    async def on_event_callback(self, *, invocation_context, event):
        invocation_context.session.state["buffer"].append({
            "t":    event.timestamp,
            "kind": classify_cheap(event),       # pure Python, no model call
            "text": extract_text(event),
        })
```

`classify_cheap` is a dict lookup on event type, not a classifier. Salience scoring, misconception detection, and mode-effectiveness judgement all happen at write-back, where they're cheap and better-informed.

**The one durable write during a session** is `tool_context.state`, which ADK persists as a `state_delta` on the event. That's how mode, attempt count and plan step survive a crash. It's small, it's traceable back to the event that caused it, and it's the mechanism the whole durability story rests on.

```python
def check_attempt(verdict: str, tool_context: ToolContext) -> dict:
    tool_context.state["attempts"] += 1              # → state_delta, durable
    tool_context.state["last_verdict"] = verdict
    new_mode = select_mode(...)
    if new_mode != tool_context.state["mode"]:
        tool_context.state["mode"] = new_mode         # durable
        tool_context.state["method_skill_body"] = skills.body(f"methods/{new_mode}")
    return {"mode": new_mode}
```

### 4.2 Session close

One background job. Reads the buffer, emits append-only operations against the wiki. Detailed in `Session_Lifecycle` §3.

---

## 5. Mode enforcement in the harness

Two layers, because one is not enough.

### 5.1 Layer 1 — the model never sees the tool

```python
MODE_TOOLS = {
    "socratic":        {"ask_probe", "give_hint", "draw", "check_attempt",
                        "flag_gap", "switch_mode"},
    "worked-example":  {"draw", "derive", "narrate_step", "emit_twin_problem",
                        "check_attempt", "switch_mode"},
    "guided-practice": {"do_step", "request_step", "draw", "check_attempt",
                        "switch_mode"},
    "review-probe":    {"emit_quiz", "check_attempt", "switch_mode"},
    "direct":          {"answer", "draw", "cite"},
}

def scope_tools(callback_context, llm_request) -> None:
    """Filter the tool list to the active mode.

    ⚠️ Mutate in place and return None. Returning an LlmRequest triggers a
    known AttributeError in _nl_planning.py on Agent Engine (adk-python #3798).
    ⚠️ Do NOT mutate agent.tools — runtime mutation is unsupported (#3647).
    """
    allowed = MODE_TOOLS[callback_context.state["mode"]]
    for decl in llm_request.config.tools:
        decl.function_declarations = [
            f for f in decl.function_declarations if f.name in allowed
        ]
    return None
```

`reveal_solution` is simply absent from the declaration list while mode is `socratic`. There is no prompt to argue with.

### 5.2 Layer 2 — the backstop

```python
class ModeGuard(BasePlugin):
    async def before_tool_callback(self, *, tool, tool_args, tool_context):
        mode = tool_context.state["mode"]
        if tool.name not in MODE_TOOLS[mode]:
            log.warning("mode_violation", tool=tool.name, mode=mode)
            return {"blocked": True,
                    "reason": f"{tool.name} unavailable in {mode} mode."}
        return None
```

Layer 1 should make Layer 2 unreachable. Log every time it isn't — that's your signal that the filter has a hole.

### 5.3 Mode is state, not conversation

`session.state["mode"]` changes through exactly two paths:

1. `check_attempt()` — evidence of progress or of being stuck
2. `switch_mode()` — an explicit, logged, student-initiated request, itself gated (a request for `direct` on a non-durable concept returns `guided-practice`)

No other route exists. Persuasion does not compile.

---

## 6. Long sessions

Two independent clocks, both shorter than a real tutoring session.

| Clock | Limit | Handling |
|---|---|---|
| **WebSocket connection** | ~10 min | `GoAway` arrives with `timeLeft` → reconnect with the resumption handle. Tokens valid 2 h. |
| **Live session (audio-only)** | 15 min uncompressed | `contextWindowCompression` with `SlidingWindow` → unlimited duration |

```python
live_config = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    context_window_compression=types.ContextWindowCompressionConfig(
        trigger_tokens=48_000,
        sliding_window=types.SlidingWindow(target_tokens=12_000),
    ),
    session_resumption=types.SessionResumptionConfig(),
    input_audio_transcription=types.AudioTranscriptionConfig(),
    output_audio_transcription=types.AudioTranscriptionConfig(),
)
```

### 6.1 Compression discards; it does not summarize

The docs are explicit: *"Context compression will cause conversation history loss."* `SlidingWindow` operates by discarding content at the beginning of the context window.

For a normal voice agent that's a serious problem. For us it's nearly harmless, **because the Live model was never carrying the state that matters.** The Brain rebuilds its context from `session.state` on every invocation; the buffer holding the session journal is in ADK state, not in the Live model's window.

One thing you *can* rely on: **the system instruction is never discarded and stays at the beginning of the context window.** That's why the Live agent's hard rule — *"you do not teach, you call tutor()"* — belongs in the system instruction and nowhere else.

### 6.2 Re-anchoring after reconnect

Same pattern as a coding agent re-reading its project file after compaction. On every reconnect, send a compact orientation before resuming audio:

```python
async def reanchor(session, state):
    await session.send_client_content(turns=types.Content(role="user", parts=[
        types.Part(text=(
            f"[context] Continuing. Topic: {state['concept_title']}. "
            f"Mode: {state['mode']}. "
            f"Last exchange: {state['buffer'][-1]['text'][:120]}"
        ))
    ]), turn_complete=False)
```

~120 tokens. Cheap insurance against the model losing the thread mid-lesson.

### 6.3 Do not enable ADK compaction on the Brain

It looks like the obvious thing to configure and it is the wrong call here.

The Brain's context is **rebuilt from memory each invocation**, not accumulated across the session. The only part that grows is the last-3-turns window, which is bounded by construction. Compaction would spend an LLM call per interval summarizing something that was never going to overflow.

It would also break: `EventsCompactionConfig` needs a model to summarize with, and a `SequentialAgent` root has no `canonical_model` — you get `AttributeError: 'SequentialAgent' object has no attribute 'canonical_model'` at run time unless you pass an explicit summarizer.

Leave it off. Revisit only if the Brain becomes multi-turn within a single invocation.

---

## 7. Where memory lives, at every moment

| Artifact | Session open | During session | Session close |
|---|---|---|---|
| `LEARNER.md` | read → `state` | read from `state` | rewritten? **no** — only appended |
| Concept pages | 3–5 read → `state` | read from `state`; `recall()` for others | status line edited, sections appended |
| Session journal | `[]` | appended in RAM, mirrored to `state_delta` | flushed to a new `sessions/*.md` |
| `tutor-notes.md` | not loaded | not touched | bullets appended, counters incremented |
| `schedule` table | one indexed query | untouched | FSRS update per touched concept |
| Method skill body | one read | swapped on mode change | untouched |
| Wiki index | not touched | `recall()` reads it | incrementally reindexed |

Read the "During session" column top to bottom: **one durable write path (`state_delta`), everything else in RAM.** That's the design in a sentence.

---

## 8. Background agents and memory

The Scheduler, PrepAgent and Curator run with no student present. They read the wiki directly — I/O is free when nobody is waiting — and resume durable sessions to do their work.

```python
@app.post("/internal/wake")
async def wake(payload: WakePayload):
    async for event in runner.run_async(
        user_id=payload.student_id,
        session_id=payload.session_id,
        new_message=types.Content(role="user", parts=[
            types.Part(text="Scheduled wake: prepare the review session.")
        ]),
        state_delta={                          # applied atomically BEFORE inference
            "phase":         "REVIEW_DUE",
            "due_concepts":  payload.concept_ids,
            "learner_md":    await wiki.read(payload.learner_path),
        },
    ):
        log(event)
```

`state_delta` lands before the model's next inference, so the agent sees correct state rather than reconstructing it after a multi-day gap.

⚠️ **If you use `VertexAiSessionService`, `get_user_state()` raises `NotImplementedError`** — the Agent Runtime API doesn't expose user state independently of a session, and you'd have to enumerate with `list_sessions` and fetch each. Use `DatabaseSessionService` over Cloud SQL and the problem doesn't exist. This is one more reason the schedule table, not ADK user state, is the source of truth for due dates.

---

## 9. Concurrency

Two devices, one student, two live sessions. Rare, but it corrupts memory silently when it happens.

```python
async def acquire_writer(student_id: str) -> bool:
    """Postgres advisory lock. Single writer per student, always."""
    return await db.fetchval(
        "SELECT pg_try_advisory_lock(hashtext($1))", student_id
    )
```

- **First session** gets the write lock and behaves normally.
- **Second session** gets read-only memory and a visible banner: *"You're also on another device — this session won't be saved."*
- Lock released at write-back or on a 2-hour timeout.

Simple, correct, and honest to the student. You will not hit this in a hackathon; ship it anyway, because the failure mode without it is a corrupted learner model you can't debug.

---

## 10. The complete wiring

```python
# ── Brain ─────────────────────────────────────────────────────────
brain = LlmAgent(
    name="Brain",
    model=Gemini(model="gemini-3.5-flash"),
    instruction=lambda ctx: "\n\n".join(assemble(ctx.state)),
    tools=ALL_TOOLS,                        # filtered per turn by scope_tools
    before_model_callback=scope_tools,      # ← mutates in place, returns None
)

app = App(
    name="nityam",
    root_agent=brain,
    context_cache_config=ContextCacheConfig(
        min_tokens=4096, ttl_seconds=1800, cache_intervals=10),
    plugins=[JournalPlugin(), ModeGuard(), CostGuard()],
    # events_compaction_config: deliberately absent — see §6.3
)

runner = Runner(
    app=app,
    session_service=DatabaseSessionService(uri=CLOUD_SQL_URI),
    artifact_service=GcsArtifactService(bucket=BUCKET),
    # memory_service: deliberately absent — the wiki is the memory
)

# ── Ear & Mouth ───────────────────────────────────────────────────
async def tutor(utterance: str, tool_context: ToolContext) -> dict:
    """The Live model's only substantive tool."""
    result = await run_brain(tool_context.state, utterance)
    for op in result.canvas_ops:
        await canvas.emit(op)               # streams to tldraw
    return {"say": result.say}

ear = LlmAgent(
    name="Ear",
    model=Gemini(model="gemini-3.1-flash-live-preview"),
    instruction=EAR_INSTRUCTION,            # ~300 tokens, no memory
    tools=[tutor, acknowledge, end_session],
)
```

Note what is **not** there: no `MemoryService`, no `VertexAiRagMemoryService`, no `preload_memory` tool. The wiki *is* the memory, and it's injected as instruction text. ADK's memory services solve a problem we solved differently — using both would give you two sources of truth for the same student.

---

*v0.1. The load-bearing decisions: §1 (thin Live), §2.1 (prefix order and the 4,096 floor), §3 (zero hot-path I/O), §4 (buffer, never write mid-session), §6.3 (no compaction on the Brain).*