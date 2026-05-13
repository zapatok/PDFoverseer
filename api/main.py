"""FastAPI app factory + lifespan."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import months, output, sessions, ws
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
    close_all()


def create_app() -> FastAPI:
    app = FastAPI(title="PDFoverseer", lifespan=lifespan)
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
    app.include_router(ws.router)
    return app


app = create_app()
