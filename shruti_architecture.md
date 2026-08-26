# SHRUTI — Lecture Capture & Knowledge Extraction

**श्रुति · "that which is heard"**
The ingestion half of Nityam. Turns a lecture recording into a queryable, teachable knowledge substrate.

Version 0.1 · architecture, research and decisions · for review before coding

---

## 0. Read this first

### 0.1 What SHRUTI is, in one paragraph

A teacher records a class — or you point it at a YouTube lecture. SHRUTI watches it the way a diligent student would: it listens to what was said, reads what was written on the board *including the parts the teacher was standing in front of*, notices what they pointed at, and stitches all three into a single timeline of **Beats**. It then distils those Beats into a concept map with prerequisite edges. Every claim in that map traces back to the exact second of the exact lecture it came from. That substrate is what the Nityam tutor teaches from — which is the deck's core promise: *"Nityam teaches each student from the lesson their own teacher gave that day."*

### 0.2 The three decisions this document makes

| # | Question you asked | Answer | Where |
|---|---|---|---|
| **D1** | Should we build the multi-model pipeline from the paper (Whisper + Qwen-VL + Qwen-LLM)? | **No.** Gemini 3.5 Flash does ASR, frame understanding *and* extraction in one stack — and beats the specialists on the two things that matter (code-mixed speech, handwritten math). Keep classical CV **only** for the board. | §2 |
| **D2** | Timeline, or knowledge graph? | **Both, layered, and the layering is the answer.** A temporal **Reel** is ground truth and is immutable; the **Atlas** graph is a *projection* of it and is disposable. Every graph node cites Beat IDs. | §5 |
| **D3** | How much CV do we actually need for the board? | **Staged.** V1 = mask-aware temporal compositing (CPU, no GPU, ~150 lines). V2 = SAM 3 masks. Do not start with SAM 3 — it needs CUDA 12.6+ and an 848M-param model, and you'll spend the hackathon on infra. | §3.3 |

### 0.3 Honest read on your uploaded materials

**The Zheng et al. paper (*Expert Systems With Applications*, 2026)** is the right *shape* and the wrong *stack* for us. Its architecture is exactly ours — decouple the video into atomic subtasks, map each modality to text, fuse with an LLM under prompt engineering. Its ablations are the most useful thing in it and I've built §2 around them. But it uses Whisper + Qwen2.5-VL + Qwen2.5 because it was written for reproducible zero-shot research on 7B/32B/72B open models. We have Gemini and $150 of credits. Take the findings, not the model list.

Three of its numbers should shape your build:

- **Objective facts live in vision, subjective facts live in speech.** Audio-only, F1 on objective fact fields collapses from 90% → **2%**. Vision-only, subjective fields drop 52% → 42%. The modalities are not redundant; they are *disjoint*. This is the single strongest argument for the fusion architecture.
- **Uniform frame sampling loses information.** Their dual-threshold sampling (dense 1f/1s in high-density regions, sparse 1f/6s elsewhere, with different pixel-difference thresholds δ₁=3, δ₂=10) measurably beat uniform. Our **Pulse** stage is the same idea, retargeted at writing activity instead of talk-intro density.
- **Prompt engineering is not garnish.** Without it, relation-extraction F1 falls from 76% → **18%**, mostly because the model stops emitting parseable format. Structured output is load-bearing.

**The `sense` skill file** has a real engineering skeleton buried in unusual packaging. Take: subtitle parsing into timestamped segments, ffmpeg frame extraction at detected boundaries, slide-gap detection, a DuckDB index with pre-built timeline views, content→skill mapping, and the `just`-style CLI ergonomics. Those are all sound and I've reused them.

Leave: the GF(3)/trit conservation layer, the Tsao visual-hierarchy mapping, and the self-avoiding-walk colouring. I looked for a mechanism by which `(-1) + (0) + (+1) ≡ 0 (mod 3)` improves extraction quality and there isn't one — the "balance" step literally appends `sheaf-cohomology` or `operad-compose` to a slide's skill list to make an arithmetic sum come out to zero, which injects labels the content doesn't support. In an educational knowledge base, a false prerequisite edge is worse than a missing one. Also drop Mathpix from that file — see §3.4, Gemini is both cheaper and more accurate for this now.

**Your two canvas flowcharts** are correct and I've kept their structure. The one thing I'd change: you have *Board localization → audio extraction* as a serial chain. Those are independent and should fan out in parallel — it's roughly a 2× wall-clock saving on a 45-minute lecture, and it's free (`ParallelAgent`).

---

## 1. Objectives

### 1.1 Product objectives

| # | Objective | Success looks like |
|---|---|---|
| O1 | **Ground the tutor in the actual lesson** | For any concept the student asks about, the tutor can cite the exact board state and utterance from their own class |
| O2 | **Recover occluded board content** | Content written and then stood in front of is present in the final board state |
| O3 | **Preserve the teacher's notation** | If sir wrote `(x+3)² − 9 + 5`, the tutor uses that form, not a textbook-normalized alternative |
| O4 | **Survive code-mixed speech** | Hindi–English mixing mid-sentence transcribes faithfully, without collapsing to one script |
| O5 | **Make every claim traceable** | Click any concept → jump to the second it was taught |
| O6 | **Be re-runnable** | Better model next month → re-derive the graph without re-uploading the video |

### 1.2 Engineering objectives

- **Deterministic where possible, probabilistic where necessary.** Shot boundaries, ink-pixel curves, erase events: deterministic CV. Concepts, prerequisites, misconceptions: LLM. Never let the LLM do arithmetic the CPU can do exactly.
- **Every stage independently re-runnable** against cached upstream outputs. You will iterate on Atlas fifty times and Gate twice.
- **Cost-bounded.** A 45-minute lecture must cost under $2 end-to-end (§8).
- **Fails soft.** No stage may block the pipeline. A failed Slate degrades to slide-only; a failed Point degrades to no-deixis.

### 1.3 Explicit non-goals for v1

Real-time/live processing (SHRUTI is offline; the live classroom capture in the deck is a later product). Multi-camera. Speaker identification beyond teacher/student. Videos over 3 hours. Handwriting *style* preservation (we extract content, not calligraphy).

---

## 2. The stack decision

### 2.1 What Gemini can now do that changes the design

| Capability | Detail | What it replaces |
|---|---|---|
| **Native video understanding** | Samples at 1 FPS, audio at 1kbps, **timestamps added every second**. Query with `MM:SS`. 1M-context models handle **1 hour at default resolution, 3 hours at low**. | The entire "stitch-and-align" preprocessing layer |
| **`media_resolution` control** | `low` = 66 tokens/frame, default = 258 tokens/frame | Lets you run a cheap coarse pass and an expensive fine pass with the same model |
| **Custom FPS + clipping** | `videoMetadata` with `fps` and start/end offsets | Adaptive sampling without extracting frames yourself |
| **YouTube URLs directly** | Public videos, no download | `yt-dlp` for the happy path |
| **Handwritten math OCR** | Independent benchmark: **Gemini 3 Flash at $0.004/page vs Mathpix at $0.025/page — 6× cheaper and more accurate.** Mathpix made semantic errors (reading `5` as `\overline{0}`) that would poison a knowledge base. A separate 2026 study found Gemini 3 Flash hit 95% accuracy on rubric items for handwritten maths grading. | Mathpix |
| **Code-mixed ASR** | A 2026 corpus study found Whisper-large-v3 *"failed on code-switched audio by transliterating or translating English into Urdu script rather than maintaining literal content,"* while Gemini outperformed due to semantic awareness and targeted prompting. Whisper has the same documented failure on Hinglish — with `language=hi` it forces everything into Devanagari, with **no API flag to request romanized output**. | Whisper |

That last row matters more than it looks. Indian classroom speech is *"अब हम iska derivative nikalenge"*. An ASR that forces one script destroys the very thing the deck promises to preserve. Gemini takes a prompt — "transcribe faithfully, keep English words in Latin script and Hindi words in Devanagari, do not translate" — and honours it.

### 2.2 Where classical CV still earns its place

Gemini at 1 FPS sees the teacher standing in front of the board. It cannot see through them, and it has no mechanism to composite information across frames. So:

> **Rule: Gemini for semantics and reading. Classical CV for geometry and time.**

CV owns: board plane detection and rectification, person masking, temporal compositing, ink-pixel accounting, erase-event detection, shot boundaries. All of these are exact, cheap, and deterministic. Gemini owns everything downstream of "here is a clean board image and a transcript."

### 2.3 The models

| Job | Model | Why |
|---|---|---|
| Video semantic pass | `gemini-3.5-flash`, `media_resolution: low` | Cheap structure extraction over the whole video |
| Board reading (composited stills) | `gemini-3.5-flash`, `media_resolution: high` | Few images, needs to read fine handwriting |
| Transcript | `gemini-3.5-flash` (audio) | Code-mix fidelity |
| Concept & relation extraction | `gemini-3.5-flash` + structured output | The paper's F1 76%→18% result: schema is load-bearing |
| Cheap classification, routing, dedup | `gemini-3.5-flash-lite` | High volume, trivial decisions |
| Everything offline | **Batch API — 50% off all models** | See §8 |
| Repeated prompt prefixes | **Explicit context caching — 90% off cached input** | Extraction schema is ~4k tokens, identical every call |

---

## 3. The pipeline

### 3.1 Flowchart

```
                                    ┌──────────────┐
   video file / YouTube URL ───────▶│  ① GATE      │  admit · probe · normalize · fingerprint
                                    └──────┬───────┘
                                           │  Recording
                                           ▼
                                    ┌──────────────┐
                                    │  ② PULSE     │  the temporal spine:
                                    │              │  shot cuts · ink-activity curve ·
                                    │              │  erase events · adaptive sample plan
                                    └──────┬───────┘
                                           │  Timeline
                    ┌──────────────────────┼──────────────────────┐
                    │                      │                      │
                    ▼                      ▼                      ▼
            ┌──────────────┐       ┌──────────────┐       ┌──────────────┐
            │  ③ SLATE     │       │  ④ ECHO      │       │  ⑤ POINT     │
            │  (CV, CPU)   │       │  (Gemini)    │       │  (Gemini)    │
            │              │       │              │       │              │
            │ locate board │       │ code-mix     │       │ deixis:      │
            │ rectify      │       │ faithful     │       │ "yeh term"   │
            │ mask teacher │       │ transcript,  │       │ → board      │
            │ composite    │       │ diarized,    │       │   region     │
            │ across time  │       │ timestamped  │       │ + gestures   │
            └──────┬───────┘       └──────┬───────┘       └──────┬───────┘
                   │ BoardState[]         │ Utterance[]          │ Deixis[]
                   └──────────────────────┼──────────────────────┘
                                          ▼
                                   ┌──────────────┐
                                   │  ⑥ WEAVE     │  one timeline, one unit:
                                   │              │  Beat = span + speech + board
                                   │              │       + deixis + provenance
                                   └──────┬───────┘
                                          │  Beat[]
                                          ▼
                                   ┌──────────────┐
                                   │  ⑦ GLYPH     │  read each BoardState:
                                   │  (Gemini hi) │  LaTeX · text · figures ·
                                   │              │  layout regions
                                   └──────┬───────┘
                                          │  BoardContent
                                          ▼
                                   ┌──────────────┐
                                   │  ⑧ ATLAS     │  concepts · prerequisite edges ·
                                   │              │  worked examples · pre-empted
                                   │              │  misconceptions · citations→Beat
                                   └──────┬───────┘
                                          │  ConceptGraph
                    ┌─────────────────────┼─────────────────────┐
                    ▼                     ▼                     ▼
            ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
            │  L1 REEL     │      │ L2 LEDGER    │      │  L3 ATLAS    │
            │  immutable   │      │ board states │      │  semantic,   │
            │  timeline    │      │ over time    │      │  rebuildable │
            └──────┬───────┘      └──────┬───────┘      └──────┬───────┘
                   └─────────────────────┼─────────────────────┘
                                         │        ⑨ VAULT
                                         ▼
                                  ┌──────────────┐
                                  │  ⑩ LENS      │  hybrid retrieval →
                                  │              │  ADK tools for the tutor
                                  └──────────────┘
```

### 3.2 ① GATE — admit the recording

**In:** file path, GCS URI, or YouTube URL. **Out:** `Recording`.

| Step | Tool | Note |
|---|---|---|
| Resolve source | `yt-dlp` for YouTube; direct otherwise | Gemini also takes YouTube URLs natively — but download anyway, because Slate needs real frames |
| Probe | `ffprobe` | duration, fps, resolution, codec, audio channels |
| Normalize | `ffmpeg` | H.264, constant frame rate, mono 16 kHz audio track extracted separately |
| Fingerprint | SHA-256 of normalized video | **Content-addressed.** Re-uploading the same lecture is a no-op. Every downstream artifact is keyed to this hash. |
| Classify surface | `gemini-3.5-flash-lite` on 5 sampled frames | `blackboard` / `whiteboard` / `slides` / `mixed` / `talking_head` — routes Slate's parameters |

That last classifier is worth the 2 cents. A slide deck and a chalkboard need completely different Slate parameters, and getting it wrong wastes an entire run.

### 3.3 ② PULSE — the temporal spine

This is the stage that decides where everything else looks. Get it right and the rest is easy.

**In:** `Recording`. **Out:** `Timeline`.

**Four signals, all deterministic:**

**(a) Shot boundaries** — PySceneDetect `AdaptiveDetector` (rolling average of HSV differences; mitigates false positives from camera motion, which matters because classroom cameras drift). `ContentDetector` at threshold ~27 as a fallback. For slide decks, `HistogramDetector` on the Y channel handles lighting variation better.

**(b) The ink curve** — the most useful signal in the pipeline and nobody uses it.

```python
def ink_curve(frames, board_quad) -> np.ndarray:
    """Ink pixel count per sampled frame, inside the rectified board."""
    counts = []
    for f in frames:
        board = rectify(f, board_quad)
        # Chalk on dark board: bright-on-dark. Marker on white: dark-on-bright.
        ink = adaptive_binarize(board, polarity=SURFACE_POLARITY)
        counts.append(int(ink.sum()))
    return np.array(counts)
```

From this one curve you get, for free:
- **Writing bursts** — positive derivative. Sample densely here.
- **Explanation stretches** — flat curve, speech continuing. Sample sparsely; the board isn't changing.
- **Erase events** — sharp negative cliff. These are the **most important timestamps in the entire lecture**, because they delimit board states.

**(c) Adaptive sample plan** — the paper's dual-threshold idea, retargeted:

| Region | Sampling | Rationale |
|---|---|---|
| Writing burst | 1 f/s, pixel-diff threshold δ=3 | Fine-grained content is appearing |
| Explanation stretch | 1 f/6s, δ=10 | Board static, only speech carries information |
| Erase neighbourhood (±5s) | 2 f/s | Capture the last complete state before erasure |
| Slide surface | on shot boundary only | One frame per slide is sufficient |

**(d) Board-state segmentation** — the key structural insight:

> **Between two erase events, board content is monotonically increasing.** Writing accumulates; it does not disappear. Therefore *the last frame before an erase is the most complete version of that board state* — and you should composite **backwards** from it.

This turns board recovery from "reconstruct arbitrary occlusion" into "fill the holes in one target frame using neighbours," which is a far easier problem.

```
ink
 │        ╭─────╮                    ╭────────╮
 │      ╭─╯     ╰╮                 ╭─╯        ╰╮
 │    ╭─╯        ╰─╮             ╭─╯           ╰─╮
 │  ╭─╯             ╰╮         ╭─╯                ╰╮
 └──┴────────────────┴─────────┴───────────────────┴──▶ t
    └── BoardState 1 ─┘ ERASE   └── BoardState 2 ───┘ ERASE
                              ▲                      ▲
                        composite target       composite target
```

### 3.4 ③ SLATE — recover the board

The technically hardest stage, and the one that makes the product feel like magic.

**In:** `Recording`, `Timeline`. **Out:** `BoardState[]` — one clean, rectified, de-occluded image per state, with a validity interval.

**Four steps:**

**(1) Locate.** Classical CV: Canny → contour detection → largest quadrilateral with board-like aspect ratio, stabilized by voting across ~30 frames sampled across the whole video (the board doesn't move; the teacher does). Fallback: `gemini-3.5-flash` with a bounding-box prompt if contour detection fails, which it will on cluttered rooms.

**(2) Rectify.** `cv2.getPerspectiveTransform` + `warpPerspective` to a canonical front-on rectangle. Compute once per video. Everything downstream operates in board coordinates, which means a deixis event at `(0.34, 0.61)` means the same thing at minute 3 and minute 40.

**(3) Mask the teacher.** Three options, in the order you should build them:

| Tier | Method | Infra | Quality |
|---|---|---|---|
| **V1** | Frame-difference + morphology + largest-connected-component | CPU, ~40 lines | 70–80%. Good enough. |
| **V2** | YOLO person detection → box → refine with GrabCut | CPU, small model | 85% |
| **V3** | **SAM 3** with text prompt `"person"` | **GPU: Python 3.12+, PyTorch 2.7+, CUDA 12.6+, 848M params** | 95%+ |

SAM 3 is genuinely the right endpoint — it does Promptable Concept Segmentation, so `"person"` as a text prompt returns masks with stable IDs tracked across frames, which is exactly the "occlusion mask over time" your flowchart called out. SAM 3.1's Object Multiplex (March 2026) makes multi-object tracking materially faster.

**But do not start here.** The classroom camera is static and the board is planar. Frame differencing against a temporal median background gets you most of the way for zero GPU cost. Build V1 in an hour, ship, and upgrade if the OCR accuracy actually demands it.

**(4) Composite.** Here is the subtlety that most implementations get wrong.

A naive temporal median across a window *erases recently written content*, because new ink is present in only a few recent frames and the median votes it away. The correct algorithm is **selective, masked, direction-aware infill**:

```python
def composite_board_state(frames, masks, target_idx, state_span):
    """
    Fill occluded regions of the target frame using the nearest frame
    where that region is visible. Search FORWARD first within the state
    (content only grows), then BACKWARD as fallback.
    """
    target = frames[target_idx].copy()
    holes  = masks[target_idx]                    # True where teacher occludes
    unfilled = holes.copy()

    # Forward: later frames have ≥ the content of the target
    for i in range(target_idx + 1, state_span.end):
        donatable = unfilled & ~masks[i]
        if not donatable.any(): continue
        target[donatable] = frames[i][donatable]
        unfilled &= ~donatable
        if not unfilled.any(): break

    # Backward fallback: only for regions still unfilled
    for i in range(target_idx - 1, state_span.start - 1, -1):
        donatable = unfilled & ~masks[i]
        target[donatable] = frames[i][donatable]
        unfilled &= ~donatable
        if not unfilled.any(): break

    return target, unfilled   # ← return the holes you could NOT fill
```

Two details that matter:

- **Photometric normalization before donation.** Lighting drifts across a 45-minute lecture. Match the donor patch's mean/std to the target's local neighbourhood or you get visible seams that confuse the OCR pass.
- **Return the unfilled mask.** Regions the teacher never moved away from are genuinely unknown. Pass that mask to GLYPH so the model is told *"the greyed regions were never visible — do not guess."* Hallucinated board content is the worst possible failure mode in an education product, and this one line prevents it.

**Fallbacks, in order:** SAM 3 → YOLO+GrabCut → frame-diff → no masking, just take the last frame before erase → skip Slate, mark the video `slide_only` and rely on ECHO alone. The pipeline never dies.

### 3.5 ④ ECHO — recover the speech

**In:** normalized audio. **Out:** `Utterance[]` — `{start, end, text, speaker, language_spans, confidence}`.

Send the audio to `gemini-3.5-flash` with an explicit fidelity contract:

```
Transcribe this classroom recording exactly as spoken.

RULES
1. This is code-mixed Hindi–English classroom speech. Transcribe FAITHFULLY:
   Hindi words in Devanagari, English words in Latin script, in the order spoken.
   Do NOT translate. Do NOT normalize to one script.
   Correct: "अब हम iska derivative nikalenge, using the chain rule."
   Wrong:   "अब हम इसका डेरिवेटिव निकालेंगे, यूजिंग द चेन रूल।"
2. Timestamp every utterance as MM:SS.
3. Label the speaker: TEACHER or STUDENT.
4. Preserve technical terms exactly as spoken, including English terms
   inside Hindi sentences.
5. If audio is unintelligible, emit [inaudible]. Never guess.
```

If a subtitle track exists (YouTube auto-captions, or an uploaded `.vtt`), parse it as a **prior** — align it to Gemini's output and prefer the subtitle for timing (it's frame-accurate) and Gemini for content (it's script-faithful). This is the useful half of the `sense` skill's subtitle parser.

### 3.6 ⑤ POINT — resolve deixis

The stage nobody builds, and the one that makes the extraction genuinely *lesson-aware*.

Teachers speak in pronouns: *"ab yeh term yahan cancel ho jayega"* — "now this term here will cancel." Without resolving *this* and *here*, the transcript is nearly useless as teaching material.

**In:** frames at writing/gesture moments, rectified board coords, `Utterance[]`. **Out:** `Deixis[]`.

```python
class Deixis(BaseModel):
    at: float                        # seconds
    utterance_id: str
    phrase: str                      # "yeh term"
    board_region: BBox               # normalized board coords, 0–1
    kind: Literal["point", "circle", "underline", "sweep", "write"]
    referent_text: str | None        # filled after GLYPH: "(x+3)²"
    confidence: float
```

Method: send Gemini a short clip (5s window, `media_resolution: default`) plus the transcript span, ask for the pointed-to region in normalized board coordinates. Only run this on frames where PULSE flagged gesture-like motion near the board — typically 30–60 events in a 45-minute lecture, so it's cheap.

After GLYPH runs, back-fill `referent_text` by intersecting `board_region` with the extracted layout regions. Now *"yeh term"* resolves to `(x+3)²`, and the tutor can say the same sentence to a student and highlight the same thing.

### 3.7 ⑥ WEAVE — fuse into Beats

**In:** everything. **Out:** `Beat[]`.

A **Beat** is the atomic unit of a lesson: one coherent span of teaching. Boundaries come from a merge of three signals — utterance pauses > 1.5s, ink-curve inflections, and shot boundaries — then a Gemini pass merges over-segmented beats into semantically coherent ones.

```python
class Beat(BaseModel):
    beat_id: str
    recording_id: str
    span: TimeSpan                       # exact seconds
    kind: Literal["explain", "derive", "example", "question",
                  "recap", "aside", "admin"]
    speech: list[Utterance]
    board_state_id: str | None           # which BoardState was live
    board_delta: BBox | None             # what changed on the board here
    deixis: list[Deixis]
    concepts: list[str]                  # filled by ATLAS
    salience: float                      # 0–1, teaching value
```

**The symmetry worth noticing:** this is the same unit the Nityam tutor *emits* when it teaches (see the Artifact Layer doc, §5.2 — `{say, artifact_op, cue}`). A captured Beat and a taught Beat have the same shape. Which means a captured Beat can be **replayed** directly as a taught Beat: same words, same board region highlighted, same order. That's not a coincidence you should design around later — it's the reason to define Beat this way now.

`kind: "admin"` is doing quiet work. Roughly 15% of a real class is attendance, homework instructions, and *"beta, please sit down."* Classify it, keep it in the Reel, exclude it from the Atlas.

### 3.8 ⑦ GLYPH — read the board

**In:** `BoardState[]` (composited), `unfilled` masks. **Out:** `BoardContent`.

One `gemini-3.5-flash` call per board state at `media_resolution: high`. Typically 8–20 states per lecture, so this is the expensive-per-call / cheap-in-total half of the two-pass cost strategy.

Output is structured — layout regions, not a flat string:

```json
{
  "regions": [
    { "id": "r1", "bbox": [0.05,0.10,0.48,0.22], "kind": "equation",
      "latex": "x^2 + 6x + 5", "role": "problem_statement", "confidence": 0.94 },
    { "id": "r2", "bbox": [0.05,0.24,0.55,0.36], "kind": "equation",
      "latex": "= x^2 + 6x + \\left(\\tfrac{6}{2}\\right)^2 - \\left(\\tfrac{6}{2}\\right)^2 + 5",
      "role": "derivation_step", "step_index": 1, "derives_from": "r1" },
    { "id": "r5", "bbox": [0.60,0.10,0.95,0.40], "kind": "figure",
      "description": "area model, square split into four labelled rectangles" },
    { "id": "r6", "bbox": [0.05,0.70,0.40,0.80], "kind": "unreadable",
      "reason": "occluded throughout state" }
  ]
}
```

The prompt must include: *"Regions shaded grey were never visible in the source video. Emit them as `kind: unreadable`. Do not infer their contents."*

**Why not Mathpix?** Cost (6× more), accuracy (it made semantic substitution errors like `5` → `\overline{0}` in a published benchmark), and — decisively — it does literal transcription with no context. Gemini can be told *"this is a Class 9 algebra lesson on completing the square"* and will resolve ambiguous handwriting using that context. On messy handwriting a contextual reader beats a literal one by a wide margin (one 2026 study: 84% vs 55% acceptable transcriptions on a hard subset).

### 3.9 ⑧ ATLAS — build the concept map

**In:** `Beat[]`, `BoardContent`, optional curriculum spine (NCERT chapter list). **Out:** `ConceptGraph`.

Three sequential sub-passes, all with strict JSON schemas:

**(a) Concept mining.** Per beat: which concepts are *taught* (introduced/explained) vs merely *mentioned*? Normalize against the curriculum spine when one is supplied — this is what stops you accumulating `completing the square`, `complete the square`, and `square completion` as three nodes.

**(b) Relation extraction.** Edge types, deliberately few:

| Edge | Meaning | Source |
|---|---|---|
| `REQUIRES` | prerequisite | teaching order + explicit callbacks (*"remember we did…"*) |
| `PART_OF` | sub-concept | hierarchy |
| `EXEMPLIFIES` | worked example → concept | example beats |
| `CONTRASTS_WITH` | commonly confused pair | *"don't confuse this with…"* |
| `TAUGHT_IN` | concept → Beat | **every node has ≥1. Non-negotiable.** |

**(c) Misconception mining.** The highest-value and least-obvious extraction. Good teachers pre-empt errors out loud: *"bacchon, yahan sab galti karte hain — (x+3)² is NOT x²+9."* Each of these is a ready-made `Misconception` record for the learner model in the main architecture doc, complete with the correct understanding and the teacher's own phrasing for the remediation.

Extract them explicitly:

```json
{ "misconception": "treats (a+b)² as a²+b²",
  "teacher_phrasing": "yeh sabse common galti hai",
  "correct_understanding": "(a+b)² = a² + 2ab + b²",
  "pre_empted_at_beat": "beat_0034",
  "board_region": "r3" }
```

This is a genuine differentiator. Every AI tutor discovers misconceptions *after* the student makes the error. SHRUTI knows them *before the student opens the app*, because their own teacher warned about them.

---

## 4. The data model

```python
Recording  ─┬─ id (sha256)  source  duration  fps  surface_kind  created_at
            │
Timeline   ─┼─ shots[]  ink_curve  erase_events[]  sample_plan  writing_bursts[]
            │
BoardState ─┼─ id  recording_id  valid_from  valid_to  composited_uri
            │     unfilled_mask_uri  ink_coverage  content: BoardContent
            │
Utterance  ─┼─ id  span  text  speaker  language_spans[]  confidence
            │
Deixis     ─┼─ id  at  utterance_id  phrase  board_region  kind  referent_text
            │
Beat       ─┼─ id  span  kind  speech[]  board_state_id  board_delta
            │     deixis[]  concepts[]  salience
            │
Concept    ─┼─ id  canonical_name  aliases[]  grade  subject  chapter
            │     definition  taught_in: BeatRef[]        ← provenance, always
            │
Edge       ─┼─ from  to  type  weight  evidence: BeatRef[]  ← provenance, always
            │
Misconception ── id  statement  teacher_phrasing  correct_understanding
                 pre_empted_at: BeatRef  concept_id
```

**The invariant that governs everything:** *no semantic object exists without a `BeatRef` back to the Reel.* A concept you cannot point at a moment in a lecture is a concept you made up.

---

## 5. Storage — the question you actually asked

### 5.1 The answer

> **Timeline as ground truth. Graph as a projection. Vectors as an index.**
> **Three layers, one direction of dependency, and only one of them is expensive to rebuild.**

Neither a pure timeline nor a pure knowledge graph works alone, and the reason is that they fail on *different questions*:

| The student asks | Needs | Layer |
|---|---|---|
| *"Show me where sir explained this"* | exact timestamp + board image | **Reel** (temporal) |
| *"What was on the board when he said that?"* | state valid at time t | **Ledger** (bitemporal) |
| *"What do I need to know before this?"* | multi-hop prerequisite traversal | **Atlas** (graph) |
| *"Explain completing the square"* | semantic similarity, single-hop | **Index** (vector) |

A graph-only store cannot answer the first two. A timeline-only store cannot answer the third. Pick both.

### 5.2 The three layers

**L1 — THE REEL.** Immutable, append-only, the ground truth.
Every Beat with exact spans. Every Utterance. Every Deixis event. Object storage for board images and audio. Content-addressed by the recording's SHA-256.
*Never modified. Never deleted. Everything else is derived from it.*
→ Postgres tables + GCS.

**L2 — THE LEDGER.** Board states with validity intervals — bitemporal, in the database sense.
`(board_state_id, valid_from, valid_to, content)`. Answers "what was written at t=14:32" as a range query. Also answers "when did equation X first appear" and "was it ever erased," which is exactly the "content lifetime" the AccessMath line of research spends most of its effort computing — and which falls out of the ink curve for free.
→ Postgres with `tstzrange` + GiST index.

**L3 — THE ATLAS.** The concept graph. Mutable, versioned, **and deliberately cheap to throw away.**
Every node and edge cites Beat IDs. Because of that, a better extraction model next month means: re-run ATLAS against the cached Reel, write `atlas_version = 2`, keep v1 for comparison. **You never re-upload the video, never re-run Slate, never pay for the expensive passes again.**
→ Postgres edge tables. Not Neo4j — see §5.4.

**THE INDEX.** pgvector over Beat text and Concept definitions, in the same database.

```
     ┌──────────────────────────────────────────┐
     │  L3  ATLAS      concepts, edges, gaps    │  ← rebuildable in minutes
     │      cites ▼                             │
     ├──────────────────────────────────────────┤
     │  L2  LEDGER     board states over time   │  ← rebuildable in ~1 hour
     │      cites ▼                             │
     ├──────────────────────────────────────────┤
     │  L1  REEL       beats, speech, frames    │  ← IMMUTABLE. never rebuilt.
     └──────────────────────────────────────────┘
```

If that structure looks familiar it's because it's DeepTutor's L1/L2/L3 memory pyramid — *"L2 cites L1 and L3 cites L2, so nothing in your profile is unaccountable"* — pointed at **content** instead of at the learner. Nityam ends up with the same provenance discipline on both sides of the system: auditable claims about the subject, auditable claims about the student. For a product sold into schools, that symmetry is a feature you can put on a slide.

### 5.3 Retrieval: hybrid, routed by question type

The GraphRAG-vs-vector literature is now clear enough to be decisive: graph construction costs *substantially more* than vector indexing (GraphRAG averages ~5 LLM calls and 2,791 input tokens per chunk vs LightRAG's 1 call and 1,269 tokens), and graph retrieval has *higher* latency due to LLM-based entity expansion and multi-step traversal. Graph pays for itself only on multi-hop and relational queries — where it genuinely wins.

So route:

```python
async def retrieve(query: str, learner: LearnerProfile) -> Evidence:
    intent = await classify(query)          # flash-lite, ~80ms

    match intent:
        case "definition" | "explanation":
            return vector_search(query, k=8)                    # Index
        case "prerequisite" | "why_stuck" | "learning_path":
            return graph_traverse(query, depth=2)               # Atlas
        case "show_me_where" | "what_did_sir_say":
            return timeline_lookup(query)                       # Reel
        case "what_was_on_board":
            return ledger_at(query.timestamp)                   # Ledger
        case _:
            return hybrid(vector_search(query, k=5),
                          graph_traverse(query, depth=1))
```

`show_me_where` is the feature nobody else has. *"Sir ne yeh kab padhaya tha?"* → jump to 23:14, show the board state, replay 40 seconds. That is the deck's entire "classroom-grounded" claim, made literal.

### 5.4 Storage choices, and one you should resist

| Layer | Choice | Why not the obvious alternative |
|---|---|---|
| Reel + Ledger + Atlas + Index | **Postgres 16 + pgvector** (Cloud SQL) | One database. One backup story. One transaction boundary across all four layers. |
| Graph | **Edge tables + recursive CTEs** | **Not Neo4j.** Your graph is ~2,000 nodes per subject. Recursive CTEs handle 2-hop traversal in single-digit milliseconds at that scale. A second database is operational cost you cannot justify until ~100k nodes. |
| Board images, audio | **GCS**, content-addressed paths | |
| Local dev / analytics | **DuckDB** mirror | The one thing `sense` got completely right: `CREATE VIEW v_timeline` with formatted timecodes makes debugging a pipeline enormously faster. Keep it. |
| Index | **pgvector**, `gemini-embedding-2` | Gemini File Search is tempting (managed chunking + citations) but you can't tune retrieval or inspect scores, and Beat-level chunking is domain-specific enough that you want control. |

### 5.5 Updating

**Content-addressed, versioned, never destructive.**

```
Same video re-uploaded          → SHA match → no-op
Better ASR model                → re-run ECHO → reel_version++, WEAVE onward re-derives
Better extraction prompt        → re-run ATLAS only → atlas_version++
Teacher corrects a transcript   → human_override row; overrides always win, and are
                                  never overwritten by a re-run
New lecture, same chapter       → new Recording; ATLAS merges into the existing
                                  concept graph, deduplicating by canonical_name
```

Re-indexing writes a **new version directory and keeps the prior one** — a working index is never destroyed mid-rebuild. (Straight from DeepTutor's KB versioning; it's a small discipline that saves you at 2am.)

---

## 6. Google ADK orchestration

### 6.1 Why ADK here, and where it stops

SHRUTI is a batch pipeline, not a conversation. Most of it is `ffmpeg`, `numpy` and API calls — code, not agents. **Do not agentify what a function call does better.**

ADK earns its place in exactly three spots:

1. **Orchestration with durable state.** A 45-minute lecture takes 10–20 minutes to process. Containers restart. `DatabaseSessionService` + a state machine means you resume from the last completed stage instead of paying for the whole run again.
2. **The judgement calls.** Beat segmentation, concept normalization, misconception mining — genuinely agentic, benefit from tools and retries.
3. **The handoff to the tutor.** LENS exposes ADK tools that the live tutoring agent calls. Same framework both sides, one session store, no glue.

### 6.2 The pipeline agent

```python
from google.adk.agents import SequentialAgent, ParallelAgent, LlmAgent
from google.adk.tools import LongRunningFunctionTool
from google.adk.models import Gemini

REASONER = "gemini-3.5-flash"
ROUTER   = "gemini-3.5-flash-lite"

# ── Stages 1–2: deterministic, wrapped as tools ────────────────────
gate  = LlmAgent(name="Gate",  model=Gemini(model=ROUTER),
                 instruction="Admit the recording. Probe, normalize, fingerprint, "
                             "classify the writing surface. Report the Recording.",
                 tools=[probe_video, normalize_video, fingerprint, classify_surface],
                 output_key="recording")

pulse = LlmAgent(name="Pulse", model=Gemini(model=ROUTER),
                 instruction="Build the temporal spine for {recording}. "
                             "Detect shots, compute the ink curve, find erase events, "
                             "emit an adaptive sample plan.",
                 tools=[detect_shots, compute_ink_curve, find_erase_events,
                        build_sample_plan],
                 output_key="timeline")

# ── Stages 3–5: independent → run concurrently ─────────────────────
slate = LlmAgent(name="Slate", model=Gemini(model=ROUTER),
                 instruction="Recover clean board states for each interval in "
                             "{timeline}. If compositing fails, degrade gracefully "
                             "and report which states are unrecoverable.",
                 tools=[LongRunningFunctionTool(func=composite_board_states)],
                 output_key="board_states")

echo  = LlmAgent(name="Echo",  model=Gemini(model=REASONER),
                 instruction=ECHO_TRANSCRIPT_PROMPT,
                 tools=[transcribe_audio, align_subtitle_prior],
                 output_key="utterances")

point = LlmAgent(name="Point", model=Gemini(model=REASONER),
                 instruction="Resolve deictic references at gesture moments "
                             "in {timeline}. Return normalized board coordinates.",
                 tools=[resolve_deixis],
                 output_key="deixis")

perceive = ParallelAgent(name="Perceive", sub_agents=[slate, echo, point])

# ── Stages 6–8: fusion and semantics ───────────────────────────────
weave = LlmAgent(name="Weave", model=Gemini(model=REASONER),
                 instruction=WEAVE_PROMPT, output_key="beats")
glyph = LlmAgent(name="Glyph", model=Gemini(model=REASONER),
                 instruction=GLYPH_PROMPT, tools=[read_board_state],
                 output_key="board_content")
atlas = SequentialAgent(name="Atlas",
                        sub_agents=[concept_miner, relation_extractor,
                                    misconception_miner])

shruti = SequentialAgent(
    name="Shruti",
    sub_agents=[gate, pulse, perceive, weave, glyph, atlas, vault_writer],
)
```

### 6.3 Durability

Same pattern as the long-running-agents guidance in the main architecture doc:

```python
class Stage:
    ADMITTED = "ADMITTED";   SPINED   = "SPINED"
    PERCEIVED = "PERCEIVED"; WOVEN    = "WOVEN"
    READ = "READ";           MAPPED   = "MAPPED";  SHELVED = "SHELVED"
```

Each stage writes `state["stage"]` via `ToolContext.state` — every write is an automatic checkpoint against `DatabaseSessionService`. Kill the container mid-Slate, restart, and it resumes at `SPINED` without re-transcribing.

Wrap `composite_board_states` in `LongRunningFunctionTool` — it's minutes of CPU work and must not block the agent loop.

### 6.4 Plugins

```python
class ProvenancePlugin(BasePlugin):
    """Every LLM call that produces a semantic object records its inputs.
       Reproducibility is not optional in an education KB."""
    async def after_model_callback(self, *, callback_context, llm_response):
        await reel.record_derivation(
            stage=callback_context.agent_name,
            model=llm_response.model_version,
            prompt_hash=hash_of(llm_response.request),
            output_ref=llm_response.id,
        )

class CostGuardPlugin(BasePlugin):
    """Hard ceiling per recording. $150 of credits is finite."""
    async def before_model_callback(self, *, callback_context, llm_request):
        if self.spend[callback_context.invocation_id] > MAX_COST_PER_RECORDING:
            return LlmResponse(error="cost_ceiling_exceeded")
```

### 6.5 Where it runs

| Component | Service | Note |
|---|---|---|
| Orchestrator + API | **Cloud Run** (CPU) | scales to zero between uploads |
| Slate worker | **Cloud Run Jobs** (CPU v1, GPU when SAM 3 lands) | separate image, separate scaling |
| Stage handoff | **Pub/Sub** | one topic per stage; retries and DLQ for free |
| Database | **Cloud SQL Postgres 16 + pgvector** | |
| Objects | **GCS** | |
| Tracing | **Cloud Trace** (on by default via `agents-cli`) | spans per LLM call and tool execution |
| Deploy | `agents-cli scaffold enhance --deployment-target cloud_run` → `agents-cli deploy` | |

---

## 7. Evaluation

Judges and, later, schools will ask "how do you know it's right?" Four cheap instruments:

| # | What | How | Target |
|---|---|---|---|
| **E1** | Board recovery | Hand-annotate 20 board states across 3 lectures. Measure connected-component recall against ground truth — the AccessMath metric. | ≥ 85% CC recall |
| **E2** | Transcript fidelity | 10 minutes of code-mixed audio, hand-transcribed. Measure WER **and** script-fidelity (fraction of English words correctly kept in Latin script). | WER < 15%, script fidelity > 90% |
| **E3** | Extraction | 3 lectures with a hand-built gold concept graph. Precision/recall on concepts and on `REQUIRES` edges. | Concept F1 > 0.75, edge precision > 0.80 |
| **E4** | Provenance | Automated invariant check: **100% of Concept and Edge rows have ≥1 valid BeatRef resolving to a real span.** | 100%, enforced in CI |

E4 is not a quality metric, it's a correctness assertion, and it should fail the build. Adopt the paper's evaluation split too — objective fields by exact match, subjective fields by BERTScore — because grading a generated chapter summary by string equality tells you nothing.

---

## 8. Cost, against your $150

Per 45-minute lecture, Gemini 3.5 Flash at $1.50/1M input, $9/1M output:

| Pass | Tokens | Standard | **Batch (50% off)** |
|---|---|---|---|
| ECHO — audio, 2,700s × 32 tok/s | 86k in | $0.13 | **$0.07** |
| Coarse video pass — `media_resolution: low`, ~100 tok/s | 270k in | $0.41 | **$0.20** |
| GLYPH — 15 board states, high res | ~40k in, 15k out | $0.20 | **$0.10** |
| POINT — 40 clips × 5s | ~60k in | $0.09 | **$0.05** |
| WEAVE + ATLAS — 3 structured passes | ~120k in, 40k out | $0.54 | **$0.27** |
| **Per lecture** | | **$1.37** | **$0.69** |

With context caching on the extraction schema (**cache reads at 10% of input rate**), the ATLAS line drops further.

**$150 ÷ $0.69 ≈ 215 lectures.** More than enough — you'll run out of *annotated evaluation data* long before you run out of credits.

Four rules that keep it there:
1. **Batch everything.** SHRUTI is offline by definition. There is no user waiting. Every call goes through the Batch API. This is a free 50%.
2. **Two-resolution discipline.** `low` for the whole video, `high` for the ~15 composited stills. Never `high` on 2,700 frames.
3. **Cache the schema.** ~4k tokens of extraction schema, identical on every call, at 10% of the rate.
4. **Route trivia to Flash-Lite.** Surface classification, beat-kind labelling, dedup. Roughly 40% of calls by count, ~3% by cost.

---

## 9. Risks

| # | Risk | Likelihood | Mitigation |
|---|---|---|---|
| R1 | Slate produces garbage on a real Indian classroom (poor light, moving camera, dusty board) | **High** | Test on real footage in week 1, not on AccessMath. Three-tier fallback (§3.4). `unfilled` mask so we never hallucinate. |
| R2 | Gemini hallucinates board content in occluded regions | **High** | The `unfilled` mask is passed into the prompt as an explicit no-guess instruction. Spot-check E1. |
| R3 | Concept graph drifts — same concept, three node names | Medium | Canonicalize against a curriculum spine (NCERT chapter list); dedup by embedding similarity > 0.92 before insert. |
| R4 | SAM 3 GPU setup eats the sprint | Medium | **Don't start there.** V1 is CPU-only by design. |
| R5 | Code-mixed transcript degrades on heavy accent + room noise | Medium | Subtitle prior when available; Sarvam / Whisper-Hinglish fine-tunes as a documented fallback |
| R6 | 1 FPS misses fast writing | Low | Custom `fps` on `videoMetadata` for writing bursts; PULSE already knows where they are |
| R7 | YouTube ToS / copyright on ingested lectures | **Medium, and real** | For the demo use openly-licensed lectures (NPTEL, Khan Academy) or your own recordings. Don't build the pitch on scraping. |

---

## Appendix — Sources

**Video understanding** — `ai.google.dev/gemini-api/docs/video-understanding`; Interactions API video guide (1 FPS default, MM:SS timestamps, `media_resolution`, YouTube URLs, 1hr default / 3hr low-res); media-resolution and token-calculation guides.

**Multi-model extraction** — Zheng, Chen, Liu, Ye & Lin, *Towards structured knowledge extraction from lecture videos via multi-model collaboration*, Expert Systems With Applications 311 (2026) 131402. Ablations Tables 2–5; dual-threshold sampling §3.2; prompt-engineering effect §4.3.

**Board content extraction** — AccessMath project (DPRL, U. Buffalo) and `bhargavaurala/accessmath-icfhr2018`; Kota et al., *Automated Detection of Handwritten Whiteboard Content in Lecture Videos for Summarization* (ICFHR 2018); *Automated Whiteboard Lecture Video Summarization by Content Region Detection and Representation*; *Whiteboard Video Summarization via Spatio-Temporal Conflict Minimization*.

**Segmentation** — Meta SAM 2 (Apache-2.0) and SAM 3 / SAM 3.1 (`facebookresearch/sam3`, Nov 2025 / Mar 2026); Promptable Concept Segmentation; HF `Sam3VideoModel`.

**Scene detection** — PySceneDetect `AdaptiveDetector`, `ContentDetector`, `HistogramDetector` (`scenedetect.com`).

**OCR** — Rivin, *Math OCR Benchmark: Why Gemini Flash Beats Mathpix* (Gemini 3 Flash $0.004/page vs Mathpix $0.025/page); *Automated Grading of Handwritten Mathematics Using Vision-Capable LLMs* (arXiv 2605.19043, 95% rubric accuracy, 87% of errors from transcription); *Evaluating AI Grading on Real-World Handwritten College Mathematics* (arXiv 2603.00895, 84% vs 55% on hard subset).

**Code-mixed ASR** — *UrduSpeech* (arXiv 2605.17846: Whisper-large-v3 fails on code-switching by transliterating; Gemini outperforms); `openai/whisper` discussion #2761 (no romanized-Hinglish flag); HiACC corpus (DIB 2025); Deepgram Hinglish WER survey (26.97–69.53%); Oriserve Whisper-Hindi2Hinglish; Trelis Whisper-Hinglish-Preview.

**Knowledge representation** — Microsoft GraphRAG; LightRAG (HKU); KG²RAG (arXiv 2502.06864, construction-cost table); *RAG vs GraphRAG: A Systematic Evaluation* (arXiv 2502.11371); *Inferring Prerequisite Knowledge Concepts in Educational Knowledge Graphs* (arXiv 2509.05393); *A systematic literature review of knowledge graph construction and application in education* (Heliyon 2024).

**Cost** — Gemini Batch API (50% off all models, ≤24h); context caching (90% discount on cached input, Gemini 2.5+); Flex/Priority tiers.

**Prior art in your uploads** — `sense` skill (subtitle parsing, ffmpeg frame extraction, DuckDB timeline views — adopted; GF(3) trit layer — not adopted, §0.3).

---

*Draft v0.1. Decisions D1–D3 in §0.2 are the ones to confirm before coding. Implementation detail lives in the companion doc.*