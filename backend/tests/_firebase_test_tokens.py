"""Get a real Firebase ID token for a fixed, auto-provisioned test account.

No signing/impersonation permission needed: this creates (if missing) a real
Firebase Auth user with a known email/password via the Admin SDK's plain
create_user/get_user_by_email (ordinary authenticated Admin API calls — same
as scripts/create_demo_firebase_user.py, works with plain ADC), then signs
in as that user via the real (free, no-quota-cost) Identity Toolkit password
sign-in REST API. Tests get a real ID token, exactly what a browser gets.

Needs: Email/Password sign-in enabled in the Firebase console (Authentication
-> Sign-in method — a one-time manual step), ADC
(`gcloud auth application-default login`), and FIREBASE_WEB_API_KEY in the
environment.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from firebase_admin import auth as firebase_auth

from app import user_auth


def ensure_test_user(email: str, password: str) -> str:
    """Idempotent: returns the uid, creating the account if it doesn't exist."""
    user_auth.init_firebase()
    try:
        return firebase_auth.get_user_by_email(email).uid
    except firebase_auth.UserNotFoundError:
        return firebase_auth.create_user(email=email, password=password).uid


def mint_id_token(email: str, password: str) -> str:
    """Auto-provisions the account if needed, then signs in for a real ID token."""
    ensure_test_user(email, password)
    api_key = os.environ["FIREBASE_WEB_API_KEY"]
    url = (
        "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
        f"?key={api_key}"
    )
    body = json.dumps(
        {"email": email, "password": password, "returnSecureToken": True},
    ).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.load(resp)["idToken"]
    except urllib.error.HTTPError as e:
        # The body is the whole diagnosis and urllib throws it away: a bare
        # "HTTP Error 400: Bad Request" hides OPERATION_NOT_ALLOWED, which is
        # what a fresh project says until Email/Password sign-in is enabled in
        # the console — by far the likeliest first-run failure here.
        raise RuntimeError(f"Firebase sign-in failed: {e.read().decode()}") from e
