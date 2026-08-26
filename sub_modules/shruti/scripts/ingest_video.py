"""Thin CLI wrapper around shruti.ingest.run_ingest — for ingesting a video
you already have as a local file. For an interactive, YouTube-URL-prompting
version, use `shruti ingest` instead (shruti/cli.py).

Usage:
    uv run --env-file .env python scripts/ingest_video.py <video_path> [--subject S] [--grade G] [--chapter C]
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from google import genai
from shruti.ingest import run_ingest
from shruti.stages.echo.transcribe import build_whisper_model


def build_client() -> genai.Client:
    vertex_key = os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN")
    return genai.Client(vertexai=True, api_key=vertex_key) if vertex_key else genai.Client()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video_path")
    parser.add_argument("--subject", default=None)
    parser.add_argument("--grade", type=int, default=None)
    parser.add_argument("--chapter", default=None)
    args = parser.parse_args()

    print("Loading Whisper model (first run downloads several GB) ...")
    whisper_model = build_whisper_model()

    await run_ingest(args.video_path, build_client(), whisper_model, subject=args.subject,
                      grade=args.grade, chapter=args.chapter)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
