# backend

The tutor: a Gemini Live voice loop, three reasoning agents, and a shared board
the tutor writes on and the student points at.

```
browser ──PCM16@16k──┐
                     ├─► /ws ─► LiveRequestQueue ─► run_live ─► Gemini Live
ContextPacket ───────┘                                 │
                                                       ├─ audio 24k ──────────► speaker
                                                       ├─ outputTranscription ► caption + avatar mouth
                                                       └─ tool calls ─────────► log
board outbox ──────────────────────────────────────────────────────────────────► canvas patches
```

Three concurrent tasks per connection. The third one is why the tutor can write
on the page at all: board tools run several frames deep inside a
`mode='single_turn'` sub-agent invocation with no reference to the socket, so
they publish to a per-session queue and `outbound()` delivers it.

## Run it

```bash
cp .env.example .env        # then fill in credentials, or set NITYAM_AUTH=mock
./run.sh                    # backend + frontend dev server
./run.sh --api-only         # backend alone
```

`run.sh` builds the virtualenv, checks credentials, seeds the demo student on
first run, and refuses to start if the port is busy — a silently-busy port used
to look like a tutor that just never spoke.

Mock mode needs no credentials, no network and no spend. It is what the tests
run against.

Defaults: API `8210`, web `5173`. Both move together via `NITYAM_API_PORT` /
`NITYAM_WEB_PORT`; `frontend/vite.config.ts` reads the same vars. The `adk`
sub-module keeps 8100/5273, so both can run side by side.

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

* Each `ask_*` takes a required `bridge` argument — the holding line VoiceAgent
  says out loud *right now*, while the specialist works. The Live model would
  otherwise either speak or call, never both.
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
`SpecialistRunner`, and expose one `async def ask_x(bridge, request,
tool_context)` tool that calls `run_turn` and returns `{"status", "summary"}`.
Register it in `voice_agent.py` wrapped in `_when_idle(...)`. The tool's
docstring is the actual interface — it is what VoiceAgent routes on. Build
agents in a factory, never at module level: an agent already attached to one
parent raises `"agent already has a parent"`.

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
