# Just commands for SHRUTI project

# Run tests
test:
    uv run pytest tests/ -v

# Run tests with coverage
test-cov:
    uv run pytest tests/ -v --cov=shruti

# Format and lint
lint:
    uv run ruff check . --fix

# Run everything
check: lint test
