# Canvas — proof of concept

A notebook the tutor and the student **share**. You scroll it like a PDF,
annotate it with a marker, and it can tell you exactly what you just pointed at.

```
CanvasDoc  ──►  validate  ──►  runtime  ──►  notebook
   (JSON)         4 gates       (hand-       + ContextPacket on every gesture
                                 written)
```

The hard part here is not rendering a notebook. It is **grounding**: turning
"the student circled a region at (340, 210)" into *"the student circled the term
`(u sinθ)²/2g`, which is `projectile.max_height`"*. That mapping is the whole
sub-module; everything else is scaffolding for it.

---

## Run it

Python 3 only. No pip install, no build step, no network at render.

```bash
cd sub_modules/canvas
python3 build.py --open
```

Tests:

```bash
node tests/resolve.js    # 24 assertions on coverage scoring — pure, no browser
node tests/browser.js    # 7 end-to-end checks in real Chrome, real layout
```

---

## What to try in the browser

1. **Select** the words *"vertical component"* with the cursor → the packet
   resolves exactly, confidence 1.00. That is tier 1 — a DOM Range, no geometry.
2. Pick up the **Marker** and swipe across `(u sinθ)²/2g` → it resolves the
   fraction, carries `projectile.max_height`, and flags the misconception that
   term is a trap for.
3. **Circle** loosely across two terms → both come back, neither above ~0.6, and
   the low-scoring one lands in `nearby` rather than `resolved`. A sloppy gesture
   should produce *"probably this, possibly that"*, never one confident wrong
   answer.
4. Circle the empty margin → nothing resolves, and the packet is still
   well-formed. The tutor gets a region with no meaning attached, and knows it.
5. Go to **page 2** and circle the apex of the trajectory image → it resolves
   `r_apex` **and returns a real cropped PNG** of what you circled, ready for a
   vision call.
6. **Page 3** holds a live artifact from `artifact_generator`, running inside the
   notebook page. Its sliders work; it reports its own evidence separately.
7. Use **Point at it** in the tutor stub → `nb.pointAt(id)` lights up the same
   anchor a student can circle. That is the two-way half of the feature.
8. Reload. Your annotations come back.

Keyboard: `1`–`4` pick a tool, `←`/`→` change page, `⌘Z` undoes.

---

## The two documents

**CanvasDoc** — what the agent will eventually emit; hand-written here.
See `doc/schema.json` and `examples/notebook_projectile.json`.

```jsonc
{ "type": "equation", "id": "b_e1", "terms": [
    { "id": "t_H", "tex": "H", "concept": "projectile.max_height" },
    { "id": "t_eq", "tex": "=", "plain": true },
    { "id": "t_frac", "over": "(u sinθ)²", "tex": "2g",
      "concept": "projectile.max_height",
      "misconception": "misc.confuses_u_with_uy" } ]}
```

Equations are **spans, not a maths library**. No external dependency, the page
runs offline, and every term becomes independently anchorable — which is the
entire point, not a shortcut.

**ContextPacket** — what the canvas emits on every gesture. This is the
interface the real product plugs into.

```jsonc
{ "gesture":"circle", "page":2, "utterance":null,
  "resolved":[ { "anchor":"r_apex", "kind":"image_region",
                 "text":"the apex of the 45° launch",
                 "concept":"projectile.max_height", "coverage":0.89 } ],
  "nearby":[], "block":"b_i1", "bbox":[418,96,112,84],
  "confidence":0.89, "crop":"data:image/png;base64,…", "tier":"geometry+crop" }
```

---

## The resolver — three tiers

`runtime/resolve.js`, tried in order:

| Tier | How | When it applies |
|---|---|---|
| **1 · selection** | native DOM `Range` intersected with anchor spans | the student selected text — exact, free |
| **2 · geometry** | stroke or polygon vs the anchor rect index, scored by coverage | marker, circle, lasso |
| **3 · crop** | real pixel crop via canvas `drawImage` | the gesture landed on an image block |

Coverage becomes `confidence`. Anchors below `RESOLVE_FLOOR` (0.35) are reported
as `nearby` instead of `resolved`.

**A marker is scored differently from a circle, on purpose.** A highlighter is a
swipe along a line, so it is scored by how much of the anchor's *width* was
swept, gated on the band meeting the anchor vertically. Plain area-intersection
scored a swipe across a tall stacked fraction at ~0.27 and dropped it below the
floor, even though the student unambiguously meant that term. `tests/resolve.js`
pins this down.

---

## Layout

```
doc/schema.json          the CanvasDoc contract
runtime/                 vanilla JS, no build step, window.Nityam namespace
  anchors.js             registry + rect index (page coordinates, cached)
  resolve.js             gesture → ContextPacket  ← the core
  blocks.js              block type → DOM, and anchor registration
  annotate.js            marker / circle / lasso, SVG overlay, undo, serialise
  pager.js               paginated scroller, page tracking
  mount.js               mountCanvas(doc, el, opts)  ← the single entry point
generate/validate.py     structural · referential · integrity · grounding
shell/template.html      standalone shell: toolbar, packet inspector, tutor stub
examples/                notebook_projectile.json
tests/                   resolve.js (pure) · browser.js + harness.js (real Chrome)
build.py                 doc → validate → inline runtime → out/canvas.html
```

Mirrors `../artifact_generator/` deliberately — same namespace, same
zero-dependency build, same *"hand-written runtime interprets a generated
document"* philosophy.

### Integration with the artifact generator

`build.py` inlines **both** runtimes, so an `artifact` block just calls
`Nityam.mountArtifact(ir, el, opts)`. There is no coupling code.

The artifact is mounted in a **shadow root**: it ships its own stylesheet whose
class names (`.card`, `.btn`, `.top`) are generic enough to collide with the
notebook's in both directions. CSS custom properties still inherit through, so
the two surfaces keep sharing one design system while their component rules stay
apart.

---

## Lifting this into the Nityam app

```jsx
const nb = Nityam.mountCanvas(canvasDoc, ref.current, {
  artifacts, themes, artifactCSS,
  onGesture: packet => agent.ask(packet),      // ← the whole student→tutor path
});

nb.pointAt('t_frac');                           // ← and the tutor points back
nb.addBlock(2, { type: 'tutor_text', ... });    // ← growing the notebook per turn
```

The handle also exposes `goToPage`, `setTool`, `undo`, `clearPage`, `anchors()`,
`getAnnotations()`, `lastPacket()` and `destroy()`. Nothing drives `pointAt` in
this proof of concept — the dev panel in the shell stands in for the agent.

---

## The validation gate

Four mechanical passes, run before anything renders (`generate/validate.py`):

| Gate | Catches |
|---|---|
| **structural** | unknown block types, bad page numbering, missing text |
| **referential** | an anchor whose `span` does not occur in its block's text, an SVG selector that isn't in the SVG, an image rect outside the unit square, an artifact that isn't bundled |
| **integrity** | duplicate anchor or block ids |
| **grounding** | a page with nothing to point at, or a declared concept no anchor carries |

The grounding gate is the one that matters: a notebook with no anchors renders
perfectly and is useless, because the student can circle things all day and the
tutor learns nothing.

---

## Deliberately not built

- **No textbook blocks.** Out of scope until the ingestion pipeline exists. When
  it does, PDF.js gives per-word boxes for free; scans need an OCR sidecar. The
  `image` block's `regions` already models the coarse version.
- **No tutor.** No responder, no Gemini. The packet goes to a panel and stops.
- **Tier-3 crop is partial.** Image blocks crop for real; text and diagram blocks
  would need a DOM rasteriser, so those packets report the block and nearest
  anchors with `crop: null`.
- **No handwriting, no OCR.** Desktop and a mouse, so highlight / circle / type
  is the whole vocabulary. A stylus would change this.
- **No object dragging, no infinite canvas, no multiplayer.** Collaboration here
  is human↔AI, so an append-only packet stream is enough — no CRDT.
- Annotations are page-anchored and not reflow-safe; page width is fixed by design.

## Note on the tests

The plan called for a stub-DOM test. There isn't one, on purpose: a stub cannot
do layout, and layout is exactly what this module resolves against, so such a
test would verify almost nothing. `tests/browser.js` drives real `PointerEvent`s
against real `getBoundingClientRect()` output in headless Chrome instead, which
covers the same ground honestly. It skips cleanly if Chrome is not installed.
