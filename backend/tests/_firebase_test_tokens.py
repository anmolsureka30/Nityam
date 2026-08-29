"""A real Firebase ID token for a fixed test account, with no admin credentials.

The account is created and signed into through the ordinary Identity Toolkit
REST API — the same endpoints the browser SDK calls — authenticated by nothing
but FIREBASE_WEB_API_KEY, which is a public client key. Tests therefore get a
real ID token, exactly what a browser gets, on any machine that can reach the
internet.

WHY NOT THE ADMIN SDK. It used to be firebase_admin's create_user /
get_user_by_email, and that needs Application Default Credentials — which on a
developer laptop are minted WITHOUT a quota project, which identitytoolkit
refuses, and the documented fix needs serviceusage.services.use on the Firebase
project, which a developer may simply not have been granted. The suites became
unrunnable for a reason that had nothing to do with the code under test.
Nothing here needs privilege, so nothing here asks for it.

Needs: Email/Password sign-in enabled once in the Firebase console
(Authentication -> Sign-in method), and FIREBASE_WEB_API_KEY in the
environment.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

_ENDPOINT = "https://identitytoolkit.googleapis.com/v1/{path}?key={key}"

_SETUP = """
These tests sign in as a real Firebase user, so they need one thing:

  FIREBASE_WEB_API_KEY in backend/.env — the same value the browser uses as
  VITE_FIREBASE_API_KEY. See backend/.env.example.

Email/Password sign-in must also be enabled once, in the Firebase console:
  Authentication -> Sign-in method -> Email/Password -> Enable

Suites that need neither, and run right now:
  .venv/bin/python -m tests.test_canvas
  cd ../frontend
  node tests/contract.mjs && node tests/reducer.mjs && node tests/chunks.mjs
"""


class _Failed(RuntimeError):
    pass


def _call(path: str, body: dict) -> dict:
    try:
        key = os.environ["FIREBASE_WEB_API_KEY"]
    except KeyError:
        raise SystemExit(_SETUP) from None
    req = urllib.request.Request(
        _ENDPOINT.format(path=path, key=key),
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        # The body is the whole diagnosis and urllib throws it away: a bare
        # "HTTP Error 400: Bad Request" hides OPERATION_NOT_ALLOWED, which is
        # what a fresh project says until Email/Password sign-in is enabled.
        raise _Failed(json.loads(e.read().decode())["error"]["message"]) from None


def mint_id_token(email: str, password: str) -> str:
    """Signs in, creating the account first if it does not exist yet."""
    creds = {"email": email, "password": password, "returnSecureToken": True}
    try:
        return _call("accounts:signInWithPassword", creds)["idToken"]
    except _Failed as first:
        if "EMAIL_NOT_FOUND" not in str(first) and "INVALID_LOGIN" not in str(first):
            raise SystemExit(f"{_SETUP}\nFirebase said: {first}\n") from None
    try:
        return _call("accounts:signUp", creds)["idToken"]
    except _Failed as e:
        raise SystemExit(f"{_SETUP}\nFirebase said: {e}\n") from None
