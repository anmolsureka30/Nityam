"""Installs a minimal, export-free OpenTelemetry TracerProvider so
trace_id/span_id correlation works for anything reading the current span —
chiefly app/memory/instrumentation.py's MemoryEvent, and the new
ToolCallEvent added in this plan. No exporter is configured: this generates
real trace/span IDs in-process only, nothing is shipped to Cloud Trace or
any collector.

Without this, opentelemetry.trace.get_current_span() always returns the
OTel API's default no-op span, and instrumentation.py's _current_trace_ids()
always returns (None, None) — confirmed true in this deployment before this
file existed. google-adk's own google.adk.telemetry.setup.maybe_set_otel_providers
only installs a real provider when OTEL_EXPORTER_OTLP*_ENDPOINT env vars are
set (none are, here) or when running under ADK's own cli/api_server.py dev
server (backend/ builds its own FastAPI app directly, so it never does).
See docs/superpowers/specs/2026-08-30-observatory-integration-design.md's
Tracing section.
"""
from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

_installed = False


def setup_tracing() -> None:
    """Idempotent. Call once at app startup, before serving traffic.

    Safe to call after other modules have already done
    `trace.get_tracer(...)`: OTel's API returns a ProxyTracer when no real
    provider is set yet, and the proxy forwards to whatever the global
    provider is at SPAN-CREATION time, not at get_tracer() time — so
    ordering relative to imports doesn't matter, only relative to the first
    real request.
    """
    global _installed
    if _installed:
        return
    trace.set_tracer_provider(TracerProvider())
    _installed = True


tracer = trace.get_tracer("nityam")
"""Shared tracer for opening spans around one unit of agent work."""
