"""WebSocket endpoint.

FASE 1: keep the connection alive with periodic pings — no progress events yet.
FASE 2 will broadcast scan progress events.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/sessions/{session_id}")
async def session_socket(ws: WebSocket, session_id: str) -> None:
    await ws.accept()
    try:
        while True:
            await asyncio.sleep(15)
            await ws.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        return
