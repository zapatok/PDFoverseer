import asyncio
import logging
import re as _re
from fastapi import WebSocket, WebSocketDisconnect, APIRouter, Query

_UUID_RE = _re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')

logger = logging.getLogger("pdfoverserver")

# Note: We removed the global state loop here, so broadcast requires loop from uvicorn directly
# Use asyncio.get_running_loop() or explicit passing.

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)

    def disconnect(self, websocket: WebSocket, session_id: str):
        if session_id in self.active_connections:
            if websocket in self.active_connections[session_id]:
                self.active_connections[session_id].remove(websocket)

    async def broadcast(self, session_id: str, message: dict):
        if session_id in self.active_connections:
            for connection in self.active_connections[session_id]:
                try:
                    await connection.send_json(message)
                except RuntimeError:
                    pass

manager = ConnectionManager()
global_loop = None

def _emit(session_id: str, event_type: str, payload: dict):
    """Schedules a broadcast on the main asyncio event loop."""
    if global_loop and global_loop.is_running():
        asyncio.run_coroutine_threadsafe(
            manager.broadcast(session_id, {"type": event_type, "payload": payload}), 
            global_loop
        )

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    logger.debug("WS attempt from session_id: %s", session_id)
    if not _UUID_RE.match(session_id or ""):
        await websocket.close(code=4003, reason="Invalid session ID")
        return
    try:
        await manager.connect(websocket, session_id)
        logger.debug("WS connected")
    except Exception as e:
        logger.warning("WS connect error: %s", e)
        return
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)
