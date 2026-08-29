# Tutor activity visibility — design

Status: approved, ready for implementation plan
Date: 2026-08-29

## Context

This is sub-project 1 of a larger, user-requested UI/UX pass across the student-facing
app (`frontend/`). The full request was decomposed into five sub-projects, each getting
its own spec → plan → implementation cycle:

1. **Tutor activity visibility** (this document) — the live session screen should show,
   in a learning-appropriate way, what the tutor is doing when she delegates to a
   specialist (writing on the board, checking the textbook, preparing a quiz question,
   building a simulation) — the equivalent of the tool-call visibility a coding agent
   gives you, reframed for a learner.
2. Dashboard/profile real-data wiring — replace `HomeScreen`'s hardcoded demo data
   (`frontend/src/lib/data.ts`) with the backend's existing read-only memory endpoints
   (`GET /memory/sessions/{id}/state`, `.../events`), and add a "My learning" view
   surfacing interests, mastery, open doubts, and session history.
3. Shruti pipeline dashboard integration — a "paste a YouTube link" flow on the
   dashboard that triggers the existing (CLI-only, credentials- and infra-heavy)
   Shruti ingest pipeline via a new, isolated backend endpoint, with progress and a
   results viewer (video + extracted markdown + concepts). Explicitly the largest and
   riskiest sub-project (new backend surface, background job, and the pipeline is
   currently billing-blocked per its own docs) — scoped separately.
4. Auth screen restyle + new tagline ("Nityam — Learn the Way You Want").
5. Textbook-peek and canvas/board sizing + motion polish on the session screen.

The `Nityam/` Next.js landing page redesign is explicitly deferred by the user's own
request and is not part of this decomposition.

**Reality check that shaped this spec:** the app's existing design system
(`frontend/src/styles/tokens.css`, `frontend/src/components/ui.tsx`) is already a
deliberate, considered "exercise-book" design language — not generic AI-template
output. The real gap this sub-project closes is not visual polish but a genuine
missing feature: the backend already streams which specialist is active
(`ask_board` / `ask_artifact` / `ask_quiz` / `ask_textbook`, each carrying the tutor's
own spoken "bridge" line as a required argument), and the frontend today reads the
specialist's name off that event and discards it, collapsing all four into one
generic "thinking" indicator. No backend or agent-logic changes are required for this
sub-project.

## Goals

- When the tutor delegates to a specialist, the student sees a friendly, specific cue
  ("Sketching it on the board…", "Checking the textbook…") instead of a generic
  "Looking that up for you…".
- The cue is spatially connected to where the result will appear — a brief highlight
  on the board/canvas, the textbook peek, or the concept/plan strip — so the student
  learns where to look, not just that something is happening.
- Zero backend or agent-logic changes.
- Zero new dependencies — stay within the codebase's existing plain-CSS, no-animation-
  library discipline (confirmed via `frontend/package.json`: no motion/animation
  library is present today).
- Graceful degradation: an unrecognized specialist (a future fifth `ask_*` tool) must
  fall back to today's generic behavior, never crash or show broken text — this exact
  failure mode broke the app once already when `ask_tutor` was split into four tools.

## Non-goals

- No changes to `backend/app/agents/*`, `specialist_runner.py`, or the wire protocol.
- No new floating UI element competing with the avatar/speech bubble for attention
  (rejected as Approach B during brainstorming).
- No redesign of the board, textbook drawer, or avatar themselves — only an additive
  highlight state on top of what exists.

## Design

### Architecture

One new field, `specialist`, rides alongside the existing `thinking` and `bridge`
state in `frontend/src/lib/live/useLiveSession.ts` — same lifecycle, set when a
matching `ask_*` function call arrives and cleared in the exact same three places
`thinking`/`bridge` already clear today (`turnComplete`, `interrupted`,
`functionResponse`). `SessionScreen` already destructures `tutor` from this hook and
passes pieces of it to its children as plain props; `specialist` joins that same
plumbing. No context provider, no new store — the component tree is a single shallow
parent (`SessionScreen`) that already owns every sibling that needs this signal.

### Components

- **New file** `frontend/src/lib/live/specialists.ts`:
  - `type Specialist = "board" | "artifact" | "quiz" | "textbook"`
  - `resolveSpecialist(toolName: string): Specialist | null` — a pure function
    (no React, no hook state) wrapping the `ask_board` → `"board"`,
    `ask_artifact` → `"artifact"`, `ask_quiz` → `"quiz"`, `ask_textbook` →
    `"textbook"` mapping, returning `null` for anything else. Pulling this out as
    a pure function (rather than an inline map read inside the hook) is what
    makes it unit-testable the same cheap way `boardReducer` already is, with no
    hook-testing infrastructure.
  - `SPECIALIST_COPY: Record<Specialist, { glyph: string; verb: string }>` — the
    fallback phrase shown only when the tutor's own `bridge` line is absent. Glyphs
    reuse the app's existing vocabulary instead of emoji (which would clash with this
    design system and reads as a generic/templated tell): `textbook` reuses `▦`
    (already "View textbook" / "Open ▦" in `TextbookPeek`), `quiz` reuses `▤` (already
    a source/reference chip glyph in `HomeScreen`), `board` reuses `✎` (already the
    marker tool glyph in `SessionControls`), `artifact` gets one new glyph, chosen
    during implementation to avoid colliding with any existing tool glyph, and uses
    the `--sim` color token (`tokens.css` already reserves this "for simulations
    only — matches artifact_generator").
- `useLiveSession.ts`: in the existing `ask_`-prefix matching block, keep
  `part.functionCall.name`, resolve it through `resolveSpecialist()` (`null` for an
  unrecognized name — see Error handling), and add `specialist` to the hook's
  returned state, cleared alongside `thinking`/`bridge`.
- `SessionControls.tsx`: accepts a new `specialist` prop; the existing three-dot
  "thinking" row prefixes the fallback phrase with the specialist's glyph and uses
  `SPECIALIST_COPY[specialist].verb` instead of the single hardcoded string, only
  when `bridge` is absent — the tutor's own words still win when present, per the
  existing design rationale in that file's comments.
- Three existing surfaces gain an additive, class-toggled highlight while their
  specialist is active, all clearing the moment `thinking` clears:
  - `SessionScreen.module.css`'s `.stage` (the board/canvas area) — soft edge glow
    while `specialist` is `"board"` or `"artifact"`, using `--accent`/`--e-accent`
    for board and `--sim`/`--sim-wash` for artifact, on the existing `--ease` timing
    curve already used throughout this file.
  - `TextbookPeek.module.css`'s `.peek` — a glow/pulse variant reusing the same
    visual language as its existing hover-lift (`--e-lift`), active while
    `specialist === "textbook"`.
  - `SessionScreen.module.css`'s `.concept` strip — a small "preparing a question"
    cue near the plan steps while `specialist === "quiz"`.
  - All transitions run ~150–250ms, consistent with existing durations in these
    files, and collapse to an instant, non-animated state change under
    `prefers-reduced-motion: reduce` — matching the pattern already used in
    `TextbookPeek.module.css` and elsewhere in this codebase.

### Data flow

Websocket event arrives → `useLiveSession`'s message handler matches
`part.functionCall.name.startsWith("ask_")` → resolves `specialist` via
`resolveSpecialist()` → sets `thinking = true`, `bridge = args.bridge?.trim()`,
`specialist = resolved` → all three flow to `SessionScreen` via the existing `tutor`
object → `SessionScreen` passes `specialist` to `SessionControls` (copy) and computes
three derived booleans (`board/artifact active`, `textbook active`, `quiz active`)
passed to the stage wrapper, `TextbookPeek`, and the concept strip. Clearing happens
in the same `turnComplete` / `interrupted` / `functionResponse` branches that already
clear `thinking` and `bridge` today — no new lifecycle to reason about.

### Error handling

- An `ask_*` call whose name `resolveSpecialist()` doesn't recognize (a future
  fifth specialist) resolves to `specialist = null`: the generic "Looking that up for
  you…" phrase still shows, no spatial glow fires anywhere, and nothing crashes or
  shows `undefined`. This is the exact failure mode a comment in
  `useLiveSession.ts` already documents as having broken the app once (when the
  single `ask_tutor` tool was split into four and no branch matched).
- Missing `bridge` always falls back to `SPECIALIST_COPY[specialist].verb` — never
  blank text.
- The three spatial highlights are purely additive CSS classes on already-rendered
  elements: if `specialist` is `null`, nothing renders differently, so there is no
  new failure surface beyond "the enrichment doesn't show."

### Testing

- Confirmed during research: no existing test touches `thinking`, `bridge`, or
  `functionCall` handling today — `frontend/tests/reducer.mjs` covers only the
  unrelated board-patch reducer (`notebookReducer.ts`). This sub-project adds new
  coverage, not an extension of existing coverage.
- New file `frontend/tests/specialists.mjs`, following the exact same no-browser,
  no-build-step pattern as `reducer.mjs` (transpile the `.ts` source with the
  `typescript` package already a dependency, import it as a data URL, run plain
  assertions), covering: `resolveSpecialist()` for all four known `ask_*` names;
  an unrecognized name resolving to `null`; every `Specialist` value has a
  `SPECIALIST_COPY` entry. This is possible with no hook-testing infrastructure
  specifically because `resolveSpecialist()` is a pure function, not something
  read inline off hook state.
- Add this new file to the `test` script in `frontend/package.json` alongside the
  other `node tests/*.mjs` invocations.
- Manual verification in the app's existing mock mode (`tutor.mode === "mock"`,
  already surfaced in `SessionScreen`'s header) to visually confirm all four
  specialists produce distinct, correctly-timed, correctly-clearing cues without
  needing live Gemini credentials.

## Files touched

- `frontend/src/lib/live/specialists.ts` (new)
- `frontend/src/lib/live/useLiveSession.ts`
- `frontend/src/features/session/SessionControls.tsx` (+ `.module.css`)
- `frontend/src/features/session/SessionScreen.tsx` (+ `.module.css`)
- `frontend/src/features/session/TextbookPeek.module.css`
- `frontend/tests/specialists.mjs` (new)
- `frontend/package.json` (`test` script gains the new test file)

No files under `backend/` are touched by this sub-project.
