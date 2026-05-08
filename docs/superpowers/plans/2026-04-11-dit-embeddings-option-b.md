# DiT Embeddings + Cosine Similarity (Option B) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test if replacing handcrafted 80-d features (dark_ratio + edge_density) + bilateral L2 with DiT-base 768-d embeddings + bilateral cosine similarity improves cover-page detection on the 13 ART folders from `A:/informe mensual/MARZO/rio_bueno/7.- ART  Realizadas/`.

**Architecture:** Reuse the existing rendered-page cache; feed pages through `microsoft/dit-base` on GPU to extract per-page 768-d CLS embeddings; cache embeddings to disk in the same `.npz` style as the pixel cache; add a `bilateral_cosine` distance that plugs into the existing `bilateral_scores` harness; reuse `scorer_find_peaks` and `scorer_rescue_c` structure but over the new signal; benchmark on the same 13 folders used as the baseline in this session and compare MAE + exact-count matches against `rescue_c` (the current best: MAE=9.5, 4/13 exact).

**Tech Stack:** Python 3.10, torch 2.10.0+cu126 (GTX 1080 already verified), transformers (to install), PyMuPDF (already present), numpy/scipy, pytest.

**Branch:** `research/pixel-density` (current checkout). No worktree needed — this is a contained experiment in an existing research branch.

**Baseline to beat** (from session 2026-04-11, `A:/informe mensual/MARZO/rio_bueno/7.- ART Realizadas`, 13 folders, 831 expected documents):

| Scorer | Exact matches | MAE | Notes |
|--------|---------------|-----|-------|
| `scorer_find_peaks` (handcrafted 80-d + L2) | 1/13 | 35.6 | Overcounts badly |
| `scorer_rescue_c` (handcrafted 80-d + L2) | **4/13** | **9.5** | Current best |

---

## Chunk 1: Setup & Dependency

### Task 1: Install transformers and sanity-check DiT model load

**Files:**
- Modify: `requirements-gpu.txt` (add transformers line)
- No test file yet — this is environment setup

- [ ] **Step 1.1: Verify transformers is missing**

Run:
```bash
source .venv-cuda/Scripts/activate && python -c "import transformers" 2>&1
```

Expected: `ModuleNotFoundError: No module named 'transformers'`

- [ ] **Step 1.2: Install transformers**

Run:
```bash
source .venv-cuda/Scripts/activate && pip install "transformers>=4.40,<5"
```

Expected: installs transformers + dependencies (tokenizers, huggingface-hub, safetensors). No errors.

- [ ] **Step 1.3: Add transformers to requirements-gpu.txt**

Append one line to `a:\PROJECTS\PDFoverseer\requirements-gpu.txt`:
```
transformers>=4.40,<5
```

Keep the existing ordering of the file; add near the other torch-adjacent deps.

- [ ] **Step 1.4: Verify DiT-base downloads and loads on CUDA**

Run the following one-liner (this triggers the first download of `microsoft/dit-base`, ~340 MB):

```bash
source .venv-cuda/Scripts/activate && python -c "
import torch
from transformers import AutoImageProcessor, AutoModel
processor = AutoImageProcessor.from_pretrained('microsoft/dit-base')
model = AutoModel.from_pretrained('microsoft/dit-base').to('cuda').eval()
print('OK:', model.config.hidden_size, 'dims, device:', next(model.parameters()).device)
"
```

Expected: `OK: 768 dims, device: cuda:0`

- [ ] **Step 1.5: Commit**

```bash
git add requirements-gpu.txt
git commit -m "chore(eval): add transformers dep for DiT embeddings experiment"
```

---

## Chunk 2: DiT Embedding Extraction + Cache

### Task 2: `bilateral_cosine` distance in metrics.py

**Files:**
- Modify: `eval/pixel_density/metrics.py` (add function after `bilateral_l2`)
- Test: `eval/tests/test_bilateral_cosine.py` (new)

- [ ] **Step 2.1: Write the failing test**

Create `a:\PROJECTS\PDFoverseer\eval\tests\test_bilateral_cosine.py`:

```python
"""Tests for bilateral_cosine distance in metrics.py."""

from __future__ import annotations

import numpy as np

from eval.pixel_density.metrics import bilateral_cosine


def test_bilateral_cosine_identical_pages_score_zero():
    """Identical page features should yield zero cosine distance."""
    features = [np.array([1.0, 2.0, 3.0]) for _ in range(5)]
    scores = bilateral_cosine(features, score_fn="min")
    assert scores.shape == (5,)
    assert np.allclose(scores, 0.0, atol=1e-6)


def test_bilateral_cosine_orthogonal_neighbors_score_one():
    """Orthogonal neighbors should yield cosine distance of 1.0."""
    features = [
        np.array([1.0, 0.0]),
        np.array([0.0, 1.0]),
        np.array([1.0, 0.0]),
    ]
    scores = bilateral_cosine(features, score_fn="min")
    # Middle page: both neighbors orthogonal, min should be 1.0
    assert abs(scores[1] - 1.0) < 1e-6


def test_bilateral_cosine_normalizes_magnitude():
    """Scaling a vector should not change cosine distance (magnitude-invariant)."""
    features = [
        np.array([1.0, 0.0]),
        np.array([1.0, 0.0]),  # same direction
        np.array([100.0, 0.0]),  # same direction, different magnitude
    ]
    scores = bilateral_cosine(features, score_fn="mean")
    assert np.allclose(scores, 0.0, atol=1e-6)
```

- [ ] **Step 2.2: Run the test and verify it fails**

Run:
```bash
source .venv-cuda/Scripts/activate && pytest eval/tests/test_bilateral_cosine.py -v
```

Expected: `ImportError` or `AttributeError: module 'eval.pixel_density.metrics' has no attribute 'bilateral_cosine'`

- [ ] **Step 2.3: Implement `bilateral_cosine` in metrics.py**

Append to `a:\PROJECTS\PDFoverseer\eval\pixel_density\metrics.py` (after `bilateral_l2`):

```python
def bilateral_cosine(
    page_features: list[np.ndarray],
    score_fn: str,
) -> np.ndarray:
    """Bilateral scoring with cosine distance (1 - cosine similarity).

    Magnitude-invariant: only the direction of each feature vector matters.
    Recommended for high-dimensional embeddings (e.g., DiT 768-d) where L2
    distance concentration is a problem.

    Args:
        page_features: Per-page feature vectors.
        score_fn: Aggregation: "min", "mean", or "harmonic".

    Returns:
        1-D array of bilateral scores in [0, 2].
    """
    def cosine_dist(a: np.ndarray, b: np.ndarray) -> float:
        na = float(np.linalg.norm(a))
        nb = float(np.linalg.norm(b))
        if na == 0.0 or nb == 0.0:
            return 1.0
        return 1.0 - float(np.dot(a, b) / (na * nb))

    return bilateral_scores(page_features, cosine_dist, score_fn)
```

- [ ] **Step 2.4: Run the test and verify it passes**

Run:
```bash
source .venv-cuda/Scripts/activate && pytest eval/tests/test_bilateral_cosine.py -v
```

Expected: 3 passed

- [ ] **Step 2.5: Ruff check**

Run:
```bash
source .venv-cuda/Scripts/activate && ruff check eval/pixel_density/metrics.py eval/tests/test_bilateral_cosine.py
```

Expected: 0 violations

- [ ] **Step 2.6: Commit**

```bash
git add eval/pixel_density/metrics.py eval/tests/test_bilateral_cosine.py
git commit -m "feat(pixel_density): add bilateral_cosine distance for high-dim embeddings"
```

---

### Task 3: DiT embedding extraction module with disk cache

**Files:**
- Create: `eval/pixel_density/dit_embeddings.py`
- Test: `eval/tests/test_dit_embeddings.py`

**Rationale:** Mirror the `cache.py` pattern. One function `ensure_dit_embeddings(pdf_path)` that loads from `data/pixel_density/dit_cache/<stem>_dit_base.npz` or computes + caches. Input: the already-cached rendered pages (from `ensure_cache`, DPI=100 grayscale). Output: `(n_pages, 768)` float32 array.

- [ ] **Step 3.1: Write the failing test**

Create `a:\PROJECTS\PDFoverseer\eval\tests\test_dit_embeddings.py`:

```python
"""Tests for DiT embedding extraction + cache."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from eval.pixel_density.cache import ensure_cache
from eval.pixel_density.dit_embeddings import ensure_dit_embeddings

# Small fixture: 3-page ART PINGON (01).pdf. Real file from the rio_bueno corpus.
# If run on a machine without that file, the test is skipped.
TINY_PDF = Path(
    "A:/informe mensual/MARZO/rio_bueno/7.- ART  Realizadas/"
    "ART PINGON 23/ART PINGON (01).pdf"
)


@pytest.mark.skipif(not TINY_PDF.exists(), reason="rio_bueno corpus not present")
def test_ensure_dit_embeddings_shape_and_dtype(tmp_path: Path):
    """Embedding array should be (n_pages, 768) float32."""
    embeddings = ensure_dit_embeddings(str(TINY_PDF), cache_dir=tmp_path)
    pages = ensure_cache(str(TINY_PDF))
    assert embeddings.shape == (pages.shape[0], 768)
    assert embeddings.dtype == np.float32


@pytest.mark.skipif(not TINY_PDF.exists(), reason="rio_bueno corpus not present")
def test_ensure_dit_embeddings_cache_hit_returns_identical_array(tmp_path: Path):
    """Second call should load from cache, not recompute."""
    first = ensure_dit_embeddings(str(TINY_PDF), cache_dir=tmp_path)
    second = ensure_dit_embeddings(str(TINY_PDF), cache_dir=tmp_path)
    np.testing.assert_array_equal(first, second)
```

- [ ] **Step 3.2: Run the test and verify it fails**

Run:
```bash
source .venv-cuda/Scripts/activate && pytest eval/tests/test_dit_embeddings.py -v
```

Expected: `ModuleNotFoundError: No module named 'eval.pixel_density.dit_embeddings'`

- [ ] **Step 3.3: Implement `dit_embeddings.py`**

Create `a:\PROJECTS\PDFoverseer\eval\pixel_density\dit_embeddings.py`:

```python
"""DiT (Document Image Transformer) embedding extraction with disk cache.

Loads microsoft/dit-base (42M document images pretrained, 768-d CLS output)
and produces one embedding per rendered page. Mirrors the pattern of
cache.py for the pixel-array cache.

Cache layout: data/pixel_density/dit_cache/<stem>_dit_base.npz
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

import numpy as np

from eval.pixel_density.cache import ensure_cache

logger = logging.getLogger(__name__)

DEFAULT_DIT_CACHE_DIR = Path("data/pixel_density/dit_cache")
MODEL_NAME = "microsoft/dit-base"
EMBED_DIM = 768
BATCH_SIZE = 16

# Lazy module-level singletons for the model + processor.
_model = None
_processor = None
_device = None


def _load_model():
    """Lazy-load DiT-base onto CUDA (or CPU fallback) exactly once."""
    global _model, _processor, _device
    if _model is not None:
        return _model, _processor, _device

    import torch
    from transformers import AutoImageProcessor, AutoModel

    _device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info("Loading %s on %s...", MODEL_NAME, _device)
    _processor = AutoImageProcessor.from_pretrained(MODEL_NAME)
    _model = AutoModel.from_pretrained(MODEL_NAME).to(_device).eval()
    return _model, _processor, _device


def _cache_path(pdf_path: str, cache_dir: Path) -> Path:
    stem = Path(pdf_path).stem
    return cache_dir / f"{stem}_dit_base.npz"


def _embed_pages(pages: np.ndarray) -> np.ndarray:
    """Run DiT over all pages in batches. Returns (n_pages, 768) float32.

    Args:
        pages: Grayscale uint8 array, shape (n, H, W).
    """
    import torch
    from PIL import Image

    model, processor, device = _load_model()
    n = pages.shape[0]
    out = np.empty((n, EMBED_DIM), dtype=np.float32)

    with torch.no_grad():
        for start in range(0, n, BATCH_SIZE):
            end = min(start + BATCH_SIZE, n)
            # Grayscale → RGB (repeat channel, DiT expects 3-channel input)
            batch_imgs = [
                Image.fromarray(pages[i]).convert("RGB") for i in range(start, end)
            ]
            inputs = processor(images=batch_imgs, return_tensors="pt").to(device)
            outputs = model(**inputs)
            # CLS token = first position of last_hidden_state
            cls = outputs.last_hidden_state[:, 0, :].cpu().numpy().astype(np.float32)
            out[start:end] = cls
    return out


def ensure_dit_embeddings(
    pdf_path: str,
    cache_dir: Path | None = None,
) -> np.ndarray:
    """Return cached DiT embeddings for a PDF, computing on first call.

    Args:
        pdf_path: Path to PDF file.
        cache_dir: Override cache directory (default: data/pixel_density/dit_cache/).

    Returns:
        Array of shape (n_pages, 768), dtype float32.
    """
    if cache_dir is None:
        cache_dir = DEFAULT_DIT_CACHE_DIR

    path = _cache_path(pdf_path, cache_dir)
    if path.exists():
        try:
            data = np.load(str(path))
            arr = data["embeddings"]
            logger.info("DiT cache hit: %s (%d pages)", path.name, arr.shape[0])
            return arr
        except Exception:
            logger.warning("DiT cache load failed for %s, recomputing", path.name)

    pages = ensure_cache(pdf_path)  # uses existing pixel cache
    logger.info("Embedding %s with %s...", Path(pdf_path).name, MODEL_NAME)
    t0 = time.perf_counter()
    embeddings = _embed_pages(pages)
    elapsed = time.perf_counter() - t0
    logger.info(
        "Embedded %d pages in %.1fs (%.1f ms/page)",
        embeddings.shape[0],
        elapsed,
        1000 * elapsed / max(embeddings.shape[0], 1),
    )

    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp.npz")
    np.savez_compressed(str(tmp_path), embeddings=embeddings)
    shutil.move(str(tmp_path), str(path))
    logger.info("Cached to %s (%.1f MB)", path.name, path.stat().st_size / 1e6)

    return embeddings
```

- [ ] **Step 3.4: Run the tests and verify they pass**

Run:
```bash
source .venv-cuda/Scripts/activate && pytest eval/tests/test_dit_embeddings.py -v
```

Expected: 2 passed (first test triggers the DiT model download + embedding of the 3-page PINGON fixture; second test hits cache). On a cold CUDA load, first run may take ~15-25s including model load.

If the tests are skipped because the rio_bueno corpus isn't mounted, stop and tell the user — we cannot continue the experiment without the input PDFs.

- [ ] **Step 3.5: Ruff check**

Run:
```bash
source .venv-cuda/Scripts/activate && ruff check eval/pixel_density/dit_embeddings.py eval/tests/test_dit_embeddings.py
```

Expected: 0 violations

- [ ] **Step 3.6: Commit**

```bash
git add eval/pixel_density/dit_embeddings.py eval/tests/test_dit_embeddings.py
git commit -m "feat(pixel_density): add DiT-base embedding extraction with disk cache"
```

---

## Chunk 3: Scoring + Batch Benchmark

### Task 4: DiT-aware scorers mirroring `scorer_find_peaks` and `scorer_rescue_c`

**Files:**
- Create: `eval/pixel_density/scorer_dit.py`
- Test: `eval/tests/test_scorer_dit.py`

**Rationale:** Reuse the peak-detection + percentile-threshold logic from `sweep_rescue.py`, but with `bilateral_cosine` over DiT embeddings instead of `bilateral_l2` over handcrafted features. No cover-shift or template rescue in this first pass — keep it minimal and see if the raw signal is better. If it is, we can port the shift/rescue later.

- [ ] **Step 4.1: Write the failing test**

Create `a:\PROJECTS\PDFoverseer\eval\tests\test_scorer_dit.py`:

```python
"""Tests for the DiT-based cover detection scorers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from eval.pixel_density.scorer_dit import (
    score_dit_find_peaks,
    score_dit_percentile,
)


def test_score_dit_find_peaks_returns_sorted_indices_with_page_0():
    """Any scorer output must include page 0 and be sorted ascending."""
    rng = np.random.default_rng(0)
    embeddings = rng.standard_normal((10, 768)).astype(np.float32)
    covers = score_dit_find_peaks(embeddings, prominence=0.1, distance=1)
    assert 0 in covers
    assert covers == sorted(covers)


def test_score_dit_percentile_returns_sorted_indices_with_page_0():
    rng = np.random.default_rng(0)
    embeddings = rng.standard_normal((10, 768)).astype(np.float32)
    covers = score_dit_percentile(embeddings, percentile=75.0)
    assert 0 in covers
    assert covers == sorted(covers)


def test_score_dit_synthetic_repeating_block_pattern():
    """Three blocks of 5 identical embeddings → covers at 0, 5, 10."""
    rng = np.random.default_rng(42)
    block1 = rng.standard_normal(768).astype(np.float32)
    block2 = rng.standard_normal(768).astype(np.float32)
    block3 = rng.standard_normal(768).astype(np.float32)
    embeddings = np.vstack(
        [np.tile(block1, (5, 1)), np.tile(block2, (5, 1)), np.tile(block3, (5, 1))]
    )
    covers = score_dit_find_peaks(embeddings, prominence=0.1, distance=1)
    # Should detect boundaries at indices 5 and 10 (plus always-include 0).
    assert 0 in covers
    assert 5 in covers
    assert 10 in covers
    # Should NOT over-detect inside blocks.
    assert len(covers) <= 4  # allow 1 spurious at most in a tiny synthetic case
```

- [ ] **Step 4.2: Run the test and verify it fails**

Run:
```bash
source .venv-cuda/Scripts/activate && pytest eval/tests/test_scorer_dit.py -v
```

Expected: `ModuleNotFoundError: No module named 'eval.pixel_density.scorer_dit'`

- [ ] **Step 4.3: Implement `scorer_dit.py`**

Create `a:\PROJECTS\PDFoverseer\eval\pixel_density\scorer_dit.py`:

```python
"""Cover-page scorers over DiT embeddings + bilateral cosine similarity.

Minimal ports of scorer_find_peaks and scorer_rescue_c from sweep_rescue.py,
using cosine distance over 768-d DiT embeddings instead of L2 over 80-d
handcrafted features.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import find_peaks as scipy_find_peaks

from eval.pixel_density.metrics import bilateral_cosine


def _bilateral_cosine_min(embeddings: np.ndarray) -> np.ndarray:
    """Return per-page bilateral-min cosine scores for an (N, D) embedding matrix."""
    features = [embeddings[i] for i in range(embeddings.shape[0])]
    return bilateral_cosine(features, score_fn="min")


def score_dit_find_peaks(
    embeddings: np.ndarray,
    prominence: float = 0.1,
    distance: int = 2,
) -> list[int]:
    """Peak-detection scorer over DiT bilateral-cosine signal.

    Args:
        embeddings: (N, 768) DiT embeddings, float32.
        prominence: Minimum peak prominence (scipy find_peaks).
        distance: Minimum separation between peaks.

    Returns:
        Sorted list of cover-page indices (always includes 0).
    """
    signal = _bilateral_cosine_min(embeddings)
    peaks, _ = scipy_find_peaks(signal, prominence=prominence, distance=distance)
    covers = set(peaks.tolist())
    covers.add(0)
    return sorted(covers)


def score_dit_percentile(
    embeddings: np.ndarray,
    percentile: float = 75.0,
) -> list[int]:
    """Percentile-threshold scorer over DiT bilateral-cosine signal.

    Args:
        embeddings: (N, 768) DiT embeddings, float32.
        percentile: Pages at or above this percentile of the bilateral score
            are classified as covers.

    Returns:
        Sorted list of cover-page indices (always includes 0).
    """
    signal = _bilateral_cosine_min(embeddings)
    threshold = float(np.percentile(signal, percentile))
    covers = set(int(i) for i in np.where(signal >= threshold)[0])
    covers.add(0)
    return sorted(covers)
```

- [ ] **Step 4.4: Run the tests and verify they pass**

Run:
```bash
source .venv-cuda/Scripts/activate && pytest eval/tests/test_scorer_dit.py -v
```

Expected: 3 passed

- [ ] **Step 4.5: Ruff check**

Run:
```bash
source .venv-cuda/Scripts/activate && ruff check eval/pixel_density/scorer_dit.py eval/tests/test_scorer_dit.py
```

Expected: 0 violations

- [ ] **Step 4.6: Commit**

```bash
git add eval/pixel_density/scorer_dit.py eval/tests/test_scorer_dit.py
git commit -m "feat(pixel_density): add DiT+cosine scorers (find_peaks, percentile)"
```

---

### Task 5: Batch benchmark runner for the 13 ART folders

**Files:**
- Create: `eval/pixel_density/benchmark_rio_bueno_dit.py`
- No test — this is a CLI reporting script, not library code.

**Rationale:** One standalone script that mirrors the ad-hoc Python we ran in this session, but using `score_dit_find_peaks` and `score_dit_percentile` with a small hyperparameter sweep. Writes a markdown report to `docs/superpowers/reports/`. This is the evidence we will use to make the Option-B/C decision.

- [ ] **Step 5.1: Implement the benchmark script**

Create `a:\PROJECTS\PDFoverseer\eval\pixel_density\benchmark_rio_bueno_dit.py`:

```python
"""Benchmark DiT+cosine scorers on the rio_bueno ART folders.

Compares each scorer + hyperparameter against the count embedded in each
folder name and writes a markdown report. Run from the project root:

    python eval/pixel_density/benchmark_rio_bueno_dit.py
"""

from __future__ import annotations

import io
import logging
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from eval.pixel_density.dit_embeddings import ensure_dit_embeddings  # noqa: E402
from eval.pixel_density.scorer_dit import (  # noqa: E402
    score_dit_find_peaks,
    score_dit_percentile,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

CORPUS_ROOT = Path("A:/informe mensual/MARZO/rio_bueno/7.- ART  Realizadas")
REPORT_DIR = Path("docs/superpowers/reports")

# Hyperparameter sweep — small and principled, not a grid-search for hyperopt.
FIND_PEAKS_GRID = [
    {"prominence": 0.05, "distance": 1},
    {"prominence": 0.1, "distance": 1},
    {"prominence": 0.1, "distance": 2},
    {"prominence": 0.2, "distance": 2},
    {"prominence": 0.3, "distance": 2},
]
PERCENTILE_GRID = [65.0, 70.0, 75.0, 80.0, 85.0]

# Baseline numbers from the 2026-04-11 session, for reference only.
BASELINE_RESCUE_C_MAE = 9.5
BASELINE_RESCUE_C_EXACT = 4


@dataclass
class FolderResult:
    name: str
    expected: int
    counted: int
    per_pdf: list[tuple[str, int]]


def _expected_from_folder(name: str) -> int | None:
    m = re.search(r"(\d+)\s*$", name)
    return int(m.group(1)) if m else None


def _unique_pdfs(folder: Path) -> list[Path]:
    pdfs = sorted(list(folder.glob("*.pdf")) + list(folder.glob("*.PDF")))
    seen: set[str] = set()
    unique: list[Path] = []
    for p in pdfs:
        key = str(p).lower()
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def run_scorer(
    scorer_name: str, params: dict, folders: list[Path]
) -> list[FolderResult]:
    results: list[FolderResult] = []
    for folder in folders:
        expected = _expected_from_folder(folder.name)
        if expected is None:
            continue
        per_pdf: list[tuple[str, int]] = []
        total = 0
        for pdf in _unique_pdfs(folder):
            embeddings = ensure_dit_embeddings(str(pdf))
            if scorer_name == "find_peaks":
                covers = score_dit_find_peaks(embeddings, **params)
            elif scorer_name == "percentile":
                covers = score_dit_percentile(embeddings, **params)
            else:
                raise ValueError(f"unknown scorer {scorer_name}")
            per_pdf.append((pdf.name, len(covers)))
            total += len(covers)
        results.append(
            FolderResult(
                name=folder.name, expected=expected, counted=total, per_pdf=per_pdf
            )
        )
    return results


def summarize(results: list[FolderResult]) -> tuple[int, float]:
    exact = sum(1 for r in results if r.counted == r.expected)
    mae = sum(abs(r.counted - r.expected) for r in results) / max(len(results), 1)
    return exact, mae


def format_report(
    all_runs: list[tuple[str, dict, list[FolderResult], int, float]]
) -> str:
    lines: list[str] = []
    lines.append(f"# DiT + Cosine benchmark — rio_bueno ART folders")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"Corpus: `{CORPUS_ROOT}`")
    lines.append("")
    lines.append("## Baseline (handcrafted 80-d + L2)")
    lines.append("")
    lines.append(
        f"- `scorer_rescue_c` — exact: {BASELINE_RESCUE_C_EXACT}/13, "
        f"MAE: {BASELINE_RESCUE_C_MAE}"
    )
    lines.append("")
    lines.append("## DiT + Cosine runs")
    lines.append("")
    lines.append("| Scorer | Params | Exact / 13 | MAE |")
    lines.append("|--------|--------|-----------:|----:|")
    for name, params, _results, exact, mae in all_runs:
        params_str = ", ".join(f"{k}={v}" for k, v in params.items())
        lines.append(f"| {name} | {params_str} | {exact} | {mae:.2f} |")
    lines.append("")
    lines.append("## Per-folder breakdown (best run)")
    lines.append("")
    # Best = highest exact, tiebreak lowest MAE
    all_runs_sorted = sorted(all_runs, key=lambda r: (-r[3], r[4]))
    best_name, best_params, best_results, best_exact, best_mae = all_runs_sorted[0]
    lines.append(
        f"Best: **{best_name}** with {best_params} — "
        f"exact {best_exact}/13, MAE {best_mae:.2f}"
    )
    lines.append("")
    lines.append("| Folder | Expected | Counted | Diff |")
    lines.append("|--------|---------:|--------:|-----:|")
    for r in best_results:
        diff = r.counted - r.expected
        lines.append(f"| {r.name} | {r.expected} | {r.counted} | {diff:+d} |")
    return "\n".join(lines)


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    if not CORPUS_ROOT.exists():
        logger.error("Corpus not found: %s", CORPUS_ROOT)
        return 1

    folders = [f for f in sorted(CORPUS_ROOT.iterdir()) if f.is_dir()]
    logger.info("Found %d folders in corpus", len(folders))

    all_runs: list[tuple[str, dict, list[FolderResult], int, float]] = []

    for params in FIND_PEAKS_GRID:
        logger.info("Running find_peaks with %s", params)
        results = run_scorer("find_peaks", params, folders)
        exact, mae = summarize(results)
        logger.info("  exact=%d/13  MAE=%.2f", exact, mae)
        all_runs.append(("find_peaks", params, results, exact, mae))

    for pct in PERCENTILE_GRID:
        params = {"percentile": pct}
        logger.info("Running percentile with %s", params)
        results = run_scorer("percentile", params, folders)
        exact, mae = summarize(results)
        logger.info("  exact=%d/13  MAE=%.2f", exact, mae)
        all_runs.append(("percentile", params, results, exact, mae))

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = (
        REPORT_DIR / f"{datetime.now():%Y-%m-%d}-dit-cosine-rio-bueno-benchmark.md"
    )
    report_path.write_text(format_report(all_runs), encoding="utf-8")
    logger.info("Wrote report: %s", report_path)

    # Print summary to stdout
    best = max(all_runs, key=lambda r: (r[3], -r[4]))
    print(
        f"BEST: {best[0]} {best[1]} — exact {best[3]}/13, MAE {best[4]:.2f}  "
        f"(baseline: exact {BASELINE_RESCUE_C_EXACT}/13, MAE {BASELINE_RESCUE_C_MAE})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5.2: Ruff check the new script**

Run:
```bash
source .venv-cuda/Scripts/activate && ruff check eval/pixel_density/benchmark_rio_bueno_dit.py
```

Expected: 0 violations

- [ ] **Step 5.3: Commit the script (before running it, so the commit reflects the tool, not the results)**

```bash
git add eval/pixel_density/benchmark_rio_bueno_dit.py
git commit -m "feat(pixel_density): add DiT+cosine benchmark runner for rio_bueno corpus"
```

---

## Chunk 4: Run the Experiment + Decision Gate

### Task 6: Run benchmark and collect results

**Files:**
- Output: `docs/superpowers/reports/YYYY-MM-DD-dit-cosine-rio-bueno-benchmark.md` (auto-generated)
- Output: `data/pixel_density/dit_cache/*.npz` (auto-generated, gitignored)

- [ ] **Step 6.1: Ensure `data/pixel_density/dit_cache/` is gitignored**

Check `a:\PROJECTS\PDFoverseer\.gitignore`. If `data/pixel_density/cache/` is already ignored (either explicitly or via a `data/` prefix), confirm `data/pixel_density/dit_cache/` is covered too. If not, add:

```
data/pixel_density/dit_cache/
```

Commit if changed:
```bash
git add .gitignore && git commit -m "chore: gitignore DiT embedding cache"
```

- [ ] **Step 6.2: Run the benchmark**

Run (long-running, ~10-25 minutes depending on first-time model download + embedding all ~54 PDFs ≈ 2300 pages):

```bash
source .venv-cuda/Scripts/activate && python eval/pixel_density/benchmark_rio_bueno_dit.py
```

Expected: prints `BEST:` line at the end and writes the report to `docs/superpowers/reports/`.

- [ ] **Step 6.3: Read the generated report**

Open `docs/superpowers/reports/<date>-dit-cosine-rio-bueno-benchmark.md`. Record the best scorer + params, the exact count, and the MAE. These are the three numbers that matter for the decision gate.

- [ ] **Step 6.4: Commit the report (results, not tool, are the artifact here)**

```bash
git add docs/superpowers/reports/*dit-cosine-rio-bueno-benchmark.md
git commit -m "docs(pixel_density): record DiT+cosine benchmark on rio_bueno corpus"
```

---

### Task 7: Decision gate — evaluate results vs baseline

**This is a checkpoint, not a code step.** Do not write any more code before making this decision explicit and reporting to the user.

Baseline to beat: `rescue_c` with **MAE=9.5** and **4/13 exact** on the same 13 folders.

- [ ] **Step 7.1: Classify the result into one of three buckets**

Apply the following criteria to the **best** DiT run from the report:

| Bucket | Criteria | Meaning |
|--------|----------|---------|
| **Strong positive** | MAE ≤ 4.0 **and** exact ≥ 8/13 | DiT embeddings substantially beat handcrafted features. The feature-quality hypothesis was correct. |
| **Marginal** | 4.0 < MAE ≤ 8.0, or exact 5–7/13 | Some improvement, but not enough to trust as a primary detector. Framing is partially the bottleneck. |
| **Negative / flat** | MAE > 8.0 **or** exact ≤ 4/13 | No meaningful improvement over handcrafted. The bilateral framing — not the features — is the bottleneck. |

- [ ] **Step 7.2: Report the classification to the user and wait for direction**

Do NOT proceed to Task 8 automatically. Write a short message to the user with:

1. The best DiT scorer, params, exact, MAE.
2. The bucket classification.
3. The recommended next step based on the bucket:
   - **Strong positive** → propose scaling up: integrate into the main inference pipeline as a cover-detection signal feeding Dempster-Shafer.
   - **Marginal** → propose one more experiment: try DiT+cosine fused with handcrafted features (late fusion at the scoring stage, not feature concatenation).
   - **Negative / flat** → propose moving to Option C (trained binary classifier head on DiT embeddings, requires a small labeled set — see Task 8).

Wait for user confirmation before proceeding.

---

## Chunk 5: Conditional — Option C Scaffold (only if Task 7 classifies as Negative/Flat)

### Task 8: Prepare Option C scoping document (no implementation)

**Files:**
- Create: `docs/superpowers/plans/YYYY-MM-DD-option-c-scoping.md`

**Rationale:** Option C (trained classifier) is meaningfully different in shape from Option B and deserves its own plan with its own decomposition. But we can lock in the key scoping decisions *now* while the context is fresh, so the eventual Option C plan is faster to write. This task is a scoping document, **not** an implementation.

- [ ] **Step 8.1: Decide only if Task 7 returned Negative/Flat**

If Task 7 returned Strong positive or Marginal, **skip Task 8 entirely.** Do not create the scoping doc.

- [ ] **Step 8.2: Draft the Option C scoping document**

Create `a:\PROJECTS\PDFoverseer\docs\superpowers\plans\<YYYY-MM-DD>-option-c-scoping.md` covering:

1. **Problem recap** — one paragraph: why Option B was not enough, what numbers motivated the move.
2. **Proposed architecture** — two options for Option C to be resolved with the user:
   - (C1) Train a small MLP head (`768 → 64 → 1`) on top of frozen DiT embeddings.
   - (C2) Fine-tune DiT itself end-to-end with a classification head.
   Flag that C1 is strictly cheaper in compute and labeled data, and is the recommended starting point.
3. **Data requirement** — estimate labeling cost. Rough target: ~500–1000 labeled pages (cover / not-cover), stratified across folders.
4. **Weak-supervision alternative** — describe the bootstrap: use the folder-name counts as a constraint ("this folder should have exactly N covers") and optimize a weakly-supervised loss. Flag that this is more complex and should be a fallback.
5. **Evaluation plan** — same 13 rio_bueno folders, plus held-out validation on a subset of ART_674 that was **not** used to tune the current rescue_c. This prevents the same overfitting problem we already diagnosed.
6. **Open questions for the user** — at least three questions the user must answer before Option C can be planned in detail (e.g., "are we OK labeling 500 pages by hand?", "should the classifier run at inference time or only at evaluation time?", "what latency budget does the pipeline allow per page?").

The scoping document is the handoff artifact for a future planning session, not a prescription.

- [ ] **Step 8.3: Commit the scoping document**

```bash
git add docs/superpowers/plans/*option-c-scoping.md
git commit -m "docs(pixel_density): scope Option C (trained classifier) as follow-up"
```

- [ ] **Step 8.4: Stop and report to the user**

Do NOT start implementing Option C. Tell the user:
1. Option B result (the three numbers).
2. Scoping document path.
3. Ask: "¿Avanzamos con un plan detallado para Option C ahora o lo dejamos como follow-up?"

---

## Out-of-scope (explicitly)

- **Fine-tuning DiT.** We use the preloaded model as-is. Fine-tuning is Option C territory.
- **RVL-CDIP or other benchmarks.** We only measure on the same 13 rio_bueno folders used in the session baseline. Broader validation comes *after* a positive result.
- **Integration with the main inference pipeline or Dempster-Shafer fusion.** That is a separate plan triggered only by a Strong-positive result in Task 7.
- **Multi-model comparison.** We test DiT-base only. DiT-large, LayoutLMv3, Donut are follow-ups, not part of this experiment.
- **Text / OCR features.** This is deliberately a pixel-only experiment — we want to isolate whether richer visual features alone move the needle.

## Known risks

1. **DiT-base first download** (~340 MB) requires internet on the machine where Task 1 runs. If offline, Task 1.4 will fail — surface to the user, don't retry silently.
2. **GTX 1080 memory** is 8 GB. `BATCH_SIZE = 16` for 224×224 RGB inputs should leave plenty of headroom, but if OOM occurs, reduce to 8 in `dit_embeddings.py` and re-run. Do not switch to CPU silently.
3. **Grayscale → RGB via `.convert('RGB')`** replicates the single channel to all three. This is standard for DiT but may lose information that a true 3-channel preprocessing would preserve. Flag as a possible cause if the result is unexpectedly flat.
4. **The corpus root contains a double space** in `7.- ART  Realizadas`. Do not "fix" it — the exact path string is load-bearing.
5. **Per-folder counts embedded in the folder name assume the sum across all PDFs equals the total.** This was verified informally in the 2026-04-11 session but is not ground truth per-page — it's a noisy oracle. Do not over-interpret ±2 differences as meaningful.
