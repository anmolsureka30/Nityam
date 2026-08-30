# Build context is the REPO ROOT (same reasoning as backend/Dockerfile — the
# COPY paths below are relative to it). Build with:
#   docker build -f sub_modules_examples/shruti/Dockerfile -t nityam-shruti-job .
#
# This is a Cloud Run JOB image, not a service — it runs shruti.job_entrypoint
# once per Job execution and exits. See docs/superpowers/specs/
# 2026-08-30-cloud-run-deployment-design.md §2-4 for why Shruti has its own
# image/deployment shape instead of living inside the main backend container.

FROM python:3.12-slim
WORKDIR /app

# ffmpeg: Shruti's own video/audio processing. curl+unzip: the deno installer.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl unzip \
    && rm -rf /var/lib/apt/lists/*

# deno: yt-dlp's JS-challenge solver runtime — without it, YouTube extraction
# silently degrades (confirmed live during this session's own debugging).
RUN curl -fsSL https://deno.land/install.sh | sh -s -- -y
ENV PATH="/root/.deno/bin:$PATH"

RUN pip install --no-cache-dir uv

# Dependencies first (better layer caching), then the actual source.
COPY sub_modules_examples/shruti/pyproject.toml sub_modules_examples/shruti/uv.lock ./
RUN uv sync --frozen --no-install-project
COPY sub_modules_examples/shruti/ .
RUN uv sync --frozen

RUN uv tool install yt-dlp
ENV PATH="/root/.local/bin:$PATH"

CMD ["uv", "run", "python", "-m", "shruti.job_entrypoint"]
