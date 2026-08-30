# Build context is the REPO ROOT, not backend/ — this stage needs frontend/
# too. Build with: docker build -f backend/Dockerfile -t nityam-backend .
#
# Pattern per ADK's own documented Cloud Run Dockerfile (docs/deploy/cloud-run.md
# in google/adk-docs), extended with a frontend build stage: main.py already
# serves frontend/dist as static files if it exists (see main.py's DIST
# check) — this just has to produce that directory inside the image.
# See docs/superpowers/specs/2026-08-30-cloud-run-deployment-design.md §3.

FROM node:20-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /app/backend

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN adduser --disabled-password --gecos "" myuser

COPY backend/ .
COPY --from=frontend /fe/dist /app/frontend/dist

RUN chown -R myuser:myuser /app
USER myuser

ENV PATH="/home/myuser/.local/bin:$PATH"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port $PORT"]
