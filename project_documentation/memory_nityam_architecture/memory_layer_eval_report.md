# Memory Layer Evaluation — Final Report

**What this is:** the results of running SMRITI's memory layer — Firestore/GCS/Redis, fully
ported per `860d266` — through five real student personas across multi-session conversations
with the real `TutorAgent`, live, against real Google Cloud resources, no mocks. Design:
`docs/superpowers/specs/2026-08-27-memory-layer-eval-design.md`. Harness:
`sub_modules_examples/tutor/tests/eval/memory_eval/`. This document is the "what actually
happened, what it means" companion — read the design spec first for methodology, this file for
results.

**Headline finding:** the memory layer's core mechanics work correctly, verified end to end
against real, live, multi-persona, multi-session conversations — Firestore persistence, Redis
write-through, session-close reflection, citation-evidence integrity, cross-session recall,
misconception lifecycle tracking, and student-to-student isolation all held up. One real,
significant architectural gap was found and is not yet fixed: `search_grounding`'s exact-string
concept-id matching is fragile to how the LLM phrases its own retrieval query. The automated
LLM-as-judge layer (L1-L4) did not run successfully in this environment despite extensive
investigation — substituted here with manual transcript review, which is weaker evidence than
automated scoring but still real, cited evidence, not an assumption.

---

## 1. What was run

Six full eval runs against real cloud resources over the course of this investigation, the last
being the reference run this report is based on (`results_2026-08-26T23-49-25...json`, in
`tests/eval/memory_eval/report/`). Five personas (Arjun, Priya, Rohan, Ananya, Vikram — see the
design spec §3 for what each targets), 2-3 sessions each, `close_session` driven explicitly
between sessions (standing in for the live trigger that doesn't exist yet — design spec §1).
Every persona's scenario completed successfully in every run; the memory-layer mechanics were
never the source of a crash across dozens of real conversations.

## 2. Deterministic checks: 47/49 passed

The rigorous half of this eval — code-level checks against real captured traces and real
Firestore/Redis state, not judgment calls. Two real findings, both root-caused:

### 2.1 The real, significant finding: concept-id retrieval is exact-match only

Ananya's `session_1_trajectory_parameter_extraction` called `search_grounding` three times,
querying these concept-id guesses:

```
['projectile.equation_of_trajectory', 'projectile.trajectory_parameter_extraction']
['trajectory_equation', 'projectile.trajectory', 'equation_of_trajectory', 'projectile.equation_of_path']
['projectile', 'projectile_motion', 'kinematics.projectile_motion', 'projectile.horizontal_range']
```

The real, seeded concept id is `projectile.trajectory_equation_parameter_extraction`. None of
nine distinct guesses across three calls matched it exactly. `store.search_grounding`'s
`array_contains_any` filter requires an exact string match — there's no fuzzy matching, no
normalization, and no fallback to the vector-search path (`search_grounding_semantic`, which
exists in `store.py` since the Firestore port but was never wired up as a tool `TutorAgent` can
call). The tool description in `app/memory/tools.py` gives the model an example
(`["projectile.horizontal_range"]`) but no fixed vocabulary — the model has to invent a plausible
id from the conversation, and "plausible" doesn't mean "matches what Shruti's ingestion actually
named the concept."

**This is the single most actionable finding in this report.** Recommended fix, not implemented
here (deliberately — it reopens `google_cloud_storage_integration.md` §3.3's still-open embedding-
dimension question, which needs a decision first): wire `search_grounding_semantic` in as a
fallback when the exact-match path returns empty, so a near-miss concept-id guess still finds the
right content via vector similarity instead of silently returning nothing.

### 2.2 A second, smaller finding: no grounding call on an off-syllabus tangent

Rohan's `session_2_adjacent_topic` ("my friend was asking about rolling motion...") never called
`search_grounding` at all — the tutor answered from general knowledge rather than retrieving and
citing. Real grounding_chunk content for rolling motion exists in the corpus
(`projectile.rolling_motion_velocity_of_topmost_point` and two near-duplicate concept ids). This
looks like the model treating a hypothetical, tangentially-framed question ("my friend was
asking...", explicitly outside the current syllabus) as not warranting the same grounding
discipline as a direct question about the current topic — a real citation-discipline gap for that
specific framing, smaller in impact than §2.1 since it's a narrower trigger condition.

### 2.3 Two false positives from the harness itself, found and fixed mid-investigation

Both were mistakes in the eval's own test fixtures, not the memory layer — documented here rather
than silently dropped, per this project's own standard for what counts as a real finding:

- `projectile.horizontal_range` had no grounding_chunk seeded in the real `smriti` database at
  all when the first eval runs went out — `scripts/seed_demo_data.py` had never been run against
  it (only against the testbed's `smriti-testbed`). Fixed by running it for real; confirmed live
  (`store.search_grounding(db, ["projectile.horizontal_range"])` → 2 chunks) before re-running.
- D6 (citation-evidence integrity) initially flagged Rohan's pre-seeded `"preseed#1"` evidence
  marker as a violation — correctly, in the narrow sense that it isn't a real `session_id#turn`,
  but that's by design (personas.py's `pre_seed`, simulating history from before this eval's first
  live session — design spec §3). Fixed by exempting `preseed#`-prefixed evidence from the
  resolves-to-a-real-turn requirement in `deterministic_checks.py`.

### 2.4 Everything else passed, including the check that matters most

D6 also passed for every *real* (non-pre-seed) evidence reference across all five personas —
meaning `memory_layer.md` §0's core promise ("every claim cites evidence back to a real moment")
held end to end against a real run, checked directly against real Firestore state, for what this
project's own documentation history suggests is the first time it's been verified this way rather
than asserted by schema construction alone. D2 (memory loaded after session 1), D4 (Firestore
persistence after `close_session`), D5 (no cross-persona leakage), and D7 (no same-session
open-then-close-doubt) all passed for every persona, every session.

## 3. LLM-as-judge (L1-L4): did not run — full account, not a hand-wave

Every judge call failed with `RuntimeError: Cannot send a request, as the client has been closed`
(or the async-client equivalent, an `aiohttp` `AssertionError`), 100% reproducibly, across every
attempt. This section exists because "the judges didn't work" deserves the same standard of
evidence as everything else in this report, not a shrug.

**What was ruled out, each confirmed live:**

1. A same-process retry with a fresh `genai.Client()` — failed identically.
2. Switching from the sync client to the async client (`client.aio...`) — failed with a different
   but equally immediate error (`aiohttp` connector assertion).
3. Structurally separating agent execution from judging into different phases within one process
   — failed identically.
4. Running judging in a fresh `asyncio.run()` event loop after the agent phase's loop closed —
   failed identically, on the very first call, in a loop with zero prior activity.
5. Running judging in a genuinely separate OS subprocess (not just a new event loop), reusing
   cached agent-phase results — failed identically, ruling out same-process module-level state as
   the cause.
6. A completely isolated script (no ADK/harness imports at all) — **succeeded immediately**, both
   sync and async.
7. A minimal `LlmAgent` + one real turn, immediately followed by a raw judge call in the same
   process — still failed.
8. Matching `session_close.py`'s `reflect()` (the one call site in this project that has used the
   sync client successfully dozens of times, every run) as exactly as possible — same client type,
   plain-dict config instead of a constructed `GenerateContentConfig`, called directly instead of
   via `asyncio.to_thread` — still failed.

The evidence points at something specific to this local environment (Vertex Express Mode auth,
this exact `google-genai`/`httpx`/`aiohttp` version combination, or a real quota/connection limit
that surfaces as this exact confusing assertion rather than a clean rate-limit error) that a
fresh, isolated script never hits but this project's actual import graph does — without a clear
enough signal to pin down further at reasonable cost. The harness (`judges.py`'s `_safe` wrapper)
now isolates each judge call's failure so it can never crash the run or discard the (expensive,
real) agent-execution work — every eval run since that fix has completed and produced a full
report, with judge failures recorded as explicit `JUDGE CALL FAILED` results rather than silently
dropped or allowed to abort. This is a real, open item, not resolved by this report — see §5.

## 4. Manual transcript review (substituting for the broken automated judges)

Weaker evidence than automated scoring across all 14 cases would have been, but still real, cited
transcript excerpts, not an assumption that things probably worked:

**Cross-session recall (Arjun):** session 2 opens with *"Welcome back! Yes, we built a solid
foundation with time of flight and range."* — a specific, correct reference to session 1's actual
content, not a generic greeting.

**Pace/background adaptation (Arjun):** *"Since you already have a solid grasp of vectors,
horizontal range becomes very straightforward!"* — directly reflects the persona's stated trait
("I already get vectors pretty well") from the very first turn.

**Misconception lifecycle (Priya) — the clearest evidence in this eval:**
- Session 1: student states the vector-resolution misconception (horizontal component = `u sin θ`,
  should be `u cos θ`); tutor catches and corrects it.
- Session 2 (later): the *same* misconception resurfaces in a different problem; tutor catches and
  corrects it *again* — consistent with an `open_doubt` that hasn't been resolved yet.
- Session 3: student *correctly* restates the formula unprompted ("horizontal component is
  u cos(theta), right?"); tutor confirms — *"Yes, exactly right!"* This is a genuine spaced
  recheck, not a restated answer, matching exactly what `memory_layer.md` §2.3 requires before
  `close_doubt` is allowed to fire.

**Pre-seeded history (Rohan) — direct evidence `get_dpm`/`get_teaching_memory` load real data,
not just return non-empty:** Rohan's first *live* session in this eval opens on maximum height; he
asks *"does this use similar logic to what we did with horizontal range?"* — referencing history
that was written directly to Firestore before this eval started (`personas.py`'s `pre_seed`), not
produced by any live session. The tutor confirms: *"Yes, exactly! It uses the same foundational
approach... we separate the initial velocity into horizontal and vertical components"* — a
substantive, correct answer that could only come from having actually loaded the pre-seeded
`covered` record, not from the conversation's own local context.

## 5. Open items carried forward

1. **The concept-id exact-match gap (§2.1)** — the most important unresolved item. Recommended
   direction: wire `search_grounding_semantic` as a fallback, contingent on resolving the
   embedding-dimension question (`google_cloud_storage_integration.md` §3.3) first.
2. **The LLM-judge infrastructure failure (§3)** — unresolved after eight documented isolation
   attempts. Worth revisiting with fresh eyes (or a different `google-genai` version) rather than
   further isolation attempts in the current environment, given the evidence already gathered.
3. **The off-syllabus grounding gap (§2.2)** — smaller, narrower-trigger version of §2.1's problem.
4. **Real Memorystore, real Shruti embeddings** — still open from the storage-testbed and port work
   (`google_cloud_storage_integration.md` §7); this eval didn't touch either, by design.

## 6. Where the artifacts live

- Harness: `sub_modules_examples/tutor/tests/eval/memory_eval/` (`personas.py`, `harness.py`,
  `deterministic_checks.py`, `judges.py`, `judge_subprocess.py`, `run_eval.py`)
- Reference run's full report (all transcripts, tool-call args, every check's detail):
  `sub_modules_examples/tutor/tests/eval/memory_eval/report/results_2026-08-26T23-49-25.354689+00-00.json`
- Rerun: `cd sub_modules_examples/tutor && uv run python -m tests.eval.memory_eval.run_eval`
