import hashlib
import json
import subprocess


def fingerprint(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def probe_video(path: str) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format",
         "-show_streams", path],
        check=True, capture_output=True, text=True,
    )
    data = json.loads(out.stdout)
    v_stream = next(s for s in data["streams"] if s["codec_type"] == "video")
    has_audio = any(s["codec_type"] == "audio" for s in data["streams"])
    num, den = (v_stream.get("r_frame_rate", "30/1")).split("/")
    return {
        "duration_s": float(data["format"]["duration"]),
        "fps": float(num) / float(den),
        "width": int(v_stream["width"]),
        "height": int(v_stream["height"]),
        "has_audio": has_audio,
    }
