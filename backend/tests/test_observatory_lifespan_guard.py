"""_lifespan's Observatory setup (store.connect(), the ingest task) is
guarded: a Firestore/ADC failure there must degrade to "Observatory
unavailable", not take the whole app -- including the live voice tutor --
down with it. Before this guard, `db = store.connect()` ran unguarded ahead
of `yield`, so an exception there failed uvicorn's startup outright.

    .venv/bin/python -m tests.test_observatory_lifespan_guard
"""
from __future__ import annotations

import sys

from fastapi.testclient import TestClient

from app import main as app_main
from app.memory import store

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


def run() -> None:
    original_connect = store.connect

    def _boom():
        raise RuntimeError("Firestore is having a day")

    store.connect = _boom
    try:
        # Entering the TestClient context re-runs _lifespan from scratch.
        # Before the guard in this finding's fix, this `with` block itself
        # would raise (uvicorn's real startup would fail the same way) --
        # the whole point of the fix is that it must not, even though
        # store.connect() now always raises.
        try:
            with TestClient(app_main.app) as client:
                check("the app still starts when store.connect() raises", True)
                response = client.get("/observatory/api/sessions")
                check(
                    "the rest of the app (including non-Observatory routes) keeps serving",
                    response.status_code == 200, response.text,
                )
        except Exception as exc:  # noqa: BLE001 - this IS the failure mode under test
            check("the app still starts when store.connect() raises", False, repr(exc))
            check("the rest of the app (including non-Observatory routes) keeps serving", False, "app never started")
    finally:
        store.connect = original_connect

    # Restored: a normal TestClient run (store.connect() working again) must
    # still succeed, proving the patch above didn't leave anything wedged.
    with TestClient(app_main.app) as client:
        response = client.get("/observatory/api/sessions")
        check("the app starts normally again once store.connect() is restored",
              response.status_code == 200, response.text)


def main() -> int:
    run()
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
