# Handoff — Nityam frontend UI/UX overhaul (multi-phase)

**Written:** 2026-08-29, updated same day after a third round of work. **For:** whichever
session picks this up next. **Repo:** this one, branch `main`, HEAD `626a483` at the time of
writing.

## The one-sentence status

All five original sub-projects plus the landing page (originally deferred, now also done) have
real, working, committed progress on `main`; the one thing nobody has done yet is open a browser
and look at any of it — everything below was verified by build/type-check/test/curl, not by eyes
on a real page. **One command now brings up the whole connected system:** `cd backend && ./run.sh`
starts the backend, the main app, the landing page, and the Observatory together (`--no-landing`
/ `--no-observatory` to skip either).

## What the user actually asked for, and where each piece stands

1. **Tutor activity visibility** — done, merged, reviewed via the full subagent-driven-development
   process (spec: `docs/superpowers/specs/2026-08-29-tutor-activity-visibility-design.md`, plan:
   `docs/superpowers/plans/2026-08-29-tutor-activity-visibility.md`).
2. **Dashboard shows real student data** (profile, memory, interests) — done. New `/profile`
   screen (`frontend/src/features/profile/`) and the dashboard's own "Where you lose marks" /
   "Exam readiness" cards now read `backend/app/memory_routes.py`'s existing
   `GET /memory/sessions/{id}/state` endpoint (`frontend/src/lib/memory.ts`), with an honest empty
   state for a student with no session history yet — confirmed for real against the live backend
   and real Firestore (see "Verified against the real backend" below).
3. **Paste a YouTube link → Shruti → memory** — the real plumbing is built and smoke-tested, but
   a full successful run has **not** been executed (see the gap below — it needs credentials this
   session doesn't have). New backend endpoint `backend/app/shruti_routes.py` (`POST
   /shruti/ingest`, `GET /shruti/runs/{id}`) shells out to Shruti's real CLI as a background
   subprocess; new dashboard section `frontend/src/features/home/ShrutiIngest.tsx` pastes a link,
   embeds the video immediately, and polls real progress.
4. **Auth page + tagline** — done. Tagline "Learn the Way You Want" added under the wordmark
   (`frontend/src/features/auth/LoginScreen.tsx`); ink-underline focus treatment, `inputMode`,
   entrance fade.
5. **Textbook/canvas sizing** — done. Textbook peek 232→288px wide, 268→340px tall; notebook page
   920→1000px (`frontend/src/styles/tokens.css`, `TextbookPeek.module.css`).
6. **General "remove AI slop" / premium font+animation pass** — done at the token level, which the
   user explicitly authorized mid-session ("feel free to change the design system... make it look
   ultra premium"): a second brand accent (marigold, paired with the existing magenta), color-
   tinted multi-layer elevation shadows, a full step softer radii, a bigger display type size, a
   near-imperceptible global paper-grain texture, and a gradient/lift primary button — all in
   `frontend/src/styles/tokens.css` + `base.css` + `components/ui.module.css`, so it cascades to
   every screen without needing every individual component touched. See "What was NOT touched" below
   for the screens this cascade reaches passively vs. the ones nobody has gone back into by hand.
7. **`Nityam/` landing page** — originally deferred, later explicitly requested and now done. It
   had its own nested `.git` (no remote, 2 local commits) — absorbed into this repo as a plain
   directory since there was nothing to lose by doing so. Header's and Hero's primary CTAs now
   link to the real app's `/login` via `NEXT_PUBLIC_APP_URL` (`Nityam/app/lib/config.ts`,
   defaulting to `http://localhost:5173`); the "Learn the way you want" tagline was added as a
   handwritten hero accent; the waitlist section is now clearly framed for schools, with a
   separate "sign in and start now" path for individual students since those are genuinely two
   different funnels. `backend/run.sh` now spawns its dev server too (port 3001 by default).
   Verified live: `npm run build`/`lint` clean, and a real curl of the rendered HTML confirmed the
   login link actually resolves to the frontend app, not just that the source reads correctly.

## The one real gap: nobody has looked at a browser

Every change above was verified by `npm run build` (clean), the five non-browser test scripts
(`contract`/`kernels`/`grounding`/`reducer`/`specialists`, all passing), and direct `curl` smoke
tests against a live backend instance — not by loading the app in an actual browser. Two things
compound this:
- `frontend/tests/ui.mjs` (the one test that WOULD drive a real headless browser end-to-end)
  fails on this machine's Node v26.7.0 for a pre-existing, unrelated reason (see below) — it was
  never available as a check during any of this work.
- Two subagents doing pieces of the earlier tutor-activity-visibility sub-project could only
  smoke-test (build/serve/no-crash), not actually look at the rendered glow/chip/animation —
  that limitation carried forward informally into everything built in this second round too.

**Do this before considering any of the above finished:** `cd backend && ./run.sh`, sign in, and
actually look at: the login page (tagline, focus underline), the dashboard (profile data — likely
an empty state unless you've had a session or seed real memory data first; the Shruti section;
button/card visual treatment), `/profile`, and the session screen's textbook/canvas size. The
design-system token change in particular (richer shadows, bigger radii, gradient button, grain
texture) has never been rendered by anyone — it is exactly the kind of change that can look great
in theory and slightly off in practice (a shadow too heavy, a gradient banding oddly), and static
review of CSS values cannot catch that.

## Things this session learned that you should not have to re-derive

**Sub-project 2/3's data model, confirmed for real:** the memory endpoint works locally against
real Firestore (this environment has working `application-default` credentials — `curl`-verified,
not assumed), keyed by `student_id` = the Firebase UID (`user.uid` from `useAuth()` — confirmed by
reading `backend/app/main.py`'s websocket handler, which passes `user_id` straight through as
`student_id`). The endpoint's path segment is `{session_id}` but the fields a profile view wants
(`dpm_profile`, `teaching_memory`) are looked up by `student_id` alone server-side — a fixed
placeholder session id (`"_profile"`) gets you real profile data with no fake session invented.
As of this writing, the real `demo_student` account has **no** recorded weaknesses/interests yet
in Firestore (confirmed via live curl) — so don't be surprised if the dashboard's empty states are
what you see first; that's correct behavior, not a bug.

**Shruti (sub-project 3) is real plumbing, not a demo.** `POST /shruti/ingest` genuinely spawns
`uv run --env-file .env shruti ingest --url ...` in `sub_modules_examples/shruti/` and tails its
log. Confirmed live: it returns a `run_id` immediately, transitions to `failed` with the log tail
`"error: No environment file found at: .env"` because **`sub_modules_examples/shruti/.env` does
not exist in this checkout** (only `.env.example` does) — Shruti needs its own Gemini/Postgres/GCS
credentials, entirely separate from the main backend's `.env`, and until someone populates that
file, every real run will fail at that exact step. A Postgres container (`docker-postgres-1`, port
5434) is already running and was left over from earlier work — that part's ready; the credentials
file is the actual blocker. `yt-dlp` and `uv` are both present on this machine.

**Design system elevation was an explicit, mid-session user override.** Earlier guidance (baked
into the tutor-activity-visibility spec) was "the design system is already good, don't touch it."
The user later said, in so many words, to change it — "you are free to change the design system...
make it look ultra premium." The token changes reflect that instruction; if a future session
re-reads the old spec and concludes the design system shouldn't be touched, that's now stale — the
user's later, more specific instruction governs.

**The curly-apostrophe path gotcha, still real:** this machine has a near-duplicate stale directory
one level up from the repo root, differing only by a typographic vs. ASCII apostrophe in "Anmol's".
It bit multiple subagents during the first sub-project. If you dispatch any subagent against this
repo, create an ASCII-only symlink first and route every path through it.

**`tests/ui.mjs` still fails on this machine's Node v26.7.0**, unrelated to any of this session's
work (confirmed pre-existing by reproducing it with entire diffs stashed out, twice, across two
separate rounds of work). The other five `frontend/tests/*.mjs` scripts plus `npm run build` are
the real automated gate here until someone fixes or pins Node for that one test.

**Other sessions are concurrently editing this exact checkout.** As of this writing, unstaged
(uncommitted, not touched by this session) modifications exist in `backend/app/agents/board_agent.py`,
`specialist_runner.py`, `voice_agent.py`, `backend/app/canvas/tools.py`, `session_close.py`,
`textbook.py`, `textbook_index.json`, `backend/tests/test_canvas.py`, `test_specialist_runner.py`,
`frontend/scripts/build-textbook-index.mjs`, `frontend/src/lib/textbook.json`,
`frontend/src/features/session/CheckpointModal.tsx`, `SessionScreen.tsx`, and
`frontend/src/lib/live/useLiveSession.ts` — none of it from this session. This session never staged
or committed any of those files. Leave them alone; check with the user before touching
`SessionScreen.tsx`/`useLiveSession.ts`/`CheckpointModal.tsx` specifically, since someone else has
real in-progress work there right now.

## Where to find the full context

- `docs/superpowers/specs/2026-08-29-tutor-activity-visibility-design.md` and the paired plan —
  sub-project 1's full detail.
- `git log --oneline 645a5e9..de0818c` — every commit from this session, in order, with real
  commit-message detail on each.
- `sub_modules_examples/shruti/docs/HANDOFF_video_ingest_billing.md` — an earlier, separate
  handoff about a Gemini billing block on Shruti; check whether it's still relevant once someone
  populates `sub_modules_examples/shruti/.env`.
- `frontend_snippet_prompts.md` (repo root) — the React Bits/Magic UI/shadcn snippets used as
  inspiration for the design-system elevation; nothing was copied verbatim (this app has no
  Tailwind/shadcn — everything was translated into the existing plain-CSS-Modules architecture).

If something here turns out stale or wrong when you check it, trust what you observe over what's
written — this is a snapshot from one session, not ground truth.
