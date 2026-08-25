from shruti.contracts.recording import Recording
from shruti.stages.gate.probe import probe_video, fingerprint
from shruti.stages.gate.normalize import normalize_video
from shruti.stages.gate.surface import classify_surface


def admit(source_uri: str, client, workdir: str) -> Recording:
    meta = probe_video(source_uri)
    video_path, _audio_path = normalize_video(source_uri, workdir)
    rec_id = fingerprint(video_path)
    surface_kind = classify_surface(client, frames=[])
    return Recording(
        id=rec_id,
        source_uri=source_uri,
        duration_s=meta["duration_s"],
        fps=meta["fps"],
        width=meta["width"],
        height=meta["height"],
        surface_kind=surface_kind,
    )
