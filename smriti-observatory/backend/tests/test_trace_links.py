from __future__ import annotations

from observatory.trace_links import adk_web_url, cloud_trace_url


def test_cloud_trace_url_includes_trace_id_and_project():
    url = cloud_trace_url("abc123", "nityam-506707")
    assert url == "https://console.cloud.google.com/traces/list?tid=abc123&project=nityam-506707"


def test_adk_web_url_points_at_dev_ui_root():
    assert adk_web_url("http://localhost:8000") == "http://localhost:8000/dev-ui/"
