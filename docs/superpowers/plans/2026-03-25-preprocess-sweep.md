# OCR Preprocessing Sweep — Isolated Testing Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone test harness that extracts the 193 failed image strips from ART_670, applies N preprocessing variants to each, runs Tesseract on all of them, and produces a ranked report of which variants recover the most pages — WITHOUT touching the production pipeline.

**Architecture:** A new `tools/preprocess_sweep.py` script that:
1. Extracts failure strips from ART_670 (reuses `capture_all.py` output or renders directly)
2. Applies a matrix of preprocessing variants to each strip
3. Runs `_parse(pytesseract.image_to_string(...))` on each variant
4. Compares against GT from `eval/fixtures/real/ART_670.json`
5. Outputs a ranked CSV + summary to `data/preprocess_sweep/`

**Tech Stack:** Python 3.10+, OpenCV, pytesseract, numpy, core.utils._parse, core.image._render_clip/_deskew

**Scope boundary:** This is a research tool ONLY. No changes to `core/ocr.py`, `core/image.py`, or `core/pipeline.py`. All code lives in `tools/preprocess_sweep.py` + `tests/test_preprocess_sweep.py`.

---

## Task 0: Prepare failure strips dataset

**Files:**
- Uses: `tools/capture_all.py` (existing)
- Output: `data/ocr_all/ART_670/p*.png` + `data/ocr_all/all_index.csv`

- [ ] **Step 1: Run capture_all on ART_670**

```bash
python tools/capture_all.py <path-to-ART_670.pdf> --out data/ocr_all
```

This produces 796 PNG strips + CSV index. The ~193 FAIL rows in the CSV are our test set.

- [ ] **Step 2: Verify output and count failures**

```bash
grep -c "^ART_670" data/ocr_all/all_index.csv  # should be ~796
# Count rows where tier1_parsed and tier2_parsed are both empty = FAIL
```

---

## Task 1: Preprocessing variant matrix

**Files:**
- Create: `tools/preprocess_sweep.py`
- Test: `tests/test_preprocess_sweep.py`

The sweep should test these preprocessing dimensions (all combinations):

### Dimension A: Binarization method (before Tesseract)
| ID | Method | Notes |
|----|--------|-------|
| `none` | No binarization (current: grayscale + unsharp) | Baseline |
| `otsu` | `cv2.threshold(THRESH_BINARY + THRESH_OTSU)` | Global threshold |
| `adapt_gauss_15` | `cv2.adaptiveThreshold(ADAPTIVE_THRESH_GAUSSIAN_C, blockSize=15, C=10)` | Local contrast |
| `adapt_gauss_31` | `cv2.adaptiveThreshold(ADAPTIVE_THRESH_GAUSSIAN_C, blockSize=31, C=10)` | Larger neighborhood |
| `adapt_mean_15` | `cv2.adaptiveThreshold(ADAPTIVE_THRESH_MEAN_C, blockSize=15, C=10)` | Mean-based local |

### Dimension B: Color filtering (before grayscale conversion)
| ID | Method | Notes |
|----|--------|-------|
| `blue_only` | Current: HSV blue mask + inpaint | Baseline |
| `sat_filter` | Remove all saturated pixels (S > 50 in HSV) → white | Aggressive color removal |
| `lum_only` | Use L channel from HLS directly (ignore color) | Bypass color entirely |
| `no_filter` | No color filtering at all | Control |

### Dimension C: Contrast enhancement (before binarization)
| ID | Method | Notes |
|----|--------|-------|
| `unsharp_1_03` | Current: sigma=1.0, strength=0.3 | Baseline |
| `clahe_2` | CLAHE clipLimit=2.0, tileGridSize=8×8 | Adaptive histogram |
| `clahe_4` | CLAHE clipLimit=4.0, tileGridSize=8×8 | More aggressive |
| `none` | No contrast enhancement | Control |

### Dimension D: Morphology (after binarization, only if binarization ≠ none)
| ID | Method | Notes |
|----|--------|-------|
| `none` | No morphology | Baseline |
| `close_2` | Morphological close (3×3 kernel, 2 iters) | Connect broken chars |
| `open_1` | Morphological open (2×2 kernel, 1 iter) | Remove noise dots |

### Dimension E: DPI override
| ID | Value | Notes |
|----|-------|-------|
| `dpi_150` | 150 (current) | Baseline — use existing strips |
| `dpi_200` | 200 | Re-render from PDF |
| `dpi_300` | 300 | Higher res — may help small text |

**Total combinations:** 5 × 4 × 4 × 3 × 3 = 720 variants per page.
With 193 pages: 720 × 193 = ~139K Tesseract calls.
At ~30ms/call: ~70 minutes (parallelizable with 6 workers → ~12 min).

- [ ] **Step 3: Write failing tests for variant generators**

Create `tests/test_preprocess_sweep.py`:
```python
import numpy as np
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.preprocess_sweep import (
    build_variant_matrix,
    apply_variant,
    Variant,
)


def test_variant_matrix_count():
    """Total combinations = 5 binarize × 4 color × 4 contrast × 3 morph × 3 dpi."""
    matrix = build_variant_matrix()
    assert len(matrix) == 5 * 4 * 4 * 3 * 3  # 720


def test_variant_has_all_fields():
    matrix = build_variant_matrix()
    for v in matrix:
        assert hasattr(v, "binarize")
        assert hasattr(v, "color_filter")
        assert hasattr(v, "contrast")
        assert hasattr(v, "morphology")
        assert hasattr(v, "dpi")


def test_baseline_variant_exists():
    """The current production config must be one of the variants."""
    matrix = build_variant_matrix()
    baseline = [v for v in matrix
                if v.binarize == "none"
                and v.color_filter == "blue_only"
                and v.contrast == "unsharp_1_03"
                and v.morphology == "none"
                and v.dpi == 150]
    assert len(baseline) == 1


def test_apply_variant_returns_gray():
    """apply_variant should return a single-channel numpy array."""
    bgr = np.random.randint(0, 255, (100, 300, 3), dtype=np.uint8)
    v = Variant("none", "no_filter", "none", "none", 150)
    result = apply_variant(bgr, v)
    assert isinstance(result, np.ndarray)
    assert len(result.shape) == 2  # grayscale


def test_apply_variant_otsu_returns_binary():
    """Otsu binarization should return only 0 and 255 values."""
    bgr = np.random.randint(0, 255, (100, 300, 3), dtype=np.uint8)
    v = Variant("otsu", "no_filter", "none", "none", 150)
    result = apply_variant(bgr, v)
    unique = set(np.unique(result))
    assert unique.issubset({0, 255})
```

- [ ] **Step 4: Run tests — verify they fail**

```bash
pytest tests/test_preprocess_sweep.py -v
```
Expected: ImportError (module doesn't exist yet).

- [ ] **Step 5: Implement `tools/preprocess_sweep.py` — variant matrix + apply_variant**

```python
"""
preprocess_sweep.py — OCR Preprocessing Variant Sweep
=====================================================
Standalone research script. Tests N preprocessing variants on failed pages
and ranks which variants recover the most OCR reads.

Usage:
    python tools/preprocess_sweep.py <path-to-ART_670.pdf>
    python tools/preprocess_sweep.py <path-to-ART_670.pdf> --max-pages 20  # quick test
    python tools/preprocess_sweep.py <path-to-ART_670.pdf> --workers 8

Output: data/preprocess_sweep/sweep_results.csv + summary.txt
"""
from __future__ import annotations

import argparse
import csv
import itertools
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pytesseract

# Project imports
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from core.utils import _parse, TESS_CONFIG, DPI
from core.image import _render_clip, _deskew
from core.ocr import _setup_sr, _upsample_4x

# ── Tesseract path (match core/ocr.py) ─────────────────────────
import os
pytesseract.pytesseract.tesseract_cmd = os.getenv(
    "TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

OUTPUT_DIR = Path("data/preprocess_sweep")


@dataclass(frozen=True)
class Variant:
    binarize: str        # none | otsu | adapt_gauss_15 | adapt_gauss_31 | adapt_mean_15
    color_filter: str    # blue_only | sat_filter | lum_only | no_filter
    contrast: str        # unsharp_1_03 | clahe_2 | clahe_4 | none
    morphology: str      # none | close_2 | open_1
    dpi: int             # 150 | 200 | 300

    @property
    def tag(self) -> str:
        return f"{self.binarize}_{self.color_filter}_{self.contrast}_{self.morphology}_dpi{self.dpi}"


BINARIZE_OPTIONS   = ["none", "otsu", "adapt_gauss_15", "adapt_gauss_31", "adapt_mean_15"]
COLOR_OPTIONS      = ["blue_only", "sat_filter", "lum_only", "no_filter"]
CONTRAST_OPTIONS   = ["unsharp_1_03", "clahe_2", "clahe_4", "none"]
MORPHOLOGY_OPTIONS = ["none", "close_2", "open_1"]
DPI_OPTIONS        = [150, 200, 300]


def build_variant_matrix() -> list[Variant]:
    return [
        Variant(b, c, ct, m, d)
        for b, c, ct, m, d in itertools.product(
            BINARIZE_OPTIONS, COLOR_OPTIONS, CONTRAST_OPTIONS,
            MORPHOLOGY_OPTIONS, DPI_OPTIONS,
        )
    ]


def _apply_color_filter(bgr: np.ndarray, method: str) -> np.ndarray:
    """Apply color filtering and return grayscale."""
    if method == "blue_only":
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array([90, 50, 50]), np.array([150, 255, 255]))
        clean = cv2.inpaint(bgr, mask, 3, cv2.INPAINT_NS)
        return cv2.cvtColor(clean, cv2.COLOR_BGR2GRAY)
    elif method == "sat_filter":
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        mask = hsv[:, :, 1] > 50
        bgr_clean = bgr.copy()
        bgr_clean[mask] = 255
        return cv2.cvtColor(bgr_clean, cv2.COLOR_BGR2GRAY)
    elif method == "lum_only":
        hls = cv2.cvtColor(bgr, cv2.COLOR_BGR2HLS)
        return hls[:, :, 1]
    else:  # no_filter
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)


def _apply_contrast(gray: np.ndarray, method: str) -> np.ndarray:
    if method == "unsharp_1_03":
        blurred = cv2.GaussianBlur(gray, (0, 0), 1.0)
        return cv2.addWeighted(gray, 1.3, blurred, -0.3, 0)
    elif method == "clahe_2":
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(gray)
    elif method == "clahe_4":
        clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
        return clahe.apply(gray)
    else:  # none
        return gray


def _apply_binarize(gray: np.ndarray, method: str) -> np.ndarray:
    if method == "otsu":
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return binary
    elif method == "adapt_gauss_15":
        return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 15, 10)
    elif method == "adapt_gauss_31":
        return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 31, 10)
    elif method == "adapt_mean_15":
        return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                     cv2.THRESH_BINARY, 15, 10)
    else:  # none
        return gray


def _apply_morphology(img: np.ndarray, method: str, binarized: bool) -> np.ndarray:
    if not binarized or method == "none":
        return img
    if method == "close_2":
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        return cv2.morphologyEx(img, cv2.MORPH_CLOSE, kernel, iterations=2)
    elif method == "open_1":
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        return cv2.morphologyEx(img, cv2.MORPH_OPEN, kernel, iterations=1)
    return img


def apply_variant(bgr: np.ndarray, v: Variant) -> np.ndarray:
    """Apply a preprocessing variant to a BGR image, return grayscale/binary for OCR."""
    gray = _apply_color_filter(bgr, v.color_filter)
    gray = _apply_contrast(gray, v.contrast)
    result = _apply_binarize(gray, v.binarize)
    result = _apply_morphology(result, v.morphology, binarized=(v.binarize != "none"))
    return result
```

- [ ] **Step 6: Run tests — verify they pass**

```bash
pytest tests/test_preprocess_sweep.py -v
```
Expected: All 6 pass.

- [ ] **Step 7: Commit**

```bash
git add tools/preprocess_sweep.py tests/test_preprocess_sweep.py
git commit -m "feat(tools): preprocess sweep — variant matrix + apply_variant"
```

---

## Task 2: Ground truth loader + page scorer

**Files:**
- Modify: `tools/preprocess_sweep.py`
- Modify: `tests/test_preprocess_sweep.py`

- [ ] **Step 8: Write failing test for GT loader**

Add to `tests/test_preprocess_sweep.py`:
```python
def test_load_ground_truth_art670():
    """Load ART_670 GT and verify structure."""
    from tools.preprocess_sweep import load_ground_truth
    gt = load_ground_truth("ART_670")
    assert isinstance(gt, dict)
    # GT maps pdf_page → (curr, total)
    assert gt[1] == (1, 4)
    assert gt[4] == (4, 4)
    assert gt[5] == (1, 4)  # doc 2 starts
    assert len(gt) == 796


def test_score_variant_result():
    """Score a single variant result against GT."""
    from tools.preprocess_sweep import score_result
    # Correct parse
    assert score_result(parsed=(2, 4), gt=(2, 4)) == "correct"
    # Wrong parse
    assert score_result(parsed=(3, 4), gt=(2, 4)) == "wrong"
    # No parse (failed)
    assert score_result(parsed=(None, None), gt=(2, 4)) == "failed"
```

- [ ] **Step 9: Run tests — verify they fail**

- [ ] **Step 10: Implement GT loader + scorer**

Add to `tools/preprocess_sweep.py`:
```python
import json

FIXTURES_DIR = Path("eval/fixtures/real")


def load_ground_truth(pdf_name: str) -> dict[int, tuple[int, int]]:
    """Load GT fixture, return {pdf_page: (curr, total)}."""
    fixture_path = FIXTURES_DIR / f"{pdf_name}.json"
    with open(fixture_path) as f:
        data = json.load(f)
    return {r["pdf_page"]: (r["curr"], r["total"]) for r in data["reads"]}


def score_result(parsed: tuple, gt: tuple) -> str:
    """Score a single OCR parse against ground truth."""
    if parsed[0] is None:
        return "failed"
    if parsed == gt:
        return "correct"
    return "wrong"
```

- [ ] **Step 11: Run tests — verify they pass**

- [ ] **Step 12: Commit**

```bash
git add tools/preprocess_sweep.py tests/test_preprocess_sweep.py
git commit -m "feat(tools): preprocess sweep — GT loader + scorer"
```

---

## Task 3: Sweep runner (main loop)

**Files:**
- Modify: `tools/preprocess_sweep.py`

The runner needs to:
1. Open the PDF
2. Identify the ~193 failed pages (run baseline preprocessing, check against GT)
3. For each failed page × each variant: apply preprocessing, run Tesseract, score
4. Aggregate results per variant (recovered, wrong, still_failed)
5. Write results CSV + ranked summary

- [ ] **Step 13: Write failing test for sweep runner**

```python
def test_run_sweep_on_small_sample(tmp_path):
    """Run sweep on a fake 3-variant matrix to verify output structure."""
    from tools.preprocess_sweep import run_sweep, Variant
    # This test needs a real PDF — skip if ART_670 not available
    import pytest
    pdf_path = Path("path/to/ART_670.pdf")  # FILL IN actual path
    if not pdf_path.exists():
        pytest.skip("ART_670 PDF not available")

    # Run with very limited variants for speed
    variants = [
        Variant("none", "blue_only", "unsharp_1_03", "none", 150),  # baseline
        Variant("otsu", "blue_only", "unsharp_1_03", "none", 150),  # one change
    ]
    results = run_sweep(pdf_path, variants=variants, max_pages=5, workers=1)
    assert "variant_stats" in results
    assert "page_results" in results
    assert len(results["variant_stats"]) == 2
```

- [ ] **Step 14: Implement sweep runner**

```python
def _ocr_with_variant(bgr: np.ndarray, variant: Variant) -> tuple[int | None, int | None]:
    """Apply variant preprocessing + Tesseract, return parsed (curr, total)."""
    processed = apply_variant(bgr, variant)
    text = pytesseract.image_to_string(processed, lang="eng", config=TESS_CONFIG)
    return _parse(text.strip())


def _identify_failed_pages(
    pdf_path: Path,
    gt: dict[int, tuple[int, int]],
) -> list[int]:
    """Return list of pdf_pages where baseline preprocessing fails to parse correctly."""
    import fitz
    doc = fitz.open(str(pdf_path))
    failed = []
    baseline = Variant("none", "blue_only", "unsharp_1_03", "none", 150)
    for page_idx in range(len(doc)):
        pdf_page = page_idx + 1
        if pdf_page not in gt:
            continue
        bgr = _render_clip(doc[page_idx])
        bgr = _deskew(bgr)
        parsed = _ocr_with_variant(bgr, baseline)
        if parsed != gt[pdf_page]:
            failed.append(pdf_page)
    doc.close()
    return failed


def run_sweep(
    pdf_path: Path,
    variants: list[Variant] | None = None,
    max_pages: int = 0,
    workers: int = 6,
) -> dict:
    """
    Run the full preprocessing sweep.
    Returns dict with 'variant_stats' and 'page_results'.
    """
    import fitz

    pdf_name = Path(pdf_path).stem
    gt = load_ground_truth(pdf_name)

    if variants is None:
        variants = build_variant_matrix()

    # Find failed pages
    print(f"[sweep] Identifying failed pages...")
    failed_pages = _identify_failed_pages(pdf_path, gt)
    if max_pages > 0:
        failed_pages = failed_pages[:max_pages]
    print(f"[sweep] {len(failed_pages)} failed pages to test × {len(variants)} variants")

    # Pre-render all failed pages at each needed DPI
    dpis_needed = sorted(set(v.dpi for v in variants))
    print(f"[sweep] Pre-rendering at DPIs: {dpis_needed}")
    doc = fitz.open(str(pdf_path))
    page_images = {}  # (pdf_page, dpi) → bgr
    for pdf_page in failed_pages:
        page = doc[pdf_page - 1]
        for dpi in dpis_needed:
            bgr = _render_clip(page, dpi=dpi)
            bgr = _deskew(bgr)
            page_images[(pdf_page, dpi)] = bgr
    doc.close()
    print(f"[sweep] Pre-rendered {len(page_images)} images")

    # Run sweep (parallelized per page×variant)
    page_results = []  # list of (pdf_page, variant_tag, score, parsed, gt_val)
    variant_stats = {v.tag: {"recovered": 0, "wrong": 0, "failed": 0} for v in variants}

    total_jobs = len(failed_pages) * len(variants)
    done = 0
    t0 = time.time()

    def _eval_one(pdf_page: int, variant: Variant):
        bgr = page_images[(pdf_page, variant.dpi)]
        parsed = _ocr_with_variant(bgr, variant)
        gt_val = gt[pdf_page]
        sc = score_result(parsed, gt_val)
        return pdf_page, variant.tag, sc, parsed, gt_val

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = []
        for pdf_page in failed_pages:
            for v in variants:
                futures.append(pool.submit(_eval_one, pdf_page, v))

        for fut in as_completed(futures):
            pdf_page, vtag, sc, parsed, gt_val = fut.result()
            page_results.append((pdf_page, vtag, sc, parsed, gt_val))
            variant_stats[vtag][sc] += 1
            done += 1
            if done % 1000 == 0:
                elapsed = time.time() - t0
                rate = done / elapsed
                eta = (total_jobs - done) / rate
                print(f"  [{done}/{total_jobs}] {rate:.0f} eval/s, ETA {eta:.0f}s")

    elapsed = time.time() - t0
    print(f"[sweep] Done: {total_jobs} evals in {elapsed:.1f}s ({total_jobs/elapsed:.0f}/s)")

    return {
        "variant_stats": variant_stats,
        "page_results": page_results,
        "failed_count": len(failed_pages),
        "elapsed": elapsed,
    }
```

- [ ] **Step 15: Run tests — verify they pass**

- [ ] **Step 16: Commit**

```bash
git add tools/preprocess_sweep.py tests/test_preprocess_sweep.py
git commit -m "feat(tools): preprocess sweep — main runner with parallel evaluation"
```

---

## Task 4: Report generator + CLI

**Files:**
- Modify: `tools/preprocess_sweep.py`

- [ ] **Step 17: Implement report writer**

```python
def write_report(results: dict, out_dir: Path = OUTPUT_DIR) -> None:
    """Write sweep results to CSV + human-readable summary."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # Detailed CSV: every page × variant result
    csv_path = out_dir / "sweep_detail.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["pdf_page", "variant", "score", "parsed_curr", "parsed_total",
                     "gt_curr", "gt_total"])
        for pdf_page, vtag, sc, parsed, gt_val in results["page_results"]:
            w.writerow([pdf_page, vtag, sc,
                        parsed[0] or "", parsed[1] or "",
                        gt_val[0], gt_val[1]])

    # Ranked summary: variants sorted by recovered count (desc), then wrong (asc)
    stats = results["variant_stats"]
    ranked = sorted(stats.items(), key=lambda kv: (-kv[1]["recovered"], kv[1]["wrong"]))

    summary_path = out_dir / "sweep_summary.txt"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(f"OCR Preprocessing Sweep Results\n")
        f.write(f"{'=' * 60}\n")
        f.write(f"Failed pages tested: {results['failed_count']}\n")
        f.write(f"Variants tested: {len(stats)}\n")
        f.write(f"Total evaluations: {results['failed_count'] * len(stats)}\n")
        f.write(f"Elapsed: {results['elapsed']:.1f}s\n\n")

        f.write(f"{'Rank':>4} {'Recovered':>9} {'Wrong':>6} {'Failed':>6}  Variant\n")
        f.write(f"{'-'*4} {'-'*9} {'-'*6} {'-'*6}  {'-'*40}\n")
        for rank, (vtag, st) in enumerate(ranked[:50], 1):
            f.write(f"{rank:4d} {st['recovered']:9d} {st['wrong']:6d} {st['failed']:6d}  {vtag}\n")

        # Baseline comparison
        baseline_tag = "none_blue_only_unsharp_1_03_none_dpi150"
        if baseline_tag in stats:
            bl = stats[baseline_tag]
            f.write(f"\n--- Baseline ({baseline_tag}) ---\n")
            f.write(f"Recovered: {bl['recovered']}, Wrong: {bl['wrong']}, Failed: {bl['failed']}\n")

            # Best vs baseline
            best_tag, best_st = ranked[0]
            delta = best_st["recovered"] - bl["recovered"]
            f.write(f"\n--- Best ({best_tag}) ---\n")
            f.write(f"Recovered: {best_st['recovered']} (+{delta} vs baseline)\n")
            f.write(f"Wrong: {best_st['wrong']}, Failed: {best_st['failed']}\n")

    # Also print summary to stdout
    with open(summary_path) as f:
        print(f.read())

    print(f"\n[report] Detail CSV: {csv_path}")
    print(f"[report] Summary: {summary_path}")
```

- [ ] **Step 18: Implement CLI `main()`**

```python
def main() -> None:
    parser = argparse.ArgumentParser(
        description="OCR Preprocessing Sweep — test variants on failed pages"
    )
    parser.add_argument("pdf_path", help="Path to PDF file (must have GT fixture)")
    parser.add_argument("--max-pages", type=int, default=0,
                        help="Limit failed pages to test (0 = all)")
    parser.add_argument("--workers", type=int, default=6,
                        help="Parallel Tesseract workers (default: 6)")
    parser.add_argument("--out", default=str(OUTPUT_DIR),
                        help=f"Output directory (default: {OUTPUT_DIR})")
    args = parser.parse_args()

    # Init SR for DPI variants that need upscale
    _setup_sr(print)

    results = run_sweep(
        Path(args.pdf_path),
        max_pages=args.max_pages,
        workers=args.workers,
    )
    write_report(results, Path(args.out))


if __name__ == "__main__":
    main()
```

- [ ] **Step 19: Quick smoke test (5 pages)**

```bash
python tools/preprocess_sweep.py <path-to-ART_670.pdf> --max-pages 5 --workers 2
```
Verify: output in `data/preprocess_sweep/`, summary shows ranked variants.

- [ ] **Step 20: Commit**

```bash
git add tools/preprocess_sweep.py
git commit -m "feat(tools): preprocess sweep — report generator + CLI"
```

---

## Task 5: Full sweep run + analysis

- [ ] **Step 21: Run full sweep on ART_670**

```bash
python tools/preprocess_sweep.py <path-to-ART_670.pdf> --workers 6
```

Expected output: ~139K evaluations, ~12 min with 6 workers.

- [ ] **Step 22: Analyze results**

Look at `data/preprocess_sweep/sweep_summary.txt`:
- What is the best variant and how many pages does it recover?
- Is it significantly better than baseline?
- Which dimension (binarization, color, contrast, morphology, DPI) contributes most?
- Are there patterns in the detail CSV (certain pages recovered by many variants, others by none)?

- [ ] **Step 23: Commit results + tag**

```bash
git add data/preprocess_sweep/sweep_summary.txt
git commit -m "data(sweep): preprocessing sweep results — ART_670 193 failed pages"
git tag -a preprocess-sweep-1 -m "First preprocessing sweep: 720 variants × 193 pages"
```

---

## Design Decisions

1. **DPI variants require re-rendering from PDF** — can't just resize existing 150 DPI strips. The sweep pre-renders all needed DPIs upfront to avoid redundant rendering.

2. **No SR (Tier 2) in the sweep** — the sweep tests preprocessing variants at a single tier (Tesseract direct). SR upscale is a separate dimension that multiplies the search space; we can add it as a follow-up if needed.

3. **Thread pool for Tesseract** — pytesseract spawns tesseract.exe as subprocess (releases GIL), so ThreadPoolExecutor gives real parallelism.

4. **Morphology only when binarized** — morphological ops on grayscale images are meaningless, so morph=none is forced when binarize=none. (The matrix still generates these combos for simplicity but they produce identical results to the no-morph variant.)

5. **Ground truth from VLM fixture** — `eval/fixtures/real/ART_670.json` has 796 reads from Claude VLM, all with total=4. This is reliable GT.

---

## What Comes After (NOT in this plan)

- If a variant recovers >30 pages with 0 wrong → candidate for production
- Port winning variant to `core/ocr.py` as Tier 1b (between current Tier 1 and Tier 2)
- Re-run eval sweep to check for regressions on other 20 PDFs
- Possibly: per-page adaptive selection (try multiple variants, pick the one that parses)
