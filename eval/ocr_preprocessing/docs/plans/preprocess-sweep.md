# OCR Preprocessing Sweep Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an evaluation harness that tests parameterized OCR preprocessing pipelines against saved image crops to find configurations that rescue failed pages without regressing successful ones.

**Architecture:** Four new files under `eval/`: parameter space definition, parameterized preprocessing pipeline, sweep runner with two-phase scoring, and results reporter. Reuses `_parse()` from `core/utils` and `_deskew()` from `core/image` as-is.

**Tech Stack:** Python, OpenCV, pytesseract, numpy, csv, concurrent.futures, json

**Spec:** `docs/superpowers/specs/2026-03-24-ocr-preprocess-sweep.md`

---

## Chunk 1: Parameter Space + Preprocessing Pipeline

### Task 1: Create `eval/ocr_params.py`

**Files:**
- Create: `eval/ocr_params.py`

- [ ] **Step 1: Create parameter space and production baseline**

```python
# eval/ocr_params.py
"""
Parameter search space for the OCR preprocessing sweep.
Each key maps to a list of discrete candidate values.
OCR_PRODUCTION_PARAMS mirrors the current _tess_ocr pipeline in core/ocr.py.
"""

OCR_PARAM_SPACE: dict[str, list] = {
    # Blue ink removal (HSV mask + inpainting)
    "blue_inpaint":       [True, False],

    # Grayscale conversion method
    #   "luminance"    = cv2.COLOR_BGR2GRAY (standard weighted)
    #   "min_channel"  = np.min(bgr, axis=2) (max ink-vs-paper contrast)
    "grayscale_method":   ["luminance", "min_channel"],

    # Skip external binarization (let Tesseract LSTM handle thresholding)
    "skip_binarization":  [True, False],

    # Tesseract internal thresholding (only effective when skip_binarization=True)
    #   0 = Otsu (Tesseract default), 2 = Sauvola (adaptive, local)
    "tess_threshold":     [0, 2],

    # White border padding in pixels (improves Tesseract edge detection)
    "white_border":       [0, 5, 10, 15],

    # Unsharp mask gaussian sigma (0 = disabled)
    "unsharp_sigma":      [0.0, 1.0, 1.5, 2.0],

    # Unsharp mask strength/amount (0 = disabled)
    "unsharp_strength":   [0.0, 0.3, 0.5, 0.8],

    # Deskew via projection profile (core/image.py _deskew)
    "deskew":             [True, False],
}

# Current production pipeline equivalent
OCR_PRODUCTION_PARAMS: dict[str, object] = {
    "blue_inpaint":      True,
    "grayscale_method":  "luminance",
    "skip_binarization": False,
    "tess_threshold":    0,
    "white_border":      0,
    "unsharp_sigma":     0.0,
    "unsharp_strength":  0.0,
    "deskew":            False,
}
```

- [ ] **Step 2: Verify file imports correctly**

Run: `python -c "from eval.ocr_params import OCR_PARAM_SPACE, OCR_PRODUCTION_PARAMS; print(len(OCR_PARAM_SPACE), 'params,', len(OCR_PRODUCTION_PARAMS), 'baseline keys')"`
Expected: `8 params, 8 baseline keys`

- [ ] **Step 3: Commit**

```bash
git add eval/ocr_params.py
git commit -m "feat(eval): add OCR preprocessing parameter space"
```

---

### Task 2: Create `eval/ocr_preprocess.py` — preprocessing pipeline

**Files:**
- Create: `eval/ocr_preprocess.py`

- [ ] **Step 1: Write tests for preprocessing pipeline**

Create `eval/tests/test_ocr_preprocess.py`:

```python
# eval/tests/test_ocr_preprocess.py
"""Tests for the parameterized OCR preprocessing pipeline."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import cv2
import numpy as np
import pytest

from eval.ocr_preprocess import preprocess
from eval.ocr_params import OCR_PRODUCTION_PARAMS


def _make_test_image(w: int = 100, h: int = 60) -> np.ndarray:
    """Create a synthetic BGR image with dark text-like marks on white."""
    img = np.full((h, w, 3), 255, dtype=np.uint8)
    cv2.putText(img, "Pag 1 de 3", (5, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
    return img


def _make_blue_ink_image(w: int = 100, h: int = 60) -> np.ndarray:
    """Create image with blue ink overlay on text."""
    img = _make_test_image(w, h)
    # Add blue stroke across middle
    cv2.line(img, (0, 30), (w, 30), (255, 100, 0), 2)  # BGR blue
    return img


class TestPreprocessProductionBaseline:
    def test_returns_tuple(self):
        bgr = _make_test_image()
        result = preprocess(bgr, OCR_PRODUCTION_PARAMS)
        assert isinstance(result, tuple) and len(result) == 2

    def test_image_is_2d(self):
        """Production pipeline should return a binarized (2D) image."""
        bgr = _make_test_image()
        img, _ = preprocess(bgr, OCR_PRODUCTION_PARAMS)
        assert img.ndim == 2

    def test_config_is_string(self):
        bgr = _make_test_image()
        _, cfg = preprocess(bgr, OCR_PRODUCTION_PARAMS)
        assert "--psm 6" in cfg and "--oem 1" in cfg


class TestSkipBinarization:
    def test_grayscale_not_binary(self):
        """When skip_binarization=True, output should have intermediate values."""
        params = dict(OCR_PRODUCTION_PARAMS, skip_binarization=True, tess_threshold=0)
        bgr = _make_test_image()
        img, _ = preprocess(bgr, params)
        unique = np.unique(img)
        # Grayscale should have more than 2 unique values (not just 0/255)
        assert len(unique) > 2

    def test_config_includes_threshold_method(self):
        params = dict(OCR_PRODUCTION_PARAMS, skip_binarization=True, tess_threshold=2)
        bgr = _make_test_image()
        _, cfg = preprocess(bgr, params)
        assert "thresholding_method=2" in cfg


class TestMinChannel:
    def test_differs_from_luminance(self):
        bgr = _make_blue_ink_image()
        p_lum = dict(OCR_PRODUCTION_PARAMS, grayscale_method="luminance", skip_binarization=True)
        p_min = dict(OCR_PRODUCTION_PARAMS, grayscale_method="min_channel", skip_binarization=True)
        img_lum, _ = preprocess(bgr, p_lum)
        img_min, _ = preprocess(bgr, p_min)
        assert not np.array_equal(img_lum, img_min)


class TestWhiteBorder:
    def test_adds_padding(self):
        bgr = _make_test_image(100, 60)
        params = dict(OCR_PRODUCTION_PARAMS, white_border=10)
        img, _ = preprocess(bgr, params)
        # Should be 20px wider and 20px taller (10 each side)
        assert img.shape[0] == 60 + 20
        assert img.shape[1] == 100 + 20

    def test_no_padding_when_zero(self):
        bgr = _make_test_image(100, 60)
        params = dict(OCR_PRODUCTION_PARAMS, white_border=0)
        img, _ = preprocess(bgr, params)
        assert img.shape[0] == 60
        assert img.shape[1] == 100


class TestUnsharpMask:
    def test_sharpened_differs(self):
        bgr = _make_test_image()
        p_none = dict(OCR_PRODUCTION_PARAMS, skip_binarization=True, unsharp_sigma=0.0)
        p_sharp = dict(OCR_PRODUCTION_PARAMS, skip_binarization=True, unsharp_sigma=1.5, unsharp_strength=0.5)
        img_none, _ = preprocess(bgr, p_none)
        img_sharp, _ = preprocess(bgr, p_sharp)
        assert not np.array_equal(img_none, img_sharp)

    def test_disabled_when_sigma_zero(self):
        bgr = _make_test_image()
        p1 = dict(OCR_PRODUCTION_PARAMS, skip_binarization=True, unsharp_sigma=0.0, unsharp_strength=0.5)
        p2 = dict(OCR_PRODUCTION_PARAMS, skip_binarization=True, unsharp_sigma=0.0, unsharp_strength=0.0)
        img1, _ = preprocess(bgr, p1)
        img2, _ = preprocess(bgr, p2)
        assert np.array_equal(img1, img2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest eval/tests/test_ocr_preprocess.py -v`
Expected: ImportError or ModuleNotFoundError for `eval.ocr_preprocess`

- [ ] **Step 3: Implement `eval/ocr_preprocess.py`**

```python
# eval/ocr_preprocess.py
"""
Parameterized OCR preprocessing pipeline for the sweep harness.

Applies a configurable sequence of image transforms to a BGR crop,
returning the processed image and the Tesseract config string to use.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.image import _deskew
from core.utils import TESS_CONFIG

# HSV range for blue ink — must match core/ocr.py _tess_ocr()
_LOWER_BLUE = np.array([90, 50, 50])
_UPPER_BLUE = np.array([150, 255, 255])


def preprocess(bgr: np.ndarray, params: dict) -> tuple[np.ndarray, str]:
    """
    Apply parameterized preprocessing to a BGR crop image.

    Returns
    -------
    (image, tess_config) where image is grayscale (or binary) ndarray
    and tess_config is the Tesseract CLI config string.
    """
    img = bgr.copy()

    # 1. Deskew (projection profile) — requires BGR input
    if params.get("deskew", False) and img.ndim == 3:
        img = _deskew(img)

    # 2. Blue ink removal
    if params.get("blue_inpaint", True):
        if img.ndim == 3 and img.shape[2] >= 3:
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            mask_blue = cv2.inRange(hsv, _LOWER_BLUE, _UPPER_BLUE)
            img = cv2.inpaint(img, mask_blue, 3, cv2.INPAINT_NS)

    # 3. Grayscale conversion
    if img.ndim == 3 and img.shape[2] >= 3:
        method = params.get("grayscale_method", "luminance")
        if method == "min_channel":
            gray = np.min(img, axis=2)
        else:  # "luminance" (default)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    elif img.ndim == 2:
        gray = img
    else:
        gray = img[:, :, 0]

    # 4. Unsharp mask
    sigma = params.get("unsharp_sigma", 0.0)
    strength = params.get("unsharp_strength", 0.0)
    if sigma > 0 and strength > 0:
        ksize = int(round(sigma * 6)) | 1  # ensure odd kernel size
        blurred = cv2.GaussianBlur(gray, (ksize, ksize), sigma)
        gray = cv2.addWeighted(gray, 1.0 + strength, blurred, -strength, 0)

    # 5. White border padding
    border = params.get("white_border", 0)
    if border > 0:
        gray = cv2.copyMakeBorder(
            gray, border, border, border, border,
            cv2.BORDER_CONSTANT, value=255,
        )

    # 6. Binarization
    skip_bin = params.get("skip_binarization", False)
    if not skip_bin:
        _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # 7. Tesseract config
    tess_cfg = TESS_CONFIG
    if skip_bin:
        tess_thresh = params.get("tess_threshold", 0)
        tess_cfg = f"{TESS_CONFIG} -c thresholding_method={tess_thresh}"

    return gray, tess_cfg
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest eval/tests/test_ocr_preprocess.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add eval/ocr_preprocess.py eval/tests/test_ocr_preprocess.py
git commit -m "feat(eval): parameterized OCR preprocessing pipeline + tests"
```

---

## Chunk 2: Sweep Runner

### Task 3: Create `eval/ocr_sweep.py` — data loading + config enumeration

**Files:**
- Create: `eval/ocr_sweep.py`

- [ ] **Step 1: Implement data loading and config generation**

```python
# eval/ocr_sweep.py
"""
Two-phase OCR preprocessing sweep.

Phase A: test all valid configs against failed pages (rescue rate).
Phase B: test top-N configs against successful pages (regression check).

Usage:
    cd a:/PROJECTS/PDFoverseer
    python eval/ocr_sweep.py
    # -> writes eval/results/ocr_sweep_YYYYMMDD_HHMMSS.json
"""
from __future__ import annotations

import csv
import json
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2
import pytesseract

from core.utils import _parse, TESS_CONFIG
from eval.ocr_params import OCR_PARAM_SPACE, OCR_PRODUCTION_PARAMS
from eval.ocr_preprocess import preprocess

_ROOT       = Path(__file__).parent.parent
DATA_DIR    = _ROOT / "data" / "ocr_all"
INDEX_CSV   = DATA_DIR / "all_index.csv"
RESULTS_DIR = Path(__file__).parent / "results"
WORKERS     = 6


# ── Data types ──────────────────────────────────────────────────────────────

@dataclass
class PageEntry:
    pdf_nickname: str
    page_num:     int
    image_path:   str       # relative to DATA_DIR
    is_success:   bool      # tier1 or tier2 parsed
    expected:     str       # e.g. "1/2" or "" if failed


# ── Data loading ────────────────────────────────────────────────────────────

def load_pages() -> tuple[list[PageEntry], list[PageEntry]]:
    """Load page index, return (failed_pages, success_pages)."""
    failed, success = [], []
    with open(INDEX_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            t1 = (row.get("tier1_parsed") or "").strip()
            t2 = (row.get("tier2_parsed") or "").strip()
            is_ok = bool(t1 or t2)
            entry = PageEntry(
                pdf_nickname=row["pdf_nickname"],
                page_num=int(row["page_num"]),
                image_path=row["image_path"],
                is_success=is_ok,
                expected=t1 or t2,
            )
            (success if is_ok else failed).append(entry)
    return failed, success


# ── Config enumeration ──────────────────────────────────────────────────────

def enumerate_configs() -> list[dict]:
    """Generate all valid parameter combinations, deduplicating tess_threshold
    when skip_binarization=False (external Otsu ignores tess_threshold)."""
    keys = list(OCR_PARAM_SPACE.keys())
    vals = [OCR_PARAM_SPACE[k] for k in keys]
    configs = []
    seen = set()
    for combo in product(*vals):
        cfg = dict(zip(keys, combo))
        # Normalize: tess_threshold irrelevant when not skipping binarization
        if not cfg["skip_binarization"]:
            cfg["tess_threshold"] = 0
        # Normalize: unsharp_strength irrelevant when sigma == 0
        if cfg["unsharp_sigma"] == 0.0:
            cfg["unsharp_strength"] = 0.0
        key = tuple(sorted(cfg.items()))
        if key not in seen:
            seen.add(key)
            configs.append(cfg)
    return configs


# ── Single-page OCR ─────────────────────────────────────────────────────────

def _ocr_page(image_path: str, params: dict) -> tuple[int | None, int | None]:
    """Load image, preprocess, run Tesseract, parse."""
    full_path = str(DATA_DIR / image_path)
    bgr = cv2.imread(full_path)
    if bgr is None:
        return None, None
    img, tess_cfg = preprocess(bgr, params)
    try:
        text = pytesseract.image_to_string(img, lang="eng", config=tess_cfg)
    except Exception:
        return None, None
    return _parse(text)


# ── Scoring ─────────────────────────────────────────────────────────────────

def score_on_pages(params: dict, pages: list[PageEntry]) -> dict:
    """Score a config against a list of pages. Returns counts dict."""
    rescued = regressed = maintained = still_failed = 0
    rescued_pages = []

    for page in pages:
        curr, total = _ocr_page(page.image_path, params)
        parsed = curr is not None

        if page.is_success and parsed:
            maintained += 1
        elif page.is_success and not parsed:
            regressed += 1
        elif not page.is_success and parsed:
            rescued += 1
            rescued_pages.append(f"{page.pdf_nickname}/p{page.page_num:03d}")
        else:
            still_failed += 1

    n_fail = rescued + still_failed
    n_ok = maintained + regressed
    return {
        "rescued":         rescued,
        "regressed":       regressed,
        "maintained":      maintained,
        "still_failed":    still_failed,
        "rescue_rate":     round(rescued / max(1, n_fail), 4),
        "regression_rate": round(regressed / max(1, n_ok), 4),
        "net_gain":        rescued - regressed * 3,
        "rescued_pages":   rescued_pages,
    }


# ── Worker function (for multiprocessing) ──────────────────────────────────

def _score_config_worker(args: tuple) -> tuple[int, dict]:
    """Worker: (config_index, params, pages) -> (config_index, scores)."""
    idx, params, pages = args
    scores = score_on_pages(params, pages)
    return idx, scores


# ── Sweep runner ────────────────────────────────────────────────────────────

def run_sweep() -> dict:
    failed, success = load_pages()
    configs = enumerate_configs()
    print(f"Loaded {len(failed)} failed + {len(success)} success pages")
    print(f"Generated {len(configs)} unique configs")

    # Baseline
    print("\nScoring baseline (production params)...")
    baseline = score_on_pages(OCR_PRODUCTION_PARAMS, failed)
    print(f"  Baseline: rescued={baseline['rescued']}, "
          f"still_failed={baseline['still_failed']}")

    # Phase A: all configs against failed pages
    print(f"\nPhase A: scoring {len(configs)} configs on {len(failed)} failed pages...")
    results_a: list[tuple[dict, dict]] = []
    t0 = time.time()

    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        futures = {
            pool.submit(_score_config_worker, (i, cfg, failed)): i
            for i, cfg in enumerate(configs)
        }
        done = 0
        for future in as_completed(futures):
            idx, scores = future.result()
            results_a.append((configs[idx], scores))
            done += 1
            if done % 50 == 0 or done == len(configs):
                elapsed = time.time() - t0
                rate = done / elapsed
                eta = (len(configs) - done) / rate if rate > 0 else 0
                print(f"  Phase A: {done}/{len(configs)} "
                      f"({elapsed:.0f}s, ~{eta:.0f}s remaining)", end="\r")

    print(f"\n  Phase A done in {time.time() - t0:.0f}s")

    # Rank by rescue count
    results_a.sort(key=lambda x: (-x[1]["rescued"], x[1]["still_failed"]))
    top10 = results_a[:10]

    print("\n  Top-10 Phase A results:")
    for i, (cfg, sc) in enumerate(top10, 1):
        diff = {k: v for k, v in cfg.items() if v != OCR_PRODUCTION_PARAMS.get(k)}
        print(f"    #{i}: rescued={sc['rescued']} | diff={diff}")

    # Phase B: regression check on top-10 against success sample
    rng = random.Random(42)
    sample_size = min(200, len(success))
    success_sample = rng.sample(success, sample_size)

    print(f"\nPhase B: regression check on {sample_size} success pages...")
    results_b = []
    for i, (cfg, sc_a) in enumerate(top10, 1):
        sc_b = score_on_pages(cfg, success_sample)
        combined = {
            "params": cfg,
            "phase_a": {k: v for k, v in sc_a.items() if k != "rescued_pages"},
            "phase_b": {k: v for k, v in sc_b.items() if k != "rescued_pages"},
            "net_gain": sc_a["rescued"] - sc_b["regressed"] * 3,
            "rescued_pages": sc_a["rescued_pages"],
        }
        results_b.append(combined)
        print(f"  Config #{i}: rescued={sc_a['rescued']}, "
              f"regressed={sc_b['regressed']}/{sample_size}, "
              f"net_gain={combined['net_gain']}")

    # Final ranking by net_gain
    results_b.sort(key=lambda x: -x["net_gain"])

    # Baseline regression check
    baseline_b = score_on_pages(OCR_PRODUCTION_PARAMS, success_sample)

    return {
        "run_at": datetime.now().isoformat(),
        "total_failed_pages": len(failed),
        "total_success_pages": len(success),
        "success_sample_size": sample_size,
        "configs_tested": len(configs),
        "baseline_failed": {k: v for k, v in baseline.items() if k != "rescued_pages"},
        "baseline_success": {k: v for k, v in baseline_b.items() if k != "rescued_pages"},
        "top_configs": results_b,
    }


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result = run_sweep()
    out_path = RESULTS_DIR / f"ocr_sweep_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(f"\nResults saved to {out_path}")
    if result["top_configs"]:
        top = result["top_configs"][0]
        print(f"Best config: net_gain={top['net_gain']}, "
              f"rescued={top['phase_a']['rescued']}, "
              f"regressed={top['phase_b']['regressed']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify data loading works**

Run: `python -c "from eval.ocr_sweep import load_pages, enumerate_configs; f,s = load_pages(); print(f'{len(f)} failed, {len(s)} success'); c = enumerate_configs(); print(f'{len(c)} configs')"`
Expected: `697 failed, 2768 success` (approx) and config count < 2048

- [ ] **Step 3: Commit**

```bash
git add eval/ocr_sweep.py
git commit -m "feat(eval): OCR preprocessing sweep runner (two-phase)"
```

---

## Chunk 3: Report + Integration Test

### Task 4: Create `eval/ocr_report.py`

**Files:**
- Create: `eval/ocr_report.py`

- [ ] **Step 1: Implement results reporter**

```python
# eval/ocr_report.py
"""
Print ranked results from an OCR preprocessing sweep JSON file.

Usage:
    python eval/ocr_report.py                          # latest result
    python eval/ocr_report.py eval/results/ocr_sweep_*.json  # specific file
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.ocr_params import OCR_PRODUCTION_PARAMS

RESULTS_DIR = Path("eval/results")


def find_latest() -> Path | None:
    files = sorted(RESULTS_DIR.glob("ocr_sweep_*.json"))
    return files[-1] if files else None


def print_report(data: dict) -> None:
    print("=" * 72)
    print("OCR Preprocessing Sweep Report")
    print(f"  Run: {data['run_at']}")
    print(f"  Failed pages: {data['total_failed_pages']}")
    print(f"  Success sample: {data['success_sample_size']}")
    print(f"  Configs tested: {data['configs_tested']}")
    print()

    bl_f = data["baseline_failed"]
    bl_s = data["baseline_success"]
    print(f"  Baseline (production): rescued={bl_f['rescued']}, "
          f"regression={bl_s['regressed']}/{data['success_sample_size']}")
    print("=" * 72)

    print(f"\n{'Rank':>4} {'Rescued':>8} {'Regressed':>10} {'NetGain':>8}  "
          f"{'Diff from production'}")
    print("-" * 72)

    for i, entry in enumerate(data["top_configs"], 1):
        pa = entry["phase_a"]
        pb = entry["phase_b"]
        diff = {k: v for k, v in entry["params"].items()
                if v != OCR_PRODUCTION_PARAMS.get(k)}
        diff_str = ", ".join(f"{k}={v}" for k, v in sorted(diff.items()))
        print(f"{i:>4} {pa['rescued']:>8} {pb['regressed']:>10} "
              f"{entry['net_gain']:>8}  {diff_str}")

    if data["top_configs"]:
        print(f"\nBest config rescued pages:")
        best = data["top_configs"][0]
        for p in best.get("rescued_pages", [])[:20]:
            print(f"  {p}")
        remaining = len(best.get("rescued_pages", [])) - 20
        if remaining > 0:
            print(f"  ... and {remaining} more")


def main():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        path = find_latest()
        if not path:
            print("No sweep results found in eval/results/")
            sys.exit(1)

    data = json.loads(path.read_text())
    print_report(data)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add eval/ocr_report.py
git commit -m "feat(eval): OCR sweep results reporter"
```

---

### Task 5: Smoke test with a small subset

- [ ] **Step 1: Run a quick 2-config smoke test**

Run:
```bash
python -c "
from eval.ocr_sweep import load_pages, score_on_pages
from eval.ocr_params import OCR_PRODUCTION_PARAMS

failed, success = load_pages()
sample = failed[:5]  # just 5 pages

# Production baseline
sc1 = score_on_pages(OCR_PRODUCTION_PARAMS, sample)
print(f'Production: {sc1}')

# Test: skip binarization + Sauvola
params2 = dict(OCR_PRODUCTION_PARAMS, skip_binarization=True, tess_threshold=2)
sc2 = score_on_pages(params2, sample)
print(f'Skip-bin+Sauvola: {sc2}')
"
```

Expected: Both run without error. May or may not rescue pages.

- [ ] **Step 2: Commit (all files, final)**

```bash
git add eval/ocr_params.py eval/ocr_preprocess.py eval/ocr_sweep.py eval/ocr_report.py eval/tests/test_ocr_preprocess.py
git commit -m "feat(eval): complete OCR preprocessing sweep harness"
```

---

## Execution Notes

**To run the full sweep:**
```bash
cd a:/PROJECTS/PDFoverseer
python eval/ocr_sweep.py
python eval/ocr_report.py
```

**Time estimate:** ~3-4 hours for full sweep with 6 workers. For a quick test, reduce configs by fixing some parameters (e.g., only vary `skip_binarization`, `tess_threshold`, `blue_inpaint`).

**After sweep results:** The winning config's parameter changes should be ported to `core/ocr.py` `_tess_ocr()` and tested on live PDFs.
