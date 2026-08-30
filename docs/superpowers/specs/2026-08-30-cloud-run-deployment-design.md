# Cloud Run deployment — Design

Status: approved in chat via brainstorming Q&A (2026-08-30). Ready for an implementation plan.

**Supersedes nothing — extends `deployment.md`.** That document (repo root, dated before this
session's Shruti integration work) already settled the base architecture through real, cited
research: one container for the backend+frontend, Cloud Run WebSocket flags, Memorystore setup,
and the finding that Firestore/GCS/Firebase Auth need zero code changes under Cloud Run's ADC.
None of that is redone here. This spec covers exactly what `deployment.md` couldn't have covered
yet: **Shruti's ingest pipeline**, which didn't exist as a live feature when it was written, plus
the three scope decisions made in this session's brainstorm.

## 1. Decisions settled this session

- **Region: `us-central1`** for the Cloud Run service, the Cloud Run Job, and Memorystore (all in
  the same region — required for Direct VPC egress to reach Memorystore's private IP, and to keep
  Job→Service latency low on every sync webhook call).
- **`--min-instances=1`** on the main backend service. This is student-facing; a cold start landing
  mid-WebSocket-handshake is not acceptable, per `deployment.md` §4's own reasoning.
- **Manual deploy only for this pass** — no CI/CD. `deployment.md` §10 already scoped this out;
  reconfirmed here rather than silently expanded.
- **Shruti's ingest runs as a Cloud Run Job, not inside the main service.** This was a real,
  researched decision, not a default — see §2.

## 2. Why Shruti needs its own deployment shape (the gap `deployment.md` didn't cover)

Today, `POST /shruti/ingest` (`backend/app/shruti_routes.py`) spawns a `threading.Thread` that
shells out to `uv run shruti ingest ...` and keeps running *after* the HTTP response has already
returned. Confirmed directly against Google's own Cloud Run docs and engineering blog posts: Cloud
Run's default billing model allocates CPU **only during active request processing** — "the moment
the response is sent, CPU gets throttled," and background threads/timers "essentially freeze
between requests," only resuming when unrelated traffic happens to hit that same instance. Deployed
as-is, a real 10-20 minute ingest would stall indefinitely rather than running to completion. This
is not a hypothetical edge case — it is exactly what the current code does on every single ingest
call.

Two fixes exist; Cloud Run Jobs was chosen over `--no-cpu-throttling` on the main service because:

- Cloud Run Jobs are Google's purpose-built primitive for "runs to completion, no request served,
  needs full CPU throughout" — confirmed via Google's own docs: no CPU-throttling concern at all
  (a Job's task gets full CPU for its whole execution by design), task timeout configurable up to
  168 hours (Shruti's ~20-minute ceiling is nowhere close), billed only for actual execution time.
- It isolates Shruti's heavy, separate toolchain (its own `uv`-managed Python env, `yt-dlp`,
  `ffmpeg`, `deno`, `opencv`/`numpy`/`asyncpg`) into its own image, instead of bloating the
  always-warm, `min-instances=1` main service image with dependencies it only needs occasionally.
- It completes a design decision this session already made and deliberately deferred: the original
  memory-integration spec (`2026-08-28-cloud-memory-and-shruti-integration-design.md` §4) called
  for an HTTP webhook with Cloud Run service-to-service auth specifically for when "Shruti and
  Nityam aren't co-located" — and simplified it to an in-process call for local dev, explicitly
  flagging that as "a small lift to put behind a real endpoint later once/if Shruti ever becomes a
  separately deployed service." A Cloud Run Job *is* that separately-deployed state. §4 below is
  that webhook, built now instead of deferred again.
- The alternative (`--no-cpu-throttling` on the main service) needs zero code changes but bills for
  continuously-allocated CPU across the *entire* always-on service for a feature used occasionally,
  and keeps Shruti's heavy dependencies inside the hot-path image. Rejected for this pass on cost
  and image-hygiene grounds, not because it wouldn't work.

## 3. The two images

**`nityam-backend` (Cloud Run Service)** — multi-stage build per `deployment.md` §3 (Node stage
building `frontend/dist`, Python stage serving it via `main.py`'s existing static mount), deployed
with the WebSocket-critical flags from `deployment.md` §4 (`--timeout=3600`, `--session-affinity`,
HTTP/2 left disabled, sized `--concurrency`/`--memory`/`--cpu`) plus `--min-instances=1`
(§1) and Direct VPC egress + `REDIS_HOST`/`REDIS_PORT` for Memorystore (`deployment.md` §5).

**`nityam-shruti-job` (Cloud Run Job)** — a separate image built from
`sub_modules_examples/shruti/`, containing Shruti's own `pyproject.toml`/`uv.lock`-managed
dependencies plus `yt-dlp`, `ffmpeg`, and `deno` (the credential/`PYTHONPATH` fix already in
`backend/app/shruti_routes.py::_subprocess_env()` stays relevant even here — the Job's entrypoint
runs the same `shruti ingest` command). The Job needs its own outbound network access to YouTube
and Gemini (no VPC egress restriction required, unlike the main service, since it never touches
Memorystore) and its own connection to Shruti's Postgres.

**Shruti's Postgres**: not covered by `deployment.md` at all (it only ever ran as a local Docker
container, `docker-postgres-1`). This spec's open item — needs a managed equivalent (Cloud SQL for
Postgres with the `pgvector` extension, since Shruti's schema requires it per its own `docker/`
setup) provisioned in the same VPC, with the Job connecting via the Cloud SQL Auth Proxy sidecar
pattern Cloud Run Jobs support natively. Sizing/tier is an implementation-plan detail, not a design
fork — smallest available tier is almost certainly sufficient given Shruti's own light query
pattern (a handful of inserts per ingest run, no serving traffic).

## 4. The sync webhook — reviving spec §4, built for real this time

Currently `shruti_sync.sync_ingested_recording()` runs in-process, called directly by
`shruti_routes.py`'s `_run_worker` after the local subprocess exits, because Shruti and Nityam
share a filesystem and a process today. Once Shruti runs as a separate Cloud Run Job, that
assumption breaks — the Job's own container has no access to the backend service's Firestore
client call, and no shared filesystem to hand off a result through informally.

**New endpoint: `POST /admin/sync-grounding` on the Nityam backend.**

- **Request body**: `{student_id, recording_slug, concept_ids, subject, video_title, youtube_url}`
  — exactly `shruti_sync.sync_ingested_recording()`'s existing parameters, just arriving over HTTP
  instead of a direct function call. The wiki content itself is *not* sent in the body — the Job
  and the backend service both need read access to the same underlying content only if co-located;
  since they won't be, **the Job pushes the wiki markdown for each touched concept in the request
  body too** (`{concept_id, wiki_markdown}` per concept), and `shruti_sync.py`'s `parse_wiki_file`
  gets a second entry point that parses markdown text directly rather than only reading from a
  `Path` — a small, additive change, not a rewrite (the existing `Path`-based signature stays for
  any remaining local/dev callers, e.g. `scripts/seed_demo_data.py`).
- **Auth**: the Job's attached service account (`nityam-shruti-job-sa`, new) requests an ID token
  audienced to the backend service's own URL via `google.oauth2.id_token.fetch_id_token()` — Cloud
  Run Jobs get this from the metadata server for their attached SA, same mechanism as Services.
  Sent as `Authorization: Bearer <token>`. **Verified at the application level inside the FastAPI
  handler** (`google.oauth2.id_token.verify_oauth2_token(token, requests.Request(),
  audience=BACKEND_SERVICE_URL)`, then checking the token's `email` claim equals
  `nityam-shruti-job-sa@PROJECT_ID.iam.gserviceaccount.com`) — **not** Cloud Run's platform-level
  IAM invoker check, because the main service must stay "allow unauthenticated" for real student
  traffic (browsers, the WebSocket), and Cloud Run's IAM enforcement is all-or-nothing per service.
  This mirrors `app/user_auth.py`'s existing pattern for verifying Firebase ID tokens (same
  library family, different issuer/audience) — not a new verification style for this codebase.
- **What it does**: exactly what `shruti_sync.sync_ingested_recording()` already does (write
  `grounding_chunks`, `current_topic`, `topic_history`) minus the filesystem read, since the
  content now arrives in the request body.

**The Job's own entrypoint** replaces `shruti_routes.py`'s `_sync_after_ingest()` (log-scraping the
`SHRUTI_RESULT_JSON:` marker line from a co-located subprocess) with: after `shruti ingest`
completes inside the Job's own container, read the touched concepts' wiki files directly (still
local to *that* container, just not to the backend's), and POST them to `/admin/sync-grounding`
before the Job exits. `shruti/cli.py`'s existing `SHRUTI_RESULT_JSON:` stdout line stays exactly as
it is — it's what the Job's own entrypoint script parses to know which concepts to read and POST,
same mechanism, one hop moved.

**Triggering the Job**: `POST /shruti/ingest` changes from spawning a local subprocess to calling
`google.cloud.run_v2.JobsClient().run_job(name="projects/PROJECT_ID/locations/us-central1/jobs/nityam-shruti-job")`
with the ingest parameters passed as the Job execution's environment variable overrides
(`RunJobRequest.overrides.container_overrides[].env`). **Polling** (`GET /shruti/runs/{run_id}`)
changes from reading an in-process `_runs` dict to querying the Execution's status via the same
client (`JobsClient.get_execution()` / listing tasks) — `run_id` becomes the Execution's resource
name rather than a locally-minted UUID. Video-title resolution (the oEmbed lookup) and the
per-student `student_id` requirement (this session's earlier work) are unaffected — both already
happen before the trigger, in `start_ingest()`.

## 5. Service accounts (extends `deployment.md` §6)

Two now, not one:

- **`nityam-backend-sa`** (as `deployment.md` §6 already specifies) — `roles/datastore.user`,
  `roles/storage.objectAdmin` scoped to the artifacts bucket. **New addition**: `roles/run.developer`
  (or the narrower `roles/run.invoker` + explicit job-execution permission — implementation-plan
  detail) so the backend service can call `JobsClient.run_job()` to trigger Shruti.
- **`nityam-shruti-job-sa`** (new) — needs outbound access to Gemini (via whatever auth mode the
  main app uses, §6 of `deployment.md` already covers this identically), `roles/cloudsql.client`
  if Cloud SQL Auth Proxy is used for Postgres, and **no Firestore/GCS role at all** — it never
  talks to those directly; everything it produces goes through the authenticated webhook in §4,
  which is the enforcement point, not a broader IAM grant.

## 6. A real gap, flagged but not fixed in this pass

Checked directly: `frontend/src/lib/live/session.ts`'s WebSocket `onclose` handler only sets
`connected: false` — there is no reconnect attempt anywhere in the client. Locally, this has never
mattered (a laptop running `./run.sh` doesn't recycle the process mid-session). On Cloud Run, an
instance being recycled mid-session (a new revision deploying, `--min-instances` churn, a rolling
update) is a normal, expected event — and today it would silently end a student's live session with
no attempt to resume. `deployment.md` §4 already flagged this as "worth checking... not fixing here
— this is research only." It's now confirmed as real, not just plausible. **Explicitly out of scope
for this deployment pass** (it's a frontend resilience feature, not deployment configuration) —
flagged here so it isn't mistaken for an oversight, and worth its own bounded fix afterward.

## 7. Explicitly out of scope (unchanged from `deployment.md` §10)

CI/CD, the SMRITI Observatory's own deployment, custom domain mapping, Agent Runtime as an
alternative target, and the load-testing pass in `deployment.md` §9 — all still deferred, for the
same reasons already stated there.

## 8. Deployment order — supersedes `deployment.md` §8

1. Enable remaining APIs: `redis.googleapis.com`, `secretmanager.googleapis.com`,
   `sqladmin.googleapis.com` (new, for Shruti's Postgres). Already enabled: `run`, `firestore`,
   `artifactregistry`, `storage`.
2. Create both service accounts (§5) and grant their roles.
3. Create the Memorystore instance (`deployment.md` §5) and the Cloud SQL Postgres instance (§3)
   for Shruti, same region/VPC.
4. Build and push both images (§3) to a new Artifact Registry repo (none exists yet).
5. Deploy the Cloud Run Job (Shruti) first — the backend service's trigger call needs it to exist.
6. Add the `/admin/sync-grounding` endpoint (§4) and the Job-trigger/poll changes to
   `shruti_routes.py` before building the backend image in step 4 — ordering note, not a separate
   step: this is application code, written and tested before either image is built.
7. Deploy the Cloud Run Service with all the flags from `deployment.md` §4 + §1's decisions here.
8. Verify: `/health`, a real end-to-end WebSocket session, and a real end-to-end Shruti upload
   (trigger the Job, confirm `/admin/sync-grounding` lands the concepts in Firestore).
