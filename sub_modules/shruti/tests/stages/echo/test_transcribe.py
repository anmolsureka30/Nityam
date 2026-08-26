import json
import pytest
from shruti.stages.echo.transcribe import transcribe_audio


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


class FlakyThenGoodClient:
    """Returns malformed JSON on the first call, valid JSON on the second —
    simulates the real, confirmed failure mode (a large response breaking
    mid-document) recovering on retry."""

    def __init__(self, good_payload):
        self._good_payload = good_payload
        self._calls = 0

    class _Models:
        def __init__(self, outer):
            self._outer = outer

        def generate_content(self, model, contents, config=None):
            self._outer._calls += 1
            if self._outer._calls == 1:
                return FakeResponse('[{"start_s": 0.0, "end_s": 2.0 "text": "broken"}]')
            return FakeResponse(json.dumps(self._outer._good_payload))

    @property
    def models(self):
        return FlakyThenGoodClient._Models(self)


class AlwaysBrokenClient:
    class _Models:
        def generate_content(self, model, contents, config=None):
            return FakeResponse('[{"start_s": 0.0, "end_s": 2.0 "text": "broken"}]')

    @property
    def models(self):
        return AlwaysBrokenClient._Models()


def test_transcribe_audio_parses_structured_utterances(tmp_path):
    payload = [
        {"start_s": 0.0, "end_s": 2.0, "text": "अब हम iska derivative nikalenge",
         "speaker": "TEACHER", "confidence": 0.92},
    ]
    client = FakeClient(payload)
    audio_path = tmp_path / "fake.wav"
    audio_path.write_bytes(b"RIFF....WAVEfmt ")  # minimal placeholder bytes; content is never inspected
    utterances = transcribe_audio(client, audio_path=str(audio_path), recording_id="r1")
    assert len(utterances) == 1
    assert utterances[0].text == "अब हम iska derivative nikalenge"
    assert utterances[0].speaker == "TEACHER"
    assert utterances[0].recording_id == "r1"


def test_transcribe_audio_retries_once_on_malformed_json(tmp_path):
    payload = [{"start_s": 0.0, "end_s": 2.0, "text": "recovered on retry",
                "speaker": "TEACHER", "confidence": 0.9}]
    client = FlakyThenGoodClient(payload)
    audio_path = tmp_path / "fake.wav"
    audio_path.write_bytes(b"RIFF....WAVEfmt ")
    utterances = transcribe_audio(client, audio_path=str(audio_path), recording_id="r1")
    assert len(utterances) == 1
    assert utterances[0].text == "recovered on retry"
    assert client._calls == 2


def test_transcribe_audio_raises_the_real_error_if_both_attempts_fail(tmp_path):
    client = AlwaysBrokenClient()
    audio_path = tmp_path / "fake.wav"
    audio_path.write_bytes(b"RIFF....WAVEfmt ")
    with pytest.raises(json.JSONDecodeError):
        transcribe_audio(client, audio_path=str(audio_path), recording_id="r1")
