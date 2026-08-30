# `adk` — conversational voice with Google ADK

A React page with one button. Press it, talk, and a Gemini agent talks back —
interrupting it mid-sentence works, the way it does with a person. Two agents
live behind the socket and hand the student between themselves; you can *hear*
the handoff, because each one has its own voice.

Scope, as with the other sub-modules: this is a reference implementation to be
read and lifted, not the product. It is deliberately small enough to read in
one sitting.

```
sub_modules_examples/adk/
├── .env                    Credentials + mode. One file, gitignored.
├── backend/
│   ├── main.py             FastAPI + WebSocket. The only file that knows about HTTP.
│   ├── auth.py             Which Google backend, and a preflight that proves it works.
│   ├── nityam_agents/      The two agents. No transport code.
│   └── mock_live.py        A fake Live API, for demoing without credits.
├── frontend/
│   ├── src/liveSession.js  The browser half of the pipeline. Framework-free.
│   ├── src/useLiveSession.js  ADK events -> UI state.
│   ├── src/App.jsx         The page.
│   └── public/*.js         Two AudioWorklets: capture and playback.
└── tests/                  22 assertions, no API key needed.
```

## Run it

```bash
./run.sh              # backend + Vite dev server, then open localhost:5273
./run.sh --built      # backend only, serving frontend/dist
```

**Ports: backend `8100`, dev server `5273`.** Both are moved clear of `5173`
and `8000`, which the product front end in `frontend/` uses. Override either:

```bash
NITYAM_ADK_API_PORT=8101 NITYAM_ADK_WEB_PORT=5274 ./run.sh
```

The Vite proxy derives its target from the API port, so moving the backend
moves the front end's WebSocket with it.

`run.sh` creates the virtualenv on first use (needs Python 3.10+; ADK does not
support 3.9) and runs the credential preflight before starting — skipped in
mock mode, where there is nothing to check.

Configuration is one file, `.env` at this directory's root. `NITYAM_AUTH`
chooses the backend and `NITYAM_MODEL` is the single place a model name
appears.

## Credentials — the combination that works

**Working, verified end to end against real Gemini Live:**

```ini
NITYAM_AUTH=vertex_express
NITYAM_MODEL=gemini-live-2.5-flash
GOOGLE_CLOUD_PROJECT=nityam-506707
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_OAUTH_ACCESS_TOKEN=…      # this is the credential that works
```

`node tests/live.mjs` drives the real thing and passes: the tutor opens the
conversation unprompted, answers a question, `show_formula` executes, and
hundreds of kilobytes of real audio come back with transcription.

Getting there took three separate discoveries, none of them obvious, all of
them things the next person will hit:

**1. The OAuth token is the credential — used as an API key.** Not as OAuth
credentials, which returns `401`. `genai.Client(vertexai=True, api_key=<the
OAuth token>)` authenticates; the same call with `GOOGLE_API_KEY` returns `403
PERMISSION_DENIED` for `aiplatform`, and `GOOGLE_API_KEY` on AI Studio returns
`429 — prepayment credits are depleted`. So of the four plausible
credential/platform pairings, exactly one works.

**2. Vertex Live needs the full resource path.** A bare model name returns
`1007 Invalid resource field value`. `google-genai` expands bare names only to a
*relative* `publishers/google/models/…`, which the Live service rejects, so
`auth.resolve_model()` builds the absolute path:

```
projects/nityam-506707/locations/us-central1/publishers/google/models/gemini-live-2.5-flash
```

ADK cooperates with this — it switches its client to enterprise mode when the
model starts with `projects/`. Express mode also requires project and location
to be *absent* from the environment, or the SDK takes the ADC path and ignores
the key; the project id survives inside the model path, which is why the order
of operations in `configure()` matters.

**3. The native-audio models are not provisioned for this project.** Every
`*-native-audio*` name returns `1008 Publisher model not found`. The
half-cascade `gemini-live-2.5-flash` works. Consequences worth knowing:

- Voices are the eight half-cascade ones — `Leda` and `Puck`, used by the two
  agents, are both in that set.
- `speech_config.language_code` is honoured, where native audio would infer
  language from context.
- `TEXT` response modality is available, which native audio does not offer.
- No affective dialog or proactive audio.

### The token expires in about an hour

This is the one real operational limit. When voice suddenly returns `401
UNAUTHENTICATED`, the token has lapsed — mint a fresh
`GOOGLE_OAUTH_ACCESS_TOKEN`, put it in `.env` and restart. The server forwards
the error to the browser as a banner rather than hanging, and
`tests/live.mjs` says so explicitly.

For something that does not expire, install gcloud and use ADC:

```bash
brew install --cask google-cloud-sdk
gcloud auth application-default login
gcloud config set project nityam-506707
gcloud services enable aiplatform.googleapis.com
```

then `NITYAM_AUTH=vertex`. `resolve_model()` builds the same path for that mode.

### The other modes, and why they fail here

| Mode | Needs | Status |
|---|---|---|
| `vertex_express` | OAuth token as `api_key` | **works** |
| `vertex` | project + location + ADC | no gcloud installed |
| `ai_studio` | `GOOGLE_API_KEY` | key valid, **project out of prepay credits** |
| `mock` | nothing | works, no network |

On the AI Studio one: a linked Cloud Billing account is *not* drawn on
automatically — the Gemini API needs its own prepay balance, bought at
<https://aistudio.google.com/app/billing>. That is why the key authenticates
and still returns 429.

`python backend/auth.py` probes all of them and, for whichever works, opens a
real Live session to confirm voice specifically. Ordinary text calls succeeding
would not prove Live works — that is the whole point of this module, and Live
is a separate, separately-priced surface.

> Two of the values in `.env` are live secrets and are now in a chat
> transcript. Rotate the API key; the OAuth token expires on its own.
> `.env` is gitignored, `.env.example` is the committed copy. `DATABASE_URL`,
> `GCS_BUCKET` and `STORAGE_EMULATOR_HOST` are unrelated to the LLM call and
> are not read here.

## How it fits together

```
  browser                        this process                     Google
  ───────                        ────────────                     ──────
  mic ──► AudioWorklet
          Float32 ─► PCM16 16k
                    │
                    │ WebSocket, binary frames
                    ▼
                              LiveRequestQueue.send_realtime()
                                          │
                              Runner.run_live()  ◄──────► Live API
                                          │                (WebSocket)
                                          │  Event objects
                    ◄─────────────────────┘
                    │ WebSocket, event JSON
                    ▼
          base64 ─► PCM16 24k
  speaker ◄── AudioWorklet ◄── ring buffer
```

Everything above the queue is transport; everything below it is ADK. The
browser cannot speak to ADK directly — ADK is a server-side Python runtime with
no browser client — which is the whole reason this process exists.

Two concurrent tasks per connection, never one:

- **upstream** browser → `LiveRequestQueue`
- **downstream** `run_live()` → browser

They must run together under `asyncio.gather`, because the student has to be
able to talk while the model is still talking. That is what "bidi" means, and
it is the only reason interruption works.

### Audio formats are not negotiable

ADK converts nothing. Wrong rate in means garbage in.

| Direction | Format | Rate | Channels | MIME |
|---|---|---|---|---|
| mic → model | PCM16 | **16000** | mono | `audio/pcm;rate=16000` |
| model → speaker | PCM16 | **24000** | mono | `audio/pcm;rate=24000` |

Hence two `AudioContext`s in `liveSession.js`: a context has exactly one sample
rate, and input and output disagree.

## Transcription arrives twice — and that is not a bug

The single most surprising thing in the real event stream, and invisible in any
mock that does not imitate it:

```
partial=True   "Nam"
partial=True   "aste! The formula for maximum height depends on"
partial=True   " the angle it is launched at."
partial=False  "Namaste! The formula for maximum height depends on the angle it is launched at."
   ^ finished=True — the WHOLE sentence, again
```

A client that appends every `outputTranscription.text` prints the sentence
twice. `useLiveSession.js` therefore tracks a turn as *confirmed text plus a
trailing in-flight fragment*: `partial` grows the fragment, `finished` replaces
it and appends to the confirmed text, and only end-of-turn commits a bubble. One
turn stays one bubble even though the API consolidates per sentence.

`mock_live.py` reproduces this shape exactly, which is the only reason mock mode
is worth trusting as a stand-in.

One more format wrinkle: **Vertex sends a bare `audio/pcm` with no rate
parameter**, where AI Studio spells out `;rate=24000`. The playback context is
built at the documented 24kHz either way, and `liveSession.checkRate()` warns if
a model ever declares something else — otherwise the voice would simply sound
pitch-shifted with no error anywhere.

## The two agents

`nityam_agents/agent.py`, and nothing in `main.py` knows there are two:

- **`tutor`** (root) — explains, voice *Leda*, tool `show_formula`
- **`quiz_master`** (sub-agent) — tests and scores, voice *Puck*, tool
  `record_answer`

Ask to be quizzed and ADK calls `transfer_to_agent` by itself; the stream
continues in the same `run_live()` loop, same session, same queue. Watch
`event.author` to know who is speaking — that is what drives the badge in the
UI.

Two details worth stealing:

- **Voice belongs to the agent, not the session.** Setting `speech_config` on a
  `Gemini` instance and passing that to `Agent` is what makes the handoff
  audible. A session-level `speech_config` would give both agents one voice, and
  agent-level config wins where both are set.
- **`sub_agents` forces transcription on.** ADK enables input and output
  transcription whenever an agent has sub-agents, because transfer passes text
  context to the next agent. You get free captions; you cannot turn them off.

The Live API waits for input and never takes the first turn on its own, so an
agent instructed to "open by greeting them" will sit silent. `main.py` sends a
`GREETING_CUE` — a bracketed stage direction as user-role content — when the
client connects. It never reaches the student: input transcription only covers
audio, and the UI echoes only what it typed. `tests/live.mjs` asserts the cue
does not leak into her speech.

`RunConfig` also carries `session_resumption` — the platform caps a Live
session at roughly 10–15 minutes, and without resumption a lesson simply dies
at the cap.

The `App` wrapper sets `context_cache_config`. Every transfer swaps the system
instruction and the tool set, so the prompt prefix changes and the whole prompt
is re-sent uncached on each handoff. ADK warns about this at startup if you
leave it out, and on a chatty tutor it is a real bill.

## Mock mode

`NITYAM_AUTH=mock` (the current default in `.env`) swaps the Live API for `mock_live.py`, which emits the *same
event shapes* — same field names, same ordering, same `turnComplete` /
`interrupted` flags. The whole front end, the audio pipeline, the transcript,
the handoff indicator and the tool cards run against it unchanged.

It has a crude VAD (energy over a threshold, then silence ends the turn), fakes
one agent transfer, and synthesises a syllable buzz at 24kHz so a lip-sync
consumer has real amplitude structure to follow. It does not understand you —
replies are canned. It proves the plumbing, not the intelligence.

Worth keeping past the credit problem: a voice demo whose only failure mode is
someone else's billing is a bad demo.

## Tests

```bash
node tests/audio.mjs      #  9 — PCM conversion, base64, rate arithmetic
node tests/session.mjs    # 11 — spawns uvicorn, drives the real WebSocket protocol
node tests/browser.mjs    # 14 — drives the real React app in headless Chrome
node tests/live.mjs       #  6 — the real Live API. Costs money. Skips in mock mode.
```

The first three need no API key, no credits and no browser install. `tests/browser.mjs` talks to Chrome
over the DevTools protocol directly (no Puppeteer) and uses Chrome's fake media
device as a microphone, so `getUserMedia` → worklet → PCM16 → socket → playback
is exercised for real. It writes a screenshot to `$NITYAM_SHOT`.

Bugs these caught, all of the same family — a test that only checked the happy
path would have missed each:

- The mock VAD measured speech in **wall-clock** time, so audio fed faster than
  real time never counted as a turn. A real VAD counts samples; now so does
  this one.
- `useLiveSession` returned its value through a `useMemo` whose dependency list
  was missing `drafts`, so live captions were computed and silently discarded.
  The memo bought nothing and has been removed rather than fixed.
- Captions only appeared when a turn **ended**, leaving the student watching
  silence for the length of every answer — which is the exact thing captions
  exist to prevent.
- Every caption printed **twice**, because the consolidated transcription event
  repeats the sentence its partials already spelled out. Only visible against
  the real API, until the mock was taught the same shape.
- Multi-sentence turns fragmented into **one bubble per sentence**, because the
  API consolidates per sentence rather than per turn.
- The tutor never spoke first against real Gemini: `greet` had been implemented
  in the mock only, so the instruction to open the conversation had nothing to
  trigger it.
- Fixed test ports collided with the previous suite's server, surfacing as an
  unexplained timeout. The suites now ask the OS for a free port.

## Lifting this into the product

- `frontend/src/liveSession.js` is deliberately framework-free — it is the piece
  to move first, with `useLiveSession.js` as the example of wrapping it.
- `liveSession.analyser` is an `AnalyserNode` sitting between playback and the
  speakers. That is the hook `sub_modules_examples/avatar`'s `attachAudio()` was written
  against: connect them and the avatar lip-syncs to the real voice.
- The tool → UI path (`show_formula` → a card) is the seam where
  `artifact_generator` and `canvas` attach. A tool that returns an artifact IR
  instead of a formula string is the whole integration.
- `main.py` is the only file that knows about HTTP, and `nityam_agents/` the
  only one that knows about physics. Keep that line.

## Known limits

- `InMemorySessionService` — history dies with the process. Swap for
  `DatabaseSessionService` (there is already a Postgres URL in the env) or
  `VertexAiSessionService`.
- No authentication on the WebSocket. `user_id` and `session_id` come straight
  off the URL and are trusted.
- Server-side VAD only. Push-to-talk needs
  `realtime_input_config.automatic_activity_detection.disabled = True` plus
  `send_activity_start()` / `send_activity_end()`.
- Video and screen share are unwired, though `send_realtime()` takes image
  blobs the same way.
- The OAuth-token credential expires hourly. ADC (`NITYAM_AUTH=vertex`) is the
  fix; nothing in this module can refresh a token it was handed.
- Native-audio models are unavailable on this project, so no affective dialog
  and no proactive audio — both are native-audio-only features.
- Desktop Chrome only, tested there. Safari's AudioWorklet + 16kHz
  `AudioContext` behaviour has not been checked.
