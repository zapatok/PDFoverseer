# Plan: ART_674 Tesseract Fixture Extraction + Sweep Analysis

**Branch:** `cuda-gpu`
**Scope:** Extract a real Tesseract fixture for ART_674, verify it reproduces the AI log delta, then decide on sweep re-run.
**Constraints:**
- DO NOT overwrite `eval/fixtures/real/ART_674.json` (VLM fixture — permanent reference)
- DO NOT touch `core/` at all
- DO NOT run sweep without explicit user authorization after seeing Task 3 results
- DO NOT modify `eval/extract_fixtures.py` (it is stale but not our problem to fix here)

---

## Why This Matters

The VLM fixture (`ART_674.json`, 2,686 reads, method=vlm_opus) scores **perfectly** against ground truth (delta=0 on all metrics). This means it provides **zero discriminating signal** for parameter optimization.

The production AI log (`logINS_31_fix.txt`, Tesseract scan of ART_670.pdf) shows:
- **DOC: 668** vs GT **674** → delta **−6 docs**
- **INF: 603 pages** inferred (only 35 expected per GT)

A Tesseract fixture (`ART_674_tess.json`) would:
1. Reproduce that real OCR failure pattern (~22% of 2,719 pages failing)
2. Stress-test the gap solver at 9× the scale of any current fixture
3. Provide genuine sweep signal — params that fail here are definitely wrong
4. Expose whether current params are overfitting to small, clean fixtures

**Fixture naming convention:**
- `ART_674.json` → VLM reads (do not touch, perfect score reference)
- `ART_674_tess.json` → Tesseract reads (to be created here)
- Follows the `_degraded` / `_tess` suffix pattern

---

## Context: EasyOCR Status

`eval/extract_fixtures.py` is **stale** — it imports `EASYOCR_DPI`, `_init_easyocr`, `_easyocr_reader` from `core.ocr`, which were removed 2026-03-26. **Do not use or modify it.**

Current `core/ocr.py` exports:
- `_setup_sr(on_log)` — initializes SR model
- `_process_page(doc, page_idx)` — Tesseract Tier 1 + SR Tier 2 for one page
- (No EasyOCR, no GPU consumer thread)

---

## Prerequisites

```
data/samples/ART_670.pdf   # 2,719-page source PDF — already confirmed present
.venv-cuda/Scripts/activate  # GPU venv with PyTorch CUDA
```

---

## Task 1: Create `eval/extract_art674_tess.py`

**Goal:** Standalone extraction script, Tesseract-only, saves to `ART_674_tess.json`.

**What to write:**

```python
#!/usr/bin/env python
"""
eval/extract_art674_tess.py
---------------------------
Extract Tesseract reads from data/samples/ART_670.pdf.
Saves raw OCR reads (NO inference) to eval/fixtures/real/ART_674_tess.json.

Does NOT overwrite ART_674.json (VLM fixture).

Usage:
    source .venv-cuda/Scripts/activate   # Windows: .\.venv-cuda\Scripts\activate
    python eval/extract_art674_tess.py
"""
from __future__ import annotations

import json
import queue
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import fitz  # noqa: E402

from core.ocr import _process_page, _setup_sr  # noqa: E402
from core.utils import BATCH_SIZE, PARALLEL_WORKERS, _PageRead  # noqa: E402

PDF_PATH = PROJECT_ROOT / "data" / "samples" / "ART_670.pdf"
OUT_PATH = PROJECT_ROOT / "eval" / "fixtures" / "real" / "ART_674_tess.json"
FIXTURE_NAME = "ART_674_tess"


def _log(msg: str) -> None:
    print(msg.encode("ascii", errors="replace").decode("ascii"), flush=True)


def main() -> None:
    if not PDF_PATH.exists():
        _log(f"ERROR: PDF not found at {PDF_PATH}")
        sys.exit(1)
    if OUT_PATH.exists():
        _log(f"WARNING: {OUT_PATH.name} already exists — will overwrite")

    _log("Initializing SR model...")
    _setup_sr(_log)

    meta = fitz.open(str(PDF_PATH))
    total_pages = len(meta)
    meta.close()
    _log(f"PDF: {PDF_PATH.name}, {total_pages} pages")

    reads: list[_PageRead | None] = [None] * total_pages

    doc_pool: queue.Queue[fitz.Document] = queue.Queue()
    for _ in range(PARALLEL_WORKERS):
        doc_pool.put(fitz.open(str(PDF_PATH)))

    def _submit(page_idx: int) -> _PageRead:
        doc = doc_pool.get()
        try:
            return _process_page(doc, page_idx)
        except Exception as e:
            _log(f"  p{page_idx+1}: error — {e}")
            return _PageRead(page_idx + 1, None, None, "failed", 0.0)
        finally:
            doc_pool.put(doc)

    _log(f"Scanning {total_pages} pages with {PARALLEL_WORKERS} workers...")
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as pool:
        for batch_start in range(0, total_pages, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, total_pages)
            futures = {pool.submit(_submit, i): i for i in range(batch_start, batch_end)}
            for fut, i in futures.items():
                reads[i] = fut.result()
            # Progress every 10 batches
            if (batch_start // BATCH_SIZE) % 10 == 0:
                done = batch_end
                failed = sum(1 for r in reads[:done] if r is not None and r.method == "failed")
                _log(f"  [{done}/{total_pages}] {failed} failed so far")

    while not doc_pool.empty():
        doc_pool.get_nowait().close()

    # Fill any None slots (defensive)
    for i in range(total_pages):
        if reads[i] is None:
            reads[i] = _PageRead(i + 1, None, None, "failed", 0.0)

    failed_total = sum(1 for r in reads if r.method == "failed")  # type: ignore[union-attr]
    direct_total = sum(1 for r in reads if r.method == "direct")  # type: ignore[union-attr]
    sr_total = sum(1 for r in reads if r.method == "super_resolution")  # type: ignore[union-attr]
    _log(f"\nResults: {total_pages} pages | direct={direct_total} SR={sr_total} failed={failed_total}")

    fixture = {
        "name":   FIXTURE_NAME,
        "source": "real",
        "reads": [
            {
                "pdf_page":   r.pdf_page,
                "curr":       r.curr,
                "total":      r.total,
                "method":     r.method,
                "confidence": r.confidence,
            }
            for r in reads  # type: ignore[union-attr]
        ],
    }
    OUT_PATH.write_text(json.dumps(fixture, indent=2))
    _log(f"Saved -> {OUT_PATH}")


if __name__ == "__main__":
    main()
```

**Verification before writing:**
- Confirm `OUT_PATH` is `ART_674_tess.json`, not `ART_674.json`
- Confirm no EasyOCR imports
- Confirm no `shell=True` (hookify blocker)
- Confirm no bare `except:` (hookify blocker)

**After writing:** Run `ruff check eval/extract_art674_tess.py` — must be 0 violations.

---

## Task 2: Run Extraction

**Command (PowerShell, project root):**
```powershell
.\.venv-cuda\Scripts\activate
python eval/extract_art674_tess.py
```

**Expected output:**
```
Initializing SR model...
PDF: ART_670.pdf, 2719 pages
Scanning 2719 pages with 6 workers...
  [12/2719] N failed so far
  ...
  [2719/2719] ~600 failed so far
Results: 2719 pages | direct=??? SR=??? failed=~600
Saved -> eval/fixtures/real/ART_674_tess.json
```

**Expected timing:** ~5-10 minutes (6 workers × 2,719 pages × ~150ms/page Tesseract).

**Sanity checks after run:**
1. `ART_674.json` still has 2,686 reads (VLM, unchanged)
2. `ART_674_tess.json` has 2,719 reads (one per page, including failures)
3. `failed` count ≈ 600 (matches AI log's 603 inferred pages)
4. No reads with method=`easyocr` (that tier is gone)

---

## Task 3: Run Baseline Eval with Tesseract Reads

**Goal:** Confirm the Tesseract fixture reproduces the AI log delta (−6 docs, 603 inferred pages).

**Write `eval/baseline_art674_tess.py`** — clone of `eval/baseline_art674.py` with:
- `FIXTURE_PATH = Path("eval/fixtures/real/ART_674_tess.json")`
- Keep same GT, same AI_LOG reference, same region analysis

**Run:**
```powershell
python eval/baseline_art674_tess.py
```

**Verification criteria:**
- `doc_count` delta within ±2 of AI log delta (−6 ± 2 = range −4 to −8)
- `inferred_count` ≈ 603 (very close — same Tesseract failure pattern)
- If delta is way off (e.g., 0 or −20): investigate before proceeding

**If delta matches:** proceed to Task 4.
**If delta doesn't match:** stop and report findings to user.

---

## Task 4: Sweep Decision

**Goal:** Recommend whether to add `ART_674_tess` to the sweep fixture set and re-run.

**Decision logic:**

| Scenario | Recommendation |
|----------|----------------|
| Delta matches AI log (−6 ± 2) | Add to sweep. Fixture is valid. |
| Delta is 0 (too clean) | Tesseract somehow got clean reads — debug before sweep |
| Delta is < −10 (too bad) | Fixture may have scan artifacts — inspect failed pages first |

**If sweep is recommended:**
- Do NOT run immediately — present proposed param grid to user
- Proposed grid: `min_conf_for_new_doc` × `clash_boundary_pen` × `min_boundary_gap` (3 params, ~200 combos)
- Risk: ART_674_tess is 9× larger than any current fixture → sweep will take much longer
- Mitigation: run ART_674_tess-only sweep first, then compare winners against existing fixtures

**STOP after Task 4 and wait for user authorization before running sweep.**

---

## Commits

After Task 1 (script created, ruff clean):
```
feat(eval): add ART_674 Tesseract fixture extractor (eval/extract_art674_tess.py)
```

After Task 2 (fixture JSON saved):
```
feat(eval): add ART_674_tess fixture (2719 reads, Tesseract Tier 1+2)
```

After Task 3 (baseline script + results):
```
feat(eval): add ART_674 Tesseract baseline runner + delta verification
```

---

## Files Changed

| File | Action | Rule |
|------|--------|------|
| `eval/extract_art674_tess.py` | CREATE | Task 1 |
| `eval/fixtures/real/ART_674_tess.json` | CREATE | Task 2 |
| `eval/baseline_art674_tess.py` | CREATE | Task 3 |
| `eval/fixtures/real/ART_674.json` | **DO NOT TOUCH** | VLM fixture |
| `core/` (any file) | **DO NOT TOUCH** | hookify block |
| `eval/extract_fixtures.py` | **DO NOT TOUCH** | stale, not our scope |

---

## Session Prompt (for resuming this plan)

> "Continúa el plan en `docs/superpowers/plans/2026-03-27-art674-tess-fixture.md`.
> El PDF fuente está en `data/samples/ART_670.pdf` (2,719 páginas).
> El fixture VLM existente está en `eval/fixtures/real/ART_674.json` — NO lo toques.
> El fixture Tesseract debe guardarse en `eval/fixtures/real/ART_674_tess.json`.
> `eval/extract_fixtures.py` está stale (EasyOCR removido) — no lo uses ni modifiques.
> Ejecuta paso a paso y muéstrame resultados antes de continuar. NO toques `core/`."
