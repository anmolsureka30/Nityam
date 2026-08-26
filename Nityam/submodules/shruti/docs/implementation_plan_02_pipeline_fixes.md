# Shruti pipeline correctness & efficiency fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four real, evidenced bugs found during the storage/pipeline
redesign review — PULSE and POINT both do real work for surface kinds where
that work is meaningless or wasted, GLYPH's slide-sampling drastically
undersamples continuous-shot video, and `relations.py`/`concepts.py`
disagree on concept identity so `Relations extracted: 0` on every real run
regardless of content. This is Plan 1 of 3 from
`shruti_storage_and_pipeline_redesign_design.md` — the other two (knowledge
storage/wiki generation, ECHO's Whisper swap) are separate plans since
they're independent subsystems; this one stands alone and ships working,
testable software on its own.

**Architecture:** Extract the pure, deterministic logic currently inlined in
`shruti/ingest.py` (an explicitly untested, exploratory orchestrator — see
its own module docstring) into small, focused, independently unit-testable
functions in the relevant stage packages. `ingest.py` becomes a thinner
caller. No new dependencies, no schema changes, no interface changes to
`Utterance`/`Beat`/`Concept`/`Edge`.

**Tech Stack:** Python 3.12, pytest + pytest-asyncio, existing FakeClient
test pattern (see `tests/stages/atlas/test_relations.py` for the pattern
this plan's tests follow), numpy, existing `shruti.contracts.*` Pydantic
models.

**Spec:** `shruti_storage_and_pipeline_redesign_design.md` §3 (pipeline
stage changes — PULSE/POINT/GLYPH/relations.py bullets). The embedding fix
also mentioned in that section is already done (`shruti/config.py`,
verified live) and has no task here.

## Global Constraints

- The full test suite must stay green after every task: `uv run --env-file .env python -m pytest -q` from the repo root. It is 105/105 passing before this plan starts.
- Do not touch `.local/` — it's per-run debug/observability output, gitignored, unrelated to this plan.
- Follow the existing `FakeResponse`/`FakeClient` test-double pattern already used in `tests/stages/atlas/*.py` for any test touching a `client.models.generate_content` call — do not introduce a different mocking approach.
- No behavior change for `blackboard`/`whiteboard` surface_kind recordings anywhere in this plan — every fix here only changes behavior for `slides`/`mixed`/`talking_head`, or fixes something (relations.py) that was already broken for all surface kinds identically.
- Commit after each task, not each step within a task.

---

### Task 1: `is_physical_board` predicate, wired into POINT's gate

**Files:**
- Modify: `shruti/contracts/recording.py`
- Modify: `tests/contracts/test_contracts.py` (this repo keeps one test file per contracts module — do not create a new file)
- Modify: `shruti/ingest.py:78` (import), `shruti/ingest.py:289`, `shruti/ingest.py:298` (reuse in the two existing inline checks — same condition, currently duplicated three times counting POINT), `shruti/ingest.py:412-435` (POINT section)

**Interfaces:**
- Produces: `is_physical_board(surface_kind: SurfaceKind | str) -> bool` in `shruti/contracts/recording.py`, importable as `from shruti.contracts.recording import is_physical_board`. Task 2 and Task 3 both consume this.

- [ ] **Step 1: Write the failing test**

Add to `tests/contracts/test_contracts.py` (it already imports `Recording, SurfaceKind` from `shruti.contracts.recording` at the top — extend that import):

```python
def test_is_physical_board_true_only_for_blackboard_and_whiteboard():
    from shruti.contracts.recording import is_physical_board
    assert is_physical_board(SurfaceKind.BLACKBOARD) is True
    assert is_physical_board(SurfaceKind.WHITEBOARD) is True
    assert is_physical_board(SurfaceKind.SLIDES) is False
    assert is_physical_board(SurfaceKind.MIXED) is False
    assert is_physical_board(SurfaceKind.TALKING_HEAD) is False
    # Also accepts a plain string, since ingest.py mostly carries
    # recording.surface_kind.value (a str) rather than the enum member.
    assert is_physical_board("blackboard") is True
    assert is_physical_board("slides") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --env-file .env python -m pytest tests/contracts/test_contracts.py::test_is_physical_board_true_only_for_blackboard_and_whiteboard -v`
Expected: FAIL with `ImportError: cannot import name 'is_physical_board'`

- [ ] **Step 3: Implement `is_physical_board`**

In `shruti/contracts/recording.py`, add after the `SurfaceKind` class (before `Recording`):

```python
def is_physical_board(surface_kind: "SurfaceKind | str") -> bool:
    """True only for the two surface kinds with an actual physical board to
    rectify, occlusion-mask, and gesture-track (blackboard/whiteboard).
    False for slides/mixed/talking_head, where GLYPH reads frames directly
    and there's nothing for PULSE's board-quad tracking or POINT's
    gesture-pointing to attach to — see
    memory_nityam_architecture/README.md's Phase 0.5 "Resolved" notes."""
    value = surface_kind.value if isinstance(surface_kind, SurfaceKind) else surface_kind
    return value in ("blackboard", "whiteboard")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --env-file .env python -m pytest tests/contracts/test_contracts.py::test_is_physical_board_true_only_for_blackboard_and_whiteboard -v`
Expected: PASS

- [ ] **Step 5: Wire into `shruti/ingest.py`**

In the import block, change:

```python
from shruti.contracts.recording import Recording
```

to:

```python
from shruti.contracts.recording import Recording, is_physical_board
```

Replace the two existing inline checks (no behavior change — same condition, now shared):

At `shruti/ingest.py:289`, replace:
```python
    if recording.surface_kind.value in ("blackboard", "whiteboard"):
```
with:
```python
    if is_physical_board(recording.surface_kind):
```

At `shruti/ingest.py:298`, replace:
```python
        if recording.surface_kind.value in ("blackboard", "whiteboard"):
```
with:
```python
        if is_physical_board(recording.surface_kind):
```

Then replace the whole POINT section (currently `shruti/ingest.py:412-435`):

```python
    print()
    print("=" * 70)
    print(f"POINT (capped at {POINT_CAP} utterances to bound API cost)")
    print("=" * 70)
    art.start_stage("05_point")
    deixis_list = []
    deixis_debug = []
    for u in utterances[:POINT_CAP]:
        clip = sample_frames_at(normalized_video_path, [max(0, u.start_s - 0.5), u.start_s, u.end_s])
        if not clip:
            continue
        art.save_image_series("05_point", f"clip_{u.id}", clip)
        try:
            d = resolve_deixis(client, clip, u)
        except Exception as e:
            gaps.append(f"POINT failed on utterance {u.id}: {e!r}")
            d = None
        deixis_debug.append({"utterance_id": u.id, "utterance_text": u.text,
                              "found": d is not None, "deixis": d.model_dump() if d else None})
        if d:
            deixis_list.append(d)
    art.save_json("05_point", "deixis_results", deixis_debug)
    art.end_stage("05_point")
    print(f"Gestures found: {len(deixis_list)} (out of {min(POINT_CAP, len(utterances))} checked)")
```

with:

```python
    print()
    print("=" * 70)
    art.start_stage("05_point")
    deixis_list = []
    if is_physical_board(recording.surface_kind):
        print(f"POINT (capped at {POINT_CAP} utterances to bound API cost)")
        print("=" * 70)
        deixis_debug = []
        for u in utterances[:POINT_CAP]:
            clip = sample_frames_at(normalized_video_path, [max(0, u.start_s - 0.5), u.start_s, u.end_s])
            if not clip:
                continue
            art.save_image_series("05_point", f"clip_{u.id}", clip)
            try:
                d = resolve_deixis(client, clip, u)
            except Exception as e:
                gaps.append(f"POINT failed on utterance {u.id}: {e!r}")
                d = None
            deixis_debug.append({"utterance_id": u.id, "utterance_text": u.text,
                                  "found": d is not None, "deixis": d.model_dump() if d else None})
            if d:
                deixis_list.append(d)
        art.save_json("05_point", "deixis_results", deixis_debug)
        print(f"Gestures found: {len(deixis_list)} (out of {min(POINT_CAP, len(utterances))} checked)")
    else:
        print(f"POINT (surface_kind={recording.surface_kind.value!r} — skipped: no physical "
              f"board region for gesture-pointing to attach to, and GLYPH already reads slide "
              f"content directly)")
        print("=" * 70)
    art.end_stage("05_point")
```

Note `deixis_list = []` is set before the branch either way, so the downstream `fuse_beats(client, recording.id, boundaries, utterances, board_states, deixis_list)` call keeps working unchanged whether POINT ran or was skipped.

- [ ] **Step 6: Run the full suite**

Run: `uv run --env-file .env python -m pytest -q`
Expected: 106 passed (105 + this task's new test), same as before plus one.

- [ ] **Step 7: Commit**

```bash
git add shruti/contracts/recording.py shruti/ingest.py tests/contracts/test_contracts.py
git commit -m "feat: add is_physical_board predicate, skip POINT for non-board surface kinds"
```

---

### Task 2: Extract PULSE's board-signal computation, gate it by surface kind

**Files:**
- Create: `shruti/stages/pulse/board_signal.py`
- Test: `tests/stages/pulse/test_board_signal.py`
- Modify: `shruti/ingest.py` (imports, PULSE section `shruti/ingest.py:238-263`)

**Interfaces:**
- Consumes: `is_physical_board` from Task 1 (`shruti.contracts.recording`); existing `locate_board(frames: list) -> tuple` (`shruti.stages.slate.locate`); `ink_curve(sampled: list, quad, polarity: str) -> np.ndarray` (`shruti.stages.pulse.ink`); `find_erase_events(curve, times, drop_ratio: float = 0.35, window_s: float = 3.0) -> list[EraseEvent]` (`shruti.stages.pulse.erase`); `build_sample_plan(shots: list[Shot], erase_events: list[EraseEvent], duration_s: float, dense_fps: float, sparse_fps: float) -> list[SamplePlanRegion]` (`shruti.stages.pulse.plan`).
- Produces: `BoardSignal` dataclass (`quad`, `curve: np.ndarray`, `erase_events: list[EraseEvent]`, `sample_plan: list[SamplePlanRegion]`) and `compute_board_signal(surface_kind: str, shots: list[Shot], coarse_frames: list, coarse_times: list[float], duration_s: float, drop_ratio: float, window_s: float, dense_fps: float, sparse_fps: float) -> BoardSignal` in `shruti/stages/pulse/board_signal.py`. Task 3 does not consume this (separate concern); ingest.py's WEAVE section keeps consuming `curve` and `shots` exactly as it does today (`candidate_boundaries(utterances, curve, coarse_times.tolist(), shots)` at `shruti/ingest.py:442`) — this task does not change that call.

- [ ] **Step 1: Write the failing tests**

Create `tests/stages/pulse/test_board_signal.py`:

```python
import numpy as np
from shruti.contracts.timeline import Shot
from shruti.stages.pulse.board_signal import compute_board_signal


def test_compute_board_signal_skips_board_detection_for_slides():
    shots = [Shot(start_s=0.0, end_s=100.0)]
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    signal = compute_board_signal(
        "slides", shots, coarse_frames=[frame], coarse_times=[0.0],
        duration_s=100.0, drop_ratio=0.35, window_s=3.0,
        dense_fps=1.0, sparse_fps=1 / 6,
    )
    assert signal.quad is None
    assert signal.curve.size == 0
    assert signal.erase_events == []
    assert signal.sample_plan == []


def test_compute_board_signal_skips_for_mixed_and_talking_head_too():
    shots = [Shot(start_s=0.0, end_s=10.0)]
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    for kind in ("mixed", "talking_head"):
        signal = compute_board_signal(
            kind, shots, coarse_frames=[frame], coarse_times=[0.0],
            duration_s=10.0, drop_ratio=0.35, window_s=3.0,
            dense_fps=1.0, sparse_fps=1 / 6,
        )
        assert signal.quad is None
        assert signal.sample_plan == []


def test_compute_board_signal_returns_empty_when_no_frames_sampled():
    shots = [Shot(start_s=0.0, end_s=10.0)]
    signal = compute_board_signal(
        "blackboard", shots, coarse_frames=[], coarse_times=[],
        duration_s=10.0, drop_ratio=0.35, window_s=3.0,
        dense_fps=1.0, sparse_fps=1 / 6,
    )
    assert signal.quad is None
    assert signal.curve.size == 0
    assert signal.sample_plan == []
```

(Board-detection *correctness* for real blackboard frames — `locate_board`'s
own CV logic — is already covered by `tests/stages/slate/test_locate.py`;
these tests only need to verify the surface_kind gate, not re-verify
`locate_board` itself.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --env-file .env python -m pytest tests/stages/pulse/test_board_signal.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shruti.stages.pulse.board_signal'`

- [ ] **Step 3: Implement `compute_board_signal`**

Create `shruti/stages/pulse/board_signal.py`:

```python
from dataclasses import dataclass, field

import numpy as np

from shruti.contracts.recording import is_physical_board
from shruti.contracts.timeline import EraseEvent, SamplePlanRegion, Shot
from shruti.stages.pulse.erase import find_erase_events
from shruti.stages.pulse.ink import ink_curve
from shruti.stages.pulse.plan import build_sample_plan
from shruti.stages.slate.locate import locate_board


@dataclass
class BoardSignal:
    quad: object | None
    curve: np.ndarray
    erase_events: list[EraseEvent] = field(default_factory=list)
    sample_plan: list[SamplePlanRegion] = field(default_factory=list)


def _empty_signal() -> BoardSignal:
    return BoardSignal(quad=None, curve=np.array([]), erase_events=[], sample_plan=[])


def compute_board_signal(
    surface_kind: str,
    shots: list[Shot],
    coarse_frames: list,
    coarse_times: list[float],
    duration_s: float,
    drop_ratio: float,
    window_s: float,
    dense_fps: float,
    sparse_fps: float,
) -> BoardSignal:
    """Board-quad location, ink-curve tracking, and erase-event detection
    only make sense for a physical chalkboard/whiteboard. For slides or
    talking-head content there's nothing to rectify or erase — running this
    unconditionally wasted real compute and produced a misleading "erase
    events" signal on content that was never a board (confirmed on a real
    slides-video run). Skip the whole sub-path for non-board surface kinds."""
    if not is_physical_board(surface_kind) or not coarse_frames:
        return _empty_signal()
    quad = locate_board(coarse_frames)
    if quad is None:
        return _empty_signal()
    polarity = "bright_on_dark" if surface_kind == "blackboard" else "dark_on_bright"
    curve = ink_curve(coarse_frames, quad, polarity)
    erase_events = find_erase_events(curve, coarse_times, drop_ratio=drop_ratio, window_s=window_s)
    sample_plan = build_sample_plan(shots, erase_events, duration_s, dense_fps, sparse_fps)
    return BoardSignal(quad=quad, curve=curve, erase_events=erase_events, sample_plan=sample_plan)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --env-file .env python -m pytest tests/stages/pulse/test_board_signal.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Wire into `shruti/ingest.py`**

In the import block, remove these now-unused-at-call-site imports (they move into `board_signal.py`):
```python
from shruti.stages.slate.locate import locate_board
from shruti.stages.pulse.ink import ink_curve
from shruti.stages.pulse.erase import find_erase_events
from shruti.stages.pulse.plan import build_sample_plan
```
and add:
```python
from shruti.stages.pulse.board_signal import compute_board_signal
```

Replace `shruti/ingest.py:238-263` (from `quad = locate_board(coarse_frames)...` through the end of the PULSE section, i.e. up to but not including the blank line before `print(); print("="*70); print("ECHO")`):

```python
    quad = locate_board(coarse_frames) if coarse_frames else None
    if quad is not None and coarse_frames:
        art.save_json("01_pulse", "board_quad", {"quad": [list(p) for p in quad]})
        draw_quad_overlay(coarse_frames[-1], quad, art.stage_dir("01_pulse") / "board_quad_overlay.jpg")

    polarity = "bright_on_dark" if recording.surface_kind.value == "blackboard" else "dark_on_bright"
    if quad is not None and coarse_frames:
        curve = ink_curve(coarse_frames, quad, polarity)
        erase_events = find_erase_events(
            curve, coarse_times.tolist(),
            drop_ratio=PulseConfig().erase_drop_ratio, window_s=PulseConfig().erase_window_s,
        )
    else:
        curve, erase_events = np.array([]), []
    art.save_json("01_pulse", "erase_events", [e.model_dump() for e in erase_events])
    art.save_json("01_pulse", "ink_curve", {"times": coarse_times.tolist(), "values": curve.tolist()})
    draw_ink_curve(coarse_times.tolist(), curve, erase_events, art.stage_dir("01_pulse") / "ink_curve.jpg")
    print(f"Erase events detected: {len(erase_events)}")

    sample_plan = build_sample_plan(
        shots, erase_events, recording.duration_s,
        PulseConfig().dense_fps, PulseConfig().sparse_fps,
    )
    art.save_json("01_pulse", "sample_plan", [r.model_dump() for r in sample_plan])
    art.end_stage("01_pulse")
    print(f"Sample plan regions: {len(sample_plan)}")
```

with:

```python
    pulse_cfg = PulseConfig()
    signal = compute_board_signal(
        recording.surface_kind.value, shots, coarse_frames, coarse_times.tolist(),
        recording.duration_s, pulse_cfg.erase_drop_ratio, pulse_cfg.erase_window_s,
        pulse_cfg.dense_fps, pulse_cfg.sparse_fps,
    )
    quad, curve, erase_events, sample_plan = signal.quad, signal.curve, signal.erase_events, signal.sample_plan
    if quad is not None and coarse_frames:
        art.save_json("01_pulse", "board_quad", {"quad": [list(p) for p in quad]})
        draw_quad_overlay(coarse_frames[-1], quad, art.stage_dir("01_pulse") / "board_quad_overlay.jpg")
    art.save_json("01_pulse", "erase_events", [e.model_dump() for e in erase_events])
    art.save_json("01_pulse", "ink_curve", {"times": coarse_times.tolist(), "values": curve.tolist()})
    draw_ink_curve(coarse_times.tolist(), curve, erase_events, art.stage_dir("01_pulse") / "ink_curve.jpg")
    if is_physical_board(recording.surface_kind):
        print(f"Erase events detected: {len(erase_events)}")
        art.save_json("01_pulse", "sample_plan", [r.model_dump() for r in sample_plan])
        print(f"Sample plan regions: {len(sample_plan)}")
    else:
        print("Board-quad/erase/sample-plan detection skipped (no physical board for this surface_kind)")
    art.end_stage("01_pulse")
```

`quad`, `curve`, `erase_events`, and `sample_plan` remain defined with the
same names and same empty-value fallback (`curve = np.array([])`) as
before, so nothing downstream (WEAVE's `candidate_boundaries(utterances,
curve, coarse_times.tolist(), shots)` at `shruti/ingest.py:442`, and the
`if quad is not None` check just above the SLATE/GLYPH branch) needs to
change.

- [ ] **Step 6: Run the full suite**

Run: `uv run --env-file .env python -m pytest -q`
Expected: all passing, same count as after Task 1.

- [ ] **Step 7: Commit**

```bash
git add shruti/stages/pulse/board_signal.py tests/stages/pulse/test_board_signal.py shruti/ingest.py
git commit -m "fix: skip PULSE board-quad/erase detection for non-board surface kinds"
```

---

### Task 3: Fix GLYPH's slide-sampling undersampling with periodic sampling

**Files:**
- Create: `shruti/stages/pulse/slide_sampling.py`
- Test: `tests/stages/pulse/test_slide_sampling.py`
- Modify: `shruti/ingest.py` (imports, the `else` branch of the SLATE+GLYPH section, currently `shruti/ingest.py:344-361`)

**Interfaces:**
- Consumes: `Shot` (`shruti.contracts.timeline`).
- Produces: `compute_slide_sample_spans(shots: list[Shot], duration_s: float, interval_s: float = 25.0) -> list[tuple[float, float]]` in `shruti/stages/pulse/slide_sampling.py`. `ingest.py`'s slide loop (`for i, (from_s, to_s) in enumerate(spans):`) consumes this directly — same tuple shape as before, so nothing past the sampling itself needs to change.

- [ ] **Step 1: Write the failing tests**

Create `tests/stages/pulse/test_slide_sampling.py`:

```python
from shruti.contracts.timeline import Shot
from shruti.stages.pulse.slide_sampling import compute_slide_sample_spans


def test_single_long_shot_gets_periodic_samples_not_just_two_points():
    # This is the exact real-world case that motivated the fix: an 18-minute
    # (1129.7s) lecture with continuous screen recording registered as a
    # single PULSE shot, so the old shot-cut-only logic sampled only 2
    # points (start + one midpoint) for the whole video.
    shots = [Shot(start_s=0.0, end_s=1129.7)]
    spans = compute_slide_sample_spans(shots, duration_s=1129.7, interval_s=25.0)
    assert len(spans) >= 40  # 1129.7 / 25 ~= 45
    assert spans[0][0] == 0.0
    assert spans[-1][1] == 1129.7
    for start, end in spans:
        assert end - start <= 25.0 + 1e-6
        assert end > start


def test_short_shots_keep_one_sample_each_no_extra_periodic_points():
    shots = [Shot(start_s=0.0, end_s=5.0), Shot(start_s=5.0, end_s=12.0)]
    spans = compute_slide_sample_spans(shots, duration_s=12.0, interval_s=25.0)
    assert [start for start, _ in spans] == [0.0, 5.0]
    assert spans[-1] == (5.0, 12.0)


def test_spans_are_contiguous_and_cover_the_full_duration():
    shots = [Shot(start_s=0.0, end_s=60.0)]
    spans = compute_slide_sample_spans(shots, duration_s=60.0, interval_s=25.0)
    for (_, end), (next_start, _) in zip(spans, spans[1:]):
        assert end == next_start
    assert spans[0][0] == 0.0
    assert spans[-1][1] == 60.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --env-file .env python -m pytest tests/stages/pulse/test_slide_sampling.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shruti.stages.pulse.slide_sampling'`

- [ ] **Step 3: Implement `compute_slide_sample_spans`**

Create `shruti/stages/pulse/slide_sampling.py`:

```python
from shruti.contracts.timeline import Shot


def compute_slide_sample_spans(
    shots: list[Shot], duration_s: float, interval_s: float = 25.0,
) -> list[tuple[float, float]]:
    """Sample points for reading slide/talking-head content directly (no
    physical board to rectify — see is_physical_board). Shot cuts alone
    under-sample real content: a continuous screen recording with no hard
    scene cuts registers as a single shot regardless of how many times the
    visible slide actually changed. Confirmed on a real 1129.7s lecture: 1
    detected shot, which the old shot-cut-only logic turned into 2 samples
    for the whole video. Merge shot-cut points with periodic samples every
    `interval_s` seconds so a long continuous shot still gets real
    coverage."""
    points = {0.0} | {s.start_s for s in shots}
    for s in shots:
        t = s.start_s
        while t + interval_s < s.end_s:
            t += interval_s
            points.add(t)
    sample_points = sorted(points)
    return list(zip(sample_points, sample_points[1:] + [duration_s]))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --env-file .env python -m pytest tests/stages/pulse/test_slide_sampling.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Wire into `shruti/ingest.py`**

In the import block, add:
```python
from shruti.stages.pulse.slide_sampling import compute_slide_sample_spans
```

Near the top of the file, next to `POINT_CAP = 6`, add:
```python
SLIDE_SAMPLE_INTERVAL_S = 25.0  # see compute_slide_sample_spans's docstring
```

Replace `shruti/ingest.py:344-361` (the comment block plus the
`sample_points_set = ...` through the `print(f"Sampling {len(spans)}...")`
lines):

```python
            # No physical board: a screen-recorded/rendered slide is already
            # flat, nothing to rectify and nothing occluding it the way a
            # teacher occludes a chalkboard. Sample one frame per shot
            # boundary (plus a midpoint for any shot longer than 30s, since
            # scene detection under-fires on smooth animated transitions —
            # see memory_nityam_architecture/README.md's Phase 0.5 notes),
            # and read each directly. This produces multiple BoardStates,
            # one per slide, instead of one degenerate state for the whole
            # video.
            sample_points_set = {0.0} | {s.start_s for s in shots}
            for s in shots:
                if s.end_s - s.start_s > 30.0:
                    sample_points_set.add((s.start_s + s.end_s) / 2)
            sample_points = sorted(sample_points_set)
            spans = list(zip(sample_points, sample_points[1:] + [recording.duration_s]))
            print(f"Sampling {len(spans)} slide state(s) at: "
                  f"{[round(t, 1) for t in sample_points]}")
```

with:

```python
            # No physical board: a screen-recorded/rendered slide is already
            # flat, nothing to rectify and nothing occluding it the way a
            # teacher occludes a chalkboard. Sample shot-cut points plus
            # periodic points every SLIDE_SAMPLE_INTERVAL_S seconds — shot
            # cuts alone under-sample continuous screen recordings (see
            # compute_slide_sample_spans's docstring). This produces
            # multiple BoardStates, one per sampled span, instead of one
            # degenerate state for the whole video.
            spans = compute_slide_sample_spans(
                shots, recording.duration_s, interval_s=SLIDE_SAMPLE_INTERVAL_S,
            )
            print(f"Sampling {len(spans)} slide state(s) at: "
                  f"{[round(start, 1) for start, _ in spans]}")
```

The rest of the loop (`for i, (from_s, to_s) in enumerate(spans):` onward)
is unchanged — `spans` has the same `list[tuple[float, float]]` shape as
before.

- [ ] **Step 6: Run the full suite**

Run: `uv run --env-file .env python -m pytest -q`
Expected: all passing, same count as after Task 2.

- [ ] **Step 7: Commit**

```bash
git add shruti/stages/pulse/slide_sampling.py tests/stages/pulse/test_slide_sampling.py shruti/ingest.py
git commit -m "fix: periodic slide sampling so continuous-shot videos get real coverage"
```

---

### Task 4: Fix `relations.py`/`concepts.py` concept-identity mismatch

**Files:**
- Modify: `shruti/stages/atlas/relations.py`
- Modify: `tests/stages/atlas/test_relations.py` (replace the existing test — see Step 1 note)

**Interfaces:**
- No signature change: `extract_relations(client, concepts: list[Concept], beats: list[Beat]) -> list[Edge]` keeps the same signature. `shruti/ingest.py`'s call site (`edges = extract_relations(client, concepts, beats) if len(concepts) >= 2 else []`) is unchanged — this task needs no `ingest.py` edit.

**Context for the implementer:** `concepts.py`'s `mine_concepts` sets
`Concept.id` to a slugified `canonical_name` (`row["canonical_name"].lower().replace(" ", "_")`).
`relations.py`'s prompt sends the model human-readable `canonical_name`
values (via `concept_names = [c.canonical_name for c in concepts]`) and
asks for `from_concept`/`to_concept` — the model naturally echoes back
names, not slugs. Today those raw names flow straight into
`Edge.from_concept`/`Edge.to_concept` unchanged. `shruti/ingest.py` already
has a defensive filter right after calling `extract_relations`
(`edges = [e for e in edges if e.from_concept in valid_ids and e.to_concept in valid_ids and e.evidence]`,
where `valid_ids = {c.id for c in concepts}`) — since a raw canonical name
practically never equals its own slug, that filter silently drops every
edge, every time. This is why every real run so far has printed
`Relations extracted: 0` regardless of content — not a crash, a silent
100% drop rate. Fix it inside `extract_relations` itself by resolving the
model's returned names back to the real concept ids before constructing
`Edge` objects, so `ingest.py`'s existing filter has real ids to check
against.

- [ ] **Step 1: Replace the existing test with tests that actually exercise name resolution**

The current test in `tests/stages/atlas/test_relations.py` doesn't catch
this bug — its fixture payload happens to set `to_concept` to a string that
already looks like an id (`"completing_the_square"`), so it never actually
checks resolution against `canonical_name`. Replace the whole file:

```python
import json
from shruti.stages.atlas.relations import extract_relations
from shruti.contracts.atlas import Concept, BeatRef
from shruti.contracts.beat import Beat


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeClient:
    def __init__(self, payload):
        self._payload = payload

    class _Models:
        def __init__(self, outer):
            self._outer = outer

        def generate_content(self, model, contents, config=None):
            return FakeResponse(json.dumps(self._outer._payload))

    @property
    def models(self):
        return FakeClient._Models(self)


def test_extract_relations_resolves_canonical_names_to_concept_ids():
    # The model is prompted with, and returns, human-readable
    # canonical_name values (see _RELATIONS_PROMPT) — not the slugified
    # concept.id used as the FK target in concept_edge.
    payload = [{"from_concept": "factoring", "to_concept": "completing the square",
                "edge_type": "REQUIRES", "evidence_beat_ids": ["b1"]}]
    client = FakeClient(payload)
    concepts = [
        Concept(id="factoring", canonical_name="factoring",
                taught_in=[BeatRef(beat_id="b0", relation="taught_in")]),
        Concept(id="completing_the_square", canonical_name="completing the square",
                taught_in=[BeatRef(beat_id="b1", relation="taught_in")]),
    ]
    beats = [Beat(id="b1", recording_id="r1", idx=1, start_s=5.0, end_s=10.0,
                  kind="derive", transcript="this needs factoring first")]
    edges = extract_relations(client, concepts, beats)
    assert len(edges) == 1
    assert edges[0].from_concept == "factoring"
    assert edges[0].to_concept == "completing_the_square"
    assert edges[0].edge_type == "REQUIRES"
    assert edges[0].evidence[0].beat_id == "b1"
    assert edges[0].evidence[0].relation == "evidence_for"


def test_extract_relations_is_case_insensitive_on_name_matching():
    payload = [{"from_concept": "Factoring", "to_concept": "Completing The Square",
                "edge_type": "REQUIRES", "evidence_beat_ids": []}]
    client = FakeClient(payload)
    concepts = [
        Concept(id="factoring", canonical_name="factoring"),
        Concept(id="completing_the_square", canonical_name="completing the square"),
    ]
    edges = extract_relations(client, concepts, [])
    assert edges[0].from_concept == "factoring"
    assert edges[0].to_concept == "completing_the_square"


def test_extract_relations_skips_edges_naming_an_unknown_concept():
    # The model can hallucinate a name that isn't in the concepts it was
    # given — skip that edge rather than write a dangling reference.
    payload = [{"from_concept": "factoring", "to_concept": "a concept never mined",
                "edge_type": "REQUIRES", "evidence_beat_ids": []}]
    client = FakeClient(payload)
    concepts = [Concept(id="factoring", canonical_name="factoring")]
    edges = extract_relations(client, concepts, [])
    assert edges == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --env-file .env python -m pytest tests/stages/atlas/test_relations.py -v`
Expected: FAIL — `test_extract_relations_resolves_canonical_names_to_concept_ids` and the case-insensitive test fail because `edges[0].to_concept` is currently the raw string `"completing the square"`/`"Completing The Square"`, not `"completing_the_square"`; the unknown-concept test fails because the current code doesn't skip anything, so `edges` has one entry instead of zero.

- [ ] **Step 3: Fix `extract_relations`**

In `shruti/stages/atlas/relations.py`, replace the whole `extract_relations` function:

```python
def extract_relations(client, concepts: list[Concept], beats: list[Beat]) -> list[Edge]:
    concept_names = [c.canonical_name for c in concepts]
    beats_text = "\n".join(f"[{b.id}] {b.transcript}" for b in beats)
    response = client.models.generate_content(
        model=Models().reasoner,
        contents=[_RELATIONS_PROMPT.format(concepts=concept_names, beats=beats_text)],
        config={"response_mime_type": "application/json"},
    )
    rows = json.loads(response.text)
    # concept_edge.from_concept/to_concept are FKs into concept.id, which is
    # a slugified canonical_name (see concepts.py's mine_concepts) — but the
    # model is prompted with, and returns, human-readable canonical_name
    # values, not ids. Resolve by name (case-insensitive) rather than
    # assuming the model's returned string already matches the id; every
    # real run before this fix produced "Relations extracted: 0" for
    # exactly this reason (ingest.py's own valid_ids filter silently
    # dropped every edge since a raw name never equals its own slug).
    name_to_id = {c.canonical_name.lower(): c.id for c in concepts}
    edges = []
    for row in rows:
        from_id = name_to_id.get(row["from_concept"].lower())
        to_id = name_to_id.get(row["to_concept"].lower())
        if from_id is None or to_id is None:
            continue
        edges.append(Edge(
            id=str(uuid.uuid4()),
            from_concept=from_id,
            to_concept=to_id,
            edge_type=row["edge_type"],
            evidence=[BeatRef(beat_id=bid, relation="evidence_for")
                      for bid in row["evidence_beat_ids"]],
        ))
    return edges
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --env-file .env python -m pytest tests/stages/atlas/test_relations.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full suite**

Run: `uv run --env-file .env python -m pytest -q`
Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add shruti/stages/atlas/relations.py tests/stages/atlas/test_relations.py
git commit -m "fix: resolve concept names to ids in relations.py so edges actually persist"
```

---

## After this plan

Update `memory_nityam_architecture/README.md`: move gap #3 (relations.py/
concepts.py identity mismatch) from "Known gaps" to "Resolved," correcting
the "FK violation" framing to the actual observed symptom (silent 0-edge
result via `ingest.py`'s own defensive filter). Move the PULSE/POINT
undersampling and gating items out of the design doc's TODO state — they're
part of what `shruti_storage_and_pipeline_redesign_design.md` §3 already
describes as agreed, this plan is what implements it.

Then re-run the full pipeline once against one of the two already-downloaded
test videos (`.local/videos/d_jnEkwCA6I.mp4` or `.local/videos/b6c87594bb.mp4`)
to confirm end to end: POINT is skipped and prints the skip message for the
slides video, PULSE no longer prints a misleading "Erase events detected,"
GLYPH samples significantly more than 2 slide states for the 18-minute
video, and `Relations extracted:` is nonzero if the video's concepts have
any real prerequisite/part-of relationship between them.
