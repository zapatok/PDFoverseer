# OCR Benchmark ART_670 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compare EasyOCR vs PaddleOCR on the 2719 pre-captured ART_670 page crops to determine whether PaddleOCR can recover more failed pages than EasyOCR.

**Architecture:** Standalone benchmark script `eval/ocr_benchmark.py` that loads pre-captured images from `data/ocr_all/ART_670/`, runs each OCR engine sequentially (to avoid GPU memory conflicts), scores against 796 VLM-verified ground truth entries, and reports recovery rates + timing.

**Tech Stack:** Python 3.10+, easyocr 1.7.2, paddlepaddle-gpu 3.0.0 + paddleocr, torch 2.10.0+cu126, cv2, PIL, JSON

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `eval/ocr_benchmark.py` | **Create** | Main benchmark: load images, run engines, score, output |
| `eval/tests/test_benchmark.py` | **Create** | Unit tests for helper functions (fixture loader, paddle extractor, scorer) |
| `data/benchmark_results.json` | **Create (output)** | Per-page results, gitignored |
| `.gitignore` | **Modify** | Add `data/benchmark_results.json` exclusion rule |

---

## Chunk 1: Scaffold, Loaders, and Scoring Helpers

### Task 1: Write tests for helper functions

**Files:**
- Create: `eval/tests/test_benchmark.py`

These functions are non-trivial enough to warrant tests before writing them:
- `load_fixture(path)` — parses JSON fixture into `{pdf_page: (curr, total, method)}`
- `extract_paddle_text(result)` — flattens nested PaddleOCR result into a single string
- `score_page(curr, total, gt_curr, gt_total)` — returns `"hit"`, `"miss"`, or `"none"`

- [ ] **Step 1: Create test file**

```python
# eval/tests/test_benchmark.py
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from eval.ocr_benchmark import load_fixture, extract_paddle_text, score_page


def test_load_fixture_returns_dict():
    """Fixture loads into {pdf_page: (curr, total, method)} dict."""
    gt = load_fixture("eval/fixtures/real/ART_670.json")
    assert isinstance(gt, dict)
    assert len(gt) == 796
    assert gt[1] == (1, 4, "direct")


def test_load_fixture_vlm_entries():
    """VLM-resolved entries are loaded correctly."""
    gt = load_fixture("eval/fixtures/real/ART_670.json")
    vlm_pages = [p for p, (_, _, m) in gt.items() if m in ("vlm_claude", "vlm_opus")]
    assert len(vlm_pages) == 646  # 516 + 130


def test_extract_paddle_text_empty():
    """Empty/None PaddleOCR result returns empty string."""
    assert extract_paddle_text(None) == ""
    assert extract_paddle_text([]) == ""
    assert extract_paddle_text([[]]) == ""


def test_extract_paddle_text_single_line():
    """Extracts text from standard PaddleOCR nested result."""
    result = [[
        ([0, 0, 1, 1], ("Página 1 de 4", 0.95))
    ]]
    assert "Página 1 de 4" in extract_paddle_text(result)


def test_extract_paddle_text_multiple_lines():
    """Joins multiple text regions with space."""
    result = [[
        ([0, 0, 1, 1], ("Pag", 0.9)),
        ([1, 0, 2, 1], ("1 de 4", 0.9)),
    ]]
    text = extract_paddle_text(result)
    assert "Pag" in text
    assert "1 de 4" in text


def test_score_page_hit():
    assert score_page(1, 4, 1, 4) == "hit"


def test_score_page_miss():
    assert score_page(2, 4, 1, 4) == "miss"
    assert score_page(1, 3, 1, 4) == "miss"


def test_score_page_none():
    assert score_page(None, None, 1, 4) == "none"


def test_extract_paddle_text_none_inner():
    """PaddleOCR returns [None] for completely blank images — must not crash."""
    assert extract_paddle_text([None]) == ""
```

- [ ] **Step 2: Run tests — expect ImportError (module doesn't exist yet)**

```bash
cd a:/PROJECTS/PDFoverseer && source .venv-cuda/Scripts/activate && pytest eval/tests/test_benchmark.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError` or `ImportError` — confirms tests are wired correctly.

---

### Task 2: Implement loaders and helpers

**Files:**
- Create: `eval/ocr_benchmark.py`

- [ ] **Step 3: Create script with helpers only (no engine code yet)**

```python
# eval/ocr_benchmark.py
"""
OCR Benchmark: EasyOCR vs PaddleOCR on ART_670 pre-captured images.

Loads 2719 images from data/ocr_all/ART_670/, runs each engine sequentially,
scores against 796 VLM-verified ground truth entries.

Usage:
    source .venv-cuda/Scripts/activate
    python eval/ocr_benchmark.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

# Add project root so eval/ocr_benchmark.py can import core.utils
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.utils import _parse

# ── Paths ─────────────────────────────────────────────────────────────────────

FIXTURE_PATH = Path("eval/fixtures/real/ART_670.json")
IMAGES_DIR   = Path("data/ocr_all/ART_670")
OUTPUT_PATH  = Path("data/benchmark_results.json")
TOTAL_PAGES  = 2719


# ── Helper functions ──────────────────────────────────────────────────────────

def load_fixture(path: str | Path) -> dict[int, tuple[int, int, str]]:
    """
    Load a fixture JSON file.

    Returns:
        {pdf_page: (curr, total, method)} for each entry in the fixture.
    """
    with open(path) as f:
        data = json.load(f)
    return {
        r["pdf_page"]: (r["curr"], r["total"], r["method"])
        for r in data["reads"]
    }


def extract_paddle_text(result) -> str:
    """
    Flatten PaddleOCR nested result into a single string.

    PaddleOCR returns: [[  [bbox, (text, conf)], ... ]]
    The outer list is per-image (always 1 image here), the inner list is
    per-detected-region.
    """
    if not result:
        return ""
    # result is a list with one element per image
    lines = result[0] if result else []
    if not lines:
        return ""
    parts = []
    for item in lines:
        if item and len(item) >= 2:
            text_conf = item[1]
            if text_conf and len(text_conf) >= 1:
                parts.append(str(text_conf[0]))
    return " ".join(parts)


def score_page(
    curr: Optional[int],
    total: Optional[int],
    gt_curr: int,
    gt_total: int,
) -> str:
    """
    Compare OCR result against ground truth.

    Returns:
        "hit"  — both curr and total match ground truth
        "miss" — result was parsed but does not match ground truth
        "none" — OCR returned no parseable result
    """
    if curr is None:
        return "none"
    if curr == gt_curr and total == gt_total:
        return "hit"
    return "miss"


def load_images() -> list[tuple[int, np.ndarray]]:
    """
    Load all 2719 ART_670 page images.

    Returns:
        List of (pdf_page, bgr_image) sorted by page number.
        Images are loaded as BGR (cv2 default).
    """
    images = []
    for i in range(1, TOTAL_PAGES + 1):
        path = IMAGES_DIR / f"p{i:03d}.png"
        img = cv2.imread(str(path))
        if img is None:
            print(f"  WARNING: missing image {path}", flush=True)
            continue
        images.append((i, img))
    return images
```

- [ ] **Step 4: Add `data/benchmark_results.json` and `data/benchmark_run.log` to `.gitignore`**

Append to `.gitignore` after the `# OCR image corpus (large)` block:

```
# OCR benchmark output
data/benchmark_results.json
data/benchmark_run.log
```

- [ ] **Step 5: Run tests — expect all to pass**

```bash
cd a:/PROJECTS/PDFoverseer && source .venv-cuda/Scripts/activate && pytest eval/tests/test_benchmark.py -v
```
Expected: all 9 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add eval/ocr_benchmark.py eval/tests/test_benchmark.py .gitignore
git commit -m "feat(eval): benchmark scaffold — loaders and helpers for ART_670 OCR comparison"
```

---

## Chunk 2: EasyOCR Pass

### Task 3: Implement and run EasyOCR engine

**Files:**
- Modify: `eval/ocr_benchmark.py` — add `run_easyocr(images)` function and `main()` stub

- [ ] **Step 1: Add EasyOCR runner**

Add after the `load_images()` function in `eval/ocr_benchmark.py`:

```python
# ── Engine: EasyOCR ───────────────────────────────────────────────────────────

def run_easyocr(
    images: list[tuple[int, np.ndarray]],
) -> list[dict]:
    """
    Run EasyOCR on all images sequentially.

    Uses grayscale input to match production pipeline behavior
    (core/pipeline.py converts BGR to gray before calling readtext).

    Warm-up: runs first image before timing begins.
    Timing: covers readtext() call only, not _parse().

    Returns:
        List of {pdf_page, curr, total, ms} dicts.
        curr/total are None if _parse() found nothing.
    """
    import easyocr
    import torch

    print("EasyOCR: initializing...", flush=True)
    reader = easyocr.Reader(["es", "en"], gpu=True, verbose=False)
    print("EasyOCR: ready", flush=True)

    # Warm-up (excluded from timing)
    _, bgr0 = images[0]
    gray0 = cv2.cvtColor(bgr0, cv2.COLOR_BGR2GRAY)
    reader.readtext(gray0, detail=0, paragraph=True)
    print("EasyOCR: warm-up done, starting timed run...", flush=True)

    results = []
    for i, (pdf_page, bgr) in enumerate(images):
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

        t0 = time.perf_counter()
        texts = reader.readtext(gray, detail=0, paragraph=True)
        ms = (time.perf_counter() - t0) * 1000

        text = " ".join(texts)
        curr, total = _parse(text)
        results.append({"pdf_page": pdf_page, "curr": curr, "total": total, "ms": round(ms, 1)})

        if (i + 1) % 200 == 0:
            print(f"  EasyOCR: {i + 1}/{len(images)} pages", flush=True)

    del reader
    torch.cuda.empty_cache()
    print("EasyOCR: done, GPU memory released", flush=True)
    return results
```

- [ ] **Step 2: Add `main()` stub that runs EasyOCR only**

Add at the bottom of `eval/ocr_benchmark.py`:

```python
# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Loading images...", flush=True)
    images = load_images()
    print(f"Loaded {len(images)} images", flush=True)

    print("\n--- EasyOCR pass ---")
    easy_results = run_easyocr(images)

    # Minimal progress report
    easy_found = sum(1 for r in easy_results if r["curr"] is not None)
    print(f"EasyOCR: parsed {easy_found}/{len(images)} pages")

    # Placeholder for PaddleOCR and scoring (added in Chunk 3 and 4)
    print("\n[Chunk 2 complete — PaddleOCR and scoring pending]")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Install PaddleOCR dependencies**

```bash
cd a:/PROJECTS/PDFoverseer && source .venv-cuda/Scripts/activate
pip install paddlepaddle-gpu==3.0.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
pip install paddleocr
```

If GPU install fails, fall back to CPU (accuracy comparison still valid):
```bash
pip install paddlepaddle paddleocr
```

- [ ] **Step 4: Verify both engines import cleanly**

```bash
cd a:/PROJECTS/PDFoverseer && source .venv-cuda/Scripts/activate && python -c "
import easyocr; print('easyocr OK')
from paddleocr import PaddleOCR; print('paddleocr OK')
import torch; print('torch OK, CUDA:', torch.cuda.is_available())
"
```
Expected: three `OK` lines printed, no import errors.

- [ ] **Step 5: Run EasyOCR-only benchmark (smoke test)**

```bash
cd a:/PROJECTS/PDFoverseer && source .venv-cuda/Scripts/activate && python eval/ocr_benchmark.py 2>&1 | tail -10
```
Expected: progress lines, final `EasyOCR: parsed N/2719 pages`, `[Chunk 2 complete...]`.

- [ ] **Step 6: Commit**

```bash
git add eval/ocr_benchmark.py
git commit -m "feat(eval): add EasyOCR pass to ART_670 benchmark"
```

---

## Chunk 3: PaddleOCR Pass

### Task 4: Implement PaddleOCR engine

**Files:**
- Modify: `eval/ocr_benchmark.py` — add `run_paddleocr(images)`, update `main()`

- [ ] **Step 1: Add PaddleOCR runner**

Add after `run_easyocr()` in `eval/ocr_benchmark.py`:

```python
# ── Engine: PaddleOCR ─────────────────────────────────────────────────────────

def run_paddleocr(
    images: list[tuple[int, np.ndarray]],
) -> list[dict]:
    """
    Run PaddleOCR on all images sequentially.

    Uses BGR input (PaddleOCR accepts numpy BGR arrays directly).
    use_angle_cls=False: skip orientation classifier (not needed for fixed-crop pages).
    lang="en": English model; handles mixed Spanish/English well enough for digit patterns.

    Warm-up: runs first image before timing begins.
    Timing: covers ocr() call only, not extract_paddle_text() or _parse().

    Returns:
        List of {pdf_page, curr, total, ms} dicts.
        curr/total are None if _parse() found nothing.
    """
    from paddleocr import PaddleOCR as _PaddleOCR

    print("PaddleOCR: initializing...", flush=True)
    reader = _PaddleOCR(
        use_angle_cls=False,
        lang="en",
        use_gpu=True,
        show_log=False,
    )
    print("PaddleOCR: ready", flush=True)

    # Warm-up (excluded from timing)
    _, bgr0 = images[0]
    reader.ocr(bgr0, cls=False)
    print("PaddleOCR: warm-up done, starting timed run...", flush=True)

    results = []
    for i, (pdf_page, bgr) in enumerate(images):
        t0 = time.perf_counter()
        raw = reader.ocr(bgr, cls=False)
        ms = (time.perf_counter() - t0) * 1000

        text = extract_paddle_text(raw)
        curr, total = _parse(text)
        results.append({"pdf_page": pdf_page, "curr": curr, "total": total, "ms": round(ms, 1)})

        if (i + 1) % 200 == 0:
            print(f"  PaddleOCR: {i + 1}/{len(images)} pages", flush=True)

    del reader
    try:
        import paddle
        paddle.device.cuda.empty_cache()
    except Exception:
        pass
    print("PaddleOCR: done, GPU memory released", flush=True)
    return results
```

- [ ] **Step 2: Update `main()` to run both engines**

Replace the `main()` function:

```python
def main():
    print("Loading images...", flush=True)
    images = load_images()
    print(f"Loaded {len(images)} images", flush=True)

    print("\n--- EasyOCR pass ---")
    easy_results = run_easyocr(images)
    easy_found = sum(1 for r in easy_results if r["curr"] is not None)
    print(f"EasyOCR: parsed {easy_found}/{len(images)} pages")

    print("\n--- PaddleOCR pass ---")
    paddle_results = run_paddleocr(images)
    paddle_found = sum(1 for r in paddle_results if r["curr"] is not None)
    print(f"PaddleOCR: parsed {paddle_found}/{len(images)} pages")

    # Placeholder for scoring and output (added in Chunk 4)
    print("\n[Chunk 3 complete — scoring and output pending]")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run full two-engine benchmark**

```bash
cd a:/PROJECTS/PDFoverseer && source .venv-cuda/Scripts/activate && python eval/ocr_benchmark.py 2>&1 | tail -15
```
Expected: both engine progress lines, parsed counts, `[Chunk 3 complete...]`. No GPU OOM errors (engines run sequentially).

- [ ] **Step 4: Commit**

```bash
git add eval/ocr_benchmark.py
git commit -m "feat(eval): add PaddleOCR pass to ART_670 benchmark"
```

---

## Chunk 4: Scoring and Output

### Task 5: Implement scoring, console table, and JSON output

**Files:**
- Modify: `eval/ocr_benchmark.py` — add `score_results()`, `print_report()`, `save_json()`, update `main()`

**Scoring breakdown (4 page categories):**

| Category | Pages | How identified |
|----------|-------|----------------|
| `direct` | 150 | GT exists, method="direct" — Tesseract got these; sanity check for regressions |
| `vlm` | 646 | GT exists, method in (vlm_claude, vlm_opus) — Tesseract failed; these are the hard pages |
| `no_gt_found` | ≤1923 | No GT, engine returned something — potential new recoveries |
| `no_gt_none` | ≤1923 | No GT, engine returned nothing — complete failures |

- [ ] **Step 1: Add scoring function**

Add after `run_paddleocr()`:

```python
# ── Scoring ───────────────────────────────────────────────────────────────────

def score_results(
    engine_results: list[dict],
    ground_truth: dict[int, tuple[int, int, str]],
) -> dict:
    """
    Score engine results against ground truth.

    Returns a dict with per-category counts and per-page details.

    Categories:
      direct: GT exists with method="direct" (Tesseract baseline pages)
      vlm:    GT exists with method in (vlm_claude, vlm_opus) (hard pages)
      no_gt:  No GT — engine output tracked as potential recoveries
    """
    cats = {
        "direct": {"hits": 0, "misses": 0, "nones": 0},
        "vlm":    {"hits": 0, "misses": 0, "nones": 0},
    }
    no_gt_found = []   # (pdf_page, curr, total) — engine found something
    no_gt_none  = 0    # engine found nothing, no GT

    _key = {"hit": "hits", "miss": "misses", "none": "nones"}

    for r in engine_results:
        page = r["pdf_page"]
        curr, total = r["curr"], r["total"]

        if page in ground_truth:
            gt_curr, gt_total, method = ground_truth[page]
            cat = "direct" if method == "direct" else "vlm"
            outcome = score_page(curr, total, gt_curr, gt_total)
            cats[cat][_key[outcome]] += 1
        else:
            if curr is not None:
                no_gt_found.append({"pdf_page": page, "curr": curr, "total": total})
            else:
                no_gt_none += 1

    return {
        "direct": cats["direct"],
        "vlm":    cats["vlm"],
        "no_gt_found": no_gt_found,
        "no_gt_none":  no_gt_none,
    }
```

- [ ] **Step 2: Add timing summary helper**

```python
def avg_ms(results: list[dict]) -> float:
    """Average ms per page. Skips first result to reduce cold-cache noise."""
    times = [r["ms"] for r in results[1:] if r["ms"] > 0]
    return round(sum(times) / len(times), 1) if times else 0.0
```

- [ ] **Step 3: Add console report**

```python
def print_report(
    easy_results: list[dict],
    paddle_results: list[dict],
    easy_score: dict,
    paddle_score: dict,
) -> None:
    """Print benchmark summary to console."""

    def pct(hits, total):
        return f"{hits}/{total} ({round(100*hits/total)}%)" if total else "0/0"

    e_d = easy_score["direct"]
    e_v = easy_score["vlm"]
    p_d = paddle_score["direct"]
    p_v = paddle_score["vlm"]

    e_d_total = e_d["hits"] + e_d["misses"] + e_d["nones"]
    e_v_total = e_v["hits"] + e_v["misses"] + e_v["nones"]
    p_d_total = p_d["hits"] + p_d["misses"] + p_d["nones"]
    p_v_total = p_v["hits"] + p_v["misses"] + p_v["nones"]

    print("\n" + "="*70)
    print("ART_670 OCR Benchmark Results")
    print("="*70)
    print(f"\n{'Category':<25} {'EasyOCR':>20} {'PaddleOCR':>20}")
    print("-"*65)
    print(f"{'direct (n=' + str(e_d_total) + ')':<25} {pct(e_d['hits'], e_d_total):>20} {pct(p_d['hits'], p_d_total):>20}")
    print(f"{'vlm/hard (n=' + str(e_v_total) + ')':<25} {pct(e_v['hits'], e_v_total):>20} {pct(p_v['hits'], p_v_total):>20}")

    e_gt_total = e_d_total + e_v_total
    p_gt_total = p_d_total + p_v_total
    e_gt_hits  = e_d["hits"] + e_v["hits"]
    p_gt_hits  = p_d["hits"] + p_v["hits"]
    print(f"{'ALL GT (n=' + str(e_gt_total) + ')':<25} {pct(e_gt_hits, e_gt_total):>20} {pct(p_gt_hits, p_gt_total):>20}")

    print(f"\n{'Potential recoveries':<25} {len(easy_score['no_gt_found']):>20} {len(paddle_score['no_gt_found']):>20}")
    print(f"{'  (no GT, parsed something)'}")
    print(f"{'Complete failures':<25} {easy_score['no_gt_none']:>20} {paddle_score['no_gt_none']:>20}")
    print(f"{'  (no GT, parse = None)'}")

    print(f"\n{'Timing (ms/page)':<25} {avg_ms(easy_results):>20.1f} {avg_ms(paddle_results):>20.1f}")
    print("="*70)

    # Show sample recoveries (first 10 from PaddleOCR)
    paddle_recoveries = paddle_score["no_gt_found"]
    if paddle_recoveries:
        print(f"\nPaddleOCR potential recoveries (first 10 of {len(paddle_recoveries)}):")
        for r in paddle_recoveries[:10]:
            print(f"  p{r['pdf_page']:04d}: {r['curr']}/{r['total']}")

    easy_recoveries = easy_score["no_gt_found"]
    if easy_recoveries:
        print(f"\nEasyOCR potential recoveries (first 10 of {len(easy_recoveries)}):")
        for r in easy_recoveries[:10]:
            print(f"  p{r['pdf_page']:04d}: {r['curr']}/{r['total']}")
```

- [ ] **Step 4: Add JSON output**

```python
def save_json(
    easy_results: list[dict],
    paddle_results: list[dict],
    easy_score: dict,
    paddle_score: dict,
    path: Path,
) -> None:
    """Save full per-page results and summary to JSON."""
    # Build a page-indexed dict for easy lookup
    easy_by_page   = {r["pdf_page"]: r for r in easy_results}
    paddle_by_page = {r["pdf_page"]: r for r in paddle_results}

    pages = []
    for page in range(1, TOTAL_PAGES + 1):
        e = easy_by_page.get(page, {})
        p = paddle_by_page.get(page, {})
        pages.append({
            "pdf_page":  page,
            "easyocr":   {"curr": e.get("curr"), "total": e.get("total"), "ms": e.get("ms")},
            "paddleocr": {"curr": p.get("curr"), "total": p.get("total"), "ms": p.get("ms")},
        })

    output = {
        "fixture":   "eval/fixtures/real/ART_670.json",
        "images_dir": str(IMAGES_DIR),
        "summary": {
            "easyocr":   {
                "direct":  easy_score["direct"],
                "vlm":     easy_score["vlm"],
                "no_gt_found_count": len(easy_score["no_gt_found"]),
                "no_gt_none_count":  easy_score["no_gt_none"],
                "avg_ms":  avg_ms(easy_results),
            },
            "paddleocr": {
                "direct":  paddle_score["direct"],
                "vlm":     paddle_score["vlm"],
                "no_gt_found_count": len(paddle_score["no_gt_found"]),
                "no_gt_none_count":  paddle_score["no_gt_none"],
                "avg_ms":  avg_ms(paddle_results),
            },
        },
        "pages": pages,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to {path}")
```

- [ ] **Step 5: Replace `main()` with full version**

```python
def main():
    ground_truth = load_fixture(FIXTURE_PATH)
    print(f"Fixture loaded: {len(ground_truth)} GT pages")

    print("\nLoading images...", flush=True)
    images = load_images()
    print(f"Loaded {len(images)} images", flush=True)

    print("\n--- EasyOCR pass ---")
    easy_results = run_easyocr(images)

    print("\n--- PaddleOCR pass ---")
    paddle_results = run_paddleocr(images)

    print("\n--- Scoring ---")
    easy_score   = score_results(easy_results, ground_truth)
    paddle_score = score_results(paddle_results, ground_truth)

    print_report(easy_results, paddle_results, easy_score, paddle_score)
    save_json(easy_results, paddle_results, easy_score, paddle_score, OUTPUT_PATH)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run full benchmark end-to-end**

```bash
cd a:/PROJECTS/PDFoverseer && source .venv-cuda/Scripts/activate && python eval/ocr_benchmark.py 2>&1 | tee data/benchmark_run.log
```
Expected: full console table printed, `Results saved to data/benchmark_results.json`.

- [ ] **Step 7: Verify JSON output is valid**

```bash
cd a:/PROJECTS/PDFoverseer && python -c "
import json
with open('data/benchmark_results.json') as f:
    d = json.load(f)
print('pages:', len(d['pages']))
print('EasyOCR summary:', d['summary']['easyocr'])
print('PaddleOCR summary:', d['summary']['paddleocr'])
"
```
Expected: 2719 pages in output, both summaries printed.

- [ ] **Step 8: Run tests one final time to confirm nothing broke**

```bash
cd a:/PROJECTS/PDFoverseer && source .venv-cuda/Scripts/activate && pytest eval/tests/test_benchmark.py -v
```
Expected: all 9 tests PASS (8 original + 1 `test_extract_paddle_text_none_inner`).

- [ ] **Step 9: Commit**

```bash
git add eval/ocr_benchmark.py eval/tests/test_benchmark.py
git commit -m "feat(eval): complete ART_670 OCR benchmark — EasyOCR vs PaddleOCR scoring and output"
```

---

## Decision Criteria (from spec)

After running, interpret results with these thresholds:

| Result | Action |
|--------|--------|
| PaddleOCR has **more `no_gt_found` recoveries** AND no regressions on `direct` pages | Migrate GPU consumer to PaddleOCR |
| PaddleOCR faster but similar recovery count | Consider migration for speed gain only |
| PaddleOCR has regressions on `direct` pages (Tesseract-easy pages) | Stay with EasyOCR |
| Install fails or GPU OOM | Abort migration, document findings |

**Regression threshold:** Any miss on `direct` pages is a regression (these should be trivially easy for both engines).
