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
# CPU-only (Tesseract + PyMuPDF)
pip install -r requirements.txt

# GPU (adds PyTorch CUDA for SR Tier 2 bicubic upscaling)
pip install -r requirements-gpu.txt
```

## Tech Stack

- **Backend:** Python 3.10+ with CUDA GPU, FastAPI, PyMuPDF, Tesseract
- **Frontend:** React + Vite, react-zoom-pan-pinch
- **OCR Pipeline:** V4 (6 parallel Tesseract workers, Tier 1 direct + Tier 2 SR-GPU)
- **Inference:** 5-phase engine with Dempster-Shafer post-validation
- **VLM Module:** Vision-Language Model benchmark/sweep for OCR comparison

## Project Structure

```
├── core/
│   ├── pipeline.py           # V4 Pipeline: 6 parallel Tesseract workers + telemetry
│   ├── ocr.py                # Tesseract tiers (1+2), SR GPU bicubic upsampling
│   ├── inference.py          # Multi-phase document boundary inference
│   ├── image.py              # Image preprocessing (render, crop, deskew)
│   ├── utils.py              # _PageRead, _parse(), shared constants + config
│   └── README.md             # Architecture notes (Spanish)
├── api/
│   ├── state.py              # SessionState + SessionManager
│   ├── websocket.py          # WebSocket connection manager + _emit()
│   ├── worker.py             # Background scan thread + callbacks
│   ├── database.py           # SQLite read/write (page_reads table)
│   └── routes/
│       ├── files.py          # /api/browse, /api/add_folder, /api/add_files, /api/preview
│       ├── sessions.py       # /api/sessions, /api/reset, /api/correct, etc.
│       └── pipeline.py       # /api/start, /api/stop, /api/state
├── vlm/                      # Vision-Language Model module
│   ├── client.py             # VLM API client
│   ├── parser.py             # VLM response parser
│   ├── preprocess.py         # Image preprocessing for VLM
│   ├── benchmark.py          # VLM benchmark runner
│   ├── ground_truth.py       # Ground truth management
│   ├── sweep.py              # VLM parameter sweep
│   ├── params.py             # VLM sweep parameters
│   ├── report.py             # VLM results reporter
│   └── results/              # VLM sweep results (ignored)
├── tools/                    # Standalone analysis utilities
│   ├── capture_all.py        # Capture all OCR page images
│   ├── capture_failures.py   # Capture OCR failure images
│   ├── preprocess_sweep.py   # Preprocessing parameter sweep
│   └── regex_pattern_test.py # Compare regex strategies on real OCR text (ART_670)
├── eval/                     # Evaluation harness (parameter sweep)
│   ├── inference.py          # Parameterized copy of inference pipeline
│   ├── sweep.py              # LHS sample → fine grid → beam search
│   ├── report.py             # Ranked results table
│   ├── extract_fixtures.py   # One-time fixture extraction
│   ├── params.py             # Sweep parameter space + production values
│   ├── graph_inference.py    # Graph-based inference engine
│   ├── graph_params.py       # Graph inference parameters
│   ├── graph_sweep.py        # Graph inference sweep
│   ├── compare_engines.py    # Compare inference engines
│   ├── ocr_benchmark.py      # OCR accuracy benchmark
│   ├── ocr_sweep.py          # OCR preprocessing sweep
│   ├── ocr_params.py         # OCR sweep parameters
│   ├── ocr_preprocess.py     # OCR preprocessing for eval
│   ├── ocr_report.py         # OCR sweep results
│   ├── hybrid_inference.py   # Hybrid inference approach
│   ├── ground_truth.json     # Ground truth data
│   ├── fixtures/
│   │   ├── real/             # 21 real PDFs (charlas CRS)
│   │   ├── synthetic/        # 13 synthetic test cases
│   │   ├── degraded/         # 6 degraded copies of real fixtures (~15-20% failed)
│   │   └── archived/         # Archived fixtures
│   ├── tests/
│   │   ├── test_inference.py
│   │   ├── test_sweep_scoring.py
│   │   ├── test_benchmark.py
│   │   ├── test_graph_inference.py
│   │   └── test_ocr_preprocess.py
│   └── results/              # Sweep results (ignored)
├── tests/                    # Integration + unit tests
│   ├── test_api.py           # FastAPI TestClient tests (no real OCR)
│   ├── test_database.py
│   ├── test_inference.py
│   ├── test_image.py
│   ├── test_utils.py
│   ├── test_max_total.py
│   ├── test_capture_failures.py
│   ├── test_preprocess_sweep.py
│   ├── test_vlm_benchmark.py
│   ├── test_vlm_client.py
│   ├── test_vlm_ground_truth.py
│   ├── test_vlm_parser.py
│   ├── test_vlm_preprocess.py
│   └── test_vlm_sweep.py
├── frontend/                 # React UI
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/       # ConfirmModal, CorrectionPanel, HeaderBar, HistoryModal,
│   │   │                     # IssueInbox, ProgressBar, Sidebar, Terminal
│   │   ├── hooks/            # useApi.js, useWebSocket.js
│   │   ├── lib/
│   │   └── store/
│   ├── package.json
│   └── vite.config.js
├── manual_test_logs/         # Manual test logs, one file per pipeline version/feature
├── models/                   # Super-resolution models
│   ├── FSRCNN_x4.pb          # Fast SR (default)
│   └── EDSR_x4.pb            # Enhanced SR (alternative)
├── data/
│   ├── sessions.db           # SQLite database (ignored)
│   ├── benchmark_results.json
│   ├── ocr_all/              # Full OCR captures
│   ├── ocr_failures/         # Failed OCR captures
│   ├── preprocess_sweep/     # Preprocessing sweep data
│   ├── inspection/           # Debug inspection images
│   └── samples/              # Sample data
├── docs/
│   ├── research/             # Research notes
│   └── superpowers/
│       ├── specs/            # Design specs
│       ├── plans/            # Implementation plans
│       └── reports/          # Analysis reports
├── server.py                 # FastAPI entry point
├── test_ws.py                # WebSocket smoke test (manual)
├── old_analyzer.py           # Reference: pre-modularization monolith
├── old_server.py             # Reference: pre-modularization server
└── requirements.txt          # Python dependencies (pinned exact versions)
```

## Architecture

### V4 Pipeline (core/pipeline.py)

**V4 Pipeline (Tess-SR only — EasyOCR removed 2026-03-26, see postmortem):**
1. **Producers** (6 parallel workers): PyMuPDF rendering + Tesseract (Tier 1 direct + Tier 2 w/ 4x SR GPU bicubic)
2. **Post-scan:**
   - Period detection (autocorrelation)
   - Dempster-Shafer evidence fusion
   - Confidence calibration
   - Report low-confidence inferred pages (<0.60)

### Key Configurations

All constants are in `core/utils.py`:

```python
DPI              = 150                    # Render DPI
CROP_X_START     = 0.70                   # rightmost 30%
CROP_Y_END       = 0.22                   # top 22%
TESS_CONFIG      = "--psm 6 --oem 1"     # Tesseract config
PARALLEL_WORKERS = 6                      # Tesseract concurrency
BATCH_SIZE       = 12                     # Pages per pause checkpoint

# Inference parameters (sweep2: 2026-03-24, 40 fixtures incl. degraded)
MIN_CONF_FOR_NEW_DOC = 0.55   # min confidence to open a new document boundary
CLASH_BOUNDARY_PEN   = 1.5    # gap-solver penalty for clash at boundaries
PHASE4_FALLBACK_CONF = 0.15   # re-enabled: recovers pages the gap solver missed
PH5B_CONF_MIN        = 0.50   # min period confidence to apply phase 5b correction
PH5B_RATIO_MIN       = 0.90   # lowered 0.95→0.90 (2026-03-26): fixes INS_31 OCR misreads, zero regressions on 41 fixtures
ANOMALY_DROPOUT      = 0.0    # anomaly suppression (disabled)
```

### Page Number Pattern

`PAGE_PATTERN_VERSION = "v1-baseline"` — current registry version (see `core/utils.py`)

`_PAGE_PATTERNS` (v1, baseline):
1. **Primary** `P.{0,6} N de M` — P-prefix, permissive OCR noise

Plausibility guard: `0 < curr <= total <= 10` (confirmed best after guard sweep 2026-03-26)

Matches: "Página 1 de 4", "Pag 2 de 3", etc. (Spanish-centric, with OCR digit normalization)

> **Note:** Word-anchor fallback (`\w+ N de M`) was evaluated and reverted — FP rate too high on ART_670.
> Guard variants tried: tot<=9 (worse), tot<=20 (worse), tot<=99 (much worse). tot<=10 is optimal.
> See `docs/superpowers/reports/2026-03-26-regex-guard-sweep.md` for full results.

## Development

### Git Info

- **Main branch:** `master`
- **Current branch:** `cuda-gpu`
- **Active worktree:** `.worktrees/pixel-density` → `feature/pixel-density`

### Worktrees

**Location:** `.worktrees/` (project-local, hidden)

**Active worktrees:**
- `.worktrees/pixel-density` → `feature/pixel-density` — pixel density delta clustering research (unmerged, conclusions documented)
- `.worktrees/crop-selector` → `feature/crop-selector` — UI crop region selector (unmerged, MVP complete)
- `.worktrees/ocr-matcher` → `feature/ocr-matcher` — fuzzy OCR pattern generator for "Página N de M" variants (unmerged)

**Stale branches (merged, pending deletion):**
- `feature/core-modularization` — 0 unique commits vs master, fully merged
- `feature/inference-engine` — merged via "merge: feature/inference-engine into master"

**Setup:** Use `superpowers:using-git-worktrees` skill to create isolated workspaces.

### Running Evaluation Harness

```bash
# Extract fixtures (one-time)
python eval/extract_fixtures.py

# Run parameter sweep (3 passes: ~500k combos)
python eval/sweep.py

# Print ranked results
python eval/report.py

# Compare inference engines
python eval/compare_engines.py

# Run OCR benchmark
python eval/ocr_benchmark.py
```

### VLM Module

```bash
# Run VLM as module
python -m vlm

# Run VLM benchmark
python vlm/benchmark.py

# Run VLM sweep
python vlm/sweep.py
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
[AI:<core_hash>] [MOD:v6-tess-sr] [CUDA:<hash>] [REG:<pattern_version>] file.pdf | 45p 3.2s 71ms/p | W6 | INF:s2t-helena
PRE5≡ DOC:5 COM:4(80%) INC:1 INF:3
OCR: direct:40,super_resolution:3
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
Method chars: `d`=direct, `s`=super_resolution, `e`=easyocr (legacy DB records only), `i`=inferred, `f`=failed

### Security

- **Path validation:** `api/routes/files.py` validates all submitted paths against `PDF_ROOT` to prevent directory traversal
- **subprocess.call** in `api_open_pdf` uses list form `[opener, str(path)]` — no shell injection possible; path is pre-validated against `pdf_list`
- **Session IDs:** validated as UUID4 format before use; invalid IDs rejected with HTTP 400 / WS close 4003
- **Server bind:** defaults to `127.0.0.1` — set `HOST=0.0.0.0` explicitly to expose on network

### OCR Assumptions

- **Spanish-centric regex** for "Página N de M" — adapt if needed for other languages
- **OCR digit normalization:** `O→0, I/i/l/L→1, z/Z→2, |→1, t/T→1, '→1`
- **Image preprocessing cascade:** deskew → color removal → red channel → inpainting → unsharp mask
- **Tesseract config:** `--psm 6 --oem 1` (uniform block text)

### GPU Pipeline

- SR Tier 2: PyTorch GPU bicubic 4x upscale inline in each Tesseract worker (~1ms/page vs ~150ms FSRCNN CPU fallback)
- No separate GPU consumer thread — EasyOCR removed after benchmark showed 0-1% accuracy on ART_670 GT pages

### Inference Engine

- **Version:** `s2t-helena` (see `INFERENCE_ENGINE_VERSION` in `core/utils.py`)
- **Phases 1–5 + MP + 5b:** OCR results → forward/backward propagation → cross-validation → gap-solver → D-S post-validation → multi-period correction
- **Confidence scores:** 0.0–1.0; <0.60 flagged as uncertain
- **Period inference:** Autocorrelation + Dempster-Shafer + neighbor evidence

## Conventions

### Git & Workflow
- **Commits:** English, format: `type(scope): message`
  - Examples: `feat(ocr): add SR tier 2`, `fix(inference): D-S calibration`
- **Branches:** Feature branches from `master` (or `cuda-gpu` when working on GPU features)
  - Pattern: `feature/name` or `fix/issue-name`
- **Tests:** Always pass before merge (no skipped/pending tests)
- **DB mocking:** Avoid mocking in tests — use real fixtures where possible
- **Worktrees:** Use `.worktrees/<name>` for isolated feature work (see `superpowers:using-git-worktrees`)

### Code Quality
- **Linting:** `ruff check .` must report **0 violations** before committing
  - Config in `pyproject.toml`; rules: E, F, W, I (isort), UP (pyupgrade)
  - Intentional late imports (after `sys.path` manipulation): suppress with `# noqa: E402`
- **Dead code:** Remove unused imports, variables, and unreachable assignments — never commit them
- **No bare `except:`** — catch specific types (`except ValueError`, `except Exception` at minimum)
- **No `print()` in library code** — use `logging.getLogger(__name__)`; `print()` only in CLI entry points and standalone tools

### Types & Docstrings
- **Type annotations:** Use Python 3.10+ syntax: `X | None` not `Optional[X]`, `list[X]` not `List[X]`
- **Docstrings:** Public entry points (functions callable from outside the module) need Google-style docstrings with `Args:` and `Returns:` sections

### Architecture
- **Constants:** Magic numbers belong in `core/utils.py` (pipeline/inference config) or at module level — never inline
- **One responsibility per file:** Each module has a single clear purpose; if a file is doing two things, split it
- **Module docs:** New packages/modules get a `README.md` explaining their purpose, files, and usage

## Links

- **Eval spec:** `docs/superpowers/specs/2026-03-15-eval-harness-design.md`
- **Eval plan:** `docs/superpowers/plans/2026-03-15-eval-harness.md`
- **EasyOCR postmortem:** `docs/superpowers/reports/2026-03-25-easyocr-paddle-postmortem.md`
- **Core README:** `core/README.md`
- **Memory:** `C:\Users\Daniel\.claude\projects\a--PROJECTS-PDFoverseer\memory\`

## Pending Work

- **INS_31:** ~~Last-page inference gap~~ FIXED (2026-03-26): ph5b_ratio_min 0.95→0.90, now 31/31 docs. Tray UX improvements still pending.
- **Eval sweep2:** Refined grid around sweep1 winners is ready in `eval/params.py`; next run pending (ph5b_ratio_min=0.90 is new baseline)
- **Browse UX:** `/api/browse` opens a server-side tkinter chooser (Archivos/Carpeta) — works only when server is on local machine with a display
