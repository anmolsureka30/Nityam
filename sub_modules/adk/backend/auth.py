"""Which Google backend are we talking to, and does it actually work.

Three real modes plus a mock. The reason this is a module rather than three
lines in main.py: `google-genai` picks its platform from environment variables
read at client-construction time, so the environment has to be settled *before*
anything imports the agent. Getting that ordering wrong fails silently — you
get the default platform and a confusing 404.

Run `python backend/auth.py` to test your credentials before starting the
server. It reports which mode works and what to do about the ones that don't.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# One .env, at the sub-module root — next to run.sh, where you would look for
# it. backend/.env is still honoured so an older checkout keeps working.
ROOT = Path(__file__).resolve().parent.parent
ENV_PATHS = (ROOT / ".env", ROOT / "backend" / ".env")

MODES = ("ai_studio", "vertex", "vertex_express", "mock")


def load_env() -> None:
    """Load backend/.env. Must run before importing anything that reads env."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for path in ENV_PATHS:
        if path.is_file():
            load_dotenv(path)
            return


def configure() -> str:
    """Set the env vars google-genai reads. Returns the resolved mode.

    Also resolves the model name into NITYAM_RESOLVED_MODEL, because on Vertex
    the Live API wants a full resource path and the project id has to be read
    before it is removed from the environment.
    """
    mode = os.getenv("NITYAM_AUTH", "ai_studio").strip().lower()
    if mode not in MODES:
        raise SystemExit(f"NITYAM_AUTH must be one of {MODES}, got {mode!r}")

    if mode == "mock":
        return mode

    vertex = mode in ("vertex", "vertex_express")
    # Both names are set: older releases read USE_VERTEXAI, newer docs use
    # USE_ENTERPRISE. Setting them consistently works on either.
    for var in ("GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_GENAI_USE_ENTERPRISE"):
        os.environ[var] = "TRUE" if vertex else "FALSE"

    os.environ["NITYAM_RESOLVED_MODEL"] = resolve_model(mode)

    if mode == "vertex":
        # Project + location + Application Default Credentials.
        # The API key must be cleared or the SDK may prefer express mode.
        os.environ.pop("GOOGLE_API_KEY", None)
        for var in ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"):
            if not os.getenv(var):
                raise SystemExit(f"NITYAM_AUTH=vertex needs {var} set in .env")
    elif mode == "vertex_express":
        # Express mode is keyed rather than project-scoped. The OAuth access
        # token works as the key here — it is what actually authenticates
        # against this project — and it takes precedence over GOOGLE_API_KEY.
        key = express_key()
        if not key:
            raise SystemExit(
                "NITYAM_AUTH=vertex_express needs GOOGLE_OAUTH_ACCESS_TOKEN "
                "(preferred) or GOOGLE_API_KEY in .env"
            )
        os.environ["GOOGLE_API_KEY"] = key
        # project/location must be absent, or the SDK takes the ADC path and
        # ignores the key entirely. The model path already carries the project.
        for var in ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"):
            os.environ.pop(var, None)
    else:
        _require_key(mode)

    return mode


def express_key() -> str:
    return (
        os.getenv("GOOGLE_OAUTH_ACCESS_TOKEN", "").strip()
        or os.getenv("GOOGLE_API_KEY", "").strip()
    )


def resolve_model(mode: str) -> str:
    """Expand a bare model name into whatever the chosen platform expects.

    On Vertex the Live API rejects a bare name with `1007 Invalid resource
    field value`: it wants the full publisher path. google-genai only expands
    to a *relative* `publishers/google/models/...`, which is not enough, so
    build the absolute path here. ADK cooperates — it switches its client to
    enterprise mode when the model starts with `projects/`.
    """
    model = os.getenv("NITYAM_MODEL", "").strip()
    if not model:
        raise SystemExit("NITYAM_MODEL is not set in .env")
    if mode not in ("vertex", "vertex_express") or model.startswith("projects/"):
        return model

    project = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1").strip()
    if not project:
        raise SystemExit(
            "GOOGLE_CLOUD_PROJECT is needed to build the Vertex model path"
        )
    return (
        f"projects/{project}/locations/{location}"
        f"/publishers/google/models/{model}"
    )


def _require_key(mode: str) -> None:
    if not os.getenv("GOOGLE_API_KEY"):
        raise SystemExit(f"NITYAM_AUTH={mode} needs GOOGLE_API_KEY set in .env")


def describe() -> str:
    mode = os.getenv("NITYAM_AUTH", "ai_studio")
    model = os.getenv("NITYAM_RESOLVED_MODEL") or os.getenv("NITYAM_MODEL", "(unset)")
    short = model.rsplit("/", 1)[-1]
    if mode == "mock":
        return "mode=mock (no network, synthetic audio)"
    if mode == "vertex":
        return (
            f"mode=vertex project={os.getenv('GOOGLE_CLOUD_PROJECT')} "
            f"location={os.getenv('GOOGLE_CLOUD_LOCATION')} model={short}"
        )
    key = os.getenv("GOOGLE_API_KEY", "")
    return f"mode={mode} key=…{key[-6:]} model={short}"


# ------------------------------------------------------------- preflight

def preflight() -> int:
    """Try every mode and say which one works. Returns a shell exit code."""
    load_env()
    # google-genai logs an unrelated advisory about automatic function calling
    # on every generate_content; it would bury the actual result here.
    logging.getLogger("google_genai").setLevel(logging.ERROR)

    from google import genai
    from google.genai import types  # noqa: F401  (used by _probe_live)
    globals()["types"] = types

    key = os.getenv("GOOGLE_API_KEY", "")
    project = os.getenv("GOOGLE_CLOUD_PROJECT", "")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    probe_model = os.getenv("NITYAM_PROBE_MODEL", "gemini-flash-latest")

    print(f"probing with model {probe_model!r}\n")
    results = {}

    def attempt(label, build):
        try:
            client = build()
        except Exception as exc:  # credentials missing entirely
            print(f"  [skip] {label}: {type(exc).__name__}: {_short(exc)}")
            results[label] = "skip"
            return
        try:
            client.models.generate_content(model=probe_model, contents="Reply: OK")
            print(f"  [ ok ] {label}")
            results[label] = "ok"
        except Exception as exc:
            print(f"  [fail] {label}: {type(exc).__name__}: {_short(exc)}")
            results[label] = _classify(exc)

    if key:
        attempt("ai_studio", lambda: genai.Client(api_key=key))
    else:
        print("  [skip] ai_studio: no GOOGLE_API_KEY in .env")

    # Express mode prefers the OAuth access token: on this project that is the
    # credential the API actually accepts, while the plain API key is blocked
    # for aiplatform.
    xkey = express_key()
    if xkey:
        label = "vertex_express" + (
            " (oauth token)" if xkey == os.getenv("GOOGLE_OAUTH_ACCESS_TOKEN", "").strip()
            else " (api key)"
        )
        attempt(label, lambda: genai.Client(vertexai=True, api_key=xkey))
    else:
        print("  [skip] vertex_express: no GOOGLE_OAUTH_ACCESS_TOKEN or GOOGLE_API_KEY")

    if project:
        attempt(
            "vertex",
            lambda: genai.Client(vertexai=True, project=project, location=location),
        )
    else:
        print("  [skip] vertex: no GOOGLE_CLOUD_PROJECT in .env")

    print()
    working = [k for k, v in results.items() if v == "ok"]

    # A working generate_content does NOT imply Live API access: Live is a
    # separate surface, separately priced, and this module needs *that* one.
    # So probe it for real rather than inferring.
    if working:
        mode = working[0].split(" ")[0]
        live_model = resolve_model(mode)
        print(f"probing the Live API with {live_model.rsplit('/', 1)[-1]!r} "
              "(this is what voice actually needs)")
        live_ok = asyncio.run(
            _probe_live(mode, live_model, express_key() if mode == "vertex_express" else key,
                        project, location)
        )
        print()
        if not live_ok:
            print(
                f"{working[0]} can call ordinary models but NOT the Live API.\n"
                "Voice needs Live access; check the model name and that the\n"
                "platform exposes it to this project."
            )
            return 1

    if working:
        print(f"WORKING: {', '.join(working)}")
        print(f"Set NITYAM_AUTH={working[0].split(' ')[0]} in .env")
        if "oauth token" in working[0]:
            print(
                "\nNote: an OAuth access token expires after about an hour.\n"
                "When voice suddenly returns 401 UNAUTHENTICATED, that is why —\n"
                "mint a new GOOGLE_OAUTH_ACCESS_TOKEN and restart."
            )
        return 0

    print("NO MODE WORKS. What the failures mean:")
    if "no_credits" in results.values():
        print(
            "  * no_credits — the key authenticates, but the project has no\n"
            "    prepay balance. Every model call fails, live or not. Note that\n"
            "    a linked Cloud Billing account is NOT drawn on automatically:\n"
            "    you must buy credits at https://aistudio.google.com/app/billing"
        )
    if "no_adc" in results.values():
        print(
            "  * no_adc — Vertex needs Application Default Credentials.\n"
            "    Fix: brew install --cask google-cloud-sdk\n"
            "         gcloud auth application-default login\n"
            "         gcloud services enable aiplatform.googleapis.com"
        )
    if "expired" in results.values():
        print(
            "  * expired — the OAuth access token has lapsed. They last about\n"
            "    an hour. Mint a fresh GOOGLE_OAUTH_ACCESS_TOKEN and retry."
        )
    if "blocked" in results.values():
        print(
            "  * blocked — this API key is not authorised for aiplatform.\n"
            "    API keys only work on Vertex in Express mode, which must be\n"
            "    enabled on the project. Use NITYAM_AUTH=vertex with ADC."
        )
    print("\nMeanwhile: NITYAM_AUTH=mock runs the whole app with no network.")
    return 1


async def _probe_live(mode: str, model: str, key: str, project: str, location: str) -> bool:
    """Open a real Live session, say one word, and see if audio comes back."""
    from google import genai

    if mode == "ai_studio":
        client = genai.Client(api_key=key)
    elif mode == "vertex_express":
        client = genai.Client(vertexai=True, api_key=key)
    else:
        client = genai.Client(vertexai=True, project=project, location=location)

    config = {"response_modalities": ["AUDIO"], "output_audio_transcription": {}}
    try:
        async with client.aio.live.connect(model=model, config=config) as session:
            await session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part(text="Say hi.")])
            )
            audio_bytes = 0

            async def drain() -> int:
                total = 0
                async for message in session.receive():
                    content = message.server_content
                    if content and content.model_turn:
                        for part in content.model_turn.parts:
                            if part.inline_data:
                                total += len(part.inline_data.data)
                    if content and content.turn_complete:
                        break
                return total

            # wait_for rather than asyncio.timeout: the latter is 3.11+, and
            # ADK itself supports 3.10.
            audio_bytes = await asyncio.wait_for(drain(), timeout=45)
        print(f"  [ ok ] live: {audio_bytes} bytes of audio returned")
        return audio_bytes > 0
    except Exception as exc:
        print(f"  [fail] live: {type(exc).__name__}: {_short(exc)}")
        return False


def _short(exc: object, n: int = 150) -> str:
    return str(exc).replace("\n", " ")[:n]


def _classify(exc: Exception) -> str:
    text = str(exc).lower()
    if "credits are depleted" in text or "resource_exhausted" in text:
        return "no_credits"
    if "default credentials were not found" in text:
        return "no_adc"
    if "unauthenticated" in text or "invalid authentication" in text:
        return "expired"
    if "are blocked" in text or "permission_denied" in text:
        return "blocked"
    if "no longer available" in text or "not_found" in text:
        return "bad_model"
    return "error"


if __name__ == "__main__":
    sys.exit(preflight())
