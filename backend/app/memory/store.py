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


connect = _impl.connect
put_grounding_chunk = _impl.put_grounding_chunk
search_grounding = _impl.search_grounding
get_dpm = _impl.get_dpm
put_dpm = _impl.put_dpm
get_teaching_memory = _impl.get_teaching_memory
put_teaching_memory = _impl.put_teaching_memory
put_session_log = _impl.put_session_log
get_session_log = _impl.get_session_log

#: Only Firestore has it — a vector index over the grounding chunks. Callers
#: must check rather than assume, so the sqlite path degrades to concept-id
#: search instead of raising.
search_grounding_semantic = getattr(_impl, "search_grounding_semantic", None)

log.info("memory store: %s", BACKEND)
