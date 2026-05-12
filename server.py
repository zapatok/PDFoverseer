"""Entry point for PDFoverseer FASE 1 backend.

Boots the new month-folder-oriented FastAPI app from `api.main` with uvicorn
auto-reload. Honors HOST and PORT env vars; defaults bind localhost:8000.
"""

import os

import uvicorn

from api.main import app  # noqa: F401  uvicorn reload mode resolves the import string

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
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
