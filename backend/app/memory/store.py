"""The memory store, whichever one is configured.

Two complete backends live behind this module, with byte-identical function
signatures — that was the point of keeping `store.py` the only thing that
touches storage:

  * `store_sqlite`    — a file at backend/data/memory.db. No credentials, no
                        network, works on a plane. What the tests and the demo
                        run on.
  * `store_firestore` — Firestore, ported from sub_modules_examples/tutor.
                        Adds vector search over grounding chunks. Needs a GCP
                        project and application-default credentials.

Chosen by `NITYAM_STORE`, so switching is an environment variable rather than
an edit. Everything above this module — the ADK tool functions, the schemas,
session_close — is unchanged either way, and passes around whatever handle
`connect()` returned without caring what it is.

The default is deliberately sqlite: a tutor that cannot start because a cloud
credential expired is worse than one whose memory is a local file, and the
credentials are not always to hand.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger("nityam.store")

BACKEND = os.getenv("NITYAM_STORE", "sqlite").strip().lower()

if BACKEND == "firestore":
    from app.memory import store_firestore as _impl
elif BACKEND == "sqlite":
    from app.memory import store_sqlite as _impl
else:  # pragma: no cover - a typo here should be loud, not silently sqlite
    raise SystemExit(
        f"NITYAM_STORE must be 'sqlite' or 'firestore', got {BACKEND!r}"
    )


def backend() -> str:
    """Which one is live. Reported by /health so a demo cannot be wrong about it."""
    return BACKEND


from app.memory import instrumentation  # noqa: E402


def _ids_none(args, kwargs, result):
    return None, None


def _ids_context_session_only(args, kwargs, result):
    return instrumentation.get_session_context(), None


def _ids_student_from_arg1(args, kwargs, result):
    student_id = kwargs.get("student_id", args[1] if len(args) > 1 else None)
    return instrumentation.get_session_context(), student_id


def _ids_from_profile(args, kwargs, result):
    profile = kwargs.get("profile", args[1] if len(args) > 1 else None)
    return instrumentation.get_session_context(), getattr(profile, "student_id", None)


def _ids_from_memory(args, kwargs, result):
    memory = kwargs.get("memory", args[1] if len(args) > 1 else None)
    return instrumentation.get_session_context(), getattr(memory, "student_id", None)


def _ids_from_log(args, kwargs, result):
    log_obj = kwargs.get("log", args[1] if len(args) > 1 else None)
    return getattr(log_obj, "session_id", None), getattr(log_obj, "student_id", None)


def _ids_session_from_arg1(args, kwargs, result):
    session_id = kwargs.get("session_id", args[1] if len(args) > 1 else None)
    return session_id, None


connect = _impl.connect
put_grounding_chunk = instrumentation.emit_memory_event(
    "long_term", "grounding_chunk", "write", _ids_none,
)(_impl.put_grounding_chunk)
search_grounding = instrumentation.emit_memory_event(
    "long_term", "grounding_chunk", "read", _ids_context_session_only,
)(_impl.search_grounding)
get_dpm = instrumentation.emit_memory_event(
    "long_term", "dpm_profile", "read", _ids_student_from_arg1,
)(_impl.get_dpm)
put_dpm = instrumentation.emit_memory_event(
    "long_term", "dpm_profile", "write", _ids_from_profile,
)(_impl.put_dpm)
get_teaching_memory = instrumentation.emit_memory_event(
    "long_term", "teaching_memory", "read", _ids_student_from_arg1,
)(_impl.get_teaching_memory)
put_teaching_memory = instrumentation.emit_memory_event(
    "long_term", "teaching_memory", "write", _ids_from_memory,
)(_impl.put_teaching_memory)
put_session_log = instrumentation.emit_memory_event(
    "episodic", "session_log", "write", _ids_from_log,
)(_impl.put_session_log)
get_session_log = instrumentation.emit_memory_event(
    "episodic", "session_log", "read", _ids_session_from_arg1,
)(_impl.get_session_log)

#: Firestore-only extras. `getattr` rather than a plain import so the sqlite
#: path degrades instead of raising — callers must check for None.
#:
#: `store_firestore.py` is a manually-synced copy of sub_modules_examples/
#: tutor's app/memory/store.py — no automated sync, so a fix landed in one
#: needs porting to the other by hand (confirmed drifted and re-synced twice
#: now: token-overlap fuzzy matching in search_grounding, and a
#: reflect()/close_session structured-output schema fix — see
#: app/session_close.py's own docstring). Check both when touching
#: memory-layer code.
list_session_logs = instrumentation.emit_memory_event(
    "episodic", "session_log", "read", _ids_student_from_arg1,
)(_impl.list_session_logs)

latest_session_log = instrumentation.emit_memory_event(
    "episodic", "session_log", "read", _ids_student_from_arg1,
)(_impl.latest_session_log)

search_grounding_semantic = getattr(_impl, "search_grounding_semantic", None)
list_concept_ids = getattr(_impl, "list_concept_ids", None)

log.info("memory store: %s", BACKEND)
