# Where the stubs are

Everything in this build works, and some of it works against things that will
not survive contact with a second Cloud Run instance. This file is the complete
list, so wiring Firestore / Cloud SQL / Memory Store is a set of named edits
rather than an audit.

Ordered by what breaks first when you deploy.

---

## 1. The learner model is SQLite on local disk — **blocks deployment**

`app/memory/store.py:12`

```python
DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "memory.db"
```

Cloud Run containers are ephemeral and horizontally scaled, so this file
evaporates on restart and is not shared between instances. Everything the tutor
knows about a student lives here: `dpm_profile`, `teaching_memory`,
`session_log`, `grounding_chunk`.

**To swap:** `app/memory/store.py` is the only module that touches SQL — 9
functions, all taking `conn` as their first argument, all going through
`app/memory/tools.py`. Point `connect()` at Cloud SQL (Postgres, which
`sub_modules_examples/shruti` already speaks via asyncpg) and rewrite the 9
bodies. Nothing above `store.py` changes: the tool functions, the schemas, and
`session_close.py` all stay.

The four record types are pinned by Pydantic in `app/memory/schemas.py` and are
the contract — they mirror `memory_layer.md` §2 exactly. Do not reshape them to
suit a store.

> **Firestore note.** `dpm_profile` and `teaching_memory` are one document per
> student and fit Firestore naturally. `grounding_chunk` is queried by
> `concept_id` across many rows and is Shruti's output — that one wants Postgres
> or the knowledge graph itself, not a document store.

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

Four things per session: the board (`CanvasDoc`), the id minter, the screen
snapshot, and the outbox queue. A second instance sees none of it, and a restart
mid-lesson loses the page the student is looking at.

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

## 4. The in-session turn buffer is RAM

`app/memory/tools.py:log_turn` — `tool_context.state["turn_buffer"]`

Deliberate, per `memory_layer.md` §3: turns are held in memory during the
session and written once at close, so a chatty lesson is not 60 database writes.
But it means a crash loses the session's episodic record.

**Where Memory Store fits:** this is the natural short-term-cache candidate —
Redis keyed by session id, with the same append-only shape. Note ADK session
state is *already* a persistence layer once (2) is swapped, so measure before
adding a third store.

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

## 9. Generated artifacts live only in RAM

`app/agents/artifact_agent.py` — the validated IR goes into the canvas patch and
nowhere else. Reload the page and the artifact is gone with the board.

**To swap:** write the IR to GCS (or Firestore) keyed by `artifact_id`, which the
IR already carries. Personalisation is theme-at-render-time, so one stored
artifact serves every student — that is why `artifact_id` excludes the theme.

## 10. The frontend still has hardcoded content

`frontend/src/lib/data.ts` — everything except the session board:

| Export | Used by | Becomes |
|---|---|---|
| `classRecap`, `concepts`, `readiness*`, `intensities` | home, readiness, intensity screens | Shruti's overnight recap + the learner model |
| `projectile` | the fallback simulation kernel | only used when an artifact block arrives with no IR |
| `summary` | the summary screen | `session_close.py`'s output |
| `teacherClass`, `atRisk`, `teacherInsight` | all three teacher screens | aggregate query across students |
| `textbookPage` | the textbook drawer | real PDF, per-word boxes via PDF.js |
| `notebook`, `checkpoint`, `studentFinding` | **nothing any more** — safe to delete | — |

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
