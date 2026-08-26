"""Minimal, standalone test of the Vertex AI / Gemini Enterprise Agent
Platform backend, authenticated with a "Google Cloud API key" from Agent
Platform Studio's API Keys settings page — NOT a full OAuth2 access token.

Verified directly against the installed google-genai SDK source
(_api_client.py): there's a distinct, first-class code path for this,
internally labelled "Vertex AI in express mode (api key)" — you pass
`api_key=` alongside `vertexai=True` (or `enterprise=True`), the same
api_key= parameter used for the plain Gemini Developer API, just combined
with the vertexai/enterprise flag. It is NOT wrapped in a
google.oauth2.credentials.Credentials object — that's for full OAuth
access tokens (e.g. from `gcloud auth print-access-token`), a different
auth mode this key isn't meant for. In express mode the key alone is
often sufficient — no project/location required, since the key carries
that context implicitly.

Reads GOOGLE_OAUTH_ACCESS_TOKEN from the environment (kept under this
existing variable name — it holds an Agent Platform Studio API key, not
an OAuth token; the name is a holdover from before this was diagnosed).
Nothing is hardcoded here.

Usage:
    uv run --env-file .env python scripts/test_vertex_api_key.py
"""
import os
import sys

from google import genai


def main() -> int:
    api_key = os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN")

    if not api_key:
        print("FAILED — GOOGLE_OAUTH_ACCESS_TOKEN is not set in the environment.")
        print("  Add it to .env, then run with: uv run --env-file .env python scripts/test_vertex_api_key.py")
        return 1

    client = genai.Client(vertexai=True, api_key=api_key)

    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=["reply with just: ok"],
        )
    except Exception as e:
        print("FAILED — Vertex AI express-mode call did not succeed:")
        print(f"  {e!r}")
        return 1

    print("OK — Vertex AI express-mode call succeeded.")
    print(f"  Model replied: {response.text!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
