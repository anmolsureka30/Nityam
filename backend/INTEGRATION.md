# Where the stubs are

Everything in this build works, and some of it works against things that will
not survive contact with a second Cloud Run instance. This file is the complete
list, so wiring Firestore / Cloud SQL / Memory Store is a set of named edits
rather than an audit.

Ordered by what breaks first when you deploy.

---

## 1. The learner model — now a switch, defaulting to SQLite

`app/memory/store.py` picks a backend from `NITYAM_STORE`:

| value | module | needs |
|---|---|---|
| `sqlite` *(default)* | `store_sqlite.py` — a file at `backend/data/memory.db` | nothing |
| `firestore` | `store_firestore.py` — ported from `sub_modules_examples/tutor` | a GCP project + application-default credentials |

Both expose the same functions; 11 of 13 signatures are identical past the
handle, and the two that differ (`connect`, `put_grounding_chunk`) differ only
by optional arguments no call site passes. So the seed script, the ADK tool
functions and `session_close.py` run unchanged on either, and `/health` reports
which one is live.

**To go live:**

```bash
gcloud auth application-default login
export NITYAM_STORE=firestore
export GOOGLE_CLOUD_PROJECT=nityam-506707
export FIRESTORE_DATABASE=smriti          # a named database, not (default)
.venv/bin/python -m scripts.seed_demo_data
```

**Not yet verified against a real Firestore** — this machine has no GCP
credentials, so what is proven is that the module imports, the switch selects
it, and the signatures line up. The first run against a real project is the
thing still to do.

Firestore also brings `search_grounding_semantic`, a vector search the SQLite
path does not have; `store.search_grounding_semantic` is `None` on sqlite so
callers degrade to concept-id search rather than raising. Note the open caveat
carried over from the port: Shruti's embedder emits 3072-dim vectors and
Firestore's vector index caps at 2048, so chunks are searchable by concept id
today and semantically only once a smaller companion embedding exists.

`short_term.py` (Redis / Memorystore) came across with it and is now live: it
holds the turn buffer described in §4 below, written from
`app/agents/brain.py:_record` and `app/memory/tools.py:log_artifact_evidence`,
and read back by `app/main.py:_flush_session_memory` at session close.

## 2. ADK sessions are in memory

`app/main.py` — `session_service = InMemorySessionService()`

**To swap:** one constructor. `DatabaseSessionService(db_url=...)` for Cloud SQL,
or `VertexAiSessionService(...)` for managed Sessions. `sub_modules_examples/tutor/app/app_utils/services.py`
already has the env-var-driven version of this (`SESSION_SERVICE_URI`,
`GOOGLE_CLOUD_AGENT_ENGINE_ID`) — lift that file in when you deploy and delete
the line here.

Note the ADK gotcha it documents: state mutated directly is **not** persisted;
persistence rides on `append_event`.

## 3. The board lives in a process-local dict

`app/sessions.py` — `_SESSIONS: dict[str, SessionState] = {}`

Per session: the board (`CanvasDoc`), the id minter, the screen snapshot, and
three queues — `outbox` (patches for the browser), `nudges` (things she must
say) and `context` (things she must know). A second instance sees none of it,
and a restart mid-lesson loses the page the student is looking at.

**To swap:** `publish()` is the single write path — it applies the patch to the
board *and* enqueues it. That is deliberate: split them and `read_screen` can
report a board the browser has not rendered. So the Firestore version is one
function:

```python
def publish(session_id, patch):
    state = get(session_id)
    _apply(state, patch)                      # unchanged
    doc_ref(session_id).set(state.board.model_dump())   # replaces the queue
```

Then delete `outbound()` from `app/main.py` and have the browser subscribe with
`onSnapshot` instead of listening for `canvas_patch` frames. The frontend change
is `useLiveSession.ts`'s one `canvas_patch` branch — the reducer, the patch
types and every component stay exactly as they are.

**One thing not to break while doing it.** `publish()` is also what triggers the
context injection that keeps the voice layer able to answer without delegating
(`canvas/tools.py:_brief_voice`). That injection is a *live-session* concern, not
a persistence one, so it must survive the move to Firestore — it does not belong
inside the document write. Keep `_brief_voice` where it is, at the tool call
sites, and Firestore replaces only the queue.

## 3b. The voice layer's context channel is RAM, and should stay that way

`app/sessions.py` — `state.context: asyncio.Queue[str]`, `sessions.inject()`

The counterpart to `nudges`: a nudge makes her speak, an injection makes her
*know*. The session's grounding pack (`app/briefing.py`) and every board change
go down it as `partial=True` content, which reaches the Live model's context
without completing a turn. It is what lets "which formula was it?" cost one
second instead of nine.

**This one is deliberately NOT a Firestore seam.** It is per-live-session,
per-process, and meaningless outside the lifetime of one WebSocket — the Live
API session it feeds does not outlive the connection either. If the process dies
mid-lesson the injections are lost, and that is correct: the replacement
connection rebuilds the briefing from `briefing.brief_voice_layer()` and the
board it reloads. Do not persist it.

Verified against the real Live API: partial content injected *while a function
call is outstanding* is accepted, and the text provably reaches the model's
context.

## 4. The in-session turn buffer — now written through to Memorystore

`app/memory/short_term.py` (Redis), alongside `tool_context.state["turn_buffer"]`

The RAM buffer is still there and still deliberate, per `memory_layer.md` §3:
turns accumulate during the session and the learner model is written once at
close, so a chatty lesson is not 60 database writes. What changed is that each
turn *additionally* writes through to Redis as it happens, so a crash no longer
takes the session's episodic record with it.

Two call sites write:

* `app/agents/brain.py:_record` — both halves of every exchange, appended as
  they are recorded.
* `app/memory/tools.py:log_artifact_evidence` — artifact interaction events.

Both wrap the Redis call so an outage degrades to the old RAM-only behaviour
instead of breaking a live turn. `app/main.py:_flush_session_memory` reads the
buffer back with `get_turn_buffer` at session close — that read is what
`session_close.py` actually reflects on — and then deletes the keys.

Keys are `session:{student_id}:{session_id}:turns` and
`…:artifact_events`, with a 6h safety TTL in case a close is never reached. The
`student_id` in the key is load-bearing, not decoration: `session_id` is chosen
by the client and nothing validates it against the connecting user, so without
the namespace a collision would let one student's buffered turns be reflected
into another student's memory.

**One thing this doc used to say that was never true.** `app/memory/tools.py:log_turn`
is dead code — TutorAgent's tool list has never included it, and turn logging
happens in `brain.py:_record` instead, precisely to avoid spending a model round
trip per turn on bookkeeping. It is still in the file; nothing calls it.

`REDIS_HOST` / `REDIS_PORT` configure it, defaulting to `localhost:6379`
(`app/config.py`). See `.env.example`.

## 5. `student_id` is hardcoded

`app/agents/tutor_agent.py:_init_state` — `setdefault("student_id", "demo_student")`,
and `frontend/src/features/session/SessionScreen.tsx` — `const USER_ID = "demo_student"`.

**To swap:** the WebSocket path is already `/ws/{user_id}/{session_id}`, and
`main.py` seeds both into ADK session state at creation, so the plumbing exists.
Replace the constant with the Firebase Auth uid and verify the ID token in
`ws_endpoint` before `accept()`.

## 6. There is no auth on the WebSocket

`app/main.py:ws_endpoint` accepts any connection and will happily read and write
any `session_id` you name. Fine on localhost, not fine anywhere else.

## 7. Tonight's topic is three env vars

`app/sessions.py` — `OPENING_EYEBROW`, `OPENING_HEADING`, `OPENING_CONCEPT`.

The board opens with one heading built from these. In the real product they come
from the class recap Shruti produces overnight: which lesson happened, which
concept the student is weakest on, and the question the teacher asked and never
answered.

## 8. The demo student's history is hand-written

`scripts/seed_demo_data.py`

Two parts, and they are not equally fake:

* **The grounding chunks are real.** They are parsed out of
  `sub_modules_examples/shruti/vault/wiki/*.md`, so every citation
  (`shruti:d_jnekwca6i_4c5411d0 @3:40`) points at an actual lecture timestamp.
  This part is production-shaped already; it just runs offline instead of on
  ingest.
* **The prior session is invented** — one `session_log` with 4 turns, plus the
  weaknesses and the open doubt that cite it. It exists so `get_dpm` returns
  something meaningful on turn one. In production `session_close.py` writes all
  of this.

  The citations do resolve to turns that exist in the seeded log. That was
  deliberate: `memory_layer.md`'s one invariant is that every claim in a
  student's memory resolves back to a real moment, and seeding dangling
  references would have quietly broken the property the design exists to
  protect.

## 9. Generated artifacts — now written to GCS

`app/artifacts_gcs.py`, called from `app/agents/artifact_agent.py:_build`

The validated IR still goes into the canvas patch for the live board, and now
also goes to Cloud Storage as `artifacts/{artifact_id}.json` — the copy that
survives a reload or a restart. `artifact_id` is the key because the IR already
carries it, and because personalisation is theme-at-render-time, so one stored
artifact serves every student; that is why `artifact_id` excludes the theme.

The write is wrapped and non-fatal: durability is a bonus, and a GCS failure
must not cost the student the artifact that is already on their page. It runs
through `asyncio.to_thread` — `google-cloud-storage` is a blocking client, and
`_build` is on the event loop that carries every concurrent student's audio.

`GCS_BUCKET` names the bucket and must already exist. `read_artifact_from_gcs`
and `delete_artifact_from_gcs` exist for the reload path and are exercised by
`tests/test_gcs_artifacts.py`, but **nothing in the app reads the stored copy
back yet** — the frontend still gets its IR from the board. That is the piece
still to do.

## 10. The frontend still has hardcoded content

`frontend/src/lib/data.ts` — everything except the session board:

| Export | Used by | Becomes |
|---|---|---|
| `classRecap`, `concepts`, `readiness*`, `intensities` | home, readiness, intensity screens | Shruti's overnight recap + the learner model |
| `projectile` | the fallback simulation kernel | only used when an artifact block arrives with no IR |
| `summary` | the summary screen | `session_close.py`'s output |
| `teacherClass`, `atRisk`, `teacherInsight` | all three teacher screens | aggregate query across students |
| `notebook`, `checkpoint`, `studentFinding`, `textbookPage` | **nothing any more** — safe to delete | — |

`PLAN` in `SessionScreen.tsx` is also hardcoded; the agent should emit it from
the chosen intensity.

## 11. Mastery moves locally and is thrown away

`SessionScreen.tsx` — `setMastery((m) => m + 8)` on a correct checkpoint.

Cosmetic only. The real number moves at session close, through
`app/memory/ops.py`'s validated operations, which is after this screen unmounts.
The summary screen reads `data.ts`, not the store.

## 12. Mock mode's teaching is a keyword script

`app/mock_board.py`

Not a stub to replace — keep it. It publishes through the same
`sessions.publish` → outbox → `outbound` path the real tools use, so
`frontend/tests/ui.mjs` exercises the real protocol and the real reducer with no
credentials and no spend. Only the *choice* of what to write is scripted.

---

## Not stubbed, worth knowing

* **`gemini-live-2.5-flash` is the only Live model provisioned for this project.**
  `gemini-3.1-flash-live-preview` is listed by `models.list()` and named in the
  architecture doc, but a real Live handshake returns `1008 Publisher model not
  found` — as does every other 2.0/2.5/3.x live id. See `app/config.py`.
  Reasoning runs on `gemini-3.7-flash`, which is what satisfies the hackathon's
  "Gemini 3.5 or newer" requirement.
* **The OAuth access token expires roughly hourly.** A sudden `401
  UNAUTHENTICATED` mid-lesson is that, not a code change. `python -m app.auth`
  says so.
* **ADK runs instructions through session-state template injection**, so a
  literal `{g}` in an instruction raises `KeyError: 'g'` before the model is
  called. Keep braces out of instruction text.
* **`mode='single_turn'` sub-agents do not work under `run_live`** in
  google-adk 2.7.1. `run_async` initialises `InvocationContext._event_queue`
  and `run_live` does not, so the nested node runner raises on its first event.
  This is why `app/agents/brain.py` exists, and why `architecture.md` §2's
  topology needs amending — it was verified by reading the ADK source, which is
  correct about the mechanism and silent about the queue.
* **A brain turn is genuinely slow** — grounding, two or three board writes,
  sometimes a delegated quiz. `NITYAM_BRAIN_TIMEOUT` (default 70s) bounds it,
  and VoiceAgent is instructed to speak before delegating so the student is not
  listening to silence.
