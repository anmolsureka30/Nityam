# Nityam

Nityam is a personalized learning partner: pick what you actually want to study (a chapter, a
problem set, a lecture you're stuck on) and work through it in conversation with a tutor that
teaches the way a good one does. It draws out what you already understand before adding to it,
checks understanding with a question instead of assuming the explanation landed, and only
re-explains, differently, when the gap turns out to be real. Every lesson is grounded in the
actual textbooks and lectures you're covering, so the same conversation can hold learning
something new, revising what's shaky, and chasing a tangent worth researching. And it remembers
exactly where you left off, the next time and every time after.

Built for the **Google All Things Agentic Hackathon** (track: *Collaborative Partner*), stateful
multi-turn dialogue with real-time retrieval and persistent memory.

```mermaid
graph LR
  Student([Student]) <-->|Gemini Live, voice| Voice(("VoiceAgent<br/>router"))
  Voice -->|ask_board| Board(BoardAgent)
  Voice -->|ask_textbook| Book(TextbookAgent)
  Voice -->|ask_quiz| Quiz(QuizAgent)
  Voice -->|ask_artifact| Art(ArtifactAgent)
  Board & Book & Quiz & Art --> Memory[(SMRITI<br/>workflow · episodic · long-term)]
  Lecture([Recorded lecture]) -->|Shruti pipeline| Memory
  Memory -.->|MemoryEvent| Obs[smriti-observatory]
```

*(Full detail, icon-accurate and built for redrawing in Excalidraw across five diagrams, lives in
[`docs/architecture-diagrams.html`](docs/architecture-diagrams.html).)*

## 🎓 From rote answers to real understanding

A tutor that just answers produces a student who can pass tonight's question and not next week's.
Nityam is built to keep the student doing the thinking, not just receiving it:

- **She asks, then stops.** Two or three sentences, then a question, then silence until the
  student answers. No long lectures.
- **One checkpoint per topic.** The moment something lands, a short quiz follows, before moving
  on, not saved for the end.
- **Wrong answers get real feedback.** Every wrong option is a real misconception, and every
  rebuttal says exactly what's wrong with it, never "try again."
- **Hints only on request.** A quiz question carries one hint, shown only if the student asks for
  it. The default is a real chance to think it through first.
- **Simulations you play with, not watch.** Every artifact is built around a specific
  misconception, and what the student discovers while playing with it becomes part of their
  record.
- **Marking the textbook starts a conversation.** Highlight a line, and that's what gets asked
  about next, not a note that disappears.
- **What's worked before gets remembered.** The tutor tracks which teaching style (Socratic
  questions, a worked example, guided practice) actually landed for this student, and reuses it.

This is what "Collaborative Partner" means here: not a smarter answer key, and not a video on
autoplay. A partner that keeps the student in the work.

## 🧭 The four pillars

Four things this build had to get right, in order, mapped to the hackathon's own focus areas:

**Hyper-personalized layer.** Personalization starts with what the student actually chooses to
study, and SMRITI is what keeps it personal after that: three memory tiers (a live workflow
buffer, a permanent per-session log, and long-term knowledge about the student) where every
stored claim cites the exact turn or lecture timestamp it came from. It isn't a prompt trick; it's
a schema-validated, evidence-gated write path, exercised once per session and checked against a
real multi-persona eval.

**Artifact generation engine.** ArtifactAgent turns "I don't get projectile motion" into an
interactive, student-specific visualization on demand, validated against an IR schema before it
ever reaches the canvas, and durable in Cloud Storage so a reload doesn't lose it. One stored
artifact, personalised at render time, serves every student who needs it.

**Multi-modal, by design.** One Gemini Live voice session doesn't just talk: it routes to four
specialists that write to a shared board, pull up textbook figures, publish quiz questions, and
render simulations, all inside the same conversation. Voice, board, text, and generated visuals
are one experience, not four disconnected surfaces.

**UX that hides the machinery.** The student never hears "let me call a tool": VoiceAgent speaks
every specialist's output as her own words, keeps talking while a specialist is still working
underneath her, and only interrupts herself when three separate timing gates agree it's safe to.
The complexity is real; the point is that it doesn't feel that way.

## ☁️ Built on Google Cloud, end to end

| Layer | Google technology | What it does here |
|---|---|---|
| Voice | Gemini Live (`gemini-live-2.5-flash`) | Real-time bidirectional speech: hears, speaks, routes |
| Reasoning | Gemini (`gemini-3.7-flash`) | All four specialist agents, plus Shruti's extraction passes |
| Orchestration | Agent Development Kit (ADK) | Every agent is an ADK `Runner`; non-blocking streaming tools carry the keep-talking mechanism |
| Compute | Cloud Run + Cloud Run Jobs | The tutor backend; Shruti's ingest pipeline as its own Job |
| Episodic + long-term memory | Firestore | `session_logs`, `dpm_profile`, `teaching_memory`, `grounding_chunks` (native vector search) |
| Workflow memory | Memorystore for Redis | The live per-turn buffer, and the Observatory's pub/sub channel |
| Generated artifacts | Cloud Storage | Durable copies of every `ArtifactAgent` output |
| Sign-in | Firebase Auth | ID-token verification on every WebSocket connection |
| CI/CD | Cloud Build + Artifact Registry + Secret Manager | Redeploys on every push to `main`; secrets never touch the build |

Memory made visible is its own honest addition, not a listed pillar: smriti-observatory streams
every memory read and write live as a session runs, including the writes that get *rejected*,
because a memory layer where every proposed write succeeds is indistinguishable from one with no
rules at all. See its own section below.

## 🏗️ Architecture

Five ADK agents behind one WebSocket, one storage gateway behind all of them:

| Agent | Model | Job | Owns |
|---|---|---|---|
| **VoiceAgent** | `gemini-live-2.5-flash` | Hears, speaks, routes | `read_screen`, `scroll_to`, four `ask_*` delegate tools |
| **BoardAgent** | `gemini-3.7-flash` | Writes the shared board | `write_lesson`, grounding + memory reads, `calculate` |
| **TextbookAgent** | `gemini-3.7-flash` | Finds the reference | `search_textbook`, `show_textbook_figure` |
| **QuizAgent** | `gemini-3.7-flash` | Tests understanding | `publish_quiz_question`, memory reads |
| **ArtifactAgent** | `gemini-3.7-flash` | Builds interactive visuals | `create_artifact`, `log_artifact_evidence` |

VoiceAgent never blocks on a specialist: calling one hands off to ADK's background-task registry,
which returns a free, synthetic "pending" response immediately. Three interruption gates
(`student_is_talking`, `she_just_spoke`, `mid_exchange`) and one per-specialist concurrency lock
keep the conversation coherent while up to four calls could plausibly be in flight. See
**Diagram 2** in the blueprints doc for the full delegation timeline.

### SMRITI, the memory layer

Three questions, three tiers:

| Tier | Answers | Backed by | Written |
|---|---|---|---|
| **Workflow** | What's happening *right now* in this turn? | Memorystore (Redis) + ADK `session.state` | Continuously, free |
| **Episodic** | What happened in *this* session? | Firestore `session_logs` | Once, at session close |
| **Long-term** | Who is this student, across *every* session? | Firestore `dpm_profile` + `teaching_memory` | Once, at session close, through a validated-operation gate |

Long-term memory is never written mid-session, for a reason stated plainly in the code:
*"you don't know what a turn meant until you see what followed it, and a file write inside a turn
is latency you don't need to pay."* At close, one model call (`reflect()`) proposes structured
operations against a JSON Schema; anything malformed is dropped before it touches Firestore.
Every weakness, doubt, and self-reflection carries `evidence: [session_id#turn]`, so a claim with
no citation cannot be written. See **Diagram 4**.

### Shruti, the ingest pipeline

**श्रुति · "that which is heard."** Ten stages (shot/ink-curve analysis, board recovery under
occlusion, code-mixed transcript, deixis resolution: "*this* term, *here*", Beat fusion, board
reading, concept-graph extraction) turn a lecture into a citable knowledge substrate, running as
its own Cloud Run Job against Cloud SQL + pgvector. Every concept and edge in the resulting graph
carries a `BeatRef` back to a real timestamp: *"a concept you cannot point at a moment in a
lecture is a concept you made up."* See **Diagram 3**, and note the one honest gap it draws: the
hop from Shruti's own store into the tutor's live Firestore corpus is a manual script today, not
an automated pipeline yet.

### smriti-observatory

A live view of SMRITI as a session runs: every read, every write, and the writes the
validation gate *rejected*, each correlated to its real trace span. Ships two ways: a maintained
fork of `google/adk-web` with a Memory tab built in, or a standalone React/FastAPI companion. See
`smriti-observatory/README.md`.

## 📂 Structure

- **`backend/`** + **`frontend/`**: the real production tutor, the five-agent voice loop above
  plus a shared canvas the tutor writes on and the student points at. Deployed to Cloud Run. See
  `backend/README.md` to run it, `backend/INTEGRATION.md` for the wiring details.
- **`landing/`**: the public marketing site (Next.js, deployed to Vercel). `backend/run.sh` starts
  it alongside the tutor; see `landing/README.md`.
- **`sub_modules_examples/tutor/`**: an ADK-scaffolded reference implementation of the same memory
  layer and agent topology, used for ADK-tooling-specific work (evals, the ADK dev-ui, the
  Observatory below). Runs side by side with `backend/` on different ports (`8010`/`4200` here vs
  `8210`/`5173` there); see its own `CLAUDE.md`. **`backend/app/memory/`** is a manually-synced
  copy of `sub_modules_examples/tutor/app/memory/`, and a fix landed in one needs porting to the
  other by hand; check both when touching memory-layer code.
- **`smriti-observatory/`**: real-time visualization of SMRITI memory state, built against the
  ADK reference implementation. See `smriti-observatory/README.md` for both ways to run it.
- **`sub_modules_examples/shruti/`**: the video-lecture-to-knowledge-graph extraction pipeline. A
  self-contained project (own `pyproject.toml`, `uv.lock`, tests). See
  `sub_modules_examples/shruti/docs/architecture.md` for the full ten-stage design.
- **`sub_modules_examples/artifact_generator/`**: generates the interactive physics
  visualizations (`ArtifactAgent`'s output) both `backend/` and `sub_modules_examples/tutor/`
  render.
- **`docs/architecture-diagrams.html`**: the five build-accurate diagrams referenced throughout
  this README (open it directly in a browser).
- **`project_documentation/`**: Nityam-level architecture and research, not specific to any one
  submodule:
  - `memory_nityam_architecture/`: the memory-layer/SMRITI architecture wiki (start at its
    `README.md`), covering the design, the Firestore/Redis/GCS migration, and the real
    multi-persona eval results.
  - `wiki/`: Google platform/ADK research that fed the platform decisions (start at
    `wiki/index.md`).

## 🚀 Spin-up: running it locally

Every command below is copy-pasteable from a fresh clone. Read step 0 first — two of these
prerequisites are not obvious, and both fail in ways that look like a bug in the app.

### 0. Prerequisites

| Need | Version | Why, and what breaks without it |
|---|---|---|
| **Python 3.12** | 3.10–3.12 | `backend/run.sh` builds the virtualenv itself, but it probes for `python3.12`, `python3.11`, `python3.10` **in that order and no others**. Homebrew's `python3` is 3.13/3.14 now, and a machine with only those fails with `Install Python 3.10+ first` even though Python is installed. `brew install python@3.12` |
| **Node.js** | 20+ | Three npm workspaces (tutor frontend, Observatory frontend, landing page). `run.sh` installs each one's dependencies for you. |
| **Redis** | 7 | The workflow-memory tier (`backend/app/memory/short_term.py`). `docker compose up -d redis` from `backend/`, or a native `redis-server`. |
| **A Firebase project** | — | **Not optional, and not skippable by mock mode.** Every WebSocket connection verifies a real Firebase ID token (`backend/app/user_auth.py`); there is no dev bypass. A free Firebase project with Google sign-in enabled is enough. |
| **`uv`** | latest | Only for the Observatory backend and Shruti. Skip it with `./run.sh --no-observatory`. `brew install uv` |
| **Google Cloud SDK** | latest | Only for deploying, and for `NITYAM_STORE=firestore`. Not needed for a local run. |

**What you do *not* need for a local run:** Application Default Credentials. This is the single
most common wrong assumption about this repo, and older revisions of this README said otherwise.
Verifying a Firebase ID token needs Google's *public* signing certificates and no credentials at
all — see the long comment at the top of `backend/app/user_auth.py` explaining why the Admin SDK
was deliberately removed. ADC is needed for exactly two optional things: `NITYAM_STORE=firestore`
and the GCS artifact bucket. The default (`NITYAM_STORE=sqlite`) needs neither.

### 1. Configure the backend

```bash
cd backend
cp .env.example .env
```

Then open `.env` and set, at minimum:

```bash
NITYAM_AUTH=mock                       # no Gemini credential, no network, no spend
GOOGLE_CLOUD_PROJECT=your-firebase-project-id   # must match the frontend config in step 2
NITYAM_STORE=sqlite                    # local file at backend/data/memory.db — the default
```

That is the zero-credential path, and it is what the tests run against. For a real tutor that
actually speaks, set `NITYAM_AUTH=vertex_express` and fill in `GOOGLE_API_KEY` (a
[Vertex AI Express Mode](https://cloud.google.com/vertex-ai/generative-ai/docs/start/express-mode/overview)
key) instead. `NITYAM_AUTH` accepts `ai_studio`, `vertex`, `vertex_express`, or `mock`; run
`.venv/bin/python -m app.auth` at any point to see which of them actually work on your machine,
including a real Gemini Live handshake.

### 2. Configure the frontend — do not skip this

`frontend/.env` is gitignored and holds six values from your Firebase console
(**Project settings → General → Your apps → SDK setup and configuration**):

```bash
cd ../frontend
cp .env.example .env
```

```bash
VITE_FIREBASE_API_KEY=
VITE_FIREBASE_AUTH_DOMAIN=
VITE_FIREBASE_PROJECT_ID=          # same project as GOOGLE_CLOUD_PROJECT above
VITE_FIREBASE_STORAGE_BUCKET=
VITE_FIREBASE_MESSAGING_SENDER_ID=
VITE_FIREBASE_APP_ID=
```

None of these are secrets — Firebase's web config identifies a project, it doesn't authenticate
anything, and security is enforced by Firebase Security Rules (`firestore.rules`). Vite bakes them
into the bundle at *build* time, so they cannot be supplied at runtime.

Leave them blank and the app renders a "not configured yet" setup notice rather than the tutor.
That's a deliberate guard: `getAuth()` **throws at module-evaluation time** on a missing API key,
which used to take the entire product down to a blank white page with one console line. See the
comment in `frontend/src/lib/firebase.ts`.

Enable **Google** as a sign-in provider in the Firebase console (Authentication → Sign-in method),
or nobody can sign in.

### 3. Start Redis

```bash
cd ../backend
docker compose up -d redis      # see backend/docker-compose.yml
# or, without Docker:
redis-server --daemonize yes --port 6379
```

### 4. Start everything

```bash
./run.sh
```

One command, five processes. On first run it also creates the virtualenv, installs Python and npm
dependencies, prints a credential preflight, and seeds the demo student (without which every
memory tool returns `found: false` and the tutor has nothing to teach from).

| Surface | URL | Override |
|---|---|---|
| **Tutor (start here)** | http://localhost:5173 | `NITYAM_WEB_PORT` |
| Backend API + WebSocket | http://localhost:8210 | `NITYAM_API_PORT` |
| Landing page | http://localhost:3001 | `NITYAM_LANDING_PORT` |
| SMRITI Observatory | http://localhost:3000 | `NITYAM_OBSERVATORY_PORT` / `..._WEB_PORT` |

The Observatory frontend's port **must** be 3000: its backend hardcodes CORS to
`localhost:5173` and `localhost:3000`, 5173 is already the tutor's, and a fetch from any other
origin fails silently.

Narrower run modes, when you don't want all five processes:

```bash
./run.sh --no-observatory     # skips the Observatory (and its uv requirement)
./run.sh --no-landing         # skips the Next.js landing page
./run.sh --api-only           # backend alone, nothing browser-facing
```

`run.sh` refuses to start on a busy port and prints what is holding it, rather than letting
uvicorn die quietly while Vite starts anyway — which used to present as a tutor that simply never
spoke. Ctrl-C cleans up all five processes.

### 5. Confirm it works

```bash
curl localhost:8210/health                # the backend is up
.venv/bin/python -m app.auth              # which auth modes work, including a real Live handshake
.venv/bin/python -m tests.test_canvas     # the board, no model in the loop
.venv/bin/python -m tests.test_wire       # the protocol, real server, mock mode
.venv/bin/python -m scripts.drive         # a whole lesson in text mode, prints the board it wrote
.venv/bin/python -m tests.test_live       # real Gemini — costs money, skips on mock
```

`scripts/drive.py` is the one to reach for when the tutor stops writing on the board: it runs
BoardAgent directly, prints every tool call, then prints the board that came out with a pass/fail
on the three things that have to be true — grounded, wrote to the board, patches queued.

Frontend tests: `cd frontend && npm test`.

### Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Install Python 3.10+ first` with Python installed | `run.sh` only probes `python3.12`/`3.11`/`3.10` | `brew install python@3.12` |
| The page shows a "not configured yet" notice | `frontend/.env` is missing or has a blank value | Step 2 |
| "Your sign-in has expired" on a valid sign-in | `GOOGLE_CLOUD_PROJECT` doesn't match the frontend's `VITE_FIREBASE_PROJECT_ID`, so the token's `aud` check fails closed | Make both the same project id; the backend log names the real reason |
| `Port 8210 … is already in use` | Leftover from an earlier run | `kill $(lsof -t -iTCP:8210 -sTCP:LISTEN)`, or `NITYAM_API_PORT=8211 ./run.sh` |
| Observatory's Working-memory tier is empty | Redis isn't reachable | Step 3 |
| Observatory's Episodic/Long-term tiers are empty | It reads Firestore directly | Set `NITYAM_STORE=firestore` + ADC |
| The tutor answers but never speaks | `NITYAM_AUTH=mock` uses synthetic audio | Switch to a real mode and re-run `python -m app.auth` |
| `429 RESOURCE_EXHAUSTED` | Gemini quota, usually mid-eval | Wait, or use a different key |
| Backend port 8100 collides | The `sub_modules_examples/adk` sub-module also defaults to 8100 | `NITYAM_OBSERVATORY_PORT=8101 ./run.sh` |

## 🧪 Tests and evals

The memory layer is the part with a real eval, not just unit tests:
`sub_modules_examples/tutor/tests/eval/memory_eval/` runs the real `TutorAgent` through five
multi-session student personas against real Firestore/Redis, with deterministic checks (D1–D7) and
LLM-as-judge checks (L1–L4). Needs ADC and real Gemini quota.

```bash
cd sub_modules_examples/tutor
uv run python -m tests.eval.memory_eval.run_eval
```

See `project_documentation/memory_nityam_architecture/README.md` for the reading order and
`memory_layer_eval_report.md` for the latest results, including what's still open.

## 📼 Running Shruti

The lecture-ingest pipeline is a self-contained project with its own dependencies and credentials:

```bash
cd sub_modules_examples/shruti
uv sync
cp .env.example .env             # fill in your own credentials
uv run --env-file .env python -m shruti.cli ingest
```

See `sub_modules_examples/shruti/docs/architecture.md` and its `justfile` for more commands.

## ☁️ Spin-up: deploying to Google Cloud

The whole app — FastAPI backend, all five ADK agents, the built frontend, and the built
Observatory — ships as **one container image** to **one Cloud Run service**. `backend/app/main.py`
serves `frontend/dist` at `/` and `smriti-observatory/frontend/dist` at `/observatory` whenever
those directories exist (see its `DIST` and `OBS_DIST` mounts), so there is no separate frontend
host to deploy.

### One-time project setup

```bash
export PROJECT_ID=your-project-id
gcloud config set project $PROJECT_ID

# 1. APIs
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com firestore.googleapis.com storage.googleapis.com \
  redis.googleapis.com secretmanager.googleapis.com

# 2. Artifact Registry repo (the name `nityam` is what cloudbuild.yaml expects)
gcloud artifacts repositories create nityam \
  --repository-format=docker --location=us-central1

# 3. Runtime service account + roles
gcloud iam service-accounts create nityam-backend-sa
for ROLE in roles/datastore.user roles/storage.objectAdmin \
            roles/secretmanager.secretAccessor roles/run.developer; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member=serviceAccount:nityam-backend-sa@$PROJECT_ID.iam.gserviceaccount.com \
    --role=$ROLE
done

# 4. The one real secret — the backend's Gemini credential
printf '%s' "$GOOGLE_API_KEY" | gcloud secrets create nityam-google-api-key --data-file=-

# 5. Firestore (database id `smriti`) and the artifacts bucket
gcloud firestore databases create --database=smriti --location=us-central1
gcloud storage buckets create gs://$PROJECT_ID-nityam-artifacts --location=us-central1

# 6. Memorystore for the workflow tier — REAL ONGOING COST, confirm before running
gcloud redis instances create nityam-redis --size=1 --region=us-central1 --network=default
gcloud redis instances describe nityam-redis --region=us-central1 --format='value(host)'
```

Deploy the Firestore security rules with the Firebase CLI —
`firebase deploy --only firestore:rules` from the repo root, where `firestore.rules` lives — and add
your Cloud Run URL to Firebase Authentication's **Authorized domains**, or sign-in is rejected in
production.

### Deploy

Build context is the **repo root**, not `backend/` — the image needs `frontend/`,
`smriti-observatory/`, and `sub_modules_examples/artifact_generator/` too.

```bash
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_VITE_FIREBASE_API_KEY=...,_VITE_FIREBASE_AUTH_DOMAIN=...,\
_VITE_FIREBASE_PROJECT_ID=...,_VITE_FIREBASE_STORAGE_BUCKET=...,\
_VITE_FIREBASE_MESSAGING_SENDER_ID=...,_VITE_FIREBASE_APP_ID=...
```

The `VITE_FIREBASE_*` values arrive as build substitutions rather than from Secret Manager because
Vite bakes them into the JS bundle at build time and they are not secrets (see step 2 above and
`backend/Dockerfile`'s own comment). The real secret is fetched by Cloud Run itself at deploy time
via `--update-secrets`, and never touches the build.

To build and deploy by hand instead, the equivalent of what `cloudbuild.yaml` does:

```bash
docker build -f backend/Dockerfile -t us-central1-docker.pkg.dev/$PROJECT_ID/nityam/nityam-backend:latest \
  --build-arg VITE_FIREBASE_API_KEY=... [+ the other five] .
docker push us-central1-docker.pkg.dev/$PROJECT_ID/nityam/nityam-backend:latest

gcloud run deploy nityam-backend \
  --image=us-central1-docker.pkg.dev/$PROJECT_ID/nityam/nityam-backend:latest \
  --region=us-central1 --platform=managed \
  --service-account=nityam-backend-sa@$PROJECT_ID.iam.gserviceaccount.com \
  --allow-unauthenticated \
  --timeout=3600 --session-affinity \
  --memory=2Gi --cpu=2 --concurrency=10 \
  --min-instances=1 --max-instances=10 \
  --network=default --subnet=default --vpc-egress=private-ranges-only \
  --update-secrets=GOOGLE_API_KEY=nityam-google-api-key:latest \
  --set-env-vars=NITYAM_AUTH=vertex_express,NITYAM_STORE=firestore,\
GOOGLE_CLOUD_PROJECT=$PROJECT_ID,FIRESTORE_DATABASE=smriti,\
GCS_BUCKET=$PROJECT_ID-nityam-artifacts,REDIS_HOST=<memorystore-ip>,REDIS_PORT=6379
```

Four of those flags are load-bearing and not defaults: **`--timeout=3600`** (a tutoring session is
a long-lived WebSocket, and the 5-minute default kills it mid-lesson), **`--session-affinity`**
(the socket must return to the instance holding that session's state), **`--vpc-egress` with
`--network`/`--subnet`** (Direct VPC egress is how Cloud Run reaches Memorystore's private IP), and
**`--min-instances=1`** (a cold start on a voice handshake is a student staring at a dead mic).

### Continuous deployment

`cloudbuild.yaml` is wired to a Cloud Build trigger on push to `main`: build → push to Artifact
Registry → `gcloud run deploy`. Point a trigger at it and set the six `_VITE_FIREBASE_*`
substitutions in the trigger config.

### Verify the deployment

```bash
SERVICE_URL=$(gcloud run services describe nityam-backend --region=us-central1 --format='value(status.url)')
curl $SERVICE_URL/health
open $SERVICE_URL          # sign in, then start a session and check the tutor speaks
```

The full design, including Shruti's separate Cloud Run Job and the authenticated
Job→Service sync webhook, is in
`docs/superpowers/specs/2026-08-30-cloud-run-deployment-design.md`.

**One known gap, stated plainly:** `frontend/src/lib/live/session.ts`'s WebSocket `onclose` handler
does not reconnect. Locally that never matters; on Cloud Run an instance recycling mid-session
(a new revision, `--min-instances` churn) silently ends a student's session. Confirmed real,
deliberately out of scope for the deployment pass, and not an oversight.

## ✅ Honest status

This codebase's own convention is to disclose gaps rather than smooth over them, and that's worth
keeping here too:

- **Citation faithfulness is strong**: 5/5 on an automated LLM-as-judge check, reproduced twice.
  The property SMRITI is specifically built to protect held up under real scrutiny.
- **Personalization and memory-causality are the open problem.** Does the tutor *visibly* use what
  it remembers to shape a new session's opening turn? That's the eval's own sharpest, still-open
  finding, not a solved feature.
- **Shruti's automation gap is real and disclosed.** The pipeline produces real, citable grounding
  chunks; nothing yet automates the hop into the tutor's live Firestore corpus, so a person runs
  `seed_demo_data.py` by hand today.
- **New sign-ins are demo-seeded** (`NITYAM_SEED_NEW_STUDENTS`) with a fabricated prior history, so
  a first session already looks personalized for a judge. Disclosed in-repo as a demo convenience;
  turn it off for real students.
