from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

PROJECT_ID = os.environ.get("GCP_PROJECT", "nityam-506707")
FIRESTORE_DATABASE = os.environ.get("FIRESTORE_DATABASE", "smriti-testbed")
GCS_BUCKET = os.environ.get("GCS_BUCKET", "nityam-506707-memory-testbed")
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
