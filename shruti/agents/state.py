from enum import Enum

_ORDER = ["ADMITTED", "SPINED", "PERCEIVED", "WOVEN", "READ", "MAPPED", "SHELVED"]


class Stage(str, Enum):
    ADMITTED = "ADMITTED"
    SPINED = "SPINED"
    PERCEIVED = "PERCEIVED"
    WOVEN = "WOVEN"
    READ = "READ"
    MAPPED = "MAPPED"
    SHELVED = "SHELVED"


def next_stage(current: Stage) -> Stage:
    idx = _ORDER.index(current.value)
    if idx == len(_ORDER) - 1:
        raise ValueError(f"{current} is the terminal stage")
    return Stage(_ORDER[idx + 1])


def is_before(a: Stage, b: Stage) -> bool:
    return _ORDER.index(a.value) < _ORDER.index(b.value)
