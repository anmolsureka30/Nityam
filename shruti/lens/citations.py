import re

_CITATION_RE = re.compile(r"^shruti:(?P<slug>\S+) @(?P<mmss>\d+:\d{2})$")


def seconds_to_mmss(seconds: float) -> str:
    total = int(round(seconds))
    minutes, secs = divmod(total, 60)
    return f"{minutes}:{secs:02d}"


def mmss_to_seconds(mmss: str) -> float:
    minutes, secs = mmss.split(":")
    return float(minutes) * 60 + float(secs)


def format_citation(slug: str, seconds: float) -> str:
    """The one canonical citation shape SMRITI cites, e.g.
    '[-> shruti:physics_projectile_01 @1:23]'. Keep the space before '@' —
    it's what makes the regex below unambiguous to parse back."""
    return f"shruti:{slug} @{seconds_to_mmss(seconds)}"


def resolve_citation(citation: str) -> tuple[str, float]:
    """Inverse of format_citation. Raises ValueError on anything that isn't
    exactly the format this module produces — a citation that can't be
    resolved is worse than one that's obviously rejected."""
    match = _CITATION_RE.match(citation)
    if not match:
        raise ValueError(f"not a valid shruti citation: {citation!r}")
    return match.group("slug"), mmss_to_seconds(match.group("mmss"))
