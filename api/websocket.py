import asyncio
from fastapi import WebSocket, WebSocketDisconnect, APIRouter, Query

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
    print(f"WS Attempt from session_id: {session_id}")
    try:
        await manager.connect(websocket, session_id)
        print("WS Connected!")
    except Exception as e:
        print(f"WS Connect Error: {e}")
        return
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)
