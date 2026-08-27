# Memory Layer Evaluation — Design Spec

**Status:** Draft, pending the deep-research pass on multi-session eval methodology
(in progress) before the LLM-judge rubrics below are finalized. Personas, scenarios, and
deterministic checks are grounded in this repo's real state and don't depend on that research.

**What this answers:** does SMRITI's memory layer — now fully ported to Firestore/GCS/Redis
(`docs/superpowers/plans/2026-08-27-memory-storage-testbed.md`,
the `860d266` port) — actually work end to end, under real multi-session, multi-student
conversations, in the way `memory_layer.md` promises: citation-backed claims, correct workflow/
episodic/long-term tier behavior, and real personalization that adapts across sessions.

---

## 1. A finding that shapes this whole design

**`close_session` is not wired into any running server today.** Confirmed by grepping
`sub_modules_examples/tutor/app/` and `scripts/`: `session_close.py`'s `close_session` is called
only from its own unit test. `fast_api_app.py`'s lifespan wires ADK's own session/artifact
services (`app/app_utils/services.py`) — unrelated to SMRITI's long-term tier, which is reached
only through the tool functions in `app/memory/tools.py`. Nothing triggers `close_session` when a
real conversation via `agents-cli playground`/`adk web` ends.

This means: **today, chatting with the deployed agent never updates `dpm_profile` or
`teaching_memory`.** Long-term memory only changes via `scripts/seed_demo_data.py` (initial seed)
or a direct `close_session` call. This is expected — the live session-end trigger is explicitly
Task 9/10 territory (VoiceAgent, deferred per `architecture.md`) — but it means this eval's harness
has to **drive `close_session` itself** between simulated sessions, standing in for the trigger
that doesn't exist yet. Noting this here so it isn't mistaken for an eval-harness workaround
rather than what it is: the harness doing the job the real system doesn't do yet.

## 2. Two-layer eval design

`agents-cli eval`'s dataset schema is single-conversation-trace-oriented — a case is one prompt or
one multi-turn continuation *within a session*. Nothing in it expresses "run a session, end it,
run a second session later, verify recall." Building a custom harness for everything would throw
away the built-in metrics (`multi_turn_task_success`, `multi_turn_tool_use_quality`,
`multi_turn_trajectory_quality`) that are well-suited to the single-session dimension. So:

- **Layer 1 — single-session quality, via standard `agents-cli eval run`.** A real dataset
  (replacing the scaffold's placeholder `weather_query`/`capital_lookup` cases) exercising one
  session's worth of tutoring: does the agent call `search_grounding` before stating a fact, cite
  it, call `get_dpm`/`get_teaching_memory` before deciding how to teach, delegate to ArtifactAgent
  when a visual would teach better? Graded with the built-in multi-turn metrics plus one custom
  LLM-judge metric for citation faithfulness (§4).
- **Layer 2 — cross-session recall and personalization, via a custom harness.** What nothing
  off-the-shelf covers: does a *second* session, days later, actually reflect what the *first*
  session taught? This is the harder, more important half of "does the memory layer work," and
  it's where §3's personas and §5's checks live.

## 3. Personas — five students, chosen to force specific failure modes

Grounded in the real concepts Shruti has actually extracted
(`sub_modules_examples/shruti/vault/wiki/*.md` — 19 real projectile-motion concepts, basic through
advanced), not invented topics with no `grounding_chunk` behind them.

| Persona | Traits | What it's designed to catch |
|---|---|---|
| **Arjun** | Fast pace, strong existing vector background, terse worked-examples, cricket, JEE aspirant | Whether the tutor *skips* re-teaching basics a strong student doesn't need — the opposite failure from Priya's |
| **Priya** | Deliberate pace, a real vector-resolution misconception (mixes up sin/cos for components), socratic preference, music | Misconception detection, `open_doubt` lifecycle, and the "never `close_doubt` on one correct answer" rule (memory_layer.md §2.3) under real multi-session pressure |
| **Rohan** | Moderate pace, cricket + video games, **pre-existing DPM/TeachingMemory seeded before this eval's first live session** | Whether `get_dpm`/`get_teaching_memory` correctly load state that wasn't created by a prior *live* session — a real "existing student returns" cold start |
| **Ananya** | Fast pace, JEE aspirant like Arjun (deliberately similar, to test isolation between two similar personas), visual-learner preference, art/painting, works near-duplicate concepts (`trajectory_equation_parameter_extraction` vs. `trajectory_equation_comparison_method`) | ArtifactAgent delegation triggered by stated preference; whether near-identical concept names get conflated in `teaching_memory.covered` |
| **Vikram** | No prior interaction of any kind, cold `staircase_projectile_collision_method` question | Pure isolation — `get_dpm` must return `{"found": false}` before any Vikram session, and nothing from the other four personas' sessions may appear in Vikram's record or vice versa |

Each persona gets a distinct `student_id` (e.g. `eval_arjun`, `eval_priya`, ...) — never
`demo_student`, so this eval never touches the real seeded demo data.

## 4. Scenario shape — per persona, 2–3 sessions

```
Session 1 (cold or pre-seeded start)
  -> a short scripted multi-turn conversation on 1-2 concepts
  -> log_turn fires each exchange (workflow tier, Redis write-through)
  -> harness calls close_session explicitly (simulating session end)
     -> session_log written to Firestore
     -> Reflect call proposes ops against dpm_profile/teaching_memory
     -> ops applied and persisted

Session 2 (new ADK session, same student_id, "days later")
  -> opens on a related or harder concept
  -> correct behavior: get_dpm/get_teaching_memory called and their
     content actually shapes what's said (no re-teaching a known concept,
     doubt referenced if still open, persona's pace/interest honored)
  -> harness closes this session too

[Session 3 for personas that need it — Arjun, Priya]
  -> tests doubt resolution (Priya) or continued fast-track progression (Arjun)
```

Turn content is semi-scripted: the *student* turns are fixed (so the scenario is reproducible and
graders have a stable transcript to compare across runs), the *tutor* turns are the real agent's
live output — this is what's actually under test.

## 5. What's measured

### 5.1 Deterministic checks (Python, not LLM — cheap, exact, run first)

| ID | Check |
|---|---|
| D1 | Every factual claim in a tutor turn is preceded by a `search_grounding` call in the same turn's trace, and the returned chunks are non-empty |
| D2 | `get_dpm` and `get_teaching_memory` are called at the start of every session **after the first** for a given student |
| D3 | Redis (`session:<id>:turns`) actually contains one entry per `log_turn` call, read directly from Redis, not inferred from the tool's return value |
| D4 | After `close_session`, Firestore's `session_logs`/`dpm_profiles`/`teaching_memories` documents exist and contain the expected fields — read directly from Firestore |
| D5 | **Isolation**: no persona's Firestore documents contain another persona's `student_id`, concept, or evidence reference |
| D6 | **Citation-evidence integrity** — the actual guarantee `memory_layer.md` §0 promises: every `evidence` string in `dpm_profile`/`teaching_memory` (a `session_id#turn` reference) resolves to a real turn in the corresponding `session_log`. This has never been verified end-to-end before this eval — it's always been true by construction of the schema, never checked against a real run. |
| D7 | `close_doubt` never fires in the same session an `open_doubt` was created (memory_layer.md §2.3's spaced-recheck rule) |

### 5.2 LLM-as-judge checks (custom metrics, `google.genai`, same pattern as the scaffolded `response_quality.py`)

| ID | Judges |
|---|---|
| L1 | **Memory recall quality** — given session N-1's transcript and session N's transcript, did the tutor correctly build on session N-1 (no contradiction, no re-teaching from scratch, no fabricated memory)? |
| L2 | **Personalization/adaptation quality** — does teaching style match the persona's stated pace/interest/preferred modality across the whole multi-session arc, not just one turn? |
| L3 | **Citation faithfulness** — does the tutor's explanation actually match the retrieved `grounding_chunk.text`, not distort or extend beyond it? |
| L4 | **Doubt-handling soundness** — when `open_doubt` fires, was the misconception correctly identified; when `close_doubt` fires, was the "recheck" turn a genuine re-test, not a restatement? |

Both layers write results to a single report; §6 covers the harness that produces them.

## 6. Harness architecture

New directory: `sub_modules_examples/tutor/tests/eval/memory_eval/` (inside the existing eval
tree, not a separate package — this is testing the real agent, not proving a pattern in isolation
the way `memory_storage_testbed` did).

```
tests/eval/memory_eval/
├── personas.py       # the 5 persona definitions + their scripted student turns
├── harness.py        # runs one persona's full multi-session scenario, captures traces
├── deterministic_checks.py   # D1-D7, reading real Firestore/Redis state directly
├── judges.py          # L1-L4, google.genai LLM-as-judge calls
├── run_eval.py         # orchestrates all 5 personas, writes the report
└── report/            # output: per-persona trace JSON + final markdown report
```

Each persona run uses a fresh `Runner` + `InMemorySessionService` (ADK's own session bookkeeping
— ephemeral, per `google_cloud_storage_integration.md` §5.2's reasoning, unrelated to what's
under test) against `build_tutor_agent()`, with `student_id` pre-set in the initial session state
so `_init_student`'s `setdefault` doesn't override it with `demo_student`.

## 7. Cleanup

Every `eval_*` student's Firestore documents and Redis keys are deleted at the end of a full run
— same discipline as the testbed and the ported unit tests. The report (§6) is what persists, not
the underlying data.

## 8. What "done" looks like

- A written report (this doc gets superseded by a results doc, not silently edited) with, per
  persona: pass/fail on D1–D7, scores + rationale on L1–L4, and the actual transcripts for anyone
  who wants to read them directly rather than trust the grade.
- Every failure diagnosed to a root cause (agent instruction gap, a real memory-layer bug, or an
  eval-harness bug) and either fixed-and-reverified or explicitly logged as a known limitation —
  never silently lowered to pass.
- Layer 1's `agents-cli eval run` scores shown alongside Layer 2's, not omitted.
