"""Firebase Auth: verifying a browser-supplied ID token server-side.

The one place identity flows into this backend is app/main.py's ws_endpoint —
see that file. This module owns nothing about WHERE the token comes from,
only whether it's real.
"""
from __future__ import annotations

import firebase_admin
from firebase_admin import auth as firebase_auth

_app: firebase_admin.App | None = None


def init_firebase() -> None:
    """Idempotent. ADC (Application Default Credentials) — the same
    credential path app/memory/store_firestore.py already uses, so local dev
    keeps using `gcloud auth application-default login` and a future Cloud
    Run deploy keeps working via its attached service account, with zero new
    credential plumbing."""
    global _app
    if _app is None:
        _app = firebase_admin.initialize_app()


def verify_token(id_token: str) -> dict:
    """Raises firebase_admin.auth.* exceptions (ValueError, InvalidIdTokenError,
    ExpiredIdTokenError, etc.) on anything not a currently-valid ID token for
    this project. Callers catch broadly — see app/main.py:ws_endpoint."""
    return firebase_auth.verify_id_token(id_token)
