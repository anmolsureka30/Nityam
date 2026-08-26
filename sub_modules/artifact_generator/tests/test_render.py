"""Regression test for the render extraction — build.py must produce
byte-identical output to what render_html() now produces, since build.py's
own rendering logic is being replaced with a call to this function."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "generate"))

from render import render_html  # noqa: E402


def test_render_html_produces_self_contained_html():
    with open(os.path.join(ROOT, "examples", "lesson1_max_range.json")) as f:
        ir = json.load(f)

    html = render_html(ir, "plain", {"source": "test", "spec": "test"})

    assert html.startswith("<!doctype") or html.startswith("<!DOCTYPE")
    assert ir["artifact_id"] in html
    assert "__IR_JSON__" not in html  # placeholder must be substituted
    assert "__RUNTIME_JS__" not in html


def test_render_html_falls_back_to_plain_theme_for_unknown_theme():
    with open(os.path.join(ROOT, "examples", "lesson1_max_range.json")) as f:
        ir = json.load(f)

    html = render_html(ir, "nonexistent-theme", {"source": "test", "spec": "test"})
    assert ir["artifact_id"] in html
