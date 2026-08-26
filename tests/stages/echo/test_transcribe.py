import json
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
