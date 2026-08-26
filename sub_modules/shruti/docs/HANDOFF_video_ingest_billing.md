# Handoff — Gemini API billing block on first real Shruti pipeline run

**Written:** 2026-08-26, by a prior Claude Code session. **For:** a fresh session with Google Cloud / billing tooling this session didn't have. **Repo:** this one, branch `shruti-implementation`, HEAD `83874f7`.

## The one-sentence problem

A first real end-to-end run of the Shruti video pipeline is fully built and ready, but every attempt fails on the very first live Gemini API call with `429 RESOURCE_EXHAUSTED — Your prepayment credits are depleted`, and the user's Google Cloud Billing account (linked, $150 available) does not appear to be resolving it despite purchasing Prepay credits.

## What's actually blocked, precisely

The Gemini Developer API (AI Studio / API-key auth, not Vertex) uses a **separate "Prepay" credit balance**, distinct from general Google Cloud Billing credit. Confirmed directly against `ai.google.dev/gemini-api/docs/billing` earlier this session:

> "Prepay users must purchase Prepaid credits before they can use any Google Cloud credits that are eligible for the Gemini API." / "Prepay credits apply only to Gemini API usage costs; you can't use them to pay for other Google Cloud services."

So a linked Cloud Billing account with real funds does **not** by itself unblock Gemini API calls — a separate Prepay purchase (minimum $10, via AI Studio's Billing page → "Buy credits") is required first.

**The user says they already did this purchase, and the error persists unchanged across three separate attempts, including one made specifically after the Prepay purchase.** This is the actual open question this handoff exists for — the fix isn't "buy Prepay credits," that's apparently already been tried. Something about *where* it was applied, or propagation, is still wrong.

### The specific project to check

The API key currently in `.env` (`GOOGLE_API_KEY`) belongs to GCP project **`782362848834`** — this project number came directly from the 403/429 error payloads' `consumer` field, not a guess. The leading hypothesis (unconfirmed): **the Prepay purchase may have gone to a different AI Studio/GCP project than 782362848834** — easy to do if the user has more than one project and the wrong one was selected in the AI Studio UI at checkout time.

**What to actually check, with real GCP tooling this session may have that the prior one didn't:**
1. Confirm which project(s) the user's Google account has access to, and which one(s) have a non-zero Gemini API Prepay balance.
2. Confirm project `782362848834` specifically is (or isn't) the one with funded Prepay credits.
3. If it's a different project that's funded: either (a) get billing sorted for `782362848834` specifically (transfer/re-purchase against the right project), or (b) generate a fresh API key from the *funded* project and swap it into `.env` (`GOOGLE_API_KEY=...`) — either fixes it, (b) is probably faster.
4. Also worth a plain sanity check: has enough time passed for a real propagation delay (rare but possible), and does the AI Studio billing page show the purchase as "completed" and not stuck in a pending/processing state?

## How to test whether it's actually fixed (cheap, ~$0.0001, real signal)

`models.list()` is **not** a valid test — it succeeds even with $0 Prepay balance (confirmed this session; it's a free metadata call). The only real test is an actual `generate_content` call:

```bash
cd "/Users/anmolsureka/Documents/Documents - Anmol’s MacBook Air/Nityam Prototype"
uv run --env-file .env python -c "
from google import genai
client = genai.Client()
try:
    r = client.models.generate_content(model='gemini-3.5-flash-lite', contents=['reply with just: ok'])
    print('generate_content OK -', repr(r.text)[:100])
except Exception as e:
    print('generate_content FAILED:', repr(e)[:500])
"
```
If this prints `generate_content OK`, billing is genuinely fixed — proceed to the real run below. If it still prints the same 429, it's still not resolved; don't bother running the full pipeline yet.

## Once billing is confirmed working: run the actual thing

Everything downstream of billing is already built. This is the entire remaining task:

```bash
cd "/Users/anmolsureka/Documents/Documents - Anmol’s MacBook Air/Nityam Prototype"
uv run --env-file .env python scripts/ingest_video.py .local/videos/d_jnEkwCA6I.mp4 --subject Physics --grade 11 --chapter "Projectile Motion"
```

- The video is already downloaded locally at `.local/videos/d_jnEkwCA6I.mp4` (11.6MB, 4:37, "From Zero to Genius: Learn Projectile Motion Visually!", channel "Invariant Physics" — YouTube id `d_jnEkwCA6I`).
- Postgres (pgvector) is already running in Docker (`docker-postgres-1`, port 5434) — confirm with `docker ps` first; if it's not up, `docker start docker-postgres-1` (or check `docker compose` config if that container's gone, but it existed and was healthy as of this session).
- `.env` already has `GOOGLE_API_KEY`, `GOOGLE_CLOUD_PROJECT`, `DATABASE_URL` set — don't need to recreate it, just possibly swap the key per the billing fix above.
- The script prints progress stage by stage (GATE → PULSE → SLATE+GLYPH → ECHO → POINT → WEAVE → ATLAS → embeddings → SUMMARY) and is deliberately defensive — SLATE/GLYPH failures don't kill the run, they're caught and logged under "Known gaps hit during this run" at the end.
- **Expect degraded SLATE/GLYPH results.** This video is produced/animated educational content (channel "Invariant Physics"), not a real camera-recorded classroom lecture with a physical blackboard and a teacher. Shruti's board-rectification stage (SLATE) is designed around a real physical board with occlusion from a teacher's body — it will run without crashing (falls back gracefully) but likely extract low-value or empty board content for this specific video. **This is expected, not a bug to chase.** The transcript-based extraction (ECHO → ATLAS: concepts, relations, misconceptions) doesn't depend on board quality and should be the real signal to look at.
- Just show the user everything the script prints — full transcript excerpts, concepts with citations, relations, misconceptions with the speaker's exact phrasing, and the final summary + gaps list. That's literally what they asked to see.

## What this script is, precisely (read `scripts/ingest_video.py`'s own docstring for full detail)

It's a **first-pass, hand-written orchestrator** — not a reviewed/tested Phase 0.5 implementation. No SDD process, no unit tests written for it specifically (though every stage function it calls does have its own unit tests, all passing — `uv run pytest -q` → 103 passed as of this session). It exists to prove the real stage functions can be composed end-to-end against a real video and produce real output, not to be the final, hardened Phase 0.5 orchestrator. Deliberate simplifications, documented in its own docstring:
- SLATE/GLYPH treat the whole video as one board-state span rather than windowing by erase events into multiple spans.
- POINT (deixis) is capped at 6 utterances to bound API cost.
- Misconception `concept_id` grounding is fuzzy-matched after the fact (via `difflib`) because `mine_misconceptions` doesn't receive the mined concept list and can hallucinate an id that doesn't exist — a real upstream gap, not something this script silently hides (it logs every dropped misconception under "Known gaps").

**Along the way, this session found and fixed several real, pre-existing bugs in the core `shruti/` stage functions** (not just this script) — these are genuine fixes needed for ANY real run, not exploratory-script workarounds:
- `admit()` was calling `classify_surface(client, frames=[])` — always empty frames, so surface classification was a blind guess with zero image content. Fixed to sample real frames.
- `transcribe_audio`, `resolve_deixis`, `read_board_state` were passing raw file paths / numpy arrays directly as Gemini `contents` — the SDK doesn't accept those as media; they'd either error or (worse) get silently treated as extra prompt text. Fixed to use `client.files.upload()` for audio and `types.Part.from_bytes(...)` for images.
- None of `transcribe_audio`, `resolve_deixis`, `fuse_beats`, `read_board_state`, `mine_concepts`, `extract_relations`, `mine_misconceptions` set `response_mime_type: "application/json"` on their Gemini calls — meaning the model would likely wrap JSON output in markdown fences and `json.loads()` would fail. Fixed by adding `config={"response_mime_type": "application/json"}` to each. This is exactly the failure mode `shruti/gemini/client.py`'s own code comment already warned about ("relation-extraction F1 collapsing 76% → 18% without format enforcement") — it just wasn't applied consistently across the actual stage functions.

Corresponding test files were updated to match (real numpy frames instead of placeholder `bytes`, a mocked `files.upload`, and assertions checking proper `Part` encoding instead of raw-bytes passthrough). Full test suite passes: `uv run pytest -q` → 103 passed, 0 failed.

## Repo state — nothing here is committed yet

```
git status --short
```
shows (as of HEAD `83874f7`):
```
 M .gitignore                                  (added .local/ — gitignore for downloaded video/scratch work)
 M shruti/stages/atlas/concepts.py              (JSON mime-type fix)
 M shruti/stages/atlas/misconceptions.py        (JSON mime-type fix)
 M shruti/stages/atlas/relations.py             (JSON mime-type fix)
 M shruti/stages/echo/transcribe.py             (real audio upload + JSON mime-type fix)
 M shruti/stages/gate/admit.py                  (real frame sampling for classify_surface)
 M shruti/stages/glyph/read.py                  (real image encoding + JSON mime-type fix)
 M shruti/stages/point/deixis.py                (real frame encoding + JSON mime-type fix)
 M shruti/stages/weave/fuse.py                  (JSON mime-type fix)
 M tests/stages/echo/test_transcribe.py         (updated to match)
 M tests/stages/glyph/test_read.py              (updated to match)
 M tests/stages/point/test_deixis.py            (updated to match)
?? scripts/ingest_video.py                      (new — the orchestrator)
?? memory_nityam_architecture/                  (pre-existing wiki, untracked from an earlier session)
?? shruti_implementation_plan_phase0.md         (pre-existing plan doc, untracked from an earlier session)
```
**Do not discard any of this.** The stage-function fixes are real bug fixes needed regardless of this specific run; `scripts/ingest_video.py` is real, working orchestration code. Whether/how to commit is the user's call (this session was explicitly instructed not to commit without being asked, and that instruction should carry forward) — ask before committing if it hasn't come up.

## Where to find the full context if you need it

- `memory_nityam_architecture/README.md` — the architecture wiki index; its "Where Shruti fits" and "Known gaps for Phase 0.5" sections are directly relevant.
- `shruti_implementation_plan_phase0.md` — the plan that produced the citation/provenance/embedding work this run depends on (already committed, HEAD `83874f7` is its final state after a full SDD review cycle).
- `shruti_platform_alignment.md` and `shruti_architecture.md` (repo root) — the original SHRUTI design docs.

If something in this handoff turns out stale or wrong when you check it, trust what you observe over what's written here — this is a snapshot from one session, not ground truth.
