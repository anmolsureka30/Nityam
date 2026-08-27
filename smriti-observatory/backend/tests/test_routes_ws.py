from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from observatory.broadcaster import Broadcaster
from observatory.events import EnrichedEvent, MemoryEvent
from observatory.routes_ws import build_ws_router


@pytest.fixture
def app_and_broadcaster():
    broadcaster = Broadcaster()
    app = FastAPI()
    app.include_router(build_ws_router(broadcaster))
    return app, broadcaster


def test_session_websocket_receives_published_events(app_and_broadcaster):
    app, broadcaster = app_and_broadcaster
    client = TestClient(app)
    with client.websocket_connect("/ws/sessions/s1") as ws:
        event = MemoryEvent(
            event_id="e1", ts="2026-08-27T00:00:00Z", session_id="s1", student_id="stu",
            tier="workflow", operation="write", record_type="turn_buffer",
            source_fn="append_turn", trace_id=None, span_id=None, payload=None,
        )
        broadcaster.publish(EnrichedEvent(event=event, diff=[]))
        received = ws.receive_json()
        assert received["event"]["event_id"] == "e1"


def test_global_websocket_receives_all_sessions_events(app_and_broadcaster):
    app, broadcaster = app_and_broadcaster
    client = TestClient(app)
    with client.websocket_connect("/ws/global") as ws:
        event = MemoryEvent(
            event_id="e2", ts="2026-08-27T00:00:00Z", session_id="any-session", student_id="stu",
            tier="workflow", operation="write", record_type="turn_buffer",
            source_fn="append_turn", trace_id=None, span_id=None, payload=None,
        )
        broadcaster.publish(EnrichedEvent(event=event, diff=[]))
        received = ws.receive_json()
        assert received["event"]["event_id"] == "e2"
