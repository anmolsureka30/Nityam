# Memory Layer Evaluation — Final Report

**What this is:** the results of running SMRITI's memory layer — Firestore/GCS/Redis, fully
ported per `860d266` — through five real student personas across multi-session conversations
with the real `TutorAgent`, live, against real Google Cloud resources, no mocks. Design:
`docs/superpowers/specs/2026-08-27-memory-layer-eval-design.md`. Harness:
`sub_modules_examples/tutor/tests/eval/memory_eval/`. This document is the "what actually
happened, what it means" companion — read the design spec first for methodology, this file for
results.

**Revision note:** this is a rewrite of the original report. The original left two things
unresolved — `search_grounding`'s exact-match fragility, and a completely non-functional
LLM-judge layer — and substituted manual transcript review for automated scoring as a result.
Both are now root-caused, fixed, and verified live across four further full eval runs. A third
finding — a genuine, real gap in personalization/memory-causality substantiveness — was surfaced
by the now-working judges, one fix was attempted and reverted after it traded away citation
faithfulness, and it remains open — reconfirmed as still open by a final run made after the
revert. §2 and §3 below are new; §4 replaces the old manual-review section with real
automated-judge evidence; §5 is new.

**Headline finding:** the memory layer's core mechanics work correctly, verified end to end
against real, live, multi-persona, multi-session conversations — Firestore persistence, Redis
write-through, session-close reflection, citation-evidence integrity, cross-session recall,
misconception lifecycle tracking, and student-to-student isolation all held up, now confirmed
**49/49 deterministic checks passed, identically across all four Phase-6 full eval runs**,
including the two runs made specifically to confirm the fixes are stable on the current,
reverted-to-baseline code (up from 47/49 in the original investigation). The LLM-as-judge layer
(L1-L4) is now fully functional — root cause found and fixed, confirmed working across all four
runs, the last of which completed with zero retries and zero rate-limit errors. With real
automated scores in hand, the eval surfaced a genuine, still-open finding: citation faithfulness
(L3) is consistently strong, but personalization (L2) and memory-causality (L1) are weak — and one
attempt to fix personalization via instruction tuning made L3 worse without reliably fixing L2,
so it was reverted, and the final confirmation run shows the underlying L1/L2 gap is still there
even on the safe, reverted baseline. That tradeoff, and the decision behind it, is documented in
full in §5.

> **§8 update (2026-08-27, same day):** the "session-close reflection... held up" claim above
> needs a caveat. `reflect()` had a structured-output schema bug that made every one of the runs
> behind this report's "49/49" number silently write nothing to Firestore on close — found later
> the same day by a different route (live memory-state visualization work), not by this eval.
> D4/D6, the two checks that should have caught it, both pass trivially in exactly the state the
> bug produces (see §8 for why). The bug is fixed now, and real evidence the fix works exists
> (§8), but the clean 49/49 number above has not yet been reconfirmed against the fixed code —
> read §8 before treating this report's headline as still current.

---

## 1. What was run

Ten full eval runs against real cloud resources across the whole investigation: six in the
original pass (documented in the prior version of this report), four more in this one — all
against the same five personas (Arjun, Priya, Rohan, Ananya, Vikram — see the design spec §3 for
what each targets), 2-3 sessions each, `close_session` driven explicitly between sessions
(standing in for the live trigger that doesn't exist yet — design spec §1). Of the four Phase-6
runs, two are kept as reference JSON artifacts because their instruction set matches the code as
it stands today (both fixes applied, no personalization instruction change):
`results_2026-08-27T06-15-28.734552+00-00.json` (the first run made after both fixes landed) and
`results_2026-08-27T07-20-54.452603+00-00.json` (the final run of the whole investigation, made
after the Rule-5 personalization experiment was reverted). The other two Phase-6 runs, made under
the since-reverted Rule-5 instruction change, aren't kept as separate JSON artifacts — their exact
scores and rationale are quoted directly in §5. Every persona's scenario completed successfully in
every run; the memory-layer mechanics were never the source of a crash across dozens of real
conversations.

## 2. Fix #1: `search_grounding`'s exact-match gap

### 2.1 The problem, as originally found

The original investigation found `store.search_grounding`'s Firestore `array_contains_any` filter
requires an exact string match against `concept_ids` — no fuzzy matching, no normalization. Across
Ananya's `session_1_trajectory_parameter_extraction`, nine distinct concept-id guesses across
three `search_grounding` calls all missed the real seeded id
(`projectile.trajectory_equation_parameter_extraction`) — the model had no way to know the
corpus's real naming (`"trajectory_equation_in_two-dimensional_motion"`, ingestion-derived) versus
how a tutor or student would naturally phrase the same topic
(`"equation_of_trajectory"`). Across the whole eval, roughly two-thirds of real
`search_grounding` calls returned empty for this reason, even for concepts genuinely present in
the corpus.

### 2.2 The fix: proactive vocabulary exposure + reactive fuzzy fallback

Two changes, layered:

**Primary (proactive):** a new `list_concepts()` tool
(`app/memory/tools.py`), returning every real `concept_id` in the corpus
(`store.list_concept_ids`, which unions `concept_ids` across all `grounding_chunks` documents).
`TutorAgent`'s instruction (`app/agents/tutor_agent.py`, Rule 1) now tells the model to call this
once near the start of a session, or whenever the topic shifts to something unfamiliar, and pass
`search_grounding` ids exactly as `list_concepts` returns them — never invented from the
conversation's own wording.

**Secondary (reactive safety net):** `store.search_grounding` (`app/memory/store.py`) now tries
the original exact-match logic first (extracted unchanged into `_exact_match`), and only on an
empty result, fuzzy-matches each queried id against the full real vocabulary by token-overlap
(Jaccard similarity ≥ 1/3), then retries the exact-match query with whatever real ids clear the
threshold. Tokenization (`_tokenize`) strips the fixed `projectile.` domain prefix, splits on
non-alphanumeric characters, and drops a small stopword list (`of`, `the`, `a`, `an`, `in`, `on`,
`for`, `to`, `and`) — so `"projectile.equation_of_trajectory"` tokenizes to `{equation,
trajectory}` and matches the real `"projectile.trajectory_equation_in_two-dimensional_motion"`
(tokens `{trajectory, equation, two, dimensional, motion}`, Jaccard = 2/5 = 0.4, well above
threshold) despite the differing word order and the extra qualifying detail in the real id.
Token overlap was chosen specifically because it's robust to reordering — the failure case above
is exactly a reordering case, which substring or edit-distance matching would have handled worse.

**Why threshold 1/3 and not lower:** a genuinely unrelated guess like
`"projectile.completely_different_topic"` against a real
`"projectile.impact_angle_condition"` shares zero tokens (Jaccard = 0) and correctly finds
nothing — verified in `test_search_grounding_fuzzy_fallback_rejects_unrelated_guess`
(`tests/unit/memory/test_store.py`). A threshold that's too permissive would start returning
plausible-looking but wrong chunks, which is worse than returning nothing (a wrong citation is a
correctness bug; an empty result is a visible gap the model can react to).

### 2.3 Verification

`test_search_grounding_fuzzy_fallback_matches_close_guess` reproduces the exact real failure case
above end to end against live Firestore. Beyond unit tests, the fix was verified at the system
level: **49/49 deterministic checks passed, identically, across all four Phase-6 full eval
runs** — up from 47/49 (with the two failures both being real instances of this exact gap) before
the fix. That includes the two runs made specifically to confirm robustness on the current,
reverted-to-baseline code (`06-15-28` and the final run, `07-20-54`) and the two runs made mid-way
through the personalization-instruction experiment (§5), which touched only `TUTOR_INSTRUCTION`,
not `search_grounding` or its callers — so their unaffected 49/49 result is corroborating evidence,
not a separate test of the same thing. No `search_grounding` call across 15+ multi-session
conversations, four full runs, returned an avoidable empty result after the fix landed.

## 3. Fix #2: the LLM-judge infrastructure

### 3.1 The problem, as originally found

Every judge call failed with `RuntimeError: Cannot send a request, as the client has been closed`
(or an `aiohttp` `AssertionError` on the async client), 100% reproducibly. The original
investigation ruled out eight distinct hypotheses, each tested live: a same-process retry with a
fresh client, sync-vs-async client choice, structural phase separation, a fresh event loop, a
genuinely separate OS subprocess, and matching `session_close.py`'s known-working call pattern as
closely as possible — all failed identically. A fully isolated script with no ADK/harness imports
at all succeeded immediately, which was the strongest clue: something about this project's actual
import graph or call pattern, not the API or credentials themselves, was the cause.

### 3.2 Root cause, found via targeted research

`googleapis/python-genai` GitHub issues **#1489** and **#1763** (and the matching `aiohttp`
variant, **#1453**) describe exactly this failure: constructing `genai.Client()` as a temporary
inline object — build it, make one call, let it go out of scope, repeat on the next call — breaks
starting in `google-genai>=1.39.0`, because the SDK's own cleanup can close the underlying
transport connection while a request on a **different** temporary `Client()` instance is still in
flight. Every prior `judges.py` implementation, across every one of the eight isolation attempts,
still constructed a fresh `genai.Client()` inline per call (`genai.Client().models.generate_content(...)`)
— the isolation attempts changed everything *around* that pattern (sync/async, process
boundaries, event loops) without ever changing the pattern itself. This also explains why the
fully isolated script worked: with only one call ever made, there was no second temporary client
in flight to race against.

It also explains why `session_close.py`'s `reflect()` had always worked, every run, without
anyone treating it as a deliberate workaround: `harness.py` constructs
`genai_client = genai.Client()` **once** per persona in `run_persona_scenario` and passes that
same instance to every call site that needs it — exactly the safe pattern the GitHub issues
recommend, arrived at by coincidence rather than by diagnosis of this specific bug.

### 3.3 The fix

`judges.py` now holds a **module-level singleton** (`_client: genai.Client | None = None`,
lazily constructed once by `_get_client()`), and every judge call goes through it. `_generate`
still keeps a 3-attempt retry-with-backoff loop as defense-in-depth against genuine transient
failures (distinct from this bug — see §3.4), but the fix itself is entirely about *not*
constructing a new `Client()` per call.

### 3.4 Verification

Confirmed first with a cheap synthetic-data smoke test (a real L2 score returned, not an
exception), then confirmed at full scale: **all four Phase-6 eval runs completed with every
judge call returning a real, parsed verdict** — 14/14 judge calls per run succeeded
mechanically (produced a score or pairwise verdict) across all four runs; none hit `JUDGE CALL
FAILED`. (14 = 5 personas × up to 3 applicable judges each, gated by `run_all_judges`'s
per-check applicability rules — see §4.1.) One genuine `429 RESOURCE_EXHAUSTED` was hit once
during this investigation, unrelated to this bug — real Vertex Express Mode quota exhaustion from
cumulative call volume across the session, resolved by waiting ~4 minutes and retrying. The final
run of the whole investigation (`07-20-54`, made after the personalization revert, specifically to
serve as this report's closing data point regardless of outcome) completed cleanly with no rate
limiting and no retries needed at all — the fix holds under both conditions observed across this
investigation: a busy session near quota, and a clean one.

## 4. LLM-as-judge results, now real

With the infrastructure fixed, the judges ran as designed — see `judges.py`'s module docstring
and the design spec for the full methodology. Two runs share the current code's exact instruction
set and are presented together below to show the pattern is reproducible, not a one-off: the first
post-fix run (`06-15-28`) and the final run of the whole investigation (`07-20-54`, made after the
personalization revert). Both scored **7/14 judge checks passed** — same count, and the same
qualitative pattern across every check.

### 4.1 L3 — citation faithfulness: strong, consistently 5/5

Every persona scored 5/5 ("fully faithful to the retrieved source text") in both runs, with one
exception: Ananya scored 3/5 in the first run (still passing) and 5/5 in the final run — this is
the property `memory_layer.md` explicitly calls "the one that separates a learner model from a
horoscope," and it held up under real automated scrutiny, not just manual spot-checking, across
both runs. Sample rationale (Rohan, final run): *"All tutor responses accurately reflect the
concepts, equations, and physical reasoning described in their respective retrieved source texts
without introducing any contradictory claims or unsupported claims."*

### 4.2 L2 — personalization: weak, 2/5 in both runs for the same three personas

Priya and Rohan scored **2/5** in *both* runs — the exact same failure mode both times.
Representative rationale (Rohan, final run): *"The tutor maintained an appropriate moderate pace
with clear, structured derivations and conceptual connections across both sessions. However, the
tutor completely failed to incorporate the student's [stated interests]..."* Ananya also scored
2/5 in the final run (down from a 3/5 pass in the first run — *"kept an efficient, structured
pace... but completely ignored the student's stated interests in painting and art"*). Vikram
scored 5/5 in both runs (passed, but has no stated interests to test against, so this is
structurally a weaker pass). Arjun is the one persona that varied: 2/5 (fail) in the first run,
3/5 (pass) in the final run — both with the identical, unchanged instruction set, so this is
genuine run-to-run variance in what the model actually produces, not a code difference. The
consistent pattern across both runs and across the whole Phase-6 investigation: **pace-matching
reliably works; weaving a student's stated interests into examples reliably does not**, unless the
student volunteers the interest explicitly in that turn.

### 4.3 L1 — memory causality: 0/4 in both runs, the eval's sharpest and most reproducible finding

All four applicable pairwise comparisons (Arjun, Priya, Rohan, Ananya — Vikram has no session 2
to compare, so no L1 check applies), in *both* confirmation runs, picked `"tie"` or `"no_memory"`
— **zero, across eight total comparisons, were judged to show concrete, specific evidence that the
memory-loaded response used the student's history in a way the no-memory baseline couldn't have
produced.** Representative rationale (Priya, final run): *"Both responses provide nearly identical
standard explanations of resolving velocity vectors into horizontal and vertical components.
Response A shows no concrete evidence or specific references to past..."* This is the sharpest,
most concrete, and now most reproducible evidence the eval has produced anywhere: the tutor's
opening reply to a new session, even with real prior history loaded, tends to look near-identical
to how it would open with a brand-new student, and this held identically across two independent
runs. This is a distinct problem from L2 — a response can pace-match a stated trait (L2's
strongest signal) without actually *referencing* what happened last session (L1's test) or
personalizing to *interests* (L2's weakest signal).

### 4.4 L4 — doubt handling: not applicable in either confirmation run

No persona in either confirmation run had an open doubt at the point `run_all_judges` checked, so
L4 was skipped for all five in both runs (see `run_all_judges`'s `has_doubts` gate in
`judges.py`) — not a failure, simply not triggered. The prior report's manual review (Priya's
misconception lifecycle — caught, resurfaced, correctly spaced-rechecked) remains the best direct
evidence for this mechanism and is worth re-reading as corroboration, even though no automated L4
score exists from either confirmation run. See §6 item 4 for a proposed fix (a persona/session
arrangement that reliably produces an open doubt at the check point).

## 5. The personalization instruction-tuning attempt, and why it was reverted

§4.2 and §4.3 are a real, actionable-looking gap, so one fix was attempted: a new Rule 5 was
added to `TUTOR_INSTRUCTION` (`app/agents/tutor_agent.py`) instructing the model to proactively
weave a student's stated interests into examples, and to compress (not skip) derivations for
concepts the student's `get_dpm` record already shows as mastered. This was tested across two
further full eval runs — the first with the rule as originally written, the second with a
refined version adding an explicit "compress the explanation, never the grounding" clause after
the first attempt showed a citation-quality cost.

**What happened, run over run (Arjun, the persona where the effect was clearest):**

| Run | L2 (personalization) | L3 (citation faithfulness) |
|---|---|---|
| Baseline (original 4 rules) | 2/5 — fail | 5/5 — pass |
| + Rule 5, first version | 3/5 — pass | 2/5 — fail (*"introduces concepts... not present in retrieved source texts"*) |
| + Rule 5, refined version | 2/5 — fail (regression didn't hold) | 1/5 — fail, worse |

Ananya's L3 also dipped from 5/5 to 4/5 on the first Rule-5 run (still passing, but the judge
noted *"invented example data beyond context"*), and by the refined version had dropped further to
3/5 (*"the tutor invents a completely new t[opic/example]..."*). Meanwhile L2 for Priya and Rohan
never improved at all across either attempt — both stayed at 2/5, same failure mode, in every one
of the three runs. L1 stayed at 0/4 throughout — the instruction change had no measurable effect
on memory-causality either.

**The tradeoff, plainly:** asking the model to personalize more assertively made it noticeably
more willing to introduce material — a specific number, a worked example, a formula variant — that
wasn't actually in the retrieved `search_grounding` chunks. That's the citation-faithfulness
property this whole memory layer exists to guarantee (`memory_layer.md` §0: "every claim cites
evidence back to a real moment"), and it degraded monotonically across two refinement attempts
while the personalization gain it was meant to produce didn't hold. Rule 5 was reverted in full;
`TUTOR_INSTRUCTION` is back to its original four rules (confirmed clean: all 69 unit tests pass
after the revert). This was an engineering judgment call, not something explicitly requested — the
reasoning: an unreliable, regressing L2 gain isn't worth a reliable L3 loss on the property this
system is specifically built to protect.

**This remains a genuinely open finding**, not a closed one. Two iterations is normal, expected
early progress by this project's own eval-methodology guidance (`google-agents-cli-eval`'s
own note: "Expect 5-10+ iterations... Hold cases back" — a slice of cases graded only once a fix
looks done, to catch overfitting to the exact cases iterated against). What wasn't tried: a
narrower instruction scoped only to interests (leaving mastery-based compression out, since that's
the half more likely to tempt the model into inventing "simplified" derivations); a stronger,
explicit citation-boundary constraint paired with the personalization ask, rather than a soft
"never the grounding" clause; or attacking L1 directly with an instruction to explicitly reference
a specific prior-session fact by name early in a new session's opening turn, which no attempt here
targeted.

**Confirmed by the final run.** The investigation's closing eval run (`07-20-54`, §4) was made
after the revert, on the plain 4-rule baseline, specifically to serve as the final data point
regardless of outcome. It reconfirms both halves of this section: the regression is gone (L3 is
back to 5/5 across every persona, matching the pre-Rule-5 baseline, not the 1/5-2/5 seen mid-
experiment) and the underlying gap it was meant to fix is still there (Priya and Rohan's L2 is
still 2/5, L1 is still 0/4). Reverting fixed the regression it introduced; it was never expected to
fix the gap that motivated the attempt in the first place, and it didn't.

## 6. Open items carried forward

1. **Personalization (L2) and memory-causality (L1) substantiveness (§4.2, §4.3, §5)** — the
   primary open item. One fix attempted and reverted after a citation-faithfulness regression;
   see §5 for what wasn't yet tried.
2. **Real Memorystore, real Shruti embeddings** — still open from the storage-testbed and port
   work (`google_cloud_storage_integration.md` §7); this eval didn't touch either, by design.
3. **The off-syllabus grounding gap** (originally §2.2: a tangentially-framed question not
   triggering `search_grounding` at all) — not re-tested directly in Phase 6; worth a targeted
   case in a future run now that the judge infrastructure can actually score it.
4. **L4 (doubt handling)** has real evidence only from manual review (§4.4), never from an
   automated score in a Phase-6 run — worth a persona/session arrangement that reliably produces
   an open doubt at the check point in a future run.

## 7. Where the artifacts live

- Harness: `sub_modules_examples/tutor/tests/eval/memory_eval/` (`personas.py`, `harness.py`,
  `deterministic_checks.py`, `judges.py`, `judge_subprocess.py`, `run_eval.py`)
- Fix code: `app/memory/store.py` (`_tokenize`, `list_concept_ids`, `_exact_match` +
  fuzzy-fallback `search_grounding`), `app/memory/tools.py` (`list_concepts`),
  `app/agents/tutor_agent.py` (Rule 1, `list_concepts` wired into `tools=[...]`),
  `tests/eval/memory_eval/judges.py` (`_get_client` singleton)
- New/updated tests: `tests/unit/memory/test_store.py`, `tests/unit/memory/test_tools.py`,
  `tests/unit/agents/test_tutor_agent.py`
- The two confirmation runs' full reports (all transcripts, tool-call args, every check's
  detail):
  `sub_modules_examples/tutor/tests/eval/memory_eval/report/results_2026-08-27T06-15-28.734552+00-00.json`
  (first post-fix run) and
  `sub_modules_examples/tutor/tests/eval/memory_eval/report/results_2026-08-27T07-20-54.452603+00-00.json`
  (final run of the investigation, post-revert)

## 8. Fix #3: `reflect()`'s structured-output schema silently no-op'd every close_session (2026-08-27)

Found the same day, by a different route than this eval: building live memory-state
visualization (the SMRITI Observatory's ADK-web integration) drove real conversations through
`close_session` and inspected the actual Firestore writes directly, rather than relying on this
eval's own pass/fail signal.

**The bug:** `session_close.py`'s `ReflectResult.operations[].args` was typed `dict[str, Any]` —
the schema handed to Gemini's structured output (`response_schema=ReflectResult`) as a result has
no field names for the model to fill in. Confirmed live, twice: Gemini reliably returned
`args: {}` for every proposed operation, silently dropped by `apply_operations`'s
malformed-op guard (the same guard §5's citation-integrity design relies on to drop genuinely bad
ops). `close_session` raised nothing and returned normally — it looked like it worked. No
long-term memory was ever actually written by any of the runs behind this report's own "49/49"
number, or the "found" test-driven-development history behind `apply_operations` itself.

**Why D4/D6 (§1, §2) didn't catch it:** D4 only checks that a Firestore document exists with the
right `student_id` after close — true even for an unchanged/empty profile, since `close_session`
always calls `put_dpm`/`put_teaching_memory` regardless of whether any op applied. D6 checks
citation-evidence integrity but explicitly short-circuits to `passed=True, detail="no evidence
pointers to check"` when there's none — exactly the state a fully-empty-ops `reflect()` call
produces. Both checks technically held (they proved what they actually check), but neither
proves what the report's headline sentence claims ("session-close reflection... held up").

**The fix:** a flat, fully-typed `_ReflectOpWire` schema handed to Gemini instead of
`dict[str, Any]`, translated back to the original `ReflectOp(op, args)` shape by `_to_reflect_op`
after parsing — every field gets a concrete JSON-schema type, so the model has something to fill
in. Also spelled out the exact allowed `mastery`/`strength`/`status` enum values directly in
`REFLECT_PROMPT` — live testing showed the model was separately inventing out-of-enum values
(e.g. `mastery: "proficient"`, not in `{unknown, misconceived, partial, known, durable}`), dropped
by the same guard for a second, independent reason. Ported into both
`sub_modules_examples/tutor/app/session_close.py` and its manually-synced copy at
`backend/app/session_close.py` (the latter had no test coverage at all for this path before this
fix; `backend/tests/test_session_close.py` is new).

**Live re-verification, quota-limited:** a full 5-persona `run_eval.py` re-run was attempted
after the fix landed to reconfirm this report's headline numbers on the corrected code, and hit
`429 RESOURCE_EXHAUSTED` on the Vertex AI Express Mode key partway through both attempts (this
session had already made a large number of real Gemini calls). Persona 1 (Arjun, all 3 sessions)
completed in full on the second attempt before the process died on persona 2; its post-close
Firestore state was inspected directly before the harness's own cleanup ran: real weaknesses with
evidence citations, two self-reflection notes, five curriculum coverage entries, one open doubt —
genuinely rich output, not the empty-profile state the bug produced. That's real confirmation the
fix works end to end through the actual harness, but **not** a substitute for the full clean
5-persona run this report's "49/49" number is built on — that reconfirmation is still owed, next
time quota allows a full run without interruption.
- Rerun: `cd sub_modules_examples/tutor && uv run python -m tests.eval.memory_eval.run_eval`
