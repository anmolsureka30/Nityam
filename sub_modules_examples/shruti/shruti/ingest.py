"""Phase 0.5 exploratory orchestrator — first real end-to-end run of the
Shruti pipeline against a real video file, with full intermediate-artifact
capture so every stage's work is inspectable, not just the final printout.

Status: NOT a reviewed/tested Phase 0.5 implementation. No SDD process, no
unit tests, written directly under time pressure to prove the real stage
functions can be composed and produce real output against a real video.
Treat this as a working proof, not the hardened orchestrator Phase 0.5
should eventually be.

Every run writes a full artifact trace to `.local/runs/<slug>/`: every
sampled frame, the detected board quad drawn on a real frame, every
occlusion mask, the composited board image, an ink-curve plot, and a JSON
dump of every stage's structured output — see RunArtifacts below and
run_summary.md at the end of a run for the index.

Also see `shruti/vault/mirror.py` + `shruti timeline <recording_id>` for
the cross-modal (audio/board/gesture) sync view.

Known, evidenced gap (see memory_nityam_architecture/README.md's Phase 0.5
notes for the full writeup): ECHO's single-shot transcription is not
reliably accurate on ~4.5-minute audio — confirmed by calling it three
times against identical, verified-valid audio and getting three different
coverage/timestamp results. Not fixed here.

Deliberate simplifications from the full per-stage design, documented
where they diverge:
  - SLATE/GLYPH treat the WHOLE video as one board-state span, rather than
    windowing by erase events into multiple spans.
  - POINT (deixis) is capped at POINT_CAP utterances to bound API cost,
    rather than the full design's PULSE-flagged-gesture-moments approach.
    POINT only runs for blackboard/whiteboard recordings (is_physical_board);
    it's skipped entirely for the other three surface kinds.
  - Misconception concept_id grounding is fuzzy-matched after the fact
    (mine_misconceptions doesn't receive the mined concept list and can
    hallucinate a concept_id that doesn't exist).
"""
import difflib
import json
import time
import traceback
import uuid
from pathlib import Path

import cv2
import numpy as np

from shruti.db import get_pool, apply_migrations
from shruti.config import Models, PulseConfig
from shruti.contracts.recording import Recording, is_physical_board
from shruti.contracts.beat import Beat
from shruti.contracts.atlas import Concept, Edge, Misconception, BeatRef
from shruti.contracts.board import BoardState

from shruti.stages.gate.admit import admit
from shruti.stages.pulse.shots import detect_shots
from shruti.stages.pulse.board_signal import compute_board_signal
from shruti.stages.pulse.slide_sampling import compute_slide_sample_spans
from shruti.stages.slate.rectify import rectify
from shruti.stages.slate.mask import framediff_masks
from shruti.stages.slate.composite import composite_board_state
from shruti.stages.echo.transcribe import transcribe_audio
from shruti.stages.point.deixis import resolve_deixis
from shruti.stages.weave.boundaries import candidate_boundaries
from shruti.stages.weave.fuse import fuse_beats
from shruti.stages.glyph.read import read_board_state
from shruti.stages.atlas.concepts import mine_concepts
from shruti.stages.atlas.relations import extract_relations, filter_valid_edges
from shruti.stages.atlas.misconceptions import mine_misconceptions
from shruti.stages.atlas.canonicalize import canonicalize
from shruti.stages.atlas.embed import embed_concepts, embed_misconceptions

from shruti.vault.reel import write_recording, write_utterances, write_beats
from shruti.vault.ledger import write_board_state as vault_write_board_state
from shruti.vault.atlas_store import (
    write_concepts, write_edges, write_misconceptions, ProvenanceViolation,
)
from shruti.vault.narrative import build_recording_narrative
from shruti.vault.wiki import write_concept_wiki_page
from shruti.lens.citations import format_citation

POINT_CAP = 6  # cap deixis calls to bound API cost — see module docstring
SLIDE_SAMPLE_INTERVAL_S = 25.0  # see compute_slide_sample_spans's docstring
MAX_SLIDE_SAMPLES = 60  # bounds GLYPH calls for long videos — see below
NOTES_DIR = Path("vault/notes")  # per-recording narrative, git-tracked knowledge, not .local/ scratch
WIKI_DIR = Path("vault/wiki")  # per-concept pages, git-tracked knowledge, not .local/ scratch


class RunArtifacts:
    """Everything that happens in a run gets written here, organized by
    stage, so the pipeline's actual work is inspectable — not just its
    final printed summary. See module docstring."""

    def __init__(self, run_id: str):
        self.root = Path(".local/runs") / run_id
        self.root.mkdir(parents=True, exist_ok=True)
        self._stage_started_at: dict[str, float] = {}
        self.timing: dict[str, float] = {}
        self.stage_names: list[str] = []

    def stage_dir(self, stage: str) -> Path:
        d = self.root / stage
        d.mkdir(parents=True, exist_ok=True)
        return d

    def start_stage(self, stage: str) -> None:
        self.stage_names.append(stage)
        self._stage_started_at[stage] = time.monotonic()

    def end_stage(self, stage: str) -> None:
        started = self._stage_started_at.get(stage)
        if started is not None:
            self.timing[stage] = round(time.monotonic() - started, 2)

    def save_json(self, stage: str, name: str, data) -> Path:
        path = self.stage_dir(stage) / f"{name}.json"
        path.write_text(json.dumps(data, indent=2, default=str, ensure_ascii=False))
        return path

    def save_text(self, stage: str, name: str, text: str) -> Path:
        path = self.stage_dir(stage) / f"{name}.txt"
        path.write_text(text)
        return path

    def save_image(self, stage: str, name: str, img: np.ndarray) -> Path:
        path = self.stage_dir(stage) / f"{name}.jpg"
        cv2.imwrite(str(path), img)
        return path

    def save_image_series(self, stage: str, subdir: str, images: list) -> Path:
        d = self.stage_dir(stage) / subdir
        d.mkdir(parents=True, exist_ok=True)
        for i, img in enumerate(images):
            cv2.imwrite(str(d / f"{i:03d}.jpg"), img)
        return d


def draw_ink_curve(times: list, values: np.ndarray, erase_events: list, out_path: Path,
                    w: int = 1000, h: int = 300) -> None:
    """A plain line plot via cv2 — no matplotlib dependency."""
    canvas = np.full((h, w, 3), 255, dtype=np.uint8)
    if len(values) < 2 or float(values.max()) == 0:
        cv2.imwrite(str(out_path), canvas)
        return
    vmax = float(values.max())
    tmax = max(times[-1], 1e-6)
    pts = []
    for t, v in zip(times, values):
        x = int((t / tmax) * (w - 40)) + 20
        y = h - 20 - int((v / vmax) * (h - 40))
        pts.append((x, y))
    for a, b in zip(pts, pts[1:]):
        cv2.line(canvas, a, b, (180, 80, 0), 2)
    for e in erase_events:
        x = int((e.at_s / tmax) * (w - 40)) + 20
        cv2.line(canvas, (x, 10), (x, h - 10), (0, 0, 220), 1)
        cv2.putText(canvas, "erase", (x + 3, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 220), 1)
    cv2.putText(canvas, f"ink coverage over time (0-{tmax:.0f}s), red = detected erase events",
                (10, h - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
    cv2.imwrite(str(out_path), canvas)


def draw_quad_overlay(frame: np.ndarray, quad, out_path: Path) -> None:
    canvas = frame.copy()
    pts = np.array(quad, dtype=np.int32).reshape(-1, 1, 2)
    cv2.polylines(canvas, [pts], isClosed=True, color=(0, 0, 255), thickness=3)
    cv2.imwrite(str(out_path), canvas)


def sample_frames_at(video_path: str, timestamps: list) -> list:
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frames = []
    for t in timestamps:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
        ok, frame = cap.read()
        frames.append(frame if ok else None)
    cap.release()
    return [f for f in frames if f is not None]


def _remap_concept_id(raw_id: str, concepts: list[Concept]) -> str | None:
    """mine_misconceptions never sees the mined concept list, so its
    concept_id is frequently not a real id. Fuzzy-match against canonical
    names/ids; drop (return None) if nothing is close enough to trust."""
    if any(c.id == raw_id for c in concepts):
        return raw_id
    names = {c.canonical_name: c.id for c in concepts}
    match = difflib.get_close_matches(raw_id.replace("_", " "), names.keys(), n=1, cutoff=0.5)
    if match:
        return names[match[0]]
    ids = [c.id for c in concepts]
    match = difflib.get_close_matches(raw_id, ids, n=1, cutoff=0.5)
    return match[0] if match else None


async def run_ingest(video_path: str, client, subject: str | None = None,
                      grade: int | None = None, chapter: str | None = None) -> dict:
    """Run the full pipeline against a local video file. Prints progress
    and returns the run summary dict (also saved as run_summary.json)."""
    pool = await get_pool()
    await apply_migrations(pool)
    conn = await pool.acquire()

    gaps = []
    run_id = uuid.uuid4().hex[:10]
    art = RunArtifacts(run_id)
    workdir = str(art.root / "_work")
    Path(workdir).mkdir(parents=True, exist_ok=True)
    print(f"Run artifacts: {art.root}/")

    print()
    print("=" * 70)
    print("GATE")
    print("=" * 70)
    art.start_stage("00_gate")
    recording = admit(video_path, client, workdir)
    if subject:
        recording = recording.model_copy(update={"subject": subject})
    if grade:
        recording = recording.model_copy(update={"grade": grade})
    if chapter:
        recording = recording.model_copy(update={"chapter": chapter})
    await write_recording(conn, recording)
    normalized_video_path = str(Path(workdir) / "normalized.mp4")
    audio_path = str(Path(workdir) / "audio.wav")
    art.save_json("00_gate", "recording", recording.model_dump())
    art.end_stage("00_gate")
    print(f"Recording: {recording.id[:12]}... slug={recording.slug}")
    print(f"Duration: {recording.duration_s:.1f}s  Surface: {recording.surface_kind.value}")

    print()
    print("=" * 70)
    print("PULSE")
    print("=" * 70)
    art.start_stage("01_pulse")
    shots = detect_shots(normalized_video_path)
    art.save_json("01_pulse", "shots", [s.model_dump() for s in shots])
    print(f"Shots detected: {len(shots)}")

    coarse_times = np.linspace(0, recording.duration_s, num=min(40, max(4, int(recording.duration_s))))
    coarse_frames = sample_frames_at(normalized_video_path, coarse_times.tolist())
    art.save_image_series("01_pulse", "coarse_sampled_frames", coarse_frames)
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

    print()
    print("=" * 70)
    print("ECHO")
    print("=" * 70)
    art.start_stage("04_echo")
    utterances = transcribe_audio(client, audio_path, recording.id)
    await write_utterances(conn, utterances)
    art.save_json("04_echo", "utterances", [u.model_dump() for u in utterances])
    art.save_text("04_echo", "transcript",
                   "\n".join(f"[{u.start_s:7.2f}s] {u.speaker}: {u.text}" for u in utterances))
    art.end_stage("04_echo")
    print(f"Utterances transcribed: {len(utterances)}")
    for u in utterances[:5]:
        print(f"  [{u.start_s:6.1f}s] {u.speaker}: {u.text[:90]}")
    if len(utterances) > 5:
        print(f"  ... and {len(utterances) - 5} more — full transcript saved to "
              f"{art.stage_dir('04_echo')}/transcript.txt")

    def _transcript_excerpt(from_s: float, to_s: float) -> str:
        span = [u.text for u in utterances if u.start_s < to_s and u.end_s > from_s]
        return " ".join(span)[:800] or "(no speech in this span)"

    print()
    print("=" * 70)
    if is_physical_board(recording.surface_kind):
        print("SLATE + GLYPH (board-rectification path: locate/rectify/mask/composite)")
    else:
        print(f"SLATE + GLYPH (surface_kind={recording.surface_kind.value!r} — "
              f"not routed through board-rectification; reading raw representative "
              f"frames per slide instead — see is_physical_board's docstring)")
    print("=" * 70)
    art.start_stage("02_slate")
    board_states: list[BoardState] = []
    slide_sample_points: list[float] = []
    try:
        if is_physical_board(recording.surface_kind):
            # Real physical board: geometric rectification + occlusion masking
            # + directional compositing are the right tools here.
            if quad is None or not coarse_frames:
                raise ValueError("no frames sampled, cannot locate a board")
            rectified = [rectify(f, quad) for f in coarse_frames]
            art.save_image_series("02_slate", "rectified_frames", rectified)
            masks = framediff_masks(rectified)
            art.save_image_series("02_slate", "occlusion_masks",
                                   [(m.astype(np.uint8) * 255) for m in masks])
            target_idx = len(rectified) - 1
            composited, unfilled = composite_board_state(rectified, masks, target_idx, 0, len(rectified))
            art.save_image("02_slate", "composited_board", composited)
            art.save_image("02_slate", "unfilled_mask", unfilled.astype(np.uint8) * 255)
            composited_path = str(art.stage_dir("02_slate") / "composited_board.jpg")
            ink_coverage = float(curve[-1]) if len(curve) else None
            art.end_stage("02_slate")
            print(f"Board located at quad (overlay saved). Occlusion masks computed for {len(masks)} frames "
                  f"(unfilled fraction: {unfilled.mean():.1%})")

            art.start_stage("03_glyph")
            content = read_board_state(
                client, composited, unfilled,
                context={
                    "surface_kind": recording.surface_kind.value,
                    "grade": recording.grade or "unspecified",
                    "subject": recording.subject or "unspecified",
                    "chapter": recording.chapter or "unspecified",
                    "transcript_excerpt": _transcript_excerpt(0.0, recording.duration_s),
                },
            )
            art.save_json("03_glyph", "board_content_0", content.model_dump())
            bs = BoardState(
                id=f"{recording.id[:16]}_bs0", recording_id=recording.id, idx=0,
                valid_from_s=0.0, valid_to_s=recording.duration_s,
                composited_uri=f"file://{composited_path}", unfilled_uri=None,
                ink_coverage=ink_coverage, ended_by="end_of_video", content=content,
            )
            await vault_write_board_state(conn, bs)
            board_states.append(bs)
            art.end_stage("03_glyph")
            readable = [r for r in content.regions if r.kind != "unreadable"]
            print(f"Board regions extracted: {len(content.regions)} ({len(readable)} readable)")
            for r in content.regions[:8]:
                label = r.latex or r.plain_text or r.description or "(no text)"
                print(f"  [{r.kind}] {label[:80]}")
        else:
            # No physical board: a screen-recorded/rendered slide is already
            # flat, nothing to rectify and nothing occluding it the way a
            # teacher occludes a chalkboard. Sample shot-cut points plus
            # periodic points every SLIDE_SAMPLE_INTERVAL_S seconds — shot
            # cuts alone under-sample continuous screen recordings (see
            # compute_slide_sample_spans's docstring). This produces
            # multiple BoardStates, one per sampled span, instead of one
            # degenerate state for the whole video.
            # Widen the interval for long videos so total GLYPH calls stay
            # bounded — MAX_SLIDE_SAMPLES caps it the same way POINT_CAP
            # bounds POINT, without a hard cliff: a 2-hour lecture gets a
            # longer interval instead of silently stopping at sample 60.
            effective_interval_s = max(
                SLIDE_SAMPLE_INTERVAL_S, recording.duration_s / MAX_SLIDE_SAMPLES,
            )
            spans = compute_slide_sample_spans(
                shots, recording.duration_s, interval_s=effective_interval_s,
            )
            slide_sample_points = [start for start, _ in spans]
            print(f"Sampling {len(spans)} slide state(s) at: "
                  f"{[round(start, 1) for start, _ in spans]}")

            art.end_stage("02_slate")
            art.start_stage("03_glyph")
            for i, (from_s, to_s) in enumerate(spans):
                frame = sample_frames_at(normalized_video_path, [from_s])
                if not frame:
                    continue
                frame = frame[0]
                no_occlusion = np.zeros(frame.shape[:2], dtype=bool)
                art.save_image("03_glyph", f"slide_{i:02d}_raw", frame)
                try:
                    content = read_board_state(
                        client, frame, no_occlusion,
                        context={
                            "surface_kind": recording.surface_kind.value,
                            "grade": recording.grade or "unspecified",
                            "subject": recording.subject or "unspecified",
                            "chapter": recording.chapter or "unspecified",
                            "transcript_excerpt": _transcript_excerpt(from_s, to_s),
                        },
                    )
                except Exception as e:
                    gaps.append(f"GLYPH failed on slide {i} ({from_s:.1f}-{to_s:.1f}s): {e!r}")
                    continue
                art.save_json("03_glyph", f"slide_{i:02d}_content", content.model_dump())
                slide_path = str(art.stage_dir("03_glyph") / f"slide_{i:02d}_raw.jpg")
                bs = BoardState(
                    id=f"{recording.id[:16]}_bs{i}", recording_id=recording.id, idx=i,
                    valid_from_s=from_s, valid_to_s=to_s,
                    composited_uri=f"file://{slide_path}", unfilled_uri=None,
                    ink_coverage=None,
                    ended_by="end_of_video" if to_s >= recording.duration_s - 0.01 else "shot_cut",
                    content=content,
                )
                await vault_write_board_state(conn, bs)
                board_states.append(bs)
                readable = [r for r in content.regions if r.kind != "unreadable"]
                print(f"  slide {i} [{from_s:6.1f}-{to_s:6.1f}s]: {len(content.regions)} region(s), "
                      f"{len(readable)} readable")
                for r in content.regions[:4]:
                    label = r.latex or r.plain_text or r.description or "(no text)"
                    print(f"    [{r.kind}] {label[:70]}")
            art.end_stage("03_glyph")
            total_regions = sum(len(bs.content.regions) for bs in board_states if bs.content)
            print(f"Total: {len(board_states)} slide state(s), {total_regions} region(s) across all slides")
    except Exception as e:
        gaps.append(f"SLATE/GLYPH failed: {e!r}")
        art.save_json("02_slate", "failure", {"error": repr(e), "traceback": traceback.format_exc()})
        print(f"SLATE/GLYPH did not produce usable board content: {e!r}")

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
        print(f"POINT (surface_kind={recording.surface_kind.value!r} — skipped: not routed "
              f"through the board path (see is_physical_board's docstring); for slides/"
              f"talking_head GLYPH already reads content directly, and mixed recordings lose "
              f"gesture-pointing entirely today — a known, documented gap, not a design choice "
              f"for mixed specifically)")
        print("=" * 70)
    art.end_stage("05_point")

    print()
    print("=" * 70)
    print("WEAVE")
    print("=" * 70)
    art.start_stage("06_weave")
    boundaries = candidate_boundaries(utterances, curve, coarse_times.tolist(), shots,
                                       extra_boundaries=slide_sample_points)
    art.save_json("06_weave", "boundaries", boundaries)
    beats = fuse_beats(client, recording.id, boundaries, utterances, board_states, deixis_list)
    # fuse_beats accepts board_states but doesn't use them to set
    # board_state_id (confirmed by reading it) — do the temporal match here,
    # the same way the Ledger's own board_state_at query works: the state
    # whose [valid_from_s, valid_to_s) covers this beat's start.
    for b in beats:
        match = next((bs for bs in board_states if bs.valid_from_s <= b.start_s < bs.valid_to_s), None)
        if match:
            b.board_state_id = match.id
    await write_beats(conn, beats)
    art.save_json("06_weave", "beats", [b.model_dump() for b in beats])
    art.end_stage("06_weave")
    print(f"Beats fused: {len(beats)}")
    for b in beats:
        print(f"  [{b.start_s:6.1f}-{b.end_s:6.1f}s] {b.kind:8s} salience={b.salience}: {b.transcript[:70]}")

    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    narrative_path = NOTES_DIR / f"{recording.slug}.md"
    narrative_path.write_text(build_recording_narrative(recording, beats, board_states))
    print(f"Recording narrative written to {narrative_path}")

    print()
    print("=" * 70)
    print("ATLAS")
    print("=" * 70)
    art.start_stage("07_atlas")
    concepts_raw = mine_concepts(client, beats, curriculum_spine=[chapter] if chapter else None,
                                  board_states=board_states)
    art.save_json("07_atlas", "concepts_raw", [c.model_dump() for c in concepts_raw])
    concepts = canonicalize(concepts_raw)
    if subject or grade or chapter:
        concepts = [c.model_copy(update={"subject": subject, "grade": grade,
                                          "chapter": chapter}) for c in concepts]
    try:
        await write_concepts(conn, concepts)
    except ProvenanceViolation as e:
        gaps.append(f"ATLAS: {len(e.args[0])} concept(s) had no evidence, rejected: {e.args[0]}")
        concepts = [c for c in concepts if c.taught_in]
        if concepts:
            await write_concepts(conn, concepts)
    art.save_json("07_atlas", "concepts", [c.model_dump() for c in concepts])
    print(f"Concepts mined: {len(concepts)}")
    for c in concepts:
        cites = [format_citation(recording.slug, next(
            (b.start_s for b in beats if b.id == ref.beat_id), 0.0
        )) for ref in c.taught_in[:1]]
        print(f"  - {c.canonical_name}  [{', '.join(cites)}]")

    beat_ids = {b.id for b in beats}
    edges = extract_relations(client, concepts, beats) if len(concepts) >= 2 else []
    art.save_json("07_atlas", "relations_raw", [e.model_dump() for e in edges])
    valid_ids = {c.id for c in concepts}
    raw_edge_count = len(edges)
    edges = filter_valid_edges(edges, valid_ids, beat_ids)
    if raw_edge_count and len(edges) < raw_edge_count:
        gaps.append(f"ATLAS: {raw_edge_count - len(edges)} edge(s) dropped (unresolved concept, "
                     f"missing evidence, or evidence cited a beat id that doesn't exist)")
    if edges:
        try:
            await write_edges(conn, edges)
        except ProvenanceViolation as e:
            gaps.append(f"ATLAS: {len(e.args[0])} edge(s) rejected for missing evidence")
            edges = [e for e in edges if e.evidence]
    art.save_json("07_atlas", "relations", [e.model_dump() for e in edges])
    print(f"Relations extracted: {len(edges)}")
    for e in edges:
        print(f"  - {e.from_concept} --{e.edge_type}--> {e.to_concept}")

    misconceptions_raw = mine_misconceptions(client, beats)
    art.save_json("07_atlas", "misconceptions_raw", [m.model_dump() for m in misconceptions_raw])
    misconceptions = []
    for m in misconceptions_raw:
        remapped = _remap_concept_id(m.concept_id, concepts)
        if remapped and m.pre_empted_at_beat in beat_ids:
            misconceptions.append(m.model_copy(update={"concept_id": remapped}))
        else:
            reason = "no matching concept" if not remapped else "beat id not found"
            gaps.append(f"ATLAS: misconception {m.id} dropped ({reason}: concept_id={m.concept_id!r})")
    if misconceptions:
        await write_misconceptions(conn, misconceptions)
    art.save_json("07_atlas", "misconceptions", [m.model_dump() for m in misconceptions])
    art.end_stage("07_atlas")
    print(f"Misconceptions mined: {len(misconceptions)} (of {len(misconceptions_raw)} raw)")
    for m in misconceptions:
        beat = next((b for b in beats if b.id == m.pre_empted_at_beat), None)
        cite = format_citation(recording.slug, beat.start_s) if beat else "(no citation)"
        print(f"  - {m.statement}  [{cite}]")
        if m.teacher_phrasing:
            print(f"    teacher's words: \"{m.teacher_phrasing}\"")
        print(f"    correct: {m.correct_understanding}")

    # Wiki pages are written here, after both concepts AND misconceptions
    # are finalized — a misconception's verbatim teacher_phrasing belongs on
    # its concept's page (this is the one place in the whole pipeline that
    # keeps the teacher's exact words, per memory_layer.md §3.2's "nobody
    # else can do this" citation principle), and write_concept_wiki_page
    # needs the full misconceptions list to fold them into the right entry.
    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    for c in concepts:
        write_concept_wiki_page(WIKI_DIR, c, beats, board_states, recording.slug,
                                 misconceptions=misconceptions)
    print(f"Wiki pages updated in {WIKI_DIR}")

    print()
    print("=" * 70)
    print("Embedding into the vector index")
    print("=" * 70)
    art.start_stage("08_embeddings")
    try:
        if concepts:
            await embed_concepts(client, conn, concepts)
        if misconceptions:
            await embed_misconceptions(client, conn, misconceptions)
        print(f"Embedded {len(concepts)} concept(s), {len(misconceptions)} misconception(s)")
        art.save_json("08_embeddings", "status", {"ok": True, "concepts": len(concepts),
                                                    "misconceptions": len(misconceptions)})
    except Exception as e:
        gaps.append(f"Embedding failed: {e!r}")
        art.save_json("08_embeddings", "status", {"ok": False, "error": repr(e)})
        print(f"Embedding failed: {e!r}")
    art.end_stage("08_embeddings")

    await pool.release(conn)
    await pool.close()

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    summary = {
        "run_id": run_id,
        "recording_id": recording.id,
        "recording_slug": recording.slug,
        "citation_prefix": f"shruti:{recording.slug}",
        "concept_ids": [c.id for c in concepts],
        "counts": {
            "utterances": len(utterances), "beats": len(beats), "concepts": len(concepts),
            "relations": len(edges), "misconceptions": len(misconceptions),
        },
        "stage_timing_seconds": art.timing,
        "gaps": gaps,
        "artifact_dir": str(art.root),
    }
    art.save_json(".", "run_summary", summary)
    summary_md = [f"# Run {run_id} — shruti:{recording.slug}", "",
                  f"Duration: {recording.duration_s:.1f}s | Surface: {recording.surface_kind.value}", "",
                  "## Counts", ""]
    for k, v in summary["counts"].items():
        summary_md.append(f"- {k}: {v}")
    summary_md += ["", "## Stage timing (s)", ""]
    for stage in art.stage_names:
        summary_md.append(f"- {stage}: {art.timing.get(stage, '?')}")
    summary_md += ["", "## Artifact index", ""]
    for stage_dir in sorted(art.root.iterdir()):
        if stage_dir.is_dir() and stage_dir.name != "_work":
            files = sorted(p.name for p in stage_dir.rglob("*") if p.is_file())
            summary_md.append(f"- `{stage_dir.name}/` — {len(files)} file(s)")
    if gaps:
        summary_md += ["", f"## Known gaps hit ({len(gaps)})", ""]
        for g in gaps:
            summary_md.append(f"- {g}")
    art.save_text(".", "run_summary", "\n".join(summary_md))

    print(f"Recording: shruti:{recording.slug}")
    print(f"Utterances: {len(utterances)} | Beats: {len(beats)} | Concepts: {len(concepts)} | "
          f"Relations: {len(edges)} | Misconceptions: {len(misconceptions)}")
    print(f"Stage timing: {art.timing}")
    print(f"Full artifact trace: {art.root}/  (see run_summary.md for the index)")
    print(f"Cross-modal sync view: shruti timeline {recording.id}")
    if gaps:
        print()
        print(f"Known gaps hit during this run ({len(gaps)}):")
        for g in gaps:
            print(f"  - {g}")

    return summary
