# Just commands for SHRUTI project

# Start Docker containers (Postgres, Redis, etc.)
up:
    docker compose -f docker/compose.yaml up -d

# Apply all pending SQL migrations
migrate:
    uv run --env-file .env python -m shruti.cli migrate

# Run the E4 provenance invariant check
provenance-check:
    uv run --env-file .env python -m shruti.cli provenance-check

# Run tests
test:
    uv run pytest -v

# Run fast tests (excluding asyncio)
test-fast:
    uv run pytest -v -m "not asyncio"

# Run tests with coverage
test-cov:
    uv run pytest tests/ -v --cov=shruti

# Format and lint
lint:
    uv run ruff check . --fix

# Run everything
check: lint test

# Display the v_timeline debug view for a recording (read end to end —
# it should read like lecture notes; [board]/[gesture] show cross-modal sync)
timeline recording_id:
    uv run --env-file .env python -m shruti.cli timeline {{recording_id}}

# Display recovered board states — region/unreadable counts, one row each
boards recording_id:
    uv run --env-file .env python -m shruti.cli boards {{recording_id}}

# Display mined concepts in teaching order
concepts recording_id:
    uv run --env-file .env python -m shruti.cli concepts {{recording_id}}

# Ingest a video you already have as a local file
ingest video_path *args:
    uv run --env-file .env python scripts/ingest_video.py {{video_path}} {{args}}

# Interactive: prompts for a YouTube URL, downloads it, and runs the full pipeline
ingest-youtube:
    uv run --env-file .env python -m shruti.cli ingest
