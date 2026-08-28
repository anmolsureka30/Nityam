"""app/user_auth.py: verifying a real Firebase ID token, and rejecting
everything that is not one.

    .venv/bin/python -m tests.test_user_auth
"""
from __future__ import annotations

import sys

from app.auth import load_env  # noqa: E402

load_env()

from app import user_auth  # noqa: E402
from tests._firebase_test_tokens import mint_id_token  # noqa: E402

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


def main() -> int:
    user_auth.init_firebase()

    token = mint_id_token("demo@nityam.local", "nityam-demo-2026")
    decoded = user_auth.verify_token(token)
    check("a real token verifies", decoded.get("uid") is not None, repr(decoded.get("uid")))

    for name, bad in [
        ("garbage", "not-a-real-token"),
        ("empty", ""),
        ("malformed jwt shape", "a.b.c"),
        ("well-formed but unsigned", "eyJhbGciOiJub25lIn0.e30."),
    ]:
        try:
            user_auth.verify_token(bad)
            check(f"a {name} token raises", False, "it did not raise")
        except Exception as exc:  # noqa: BLE001 - any exception is the point here
            check(f"a {name} token raises", True, type(exc).__name__)

    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
