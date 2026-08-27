# Memory Storage Testbed

## Intent

Proves Firestore (structured records + native vector search), GCS (via ADK's
`GcsArtifactService`), and local Redis (standing in for Memorystore) as SMRITI's Google-managed
storage backends — standalone, before `sub_modules_examples/tutor/app/memory/store.py` is
rewritten to use them for real. Spec:
`docs/superpowers/specs/2026-08-27-memory-storage-testbed-design.md`. Research behind the
choices: `project_documentation/memory_nityam_architecture/google_cloud_storage_integration.md`.

## What was proven

- Firestore CRUD for chunk/profile/session_log-shaped documents, against the real
  `smriti-testbed` database.
- Firestore native vector search (`find_nearest`) correctly ranks a near-duplicate vector above
  an unrelated one, against a real vector index.
- `GcsArtifactService.save_artifact`/`load_artifact` round-trip a real object in
  `gs://nityam-506707-memory-testbed`.
- The Redis write-through pattern for the workflow tier: append, read back, clear, TTL.
- The full sequence end to end: seed + retrieve a grounding chunk, turns → Redis → session_log +
  profile update → Firestore → artifact → GCS → read-back. Run live against real resources both
  via `pytest` and via a manual `uv run python -m testbed.demo_end_to_end` invocation — the
  session log, profile, and artifact all round-tripped correctly, and the artifact is visible in
  the bucket at `gs://nityam-506707-memory-testbed/memory_storage_testbed/manual_demo_student/
  manual_demo_session/demo_artifact.txt`.

## What was NOT proven (open items, tracked in google_cloud_storage_integration.md §7)

- Compatibility with Shruti's real 3072-dim embeddings — this testbed used synthetic 1536-dim
  vectors throughout. The dimension conflict (Firestore's 2048 cap) is still open.
- Real Memorystore — local Redis stood in per the design decision in
  `google_cloud_storage_integration.md` §5.4. Validate against real Memorystore once there's a
  Cloud Run deployment to attach it to via VPC.
- Any behavior specific to the real `store.py`'s four actual schemas
  (`GroundingChunk`/`DPMProfile`/`TeachingMemory`/`SessionLog`) — this testbed used deliberately
  minimal standalone shapes (`testbed/schemas.py`: `Chunk`, `Turn`, `SessionLog`, `Profile`) to
  prove the storage *pattern*, not the exact production schema. (Named without a `Test` prefix
  deliberately — pytest treats classes named `Test*` as test classes to collect, which produced
  spurious collection warnings during implementation.)

## Porting into the real `store.py`

`firestore_store.py`'s functions mirror the real `store.py`'s functions 1:1 by name — porting is
close to: swap `Chunk`/`Profile`/`SessionLog` for the real
`GroundingChunk`/`DPMProfile`/`TeachingMemory`/`SessionLog`, point `connect()` at the real
project's Firestore database (not `smriti-testbed`, which stays this testbed's own), and resolve
the embedding-dimension question first (see google_cloud_storage_integration.md §3.3).

## Where to run things

```bash
cd sub_modules_examples/memory_storage_testbed
uv sync
uv run pytest -v                          # full suite, real cloud resources
uv run python -m testbed.demo_end_to_end  # manual run, prints each step's result
```

Requires: `gcloud auth application-default login` done once against project `nityam-506707`,
local Redis running (`brew services start redis`).

## Cloud resources this testbed uses (already provisioned, not created by this code)

- GCP project `nityam-506707`
- Firestore database `smriti-testbed` (Native mode, `us-central1`) — a named, non-default
  database, kept separate from whatever the real system creates in `(default)` later
- GCS bucket `gs://nityam-506707-memory-testbed`
- A composite vector index on `grounding_chunks.embedding` (dimension 1536), created via:
  ```bash
  gcloud firestore indexes composite create \
    --collection-group=grounding_chunks --query-scope=COLLECTION \
    --database=smriti-testbed \
    --field-config field-path=embedding,vector-config='{"dimension":"1536","flat":{}}' \
    --project=nityam-506707
  ```
