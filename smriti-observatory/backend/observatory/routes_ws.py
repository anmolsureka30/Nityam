from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from observatory.broadcaster import Broadcaster


def build_ws_router(broadcaster: Broadcaster) -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws/sessions/{session_id}")
    async def session_ws(websocket: WebSocket, session_id: str):
        await websocket.accept()
        queue = broadcaster.subscribe(session_id)
        try:
            while True:
                enriched = await queue.get()
                await websocket.send_json(enriched.model_dump(mode="json"))
        except WebSocketDisconnect:
            pass
        finally:
            broadcaster.unsubscribe(session_id, queue)

    @router.websocket("/ws/global")
    async def global_ws(websocket: WebSocket):
        await websocket.accept()
        queue = broadcaster.subscribe(None)
        try:
            while True:
                enriched = await queue.get()
                await websocket.send_json(enriched.model_dump(mode="json"))
        except WebSocketDisconnect:
            pass
        finally:
            broadcaster.unsubscribe(None, queue)

    return router
