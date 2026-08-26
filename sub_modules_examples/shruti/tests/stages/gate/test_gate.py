import hashlib
import shutil
import subprocess
import pytest
from shruti.contracts.recording import SurfaceKind
from shruti.stages.gate.probe import fingerprint
from shruti.stages.gate.surface import classify_surface
from shruti.stages.gate.admit import admit


def test_fingerprint_is_stable_sha256(tmp_path):
    f = tmp_path / "clip.bin"
    f.write_bytes(b"hello world")
    expected = hashlib.sha256(b"hello world").hexdigest()
    assert fingerprint(str(f)) == expected


class FakeGeminiResponse:
    def __init__(self, text):
        self.text = text


class FakeGeminiClient:
    def __init__(self, reply_text):
        self._reply_text = reply_text
        self.calls = []

    class _Models:
        def __init__(self, outer):
            self._outer = outer

        def generate_content(self, model, contents, config=None):
            self._outer.calls.append((model, contents))
            return FakeGeminiResponse(self._outer._reply_text)

    @property
    def models(self):
        return FakeGeminiClient._Models(self)


def test_classify_surface_parses_blackboard():
    client = FakeGeminiClient(reply_text="blackboard")
    result = classify_surface(client, frames=[b"fake-frame-bytes"])
    assert result == SurfaceKind.BLACKBOARD
    assert len(client.calls) == 1


def test_classify_surface_rejects_unknown_label():
    client = FakeGeminiClient(reply_text="chalkboard-ish maybe?")
    with pytest.raises(ValueError):
        classify_surface(client, frames=[b"fake-frame-bytes"])


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_admit_end_to_end(tmp_path):
    clip = tmp_path / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=2",
         "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "2",
         "-c:v", "libx264", "-c:a", "aac", str(clip)],
        check=True, capture_output=True,
    )
    client = FakeGeminiClient(reply_text="blackboard")
    recording = admit(str(clip), client, workdir=str(tmp_path))
    assert recording.duration_s > 0
    assert recording.surface_kind == SurfaceKind.BLACKBOARD
    assert len(recording.id) == 64
