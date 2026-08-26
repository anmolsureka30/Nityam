import re
import cv2
from google.genai import types
from shruti.contracts.recording import Recording
from shruti.stages.gate.probe import probe_video, fingerprint
from shruti.stages.gate.normalize import normalize_video
from shruti.stages.gate.surface import classify_surface


def _sample_frames_for_classification(video_path: str, n: int = 5) -> list:
    """Grab n evenly-spaced frames as image Parts for classify_surface.
    Bug fix: this previously always received frames=[], so surface
    classification was a blind guess with no image content at all."""
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    parts = []
    if total > 0:
        for i in range(n):
            idx = min(total - 1, int((i + 0.5) * total / n))
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if ok:
                _, buf = cv2.imencode(".jpg", frame)
                parts.append(types.Part.from_bytes(data=buf.tobytes(), mime_type="image/jpeg"))
    cap.release()
    return parts


def _slugify(source_uri: str, rec_id: str) -> str:
    """Human-readable, stable, collision-resistant: sanitized filename plus
    an 8-char disambiguator from the content hash. Doesn't need subject/
    chapter — admit() doesn't have those yet, and the slug must not block
    on metadata that arrives later."""
    name = source_uri.rsplit("/", 1)[-1]
    name = re.sub(r"\.[^.]+$", "", name)
    name = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    return f"{name}_{rec_id[:8]}"


def admit(source_uri: str, client, workdir: str) -> Recording:
    meta = probe_video(source_uri)
    video_path, _audio_path = normalize_video(source_uri, workdir)
    rec_id = fingerprint(video_path)
    surface_kind = classify_surface(client, frames=_sample_frames_for_classification(video_path))
    return Recording(
        id=rec_id,
        slug=_slugify(source_uri, rec_id),
        source_uri=source_uri,
        duration_s=meta["duration_s"],
        fps=meta["fps"],
        width=meta["width"],
        height=meta["height"],
        surface_kind=surface_kind,
    )
