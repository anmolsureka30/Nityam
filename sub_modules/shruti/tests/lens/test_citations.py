import pytest
from shruti.lens.citations import seconds_to_mmss, mmss_to_seconds, format_citation, resolve_citation


def test_seconds_to_mmss_pads_seconds_under_ten():
    assert seconds_to_mmss(23) == "0:23"
    assert seconds_to_mmss(83) == "1:23"


def test_seconds_to_mmss_handles_over_an_hour():
    assert seconds_to_mmss(3661) == "61:01"


def test_mmss_to_seconds_is_the_inverse():
    assert mmss_to_seconds("1:23") == 83.0
    assert mmss_to_seconds("61:01") == 3661.0


def test_format_citation_produces_expected_shape():
    assert format_citation("physics_projectile_01", 83) == "shruti:physics_projectile_01 @1:23"


def test_resolve_citation_round_trips_with_format_citation():
    citation = format_citation("kinematics_lecture_04", 725)
    slug, seconds = resolve_citation(citation)
    assert slug == "kinematics_lecture_04"
    assert seconds == 725.0


def test_resolve_citation_rejects_malformed_input():
    with pytest.raises(ValueError):
        resolve_citation("not a citation")
    with pytest.raises(ValueError):
        resolve_citation("shruti:missing-timestamp")
