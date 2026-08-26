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
