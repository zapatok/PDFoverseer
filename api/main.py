"""FastAPI app factory + lifespan."""

from __future__ import annotations

import asyncio
import mimetypes
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.presence import CellLockedError
from api.routes import history, months, output, presence, sessions, siglas, ws
from api.routes.sessions import get_manager
from api.state import SessionManager
from core.db.connection import close_all, open_connection
from core.db.migrations import init_schema


def _db_path() -> Path:
    return Path(
        os.environ.get(
            "OVERSEER_DB_PATH",
            "A:/PROJECTS/PDFoverseer/data/overseer.db",
        )
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = open_connection(_db_path())
    init_schema(conn)
    manager = SessionManager(conn=conn)
    app.dependency_overrides[get_manager] = lambda: manager
    # FASE 2: capture loop for cross-thread WS broadcasts; init batch registry;
    # expose manager on app.state for tests that need to invoke setters directly
    # (e.g. Chunk 6 Task 31 history-method tests). Production code still goes
    # through Depends(get_manager).
    app.state.loop = asyncio.get_running_loop()
    app.state.batches = {}
    app.state.manager = manager
    yield
    # Graceful shutdown: cancela cualquier batch OCR en vuelo y espera a que su
    # hilo de dispatch termine ANTES de cerrar la DB. scan_cells_ocr hace join del
    # hilo de drain antes de retornar, así esperar el future garantiza que el merge
    # incremental por-archivo (Incr. 1A) no escriba sobre una conexión cerrada.
    batches = getattr(app.state, "batches", {})
    for handle in list(batches.values()):
        if handle.cancel_event is not None:
            handle.cancel_event.set()
    for handle in list(batches.values()):
        fut = getattr(handle, "future", None)
        if fut is not None:
            try:
                fut.result(timeout=10)
            except Exception:
                pass
    close_all()


def create_app() -> FastAPI:
    app = FastAPI(title="PDFoverseer", lifespan=lifespan)

    @app.exception_handler(CellLockedError)
    async def _cell_locked_handler(_request, exc: CellLockedError):
        return JSONResponse(
            status_code=409,
            content={
                "detail": "cell_locked",
                "hospital": exc.hospital,
                "sigla": exc.sigla,
                "lock_holder": exc.holder,
            },
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(months.router, prefix="/api")
    app.include_router(sessions.router, prefix="/api")
    app.include_router(output.router, prefix="/api")
    app.include_router(history.router, prefix="/api")
    app.include_router(siglas.router, prefix="/api")
    app.include_router(ws.router)
    app.include_router(presence.router, prefix="/api")
    # Serve the built frontend same-origin (multiplayer M1, LAN): a client on the LAN
    # loads http://<server>:8000/ and config.js derives the backend host from
    # window.location.hostname → API + WS hit the same origin (no CORS needed; the
    # localhost:5173 CORS rule above stays for local Vite dev). Mounted LAST so
    # /api/* and /ws/* take precedence; html=True serves index.html at "/". Skipped
    # when the build is absent (dev without `npm run build`).
    # Windows registers no MIME type for `.mjs`, so StaticFiles would serve the
    # Vite/pdf.js worker bundles as text/plain and browsers reject them under strict
    # module MIME checking (PDF preview fails with "No se pudo abrir el PDF"). Force
    # the correct JS type process-wide before mounting.
    mimetypes.add_type("text/javascript", ".mjs")
    mimetypes.add_type("text/javascript", ".js")
    _dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if _dist.is_dir():
        app.mount("/", StaticFiles(directory=_dist, html=True), name="ui")
    return app


app = create_app()
