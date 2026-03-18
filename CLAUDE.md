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

## Tech Stack

- **Backend:** Python 3.10+ with CUDA GPU, FastAPI, PyMuPDF, Tesseract, EasyOCR
- **Frontend:** React + Vite, react-zoom-pan-pinch
- **OCR Pipeline:** V4 (producer-consumer) with GPU acceleration
- **Inference:** 5-phase engine with Dempster-Shafer post-validation

## Project Structure

```
├── core/
│   ├── analyzer.py           # V4 Pipeline: Tesseract + SR + EasyOCR GPU
│   └── __init__.py
├── eval/                     # Evaluation harness (parameter sweep)
│   ├── inference.py          # Parameterized copy of 5-phase pipeline
│   ├── sweep.py              # LHS sample → fine grid → beam search
│   ├── report.py             # Ranked results table
│   ├── extract_fixtures.py   # One-time fixture extraction
│   ├── fixtures/
│   │   ├── real/             # 7 real PDFs (charlas CRS)
│   │   └── synthetic/        # 6 synthetic test cases
│   └── results/              # Sweep results (ignored)
├── frontend/                 # React UI
│   ├── src/
│   ├── package.json
│   └── vite.config.js
├── models/                   # FSRCNN_x4.pb (super-resolution)
├── data/
│   └── sessions/             # Session history (ignored)
├── server.py                 # FastAPI backend
├── app.py                    # GUI entry point
├── history.py                # Session logging
└── requirements.txt          # Python dependencies
```

## Architecture

### V4 Pipeline (core/analyzer.py)

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
```

### Page Number Pattern

```regex
P.{0,2}[gq](?:ina?)?\.?\s*(\d{1,3})\s*\.?\s*de\s*(\d{1,3})
```
Matches: "Página 1 de 10", "Pag 1 de 10", "page 1 of 10", etc. (Spanish-centric)

## Development

### Restart Procedure ("reinicia todo")

When testing the app locally:
1. Kill processes: `powershell -Command "Get-Process | Where-Object { (\$_.ProcessName -eq 'python' -or \$_.ProcessName -eq 'node') } | Stop-Process -Force"`
2. Verify ports free: `netstat -ano | grep -E ':(8000|5173)'`
3. Start backend (background): `source .venv-cuda/Scripts/activate && python server.py`
4. Start frontend (background): `cd frontend && npm run dev`
5. Access: http://localhost:5173 (React UI) · http://localhost:8000/ui/ (API/Swagger docs)

### Testing Baseline (real PDFs)

All 7 must pass before merging inference changes (`eval/fixtures/real/`):

| File | Pages | Notes |
|------|-------|-------|
| CH_9docs.pdf | 17 | Minimal, fast smoke test |
| CH_39docs.pdf | 78 | Medium, catches inference bugs |
| CH_51docs.pdf | 102 | OCR challenges |
| CH_74docs.pdf | 150 | Large stress test |
| INS_31docs.pdf | 31 | Triggers Phase 5b (period detection) |
| HLL_363docs.pdf | 538 | Large, multi-document |
| ART_HLL_674docsapp.pdf | 2719 | Stress test, Phase 5 merge boundary issues |

### Safe Revert Checkpoint

Tag `6ph-t2-almost-there` = known-stable state. Revert specific files without changing branch:
```bash
git checkout 6ph-t2-almost-there -- server.py core/analyzer.py
```

### OCR Digit Normalization

`_OCR_DIGIT` (core/analyzer.py:90) maps Tesseract-confused chars (O→0, I/i→1, l→1, etc.).
Keep in sync with regex flags — if `re.IGNORECASE` is used, both upper and lowercase must be mapped.

### Debugging

Use `superpowers:systematic-debugging` skill before attempting fixes. Partial fixes compound problems — find root cause first, then fix one thing at a time.

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

### Key Commands

| Command | Purpose |
|---------|---------|
| `python server.py` | Start FastAPI backend + WebSocket |
| `cd frontend && npm run dev` | Start React dev server |
| `python app.py` | Legacy GUI (Tkinter) |
| `pytest` | Run test suite |

## Important Notes

### OCR Assumptions & Noise Mitigation Rules

- **Spanish-centric regex** for "Página N de M". The current regex intentionally allows confusing typos (e.g., lowercase l instead of 1, O instead of 0) and spacing issues to give Tesseract the maximum leeway. These are remapped via `_OCR_DIGIT`.
- **Image preprocessing cascade (CRITICAL):**
  1. **Color Ink Masking:** We convert the original BGR image to HSV to isolate specific ink matices (Blue Hue `90-150`).
  2. **Inpainting:** We apply `cv2.inpaint(img, mask, 3, cv2.INPAINT_NS)` to remove the blue ink and *rebuild* the black text boundaries underneath the signature. **DO NOT** use naive saturation clipping or `v_channel[mask]=255` as it erodes the black text characters intersecting the ink, making them unreadable to Tesseract.
  3. **Otsu Threshold:** Finally, this cleaned BGR image is grayscaled and binarized using `cv2.THRESH_OTSU`.
- **Alucination Handling on Blank Pages:** Tesseract's Super Resolution (Tier 2) naturally generates noise/garbage characters when fed an empty page. This is *expected and handled*. Rather than implementing fragile "blank image detection" logic, we rely on the strict Regex and Dempster-Shafer engine to discard these hallucinated artifacts.
- **Tesseract config:** `--psm 6 --oem 1` (uniform block text)

- EasyOCR runs on GPU thread while Tesseract continues (concurrent)
- Fallback only triggered if Tesseract tiers fail
- GPU memory managed via single-threaded consumer

### Inference Engine

- **Phase 1–5:** OCR results → period detection → evidence fusion
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
- **Active branch:** `feature/inference-engine`
- **Eval spec:** `docs/superpowers/specs/2026-03-15-eval-harness-design.md`
- **Eval plan:** `docs/superpowers/plans/2026-03-15-eval-harness.md`
- **Memory:** `C:\Users\Daniel\.claude\projects\a--PROJECTS-PDFoverseer\memory\`

## Pending Work

- **INS_31:** Last-page inference gap + tray UX improvements to reduce human intervention
- **Eval harness:** Complete parameter sweep implementation and tuning report
