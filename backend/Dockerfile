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

# Not secrets, despite what a Dockerfile linter will say about ARG/ENV here:
# Firebase's own docs are explicit that the web config (including the API
# key) is safe to expose client-side — it identifies the project, it does
# not authenticate anything. Firestore/Storage security is enforced by
# Firebase Security Rules, not by hiding this config. The real secret
# (GOOGLE_API_KEY, the backend's Gemini credential) is in Secret Manager,
# never here.
#
# Vite bakes VITE_* into the JS bundle at build time (import.meta.env),
# not read at container runtime — confirmed live: without these, the built
# app renders frontend/src/lib/firebase.ts's "not configured yet" fallback
# regardless of what env vars the running container later has. .dockerignore
# excludes .env from the build context entirely (secrets don't belong in a
# COPY), so these must arrive as --build-arg instead, e.g.:
#   docker buildx build --build-arg VITE_FIREBASE_API_KEY=... ...
ARG VITE_FIREBASE_API_KEY
ARG VITE_FIREBASE_AUTH_DOMAIN
ARG VITE_FIREBASE_PROJECT_ID
ARG VITE_FIREBASE_STORAGE_BUCKET
ARG VITE_FIREBASE_MESSAGING_SENDER_ID
ARG VITE_FIREBASE_APP_ID
ENV VITE_FIREBASE_API_KEY=$VITE_FIREBASE_API_KEY \
    VITE_FIREBASE_AUTH_DOMAIN=$VITE_FIREBASE_AUTH_DOMAIN \
    VITE_FIREBASE_PROJECT_ID=$VITE_FIREBASE_PROJECT_ID \
    VITE_FIREBASE_STORAGE_BUCKET=$VITE_FIREBASE_STORAGE_BUCKET \
    VITE_FIREBASE_MESSAGING_SENDER_ID=$VITE_FIREBASE_MESSAGING_SENDER_ID \
    VITE_FIREBASE_APP_ID=$VITE_FIREBASE_APP_ID

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM node:20-slim AS observatory-frontend
WORKDIR /obs-fe
COPY smriti-observatory/frontend/package.json smriti-observatory/frontend/package-lock.json ./
RUN npm ci
COPY smriti-observatory/frontend/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /app/backend

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN adduser --disabled-password --gecos "" myuser

COPY backend/ .
COPY --from=frontend /fe/dist /app/frontend/dist
COPY --from=observatory-frontend /obs-fe/dist /app/smriti-observatory/frontend/dist

# artifact_agent.py resolves this via a repo-root-relative sys.path walk
# (backend/app/agents/ -> ... -> repo root -> sub_modules_examples/artifact_generator)
# and generator.py reads prompt.md / ir/schema.json / examples/ at runtime via
# open() — the whole tree is needed, not just generate/. Confirmed live:
# without this, every ask_artifact call fails with
# "ModuleNotFoundError: No module named 'spec'" (same failure class as the
# earlier Shruti PYTHONPATH fix — a subdirectory-only COPY breaking a
# repo-root-relative import).
COPY sub_modules_examples/artifact_generator/ /app/sub_modules_examples/artifact_generator/

# app/main.py imports smriti-observatory/backend's `observatory` package as a
# sibling directory on sys.path (see app/main.py's _OBS_BACKEND insert) — the
# whole package tree is needed, not a subset, same reasoning as the
# artifact_generator COPY above.
COPY smriti-observatory/backend/observatory/ /app/smriti-observatory/backend/observatory/

RUN chown -R myuser:myuser /app
USER myuser

ENV PATH="/home/myuser/.local/bin:$PATH"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port $PORT"]
