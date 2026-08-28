"""GCS artifact persistence: the IR a completed artifact mounts with also
lands durably in Cloud Storage, keyed by artifact_id, and can be read back
and deleted.

    .venv/bin/python -m tests.test_gcs_artifacts
"""
from __future__ import annotations

import sys
import uuid

from app.auth import load_env

load_env()

from app.artifacts_gcs import (
    delete_artifact_from_gcs,
    read_artifact_from_gcs,
    save_artifact_to_gcs,
)

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


def main() -> int:
    artifact_id = f"test_{uuid.uuid4().hex[:10]}"
    ir = {"artifact_id": artifact_id, "title": "test artifact", "controls": []}

    save_artifact_to_gcs(artifact_id, ir)
    round_tripped = read_artifact_from_gcs(artifact_id)
    check("the artifact round-trips through GCS", round_tripped == ir, repr(round_tripped))

    delete_artifact_from_gcs(artifact_id)
    try:
        read_artifact_from_gcs(artifact_id)
        check("and is gone after delete", False, "read did not raise")
    except Exception:  # noqa: BLE001 - any exception (NotFound) is the point
        check("and is gone after delete", True)

    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
