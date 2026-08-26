"""Minimal, standalone test of the Gemini API key in .env.

Note: listing models (client.models.list()) is NOT a valid test — it
succeeds even with a $0 Prepay balance. The only real test is an actual
generate_content call, which is what this script does.

Usage:
    uv run --env-file .env python scripts/test_api_key.py
"""
import sys

from google import genai


def main() -> int:
    client = genai.Client()
    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=["reply with just: ok"],
        )
    except Exception as e:
        print("FAILED — the API key is not currently usable:")
        print(f"  {e!r}")
        return 1

    print("OK — the API key is working.")
    print(f"  Model replied: {response.text!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
