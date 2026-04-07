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
│   ├── pattern_eval.py       # Pattern evaluation utility
│   ├── preprocess_sweep.py   # Preprocessing parameter sweep
│   └── regex_pattern_test.py # Compare regex strategies on real OCR text (ART_670)
├── eval/                     # Evaluation harness (organized by investigation stage)
│   ├── shared/               # Shared types and loaders
│   │   ├── types.py          # PageRead, Document dataclasses (single source of truth)
│   │   └── loaders.py        # load_fixtures(), load_ground_truth()
│   ├── inference_tuning/     # Parameter sweep for core/inference.py
│   │   ├── inference.py      # Parameterized copy of core/inference.py
│   │   ├── params.py         # PARAM_SPACE + PRODUCTION_PARAMS
│   │   ├── sweep.py          # LHS sample → fine grid → beam search
│   │   ├── report.py         # Ranked results table
│   │   ├── baseline_art674.py       # ART_674 baseline runner
│   │   ├── baseline_art674_tess.py  # ART_674 Tesseract baseline runner
│   │   └── results/          # Sweep results (gitignored)
│   ├── graph_inference/      # Experimental graph-based inference (HMM + Viterbi)
│   │   ├── engine.py         # Graph inference engine
│   │   ├── params.py         # Graph engine parameters
│   │   ├── sweep.py          # Graph engine sweep
│   │   ├── hybrid.py         # Phases 0-6 + Viterbi global decoder
│   │   ├── compare.py        # Head-to-head engine comparison
│   │   └── results/          # Sweep results (gitignored)
│   ├── ocr_preprocessing/    # OCR image preprocessing sweeps
│   │   ├── preprocess.py     # Preprocessing pipeline variants
│   │   ├── params.py         # Preprocessing parameter space
│   │   ├── sweep.py          # Preprocessing sweep runner
│   │   ├── report.py         # Preprocessing results
│   │   └── results/          # Sweep results (gitignored)
│   ├── ocr_engines/          # OCR engine benchmarks (EasyOCR, PaddleOCR)
│   │   └── benchmark.py      # Engine accuracy benchmark
│   ├── pixel_density/        # Bilateral pixel density cover detection (no OCR)
│   │   ├── pixel_density.py  # Core: rendering, dark_ratio, grid, L2, clustering
│   │   ├── params.py         # BEST_COUNT_CONFIG + BEST_QUALITY_CONFIG (PD_BASELINE)
│   │   ├── sweep_bilateral.py       # Bilateral scores + K-Means classification
│   │   ├── sweep_preprocessing.py   # 8 variants: CLAHE, Otsu, ink, red channel
│   │   ├── baseline.py              # Full 54-combo standalone sweep + VLM eval
│   │   ├── inspect_pages.py          # 3-way diff (bilateral vs Tesseract)
│   │   ├── audit_coverage.py        # Pipeline cross-reference + VLM GT
│   │   ├── characterize_density.py  # Density regimes + bimodality
│   │   ├── simulate_injection.py    # Realistic injection simulation
│   │   ├── simulate_naive.py        # Naive injection (total=1)
│   │   └── extract_pages.py         # PNG extraction for visual inspection
│   ├── tests/                # Centralized tests for all stages
│   │   ├── test_inference.py
│   │   ├── test_sweep_scoring.py
│   │   ├── test_graph_inference.py
│   │   ├── test_preprocess.py
│   │   ├── test_ocr_preprocess.py
│   │   ├── test_ocr_preprocess_new.py
│   │   ├── test_pixel_density.py
│   │   └── test_benchmark.py
│   ├── fixtures/
│   │   ├── real/             # 21 real PDFs (charlas CRS)
│   │   ├── synthetic/        # 13 synthetic test cases
│   │   ├── degraded/         # 7 degraded copies (~15-20% OCR failure rate)
│   │   ├── archived/         # Archived fixtures
│   │   ├── ground_truth.json # Expected document counts per fixture
│   │   ├── extract_fixtures.py      # Fixture extraction from real PDFs (Tess+SR)
│   │   └── extract_art674_tess.py   # ART_674 Tesseract fixture extraction
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
│   └── samples/              # Source PDFs for scan + fixture extraction (21 PDFs: ALUM_1, ALUM_19, ART_670[=ART_674], CASTRO_15, CASTRO_5, CHAR_17, CHAR_25, CH_39, CH_51docs, CH_74docs, CH_9, CH_BSM_18, CRS_9, INSAP_20, INS_31.pdf.pdf, JOGA_19, QUEVEDO_1, QUEVEDO_13, QUEVEDO_2, RACO_25, SAEZ_14)
├── docs/
│   ├── research/             # Research notes
│   └── superpowers/
│       ├── specs/            # Design specs
│       ├── plans/            # Implementation plans
│       └── reports/          # Analysis reports
├── archived/                 # Reference copies: pre-modularization monolith + server
├── server.py                 # FastAPI entry point
├── test_ws.py                # WebSocket smoke test (manual)
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
CLASH_BOUNDARY_PEN   = 1.5   # gap-solver penalty for clash at boundaries
PHASE4_FALLBACK_CONF = 0.15  # re-enabled: recovers pages the gap solver missed
PH5B_CONF_MIN        = 0.50  # min period confidence to apply phase 5b correction
PH5B_RATIO_MIN       = 0.90  # lowered 0.95→0.90: fixes INS_31 OCR misreads, zero regressions on 40 fixtures
ANOMALY_DROPOUT      = 0.0   # soft dropout for singleton anomalies in homogeneous regions
```

### Page Number Pattern

`PAGE_PATTERN_VERSION = "v1-baseline"` — current registry version (see `core/utils.py`)

`_PAGE_PATTERNS` (v1, baseline):
1. **Primary** `P.{0,6} N de M` — P-prefix, permissive OCR noise

Plausibility guard: `0 < curr <= total <= 10` (confirmed best after guard sweep 2026-03-26)

Matches: "Página 1 de 4", "Pag 2 de 3", etc. (Spanish-centric, with OCR digit normalization)

> **Note:** Word-anchor fallback (`\w+ N de M`) was evaluated and reverted — FP rate too high on ART_670.
> Guard variants tried: tot<=9 (worse), tot<=20 (worse), tot<=99 (much worse). tot<=10 is optimal.
> See `docs/superpowers/plans/2026-03-26-word-anchor-fallback.md` for full results.

## Development

### Git Info

- **Main branch:** `master`
- **Current branch:** `master`
- **Active worktrees:** `.worktrees/pixel-density`, `.worktrees/crop-selector`, `.worktrees/ocr-matcher`

### Worktrees

**Location:** `.worktrees/` (project-local, hidden)

**Active worktrees:**
- `.worktrees/pixel-density` → `feature/pixel-density` — pixel density delta clustering research (unmerged, conclusions documented)
- `.worktrees/crop-selector` → `feature/crop-selector` — UI crop region selector (unmerged, MVP complete)
- `.worktrees/ocr-matcher` → `feature/ocr-matcher` — fuzzy OCR pattern generator for "Página N de M" variants (unmerged)

**Stale branches (merged, pending deletion):**
- `feature/inference-engine` — merged via "merge: feature/inference-engine into master"

**Setup:** Use `superpowers:using-git-worktrees` skill to create isolated workspaces.

### Running Evaluation Harness

```bash
# Extract fixtures (one-time)
python eval/fixtures/extract_fixtures.py

# Inference tuning (primary workflow)
python eval/inference_tuning/sweep.py
python eval/inference_tuning/report.py

# Graph inference (experimental)
python eval/graph_inference/sweep.py
python eval/graph_inference/compare.py

# OCR preprocessing sweep
python eval/ocr_preprocessing/sweep.py
python eval/ocr_preprocessing/report.py

# OCR engine benchmark
python eval/ocr_engines/benchmark.py

# Pixel density (standalone cover detection, no OCR)
python eval/pixel_density/baseline.py           # full 54-combo sweep
python eval/pixel_density/inspect_pages.py            # 3-way diff vs Tesseract
python eval/pixel_density/inspect_pages.py --diagnose # per-page score table
python eval/pixel_density/audit_coverage.py     # pipeline cross-reference
python eval/pixel_density/characterize_density.py --bimodality  # density regimes
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
Method chars: `d`=direct, `s`=super_resolution, `e`=easyocr (legacy DB records only), `i`=inferred, `f`=failed, `v`=vlm_ollama, `V`=vlm_claude

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

### Guardrails & Hooks

**Hookify rules** (`.claude/hookify.*.local.md`) enforce code quality + safety at file write time:

| Rule | Type | Purpose |
|------|------|---------|
| **eval-before-core** | warn | Inference changes must be tested in `eval/inference.py` first — warns before editing `core/inference.py`, requires user approval at prompt |
| **no-bare-except** | **BLOCK** | All exception handlers must catch specific types (not bare `:`) |
| **no-shell-true** | **BLOCK** | Never use `shell=True` in subprocess calls — always use list form |
| **no-sql-fstrings** | **BLOCK** | SQL queries must use `?` parameterized form, never f-strings |
| **no-print-in-libs** | warn | `print()` forbidden in `core/`, `api/`, `vlm/`, `eval/` — use `logging.getLogger(__name__)` |
| **ruff-before-done** | warn | Verify `ruff check .` passes (0 violations) before stopping |
| **no-legacy-typing** | warn | Use Python 3.10+ syntax: `X \| None` not `Optional[X]`, `list[X]` not `List[X]` |
| **bump-version-tags** | warn | Update `PAGE_PATTERN_VERSION` or `INFERENCE_ENGINE_VERSION` after pipeline changes |
| **constants-in-utils** | warn | Pipeline constants belong in `core/utils.py`, not scattered across files |
| **no-db-mocking** | warn | Project convention: never mock database in tests; use real SQLite fixtures |
| **torch-try-except** | warn | Torch imports must be wrapped in try/except for CPU fallback |

Rules take effect immediately (no restart needed). BLOCK rules prevent tool execution; warn rules show a message but allow it.

## Links

- **Eval reorg plan:** `docs/superpowers/plans/2026-03-28-eval-reorganization.md`
- **VLM integration postmortem:** `docs/superpowers/reports/2026-03-29-vlm-integration-postmortem.md`
- **Pixel density research (V1):** `docs/research/2026-03-31-bilateral-pixel-density.md`
- **Pixel density advanced sweep + rescue (V2 RC):** `docs/research/2026-04-01-pixel-density-advanced-sweep-results.md`
- **Pixel density V3 error analysis:** `docs/research/2026-04-01-pd-v3-error-analysis.md`
- **Pixel density README:** `eval/pixel_density/README.md`
- **Eval README:** `eval/README.md`
- **Core README:** `core/README.md`
- **Memory:** `C:\Users\Daniel\.claude\projects\a--PROJECTS-PDFoverseer\memory\`

## Documentation Access (AgentSearch)

When you need current documentation for any library used in this project, use `npx nia-docs` to query it directly:

```bash
# Browse structure
npx nia-docs <docs-url> -c "tree -L 1"

# Read a page
npx nia-docs <docs-url> -c "cat <page>.md"

# Search across docs
npx nia-docs <docs-url> -c "grep -rl '<term>' ."
```

Commonly used documentation URLs:
- PyMuPDF: https://pymupdf.readthedocs.io
- FastAPI: https://fastapi.tiangolo.com
- Tesseract: https://tesseract-ocr.github.io/tessdoc/
- React: https://react.dev
- Vite: https://vite.dev/guide/
- ChromaDB: https://docs.trychroma.com

Use this BEFORE implementing anything that depends on external API behavior, especially if your training data may be outdated.

## Pending Work

- **INS_31:** ~~Last-page inference gap~~ FIXED (2026-03-26): ph5b_ratio_min 0.95→0.90, now 31/31 docs. Tray UX improvements still pending.
- **VLM integration:** ~~Attempted~~ REVERTED (2026-03-30): VLM pre-inference tier removed, s2t-helena baseline restored. See `docs/superpowers/reports/2026-03-29-vlm-integration-postmortem.md`.
- **Browse UX:** `/api/browse` opens a server-side tkinter chooser (Archivos/Carpeta) — works only when server is on local machine with a display
