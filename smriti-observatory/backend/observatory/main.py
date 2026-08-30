"""SMRITI Observatory backend entry point. Run with:
    uv run uvicorn observatory.main:app --reload --port 8100
"""
from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import firestore

from observatory.broadcaster import Broadcaster
from observatory.ingest import run_ingest_loop
from observatory.routes_rest import build_router
from observatory.routes_ws import build_ws_router
from observatory.snapshot_cache import SnapshotCache

load_dotenv()

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
GCP_PROJECT = os.environ.get("GCP_PROJECT", "nityam-506707")
FIRESTORE_DATABASE = os.environ.get("FIRESTORE_DATABASE", "smriti")
TUTOR_BASE_URL = os.environ.get("TUTOR_BASE_URL", "http://localhost:8000")

broadcaster = Broadcaster()
snapshot_cache = SnapshotCache()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.firestore = firestore.Client(project=GCP_PROJECT, database=FIRESTORE_DATABASE)

    def get_dpm(student_id: str):
        doc = app.state.firestore.collection("dpm_profiles").document(student_id).get()
        return doc.to_dict() if doc.exists else None

    def get_teaching_memory(student_id: str):
        doc = app.state.firestore.collection("teaching_memories").document(student_id).get()
        return doc.to_dict() if doc.exists else None

    ingest_task = asyncio.create_task(
        run_ingest_loop(REDIS_HOST, REDIS_PORT, snapshot_cache, broadcaster, get_dpm, get_teaching_memory)
    )
    yield
    ingest_task.cancel()
    app.state.firestore.close()


import httpx


async def _proxy_memory_state(session_id: str, student_id: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{TUTOR_BASE_URL}/memory/sessions/{session_id}/state",
            params={"student_id": student_id}, timeout=10.0,
        )
    return response.json()


async def _proxy_memory_events(session_id: str, student_id: str, trace_id: str | None) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{TUTOR_BASE_URL}/memory/sessions/{session_id}/events",
            params={"student_id": student_id}, timeout=10.0,
        )
    return response.json()


app = FastAPI(title="SMRITI Observatory", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(
    build_router(
        tutor_base_url=TUTOR_BASE_URL, redis_host=REDIS_HOST, redis_port=REDIS_PORT,
        memory_state_fn=_proxy_memory_state, memory_events_fn=_proxy_memory_events,
    )
)
app.include_router(build_ws_router(broadcaster))
