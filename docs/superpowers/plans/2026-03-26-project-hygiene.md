# Project Hygiene Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the project up to standard on documentation, tooling config, and internal bookkeeping — without touching any logic or breaking anything.

**Architecture:** Four independent areas, each self-contained and zero-risk to production code. Execute in any order. No logic changes, no refactors — pure documentation and config.

**Tech Stack:** Python 3.10+, ruff (linting), Markdown (READMEs), CLAUDE.md (project memory)

---

## Scope

| Area | Risk | Time |
|------|------|------|
| A. CLAUDE.md + Memory hygiene | Zero | ~15 min |
| B. Module READMEs (api, eval, vlm, tools) | Zero | ~30 min |
| C. Docstrings for entry points | Minimal | ~15 min |
| D. Linting config (ruff, config only) | Zero | ~10 min |

**Explicitly excluded:**
- mypy/pyright — codebase has partial annotations and `callable` (lowercase). Setup would require annotating hundreds of functions. Not worth it now.
- pre-commit hooks — overkill for solo project.
- conftest.py — tests work as-is; minimal duplication.
- Auto-fixing linting violations — ruff config is added, but fixing violations is a separate decision.
- Deleting stale branches — `feature/core-modularization` and `feature/inference-engine` are fully merged (0 unique commits). Confirm with user before deleting.

---

## Area A: CLAUDE.md + Memory hygiene

**Files:**
- Modify: `CLAUDE.md` (Worktrees section + Project Structure)
- Modify: `C:\Users\Daniel\.claude\projects\a--PROJECTS-PDFoverseer\memory\project_pixel_density.md`
- Modify: `C:\Users\Daniel\.claude\projects\a--PROJECTS-PDFoverseer\memory\MEMORY.md`
- Create: `C:\Users\Daniel\.claude\projects\a--PROJECTS-PDFoverseer\memory\project_stale_branches.md`

### Task A1: Fix CLAUDE.md — Worktrees section

Current state: only mentions `.worktrees/pixel-density`. Reality: 3 active worktrees.

- [ ] **Step 1: Update Worktrees section in CLAUDE.md**

Replace the current worktrees section (around line 200):

```markdown
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
```

- [ ] **Step 2: Update Project Structure in CLAUDE.md**

Add `regex_pattern_test.py` to the `tools/` section:

```
├── tools/                    # Standalone analysis utilities
│   ├── capture_all.py        # Capture all OCR page images
│   ├── capture_failures.py   # Capture OCR failure images
│   ├── preprocess_sweep.py   # Preprocessing parameter sweep
│   └── regex_pattern_test.py # Compare regex strategies on real OCR text (ART_670)
```

- [ ] **Step 3: Verify the rest of CLAUDE.md is consistent with current state**

Check: inference engine version, PH5B_RATIO_MIN=0.90, TESS_CONFIG=--psm 6. These are already correct per recent commits.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): fix worktrees section — 3 active, 2 stale merged branches"
```

### Task A2: Fix stale memory entry — pixel-density

Current memory says "research concluded" but the branch has 5+ unmerged commits.

- [ ] **Step 1: Update `project_pixel_density.md`**

Update body to reflect that research is complete but branch is NOT merged:

```
pixel-density branch has 5+ commits not in master. Research concluded (mathematical analysis + hybrid delta clustering written). Pending decision: merge, close, or shelve.
Why: research showed pixel density clustering is viable but results weren't conclusive enough to integrate immediately.
How to apply: don't assume pixel-density work is lost or merged — it's in the worktree.
```

- [ ] **Step 2: Create `project_stale_branches.md`**

```markdown
---
name: project_stale_branches
description: Branches that are fully merged into master and safe to delete
type: project
---

feature/core-modularization and feature/inference-engine have 0 unique commits vs master — both are fully absorbed. Safe to delete locally and remotely after user confirmation.

**Why:** These were feature branches that completed their work and got merged. They remain as leftover pointers.

**How to apply:** Don't create worktrees from these or base new work on them. Suggest deletion when the user is doing branch cleanup.
```

- [ ] **Step 3: Update MEMORY.md index**

Add line:
```
- [project_stale_branches.md](project_stale_branches.md) — feature/core-modularization and feature/inference-engine: merged, safe to delete
```

---

## Area B: Module READMEs

**Files to create:**
- `api/README.md`
- `eval/README.md`
- `vlm/README.md`
- `tools/README.md`

These must describe what each module does, what each file is responsible for, and how to use it. They must NOT invent behaviors — only document what is already in the code.

### Task B1: api/README.md

- [ ] **Step 1: Write api/README.md**

```markdown
# api/

Backend layer: session state, WebSocket, database I/O, background worker, and HTTP routes.

## Modules

### state.py
`SessionState` + `SessionManager`. One `SessionState` per client session — holds scan progress,
document counts, issue list, OCR metrics, pause/cancel events. `SessionManager` manages the
session map with TTL-based eviction (`SESSION_TTL` env var, default 3600s). `get_session()`
is a FastAPI dependency that validates UUID4 format before returning the session.

### database.py
SQLite read/write for the `page_reads` table. Functions: `save_reads()`, `has_reads()`,
`get_reads()`, `clear_session()`. Database path: `data/sessions.db`.

### websocket.py
WebSocket connection manager + `_emit()` helper. `_emit()` is the single point of contact
for pushing real-time events to the frontend. All log messages, progress updates, and issue
notifications go through `_emit()`.

### worker.py
Background scan thread. `run_scan()` iterates the session's `pdf_list`, calls `analyze_pdf()`
per file, and uses callbacks to feed results back via `_emit()`. `_recalculate_metrics()`
rebuilds aggregate counts from raw `page_reads` after corrections.

## routes/

### routes/pipeline.py
`/api/start`, `/api/stop`, `/api/state` — scan lifecycle control.

### routes/files.py
`/api/browse`, `/api/add_folder`, `/api/add_files`, `/api/preview` — file discovery and
PDF preview. All paths validated against `PDF_ROOT` env var to prevent directory traversal.

### routes/sessions.py
`/api/sessions`, `/api/reset`, `/api/correct`, `/api/exclude`, `/api/restore` — session
management and manual correction of document boundaries.
```

- [ ] **Step 2: Commit**

```bash
git add api/README.md
git commit -m "docs(api): add module README"
```

### Task B2: eval/README.md

- [ ] **Step 1: Write eval/README.md**

```markdown
# eval/

Parameter sweep harness and evaluation infrastructure. Used to tune `core/inference.py`
parameters against 40 fixtures before porting changes to production.

## Workflow

```
extract_fixtures.py  →  sweep.py  →  report.py
```

1. **extract_fixtures.py** — one-time setup: extracts page-read fixtures from real PDFs
2. **sweep.py** — three-pass search: Latin Hypercube Sampling → fine grid → beam search
3. **report.py** — prints ranked results table from `eval/results/`

## Core Files

| File | Purpose |
|------|---------|
| `inference.py` | Parameterized copy of `core/inference.py` — self-contained for sweep isolation |
| `params.py` | `PARAM_SPACE` (search ranges) + `PRODUCTION_PARAMS` (current sweep2 winners) |
| `ground_truth.json` | Expected document counts per fixture |
| `sweep.py` | LHS sample → fine grid → beam search |
| `report.py` | Ranked results from eval/results/ |
| `extract_fixtures.py` | One-time fixture extraction from real PDFs |
| `ocr_benchmark.py` | OCR accuracy benchmark across tiers |
| `ocr_sweep.py` | OCR preprocessing parameter sweep |
| `compare_engines.py` | Compare inference engines head-to-head |

## Experimental (not production)

| File | Purpose |
|------|---------|
| `graph_inference.py` | Graph-based inference engine (HMM variant) |
| `graph_sweep.py` | Sweep for graph engine |
| `hybrid_inference.py` | Phases 0-6 + Viterbi global decoder — experimental |

## Fixtures

```
fixtures/
├── real/       # 21 real CRS PDFs — primary benchmark corpus
├── synthetic/  # 13 synthetic edge cases
├── degraded/   # 7 degraded copies (~15-20% OCR failure rate)
└── archived/   # Superseded fixtures
```

## Important

`eval/inference.py` is intentionally a separate copy from `core/inference.py`.
Changes to the inference algorithm must be tested in `eval/inference.py` first,
then ported to `core/inference.py` after sweep validation.
```

- [ ] **Step 2: Commit**

```bash
git add eval/README.md
git commit -m "docs(eval): add module README"
```

### Task B3: vlm/README.md

- [ ] **Step 1: Write vlm/README.md**

```markdown
# vlm/

Vision-Language Model evaluation module. Benchmarks VLM accuracy on OCR-failed pages
and sweeps preprocessing parameters.

**Status:** Benchmark infrastructure complete. VLM resolver (post-inference selective
re-inference using VLM reads) is designed but not yet implemented.
See: `docs/superpowers/specs/2026-03-25-vlm-resolver-design.md`

## Usage

```bash
# Run interactive benchmark
python -m vlm

# Run full benchmark
python vlm/benchmark.py

# Run parameter sweep
python vlm/sweep.py
```

## Modules

| File | Purpose |
|------|---------|
| `client.py` | VLM API client — sends page image, receives text response |
| `parser.py` | Parse VLM response into (curr, total) tuple |
| `preprocess.py` | Image preprocessing before sending to VLM |
| `benchmark.py` | Run VLM on fixture pages, record hit/miss/none |
| `ground_truth.py` | Load and manage ground truth for VLM pages |
| `sweep.py` | Sweep preprocessing parameters for VLM |
| `params.py` | VLM sweep parameter space |
| `report.py` | Print benchmark results summary |
| `results/` | Output directory (gitignored) |

## Background

VLM achieves 79-89% accuracy on OCR-failed pages. Naive filling of all VLM reads
into inference worsens overall accuracy by ~7pp because low-confidence VLM reads
introduce noise. The VLM resolver (pending) is designed to fix this via selective,
context-validated replacement.
```

- [ ] **Step 2: Commit**

```bash
git add vlm/README.md
git commit -m "docs(vlm): add module README"
```

### Task B4: tools/README.md

- [ ] **Step 1: Write tools/README.md**

```markdown
# tools/

Standalone analysis utilities. These are run manually for data capture and debugging —
not part of the API or pipeline.

## Scripts

### capture_all.py
Renders and saves OCR page images for every page in every fixture PDF.
Output: `data/ocr_all/<fixture>/page_NNN.png`

### capture_failures.py
Renders and saves image strips specifically from pages where OCR failed (method=failed).
Output: `data/ocr_failures/<fixture>/`
Used to visually analyze failure patterns.

### preprocess_sweep.py
Sweeps preprocessing parameters (DPI, crop, thresholding) on a set of pages
to find the best settings for OCR accuracy.
Output: `data/preprocess_sweep/`

### regex_pattern_test.py
Compares 4 regex strategies for "Página N de M" detection using real OCR text
from `data/ocr_all/all_index.csv` (no re-OCR needed):
- `CONTROL` — current production pattern (P-prefix anchor)
- `NO_ANCHOR` — pure N de M without prefix
- `SOFT` — P-word anywhere on same line
- `WORD` — any word before N de M

Run against ART_670 to measure Tier 1 success/failure rates and disagreements.
```

- [ ] **Step 2: Commit**

```bash
git add tools/README.md
git commit -m "docs(tools): add module README"
```

---

## Area C: Docstrings for entry points

**Files:**
- Modify: `core/pipeline.py` lines 163 and 333

These two functions are the public API of the core module. No logic changes — docstrings only.

### Task C1: Docstring for `analyze_pdf`

- [ ] **Step 1: Add docstring to `analyze_pdf`**

Insert after line 171 (`-> tuple[list[Document], list[_PageRead]]:`):

```python
    """Run the V4 OCR + inference pipeline on a PDF file.

    Spawns PARALLEL_WORKERS processes via ProcessPoolExecutor, each running
    Tesseract Tier 1 (direct) + Tier 2 (4x SR bicubic) on a page crop.
    Pages are processed in batches of BATCH_SIZE with pause/cancel support.

    After OCR, runs period detection (autocorrelation) and Dempster-Shafer
    inference to recover failed pages, then builds Document boundaries.

    Args:
        pdf_path:     Absolute path to the PDF file.
        on_progress:  Callback(pdf_page, total_pages) — called after each page.
        on_log:       Callback(message, level) — receives all log lines.
        pause_event:  If set, workers wait at batch boundaries. Default: None.
        cancel_event: If set and is_set(), scan aborts immediately. Default: None.
        on_issue:     Callback(page, kind, detail, extra) for low-confidence
                      inferences and other issues. Default: None.
        doc_mode:     Document mode string (currently unused, reserved). Default: "charla".

    Returns:
        Tuple of (documents, reads):
        - documents: List[Document] — inferred document boundaries.
        - reads: List[_PageRead] — one entry per page with OCR result and method.
        Returns ([], []) on PDF read error or cancel.
    """
```

- [ ] **Step 2: Verify the file still imports and parses cleanly**

```bash
python -c "from core.pipeline import analyze_pdf; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add core/pipeline.py
git commit -m "docs(pipeline): add docstring to analyze_pdf"
```

### Task C2: Docstring for `re_infer_documents`

- [ ] **Step 1: Add docstring to `re_infer_documents`**

Insert after line 339 (`-> tuple[list[Document], list[_PageRead]]:`):

```python
    """Re-run document inference applying manual corrections and exclusions.

    Used after the user corrects document boundaries in the UI. Mutates
    the provided reads in-place: corrections override (curr, total) with
    confidence=1.0; exclusions set method="excluded" and clear curr/total.

    Args:
        reads:       List[_PageRead] from a previous analyze_pdf() call.
        corrections: Dict mapping pdf_page → (curr, total) manual override.
        on_log:      Callback(message, level) — receives all log lines.
        on_issue:    Callback(page, kind, detail, extra) for new low-confidence
                     inferences post-correction. Default: None.
        exclusions:  List of pdf_page numbers to exclude from inference. Default: [].

    Returns:
        Tuple of (documents, reads):
        - documents: Re-inferred List[Document] after applying corrections.
        - reads: The same list, mutated in-place with corrections applied.
    """
```

- [ ] **Step 2: Verify**

```bash
python -c "from core.pipeline import re_infer_documents; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add core/pipeline.py
git commit -m "docs(pipeline): add docstring to re_infer_documents"
```

### Task C3: Module docstring for server.py

- [ ] **Step 1: Add module docstring at top of server.py**

Insert before the first import:

```python
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
```

- [ ] **Step 2: Verify server imports cleanly**

```bash
python -c "import server; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add server.py
git commit -m "docs(server): add module docstring"
```

---

## Area D: Linting config

**Files:**
- Create: `pyproject.toml`

Config-only. No auto-fixes applied in this plan — ruff runs to surface issues, human decides what to fix.

### Task D1: Add pyproject.toml with ruff config

- [ ] **Step 1: Create pyproject.toml**

```toml
[tool.ruff]
target-version = "py310"
line-length = 100

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "F",   # pyflakes (undefined names, unused imports)
    "W",   # pycodestyle warnings
    "I",   # isort
    "UP",  # pyupgrade
]
ignore = [
    "E501",  # line too long — handled by formatter if needed
    "E741",  # ambiguous variable names (l, O, I) — used intentionally in OCR code
    "UP007", # Use X | Y instead of Optional[X] — codebase uses both styles
]
exclude = [
    ".venv-cuda",
    "archived",
    "old_*.py",
    "eval/results",
    "vlm/results",
    "data",
    "models",
    "frontend",
]

[tool.ruff.lint.per-file-ignores]
"eval/*" = ["F401"]   # eval scripts have intentional star-imports for sweep params
"tests/*" = ["F401"]  # test files may import fixtures without direct use
```

- [ ] **Step 2: Install ruff if not present**

```bash
pip install ruff
```

- [ ] **Step 3: Run ruff check — report only, do NOT auto-fix**

```bash
ruff check . --statistics 2>&1 | head -40
```

Review the output. If violations are > 50, create a follow-up task to address them in batches by category. Do NOT run `ruff check --fix` in this task.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add ruff linting config (report-only, no auto-fix)"
```

---

## Execution order recommendation

1. **A first** — zero risk, fixes project memory immediately
2. **D second** — establishes the linter before writing new docs (so they're clean)
3. **B + C in parallel** — independent, no order dependency between them

## What's next after this plan

- Decide fate of `feature/pixel-density` (unmerged research — merge, close, or shelve?)
- Delete stale branches: `feature/core-modularization`, `feature/inference-engine`
- Review ruff violation report from Task D1 and decide what to fix
- VLM resolver implementation (separate plan: `docs/superpowers/specs/2026-03-25-vlm-resolver-design.md`)
