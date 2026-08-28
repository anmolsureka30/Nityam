# Redis / Memorystore — current state and production plan

Status: local-only, by deliberate choice (2026-08-28). This is the short, action-oriented
version — full research and the reasoning behind choosing Memorystore at all lives in
`google_cloud_storage_integration.md` §5, which this file does not repeat.

## What's true right now

- The workflow-tier turn buffer (`backend/app/memory/short_term.py`) writes through to a
  **local** Redis (`redis-server` on `localhost:6379`) during development.
- **Nothing has been provisioned in Google Cloud for this yet** — confirmed directly against
  the `nityam-506707` project this session, not assumed:
  - The `redis.googleapis.com` API is not enabled on this project.
  - No Memorystore instance exists.

## Why local-only for now, specifically

Memorystore bills for the **instance existing**, not for what it actually does — roughly
$0.049/GB-hr on the Basic tier, running whether or not anything ever reads or writes to it.
That's a different cost shape from everything else in this stack: Firestore and Cloud Storage
only bill per read/write/byte, so they cost nothing when idle. Provisioning Memorystore before
this is actually being deployed would mean paying a constant cost for zero benefit. Deferred
until the app is actually going to production, not because Memorystore is the wrong choice —
the choice itself (Memorystore over alternatives) is already settled, see the research doc.

## What "production" means for this piece

**Google Cloud Memorystore** — Google's own hosted Redis (or its newer Redis-API-compatible
sibling, Memorystore for Valkey; either works unchanged). Same wire protocol, same
`redis.asyncio` client code already in `short_term.py` today — deploying this is an environment
variable change, not a code change.

Already true today, confirmed this session, so these need no new setup when the time comes:
- A VPC network already exists on this project: `default` (42 subnets, `us-central1` region
  used throughout this project).
- The deploy target is Cloud Run — decided during the memory-migration design, see
  `docs/superpowers/specs/2026-08-28-cloud-memory-and-shruti-integration-design.md` §2 (Cloud
  Run fits this app's shape — a custom FastAPI service with a raw WebSocket route and static
  frontend hosting — where Vertex AI Agent Engine's managed-API model does not).

## Exact steps, when it's time to deploy

1. **Enable the API:**
   ```bash
   gcloud services enable redis.googleapis.com --project=nityam-506707
   ```

2. **Create the instance** (Basic tier: no failover, cheapest — upgrade to Standard/HA later
   only if this needs to survive a zone outage; 1GB is generous for a single turn-buffer
   workload at this project's scale):
   ```bash
   gcloud redis instances create nityam-turns \
     --project=nityam-506707 \
     --region=us-central1 \
     --network=default \
     --tier=basic \
     --size=1
   ```

3. **Get its private IP** once created (Memorystore has no public IP by design — this is the
   only address that will ever reach it):
   ```bash
   gcloud redis instances describe nityam-turns \
     --project=nityam-506707 --region=us-central1 --format="value(host)"
   ```

4. **On the Cloud Run service, enable Direct VPC egress**, pointed at the `default` network's
   subnet in `us-central1`. This is Google's current recommendation over the older Serverless
   VPC Access connector (lower latency, lower cost) — it's what lets a Cloud Run container
   reach a VPC-internal-only private IP at all.

5. **Set the Cloud Run service's environment variables:**
   ```
   REDIS_HOST=<the private IP from step 3>
   REDIS_PORT=6379
   ```
   Nothing else changes. `backend/app/config.py` already reads exactly these two variables
   with sane localhost defaults, and every call site in `short_term.py` already goes through
   that same config — no code touches this file at deploy time.

## Cost, concretely

Basic tier, 1GB, running 24/7: roughly $0.049/hr × 24 × 30 ≈ **$35/month**, as a fixed line
item regardless of usage — budget for it that way, not like the usage-based Firestore/GCS costs
elsewhere in this stack.

## What this file deliberately does not cover

- *Why* Memorystore over Vertex AI Vector Search, Agent Search, or a self-hosted alternative —
  `google_cloud_storage_integration.md` §5 and §1.
- The write-through-mirror design (why this isn't a full ADK `SessionService` swap) —
  `google_cloud_storage_integration.md` §5.2.
- Anything about Firestore or Cloud Storage — see the same research doc's §3 and §4; those are
  already deployed and running (Firestore is live today; the GCS bucket
  `nityam-506707-tutor-artifacts` already exists and is in use).
