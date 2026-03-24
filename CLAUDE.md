# PDFoverseer

**PDF document analyzer** that counts internal documents in lecture PDFs (CRS) using an OCR + AI inference engine.

## Quick Start

```bash
# Backend (inference + API)
source .venv-cuda/Scripts/activate  # or: .\.venv-cuda\Scripts\activate (Windows)
python server.py                     # FastAPI on http://localhost:8000

# Frontend (React UI)
cd frontend && npm run dev           # Vite on http://localhost:5173

# Tests
pytest
```

## Installation

```bash
# CPU-only (Tesseract + PyMuPDF, no EasyOCR)
pip install -r requirements.txt

# GPU (adds EasyOCR + PyTorch CUDA)
pip install -r requirements-gpu.txt
```

## Tech Stack

- **Backend:** Python 3.10+ with CUDA GPU, FastAPI, PyMuPDF, Tesseract, EasyOCR
- **Frontend:** React + Vite, react-zoom-pan-pinch
- **OCR Pipeline:** V4 (producer-consumer) with GPU acceleration
- **Inference:** 5-phase engine with Dempster-Shafer post-validation

## Project Structure

```
├── core/
│   ├── pipeline.py           # V4 Pipeline: producer-consumer scan + telemetry
│   ├── ocr.py                # Tesseract tiers, EasyOCR reader, SR upsampling
│   ├── inference.py          # Multi-phase document boundary inference
│   ├── image.py              # Image preprocessing (render, crop, Otsu, etc.)
│   ├── utils.py              # _PageRead, _parse(), shared constants
│   └── __init__.py
├── api/
│   ├── state.py              # SessionState + SessionManager
│   ├── websocket.py          # WebSocket connection manager + _emit()
│   ├── worker.py             # Background scan thread + callbacks
│   ├── database.py           # SQLite read/write (page_reads table)
│   └── routes/
│       ├── files.py          # /api/browse (tkinter dialog), /api/add_folder, /api/add_files, /api/preview
│       ├── sessions.py       # /api/sessions, /api/reset, /api/correct, etc.
│       └── pipeline.py       # /api/start, /api/stop, /api/state
├── eval/                     # Evaluation harness (parameter sweep)
│   ├── inference.py          # Parameterized copy of inference pipeline
│   ├── sweep.py              # LHS sample → fine grid → beam search
│   ├── report.py             # Ranked results table
│   ├── extract_fixtures.py   # One-time fixture extraction
│   ├── params.py             # Sweep parameter space + production values
│   ├── fixtures/
│   │   ├── real/             # 21 real PDFs (charlas CRS)
│   │   ├── synthetic/        # 13 synthetic test cases
│   │   └── degraded/         # 6 degraded copies of real fixtures (~15-20% failed)
│   ├── tests/
│   │   ├── test_inference.py # Inference unit tests (eval harness)
│   │   └── test_sweep_scoring.py
│   └── results/              # Sweep results (ignored)
├── tests/                    # Integration + unit tests
│   ├── test_api.py           # FastAPI TestClient tests (no real OCR)
│   ├── test_database.py
│   ├── test_inference.py
│   ├── test_tray_issues.py
│   └── test_utils.py
├── frontend/                 # React UI
│   ├── src/
│   ├── package.json
│   └── vite.config.js
├── models/                   # FSRCNN_x4.pb (super-resolution)
├── data/
│   └── sessions.db           # SQLite database (ignored)
├── server.py                 # FastAPI entry point
├── test_ws.py                # WebSocket smoke test (manual)
├── old_analyzer.py           # Reference: pre-modularization monolith
├── old_server.py             # Reference: pre-modularization server
└── requirements.txt          # Python dependencies (pinned exact versions)
```

## Architecture

### V4 Pipeline (core/pipeline.py)

**Producer-Consumer Pattern:**
1. **Producers** (6 parallel workers): PyMuPDF rendering + Tesseract (Tier 1 + Tier 2 w/ SR)
2. **GPU Consumer** (1 dedicated thread): EasyOCR on failed pages
3. **Post-scan:**
   - Period detection (autocorrelation)
   - Dempster-Shafer evidence fusion
   - Confidence calibration
   - Report low-confidence inferred pages (<0.60)

### Key Configurations

```python
DPI              = 150                    # Render DPI
CROP_X_START     = 0.70                   # rightmost 30%
CROP_Y_END       = 0.22                   # top 22%
PARALLEL_WORKERS = 6                      # Tesseract concurrency
BATCH_SIZE       = 12                     # Pages per pause checkpoint

# Inference parameters (sweep2: 2026-03-24, 40 fixtures incl. degraded)
MIN_CONF_FOR_NEW_DOC = 0.55   # min confidence to open a new document boundary
CLASH_BOUNDARY_PEN   = 1.5    # gap-solver penalty for clash at boundaries
PHASE4_FALLBACK_CONF = 0.15   # re-enabled: recovers pages the gap solver missed
PH5B_CONF_MIN        = 0.50   # min period confidence to apply phase 5b correction
PH5B_RATIO_MIN       = 0.95   # min ratio of reads with expected total to correct
ANOMALY_DROPOUT      = 0.0    # anomaly suppression (disabled)
```

### Page Number Pattern

```regex
P.{0,2}[gq](?:ina?)?\.?\s*(\d{1,3})\s*\.?\s*de\s*(\d{1,3})
```
Matches: "Página 1 de 10", "Pag 1 de 10", "page 1 of 10", etc. (Spanish-centric)

## Development

### Worktrees

**Location:** `.worktrees/` (project-local, hidden)

**Setup:** Use `superpowers:using-git-worktrees` skill to create isolated workspaces.

### Running Evaluation Harness

```bash
# Extract fixtures (one-time)
python eval/extract_fixtures.py

# Run parameter sweep (3 passes: ~500k combos)
python eval/sweep.py

# Print ranked results
python eval/report.py
```

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `HOST` | `127.0.0.1` | Server bind address (`server.py`) |
| `PORT` | `8000` | Server port |
| `TESSERACT_CMD` | system PATH | Override Tesseract binary path |
| `PDF_ROOT` | _(required)_ | Allowed root dir for PDF path validation |
| `SESSION_TTL` | `3600` | Session TTL in seconds before eviction |

### Key Commands

| Command | Purpose |
|---------|---------|
| `python server.py` | Start FastAPI backend + WebSocket |
| `cd frontend && npm run dev` | Start React dev server |
| `pytest` | Run test suite |

## Important Notes

### Telemetry Log Format

After each PDF scan, `core/pipeline.py` emits two machine-dense log blocks:

**`[AI:]` block** (log level `"ai"`) — scan summary:
```
[AI:<core_hash>] [MOD:v3.1-fix] [CUDA:<hash>] file.pdf | 45p 3.2s 71ms/p | W6+GPU | INF:soft-alignment-v3-sweep1
PRE5≡ DOC:5 COM:4(80%) INC:1 INF:3
OCR: direct:40,super_resolution:3,easyocr:2
DOCS: 5total → 4ok+1bad(seq:0 under:1) | dist: 3p×2 5p×3
INF: 3total(low:1 mid:1 hi:1) | LOW: p12=2/3(42%)
FAIL: 2pp:7,23
```

**`[DS:]` block** (log level `"ai_inf"`) — inference cross-validation:
```
[DS:<core_hash>] D:5 P:P=3 conf=85% expect=3
INF:3 x̄=72% 1✓1~1✗
✓12:2/3d>3/3@91%>1/3d
~15:3/3s>1/3@55%>2/3d
✗7:->=/>1/3@38%>2/3d
```

XVAL entry format: `<pdf_page>:<left_neighbor>><curr>/<total>@<conf%>><right_neighbor>`
Method chars: `d`=direct, `s`=super_resolution, `e`=easyocr, `i`=inferred, `f`=failed

### Security

- **Path validation:** `api/routes/files.py` validates all submitted paths against `PDF_ROOT` to prevent directory traversal
- **subprocess.call** in `api_open_pdf` uses list form `[opener, str(path)]` — no shell injection possible; path is pre-validated against `pdf_list`
- **Session IDs:** validated as UUID4 format before use; invalid IDs rejected with HTTP 400 / WS close 4003
- **Server bind:** defaults to `127.0.0.1` — set `HOST=0.0.0.0` explicitly to expose on network

### OCR Assumptions

- **Spanish-centric regex** for "Página N de M" — adapt if needed for other languages
- **Image preprocessing cascade:** Otsu → color removal → red channel → inpainting
- **Tesseract config:** `--psm 6 --oem 1` (uniform block text)

### GPU Pipeline

- EasyOCR runs on GPU thread while Tesseract continues (concurrent)
- Fallback only triggered if Tesseract tiers fail
- GPU memory managed via single-threaded consumer

### Inference Engine

- **Version:** `soft-alignment-v3-sweep2` (see `INFERENCE_ENGINE_VERSION` in `core/utils.py`)
- **Phases 1–5 + MP + 5b:** OCR results → forward/backward propagation → cross-validation → gap-solver → D-S post-validation → multi-period correction
- **Confidence scores:** 0.0–1.0; <0.60 flagged as uncertain
- **Period inference:** Autocorrelation + Dempster-Shafer + neighbor evidence

## Conventions

- **Commits:** English, format: `type(scope): message`
  - Examples: `feat(ocr): add EasyOCR fallback`, `fix(inference): D-S calibration`
- **Branches:** Feature branches from `master`
  - Pattern: `feature/name` or `fix/issue-name`
- **Tests:** Always pass before merge (no skipped/pending tests)
- **DB mocking:** Avoid mocking in tests — use real fixtures where possible

## Links

- **Main branch:** `master`
- **Active branch:** `feature/core-modularization`
- **Eval spec:** `docs/superpowers/specs/2026-03-15-eval-harness-design.md`
- **Eval plan:** `docs/superpowers/plans/2026-03-15-eval-harness.md`
- **Memory:** `C:\Users\Daniel\.claude\projects\a--PROJECTS-PDFoverseer\memory\`

## Pending Work

- **INS_31:** Last-page inference gap + tray UX improvements to reduce human intervention
- **Eval sweep2:** Refined grid around sweep1 winners is ready in `eval/params.py`; next run pending
- **Browse UX:** `/api/browse` opens a server-side tkinter chooser (Archivos/Carpeta) — works only when server is on local machine with a display
