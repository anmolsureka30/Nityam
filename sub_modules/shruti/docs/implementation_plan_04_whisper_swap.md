# Shruti ECHO engine swap: Gemini → local Whisper — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ECHO's Gemini-based transcription with a local
`faster-whisper` model. Two motivations, both real: cost (ECHO has been up
to ~50% of a run's total wall-clock time, all billed API calls, across
every real run this session) and reliability (ECHO's Gemini-based
single-shot transcription has produced non-deterministic timestamps across
identical repeated calls, and — confirmed again this session — a beat
`end_s` over 1600 seconds past a video's actual duration). This is Plan 3
of 3 from `shruti_storage_and_pipeline_redesign_design.md`. Independent of
Plan 2 (knowledge storage) — touches a completely different part of the
pipeline (audio transcription vs. concept/board content storage), no
shared files.

**Architecture:** `faster-whisper`'s `WhisperModel` (large-v3, int8,
CPU) replaces the Gemini `generate_content` call inside
`transcribe_audio`. The model is expensive to load (real disk I/O, a
multi-GB download on first use) and is built ONCE by the caller —
mirroring exactly how the Gemini `client` is already built once and
threaded through `run_ingest` — not instantiated inside `transcribe_audio`
itself, which keeps it swappable for a fake test double the same way the
Gemini client already is. `transcribe_audio` drops its `client` parameter
entirely (Whisper needs no Gemini client) and gains a `model` parameter in
its place. Every utterance is labeled `TEACHER` — Whisper does no speaker
diarization, and in every real run this session, 100% of transcribed
speech has been a single narrator (see the design doc's own rationale,
§4).

**Tech Stack:** Python 3.12, pytest, `faster-whisper==1.2.1` (verified
installable and resolves cleanly on this machine — arm64 Darwin — via
`uv add faster-whisper`, already added to `pyproject.toml`/`uv.lock`
ahead of this plan; Task 1 below commits that addition alongside its own
code). `faster-whisper`'s real API was verified directly against the
installed package (not assumed from training data) before writing this
plan — `WhisperModel.transcribe()` returns
`Tuple[Iterable[Segment], TranscriptionInfo]`, `Segment` has `.start`,
`.end`, `.text` (plus `.words` when `word_timestamps=True`), and there is
a real `multilingual: bool` parameter whose docstring reads "Perform
language detection on every segment" — exactly the setting needed for
code-mixed Hindi-English speech, verified via `help(WhisperModel.transcribe)`
against the installed package, not guessed at.

**Spec:** `shruti_storage_and_pipeline_redesign_design.md` §4 (ECHO
engine swap — model choice, speaker-labeling decision, fidelity
requirement).

## Global Constraints

- The full test suite must stay green after every task:
  `uv run --env-file .env python -m pytest -q` from the repo root.
- `transcribe_audio`'s tests must NOT load a real `WhisperModel` — that
  downloads multiple gigabytes and takes real wall-clock time, unsuitable
  for a unit test run on every `pytest` invocation. Use a fake test double
  matching `WhisperModel.transcribe`'s real interface (a `.transcribe(audio,
  **kwargs) -> (segments, info)` method), the same dependency-injection
  pattern already used for the Gemini `client` throughout this codebase
  (`FakeClient` in `tests/stages/atlas/*.py`, etc.).
- `build_whisper_model()` (the function that constructs a real
  `WhisperModel`) gets NO automated test — matches this codebase's
  existing convention that real external-resource construction (the
  Gemini client itself has no dedicated test either) isn't something CI
  exercises. It's proven working by the real-audio verification in this
  plan's own "After this plan" section, not a unit test.
- `Utterance`'s contract (`shruti/contracts/speech.py`) is unchanged by
  this plan — `speaker: Literal["TEACHER", "STUDENT", "UNKNOWN"]` already
  accepts `"TEACHER"`, `confidence: float | None = None` is already
  optional. No contract changes needed.
- Commit after each task, not each step within a task.

---

### Task 1: Rewrite `transcribe_audio` to use `faster-whisper`

**Files:**
- Modify: `shruti/stages/echo/transcribe.py`
- Modify: `tests/stages/echo/test_transcribe.py`
- Modify: `pyproject.toml`, `uv.lock` (the `faster-whisper` dependency
  addition already sitting uncommitted in the working tree from before
  this plan started — commit it here, alongside the code that actually
  uses it, rather than as an unrelated bystander change)

**Interfaces:**
- Produces: `build_whisper_model() -> WhisperModel` and
  `transcribe_audio(model, audio_path: str, recording_id: str) -> list[Utterance]`
  in `shruti/stages/echo/transcribe.py`. Task 2 (`ingest.py` wiring) calls
  both — `build_whisper_model()` once at the top of the run, and
  `transcribe_audio` with that model in place of today's
  `transcribe_audio(client, audio_path, recording.id)` call.

**Context for the implementer:** the CURRENT `transcribe_audio` takes a
Gemini `client` as its first parameter — this task removes that parameter
entirely and replaces it with `model` (the Whisper model). This is a
breaking signature change to an existing function; `shruti/ingest.py`'s
call site is NOT your concern — that's Task 2 in this same plan, which
runs after you and updates it. Your job is just to make
`shruti/stages/echo/transcribe.py` and its own test file correct and
self-consistent; leave `shruti/ingest.py` untouched (its current call to
the old signature will be broken until Task 2 lands — that's expected and
fine, Task 2 fixes it immediately after).

- [ ] **Step 1: Write the failing tests**

Replace the whole contents of `tests/stages/echo/test_transcribe.py`:

```python
from shruti.stages.echo.transcribe import transcribe_audio


class FakeSegment:
    def __init__(self, start, end, text):
        self.start = start
        self.end = end
        self.text = text


class FakeTranscriptionInfo:
    language = "hi"


class FakeWhisperModel:
    def __init__(self, segments):
        self._segments = segments

    def transcribe(self, audio, **kwargs):
        return iter(self._segments), FakeTranscriptionInfo()


def test_transcribe_audio_parses_segments_into_utterances(tmp_path):
    segments = [FakeSegment(0.0, 2.0, " अब हम iska derivative nikalenge ")]
    model = FakeWhisperModel(segments)
    audio_path = tmp_path / "fake.wav"
    audio_path.write_bytes(b"RIFF....WAVEfmt ")  # content is never inspected
    utterances = transcribe_audio(model, audio_path=str(audio_path), recording_id="r1")
    assert len(utterances) == 1
    assert utterances[0].text == "अब हम iska derivative nikalenge"
    assert utterances[0].speaker == "TEACHER"
    assert utterances[0].recording_id == "r1"
    assert utterances[0].start_s == 0.0
    assert utterances[0].end_s == 2.0


def test_transcribe_audio_skips_empty_segments():
    model = FakeWhisperModel([FakeSegment(0.0, 1.0, "   "), FakeSegment(1.0, 3.0, "real text")])
    utterances = transcribe_audio(model, audio_path="unused.wav", recording_id="r1")
    assert len(utterances) == 1
    assert utterances[0].text == "real text"


def test_transcribe_audio_calls_the_model_with_word_timestamps_and_multilingual():
    captured_kwargs = {}

    class CapturingModel(FakeWhisperModel):
        def transcribe(self, audio, **kwargs):
            captured_kwargs.update(kwargs)
            return super().transcribe(audio, **kwargs)

    model = CapturingModel([])
    transcribe_audio(model, audio_path="unused.wav", recording_id="r1")
    assert captured_kwargs.get("word_timestamps") is True
    assert captured_kwargs.get("multilingual") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --env-file .env python -m pytest tests/stages/echo/test_transcribe.py -v`
Expected: FAIL — the old `transcribe_audio(client, audio_path, recording_id)`
signature doesn't match how these tests call it (`transcribe_audio(model, ...)`
with a `FakeWhisperModel`, not a Gemini `FakeClient`), and it still tries
to call Gemini's `generate_content`-shaped interface on an object that
doesn't have one.

- [ ] **Step 3: Rewrite `transcribe_audio`**

Replace the whole contents of `shruti/stages/echo/transcribe.py`:

```python
import uuid

from faster_whisper import WhisperModel

from shruti.config import Models
from shruti.contracts.speech import Utterance


def build_whisper_model() -> WhisperModel:
    """Loads once per process — real model weights, real disk I/O, not
    something to call per-transcription. CPU + int8 quantization: this
    pipeline runs on a MacBook Air with no dedicated GPU, and int8 keeps
    inference tolerable there. large-v3 chosen over medium because
    code-mixed Hindi-English classroom speech is exactly the harder input
    where the larger model's accuracy gap matters most — see
    shruti_storage_and_pipeline_redesign_design.md §4.
    Models().whisper_model_size is a one-line override if real-world
    latency ever makes medium the better trade — no redesign needed."""
    return WhisperModel(Models().whisper_model_size, device="cpu", compute_type="int8")


def transcribe_audio(model, audio_path: str, recording_id: str) -> list[Utterance]:
    """model is a faster_whisper.WhisperModel (see build_whisper_model), or
    in tests, anything with a matching .transcribe(audio, **kwargs) ->
    (segments, info) interface. Every utterance is labeled TEACHER —
    Whisper does no speaker diarization on its own, and in every real run
    this pipeline has done, 100% of transcribed speech was a single
    narrator (see shruti_storage_and_pipeline_redesign_design.md §4).
    multilingual=True asks Whisper to detect language per segment rather
    than once for the whole file — the right setting for code-mixed
    Hindi-English speech (verified against the installed faster-whisper
    package's own docstring: "Perform language detection on every
    segment"). word_timestamps=True uses Whisper's cross-attention word
    alignment, expected to be materially more reliable than the previous
    single-shot JSON-timestamp-guessing approach — see the ECHO
    reliability gap this swap addresses in
    memory_nityam_architecture/README.md."""
    segments, _info = model.transcribe(audio_path, word_timestamps=True, multilingual=True)
    utterances = []
    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        utterances.append(Utterance(
            id=str(uuid.uuid4()),
            recording_id=recording_id,
            start_s=segment.start,
            end_s=segment.end,
            text=text,
            speaker="TEACHER",
        ))
    return utterances
```

Add `whisper_model_size: str = "large-v3"` to the `Models` class in
`shruti/config.py`. Find:
```python
class Models(BaseSettings):
    reasoner: str = "gemini-3.5-flash"
    router: str = "gemini-3.5-flash-lite"
    embedder: str = "gemini-embedding-001"
```
Replace with:
```python
class Models(BaseSettings):
    reasoner: str = "gemini-3.5-flash"
    router: str = "gemini-3.5-flash-lite"
    embedder: str = "gemini-embedding-001"
    whisper_model_size: str = "large-v3"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --env-file .env python -m pytest tests/stages/echo/test_transcribe.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full suite**

Run: `uv run --env-file .env python -m pytest -q`

Expected: some failures elsewhere are EXPECTED and CORRECT at this point
— `shruti/ingest.py:266` still calls the OLD `transcribe_audio(client,
audio_path, recording.id)` signature, which Task 2 (not yours) fixes
immediately after. Confirm the failures are limited to exactly that —
nothing under `tests/stages/echo/`, `tests/stages/atlas/`,
`tests/stages/pulse/`, `tests/stages/weave/`, `tests/stages/gate/`,
`tests/stages/point/`, `tests/stages/slate/`, `tests/vault/`, or
`tests/contracts/` should fail from this change, since none of those call
`transcribe_audio` directly. If you see failures anywhere else, that's a
real problem — investigate before reporting done, don't just note the
count and move on.

- [ ] **Step 6: Commit**

```bash
git add shruti/stages/echo/transcribe.py tests/stages/echo/test_transcribe.py shruti/config.py pyproject.toml uv.lock
git commit -m "feat: swap ECHO from Gemini to local faster-whisper (large-v3, int8)"
```

---

### Task 2: Wire the Whisper model through `run_ingest` and both entry points

**Files:**
- Modify: `shruti/ingest.py`
- Modify: `shruti/cli.py`
- Modify: `scripts/ingest_video.py`

**Interfaces:**
- Consumes: `build_whisper_model()`, `transcribe_audio(model, audio_path, recording_id)`
  (Task 1, `shruti.stages.echo.transcribe`).
- `run_ingest`'s signature changes: `run_ingest(video_path: str, client, whisper_model, subject=None, grade=None, chapter=None)` — `whisper_model` is a new required positional parameter, inserted right after `client` (mirrors how `client` itself is already a required, no-default parameter — Whisper is just as essential to a real run as Gemini is). No other plan or task in this codebase calls `run_ingest` — grepped the whole repo to confirm before writing this plan; the only two call sites are `shruti/cli.py` and `scripts/ingest_video.py`, both listed above.

- [ ] **Step 1: Update `run_ingest`'s signature and its `transcribe_audio` call**

In `shruti/ingest.py`, find:
```python
async def run_ingest(video_path: str, client, subject: str | None = None,
                      grade: int | None = None, chapter: str | None = None) -> dict:
```
Replace with:
```python
async def run_ingest(video_path: str, client, whisper_model, subject: str | None = None,
                      grade: int | None = None, chapter: str | None = None) -> dict:
```

Find (locate by content — this line is inside the ECHO section):
```python
    utterances = transcribe_audio(client, audio_path, recording.id)
```
Replace with:
```python
    utterances = transcribe_audio(whisper_model, audio_path, recording.id)
```

- [ ] **Step 2: Update `shruti/cli.py`'s `ingest` command**

Find:
```python
    from google import genai
    vertex_key = os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN")
    if not vertex_key and not os.environ.get("GOOGLE_API_KEY"):
        typer.echo("Neither GOOGLE_OAUTH_ACCESS_TOKEN nor GOOGLE_API_KEY is set — "
                   "add one to .env and run with `uv run --env-file .env shruti ingest`.")
        raise typer.Exit(code=1)
    client = genai.Client(vertexai=True, api_key=vertex_key) if vertex_key else genai.Client()

    from shruti.ingest import run_ingest
    asyncio.run(run_ingest(video_path, client, subject=subject, grade=grade, chapter=chapter))
```
Replace with:
```python
    from google import genai
    vertex_key = os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN")
    if not vertex_key and not os.environ.get("GOOGLE_API_KEY"):
        typer.echo("Neither GOOGLE_OAUTH_ACCESS_TOKEN nor GOOGLE_API_KEY is set — "
                   "add one to .env and run with `uv run --env-file .env shruti ingest`.")
        raise typer.Exit(code=1)
    client = genai.Client(vertexai=True, api_key=vertex_key) if vertex_key else genai.Client()

    from shruti.stages.echo.transcribe import build_whisper_model
    typer.echo("Loading Whisper model (first run downloads several GB) ...")
    whisper_model = build_whisper_model()

    from shruti.ingest import run_ingest
    asyncio.run(run_ingest(video_path, client, whisper_model, subject=subject,
                            grade=grade, chapter=chapter))
```

- [ ] **Step 3: Update `scripts/ingest_video.py`**

Find:
```python
from google import genai
from shruti.ingest import run_ingest


def build_client() -> genai.Client:
    vertex_key = os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN")
    return genai.Client(vertexai=True, api_key=vertex_key) if vertex_key else genai.Client()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video_path")
    parser.add_argument("--subject", default=None)
    parser.add_argument("--grade", type=int, default=None)
    parser.add_argument("--chapter", default=None)
    args = parser.parse_args()

    await run_ingest(args.video_path, build_client(), subject=args.subject,
                      grade=args.grade, chapter=args.chapter)
```
Replace with:
```python
from google import genai
from shruti.ingest import run_ingest
from shruti.stages.echo.transcribe import build_whisper_model


def build_client() -> genai.Client:
    vertex_key = os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN")
    return genai.Client(vertexai=True, api_key=vertex_key) if vertex_key else genai.Client()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video_path")
    parser.add_argument("--subject", default=None)
    parser.add_argument("--grade", type=int, default=None)
    parser.add_argument("--chapter", default=None)
    args = parser.parse_args()

    print("Loading Whisper model (first run downloads several GB) ...")
    whisper_model = build_whisper_model()

    await run_ingest(args.video_path, build_client(), whisper_model, subject=args.subject,
                      grade=args.grade, chapter=args.chapter)
```

- [ ] **Step 4: Run the full suite**

Run: `uv run --env-file .env python -m pytest -q`
Expected: all tests pass, including the ones Task 1 correctly left failing
(they call the old `transcribe_audio`/`run_ingest` signature only via
`shruti/ingest.py`'s own internal call, which this task fixes). Report the
exact final passed count — no test in this repo directly unit-tests
`run_ingest` itself (it's the untested exploratory orchestrator, per its
own module docstring), so this task adds no new tests; it's verified by
the suite staying green plus the real end-to-end run in this plan's "After
this plan" section.

- [ ] **Step 5: Commit**

```bash
git add shruti/ingest.py shruti/cli.py scripts/ingest_video.py
git commit -m "feat: wire the Whisper model into run_ingest and both CLI entry points"
```

---

## After this plan

This is the one place in the whole storage/pipeline redesign where a real
empirical check is not optional — the design doc itself flags fidelity on
code-mixed Hindi-English speech as "the one place the swap could regress
quality instead of just cost," and nothing in Tasks 1-2's unit tests (both
using fake model doubles, correctly) can validate that. Do this directly,
the same way ECHO's original reliability gap was diagnosed this session
(real audio, not mocks):

1. Run the real pipeline against one of the two already-downloaded test
   videos (`.local/videos/d_jnEkwCA6I.mp4` or `.local/videos/b6c87594bb.mp4`)
   via `uv run --env-file .env python scripts/ingest_video.py <path>`.
2. Read the resulting `04_echo/transcript.txt` directly and compare it
   against that SAME video's prior Gemini-based transcript, already saved
   from earlier this session (e.g. `.local/runs/bfa16f93c7/04_echo/transcript.txt`
   or `.local/runs/42f5598a9b/04_echo/transcript.txt` — find the run whose
   `00_gate/recording.json` `source_uri` matches the video used). Check
   specifically: is code-switched text (Hindi in Devanagari, English in
   Latin script, in the order actually spoken) preserved with comparable
   fidelity, or does Whisper's per-segment language detection distort it
   (e.g. transliterating English terms into Devanagari, or vice versa)?
   Are timestamps monotonically increasing with no hallucinated values
   past the video's real duration (the specific failure mode that
   motivated this swap)?
3. Report the comparison honestly. If fidelity has regressed in a way that
   matters, that's a real finding — the swap may need a different
   `multilingual`/`language` setting, or the `large-v3` vs `medium`
   tradeoff may need revisiting, and either should go through a fresh,
   short design conversation rather than being silently shipped or
   silently reverted.

Then update `memory_nityam_architecture/README.md`'s gap 4a (ECHO
reliability) — it currently says "Fix direction agreed, not yet
implemented"; update it to reflect what was actually built and what the
real-audio comparison in step 2 above found.
