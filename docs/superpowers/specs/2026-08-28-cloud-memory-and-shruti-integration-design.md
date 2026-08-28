# Cloud memory migration + Shruti live integration — Design

Status: approved in chat via brainstorming Q&A (2026-08-28). Ready for an implementation plan.

## 1. Problem

Two things are true right now, verified against the running code this session:

1. **SMRITI's storage architecture is already researched and half-built**, but not finished
   and not fully connected. `project_documentation/memory_nityam_architecture/
   google_cloud_storage_integration.md` (v1.1, 2026-08-27) and `memory_layer.md` (v2.0) already
   decided: Firestore for episodic + long-term tiers, Cloud Storage for artifacts, Memorystore
   as a write-through mirror for the workflow tier — declining Vertex AI Memory Bank, Agent
   Search, and Vector Search 2.0, because none of them can carry a `session_id#turn` evidence
   citation through their consolidation/retrieval path, which every SMRITI record depends on.
   Firestore is live and running (`NITYAM_STORE=firestore`). GCS and the Memorystore
   write-through are not wired into the running app. And — found independently this session,
   not previously verified — **`session_close.close_session()`, the function that actually
   writes `session_log` and updates `dpm_profile`/`teaching_memory`, is never called anywhere
   in the live WebSocket flow.** `main.py`'s `finally` block calls a different, similarly-named
   `logs.close_session()` that only closes the per-session debug log file. Today, no real
   session's memory reaches Firestore at all — only the one hand-seeded demo record exists.

2. **Shruti already does everything described as "upload a video."** `shruti ingest --url
   <youtube-url>` downloads, runs the full extraction pipeline, and writes citation-backed
   `vault/wiki/<concept>.md` pages with real 3072-dim embeddings. Shruti deliberately keeps its
   own local Postgres for structure/provenance (its own 2026-08-26 design decision — out of
   scope here). But nothing connects that output to Nityam's Firestore live — today it's a
   one-time hand-run `seed_demo_data.py` script parsing a static snapshot.

This spec covers: finishing the storage migration, fixing the `close_session` gap, building the
live Shruti → Nityam bridge, and — added during this brainstorm — restructuring how grounding
content reaches the tutor's context (a per-lecture summary, always injected, and task-scoped
retrieval instead of a multi-concept blast).

**Explicitly not covered** (raised and deliberately deferred during this brainstorm):
- Shruti's own storage (Postgres, its vault's graph/embedding index) — stays exactly as
  designed in Shruti's own 2026-08-26 doc.
- The frontend's separate `classRecap`/readiness/teacher-screens stub (`INTEGRATION.md` #10) —
  a materially larger, separate subsystem. This spec only adds a backend `current_topic`
  pointer that `sessions.py` reads instead of static env vars.
- `BaseSessionService` internals verification, for a possible future custom session service —
  not needed for anything in this spec (`InMemorySessionService` stays, per the existing doc's
  own recommendation).
- Context Window Management (periodic mid-session summarization) — noted as a future concern
  in the existing doc, not triggered by anything this spec adds.

---

## 2. Deployment target

**Cloud Run.** Decided during this brainstorm, not assumed: Nityam's backend is a custom
FastAPI app (a raw browser-facing WebSocket at `/ws/{user_id}/{session_id}`, a `/health`
endpoint, and it serves the built frontend as static files from the same process) — not a bare
ADK agent exposed through `query()`/`stream_query()`. That shape matches Cloud Run (the
documented `adk api_server` → Docker container → Cloud Run path) rather than Vertex AI Agent
Engine, whose managed API-gateway model is built around exposing an agent, not hosting an
arbitrary app. This also settles Memorystore's networking: Direct VPC egress, same region/VPC
as the Memorystore instance — the path the existing doc already researched.

---

## 3. Storage — finishing what's already decided

No new research here; implementing `google_cloud_storage_integration.md` §3-§5 as written, plus
one fix it flagged as unverified.

### 3.1 Cloud Storage — `GcsArtifactService`

`app/main.py`'s `Runner(...)` gains `artifact_service=GcsArtifactService(project=..., bucket_name="nityam-artifacts")`.
`ArtifactAgent`'s tool that currently returns generated HTML/diagram content directly saves it
via `tool_context.save_artifact(...)` instead (or in addition, during transition — see §9).
Confirmed against current ADK docs this session: the API is exactly this shape,
`{app_name}/{user_id}/{session_id}/{filename}/{version}` path structure, ADC-authenticated.

### 3.2 Memorystore — the write-through mirror

`app/memory/short_term.py` already exists matching `google_cloud_storage_integration.md` §5.3.
`app/memory/tools.py`'s `log_turn`/`log_artifact_evidence` gain the write-through call the
existing doc already specifies (both become `async`, which ADK's tool dispatch already
supports). `session_service` stays `InMemorySessionService()` — no custom session service, per
the existing doc's own recommendation (§5.2, option (b)).

### 3.3 The `close_session` fix

`app/main.py`'s `ws_endpoint` `finally` block currently only calls `logs.close_session(session_id)`
(debug log bookkeeping). It needs to **also** call `session_close.close_session(...)` — sourcing
`buffer` from `tool_context.state["turn_buffer"]` if reachable from that scope, else from
`short_term.get_turn_buffer(session_id)` (the Memorystore mirror, per the existing doc's own
open item 4) — passing the real `genai.Client`, `session_id`, `student_id`, and session start
time already available in `SessionState`. This is the single highest-value fix in this spec:
every other piece of the memory layer is inert without it.

### 3.4 Embedding dimension

Decided during this brainstorm: **Nityam computes it**, not Shruti. The new sync bridge (§4)
calls Gemini's embedder with `output_dimensionality=1536` when it writes each `grounding_chunk`.
Shruti's own 3072-dim index and pipeline are untouched — zero changes to Shruti's codebase for
this.

---

## 4. Shruti → Nityam sync bridge

**Mechanism: HTTP webhook, Cloud Run service-to-service auth.** Decided over a subprocess call
(breaks once Shruti and Nityam aren't co-located) and a GCS+Eventarc event-driven pipeline (real
new infrastructure — a bucket, a trigger, a separate function — for what's fundamentally a
one-call handoff, and it would touch Shruti's storage layer).

- **New endpoint**: `POST /admin/sync-grounding` on the Nityam backend. Authenticated via Cloud
  Run's built-in service-to-service IAM (an ID token from Shruti's service account, verified by
  Nityam) — no bespoke secret to manage, works identically whether both run locally or both run
  in Cloud Run.
- **Caller**: `shruti/cli.py`'s `ingest` command, after `run_ingest` completes and wiki pages are
  written, POSTs the list of touched concept slugs (and the recording id, for §5) to this
  endpoint.
- **What the endpoint does**, per touched concept:
  1. Reads the concept's current `vault/wiki/<slug>.md` content (or receives it in the request
     body — implementation-plan detail).
  2. Embeds the text at `output_dimensionality=1536` (§3.4).
  3. Upserts into Firestore `grounding_chunks` (same shape `store_firestore.py` already writes).
  4. Writes/updates a `current_topic` document (concept id, heading, eyebrow) that
     `app/sessions.py`'s `_new_board()` reads instead of the static `NITYAM_TOPIC_*` env vars —
     so uploading a video changes what the next session actually opens on.
  5. Triggers the summary step (§5) for the recording, if not already done for this recording.

---

## 5. Per-lecture summary — new artifact, always injected

**Problem this solves**: today there is no summary of a lecture anywhere. `vault/notes/<id>.md`
is a deterministic, un-summarized transcript-with-board-annotations (no LLM call). `briefing.py`
conditionally retrieves up to 6 raw grounding chunks, which may span multiple concepts and never
guarantees full-lecture coverage (a practiced question mentioned once, in passing, could easily
fall outside the 6-chunk cap).

- **New step, in the sync bridge (not in Shruti)**: when `/admin/sync-grounding` receives a
  recording it hasn't summarized yet, it reads that recording's `vault/notes/<recording_id>.md`
  (the full beat-by-beat transcript) and makes one Gemini call with a dedicated summarization
  prompt — this is real prompt-engineering work, not a generic "summarize this" call. The prompt
  needs to explicitly ask for: every concept taught (not just the one the tutor session is
  about — the whole lecture), any question the teacher posed to the class or worked through,
  and any misconception the teacher addressed — because those are exactly the things a
  6-chunk cap could silently drop. Structured output (not free prose) so it composes cleanly
  into a context injection: an ordered list of {topic, explanation, practiced_question?} entries
  plus a short overall summary line.
- **Storage**: a new Firestore collection, `lecture_summaries`, one document per
  `recording_id`/`source_ref`.
- **`briefing.py` change**: `brief_voice_layer` currently assembles `chunks` (up to 6, via
  `search_grounding`) plus the per-student `_brief`. It gains a third, **unconditional** piece:
  the lecture summary for whichever recording(s) back tonight's topic, always present in the
  injection regardless of the 6-chunk cap or concept-matching. The existing chunk retrieval
  narrows further, per §6, to the current task only.

---

## 6. Task-scoped retrieval — the state machine

**What already exists and is being reused, not replaced**: `TeachingMemory.covered[concept_id]
.status` (`in_progress`/`covered`) is already exactly a per-concept task status — it's just not
what drives context injection today, and it's only updated once, at `close_session`. (`syllabus`
itself — a plain list of concept_ids — isn't read by anything today, `resolve_concepts()`
included, and isn't what's driving the task queue either; noting this so the two aren't
conflated.)

**Task grain**: one task per concept — the same grain the wiki already writes at. **Task queue
source**: `briefing.py`'s existing `resolve_concepts(plan, student_id)` — no new selection
logic. It already orders a student's weak concepts and open doubts first, then topic-matched
concepts; that ordering *becomes* the task queue, independent of the unused `syllabus` field.

**The pointer is ephemeral, workflow-tier state** — in `SessionState` (RAM) with the same
Memorystore mirror as the turn buffer, not a Firestore write. This is deliberate: it preserves
`memory_layer.md`'s existing rule that long-term memory is never written mid-session ("you don't
know what a turn meant until you see what followed it, and a file write inside a turn is latency
you don't need to pay"). The pointer answers "which task are we on right now, in this session,"
which is a workflow-tier question by definition — the persisted, cross-session `covered` status
still only updates at `close_session`, via the same Reflect call that already proposes
`update_coverage` operations, now additionally informed by which tasks this session's pointer
actually advanced through.

**`advance_task()`** — a new tool, callable by TutorAgent when it judges the current concept
sufficiently covered:
1. Advances the ephemeral pointer to the next entry in the task queue.
2. **Directly fetches** the new current concept's `grounding_chunk`(s) from Firestore and pushes
   them via `sessions.inject()` — server-side, inside `advance_task`'s own implementation, in the
   same call. **Not** a `search_grounding` tool call the model has to separately invoke — the
   whole point, per this session's discussion, is that a live retrieval round trip is measured,
   real latency here (this codebase's own logs show `ask_tutor` delegations running 13-70+
   seconds; `sessions.inject()` exists specifically to avoid paying that cost for
   already-known-relevant content — the opening briefing and board-update pushes already work
   this way).

`search_grounding`/`search_grounding_semantic` stay available as tools for genuinely off-syllabus
tangents — a curious question outside tonight's planned concepts — but the designed
task-progression path never calls them. When the pointer reaches the end of the queue,
`advance_task()` is simply not called again; TutorAgent keeps teaching from whatever's already
in context.

---

## 7. Data flow, end to end

```
shruti ingest --url <youtube-url>
  → pipeline runs (PULSE/GLYPH/ECHO/ATLAS/WEAVE/...) — unchanged
  → vault/wiki/<concept>.md written/appended — unchanged
  → vault/notes/<recording_id>.md written — unchanged
  → [NEW] POST /admin/sync-grounding {recording_id, touched_concepts}
       (Cloud Run service-to-service auth)

Nityam /admin/sync-grounding:
  → per touched concept: embed @1536 → upsert grounding_chunks (Firestore)
  → write/update current_topic doc (Firestore)
  → if recording not yet summarized: read vault/notes/<id>.md → Gemini summarization call
       → write lecture_summaries/<recording_id> (Firestore)

Next tutoring session:
  → sessions.py._new_board() reads current_topic instead of NITYAM_TOPIC_* env vars
  → briefing.brief_voice_layer():
       - resolve_concepts() → task queue (ephemeral pointer starts at 0)
       - lecture_summaries for the topic's recording(s) → ALWAYS injected
       - grounding_chunks for task_queue[0] only → injected
  → mid-session, TutorAgent calls advance_task() when a concept is done:
       - pointer → task_queue[pointer+1]
       - grounding_chunks for the new current task → directly injected (no tool round trip)
  → session ends → ws_endpoint's finally block calls session_close.close_session()
       - session_log written (Firestore)
       - Reflect call proposes update_coverage/set_mastery/etc. against this session's
         actual turns AND which tasks the pointer advanced through
       - dpm_profile / teaching_memory updated (Firestore) — the ONLY point either is written
```

---

## 8. Schema additions

Two new Firestore collections, both additive — no existing schema changes:

- **`current_topic`** — singleton-per-deployment or keyed by some scope (implementation-plan
  detail: likely one document, since Nityam currently serves one demo cohort; revisit if
  multi-class support is ever needed). Fields: `concept_id`, `heading`, `eyebrow`,
  `recording_id`, `updated_at`.
- **`lecture_summaries`** — one document per `recording_id`. Fields: `recording_id`,
  `source_ref`, `summary` (short overall line), `entries` (ordered list of
  `{concept_id?, topic, explanation, practiced_question?}`), `created_at`.

No changes to `grounding_chunk`, `dpm_profile`, `teaching_memory`, or `session_log`'s existing
schemas (`backend/app/memory/schemas.py`) — `TeachingMemory.covered` already carries the
persisted half of what §6 needs; the task queue's ordering itself is computed, not stored.

---

## 9. Error handling

- **`/admin/sync-grounding` failures** (embedding call fails, Firestore write fails): Shruti's
  `ingest` CLI logs the failure and exits non-zero on that step, but does not lose the
  already-written `vault/wiki/*.md`/`notes/*.md` files — they remain the source of truth and a
  retry (of just the sync call, not the whole ingest) is always possible. Mirrors Shruti's own
  existing idempotent-per-citation design.
- **Missing `current_topic`**: `sessions.py` falls back to the existing static
  `NITYAM_TOPIC_*` env vars if the document doesn't exist — the fallback that already works
  today, not a new failure mode.
- **`advance_task()` with an empty/exhausted queue**: a no-op that returns a small
  "already teaching the last planned concept" result rather than raising — consistent with
  `PatchRejected`'s existing pattern of tool errors the model can react to rather than a hard
  crash.
- **`close_session` failures** (the Reflect call fails, or Firestore write fails): logged, not
  raised into the WebSocket teardown path — a memory-write failure must never prevent the
  connection from closing cleanly. Matches `apply_operations`'s existing "drop a malformed op,
  never crash the whole run" philosophy.

---

## 10. Testing

Given this session's instruction not to spend time testing mid-design — this section describes
what the implementation plan should verify, not work to do now:

- `test_ws_auth.py`-style: a real (mock-mode) server run exercising `close_session` actually
  firing on disconnect, and `dpm_profile`/`teaching_memory`/`session_log` actually present in
  Firestore afterward (today: nothing to find, by design of the bug being fixed).
- A unit test for `advance_task()`'s pointer arithmetic and its direct-injection call, with a
  fake `sessions.inject` capturing what was pushed — no live model needed.
- A unit test for the lecture-summarization prompt against a fixed `notes.md` fixture, checking
  the structured-output schema round-trips and that a known practiced-question in the fixture
  survives into the summary (regression guard for the exact failure mode §5 exists to prevent).
- `/admin/sync-grounding`'s auth: a real test hitting it with a valid Cloud Run ID token, an
  invalid one, and none — mirroring `test_ws_auth.py`'s existing three-case pattern.

---

## 11. Open items for the implementation plan

1. Exact request/response shape for `/admin/sync-grounding` (full wiki text in the body vs. the
   endpoint reading `vault/wiki/*.md` itself — only viable if Shruti and Nityam share a
   filesystem, which won't hold once deployed separately; body-based is likely correct but not
   settled here).
2. `current_topic`'s exact keying if/when multi-cohort support is ever needed (noted, not
   blocking — today's single-document assumption matches today's single-demo-cohort reality).
3. Whether `ArtifactAgent`'s existing in-RAM artifact path is fully replaced by
   `GcsArtifactService` or runs alongside during a transition — an implementation sequencing
   question, not a design fork.
4. The lecture-summarization prompt's exact structured-output schema (field names/types) —
   design intent is fixed (§5), exact schema is implementation detail.
