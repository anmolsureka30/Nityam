import difflib
from shruti.contracts.atlas import Concept


def canonicalize(concepts: list[Concept], similarity_threshold: float = 0.92) -> list[Concept]:
    merged: list[Concept] = []
    for c in concepts:
        match = next(
            (m for m in merged
             if difflib.SequenceMatcher(None, m.canonical_name, c.canonical_name).ratio()
             >= similarity_threshold),
            None,
        )
        if match is None:
            merged.append(c)
            continue
        merged[merged.index(match)] = match.model_copy(update={
            "aliases": list(set(match.aliases) | set(c.aliases) | {c.canonical_name}),
            "taught_in": match.taught_in + c.taught_in,
        })
    return merged
