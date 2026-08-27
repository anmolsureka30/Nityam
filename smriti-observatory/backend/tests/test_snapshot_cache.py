from __future__ import annotations

from observatory.snapshot_cache import SnapshotCache


def test_first_call_uses_loader_as_previous_value():
    cache = SnapshotCache()
    loader_calls = []

    def loader():
        loader_calls.append(1)
        return {"student_id": "s1", "weaknesses": {}}

    prev = cache.get_and_set("s1", "dpm_profile", {"student_id": "s1", "weaknesses": {"x": 1}}, loader)
    assert prev == {"student_id": "s1", "weaknesses": {}}
    assert len(loader_calls) == 1


def test_second_call_uses_cached_value_not_loader():
    cache = SnapshotCache()
    cache.get_and_set("s1", "dpm_profile", {"v": 1}, lambda: {"v": 0})

    loader_calls = []
    prev = cache.get_and_set("s1", "dpm_profile", {"v": 2}, lambda: loader_calls.append(1))
    assert prev == {"v": 1}
    assert loader_calls == []


def test_loader_returning_none_yields_none_as_previous():
    cache = SnapshotCache()
    prev = cache.get_and_set("s1", "dpm_profile", {"v": 1}, lambda: None)
    assert prev is None


def test_different_record_types_are_independent():
    cache = SnapshotCache()
    cache.get_and_set("s1", "dpm_profile", {"v": "dpm"}, lambda: None)
    cache.get_and_set("s1", "teaching_memory", {"v": "tm"}, lambda: None)
    assert cache.get_and_set("s1", "dpm_profile", {"v": "dpm2"}, lambda: None) == {"v": "dpm"}
    assert cache.get_and_set("s1", "teaching_memory", {"v": "tm2"}, lambda: None) == {"v": "tm"}


def test_set_primes_the_cache_so_a_later_get_and_set_skips_the_loader():
    cache = SnapshotCache()
    cache.set("s1", "dpm_profile", {"v": "from_a_read_event"})

    loader_calls = []
    prev = cache.get_and_set("s1", "dpm_profile", {"v": "written"}, lambda: loader_calls.append(1))
    assert prev == {"v": "from_a_read_event"}
    assert loader_calls == []


def test_set_can_prime_with_none():
    cache = SnapshotCache()
    cache.set("s1", "dpm_profile", None)
    loader_calls = []
    prev = cache.get_and_set("s1", "dpm_profile", {"v": "written"}, lambda: loader_calls.append(1))
    assert prev is None
    assert loader_calls == []
