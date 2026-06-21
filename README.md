# PDFoverseer

**PDF document analyzer** — counts the internal documents inside monthly prevention PDFs
per *(hospital, category)* and writes a 72-cell summary Excel (`RESUMEN_<YYYY>-<MM>.xlsx`).
It is "paso 2" of a three-step monthly pipeline (a sibling project normalizes the PDFs →
**PDFoverseer counts + generates the resumen** → another project builds the consolidated
stats workbook).

## Counting model (two regimes)

- **~90% filename-trivial** — 1 PDF = 1 document. Counted by filename glob, no OCR
  (`SimpleFilenameScanner`).
- **~10% implicit compilations** — many documents bundled into one PDF. Counted by OCR:
  - **Pagination-first** (`PaginationScanner`, the primary engine since 2026-06-21): OCRs
    only the top-right "Página N de M" corner, recovers unreadable corners by completing the
    numeric cycle from neighbors, and counts a document at each `curr == 1`. Low-confidence
    counts route to the keyboard counter for review.
  - **Header anchors** (`AnchorsScanner`): for the few templates that repeat "Página 1 de 2"
    on continuations (which would break pagination) — OCRs the header band and matches
    per-template cover anchors.

The per-sigla strategy lives in `core/scanners/patterns.py` (single source of truth). The
effective per-cell count is derived in one place — `core/cell_count.py` — so the UI, the
Excel, and the historical record can never disagree.

## Quick Start

```bash
# Install Python dependencies
pip install -r requirements.txt        # CPU-only (Tesseract + PyMuPDF)
# OR
pip install -r requirements-gpu.txt    # adds PyTorch CUDA (super-resolution for the deferred V4 path)

# Backend (FastAPI + WebSocket)
source .venv-cuda/Scripts/activate     # or: .\.venv-cuda\Scripts\activate (Windows)
python server.py                       # → http://localhost:8000

# Frontend (React + Vite)
cd frontend && npm install
npm run dev                            # → http://localhost:5173

# Tests / lint
pytest                                 # full suite
ruff check .                           # must be 0 violations
```

Open the month folder under `A:\informe mensual\<MES>\`; the app enumerates 4 hospitals ×
18 categories, counts pase 1 (filename glob), and lets you run pase 2 (OCR) per cell. Export
writes the RESUMEN Excel atomically to `data/outputs/` (override via `OVERSEER_OUTPUT_DIR`).

## Requirements

- **Python 3.10+**
- **Node.js 18+** (frontend)
- **Tesseract OCR** (system PATH or `TESSERACT_CMD` env var) — the sole OCR engine
  - Windows: <https://github.com/UB-Mannheim/tesseract/wiki>
- **PyMuPDF** (PDF rendering) — installed via requirements
- *Optional:* **CUDA** — only used by the deferred V4 fallback's super-resolution tier

## Tech Stack

- **Backend:** Python 3.10+ / FastAPI / PyMuPDF / Tesseract, single process (collaboration
  state is in-memory — never run with `--workers N`).
- **Frontend:** React + Vite, with live multiplayer sync/presence/locks over a per-session
  WebSocket.
- **Persistence:** SQLite (`overseer.db`) — session state + `historical_counts`.

## Collaboration (multiplayer)

Two people (and Claude, as a participant) can work the same month live: edits broadcast over
the WebSocket, presence shows who is in which cell, and per-cell locks prevent clobbering. See
the multiplayer design under `docs/superpowers/specs/`.

## Project layout

```
core/      OCR scanners + counting engine + DB + Excel writer   (see core/CLAUDE.md)
api/       FastAPI routes, sessions, presence, WebSocket         (see api/CLAUDE.md)
frontend/  React UI
eval/      evaluation harness: fixtures + sanctioned sandboxes   (see eval/CLAUDE.md)
tools/     standalone dev/audit utilities
docs/      specs, plans, research notes
```

> **Note on V4:** the original V4 OCR+inference engine (`core/pipeline.py`,
> `core/inference.py`, `core/ocr.py`) is retained as a *deferred fallback* — it is no longer
> wired into counting (the pagination engine replaced it) but kept importable for reference.

For the architecture and design history, see `CLAUDE.md`, `core/CLAUDE.md`, and the dated
specs/plans under `docs/superpowers/`.
