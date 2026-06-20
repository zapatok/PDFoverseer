"""WebSocket endpoint + broadcast helper for FASE 2 progress events."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

router = APIRouter()

_CONNECTIONS: dict[str, set[WebSocket]] = defaultdict(set)


async def broadcast(session_id: str, event: dict) -> None:
    """Send a JSON event to all WS connections for a session.

    Dead connections are pruned silently; no exception escapes. Callers on a
    non-asyncio thread should marshal via ``asyncio.run_coroutine_threadsafe``
    or ``loop.call_soon_threadsafe(asyncio.ensure_future, broadcast(...))``.
    """
    payload = json.dumps(event)
    dead: list[WebSocket] = []
    for ws in list(_CONNECTIONS.get(session_id, ())):
        try:
            await ws.send_text(payload)
        except Exception:  # noqa: BLE001
            dead.append(ws)
    for ws in dead:
        _CONNECTIONS[session_id].discard(ws)


def _emit(request: Request, session_id: str, event: dict) -> None:
    """Programa un broadcast WS desde un handler de ruta síncrono (M1).

    Los handlers son ``def`` síncronos → corren en un hilo del threadpool sin event
    loop, así que marshaleamos al loop guardado del app, igual que
    ``scan_ocr._safe_broadcast``. Best-effort: si no hay loop (un ``TestClient`` sin
    ``with`` no dispara el startup que fija ``app.state.loop``) o ya se cerró
    (teardown), se descarta el evento en vez de reventar la escritura — el broadcast
    nunca debe romper el camino HTTP real.
    """
    loop = getattr(request.app.state, "loop", None)
    if loop is None:
        return
    try:
        if not loop.is_closed():
            asyncio.run_coroutine_threadsafe(broadcast(session_id, event), loop)
    except RuntimeError:
        pass


@router.websocket("/ws/sessions/{session_id}")
async def session_socket(ws: WebSocket, session_id: str) -> None:
    await ws.accept()
    _CONNECTIONS[session_id].add(ws)
    try:
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=15.0)
            except asyncio.TimeoutError:
                await ws.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        return
    finally:
        _CONNECTIONS[session_id].discard(ws)
