import subprocess
from pathlib import Path


def normalize_video(path: str, out_dir: str) -> tuple[str, str]:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    video_path = str(Path(out_dir) / "normalized.mp4")
    audio_path = str(Path(out_dir) / "audio.wav")
    subprocess.run(
        ["ffmpeg", "-y", "-i", path, "-c:v", "libx264", "-r", "30",
         "-an", video_path],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", path, "-vn", "-ac", "1", "-ar", "16000",
         audio_path],
        check=True, capture_output=True,
    )
    return video_path, audio_path
