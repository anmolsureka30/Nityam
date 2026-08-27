"""URL builders for deep-linking out to the real Cloud Trace console and the
real ADK web dev UI — the Observatory shows genuine trace/session data, it
doesn't reimplement either surface."""
from __future__ import annotations


def cloud_trace_url(trace_id: str, gcp_project: str) -> str:
    return f"https://console.cloud.google.com/traces/list?tid={trace_id}&project={gcp_project}"


def adk_web_url(tutor_base_url: str) -> str:
    """ADK web mounts at /dev-ui/ (confirmed against the real installed
    google-adk==2.7.1 package). No confirmed session-scoping query param —
    this links to the dev-ui root; the session id is shown alongside for
    manual paste into its own session search box."""
    return f"{tutor_base_url.rstrip('/')}/dev-ui/"
