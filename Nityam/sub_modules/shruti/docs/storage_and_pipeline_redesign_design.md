# Shruti — storage redesign, pipeline simplification, ECHO engine swap

Status: design approved in chat via brainstorming Q&A (2026-08-26). Ready for
an implementation plan.

## 1. Problem

Two real videos have now gone through the full pipeline. Extraction *works*
(PULSE samples real frames, GLYPH reads real slide content, ECHO transcribes
real code-mixed speech, ATLAS mines real concepts and misconceptions with
citations). But three things are wrong with what happens to that content:

1. **ATLAS throws away almost everything it extracts.** `Concept.definition`
   exists on the contract but `mine_concepts` never asks the model for it and
   never sets it. The stored result is a bare name and a timestamp — none of
   the actual explanation, derivation, or board content survives past the
   beat it was mined from.
2. **Coverage is much lower than it looks.** GLYPH's slide-sampling only
   fires on shot cuts. A real 18-minute lecture with continuous screen
   recording (no hard scene cuts) registered as a single PULSE shot, so
   GLYPH sampled two points total for the entire video.
3. **The pipeline runs stages/sub-paths that don't apply to the actual
   content.** PULSE's board-quad/ink-curve/erase-event detection assumes a
   physical chalkboard and runs unconditionally even for slide content,
   where its own output isn't consumed by anything. POINT is capped at the
   first 6 utterances of the video regardless of length or surface kind.

Separately: ECHO (transcription) is both the most expensive stage in the
pipeline (up to ~50% of wall-clock time) and the one stage with a
previously-documented, evidenced reliability gap (non-deterministic
timestamps across identical repeated calls, and — newly confirmed in this
session — an outright hallucinated beat timestamp 2600+ seconds past a
1129-second video's actual duration). Swapping it for a local, purpose-built
ASR model addresses both the cost and — plausibly — the reliability gap in
one move.

## 2. Storage architecture

**Decision: Markdown-first for the actual learning content; Postgres VAULT
stays for structure, citations, and provenance enforcement — it does not go
away.**

Two new kinds of file, both git-tracked (NOT under `.local/`, which is
per-run debug/observability scratch and stays exactly what it is today —
frame dumps and JSON snapshots for inspecting how a run worked mechanically,
not the knowledge product itself):

- **`vault/notes/<recording_id>.md`** — one per-recording narrative,
  generated deterministically (no extra LLM call) from Beats in chronological
  order, each beat's transcript interleaved with its linked BoardState's
  region content. This is the "what actually happened in this lecture,
  readable start to finish" artifact — a staging document that ATLAS reads
  from, and also useful standalone (a student could read "today's class" as
  prose).
- **`vault/wiki/<concept_slug>.md`** — one per concept, **append-only, never
  rewritten** (same principle as the student-facing concept pages in
  `memory_layer.md` §3.4 — rewriting trades specific insight for tidier
  prose and degrades over time). Every time any recording teaches this
  concept, a new "Taught in" entry is appended: citation, explanation for
  that occurrence, any misconceptions preempted, sourced from the widened
  `mine_concepts` output (see §3). `canonicalize.py` is what decides whether
  a mined concept matches an existing wiki page or starts a new one — this
  makes the existing (currently broken, see §3) cross-recording concept
  identity logic a hard dependency of the wiki actually compounding
  correctly, not just a nice-to-have.

Postgres keeps `concept` / `concept_edge` / `misconception` / `beat_ref` /
`board_state` / `board_region` exactly as they are — these stay the
queryable, provenance-enforced backbone. The `.md` files aren't a
replacement for them; they're where the *prose* lives, cited from the same
`shruti:<slug> @mm:ss` scheme already in use, and pointed to by a bare
`wiki_path` — no schema migration needed for that pointer since it's
derivable from the concept's own slug.

## 3. Pipeline stage changes

- **`shruti/stages/atlas/concepts.py`** — widen `_CONCEPTS_PROMPT` to also
  return `definition`/`explanation` per concept (grounded in the beat text
  and any linked board content passed in), and set `Concept.definition` from
  it. This is the fix that makes the wiki pages worth reading.
- **`shruti/stages/atlas/relations.py`** — fix the pre-existing concept
  identity mismatch (`concepts.py` slugifies `canonical_name` into `id`;
  `relations.py` uses the model's raw name verbatim as `from_concept`/
  `to_concept`, which is not the same string and violates the FK on every
  real insert). Apply the same slugify function relations.py's edges resolve
  through, so edges actually persist. Documented in
  `memory_nityam_architecture/README.md` gap #3 — this closes it.
- **PULSE** (`shruti/ingest.py`, PULSE section) — gate `locate_board` /
  `ink_curve` / `find_erase_events` / `build_sample_plan` behind
  `surface_kind in (blackboard, whiteboard)`. For slides/mixed/talking_head,
  skip this sub-path entirely: it costs real compute, its `sample_plan`
  output isn't consumed by the slides branch today, and its "erase events"
  signal is meaningless (and actively misleading) on non-board content.
- **GLYPH slide-sampling** (`shruti/ingest.py`, the `else` branch under
  SLATE+GLYPH) — stop relying solely on shot cuts. Add periodic sampling
  (fixed interval, e.g. every 20-30s) merged with shot-cut points, so a
  single-shot continuous screen recording still gets real coverage across
  its length instead of two samples for an 18-minute video. Exact interval
  and any content-change-detection refinement is an implementation-plan
  detail, not a design fork.
- **POINT** (`shruti/ingest.py`, POINT section) — only run for
  `surface_kind in (blackboard, whiteboard)`. For slides/talking_head,
  GLYPH already reads full slide content directly, gesture-pointing at a
  board region isn't a meaningful signal there, and real runs confirm near-
  zero yield (0-1 gestures found per run, both against slide content) for
  real API cost. `POINT_CAP` stays as the existing bound for the surface
  kinds where POINT still runs.
- **Embedding — DONE, ahead of the implementation plan.** Root cause was
  exactly the config issue predicted: `Models().embedder` was set to
  `"gemini-embedding-2"`, which is not a real model id (a bad translation of
  a product-name doc page into an id string, applied by an earlier
  correction pass — see `nityam_error_registory.md` E21). Live-tested four
  candidate ids directly against `embed_content`; `"gemini-embedding-001"`
  works and returns a real 3072-dim vector. Fixed in `shruti/config.py`,
  full suite verified green (105/105). No implementation-plan task needed
  for this.

No stage is being deleted outright. GATE, WEAVE, and MISCONCEPTIONS are
confirmed doing real, necessary work as-is.

## 4. ECHO: Gemini → local Whisper

**Decision: `faster-whisper`, `large-v3` model, int8 quantization, run
locally.** Plain Python package (uv-installable, no separate build/compile
step) — keeps the integration surface small, which matters given the
explicit ask to not add complexity that can't be easily monitored.
`whisper.cpp` would be faster on this machine's Apple Silicon but requires a
separate compiled binary and a non-Python integration path; rejected for
that reason. `large-v3` over `medium`: code-mixed Hindi-English classroom
speech is exactly the kind of harder input where the larger model's accuracy
gap matters most, and int8 quantization keeps CPU inference tolerable on
Apple Silicon. If real-world latency turns out to be a problem once this is
actually measured against a full lecture, dropping to `medium` is a one-line
config change, not a redesign — noted here so that fallback doesn't require
a new design conversation.

- **Speaker labeling**: default every utterance to `TEACHER`. Whisper does
  no diarization on its own, and in every real run this session, 100% of
  transcribed utterances came back labeled TEACHER — there's no evidence yet
  of content with real back-and-forth dialogue. Not building a
  diarization/speaker-detection path for a case that hasn't shown up.
- **Timestamp sync**: use Whisper's word-level timestamps
  (`word_timestamps=True` in faster-whisper), not just segment-level, since
  segment boundaries are the documented failure mode for the current
  Gemini-based ECHO (non-monotonic timestamps, one hallucinated far past the
  audio's actual duration). This is expected to be more reliable than the
  current approach precisely because it's a purpose-built alignment model
  rather than a general multimodal model guessing at a JSON timestamp field.
- **Fidelity requirement carries over unchanged**: code-mixed Hindi-English
  speech, Hindi in Devanagari, English in Latin script, no translation, no
  script normalization. This needs empirical verification once implemented
  — Whisper's multilingual models handle code-switching with varying
  quality, and this is the one place the swap could regress quality instead
  of just cost. Flagging this explicitly so the implementation plan includes
  a real check against actual code-mixed audio, not just a happy-path
  English test.
- `transcribe_audio`'s signature and `Utterance` contract are unaffected —
  this is an internal swap of what's inside the function, not an interface
  change. Everything downstream (WEAVE, ATLAS, the new narrative generator)
  keeps working against the same `Utterance` shape.

## 5. Explicitly out of scope for this pass

- Multi-speaker diarization (revisit if a video with real dialogue shows up).
- Re-architecting `board_region`/`board_state` beyond what's already fixed
  (namespaced ids, relaxed `derives_from`) — that work is done and verified.
- The console-script (`shruti` binary) sys.path issue — known, worked
  around, unrelated to this redesign.
- Any change to `human_override`, `beat_ref`, or the citation format itself.

## 6. Testing

- `mine_concepts`/`relations.py` fixes get unit tests with a fake client
  returning a `definition` field and verifying the slug-matching fix
  resolves edges without FK violations.
- The narrative/wiki-writer (new module) gets tests against a small
  synthetic set of Beats + BoardStates, asserting deterministic markdown
  output and correct append-not-rewrite behavior on a second write.
- PULSE/POINT surface_kind gating gets tests confirming the board-only
  sub-path is skipped for `slides`/`talking_head` recordings.
- The Whisper swap gets a smoke test against a short real audio clip
  (not synthetic) verifying code-mixed script fidelity and monotonic
  timestamps — this is the one area a fake-client unit test can't actually
  validate quality, matching how ECHO's existing reliability gap was
  originally diagnosed (real audio, not mocks).
- Existing 105/105 suite must stay green throughout.
