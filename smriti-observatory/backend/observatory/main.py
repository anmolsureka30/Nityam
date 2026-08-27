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

from app.memory import store
from observatory.broadcaster import Broadcaster
from observatory.ingest import run_ingest_loop
from observatory.routes_rest import build_router
from observatory.routes_ws import build_ws_router
from observatory.snapshot_cache import SnapshotCache

load_dotenv()

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
TUTOR_BASE_URL = os.environ.get("TUTOR_BASE_URL", "http://localhost:8000")

broadcaster = Broadcaster()
snapshot_cache = SnapshotCache()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.firestore = store.connect()

    def get_dpm(student_id: str):
        profile = store.get_dpm(app.state.firestore, student_id)
        return profile.model_dump(mode="json") if profile else None

    def get_teaching_memory(student_id: str):
        memory = store.get_teaching_memory(app.state.firestore, student_id)
        return memory.model_dump(mode="json") if memory else None

    ingest_task = asyncio.create_task(
        run_ingest_loop(REDIS_HOST, REDIS_PORT, snapshot_cache, broadcaster, get_dpm, get_teaching_memory)
    )
    yield
    ingest_task.cancel()
    app.state.firestore.close()


app = FastAPI(title="SMRITI Observatory", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(build_router(tutor_base_url=TUTOR_BASE_URL))
app.include_router(build_ws_router(broadcaster))
