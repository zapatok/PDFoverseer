"""
PDFoverseer FastAPI server.

Entry point for the backend. Exposes:
  - REST routes: /api/browse, /api/add_folder, /api/add_files, /api/preview,
                 /api/start, /api/stop, /api/state,
                 /api/sessions, /api/reset, /api/correct, /api/exclude, /api/restore
  - WebSocket:   /ws/{session_id}

Run:
    python server.py

Environment variables:
    HOST      Bind address (default: 127.0.0.1)
    PORT      Port (default: 8000)
    PDF_ROOT  Required — allowed root directory for PDF path validation
    SESSION_TTL  Session TTL in seconds (default: 3600)
"""

import os
import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from core import INFERENCE_ENGINE_VERSION
import api.websocket as ws
from api.websocket import router as ws_router
from api.routes import files, sessions, pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pdfoverserver")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Capture the main asyncio loop so background threads can broadcast
    ws.global_loop = asyncio.get_running_loop()

    async def _eviction_loop():
        while True:
            await asyncio.sleep(300)  # every 5 minutes
            from api.state import session_manager
            evicted = session_manager.evict_stale()
            if evicted:
                logger.info("Evicted %d stale sessions", evicted)

    task = asyncio.create_task(_eviction_loop())
    yield
    task.cancel()

app = FastAPI(title="PDFoverseer V3 API", lifespan=lifespan)
logger.info(f"Inference engine loaded: {INFERENCE_ENGINE_VERSION}")

# Allow CORS for local Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

frontend_path = Path(os.path.dirname(os.path.abspath(__file__))) / 'frontend' / 'dist'
if frontend_path.exists():
    app.mount("/ui", StaticFiles(directory=str(frontend_path), html=True), name="ui")
    assets_path = frontend_path / "assets"
    if assets_path.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_path)), name="assets")
else:
    logger.warning("UI directory %s not found. Build the frontend first.", frontend_path)

@app.get("/")
def read_root():
    return RedirectResponse(url="/ui/")

# Include routers
app.include_router(ws_router)
app.include_router(files.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(pipeline.router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(
        "server:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=port,
        reload=True,
        reload_excludes=[
            "*/__pycache__/*",
            "**/__pycache__/**",
            "*/data/*",
            "*/frontend/*",
            "*.db",
            "*.db-journal",
            "*.pyc",
            "*.log",
            "*.png",
            "*.json",
        ],
    )
