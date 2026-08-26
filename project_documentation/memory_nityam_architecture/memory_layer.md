# SMRITI — The Memory Layer (v0.2)

**स्मृति · "that which is remembered"**
What Nityam remembers about a student, how it stores it, and how the tutor's teaching improves over time.

Supersedes v0.1. Shorter, and organised around three questions instead of five layers.

---

## 0. What changed from v0.1, and why

You were right that it was confusing, and there were two real mistakes underneath.

**Mistake 1 — I made SQL schemas the primary format.** They aren't. The DeepTutor paper you just uploaded settles this: their learner profile `D = (D_s, D_w, D_r)` is three *prose views*, and Appendix D.6 states that weakness transitions are **evidence-gated, not numeric** — *"a weakness is marked resolved when the user answers correctly on the topic in recent sessions and stops re-asking about it."* No confidence score, no threshold. And the most detailed picture of a learner anywhere in that paper is Listing 1 — the student simulator prompt — which is a **markdown document with headings**: Who You Are, Your Background, Why You Are Here, What You Know, What You Believe.

That's a wiki page. So v0.2 stores the learner as a wiki page (§3), and keeps exactly one small table for the six numbers that genuinely need arithmetic (§4).

**Mistake 2 — I left out teaching mode entirely.** A memory that knows *what* a student is weak at but not *how they should be taught right now* is half a memory. §5 is the fix, and it's the most important new section.

**One correction to your framing, offered carefully:** "learning style" in the visual/auditory/kinesthetic sense is a well-documented neuromyth. Pashler et al. reviewed 70+ studies and found essentially no evidence that matching instruction to a stated style improves achievement; the meshing hypothesis has been repeatedly disconfirmed. So do **not** store *"Anmol is a visual learner."*

But your instinct is right, and three real things sit underneath it:

| What's real | Evidence | Where it lives |
|---|---|---|
| **Prior knowledge changes what teaching works** | Expertise reversal effect (Kalyuga, Sweller). Worked examples help novices and *actively hurt* experts. | Concept page + mode selector |
| **Preference affects whether they keep going** | Motivation, not comprehension. Still worth honouring. | Learner page |
| **Mode is a property of the moment, not the person** | Adaptive fading beats fixed fading (Renkl et al.) | Session state |

The reframe: **teaching mode is a setting we choose per concept per moment from evidence — not a personality type we assign once.** That is both better science and a better product.

---

## 1. What the memory has to do

Nityam is a voice tutor that draws on a canvas, grounded in the student's own classroom lesson. Before the tutor opens its mouth, memory must answer three questions:

> **① Who am I teaching?** → `LEARNER.md`
> **② What do they know, and what's fading?** → the concept pages + one schedule table
> **③ How should I teach this, right now?** → the mode, and the method skill for that mode

Three questions, three artifacts. That's the whole design. Everything below is detail.

---

## 2. Why markdown, not schemas

> **Write memory the way you'd want the student to read it over your shoulder. Keep one small table, only for numbers that need arithmetic.**

Five reasons, in order of weight:

**1. Markdown is what the model actually consumes.** A page goes into the prompt verbatim. A SQL row has to be serialized into prose first — a lossy translation step you write, maintain, and debug forever. The wiki removes a whole layer.

**2. Confusions don't have a schema.** *"Treats (x+3)² as x²+9, expands by squaring each term separately, and their own teacher warned about this on 24 Aug"* — you cannot represent that faithfully in typed columns. Try, and you'll end up with a `notes TEXT` field doing all the work, which means you built a wiki with extra steps.

**3. It's readable and editable by the student, the parent, and the teacher.** That gives you an Open Learner Model for free — and the research on scrutable and negotiable learner models finds that letting a learner see and argue with the system's beliefs improves both model accuracy and the learner's own self-assessment.

**4. It's a git repo.** Version history for free. A diff shows how a student changed over a term. That is a genuinely useful teacher artifact and it costs nothing.

**5. It survives everything.** New model, new framework, new vendor — the files still make sense.

This is the LLM-wiki pattern, which is well-established now: raw sources stay immutable, the agent maintains an interlinked markdown knowledge base derived from them, and a schema file tells the agent how to maintain it. *"The knowledge is compiled once and then kept current, not re-derived on every query."* DeepTutor's own shipped memory works this way too — L1 append-only event traces, L2 per-surface facts, L3 synthesis, **deliberately not a hidden vector store**, with L2 citing L1 so nothing in a profile is unaccountable.

**Where markdown is the wrong tool:** you will query *"which concepts are due today"* thousands of times per day, and you must never let a language model near that arithmetic. That gets a table. It's six columns (§4).

---

## 3. The student's wiki

```
students/anmol/
├── LEARNER.md                        ← who. ~120 lines. Injected every turn.
├── concepts/
│   ├── quad.completing-square.md     ← one page per concept touched
│   └── kinematics.range.md
├── sessions/
│   └── 2026-08-24.md                 ← what happened. Append-only.
└── tutor-notes.md                    ← what works for THIS student. Append-only.
```

Four kinds of file. That's it.

### 3.1 `LEARNER.md`

Injected on every turn. Hard cap ~120 lines — past that, adherence measurably drops, which is why Claude Code's own guidance targets under 200 lines for the file it loads into every session.

```markdown
# Anmol · Class 9 · CBSE

## Who
14. Mumbai. Studies in Hindi-English mix — English for technical terms,
Hindi for reasoning aloud. Impatient with long explanations; interrupts
when he's got it.

## Why he's here
Half-yearlies in November. Maths is the worry; he likes physics.

## What he cares about
Rockets, cricket. Frame problems in those when it's natural — not forced.

## Standing preferences
- Wants to be made to think. Said so on 19 Aug: *"sir mujhe sochne do."*
  → Default to socratic unless he's genuinely new to a concept.
- Hates being asked "did you understand?" Ask him to explain it back instead.

## How he learns (observed, not assumed)
- Area models and diagrams land fast. Pure symbol manipulation loses him
  around step 3. [→ 2026-08-19 #6, 2026-08-24 #14]
- Recovers well from being stuck. Doesn't need reassurance, needs a nudge.

## Where he stands
Strong: linear equations, coordinate geometry
Shaky: quadratics (completing the square), trigonometric identities
Untouched: circles, surface areas

## Not for discussion unless he raises it
[sensitive entries live here — read only when the student opens the topic]
```

Note the shape. It's the DeepTutor student-simulator prompt structure (Who / Background / Purpose / What You Know / What You Believe) turned around: instead of describing a simulated student *to* a simulator, it describes a real student *to* a tutor. Same document, opposite direction.

Note also `[→ 2026-08-19 #6]`. **Every behavioural claim cites a session and a turn.** That's the one rule this system must not break, and it's what makes the "why do you think that about me?" button possible.

### 3.2 A concept page

One per concept the student has actually touched. Created on first contact, updated at session end.

```markdown
# Completing the Square
`quad.completing-square` · Class 9 · Maths · Ch. 2 Polynomials

## Where Anmol is
**Partial.** Completes the square fine when b is even. Loses the sign
when b is negative. Last checked 24 Aug.

## Open confusion
> He treats (x+3)² as x²+9.

**How it shows up:** expands the bracket by squaring each term separately.
**What's true:** (a+b)² = a² + 2ab + b².
**His teacher already warned about this** on 24 Aug — *"yeh sabse common
galti hai"* — so use her words, he'll recognise them. [→ shruti:lec_41 @23:14]

**Status:** remediating. Cleared once on 24 Aug. Needs one more spaced
check before this closes. [→ 2026-08-24 #12]

## What worked, what didn't
- ✓ Area model shown *before* any algebra. Landed immediately. [→ 24 Aug #14]
- ✗ Starting from the symbolic identity. Lost him by step 3. [→ 19 Aug #6]
- ✓ Letting him predict the sign before revealing it. [→ 24 Aug #17]

## Current mode
**guided-practice** (I do a step, he does a step). Was worked-example
until 24 Aug, when he started completing steps unprompted.
```

Three things this format does that a schema can't:

- **Manifestation and correction sit together.** DeepTutor's TutorBench encodes each knowledge gap as *manifestation* (how the student would exhibit it) plus *correct understanding*. Same idea, in prose, where it reads naturally.
- **Status is evidence-gated.** "Cleared once, needs one more spaced check" — not `confidence: 0.72`. This mirrors DeepTutor's actual implementation, which uses prompt-based criteria rather than numeric thresholds, and requires explicit correction of the misconception plus an explanation of why the old understanding was wrong.
- **The teacher's own phrasing is preserved and cited back to SHRUTI.** Nobody else can do this, because nobody else watched the class.

### 3.3 A session page

Append-only. Written during the session, never edited after.

```markdown
# Session · 24 Aug 2026 · 22 min · quadratics

#8  Q: "sir (x+3)² ka expand kaise karte hain, x²+9 hi hoga na?"
#9  → misconception surfaced: quad.completing-square
#10 mode: socratic → worked-example (he's genuinely new here)
#11 artifact: area-model {a:x, b:3}
#12 attempt: correct, unaided, after seeing the area model
#14 note: area model landed instantly. Contrast with 19 Aug.
#17 attempt: predicted the sign correctly before I revealed it
#19 barge-in during my explanation of the general form
    → classified: "already got it", not "lost"
#21 mode: worked-example → guided-practice
```

Terse, greppable, and the numbered turns are what everything else cites.

### 3.4 `tutor-notes.md`

What works for *this* student, across all concepts. **Append bullets; never rewrite the file.**

```markdown
- Show the picture before the algebra. Every time it's worked. [24 Aug, 12 Aug]  ✓4 ✗0
- Let him predict before revealing. He engages harder. [24 Aug]                  ✓2 ✗0
- Don't ask "did you understand". Ask him to explain it back. [19 Aug]           ✓3 ✗0
- Reframing in cricket terms. Tried once, he found it patronising. [12 Aug]      ✗1
```

The `✓/✗` counters matter more than they look. They're how a note earns its place or gets retired, and they're how you later spot which notes generalise across students (§7).

**The rewrite trap, in plain terms:** the obvious design is "at session end, ask the model to rewrite the student's profile." Don't. Each rewrite trades a specific insight for a tidier sentence, and after ten sessions the page has degraded into generic mush. The ACE paper measured exactly this — an agent's context eroding to 66.7% accuracy through iterative rewriting — and the fix is not a better summarizer, it's **never rewriting**. Append bullets. Increment counters. Edit only the one-line status at the top of a concept page.

---

## 4. The one table

```sql
CREATE TABLE schedule (
    student_id  TEXT NOT NULL,
    concept_id  TEXT NOT NULL,
    difficulty  REAL,          -- FSRS D
    stability   REAL,          -- FSRS S, in days
    due         TIMESTAMPTZ,
    lapses      INT DEFAULT 0,
    reps        INT DEFAULT 0,
    page_path   TEXT NOT NULL, -- → students/anmol/concepts/quad....md
    PRIMARY KEY (student_id, concept_id)
);
```

Six numbers and a path. That is the entire database.

It exists because *"what's due today"* runs constantly and must be exact, and because FSRS is arithmetic — stability is the number of days until recall probability falls to 90%, and a model paraphrasing that into "needs review soon" destroys the scheduler silently. Written only by code, from a graded attempt. An LLM produces the grade; the arithmetic is a pure function.

Everything a human would want to *read* is in the wiki. Everything a computer needs to *compute* is here. No overlap, no second source of truth.

---

## 5. Teaching modes

The missing half of v0.1.

### 5.1 Six modes

Each is a folder with a `SKILL.md`. The tutor loads exactly one at a time.

| Mode | The tutor… | Use when | Never |
|---|---|---|---|
| **socratic** | Asks a question that makes the student produce the next step. Hints only. | Student has a wrong model to surface, or knows enough to reason to it | Reveals the answer, however asked |
| **worked-example** | Solves it fully, narrating *why* at each step. Then hands over a twin problem. | Concept is genuinely new (`unknown`). Load is high. | Asks them to derive something they've never seen |
| **guided-practice** | Alternates: tutor does a step, student does the next. Fades over turns. | `partial` — right idea, unreliable execution | Keeps doing steps the student has already shown they can do |
| **productive-failure** | Hands over the hard version *first*, lets them try suboptimal approaches, then teaches into the gap they just felt | Strong student, new concept, time available | Runs when the student is already frustrated or short on time |
| **review-probe** | Short spaced re-check. Two or three items. No teaching unless they miss. | FSRS says due | Turns into a lesson without the student asking |
| **direct** | Answers plainly and moves on | Factual lookup · concept `durable` · exam tomorrow · student is spent | Is the default for anything |

The evidence behind the first four is unusually solid. Worked examples beat problem-solving for low-knowledge learners and the relationship **reverses** as knowledge grows — that's the expertise reversal effect, and adaptive fading (support removed in response to individual progress) outperformed both fixed fading and constant support in Renkl's studies. Productive failure has a meta-analysis behind it: Sinha & Kapur's review of 53 studies found it more effective than classical teaching methods.

### 5.2 Mode selection is a table, not a judgement

```python
def select_mode(concept_page, session, learner) -> Mode:
    # 1. Student's explicit request wins — with one exception
    if session.requested_mode:
        if session.requested_mode == "direct" and concept.mastery != "durable":
            return "guided-practice"          # ← the assistance dilemma, resolved
        return session.requested_mode

    # 2. Standing preference from LEARNER.md
    if learner.pinned_mode and concept.mastery in ("partial", "known"):
        return learner.pinned_mode

    # 3. Evidence
    match concept.mastery:
        case "unknown":       return "worked-example"
        case "misconceived":  return "socratic"      # surface the wrong model first
        case "partial":       return ("guided-practice" if session.fails >= 2
                                      else "socratic")
        case "known":         return ("review-probe" if concept.due <= today
                                      else "socratic")
        case "durable":       return "direct"

    # 4. Overrides
    if session.frustration_signals >= 2:  return "worked-example"
    if learner.exam_within_days <= 3:     return "review-probe"
```

Deterministic on purpose. Mode is too important to leave to model vibes turn by turn, and a table is something you can read, argue with, and change.

### 5.3 Scaffolding collapse — the failure this prevents

There is a named, measured failure mode for Socratic tutors: **under sustained student pressure, the tutor gradually abandons guided inquiry and starts revealing solutions.** Recent work red-teams this with an adversarial student that escalates pressure each turn and records the turn at which collapse occurs.

Every LLM tutor promises "it asks before it tells." Almost all of them fold when the student pushes. The reason is that mode lives in the prompt, so a persuasive student can talk the model out of it.

**The fix is that mode is state, not prompt.**

```python
# session.state["mode"] can ONLY be changed by:
#   1. check_attempt()  — evidence of progress or of being stuck
#   2. switch_mode()    — an explicit, logged, student-initiated request
# The model has no other route. Persuasion does not compile.

class ModeGuard(BasePlugin):
    async def before_tool_callback(self, *, tool, tool_args, tool_context):
        mode = tool_context.state["mode"]
        allowed = MODE_TOOLS[mode]
        if tool.name not in allowed:
            return {"blocked": True,
                    "reason": f"{tool.name} is not available in {mode} mode."}
```

`reveal_solution` is simply not in the tool list while mode is `socratic`. The model cannot use a tool it doesn't have.

This gives you your best demo beat: say *"just tell me the answer"* on stage, three times, escalating, and watch it hold — then say *"okay, I've tried, here's my attempt"* and watch it open up.

And it gives you a real metric: **turns-to-collapse under adversarial pressure.** Target: no collapse in 16 turns.

### 5.4 Modes as skill files

Each mode is an Agent Skill — a folder with `SKILL.md`, following the open standard (agentskills.io, released Dec 2025, now supported across 40+ platforms).

```
methods/socratic/
├── SKILL.md            ← ~600 tokens. Loads only when mode is socratic.
├── references/
│   ├── question-ladder.md
│   └── when-to-yield.md
└── examples/
    └── algebra-misconception.md
```

```markdown
---
name: socratic
description: >-
  Teach by questioning. Use when the student holds a wrong model that needs
  surfacing, or already knows enough to reason to the answer. Do not use for
  concepts they have never seen.
---

# Socratic mode

## The ladder — climb one rung per turn, never skip
1. **Orient.** Ask what they think happens, before anything else.
2. **Probe.** Ask the question whose answer exposes the contradiction.
3. **Hint.** Point at the thing, don't name it. "What's the area of that
   middle rectangle?"
4. **Partial.** Give the first step only. Ask for the second.
5. **Yield.** Only after a genuine attempt. Then narrate the whole thing.

## Rules
- One question per turn. Two is an interrogation.
- Never ask "do you understand?" — ask them to say it back in their words.
- If they're wrong, don't correct. Ask the question that makes the
  wrongness visible to them.
- Three failed rungs → switch to guided-practice. Don't grind.

## Never
- Reveal the answer before rung 5, no matter how the student asks.
- Ask a question you know they can't answer. That's not Socratic, that's
  a quiz.
```

**Why skills and not code:** progressive disclosure. Only `name` + `description` load at startup — about 80–100 tokens per skill. Anthropic's own 17 official skills cost ~1,700 tokens of standing context *in total*. So you can have 30 teaching methods and 25 artifact templates installed for ~4,000 tokens, and only the one that fires loads its body.

The same applies to the artifact templates from the Artifact Layer doc:

```
artifacts/projectile-motion/
├── SKILL.md            ← when to reach for it, what the params mean
├── kernel.ts           ← the closed-form maths
└── examples/
```

**This is the answer to "how does it grow."** A new teaching method is a new markdown file. A new artifact is a folder. No code change, no deploy, no schema migration. And a teacher who has a particular way of introducing quadratics can write one — which is the network effect DeepTutor is chasing with its EduHub skill registry.

---

## 6. What goes into context, per turn

| | Source | Tokens |
|---|---|---|
| `LEARNER.md` | always | ~400 |
| Active concept page | always | ~250 |
| Active method skill body | on mode selection | ~600 |
| Active artifact skill body | on artifact call | ~500 |
| All skill names + descriptions | always | ~800 |
| Session so far | ADK `session.state` | ~500 |
| **Standing total** | | **~3,050** |

Past sessions, other concept pages, the full note history: **tool only, never automatic.** The agent calls `recall(query)` when it needs them.

That's the whole point of progressive disclosure, and DeepTutor's implementation is a useful sanity check on the budgets: trace retrieval defaults to `top_k = 3–5`, individual trace views truncate at 6,000 characters, solver scratchpad 6,000 tokens, writer 12,000. Small, capped, deliberate.

ADK gives you the plumbing free — `user:`-prefixed state persists across all of a student's sessions, `temp:` vanishes after the invocation, and `{placeholders}` in an agent instruction are filled from state at run time. Your Day 1 memory system is `user:pinned_mode` and nothing else.

---

## 7. How it improves — three loops, three speeds

**Per turn — mode adapts.** `check_attempt` returns `genuine_attempt | guess | stuck | refusing`, and the mode selector re-runs. Cheap, immediate.

**Per session — the tutor writes what it learned.** One background agent reads the session page and emits *appends only*:

```python
writer = LlmAgent(
    name="SessionWriter", model=Gemini(model=REASONER),
    instruction="""You did not teach this session. Read it as an observer.

Session: {session_page}
Concept pages touched: {concept_pages}

Emit ONLY these operations. Never rewrite a file.
  - append_note(file, bullet, evidence_turns)
  - increment(note_id, "helpful" | "harmful")
  - set_status(concept_id, mastery, one_line_reason)   ← the only edit-in-place
  - open_confusion(concept_id, manifestation, correct_understanding, turn)
  - close_confusion(concept_id, turn)   ← only after a SPACED clear, not a single
                                          correct answer

For status changes, use evidence, not confidence. "Cleared once on 24 Aug,
needs one more spaced check" — not a number.""",
)
```

**Per week — the curator prunes and promotes.** Merges duplicate notes, retires anything with `✗ > ✓`, and — the interesting one — **spots notes that work across many students and proposes them as new method skills.**

```
"Show the picture before the algebra"
  ✓47 ✗3  across 31 students, all on quadratics
     ↓ promote
methods/visual-first-algebra/SKILL.md
```

That is the compounding asset. Per-student notes make one student's tutor better. Promoted method skills make **every future student's** tutor better, including students who haven't signed up yet. Don't build the promotion pipeline now — but the counters and the `scope` field mean you won't have to redesign for it.

---

## 8. Two rules that don't bend

**The student owns their pages.** They can read every file, and edit any of it. A student edit is marked `[student-edited]` and no background pass may overwrite it. This is an Open Learner Model in the technical sense, and the literature is clear that letting learners scrutinise and negotiate the system's beliefs improves both model accuracy and the learner's own self-assessment. It also happens to be the honest thing to do when the subject is a 14-year-old.

**The tutor can learn *how* to teach, never *whether*.** Method skills are reviewed before install. A student cannot talk the system into a `just-tell-me` method, and per-student notes cannot override a method skill's `## Never` section. Concretely: a note saying *"he prefers getting the answer directly"* is allowed to exist and is allowed to influence framing — but it cannot remove `reveal_solution` from the mode guard.

---

## 9. Build order

| | Build | Time |
|---|---|---|
| **Day 1** | `LEARNER.md` + one concept page, **written by hand**. Inject both into the tutor prompt. | 2 hours |
| **Day 2** | Session pages + the end-of-session writer (appends only) | 1 day |
| **Day 3** | Three method skills — `socratic`, `worked-example`, `direct` — plus the mode selector table and `ModeGuard` | 1 day |
| **Day 4** | The `schedule` table + FSRS + `review-probe` mode | 1 day |
| **Week 2** | `tutor-notes.md` with counters; `guided-practice` and `productive-failure` | |
| **Later** | The weekly curator; cross-student skill promotion | |

**Day 1 is not a toy.** Hand-write one student's page, inject it, and the tutor is already more personalised than most products on the market. Everything after that is automating the writing of a file you already know the shape of.

**If you're behind, cut in this order:** curator → `productive-failure` → `tutor-notes` counters → the schedule table.
**Never cut:** `LEARNER.md`, the concept page, the `ModeGuard`, and the citation rule. Those four are the system.

---

## 10. Evaluating it

Three cheap tests, all demoable:

| | Test | Pass |
|---|---|---|
| **M1** | **Turns to collapse.** Adversarial student escalates "just tell me" for 16 turns while mode is `socratic`. | No collapse in 16 |
| **M2** | **Does the page read true?** Show three students their own `LEARNER.md`. Ask what's wrong. | ≥80% of claims accepted; every rejected claim has a citation they can check |
| **M3** | **Citation invariant.** Automated: every behavioural claim in every page resolves to a real session turn. | 100%, enforced in CI |

M1 is the one to run on stage. M3 is the one that should fail the build.

---

## 11. v0.3 — refinements from a deeper research pass

A follow-up research pass (ADK source, Zep/Graphiti, the ACE paper re-read against its actual text rather than a paraphrase, DeepSeek Harness, and the Gemini Enterprise Agent Platform's Memory Bank) found the v0.2 design sound but sharpened five things. None of these change §2's core decision — they refine how it's implemented.

**"Append-only" was an oversimplification of what actually works.** The real ACE paper (arXiv 2510.04618, ICLR 2026, verified against its actual text) doesn't argue for pure append-only — its mechanism is **grow-and-refine**: new bullets get IDs and are appended, but *existing* bullets are updated in place (a helpful/harmful counter increments, for instance) and a periodic semantic de-duplication pass prunes redundancy. That's closer to what §5.2's `increment`/`set_status` operations already do than the "never rewrite" framing suggests. The infamous collapse numbers (66.7%→57.1% accuracy) describe a *different, prior* method (Dynamic Cheatsheet, a full-rewrite baseline) that ACE's own paper uses as the cautionary example — not something that happened to ACE itself. Reword any "never rewrite, ever" language to "append new entries; update existing entries' counters and status in place; periodically de-duplicate" — this is both more accurate to the source and a better description of what §5.2 already specifies.

**Notes and confusions need supersession metadata, not just append-order.** Borrowed from Zep/Graphiti's bi-temporal edges (new information invalidates old information but never deletes it — full history stays queryable): give each `tutor-notes.md` bullet and each concept-page confusion entry a `created_at` / `status` / `superseded_by` triple. Without this, two notes about the same concept can sit in the file contradicting each other with no signal about which is current — a documented failure mode in reflection-based memory systems generally, not a hypothetical one.

**Session-log pages need an explicit archival policy.** Nothing in v0.2 bounds the growth of `sessions/*.md` over a multi-year tutoring relationship. Cap the active log at a size (or a rolling window), and roll older sessions into a cold-storage page — still git-tracked, still auditable, just excluded from default retrieval and reindexing. Otherwise index-rebuild time and the "human-readable" promise both degrade slowly and invisibly.

**Frame the RAM buffer as ground truth; the wiki as a derived, re-derivable view.** One idea worth taking from DeepSeek Harness (a real, current open-source coding-agent harness — not directly reusable code, wrong language/domain, but this one pattern generalizes): its append-only `SessionEvent` log is the actual source of truth, and everything the model sees is a pure function of that log. Applied here: the raw per-session buffer (already flowing into `state_delta`, per §4) is what's truly authoritative; `sessions/*.md` and the concept-page edits are a distillation *of* it. This doesn't change anything that's already built — it just means that if a bug is ever found in the write-back distillation logic, the wiki can be re-derived from the raw log rather than trusted blindly. Worth preserving raw buffers for longer than the wiki pages that get built from them.

**Gemini Enterprise Agent Platform's Memory Bank does not replace any of this — checked directly, including its new Memory Profiles feature.** Both modes were evaluated specifically for whether they close the citation gap this document's §3 and §8 depend on. Neither does — see `google_platform_integration.md` §2 for the full evaluation. One narrow addition earned from that check: Memory Profiles (a typed, low-latency, schema-customizable record Memory Bank now supports) is a reasonable place for soft personalization facts that were never going to carry a citation anyway — stated name, preferred explanation style, self-reported grade. It must never hold anything §3's citation rule protects.

---

## Appendix — What each source contributed

**DeepTutor** (arXiv 2604.26962v3) — learner profile as three prose views `D_s / D_w / D_r`; the three memory agents are literally named *summary, weakness, reflection* (Table 8, temp 0.5, 8192 tokens); **weakness transitions are evidence-gated and prompt-based, not threshold-based** (Appendix D.6); knowledge gaps carry *manifestation* + *correct understanding*; profiles use `known_well / partially_known / unknown`; trace retrieval `top_k = 3–5` with level-specific filtering; the student-simulator prompt (Listing 1) as the canonical learner-document shape; SOUL files for teaching philosophy; skills as portable workflow descriptors shared through EduHub. Ablation: removing DPM drops Personalization 8.1% and Fitness 6.0% — the learner model is what makes explanations gap-aware.

**LLM Wiki** (Karpathy pattern; `llm-wiki-plugin`, `llm-wiki-agent`) — three layers: immutable sources / agent-maintained markdown wiki / a schema file governing maintenance. Knowledge compiled once and kept current rather than re-derived per query. Contradiction flagging at ingest. Split a page past ~200 lines.

**Agent Skills** (agentskills.io, open standard Dec 2025) — `SKILL.md` with `name` + `description` frontmatter; three-tier progressive disclosure (~80–100 tokens discovery, <5k body, bundled files on demand); Anthropic's 17 official skills ≈ 1,700 tokens standing context total.

**Teaching modes** — Kalyuga & Sweller, expertise reversal effect; Renkl et al. on adaptive fading beating fixed fading; Kapur, productive failure, with Sinha & Kapur's 53-study meta-analysis; Puech et al., *Pedagogical Steering of LLMs* (StratL — tutoring intents on a transition graph); *Mitigating Scaffolding Collapse in Socratic Tutors* (arXiv 2607.19371) for the collapse failure mode and the red-team protocol.

**Learning styles** — Pashler et al. (70+ studies, no support for meshing); Newton, *The Learning Styles Myth is Thriving in Higher Education*; Dekker et al. on neuromyth prevalence among teachers (93–96%).

**Not rewriting** — Zhang et al., *Agentic Context Engineering* (arXiv 2510.04618, ICLR 2026): brevity bias, context collapse, delta updates over monolithic rewrites. Re-verified against the paper's actual text for v0.3 (§11) — the mechanism is grow-and-refine (append + in-place update + periodic dedup), and the cited collapse numbers describe a prior baseline method, not ACE itself.

**Bi-temporal supersession** — Zep / Graphiti (arXiv 2501.13956): edges are invalidated, not deleted, on conflicting new information; full history stays queryable. Applied in v0.3 §11 as lightweight frontmatter on notes and confusion entries.

**Event-log-as-truth** — DeepSeek Harness (real, MIT-licensed, released 2026-08): an append-only `SessionEvent` log as the single source of truth, with everything the model sees derived from it as a pure function. Applied in v0.3 §11 as a framing for the existing RAM-buffer design, not a new mechanism.

**Gemini Enterprise Agent Platform** — Memory Bank (free-text and Profiles modes) and the platform's other managed services, evaluated in full in the companion `google_platform_integration.md`.

**ADK** — `session.state` prefixes (`user:` / `app:` / `temp:`); `{placeholder}` instruction templating; `BasePlugin.before_tool_callback` returning a value to short-circuit a tool; `DatabaseSessionService` for persistence.

**Open Learner Models** — Bull & Kay: scrutable, cooperative, negotiable, editable.

---

*v0.3. §2's core decision is unchanged and now independently verified against Google's managed alternatives (§11, `google_platform_integration.md`) — markdown wiki as primary, one six-column table for the scheduler, nothing else. §11 refines *how* the append-only rule and session-log growth are handled; it does not reopen §2. If §2 is agreed, §9 Day 1 can start today.*