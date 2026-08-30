# `frontend` — the product

The real Nityam front end. React + TypeScript + Vite, built from
`Nityam_Claude_Design/Nityam.dc.html`.

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # dist/
npm run test       # drives the built app in headless Chrome
```

## The screens

| Route | What it is |
|---|---|
| `/` | Student home. Today's class, the three things to act on, weak areas. |
| `/intensity/:conceptId` | "How long do you have tonight?" — the plan is built to fit. |
| `/session` | The session. Full-width canvas, the tutor standing in the corner. |
| `/readiness` | Exam readiness, worst concept first. |
| `/summary` | What moved, and what happens in class tomorrow. |
| `/teacher` | Today's class: understanding, shared misconception, board time. |
| `/teacher/intervene` | Who needs two minutes before tomorrow. |
| `/teacher/insights` | One thing to know, one thing to do. |

The role switch in the header is on every screen, because the two dashboards are
one product seen from two sides.

## Layout

```
src/
├── styles/
│   ├── tokens.css        every colour, face and radius — change values here
│   └── base.css          reset, fonts, shared utilities, keyframes
├── lib/
│   ├── types.ts          the domain model
│   ├── data.ts           all demo content. The backend replaces THIS file.
│   ├── kinematics.ts     the projectile kernel (hand-written physics)
│   ├── grounding.ts      gesture → ContextPacket: the swept text and its block
│   └── tutorScript.ts    the tutor's replies — the ADK seam
├── components/           Shell, TeacherShell, and shared primitives
└── features/<screen>/    one folder per screen, CSS modules alongside
```

No component hardcodes content. Everything comes from `lib/data.ts`, so wiring
real endpoints is a change to that file and its callers.

## The session layout

The canvas is the page. It spans the full window, and **every control floats
over it** — there is no side panel taking width from the thing the student is
reading.

```
┌──────────────────────────────────────────────────────────┐
│ header · concept · mastery · progress through tonight     │
├──────────────────────────────────────────────────────────┤
│                                            ┌───────────┐ │
│  the notebook, full width                  │  bubble   │ │
│  prose capped at 74ch                      └─────▼─────┘ │
│  figures use the whole sheet                             │
│                                                  ╭─────╮ │
│  ┌─ you marked ─┐                                │ she │ │
│  ╰ tools · ask · mic · end ╯                     ╰─────╯ │
└──────────────────────────────────────────────────────────┘
```

Two things that look like details and are not:

- **The page runs the full width, and she stands in front of it.** No z-index
  can rescue content behind her, so the honest fix is scroll room: the notebook
  reserves `avatar height + 96px` of bottom padding, which means anything she
  covers can always be scrolled out from under her. Both sides read the avatar's
  footprint from the same `--avatar-h`, so they cannot drift.
- **The bubble sits above her head, not beside her.** Beside her there is only
  notebook, and a bubble there covers the figure she is talking about.
- **The bubble minimises.** Even above her head it can land on a readout, so the
  minus at its top-left folds it into a small thought cloud over her hair;
  clicking the cloud brings the words back. Minimising is a preference, not a
  dismissal — she keeps talking, and the cloud goes accent-coloured to admit
  that something new was said rather than silently swallowing it.

## The avatar

`lib/avatar/` is `sub_modules_examples/avatar/runtime/` — rig, emotion engine,
speech engine, mount. Two deliberate divergences from the module, and nothing
else:

1. The IIFE in each file receives a local namespace instead of `window.Nityam`.
2. `NECK_TRIM` in `rig.js` halves the visible neck. It lifts the whole torso
   rather than redrawing the neck path, and pushes anything pinned to the bottom
   edge down by the same amount so the bust still fills its frame.

Otherwise the drawing code is untouched on purpose: the rig is where the face is
defined, so "tidying" it would make the product's tutor stop matching the
module's. If the module's rig changes, re-copy and re-apply those two edits.

`features/session/TutorAvatar.tsx` is a thin wrapper whose only job is keeping
the rig's imperative handle in step with React state, and tearing down the RAF
loop. It is transparent because the rig calls `clearRect` rather than filling a
background — the notebook shows through, and she reads as standing in the room
rather than sitting in a widget.

Lip sync currently comes from the *syllables of the text* (`say()`). When the
Live API is wired in, swap that one call for `attachAudio()` and the mouth
follows real speech. Nothing else changes.

## Design decisions worth knowing

**One theme, deliberately.** The design commits to warm paper, so there is no
dark mode. Every colour is painted explicitly rather than inherited.

**Two neutral families, and the difference means something.** Warm cream for the
student's paper, cooler greys for data surfaces (teacher tables, the textbook).
A student should never be unsure whether they are looking at Nityam's writing or
the textbook's.

**One accent, spent on the next action.** Magenta marks what to do next and
nothing else. Mastery bars use red / amber / green — those encode where the
student *stands*, which is not a brand decision. Blue (`--sim`) is reserved for
simulations, matching `artifact_generator`; the teacher's charts deliberately do
not borrow it.

**Numbers are tabular.** Anything in a column uses `font-variant-numeric`.

## How this maps to the sub-modules

Each sub-module has a counterpart here, kept behind one file so it can be
swapped for the real thing without touching the screens.

| Sub-module | Here | Swap by |
|---|---|---|
| `adk` | `lib/tutorScript.ts` | Replacing scripted replies with a live WebSocket. Same `TutorState` out. |
| `canvas` | `lib/grounding.ts`, `features/session/readPage.ts`, `features/session/AnnotationLayer.tsx` | Nothing. The coverage scoring is ported, including its fix, but it scores *words* rather than the module's authored anchors — see below. |
| `artifact_generator` | `lib/kinematics.ts`, `features/session/ProjectileSim.tsx` | Feeding an IR instead of a fixed spec. The kernel stays hand-written. |
| `avatar` | `lib/avatar/` | Nothing — the rig is ported verbatim. Wire `attachAudio()` for real lip sync. |
| NCERT PDFs | `features/session/TextbookDrawer.tsx` | Real PDF rendering behind the same selectable regions. |

`ContextPacket`, `NotebookBlock` and `TutorState` are the three contracts to
keep stable; everything else is free to change.

**`ContextPacket` deliberately diverges from the canvas module.** That module
resolves a gesture to the authored `Anchor` spans it overlaps, so a packet comes
back holding anchor ids. Here a gesture reports the **text it actually covered**
and the **block it came from** — `text`, `regions[]`, `blockId` — and nothing
else. There is no `resolved`/`nearby`/`coverage` tier.

The reason is that anchors are authored, and a student highlights whatever they
like. In this notebook only three tokens were ever anchored (`v`, `θ`,
`sin(2θ)`), so sweeping a whole sentence came back holding two letters, and
sweeping unanchored prose came back empty — the student pointed at something and
was ignored. `features/session/readPage.ts` measures per word off the DOM
instead, and `regions[].sentences` widens each swept run to the sentence it sits
inside, because a stroke almost always starts and ends mid-sentence and a
fragment is poor material for the tutor to reason about.

Anchors still exist, but only for the tutor's half of two-way pointing: she
lights one up while she is talking about it. They are no longer what a gesture
resolves to.

## What is real and what is scripted

**Real:** the projectile physics, the grounding resolver (gesture → swept text
→ the block it came from), the avatar (the actual rig, animating and lip-syncing), all layout
and interaction, the annotation tools, the checkpoint flow, mastery moving when
the student earns it.

**Live:** the tutor. Her words, everything she writes on the board, the quiz she
sets and the artifacts she generates all come from the backend over a WebSocket
— see "The live tutor" below. `lib/tutorScript.ts` is gone.

**Still scripted:** every screen except the session — the class recap, the
readiness numbers, the summary, the teacher views, and the textbook page, all
from `lib/data.ts`. `backend/INTEGRATION.md` lists each one.

## Notes for whoever wires the backend

- **`data.ts` is the integration surface for every screen EXCEPT the session.**
  The session board now arrives from the backend and grows by patch
  (`lib/notebookReducer.ts`), so `data.ts`'s `notebook`, `checkpoint` and
  `studentFinding` exports are dead and safe to delete. For the rest — recap,
  readiness, summary, teacher — match the shapes and the UI needs no changes.
- **Mastery moves on evidence, not on time.** `+16` appears when the checkpoint
  is answered correctly, not on a timer. Keep that property — a number that
  moves for free is worthless to a student.
- **The greeting cue is handled.** The Live API never speaks first, so
  `useLiveSession` sends `{type:"greet"}` on connect and the backend turns it
  into a stage direction the student never sees.
- **`onExplored` in `ProjectileSim` is a probe.** It fires when the student has
  been either side of the maximum and returned to it — behavioural evidence they
  found the peak rather than read it. That is the `artifact_generator` pattern;
  keep the idea when the real IR arrives.

## Known gaps

- Desktop only. The grid collapses below 900px but the session was designed for
  a laptop and has not been tested on touch.
- The textbook drawer renders one hardcoded page, not a real PDF. Adding PDF.js
  is a real dependency decision, not an afternoon.
- Annotations are not persisted; a reload clears the page.
- ~~No auth, no routing guards. `/teacher` is reachable by anyone.~~ **Resolved.**
  Firebase Auth is wired in; every route, `/teacher*` included, is wrapped in
  `<ProtectedRoute>` (`App.tsx`).
- The mic needs a real microphone, so headless tests exercise the typed path
  instead — same upstream messages, no audio device. Her mouth reads the model's
  actual waveform via `attachAudio`; the syllable engine is now only the
  fallback for mock mode, where nothing is played.

## The live tutor

The scripted stub is gone. `src/lib/live/` is the transport, and the notebook is
state driven by the tutor's own writes.

```
src/lib/live/
  audio.ts          Float32 -> PCM16, base64url normalisation, RMS
  session.ts        mic -> worklet -> socket -> worklet -> speaker, framework-free
  protocol.ts       every message on the wire, mirroring backend/app/canvas/doc.py
  useLiveSession.ts the hook: captions, patches, mic, screen snapshots
src/lib/notebookReducer.ts   patch -> page. Pure, and tested without a browser.
src/lib/artifact/            the artifact runtime, ported from the sub-module
```

Run the backend and the frontend together with `../backend/run.sh`. On its own,
`npm run dev` proxies `/ws` to `127.0.0.1:8210` — so `location.host` is all
`session.ts` ever needs and nothing carries a base URL.

### Why the notebook is state

`data.ts`'s `notebook` export is no longer used. The board arrives from the
backend on connect and grows by patch: `append_block`, `replace_block`,
`strike`, `point_at`, `show_quiz`, `goto`. One writer (the server), one reader
(the reducer), no reconciliation.

A three-question quiz arrives as three `show_quiz` patches in a row, which is
why `quizQueue` is a queue and not a slot — with a slot, questions one and two
flash past and only the last is ever answerable.

### Artifacts

Generated live as IR by ArtifactAgent and mounted by `ArtifactBlock.tsx` into a
**shadow root**. The artifact ships its own stylesheet whose class names
(`.card`, `.btn`, `.wrap`) collide with the notebook's in both directions; a
shadow root stops that while CSS custom properties still inherit through, so the
artifact picks up `tokens.css` and looks native to the page rather than embedded.

`src/lib/artifact/embed.css` is generated — `node scripts/lift-artifact-css.mjs`
regenerates it from the sub-module's own shell, so the sub-module stays the
source of truth for how its artifacts look.

An artifact block with no IR falls back to the hand-written `ProjectileSim`,
which is what mock mode uses.

### Tests

```bash
npm run build && npm test        # all four suites
```

| Suite | What it pins |
|---|---|
| `tests/contract.mjs` | `NotebookBlock` here vs the pydantic models in `backend/app/canvas/doc.py`, field by field, plus that the reducer handles every patch op the backend can emit. These files are hand-mirrored and nothing else compares them — a field added on one side only typechecks fine and renders a block with a piece missing. |
| `tests/grounding.mjs` | the resolver's logic: word gaps, sentence bounds, coverage maths at its edges |
| `tests/reducer.mjs` | patch → page, with no browser, socket or model |
| `tests/ui.mjs` | the whole thing in headless Chrome |

`tests/ui.mjs` runs the **backend in mock mode serving the built frontend** —
one port, one real WebSocket, no proxy and no fake socket. So what it proves is
the actual wiring: she writes on the board, the marker quotes the words it
swept, a checkpoint opens and answers, and the avatar is drawn, transparent and
animating.
