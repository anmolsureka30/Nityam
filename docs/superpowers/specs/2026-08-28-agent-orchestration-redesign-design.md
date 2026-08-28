# Agent orchestration redesign — VoiceAgent + specialists

Status: draft, awaiting review. Nothing in this document has been built yet.

## 1. Goal

Replace today's shape — a small `VoiceAgent` bridging to one monolithic
`TutorAgent` that holds nine board tools, two textbook tools, grounding, and
artifact commissioning all at once — with a router-plus-specialists shape:

- **VoiceAgent** talks, reads the board, answers what's already in front of
  it, and routes anything substantive to exactly one specialist.
- **BoardAgent**, **ArtifactAgent**, **QuizAgent**, **TextbookAgent** each own
  one domain's judgment and tools completely. `TutorAgent` is retired — its
  board-writing judgment moves to BoardAgent, its textbook logic moves to
  TextbookAgent.
- Every specialist call is genuinely fire-and-forget: VoiceAgent keeps
  teaching while a specialist works, and the result lands back in the
  conversation at a natural pause — never mid-sentence.
- No agent's prompt names a specific subject, chapter, or concept. Everything
  subject-specific comes from the shared grounding substrate (today:
  `grounding_chunk` in Firestore, populated by Shruti/book ingestion) at
  runtime.

Everything below assumes the reader has `docs/.../2026-08-28-...` style
context on the current codebase; the companion reference is the "Nityam Agent
Atlas" produced this session (agent topology, full tool inventory, the one
existing callback, the six memory tiers, and the exact context-over-time
walkthrough) — this spec calls out deltas from that baseline rather than
re-describing it.

## 2. The core mechanism: native scheduled function responses, not a hand-built queue

This is the answer to the hardest part of the brief — "the voice agent
shouldn't wait, and shouldn't feel interrupted."

Gemini Live API supports asynchronous function calling: a tool can be tagged
with `response_scheduling`. Confirmed against ADK's actual source
(`google/adk/tools/base_tool.py`, `google/adk/flows/llm_flows/functions.py`)
and Google's own sample (`contributing/samples/live/live_non_blocking_tool_agent`):

- The tool call returns to the model **immediately** (the model is never
  blocked), while ADK runs the real work as a background `asyncio` task.
- `WHEN_IDLE` — the Gemini Live API server itself holds the `FunctionResponse`
  and delivers it into the model's context **at the next natural pause**,
  letting the model react to it as a normal turn.
- `SILENT` — delivered similarly, but without forcing a reaction; the model
  simply knows it for later reference.

This is **server-side** behavior, not a client-side heuristic — it doesn't
race the event stream the way a hand-built "watch for a gap" tracker would
(the exact failure mode this research turned up in adjacent ADK/Gemini issues
on premature turn-complete signals). It is also the same principle every
production voice-agent platform surveyed converges on (LiveKit's `async
tools`, OpenAI Realtime's async function calling, Pipecat's deferred
developer-message injection) — gate on the platform's own idle/turn-complete
signal, never on a fixed timer, never force an interrupt.

Confirmed compatible with the model already in use: async function calling
is supported on `gemini-live-2.5-flash` (Nityam's current Live model) — it is
**not** yet supported on Gemini 3.1 Flash Live, so no model change is needed
or possible here.

**What this replaces:** `sessions.py`'s `nudges`/`context` queues, `main.py`'s
`nudges()`/`injections()` background tasks, and `brain.py`'s
`asyncio.Queue.get()`-driven delivery all go away. A specialist call becomes
an ordinary `async def` tool that `await`s its own Runner to completion and
returns the real result, tagged `response_scheduling=WHEN_IDLE`. One
mechanism, not two — a spoken result and "VoiceAgent now knows the fact" are
the same delivery, since the `FunctionResponse` lands in context either way.

**What does not change:** board patches keep reaching the browser exactly as
today, through `sessions.publish() → outbox → outbound()` — a channel
entirely separate from the Live model's own context. A specialist's visual
result can appear on screen slightly before VoiceAgent comments on it
verbally; that's the natural order (see it land, then hear about it), not a
race to fix.

**Why not real ADK sub-agent nesting instead?** A fix landed in google-adk
2.8.0 that stops `run_live` from crashing on a nested `mode='single_turn'`
sub-agent. It does **not** make that path non-blocking — nesting still
blocks the parent's turn until the child returns; only the
`response_scheduling`-tagged separate-Runner-tool path gets the
non-interrupting property. The current separate-Runner-per-specialist shape
(already used for ArtifactAgent) is kept for exactly this reason; only how a
specialist's *result* gets back to VoiceAgent changes.

**Model call, not code call:** the model can technically call the same
specialist tool twice before the first resolves. Rather than reintroducing
`brain.py`'s hand-rolled `_pending`/`_running` queue, each specialist tool's
own docstring says plainly not to call it again while a call is outstanding —
the same convention `ask_tutor` already uses successfully today. Two
concurrent calls wouldn't corrupt anything (board writes are append-only),
this is a prompt-discipline note, not a code guard.

**ADK upgrade:** the `WHEN_IDLE`/`SILENT` mechanism itself works on the
currently-installed 2.7.1 (`response_scheduling` predates it). Upgrading to
2.8.0 is still worth doing alongside this work — it adds
`event.interaction_status` (`IDLE`/`IN_PROGRESS`), useful as an Observatory
diagnostic, and the same `run_live` fix that's a prerequisite for streaming
tools if those are ever used later. Not required for this redesign to work.

## 3. The agents

### VoiceAgent (unchanged role, smaller tool surface than today's TutorAgent-bridge)

- Model: `gemini-live-2.5-flash` (unchanged).
- Tools: `read_screen`, `point_at`, `scroll_to` (unchanged — free, local,
  zero-latency) plus four new delegate tools: `ask_board`, `ask_artifact`,
  `ask_quiz`, `ask_textbook`. Each takes `(bridge: str, request: str)`,
  matching today's proven `ask_tutor` shape (a spoken bridge line as a
  required argument, not a separate step — the exact fix for the
  speak-vs-call race documented in `voice_agent.py`'s own history).
- Answers directly, per today's existing rule, when the thing being asked
  about is already on the board or in its briefing. Everything else is a
  delegate call — including any substantive explanation (see §5, "explain"
  folds into BoardAgent, no separate teaching path on VoiceAgent itself).
- System instruction stays fixed-size and small, per the existing,
  already-verified constraint: the Live API bills the whole system
  instruction on every turn. Nothing subject-specific or student-specific
  lives in it.

### BoardAgent (new — absorbs TutorAgent's board-writing judgment)

- Owns: all 9 current board tools (`write_lesson` and friends),
  `search_grounding`, `list_concepts` — real pedagogical judgment, not just
  formatting. Given a request and the last-N transcript, it decides *what*
  to teach and writes it, citing the actual lecture content.
- This is where "explain a new concept" lives — matching the existing
  philosophy ("everything worth remembering goes on the board... a lesson
  that only happened out loud did not happen") and the approved decision not
  to add a separate spoken-only explain path.
- Its own Runner, `run_async`, same shape as today's TutorAgent/ArtifactAgent.

### ArtifactAgent (existing, unchanged internals — only the return path changes)

- Same `create_artifact`/generate-validate-retry pipeline as today.
- Reached via `ask_artifact`, tagged `WHEN_IDLE` — replaces `commission_artifact`'s
  current fire-and-forget-plus-hand-rolled-nudge return.

### QuizAgent (existing, gets real transcript instead of a hand-written brief)

- Same `publish_quiz_question` mechanism.
- The meaningful change: it now receives the real last-N-turns transcript
  (see §4), so checkpoint questions can test what was *actually* just
  discussed, not just what the calling agent remembered to summarize.

### TextbookAgent (new — split out of TutorAgent's current textbook tools)

- Owns `search_textbook`, `show_textbook_figure`, and the retry-cap fix
  already shipped this session (two searches without placing a figure →
  stop and say so).
- Can either hand text back to VoiceAgent to say, or place a page/figure on
  the board directly — matching the "either give back the text... or stick
  the PDF page onto the board" requirement.
- Boundary with BoardAgent: specialists don't call each other — that would
  add a second orchestration layer this redesign is explicitly trying to
  avoid. When a request genuinely needs both ("explain this, and show the
  textbook figure"), VoiceAgent makes two delegate calls in the same
  message, matching the existing, already-proven "everything a turn needs
  goes in ONE message" convention (`TUTOR_INSTRUCTION`'s own documented
  latency win). VoiceAgent decides which specialist owns the *primary* ask;
  the second call is a supporting one.

## 4. Transcript capture — a real fix this redesign requires, and a bug fix as a side effect

For "last N turns" to mean anything, it has to be the *actual spoken
conversation*, not just delegated exchanges. Today, `brain._record()` only
fires on an `ask_tutor` call — most direct VoiceAgent exchanges are never
recorded (the root cause behind an earlier session's "only 2 turns
recorded" finding).

Proposed fix: hook into `main.py`'s `trace()`, which already sees every
`input_transcription`/`output_transcription` event for *every* exchange,
delegated or not. Pairing consecutive input/output transcriptions into clean
turns and appending them to the existing Redis-backed rolling buffer
(`short_term.append_turn`, already namespaced per session/student) gives
every specialist a genuine last-N-turns window, and separately fixes the
old under-recording bug as a byproduct — one mechanism, two payoffs.

Care needed: avoid double-recording an exchange that *also* goes through a
specialist delegation (the delegated request/reply would otherwise appear
twice — once from `trace()`, once from the specialist's own turn).

## 5. The lightweight brief — kept out of VoiceAgent's system instruction

Per the approved decision: VoiceAgent gets *some* student-profile awareness
to route well, but not the full profile TutorAgent preloads today, and
critically **not baked into the system instruction** (which is what gets
rebilled every single turn — the real cost this constraint exists to avoid).

Proposed shape: the existing one-time session-opening briefing
(`briefing.brief_voice_layer()` — topic, persona, weaknesses, cited grounding
chunks) already does this correctly today, injected as conversation content
once at session start, not as part of the fixed instruction. The change:
refresh it once after every specialist call resolves (an event-driven rule,
not a timer) — a specialist's own work is exactly the moment the student's
record is most likely to have changed, so that's the natural point to
re-inject an updated brief. Still injected content, still outside the
rebilled instruction.

## 6. No hardcoded subject — a standing rule for every specialist's instruction

Concrete instances of the problem to remove: `TUTOR_INSTRUCTION` names NCERT
chapters by number and title directly in the prompt; `sessions.py` defaults
every new session's opening heading to a fixed demo topic
(`"Maximum range — why 45° wins"`). Every specialist's instruction should
instead describe *how* to find and use subject material (`list_concepts`,
`search_grounding`, `search_textbook`) — never *which* subject. This is what
makes "grounded in the Shruti pipeline as the common substrate" actually
true rather than aspirational: the same agents work for any ingested
subject with no prompt edit.

## 7. Shared memory/grounding substrate — mostly already correct, one gap to close

`memory/tools.py`'s `search_grounding`/`list_concepts`/`get_dpm`/
`get_teaching_memory` are already shared, tool objects handed to whichever
agent needs them (TutorAgent and QuizAgent both use them today) — this part
of "one substrate, not five copies" is already true and just needs
extending: BoardAgent, TextbookAgent, and ArtifactAgent get the same shared
tool objects, not their own copies. No new store, no new schema.

## 8. What this deletes

- `app/agents/tutor_agent.py` and `app/agents/brain.py` (TutorAgent, the
  `ask_tutor` fire-and-forget-plus-queue mechanism, the 14s keep-alive nudge,
  the 70s hard timeout, the `_pending`/`_running` hand-rolled queue).
- `sessions.py`'s `nudges`/`context` queues and `main.py`'s `nudges()`/
  `injections()` background tasks.
- The dead `log_turn` function (already unused today).

## 9. Explicitly out of scope for this change

- No move to real ADK sub-agent nesting (§2 explains why it's a trap here).
- No change to how board patches reach the browser (already correct,
  untouched).
- No change to the durable memory tiers' schemas (DPMProfile, TeachingMemory,
  SessionLog, GroundingChunk) — this is an orchestration change, not a
  memory-schema change.
- The already-flagged, separately-tracked issues (bracket leak, VoiceAgent
  occasionally refusing directly instead of delegating) are not folded into
  this redesign — they get their own targeted fixes, before or after this
  lands, independently.

## 10. Open risks to verify during implementation, not design-blocking

- Exact behavior when a specialist's background task raises after
  `WHEN_IDLE` scheduling — needs a verified error-delivery path (today's
  `ask_tutor` has explicit rate-limit/failure nudges; the equivalent needs
  confirming under the new mechanism, likely via the same tool simply
  returning an error-shaped result, still `WHEN_IDLE`-delivered).
- Whether `response_scheduling` needs to be set on the `FunctionTool` at
  registration time in a way ADK's automatic tool-wrapping from a plain
  `async def` function supports directly, or requires wrapping in an
  explicit `FunctionTool(...)` instance — needs a small spike against the
  installed ADK version before the full implementation plan is written.
