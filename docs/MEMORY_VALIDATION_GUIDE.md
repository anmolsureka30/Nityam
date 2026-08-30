# Validating the cloud memory migration — a walkthrough

Everything in this guide checks a specific piece of what changed in the
`2026-08-28-memory-storage-completion` plan: Firestore, Cloud Storage, Redis, and the fix that
makes session memory actually get written at all. Two ways to check each piece — an automated
test (fast, exact pass/fail) and a manual walkthrough (see it happen with your own eyes in the
Google Cloud console). Do both if you want real confidence; the automated tests alone are
enough to prove the code works.

---

## 0. One-time setup

You need these running before anything below will work:

```bash
# 1. A local Redis — new requirement, wasn't needed before this plan
redis-server --daemonize yes --port 6379
redis-cli ping   # should print PONG

# 2. Backend dependencies (already installed if you've run this before)
cd backend
.venv/bin/python -m pip install -r requirements.txt

# 3. Confirm your real credentials are set
grep NITYAM_AUTH .env   # should show NITYAM_AUTH=vertex_express (or similar, not "mock")
```

---

## 1. Automated tests — fast, exact pass/fail

Run these from `backend/`. Each one proves one specific piece.

### Cloud Storage — generated artifacts persist

```bash
.venv/bin/python -m tests.test_gcs_artifacts
```
**Proves:** an artifact's data actually round-trips through the real
`nityam-506707-tutor-artifacts` bucket — saved, read back identical, deleted. No mocks; this
talks to real Google Cloud Storage.

### Redis — the turn buffer write-through

```bash
.venv/bin/python -m tests.test_short_term_writethrough
```
**Proves:** when the tutor and student exchange a turn, it actually lands in Redis — not just
in the server's own memory.

### The WebSocket teardown fix

```bash
.venv/bin/python -m tests.test_ws_teardown
```
**Proves:** when a student disconnects, the server-side connection handler actually finishes
running (this was broken before this plan — the server would just hang open silently). Runs a
mock-mode check for free, then a real-credentials check.

### Firebase Auth (from the earlier work this session)

```bash
.venv/bin/python -m tests.test_ws_auth
.venv/bin/python -m tests.test_user_auth
```
**Proves:** no token / a garbage token / the wrong token gets rejected; a real signed-in user
connects normally.

### The big one — close_session actually reaches Firestore

```bash
NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_close_session_wiring
```
**Proves the actual headline fix:** seeds two turns, opens a real connection, disconnects, then
checks Firestore for a real `session_log` document containing those exact turns. This is the
one that was silently broken before this whole plan — nothing reached Firestore at all.

**Note:** this one makes one real, small Gemini API call (the "Reflect" step) and writes real
data to your `demo_student` record in Firestore — that's expected, not a bug. It's also the
only one of these that needs real credentials; the rest work with no spend.

### The existing protocol test (for context, not new)

```bash
.venv/bin/python -m tests.test_wire
```
You'll see **4 failures** here (`greeting makes the tutor write something`, `and say something`,
`a question produces board writes`, `including the formula`) — these are pre-existing, confirmed
unrelated to anything in this plan (verified via `git stash` against the baseline before any of
this work started). Everything else in this file should pass.

---

## 2. Manual walkthrough — see it happen live

### Step 1 — start everything

```bash
redis-server --daemonize yes --port 6379   # if not already running
cd backend && ./run.sh
```
Open [http://localhost:5173](http://localhost:5173), sign in (demo account:
`demo@nityam.local` / `nityam-demo-2026`, or your own Google sign-in), and start a session.

### Step 2 — have an actual conversation

Talk to the tutor for a minute or two. Ask it a question, let it write something on the board.
**Ask it to build you a simulation** at some point (e.g. "can you show me a simulation of
this?") — that's what exercises the Cloud Storage piece.

### Step 3 — watch Redis fill up live (optional, while still connected)

In a second terminal, *before* you disconnect:
```bash
redis-cli KEYS "session:*"
```
You should see a key like `session:<your-uid>:<session-id>:turns` — that's the live turn buffer.
Read it directly if you're curious:
```bash
redis-cli LRANGE "session:<the-key-you-saw>:turns" 0 -1
```

### Step 4 — end the session

Close the tab, or navigate away from `/session`.

### Step 5 — check Firestore

Go to [console.cloud.google.com](https://console.cloud.google.com) → project `nityam-506707` →
Firestore → database **`smriti`** (not the default database — this project uses a named one):

- **`session_logs` collection** → a new document, named after your session id, should appear
  within a few seconds — containing the actual conversation you just had.
- **`dpm_profiles` / `teaching_memories` collections** → the document for your student id
  (`demo_student`, or your real uid if you signed in with Google) should show fields that
  changed based on what you actually discussed — not just the original seeded demo data.

### Step 6 — check Cloud Storage

Go to Cloud Storage → bucket **`nityam-506707-tutor-artifacts`** → `artifacts/` folder. If you
asked for a simulation in Step 2, you should see a new `<artifact_id>.json` file with a
timestamp matching your session.

### Step 7 — confirm Redis cleaned up after itself

```bash
redis-cli KEYS "session:*"
```
Should now be **empty** for that session — a successful flush clears the buffer behind it.

---

## Troubleshooting

**Nothing new shows up in Firestore after Step 5.**
Almost certainly Redis wasn't running when the session happened — check `redis-cli ping`
returns `PONG`. Without Redis, the flush fails silently with just a warning in the terminal
(search the backend's terminal output for `failed to flush session memory`).

**The terminal shows `failed to flush session memory` even with Redis running.**
Check the full traceback in the terminal (it's logged with `exc_info=True`) — most likely
causes are `NITYAM_AUTH` not pointing at working credentials, or Firestore's `smriti` database
being unreachable. Run `.venv/bin/python -m app.auth` to check credentials independently.

**`test_close_session_wiring` shows `RESOURCE_EXHAUSTED` in its output.**
That's Vertex AI Express Mode quota being temporarily exhausted from other testing, not a bug —
wait a few minutes and retry.

**You don't see anything in the GCS bucket even after asking for a simulation.**
Artifact generation takes ~30 seconds in the background — give it a moment after the tutor says
it's building one, then check the bucket again.
