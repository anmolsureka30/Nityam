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
