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
│   ├── grounding.ts      gesture → ContextPacket (the resolver)
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
| `canvas` | `lib/grounding.ts`, `features/session/AnnotationLayer.tsx` | Nothing — the resolver is ported, including its scoring fix. |
| `artifact_generator` | `lib/kinematics.ts`, `features/session/ProjectileSim.tsx` | Feeding an IR instead of a fixed spec. The kernel stays hand-written. |
| `avatar` | `lib/avatar/` | Nothing — the rig is ported verbatim. Wire `attachAudio()` for real lip sync. |
| NCERT PDFs | `features/session/TextbookDrawer.tsx` | Real PDF rendering behind the same selectable regions. |

`ContextPacket`, `NotebookBlock` and `TutorState` are the three contracts to
keep stable; everything else is free to change.

## What is real and what is scripted

**Real:** the projectile physics, the grounding resolver (gesture → anchors →
confidence), the avatar (the actual rig, animating and lip-syncing), all layout
and interaction, the annotation tools, the checkpoint flow, mastery moving when
the student earns it.

**Scripted:** the tutor's words, and all content in `lib/data.ts`. There is no
network call anywhere yet.

## Notes for whoever wires the backend

- **`data.ts` is the whole integration surface.** Match its shapes and the UI
  needs no changes.
- **Mastery moves on evidence, not on time.** `+16` appears when the checkpoint
  is answered correctly, not on a timer. Keep that property — a number that
  moves for free is worthless to a student.
- **The greeting cue problem exists here too.** The Live API never speaks first
  (see `sub_modules_examples/adk`), so the session has to prompt the opening turn.
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
- No auth, no routing guards. `/teacher` is reachable by anyone.
- Voice input is a button that changes state and nothing else until `adk` is
  wired in. Her mouth moves to the *text*, not to audio, until then.
