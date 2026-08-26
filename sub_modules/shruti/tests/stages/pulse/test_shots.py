import shutil
import subprocess
import pytest
from shruti.stages.pulse.shots import detect_shots


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_detect_shots_on_synthetic_two_scene_clip(tmp_path):
    clip = tmp_path / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-y",
         "-f", "lavfi", "-i", "color=c=black:s=64x64:d=2:r=10",
         "-f", "lavfi", "-i", "color=c=white:s=64x64:d=2:r=10",
         "-filter_complex", "concat=n=2:v=1:a=0", "-c:v", "libx264", str(clip)],
        check=True, capture_output=True,
    )
    shots = detect_shots(str(clip), threshold=27.0)
    assert len(shots) >= 1
    assert shots[0].start_s == 0.0
