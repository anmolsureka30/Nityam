# ArtifactGenerator — proof of concept

One worked example, end to end: **a pedagogical request goes in, an interactive
artifact comes out.**

```
ArtifactSpec  ──►  Gemini  ──►  Artifact IR  ──►  validator  ──►  runtime  ──►  artifact.html
  (what the        (config,      (JSON, no        (4 gates)      (hand-        + evidence
   student          not code)     code in it)                     written)       events
   must work out)
```

The example is projectile motion: the student is meant to *discover* that range
peaks at 45°, rather than be told.

---

## Run it

Needs Python 3 only. No pip install, no build step, no network.

```bash
cd sub_modules_examples/artifact_generator

python3 build.py --all --open        # ALL THREE lessons + an index page
python3 build.py --open              # just lesson 1
python3 build.py --theme spiderman   # same artifact, different student
python3 build.py --live              # let Gemini write the IR (see below)
```

Output lands in `out/` — self-contained single files. Double-click any of them.

## One kernel, three lessons

All three run the **same** `kinematics2d` engine and the **same** renderer.
Everything that differs lives in a JSON document.

| Lesson | Question | What it cost |
|---|---|---|
| `lesson1_max_range` | Which angle sends it farthest? | — |
| `lesson2_gravity` | What if you played on the Moon? | **no code** — unlocked a locked state variable |
| `lesson3_xy_independence` | Does it slow down horizontally? | one reusable layer type (`vector_set`, ~30 lines) |

Watch the validation gate reject a bad artifact:

```bash
python3 build.py --ir examples/ir_broken_wiring.json    # refs that don't resolve
python3 build.py --ir examples/ir_broken_physics.json   # wired fine, teaches the wrong thing
```

The second one is the interesting case. That IR is perfectly valid JSON, would
render beautifully, and is rejected — because the angle slider is capped at 30°,
so the student could never reach the 45° optimum the learning outcome is about.
No amount of looking at generated HTML catches that.

Tests (need `node`):

```bash
node tests/smoke.js    # kernel parity + probe logic, replays a session
node tests/dom.js      # mounts the artifact against a stub DOM and drives it

# both are lesson-aware — point them at any IR
IR=examples/lesson2_gravity.json node tests/smoke.js
```

### The `--live` path

```bash
pip install google-genai
export GEMINI_API_KEY=...
python3 build.py --live
```

Gemini receives the spec, the IR schema, the kernel contract and one worked
example, and returns an IR. If it fails validation, the errors are fed back for
one retry; if it still fails, the build falls back to the golden IR and says so.
**A student never sees an unvalidated artifact.**

---

## What to try in the browser

1. Drag **Launch angle** to 20°, then 15°, then 60°, then 45°.
   Watch the **evidence stream** at the bottom fill up.
2. At 30° and 60° an annotation appears — the ranges are identical. Hit
   **Pin this attempt** at each to leave ghost traces and see it.
3. Land near 45° and `artifact.discovered_optimum` fires. That event is the
   whole point: the artifact reports that the student *worked it out*.
4. After two explorations the **Checkpoint** question unlocks. It cannot be
   answered before the student has played.
5. Reload, then drag only the **speed** slider three times and never touch
   angle → `artifact.misconception_behavior` fires. The artifact diagnosed the
   misconception from behaviour, without asking a question.
6. Change **Personalisation** to Spider-Man. Same physics, same artifact_id,
   different world. Nothing is regenerated.

---

## The four things this proves

| | |
|---|---|
| **The model configures, it does not code** | Gemini emits JSON. Physics lives in a hand-written kernel; layout lives in a hand-written renderer. |
| **Artifacts can be gated** | The validator sweeps the kernel and rejects bad artifacts *before* render. Generated HTML cannot be checked this way. |
| **Artifacts produce evidence** | Probes emit concept-tagged events. This is what closes the loop back to the student model and the teacher dashboard. |
| **Personalisation is free** | Theme resolves at render time and is excluded from the artifact's identity. One artifact serves 42 students. |

---

## Layout

```
ir/schema.json          the IR contract — also fed to Gemini as part of the prompt
generate/
  spec.py               ArtifactSpec: the pedagogical request
  prompt.md             what Gemini is allowed to do (and forbidden from doing)
  generator.py          spec -> IR   (mock | live, with validate-and-retry)
  kernel_py.py          kinematics2d, Python twin — used for validation sweeps
  validate.py           4 gates: structural, referential, invariants, pedagogical
runtime/                plain JS, no framework, no build step
  kernel.js             kinematics2d, JS twin — used for rendering
  evaluate.js           state -> frame  (pure)
  probes.js             interaction -> concept-tagged evidence
  render.js             frame -> canvas + DOM
  mount.js              mountArtifact(ir, el, opts)  ← the single entry point
shell/template.html     the standalone wrapper
examples/               spec_projectile.json, ir_projectile.json (golden), themes.json
tests/                  smoke.js, dom.js
build.py                the pipeline, with every stage printed
out/artifact.html       the result
```

### Why the kernel is written twice

`kernel_py.py` and `kernel.js` are the same physics in two languages, because
validation happens server-side (Python, next to the agent) and rendering happens
client-side. They are kept honest by a **parity check**: `build.py` samples the
Python kernel, embeds the vectors in the page, and the JS kernel re-computes
them at load. Open the browser console — it prints `[nityam:parity]`. Drift
becomes a visible failure instead of a silent one.

---

## Lifting this into the Nityam app

The runtime has no opinion about the shell. In the student app:

```jsx
useEffect(() => {
  const a = Nityam.mountArtifact(ir, ref.current, {
    themes,
    theme: student.interest,
    onEvidence: e => agent.updateStudentMemory(e),   // <- the loop closes here
  });
  return () => a.destroy();
}, [ir]);
```

`generate/` becomes the body of the `create_artifact()` ADK tool.
`ir/schema.json` is the contract between the two halves.

---

## Deliberately not built

This is a proof of concept, and the cuts are on purpose. None of them change
the architecture — they are all additive:

- **no expression language** — `derived` values are plain refs like
  `"kernel.range"`. Anything you want must come out of the kernel.
- **one kernel** — `kinematics2d`. A second kernel (`vectors2d`, `graph1d`) is
  a new file plus a registry entry.
- **no artifact cache / tier routing** — every build regenerates.
- **no `update_artifact`** — the design patches a live IR with JSON Patch so an
  artifact can grow with the student. Not wired here.
- **no code-generation fallback** — the tiered design drops to a constrained
  SDK when the IR cannot express something. Out of scope for one example.
