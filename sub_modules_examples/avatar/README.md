# Avatar — proof of concept

The tutor's face. She breathes, blinks, drifts, changes expression, and moves
her mouth to what she is saying.

```bash
cd sub_modules_examples/avatar
python3 build.py --open
node tests/avatar.js
```

Python 3 only. No dependencies, no model files, no network, no build step.

---

## What the research said, and what follows from it

Three approaches were live: **Rive** (vector state machines, ~120fps, but the
character must be authored in the Rive editor), **Lottie** (no state model at
all — "any smart behaviour has to be rebuilt in code"), and **Live2D** (heavy,
licensed, needs a rigged model).

The finding that decided it: *there is no off-the-shelf audio-to-lip-sync
solution for Rive, Spine or Lottie characters.* **Whichever renderer you pick,
this layer gets built.** And the standard web technique — Web Audio
`AnalyserNode` → FFT band energies → viseme classification — is buildable with
zero dependencies.

So the module is split along the line that actually matters:

| Durable | Swappable |
|---|---|
| the **rig contract** — 20 named parameters | how those parameters become pixels |
| the **emotion engine** — presets + springs | |
| the **lip-sync engine** — visemes from audio or text | |
| the **public API** — `setState`, `react`, `say` | |

`runtime/rig.js` draws a procedural character on a canvas. Replace it with a
Rive board or a 3D head with ARKit blendshapes and **nothing else changes**,
because the parameter names are the contract.

---

## The API

```js
const tutor = Nityam.mountAvatar(el, { size: 260 });

tutor.setState('listening');                 // idle | listening | thinking | speaking
tutor.setEmotion('curious');                 // hold it
tutor.react('encouraging', 3);               // a beat that reverts on its own
tutor.say("So what do you think decides the range?");   // no audio needed
tutor.attachAudio(audioEl);                  // real TTS → real visemes
tutor.tick(seconds);                         // drive it from your own clock
```

State and emotion are **orthogonal**: she can be listening *and* concerned, or
speaking *and* delighted. Speech drives the mouth; the emotion drives everything
else; they layer through the same spring system rather than fighting.

---

## The ten emotions

`neutral` · `listening` · `thinking` · `explaining` · `encouraging` ·
`excited` · `curious` · `surprised` · `gentle` · `proud`

Two deliberate choices:

- **There is no "sad" and no "angry".** A tutor is never disappointed in a
  student. The nearest thing is `gentle` — inner brows up, head tilted, warm.
  "Not quite, let's look again", not "you failed".
- **`encouraging` squints the eyes.** A smile that reaches only the mouth reads
  as fake to everybody, instantly. `eyeSquint` and `cheekRaise` carry more of
  that expression than mouth width does.

An emotion is a *partial* set of targets. Anything it doesn't mention keeps its
current value, which is why `excited → proud` never detours through a neutral
mouth. There's a test for exactly that.

---

## What makes it look alive

Not the expressions — the things underneath them:

- **Per-parameter springs.** Eyes and mouth are fast; brows and smile take
  ~0.3s; the head is slow and lags. Everything **overshoots and settles** rather
  than easing linearly. A test asserts the overshoot, because without it the
  face reads as a slideshow.
- **Blinking**, at random 2–6s intervals, sometimes doubled.
- **Micro-saccades** — the eyes are never perfectly still.
- **Slow head drift** on layered sines, so a held pose never freezes.
- **Breathing.**

Remove those five and you have a corpse with a moving mouth.

---

## Lip sync

Two drivers, one output:

```
fromAudio(el | MediaStream)   AnalyserNode → F1 (300–900Hz) sets openness,
                              F2/F1 ratio separates wide vowels from rounded,
                              a hiss band catches sibilants. Sub-frame latency,
                              no network.

say(text)                     a synthetic envelope built from the actual
                              syllables. No microphone, no TTS, and the rhythm
                              still matches the words.
```

Ten visemes (`REST MBP AA E I O U FV L S`), each a target for four mouth
parameters. Coarticulation — the smooth blur between shapes that makes real
speech legible — is free, because the targets go through the same springs.

Verified: `m`/`b`/`p` fully close the lips, `mouthOpen` peaks at 0.85 on vowels
and returns to 0.00 between syllables, and width varies across 36 distinct
values in one sentence so it isn't just a flapping jaw.

---

## Layout

```
runtime/rig.js         20 parameters + the procedural drawing   ← the swappable part
runtime/emotions.js    10 presets, springs, idle behaviours
runtime/speech.js      visemes from audio or from text
runtime/mount.js       mountAvatar() — the public API
shell/template.html    demo: every emotion, every state, live parameter readout
tests/avatar.js        27 assertions on the arithmetic
build.py               inline → out/avatar.html
```

---

## Two bugs worth knowing about, both now fixed

Both were the same class — **a component owning its own clock while the host
owns another.**

1. `say()` called `performance.now()` while `tick()` accepted an arbitrary time,
   so any host driving its own loop desynced the mouth from the words.
2. `react(name, seconds)` stored an absolute deadline from `Date.now()`, so a
   transient emotion never expired under a different clock.

Both now take time from the caller. If you add anything time-based to this
module, take `now` as an argument — don't reach for a clock.

---

## Her look, and how to change it

Styled after a soft-3D cartoon reference: light peachy skin, warm brown hair
centre-parted with a low side bun, round tortoiseshell glasses, hazel-gold eyes,
mint collared shirt. Every mass is a canvas gradient rather than a flat fill,
lit consistently from the upper left.

**All of it is in one place.** The `C = { ... }` palette at the top of
`runtime/rig.js` holds ~30 hex values — skin, hair, eyes, frames, lips, shirt.
Change those and she changes, with no other edits. Geometry lives in the same
file, authored in a fixed 300×340 space so every number is stable.

The restyle from the first version — a different skin tone, different hair,
no glasses, a maroon kurta — touched **only `rig.js`**. The emotion engine, the
lip-sync engine, the tests and the public API were all untouched, which is the
claim the module's structure was built to make.

## Deliberately not built

- **No photorealism, and no true 3D.** The reference is a rendered 3D model with
  real subsurface scattering and volume; this is a 2D approximation of that look
  using gradients. It lands in the same family but it is not the same thing —
  if you need the render, the honest answer is a Rive character or a GLB with
  blendshapes, dropped in behind the same parameter contract.
- **No phoneme-accurate lip sync.** Matching rhythm and the rounded/wide
  distinction is what the eye actually checks.
- **No body, no hands, no gaze tracking to the notebook.** Gaze would be the
  highest-value addition next: having her look at the artifact the student is
  manipulating is a strong cue.
- **No TTS.** `attachAudio()` is the seam; bring your own voice.
