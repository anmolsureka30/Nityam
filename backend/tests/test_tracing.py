"""setup_tracing() installs a real TracerProvider, so a span opened via
app.tracing.tracer produces a non-None trace_id that
instrumentation._current_trace_ids() can read back — the precondition every
later task in this plan depends on.

    .venv/bin/python -m tests.test_tracing
"""
from __future__ import annotations

import sys

from app import tracing
from app.memory import instrumentation

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


def run() -> None:
    before_trace_id, before_span_id = instrumentation._current_trace_ids()
    check("no active span before setup: trace_id is None", before_trace_id is None)

    tracing.setup_tracing()

    with tracing.tracer.start_as_current_span("test-span") as span:
        trace_id, span_id = instrumentation._current_trace_ids()
        check("trace_id is set inside a span", trace_id is not None, repr(trace_id))
        check("span_id is set inside a span", span_id is not None, repr(span_id))
        expected_trace_id = format(span.get_span_context().trace_id, "032x")
        check("trace_id matches the span's own context", trace_id == expected_trace_id)

    after_trace_id, _ = instrumentation._current_trace_ids()
    check("trace_id is None again once the span closes", after_trace_id is None)

    # Idempotency: calling setup_tracing() again must not raise or replace
    # the provider (a second real trace.set_tracer_provider() call on an
    # already-real provider logs a warning and is a no-op upstream — this
    # guards against ever calling it a second time ourselves).
    tracing.setup_tracing()
    with tracing.tracer.start_as_current_span("test-span-2"):
        trace_id_2, _ = instrumentation._current_trace_ids()
        check("tracing still works after a second setup_tracing() call", trace_id_2 is not None)


def main() -> int:
    run()
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
