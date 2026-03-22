import asyncio
from fastapi import WebSocket, WebSocketDisconnect, APIRouter

from api.state import state

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except RuntimeError:
                pass

manager = ConnectionManager()

def _emit(event_type: str, payload: dict):
    """Schedules a broadcast on the main asyncio event loop."""
    if state.loop and state.loop.is_running():
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({"type": event_type, "payload": payload}), 
            state.loop
        )

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
