"""Firebase Auth: verifying a browser-supplied ID token server-side.

The one place identity flows into this backend is app/main.py's ws_endpoint —
see that file. This module owns nothing about WHERE the token comes from,
only whether it's real.

WHY THIS DOES NOT USE THE ADMIN SDK
-----------------------------------
It used to be `firebase_admin.auth.verify_id_token()`, and that call drags in
Application Default Credentials — not to check the signature, which needs no
credentials at all, but to identify itself to the Identity Toolkit API. Two
separate ways that failed on a normal laptop:

  * No ADC at all: a twenty-frame traceback out of google.auth that never
    mentions Nityam.
  * ADC present but with NO QUOTA PROJECT, which is what
    `gcloud auth application-default login` produces by default:
    identitytoolkit refuses outright. The documented fix,
    `gcloud auth application-default set-quota-project <id>`, itself needs
    serviceusage.services.use on the project — so a developer without an IAM
    grant on the Firebase project cannot run the backend at all. That is not
    hypothetical; it is what happened here.

Both surfaced identically to the student: "Your sign-in has expired. Please
refresh and sign in again," on a sign-in that was completely valid.

A Firebase ID token is an RS256 JWT signed by Google. Verifying it needs
Google's PUBLIC certificates and nothing else — no service account, no ADC, no
IAM. That is what this does, so the backend now runs for anyone who can reach
the internet, and correctness does not depend on who granted whom what.

WHAT IS CHECKED, and it must stay this list — each line is load-bearing:
  * RS256 signature against Google's published securetoken certificates
  * `aud` == this Firebase project (a token minted for a DIFFERENT project is
    a real attack, not a hypothetical: anyone can create a Firebase project
    and sign in to it)
  * `iss` == https://securetoken.google.com/<project>
  * `exp` / `iat`, with a small allowance for clock skew
  * `sub` present and non-empty — it becomes the uid the caller compares

NOT checked: revocation and account-disabled. Those genuinely require a
privileged API call. A token lives an hour, so the window is an hour; if that
ever matters, the Admin SDK path is the fix and it needs a service account,
not user ADC. Said plainly here so nobody assumes otherwise.
"""
from __future__ import annotations

import json
import os
import threading
import time

from google.auth import jwt
from google.auth.transport import requests as ga_requests
from google.oauth2 import id_token as google_id_token

# Google's public signing certificates for Firebase ID tokens. The same URL
# google-auth's own verify_firebase_token uses.
_CERTS_URL = google_id_token._GOOGLE_APIS_CERTS_URL

# Tokens are minted by the browser and verified here; a minute covers ordinary
# clock drift without meaningfully extending a token's life.
_SKEW_S = 60

_lock = threading.Lock()
_certs: dict | None = None
_certs_expire = 0.0


def _project() -> str:
    """The Firebase project a token must have been minted for.

    NITYAM_PROJECT_ID first: app/auth.py's configure() DELETES
    GOOGLE_CLOUD_PROJECT from the environment in vertex_express mode (the genai
    SDK would otherwise ignore the API key), so reading that alone found
    nothing and refused every token on a machine whose .env was correct. See
    the comment beside the deletion.

    Empty means "not configured", and verify_token then refuses everything
    rather than accepting tokens from any project on the internet — an unset
    environment variable must fail closed.
    """
    return (
        os.environ.get("NITYAM_PROJECT_ID")
        or os.environ.get("FIREBASE_PROJECT_ID")
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
        or ""
    ).strip()


def _fetch_certs(force: bool = False) -> dict:
    """Google's certificates, cached until they expire.

    Without the cache this is an HTTPS round trip on every WebSocket connect.
    Google rotates these roughly daily and says how long they are good for in
    Cache-Control, so that is what is honoured.
    """
    global _certs, _certs_expire
    with _lock:
        if _certs is not None and not force and time.time() < _certs_expire:
            return _certs
        response = ga_requests.Request()(url=_CERTS_URL, method="GET")
        if response.status != 200:
            raise ValueError(
                "could not fetch Google's signing certificates "
                f"(HTTP {response.status})",
            )
        _certs = json.loads(response.data.decode("utf-8"))
        # Cache-Control wins; an hour if it is missing or unparseable. Never
        # cache forever: a rotation would then break every sign-in until the
        # process restarts.
        ttl = 3600
        for part in (response.headers.get("cache-control") or "").split(","):
            part = part.strip()
            if part.startswith("max-age="):
                try:
                    ttl = max(60, int(part[len("max-age="):]))
                except ValueError:
                    pass
        _certs_expire = time.time() + ttl
        return _certs


def init_firebase() -> None:
    """Kept for the Admin SDK callers that genuinely need it — the demo-user
    script and anything that CREATES users, which really does need privileged
    credentials. Verification does not, and no longer calls this. Idempotent,
    and imports firebase_admin lazily so an unconfigured machine pays nothing
    for a code path it never takes."""
    import firebase_admin

    if not firebase_admin._apps:
        firebase_admin.initialize_app()


def verify_token(id_token: str) -> dict:
    """The decoded claims of a currently-valid ID token for this project.

    Raises ValueError on anything else. Callers catch broadly — see
    app/main.py:ws_endpoint.
    """
    project = _project()
    if not project:
        raise ValueError(
            "no Firebase project configured — set FIREBASE_PROJECT_ID or "
            "GOOGLE_CLOUD_PROJECT in backend/.env",
        )

    def _decode(certs: dict) -> dict:
        # Signature, `aud` and `exp`/`iat` are all enforced here.
        return jwt.decode(
            id_token, certs=certs, audience=project, clock_skew_in_seconds=_SKEW_S,
        )

    try:
        claims = _decode(_fetch_certs())
    except ValueError:
        # A rotation between our cached copy and this token looks exactly like
        # a bad signature. Refetch once before calling it invalid — otherwise
        # every student is signed out for as long as the stale cache lives.
        claims = _decode(_fetch_certs(force=True))

    issuer = f"https://securetoken.google.com/{project}"
    if claims.get("iss") != issuer:
        raise ValueError(f"wrong issuer: {claims.get('iss')!r}")
    if not claims.get("sub"):
        raise ValueError("token has no subject")
    # `uid` is the Admin SDK's name for `sub`, and it is what every caller
    # reads — app/main.py compares decoded["uid"] to the url's user_id. Raw JWT
    # claims carry only `sub`, so leaving it out silently turned every valid
    # sign-in into "your sign-in has expired": the comparison was None against
    # a real uid, and nothing in the log said so.
    claims["uid"] = claims["sub"]
    return claims
