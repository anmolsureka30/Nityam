# backend

The tutor: a Gemini Live voice loop, four reasoning specialists, and a shared
board the tutor writes on and the student points at.

```
browser ──PCM16@16k──┐
                     ├─► /ws ─► LiveRequestQueue ─► run_live ─► Gemini Live
ContextPacket ───────┘                                 │
                                                       ├─ audio 24k ──────────► speaker
                                                       ├─ outputTranscription ► caption + avatar mouth
                                                       └─ tool calls ─────────► log
board outbox ──────────────────────────────────────────────────────────────────► canvas patches
```

Five concurrent tasks per connection (`read_client`, `downstream`, `outbound`,
`heartbeat`, `_transcript_writer` — see `app/main.py`'s own docstring). The
board patch path is why the tutor can write on the page at all: board tools
run several frames deep inside their own specialist's `Runner`, with no
reference to the socket, so they publish to a per-session queue and
`outbound()` delivers it.

## Prerequisites

**Redis** (the working-memory tier, `app/memory/short_term.py`) — either:

```bash
docker compose up -d redis     # recommended — see docker-compose.yml
# or, without Docker:
redis-server --daemonize yes --port 6379
```

**A Firebase project** — every real connection verifies a Firebase ID token
(`app/user_auth.py`), and there is no dev bypass; `NITYAM_AUTH=mock` removes
the *Gemini* credential requirement, not this one. Set
`GOOGLE_CLOUD_PROJECT` in `.env` to the same project id the frontend's
`VITE_FIREBASE_PROJECT_ID` names, or every token is refused on its `aud`
check and the student is told their sign-in expired.

This needs **no credentials at all**. A Firebase ID token is an RS256 JWT
verified against Google's *public* certificates — see this module's own
header for why the Admin SDK (and the ADC dependency it dragged in) was
deliberately removed. An earlier revision of this file said ADC was required
here; it isn't, and hasn't been since that change.

**Application Default Credentials (ADC)** — needed for exactly one thing:
Firestore (`app/memory/store_firestore.py`), and only when
`NITYAM_STORE=firestore`. ADC is a machine-level credential, not a `.env`
value, so copying `.env` to a different machine with every value filled in
will still not make Firestore work there. Pick one:

- **You have access to the GCP project** (the one named in
  `GOOGLE_CLOUD_PROJECT`):
  ```bash
  gcloud auth application-default login
  ```
  One-time, per machine.

- **You don't** (e.g. a friend trying this out without project access): ask
  whoever owns the project for a service account key covering Firestore,
  Firebase Auth verification, and the GCS bucket, then:
  ```bash
  export GOOGLE_APPLICATION_CREDENTIALS=/path/to/the-key.json
  ```
  Put that line in `.env` (or a shell profile) so it's set every time. Treat
  the key file like a password — it grants real access, so it belongs
  nowhere near a commit.

`NITYAM_STORE=sqlite` is the default, and it skips Firestore's credential
requirement entirely — memory becomes a local file (`backend/data/memory.db`),
no project access needed. Sign-in is unaffected either way: it isn't gated by
`NITYAM_STORE` and it doesn't use ADC.

## Run it

```bash
cp .env.example .env        # then fill in credentials, or set NITYAM_AUTH=mock
./run.sh                    # backend + frontend + Observatory + landing page
./run.sh --no-observatory   # skip the Observatory (and its uv requirement)
./run.sh --no-landing       # skip the Next.js landing page
./run.sh --api-only         # backend alone, nothing browser-facing
```

`frontend/.env` is a separate, required step — six Firebase web-config values,
gitignored, without which the app renders a setup notice instead of the tutor.
See the repo-root README's spin-up section for the full sequence.

`run.sh` builds the virtualenv, checks credentials, seeds the demo student on
first run, and refuses to start if the port is busy — a silently-busy port used
to look like a tutor that just never spoke.

Mock mode needs no credentials, no network and no spend. It is what the tests
run against.

Defaults: API `8210`, web `5173`, landing `3001`, Observatory API `8100` and
Observatory web `3000`. API and web move together via `NITYAM_API_PORT` /
`NITYAM_WEB_PORT`; `frontend/vite.config.ts` reads the same vars. The
Observatory's web port must stay `3000` — its backend hardcodes CORS to
`5173` and `3000`, and 5173 is already taken here. The `adk` sub-module also
defaults to 8100, so run one or the other, or move ours with
`NITYAM_OBSERVATORY_PORT`.

## Check it works

```bash
.venv/bin/python -m app.auth              # which auth modes work, INCLUDING a real Live handshake
.venv/bin/python -m tests.test_canvas     # the board, no model in the loop
.venv/bin/python -m tests.test_wire       # the protocol, real server, mock mode
.venv/bin/python -m tests.test_live       # real Gemini — costs money, skips on mock
.venv/bin/python -m scripts.drive         # a whole lesson in text mode, prints the board it wrote
```

`scripts/drive.py` is the one to reach for when the tutor stops writing on the
board. It runs BoardAgent directly through `run_async`, prints every tool call,
and then prints the board that came out with a pass/fail on the three things
that have to be true: grounded, wrote to the board, patches queued.

## The agents

```
VoiceAgent            gemini-live-2.5-flash   ears and mouth, tiny instruction
├─ BoardAgent         gemini-3.7-flash        what belongs on the board, and writes it
├─ ArtifactAgent      gemini-3.7-flash        spec -> IR -> validate -> mounted
├─ QuizAgent          gemini-3.7-flash        writes checkpoint questions
└─ TextbookAgent      gemini-3.7-flash        finds and places real NCERT pages/figures
```

VoiceAgent is a **router**. It answers directly from its briefing whatever it
can, and delegates everything else to exactly one of four specialists through
`ask_board` / `ask_artifact` / `ask_quiz` / `ask_textbook`. **Only VoiceAgent
addresses the student**; a specialist takes a request, puts something on screen,
and reports back a line of prose for VoiceAgent to say in its own voice.

**The specialists are function tools, not `sub_agents`.** `architecture.md` §2
specifies `sub_agents=[... mode='single_turn']`, and that cannot work on the
streaming path: a `single_turn` child is executed by
`workflow/_node_runner.py`, which enqueues onto
`InvocationContext._event_queue` — a queue `run_async` creates (`runners.py:595`,
`:752`) and `run_live` never does. On the live path it raises on the child's
first event, the tool returns an error string, and the tutor apologises to the
student about a technical hiccup.

So each specialist runs in its own Runner through `run_async`, bootstrapped by
`app/agents/specialist_runner.py:SpecialistRunner` — one helper shared by all
four rather than the same bootstrap hand-rolled per agent. That also delivers
what §2 wanted from the arrangement (the full `before_model_callback`
lifecycle, which never fires under `run_live`) more directly than the sub-agent
mechanism did.

**Each `ask_*` tool is tagged `response_scheduling=WHEN_IDLE`.** The Gemini Live
API itself then holds the tool's result and delivers it at the next natural
pause, instead of cutting VoiceAgent off mid-sentence. That platform mechanism
replaced a hand-rolled nudge/inject queue (`sessions.nudges`/`state.context`),
which is now gone. Two consequences worth knowing:

* Each `ask_*` is an **async generator**, not a coroutine — `specialist_runner.delegate()`
  is what every one of them wraps and yields from. ADK routes an async-generator
  tool through its streaming path, where every `yield` becomes its own
  `send_tool_response` on the same call id: an opening placeholder the moment
  the call lands, a "still working" chunk on a cadence while the specialist
  runs, and the real result once it finishes. VoiceAgent never has to be handed
  a holding line by the caller — `delegate()` generates one from the
  specialist's own label.
* ADK yields no `function_response` event into `run_live`'s stream for a
  WHEN_IDLE tool, so nothing can be triggered off one. Anything that must happen
  when a delegation finishes belongs at the tool function's own call site — see
  `specialist_runner.refresh_brief`, which re-briefs the voice layer there.

Why two model layers rather than one: the Live API bills every context token,
including the system instruction, on every turn — so memory can never live in
the voice agent's prompt (`architecture.md` §3). The cost is a pause on
substantive turns, which is why VoiceAgent must say something before it
delegates.

Adding a specialist: write `build_x_agent()`, give it a module-level
`SpecialistRunner`, and expose one `async def ask_x(request: str, tool_context:
ToolContext)` async generator that `async for`-yields from
`specialist_runner.delegate(...)`, passing your label, runner, request,
transcript length, and the default/error summaries to speak. Register it in
`voice_agent.py` wrapped in `_when_idle(...)`. The tool's docstring is the
actual interface — it is what VoiceAgent routes on. Build agents in a
factory, never at module level: an agent already attached to one parent
raises `"agent already has a parent"`.

## The board

`app/canvas/` — the models, the tools, the anchor rules.

Anchors are marked up **inline**, not passed alongside the text:

```python
write_equation("R = u² [[sin(2θ)|projectile.horizontal_range]] / g", "range on flat ground")
```

The tool extracts the span out of the text it is already writing, which makes
the one failure that silently breaks grounding — a span that is not in the text,
so it renders as nothing — impossible rather than merely validated. Block and
anchor ids are minted server-side and returned, so `point_at` and `strike_block`
can only ever name something that exists.

There is no delete. `strike_block` crosses a block out and leaves it visible: a
corrected mistake teaches more than a mistake that quietly vanished.

## Where the stubs are

See [INTEGRATION.md](INTEGRATION.md) — the complete list, ordered by what breaks
first on deployment, with the file and line for each and what the swap actually
involves.
