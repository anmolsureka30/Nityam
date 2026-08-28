"""One-time setup: creates the demo Firebase user backend/scripts/seed_demo_data.py's
Firestore documents are keyed to. Pins uid="demo_student" explicitly (the
Admin SDK allows choosing the uid at creation) so none of the already-seeded
data needs to change.

Idempotent — safe to re-run. `run.sh` runs it alongside the Firestore seed on
first start, so a fresh clone gets both halves of "the demo student".

**This account and its password are public — they are checked into git.**
Delete it or rotate its password before any real/production deployment; it
exists only for local dev and CI.

Run directly: `.venv/bin/python -m scripts.create_demo_firebase_user`
"""
from __future__ import annotations

from firebase_admin import auth as firebase_auth

from app import user_auth

DEMO_UID = "demo_student"
DEMO_EMAIL = "demo@nityam.local"
DEMO_PASSWORD = "nityam-demo-2026"  # local/demo only — not a real account


def main() -> None:
    user_auth.init_firebase()
    try:
        firebase_auth.get_user(DEMO_UID)
        print(f"{DEMO_UID} already exists — nothing to do")
        return
    except firebase_auth.UserNotFoundError:
        pass

    firebase_auth.create_user(
        uid=DEMO_UID, email=DEMO_EMAIL, password=DEMO_PASSWORD, email_verified=True,
    )
    print(f"created {DEMO_UID} ({DEMO_EMAIL})")


if __name__ == "__main__":
    main()
