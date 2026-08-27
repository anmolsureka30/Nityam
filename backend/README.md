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
board. It runs TutorAgent directly through `run_async`, prints every tool call,
and then prints the board that came out with a pass/fail on the three things
that have to be true: grounded, wrote to the board, patches queued.

## The agents

```
VoiceAgent          gemini-live-2.5-flash   ears and mouth, tiny instruction
└─ TutorAgent       gemini-3.7-flash        the brain — all memory, all board tools
   ├─ ArtifactAgent gemini-3.7-flash        spec -> IR -> validate -> mounted
   └─ QuizAgent     gemini-3.7-flash        writes checkpoint questions
```

ArtifactAgent and QuizAgent declare `mode='single_turn'`, so ADK wraps them into
TutorAgent's own tools rather than making them transfer targets. **Only
TutorAgent addresses the student**; they take a brief, put something on screen,
and report back.

**VoiceAgent reaches TutorAgent through a function tool, not `sub_agents`.**
`architecture.md` §2 specifies `sub_agents=[TutorAgent(mode='single_turn')]`, and
that cannot work on the streaming path: a `single_turn` child is executed by
`workflow/_node_runner.py`, which enqueues onto
`InvocationContext._event_queue` — a queue `run_async` creates (`runners.py:595`,
`:752`) and `run_live` never does. On the live path it raises on the child's
first event, the tool returns an error string, and the tutor apologises to the
student about a technical hiccup.

So TutorAgent runs in its own Runner through `run_async`, called from
`app/agents/brain.py:ask_tutor`. That also delivers what §2 wanted from the
arrangement — the full `before_model_callback` lifecycle, which never fires under
`run_live` — more directly than the sub-agent mechanism did.

Why two model layers rather than one: the Live API bills every context token,
including the system instruction, on every turn — so memory can never live in
the voice agent's prompt (`architecture.md` §3). The cost is a pause on
substantive turns, which is why VoiceAgent is instructed to say something before
it delegates.

Adding an agent: write `build_x_agent()` with `mode='single_turn'`, add it to
TutorAgent's `sub_agents`, and give it a `description` — the description is what
TutorAgent routes on, so it is the actual interface. Build sub-agents in a
factory, never at module level: an agent already attached to one parent raises
`"agent already has a parent"`.

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
