# Just commands for SHRUTI project

# Start Docker containers (Postgres, Redis, etc.)
up:
    docker compose -f docker/compose.yaml up -d

# Apply all pending SQL migrations
migrate:
    uv run shruti migrate

# Run the E4 provenance invariant check
provenance-check:
    uv run shruti provenance-check

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

# Display timeline for a recording
timeline recording_id:
    echo "SELECT * FROM v_timeline WHERE recording_id='{{recording_id}}'" | uv run python -c "import sys; print(sys.stdin.read())"
