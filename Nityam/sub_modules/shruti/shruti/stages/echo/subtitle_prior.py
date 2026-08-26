import re
from shruti.contracts.speech import Utterance

_TIME_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[.,](\d{3})")


def _to_seconds(h, m, s, ms) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_subtitle_file(path: str) -> list[dict]:
    text = open(path, encoding="utf-8").read()
    blocks = re.split(r"\n\s*\n", text.strip())
    segments = []
    for block in blocks:
        match = _TIME_RE.search(block)
        if not match:
            continue
        h1, m1, s1, ms1, h2, m2, s2, ms2 = match.groups()
        lines = block[match.end():].strip().splitlines()
        segment_text = " ".join(line.strip() for line in lines if line.strip())
        segments.append({
            "start_s": _to_seconds(h1, m1, s1, ms1),
            "end_s": _to_seconds(h2, m2, s2, ms2),
            "text": segment_text,
        })
    return segments


def align_subtitle_prior(utterances: list[Utterance], subtitle_segments: list[dict]) -> list[Utterance]:
    aligned = []
    for u in utterances:
        best = None
        best_overlap = 0.0
        for seg in subtitle_segments:
            overlap = min(u.end_s, seg["end_s"]) - max(u.start_s, seg["start_s"])
            if overlap > best_overlap:
                best_overlap = overlap
                best = seg
        if best is not None:
            aligned.append(u.model_copy(update={"start_s": best["start_s"], "end_s": best["end_s"]}))
        else:
            aligned.append(u)
    return aligned
