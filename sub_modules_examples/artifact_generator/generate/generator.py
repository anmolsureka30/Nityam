"""spec -> IR.

Two paths, on purpose:

  mock  loads examples/ir_projectile.json. Deterministic, offline, instant.
        This is the path you demo on stage.

  live  asks Gemini to emit the IR, then validates it and retries once with the
        validator's errors fed back. This is the path that proves the concept.

Note what Gemini is and is not asked to do. It never writes physics, never
writes JavaScript, never decides layout. It writes a configuration of parts
that already exist and are already trusted.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEFAULT_MODEL = os.environ.get("NITYAM_MODEL", "gemini-2.5-flash")


def generate_mock(spec):
    with open(os.path.join(ROOT, "examples", "lesson1_max_range.json")) as f:
        return json.load(f), "mock (golden IR)"


def _build_prompt(spec):
    with open(os.path.join(HERE, "prompt.md")) as f:
        system = f.read()
    with open(os.path.join(ROOT, "ir", "schema.json")) as f:
        schema = f.read()
    with open(os.path.join(ROOT, "examples", "lesson1_max_range.json")) as f:
        example = f.read()

    return (
        system
        + "\n\n## IR JSON Schema\n```json\n" + schema + "\n```"
        + "\n\n## A complete, valid example IR\n```json\n" + example + "\n```"
        + "\n\n## The ArtifactSpec you must satisfy\n```json\n" + spec.to_prompt_json() + "\n```"
        + "\n\nReturn ONLY the IR JSON object. No prose, no markdown fence."
    )


def generate_live(spec, validate_fn, model=DEFAULT_MODEL, max_attempts=2):
    try:
        from google import genai
    except ImportError:
        sys.exit(
            "\n  --live needs the Gemini SDK.\n"
            "    pip install google-genai\n"
            "    export GEMINI_API_KEY=...\n"
        )

    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        sys.exit("\n  Set GEMINI_API_KEY (or GOOGLE_API_KEY) in your environment.\n")

    client = genai.Client(api_key=key)
    prompt = _build_prompt(spec)
    last_errors = None

    for attempt in range(1, max_attempts + 1):
        msg = prompt
        if last_errors:
            msg += ("\n\n## Your previous attempt FAILED validation\n"
                    + "\n".join("- " + e for e in last_errors)
                    + "\nEmit a corrected IR that fixes every one of these.")

        print(f"  generating   -> {model} (attempt {attempt}/{max_attempts})")
        resp = client.models.generate_content(
            model=model,
            contents=msg,
            config={"response_mime_type": "application/json", "temperature": 0.2},
        )
        raw = (resp.text or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            raw = raw[4:] if raw.startswith("json") else raw

        try:
            ir = json.loads(raw)
        except json.JSONDecodeError as e:
            last_errors = [f"response was not valid JSON: {e}"]
            continue

        report = validate_fn(ir)
        if report.ok:
            return ir, f"live ({model}, attempt {attempt})"

        last_errors = report.errors
        print(f"  validation   -> rejected, {len(last_errors)} error(s), feeding back")
        for e in last_errors[:6]:
            print(f"                 - {e}")

    print("\n  Live generation did not pass the gate. Falling back to the golden IR.")
    print("  (This is the tiered fallback from the design: a student never sees an unvalidated artifact.)\n")
    ir, _ = generate_mock(spec)
    return ir, "mock fallback (live rejected by validator)"
