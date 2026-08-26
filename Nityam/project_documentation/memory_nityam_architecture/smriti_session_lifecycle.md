# SMRITI — Session Lifecycle & Operations

What runs when, what it costs, and what breaks.
Companion to *Harness Integration* and the *Error Register*. Version 0.1.

---

## 1. Online vs offline — the whole split on one page

The organising rule: **anything that requires knowing what happened next is offline.**

That single test decides almost every case, and it explains why so much has to be deferred. You cannot tell whether a barge-in meant "I've got it" or "you lost me" at the moment of the barge-in. You cannot tell whether a mode worked until you see what the student did with it. You cannot mark a misconception resolved from one correct answer.

| | **ONLINE** — student waiting | **OFFLINE** — nobody waiting |
|---|---|---|
| **Reads** | `session.state` only. Zero I/O. | Wiki, schedule table, index — all free |
| **Writes** | RAM buffer + `state_delta` | Wiki pages, schedule, index |
| **LLM calls** | 1 Brain call per teaching turn | 2–3 per session |
| **Budget** | < 900 ms | minutes |
| **Failure** | student notices immediately | retry silently |

**Online:** assemble context · select mode · teach · emit canvas ops · grade an attempt · append to the buffer · switch mode · `recall()` on explicit request.

**Offline:** write session page · update concept pages · classify barge-ins · score salience · open/close confusions · append tutor notes · run FSRS · reindex the wiki · prepare the next session · weekly curation.

---

## 2. A session, end to end

### Phase 0 — Open (~400 ms, overlapped with connection setup)

```
student taps "start"
    │
    ├─ read LEARNER.md ──────────┐
    ├─ query schedule for due ───┤ parallel, ~250 ms
    ├─ read 3–5 concept pages ───┤
    ├─ load skill catalog ───────┘  (process-cached, ~0 ms)
    │
    ├─ check for unwritten buffer from a previous session   ← E14
    ├─ select_mode() → load method skill body
    ├─ assemble cached prefix → warm the Gemini cache
    │
    └─ open Live WebSocket, send setup
```

Two things happen here that pay off for the rest of the session: **prerequisites of the planned concept are prefetched** (the most likely pivot when a student gets stuck), and **the cache is warmed** before the first real turn, so turn 1 isn't the one that pays cache-creation cost.

The `unwritten buffer` check is the one people forget. A student who closes and immediately reopens is common, and without it their last twenty minutes vanish.

### Phase 1 — Teaching turns

Not every turn is a teaching turn, and that distinction is where the latency budget is won.

```
student speaks
    │
    ▼
EAR (Live model) decides: teaching turn?
    │
    ├── NO  (acknowledgement, chit-chat, "haan", "wait") ──▶ answers directly
    │                                                          ~350 ms · no Brain
    │
    └── YES ─▶ acknowledge immediately ("achha, ek second…")   ~200 ms to audio
               │
               └─▶ Brain: assemble → 1 LLM call → ops + say
                                                            ~700 ms
                   └─▶ EAR speaks the result, canvas ops stream
```

**Roughly 40% of turns need the Brain.** The rest the Live model handles alone, at a third of the latency.

The immediate acknowledgement is not a trick — it's what a human tutor does while thinking, and it converts 900 ms of dead air into 200 ms of dead air plus a natural pause.

**Per-turn budget:**

| Stage | ms |
|---|---|
| VAD end-of-speech | 100 |
| Ear decides + calls `tutor()` | 250 |
| Brain: assemble (pure function) | 5 |
| Brain: LLM, cached prefix, `thinkingLevel: minimal` | 600 |
| Ear speaks | 200 |
| **First audio after a teaching turn** | **~1,150** |
| **First audio after a non-teaching turn** | **~350** |

The 600 ms Brain call is the whole game. It assumes a warm cache, one call (not a pipeline — see Error Register E1), and no I/O.

### Phase 2 — The long middle

Two clocks run underneath, neither of which the student should ever perceive:

```
    connection    ├──10 min──┤├──10 min──┤├──10 min──┤
                       GoAway ▲     GoAway ▲
                       reconnect     reconnect
                       + reanchor    + reanchor

    Live session  ├───15 min uncompressed───┤─── compressed, unlimited ───▶
                                     trigger at 48k tokens
                                     window down to 12k

    Brain context ├─ rebuilt from memory, every single invocation ─────────▶
                       (flat. does not grow. nothing to compact.)
```

The third line is the important one. **The Brain's context does not accumulate**, so compression on the Live side can discard whatever it likes without touching the state that matters. That's the payoff from the thin-Live architecture.

### Phase 3 — Close and write back

Triggered by explicit end, 90 s idle, or the sweeper.

```
buffer (RAM + state_delta)
    │
    ├─ 1. Session page          ── format buffer → sessions/<date>.md
    │                              deterministic. no LLM.
    │
    ├─ 2. Reflect               ── 1 LLM call over the session page
    │                              · classify barge-ins from what followed
    │                              · score salience
    │                              · judge which modes worked
    │                              · propose status changes with evidence
    │
    ├─ 3. Apply                 ── validated operations only:
    │                              append_note · increment · set_status
    │                              open_confusion · close_confusion
    │                              NEVER rewrite a file
    │
    ├─ 4. FSRS                  ── pure arithmetic per touched concept
    │                              → schedule table
    │
    ├─ 5. Citations             ── write ref → (file, line) rows
    │
    └─ 6. Reindex               ── content-hash diff, FTS5 + embeddings
```

Steps 1, 4, 5, 6 are deterministic. **Only step 2 uses a model.** Step 3 validates its output against a fixed operation schema and drops anything malformed.

Total: 2–4 seconds, one Flash call, roughly $0.004 per session.

### Phase 4 — Between sessions

| Job | Trigger | Does |
|---|---|---|
| **Scheduler** | after write-back | FSRS due dates → schedule table |
| **PrepAgent** | cron, when a concept comes due | Generates + validates the probe, pre-renders the artifact, caches it. **The next session is already built before the student opens the app.** |
| **Curator** | weekly | Merges duplicate notes, retires `✗ > ✓` ones, proposes cross-student promotions |

---

## 3. Failure modes

| What breaks | Student sees | System does |
|---|---|---|
| WebSocket drops | brief silence | Reconnect with resumption handle, re-anchor (~120 tok) |
| Brain call times out (>2 s) | *"Ek minute, phir se…"* | Retry once at `thinkingLevel: minimal`; on second failure the Ear handles the turn alone |
| Cache creation times out | nothing | ADK fails gracefully and proceeds uncached — set `create_http_options` timeout to 10 s |
| Concept page missing | nothing | Create an empty page with `mastery: unknown`; the tutor treats it as new |
| `recall()` index stale | slightly worse recall | Serve stale, queue reindex |
| Write-back fails | nothing, this session | Buffer stays in `state`; next open picks it up (E14) |
| Container dies mid-session | reconnect prompt | `DatabaseSessionService` has every `state_delta`; resume from the last event |
| Two devices | banner on the second | Advisory lock; second session read-only |
| Mode guard fires | nothing | Logged as `mode_violation` — a hole in the tool filter, fix it |

The pattern worth noticing: **almost every failure degrades to "slightly worse teaching," not "broken."** The one that doesn't is the container dying, and durable sessions handle that.

---

## 4. Cost

Per 30-minute session:

| | Tokens | $ |
|---|---|---|
| Live audio in/out (~25 tok/s both ways) | ~90k | 0.11 |
| Ear system instruction × ~60 turns | ~18k | 0.03 |
| Brain: ~24 teaching turns × (4.6k cached + 0.9k fresh) | 110k cached + 22k fresh | **0.05** |
| Write-back: 1 Flash call | ~8k | 0.01 |
| PrepAgent (next session) | ~15k | 0.02 |
| **Per session** | | **~$0.22** |

The Brain line is the one to look at. Without caching it would be $0.20 rather than $0.05 — **caching is 68% of the total saving, and it only works if the prefix clears 4,096 tokens** (Error Register E5).

The single biggest cost is audio, and there is nothing to do about it except keep sessions purposeful.

**$150 of credits ≈ 680 sessions.** Not the constraint.

---

## 5. Does this actually make a good harness?

The honest scorecard. A harness is good when an agent can run for a long time, recover from anything, and be debugged by a human.

| Property | Status | How |
|---|---|---|
| **Durable state** | ✅ | Every `tool_context.state` write persists as a `state_delta` on an event |
| **Resumable** | ✅ | Live resumption handles + ADK session replay. Kill the container on stage. |
| **Observable** | ✅ | Cloud Trace spans per LLM call and tool; the session page is human-readable |
| **Auditable** | ✅ | Every claim → citation → session line. This is the strongest property in the system. |
| **Tool safety** | ✅ | Mode filter at the model + guard at the tool. Two independent layers. |
| **Context managed** | ✅ | Brain rebuilds rather than accumulates; Live compresses server-side |
| **Bounded cost** | ✅ | `CostGuard` plugin with a per-session ceiling |
| **Evaluable** | ✅ | Turns-to-collapse · page-reads-true · citation invariant in CI |
| **Recoverable memory** | ⚠️ | Buffer survives crashes, but a failed write-back needs the sweeper to catch it. Test this path. |
| **Concurrent-safe** | ⚠️ | Advisory lock handles it, but only if you build it. It's ten lines; build it. |
| **Portable** | ✅ | Memory is markdown in git. Change model, framework or vendor and the files still mean something. |

Two amber, both known, both cheap. Nothing red.

### What's genuinely unusual here

Three properties most agent harnesses don't have:

- **Memory that a human can read, edit, and argue with.** The student can open their own file. That's an Open Learner Model, and the research says letting learners contest the system's beliefs improves both accuracy and self-assessment.
- **A behavioural rule that persuasion cannot break.** Mode lives in state and controls the tool list. Most Socratic tutors fold under pressure because their mode lives in a prompt.
- **A memory that compounds across users.** A tutor note that works for 47 students becomes a method skill every future student inherits. The counters and the `scope` field are already in the design; the promotion pipeline is later.

### What it still can't do

Stated plainly, so nobody is surprised:

- **No mid-session memory revision.** If the tutor learns something important at minute 5, it shapes the *rest of that session* through `session.state`, but `LEARNER.md` isn't rewritten until close. Correct — you shouldn't rewrite a child's profile on partial evidence — but it's a real limitation.
- **No cross-session real-time sync.** Two devices means one is read-only.
- **Retrieval is lexical-first.** FTS5 + optional local embeddings will miss a paraphrase that a good embedding model would catch. Fine at one student's scale; revisit at scale.
- **The whole thing rests on write-back running.** If the sweeper is broken, the system silently stops learning and nothing alerts you. **Add a metric: sessions closed vs. write-backs completed.** They should be equal. Alert on drift.

That last one deserves the most attention. It's the failure that looks like nothing is wrong.

---

## 6. Build order

Each row is independently shippable. Stop after any of them and you have something that works.

| | Build | Proves |
|---|---|---|
| **1** | Ear + Brain split. Ear has 3 tools. Brain has a hand-written `LEARNER.md` and one concept page pasted into its instruction. | The split works and voice latency is acceptable |
| **2** | Memory Context Assembly + `ContextCacheConfig(min_tokens=4096)`. Log `cached_content_token_count` and confirm it's non-zero. | Caching actually engages |
| **3** | `session.state` buffer + `JournalPlugin`. Write the session page at close. **No LLM in the write-back yet.** | Durability, end to end |
| **4** | Mode selector + `scope_tools` filter + `ModeGuard`. Three method skills. | Turns-to-collapse ≥ 16 |
| **5** | The Reflect call in write-back. Concept pages update. Citations written. | Memory improves across sessions |
| **6** | Schedule table + FSRS + PrepAgent. | The background story, real |
| **7** | Advisory lock · sweeper · unwritten-buffer recovery · write-back drift metric. | It survives contact with real users |

**Step 2 is the one people skip and shouldn't.** Log `cached_content_token_count` on the first Brain call. If it's zero, your prefix is under 4,096 or something in it is mutating per turn, and you'll be paying 4× for the whole build without knowing.

**Step 7 is the one people postpone forever.** It's half a day and it's the difference between a demo and a product.

---

## 7. Instrumentation — five numbers

Everything else is noise until these are right.

| Metric | Target | Meaning |
|---|---|---|
| `first_audio_ms` p95, teaching turns | < 1,400 | The product feels alive |
| `cached_content_token_count` > 0 | 100% of Brain calls | Caching is on |
| `writebacks / sessions_closed` | 1.00 | The system is still learning |
| `mode_violations` | 0 | The tool filter has no holes |
| `citations_resolvable` | 100% | Every claim is defensible |

The third is the one that fails silently. Alert on it.

---

*v0.1. Read alongside the Error Register — E1, E5, E13 and E14 all show up in this lifecycle and are the difference between it working and it looking like it works.*