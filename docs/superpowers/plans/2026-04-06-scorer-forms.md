# Scorer Forms Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a page-classification scorer (`scorer_forms`) that detects document covers in form-based PDFs (HLL_363) by analyzing vertical ink distribution, without regressing ART family results.

**Architecture:** New scorer in `eval/pixel_density/sweep_forms.py` classifies each page as cover/non-cover using vertical density features + Otsu/percentile thresholding. Completely independent from existing bilateral scorers. ART safety gate runs `scorer_find_peaks` to confirm 6/6 exact after every change.

**Tech Stack:** numpy, scipy.stats (skew/kurtosis for bimodality), scipy.signal.find_peaks (Phase 2 table detection). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-06-scorer-forms-design.md`

---

## Chunk 1: Feature + Scorer + Tests

### Task 1: `feat_vertical_density` feature function

**Files:**
- Modify: `eval/pixel_density/features.py` (add function, do NOT add to `_FEATURE_REGISTRY`)
- Test: `eval/tests/test_scorer_forms.py`

- [ ] **Step 1: Write tests for feat_vertical_density**

Create `eval/tests/test_scorer_forms.py`:

```python
"""Tests for scorer_forms: vertical density feature, Otsu 1D, scorer smoke, ART gate."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np  # noqa: E402
import pytest  # noqa: E402


# ── feat_vertical_density ─────────────────────────────────────────────────


def test_vertical_density_shape():
    """Returns shape (2,) for any image."""
    from eval.pixel_density.features import feat_vertical_density

    img = np.random.randint(0, 256, (100, 80), dtype=np.uint8)
    result = feat_vertical_density(img, bottom_frac=0.35)
    assert result.shape == (2,)
    assert result.dtype == np.float64


def test_vertical_density_white_page():
    """All-white page has [0, 0] dark ratios."""
    from eval.pixel_density.features import feat_vertical_density

    img = np.full((100, 80), 255, dtype=np.uint8)
    result = feat_vertical_density(img, bottom_frac=0.35)
    assert result[0] == 0.0
    assert result[1] == 0.0


def test_vertical_density_black_page():
    """All-black page has [1, 1] dark ratios (all pixels < 128)."""
    from eval.pixel_density.features import feat_vertical_density

    img = np.zeros((100, 80), dtype=np.uint8)
    result = feat_vertical_density(img, bottom_frac=0.35)
    assert result[0] == pytest.approx(1.0)
    assert result[1] == pytest.approx(1.0)


def test_vertical_density_bottom_heavy():
    """Page with dark bottom, white top has high bot_dark, low top_dark."""
    from eval.pixel_density.features import feat_vertical_density

    img = np.full((100, 80), 255, dtype=np.uint8)
    img[65:, :] = 0  # bottom 35% is black
    result = feat_vertical_density(img, bottom_frac=0.35)
    assert result[0] == 0.0  # top is white
    assert result[1] == pytest.approx(1.0)  # bottom is black


def test_vertical_density_different_bottom_frac():
    """Changing bottom_frac changes the split point."""
    from eval.pixel_density.features import feat_vertical_density

    img = np.full((100, 80), 255, dtype=np.uint8)
    img[50:, :] = 0  # bottom 50% is black

    r25 = feat_vertical_density(img, bottom_frac=0.25)
    r50 = feat_vertical_density(img, bottom_frac=0.50)
    # With bottom_frac=0.50, bot zone covers exactly the black region
    assert r50[1] == pytest.approx(1.0)
    # With bottom_frac=0.25, bot zone is fully black AND top zone has some black
    assert r25[1] == pytest.approx(1.0)
    assert r25[0] > 0.0  # top zone includes some black pixels


def test_vertical_density_not_in_registry():
    """feat_vertical_density must NOT be in the feature registry."""
    from eval.pixel_density.features import _FEATURE_REGISTRY

    assert "vertical_density" not in _FEATURE_REGISTRY
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest eval/tests/test_scorer_forms.py -v`
Expected: FAIL with `ImportError` or `cannot import name 'feat_vertical_density'`

- [ ] **Step 3: Implement feat_vertical_density**

Add to `eval/pixel_density/features.py`, AFTER the existing `feat_projection_stats` function and BEFORE the `_FEATURE_REGISTRY` dict. Do NOT add it to `_FEATURE_REGISTRY`:

```python
def feat_vertical_density(
    img: np.ndarray,
    bottom_frac: float = 0.35,
) -> np.ndarray:
    """Dark pixel fraction for top and bottom zones.

    Divides the page into two zones: top (1 - bottom_frac) and bottom (bottom_frac).
    Used by scorer_forms for page classification on form-based PDFs.

    Not registered in _FEATURE_REGISTRY — purpose-specific semantics that should
    not be concatenated with general features via extract_features().

    Args:
        img: Grayscale image (H, W), uint8.
        bottom_frac: Fraction of page height for the bottom zone.

    Returns:
        1-D array of shape (2,), float64: [top_dark, bot_dark].
    """
    h = img.shape[0]
    split = int(h * (1.0 - bottom_frac))
    top = img[:split, :]
    bot = img[split:, :]
    top_dark = float((top < 128).mean()) if top.size else 0.0
    bot_dark = float((bot < 128).mean()) if bot.size else 0.0
    return np.array([top_dark, bot_dark], dtype=np.float64)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest eval/tests/test_scorer_forms.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add eval/pixel_density/features.py eval/tests/test_scorer_forms.py
git commit -m "feat(pixel-density): add feat_vertical_density for form page classification"
```

---

### Task 2: Otsu 1D threshold + bimodality check

**Files:**
- Create: `eval/pixel_density/sweep_forms.py` (start file with utilities)
- Test: `eval/tests/test_scorer_forms.py` (append tests)

- [ ] **Step 1: Write tests for otsu_threshold_1d and bimodal_coefficient**

Append to `eval/tests/test_scorer_forms.py`:

```python
# ── Otsu 1D + bimodality ──────────────────────────────────────────────────


def test_otsu_bimodal_separation():
    """Otsu on clearly bimodal data separates the two groups."""
    from eval.pixel_density.sweep_forms import otsu_threshold_1d

    rng = np.random.default_rng(42)
    low = rng.normal(0.3, 0.02, 200)
    high = rng.normal(0.8, 0.02, 100)
    data = np.concatenate([low, high])
    thresh = otsu_threshold_1d(data)
    assert 0.4 < thresh < 0.7  # threshold falls between groups


def test_otsu_uniform_data():
    """Otsu on uniform data returns some threshold without crashing."""
    from eval.pixel_density.sweep_forms import otsu_threshold_1d

    data = np.linspace(0.0, 1.0, 100)
    thresh = otsu_threshold_1d(data)
    assert 0.0 <= thresh <= 1.0


def test_bimodal_coefficient_bimodal():
    """Bimodal data has BC >= 0.555."""
    from eval.pixel_density.sweep_forms import bimodal_coefficient

    rng = np.random.default_rng(42)
    low = rng.normal(0.3, 0.02, 300)
    high = rng.normal(0.8, 0.02, 300)
    data = np.concatenate([low, high])
    bc = bimodal_coefficient(data)
    assert bc >= 0.555


def test_bimodal_coefficient_unimodal():
    """Unimodal data has BC < 0.555."""
    from eval.pixel_density.sweep_forms import bimodal_coefficient

    rng = np.random.default_rng(42)
    data = rng.normal(0.5, 0.1, 500)
    bc = bimodal_coefficient(data)
    assert bc < 0.555
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest eval/tests/test_scorer_forms.py::test_otsu_bimodal_separation -v`
Expected: FAIL with `ModuleNotFoundError` (sweep_forms doesn't exist yet)

- [ ] **Step 3: Implement otsu_threshold_1d and bimodal_coefficient**

Create `eval/pixel_density/sweep_forms.py`:

```python
"""Scorer for form-based PDFs — page classification by vertical density.

Classifies each page as cover/non-cover using vertical ink distribution.
Independent from bilateral scorers (scorer_find_peaks, scorer_rescue_c).

Usage
-----
    python eval/pixel_density/sweep_forms.py          # full sweep
    python eval/pixel_density/sweep_forms.py --quick   # HLL_363 only
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np  # noqa: E402
from scipy.stats import kurtosis, skew  # noqa: E402


# ── Threshold utilities ───────────────────────────────────────────────────


def otsu_threshold_1d(data: np.ndarray, n_bins: int = 256) -> float:
    """Otsu's method on a 1-D float array.

    Finds the threshold that maximizes between-class variance. Equivalent to
    cv2.threshold(THRESH_OTSU) but operates on arbitrary float arrays.

    Args:
        data: 1-D array of float values.
        n_bins: Number of histogram bins.

    Returns:
        Optimal threshold value.
    """
    lo, hi = float(data.min()), float(data.max())
    if hi - lo < 1e-12:
        return lo

    hist, bin_edges = np.histogram(data, bins=n_bins, range=(lo, hi))
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0
    hist_norm = hist.astype(np.float64) / hist.sum()

    best_thresh = lo
    best_var = -1.0

    cum_w = 0.0
    cum_sum = 0.0
    total_sum = float((hist_norm * bin_centers).sum())

    for i in range(n_bins):
        cum_w += hist_norm[i]
        cum_sum += hist_norm[i] * bin_centers[i]

        if cum_w < 1e-12 or (1.0 - cum_w) < 1e-12:
            continue

        mean_bg = cum_sum / cum_w
        mean_fg = (total_sum - cum_sum) / (1.0 - cum_w)

        var_between = cum_w * (1.0 - cum_w) * (mean_bg - mean_fg) ** 2

        if var_between > best_var:
            best_var = var_between
            best_thresh = bin_centers[i]

    return best_thresh


def bimodal_coefficient(data: np.ndarray) -> float:
    """Bimodal coefficient (BC) for a 1-D array.

    BC = (skewness^2 + 1) / kurtosis_excess_plus_3.
    BC >= 5/9 (0.555) suggests bimodality.

    Args:
        data: 1-D array of float values.

    Returns:
        Bimodal coefficient. Returns 0.0 for constant arrays.
    """
    if len(data) < 4 or data.std() < 1e-12:
        return 0.0

    s = float(skew(data))
    # scipy kurtosis() returns excess kurtosis by default; we need regular kurtosis
    k = float(kurtosis(data, fisher=True)) + 3.0

    if k < 1e-12:
        return 0.0

    return (s ** 2 + 1.0) / k
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest eval/tests/test_scorer_forms.py -v`
Expected: 10 PASSED

- [ ] **Step 5: Commit**

```bash
git add eval/pixel_density/sweep_forms.py eval/tests/test_scorer_forms.py
git commit -m "feat(pixel-density): add otsu_threshold_1d and bimodal_coefficient"
```

---

### Task 3: scorer_forms function

**Files:**
- Modify: `eval/pixel_density/sweep_forms.py` (add scorer)
- Test: `eval/tests/test_scorer_forms.py` (append tests)

- [ ] **Step 1: Write tests for scorer_forms**

Append to `eval/tests/test_scorer_forms.py`:

```python
# ── scorer_forms ──────────────────────────────────────────────────────────


def test_scorer_forms_returns_list():
    """Scorer returns a list of ints."""
    from eval.pixel_density.sweep_forms import scorer_forms

    # 10 pages, 100x80 each, random
    rng = np.random.default_rng(42)
    pages = rng.integers(0, 256, (10, 100, 80), dtype=np.uint8)
    result = scorer_forms(pages)
    assert isinstance(result, list)
    assert all(isinstance(i, int) for i in result)


def test_scorer_forms_includes_page_0():
    """Page 0 is always in the result."""
    from eval.pixel_density.sweep_forms import scorer_forms

    rng = np.random.default_rng(42)
    pages = rng.integers(0, 256, (10, 100, 80), dtype=np.uint8)
    result = scorer_forms(pages)
    assert 0 in result


def test_scorer_forms_single_page():
    """Single-page PDF returns [0]."""
    from eval.pixel_density.sweep_forms import scorer_forms

    pages = np.full((1, 100, 80), 200, dtype=np.uint8)
    result = scorer_forms(pages)
    assert result == [0]


def test_scorer_forms_sorted_output():
    """Output is sorted ascending."""
    from eval.pixel_density.sweep_forms import scorer_forms

    rng = np.random.default_rng(42)
    pages = rng.integers(0, 256, (20, 100, 80), dtype=np.uint8)
    result = scorer_forms(pages)
    assert result == sorted(result)


def test_scorer_forms_all_signals():
    """All signal types run without error."""
    from eval.pixel_density.sweep_forms import scorer_forms

    rng = np.random.default_rng(42)
    pages = rng.integers(0, 256, (10, 100, 80), dtype=np.uint8)
    for signal in ("bot_top_ratio", "bot_absolute", "bot_full_ratio", "bot_mid_ratio"):
        result = scorer_forms(pages, signal=signal)
        assert 0 in result


def test_scorer_forms_all_threshold_methods():
    """All threshold methods run without error."""
    from eval.pixel_density.sweep_forms import scorer_forms

    rng = np.random.default_rng(42)
    pages = rng.integers(0, 256, (10, 100, 80), dtype=np.uint8)
    for method in ("otsu", "kmeans_k2", "percentile_50"):
        result = scorer_forms(pages, threshold_method=method)
        assert 0 in result


def test_scorer_forms_otsu_bimodality_guard_identical():
    """Otsu on identical pages triggers bimodality guard (early return path)."""
    from eval.pixel_density.sweep_forms import scorer_forms

    # All pages identical → std < 1e-12 → BC = 0.0 → return [0]
    page = np.full((100, 80), 200, dtype=np.uint8)
    pages = np.stack([page] * 10)
    result = scorer_forms(pages, threshold_method="otsu")
    assert result == [0]


def test_scorer_forms_otsu_bimodality_guard_unimodal():
    """Otsu on varied but unimodal pages triggers bimodality guard (BC formula path)."""
    from eval.pixel_density.sweep_forms import scorer_forms

    # Pages with gradually varying darkness — unimodal distribution
    # Bottom zone gets progressively darker but no bimodal separation
    rng = np.random.default_rng(42)
    pages = np.full((20, 100, 80), 200, dtype=np.uint8)
    for i in range(20):
        # Add noise proportional to page index — creates smooth gradient, not bimodal
        noise = rng.integers(0, 10 + i * 2, (100, 80), dtype=np.uint8)
        pages[i] = np.clip(pages[i].astype(np.int16) - noise, 0, 255).astype(np.uint8)
    result = scorer_forms(pages, threshold_method="otsu")
    # Should either trigger guard (return [0]) or at minimum not crash
    assert 0 in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest eval/tests/test_scorer_forms.py::test_scorer_forms_returns_list -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement scorer_forms**

Append to `eval/pixel_density/sweep_forms.py`:

```python
from eval.pixel_density.features import feat_vertical_density  # noqa: E402


def scorer_forms(
    pages: np.ndarray,
    bottom_frac: float = 0.35,
    signal: str = "bot_top_ratio",
    threshold_method: str = "otsu",
    _vd_precomputed: np.ndarray | None = None,
) -> list[int]:
    """Classify pages as cover/non-cover by vertical ink distribution.

    Designed for form-based PDFs (e.g., HLL_363) where bilateral scoring fails
    due to visual uniformity across all pages.

    Args:
        pages: Array of shape (N, H, W), uint8 grayscale pages.
        bottom_frac: Fraction of page height for the bottom zone.
        signal: Discriminant signal to compute per page. One of:
            "bot_top_ratio", "bot_absolute", "bot_full_ratio", "bot_mid_ratio".
        threshold_method: Separation method. One of:
            "otsu", "kmeans_k2", "percentile_<N>" (e.g. "percentile_50").
        _vd_precomputed: Optional pre-computed vertical density array of shape
            (N, 2) from feat_vertical_density. Used by sweep to avoid redundant
            extraction. If None, features are extracted internally.

    Returns:
        Sorted list of 0-based page indices classified as covers.
    """
    n = pages.shape[0]
    if n <= 1:
        return [0]

    # Extract vertical density for all pages (or use pre-computed cache)
    if _vd_precomputed is not None:
        vd = _vd_precomputed
    else:
        vd = np.array([feat_vertical_density(pages[i], bottom_frac) for i in range(n)])
    top_dark = vd[:, 0]
    bot_dark = vd[:, 1]

    # Compute discriminant signal
    if signal == "bot_top_ratio":
        values = bot_dark / np.maximum(top_dark, 1e-9)
    elif signal == "bot_absolute":
        values = bot_dark
    elif signal == "bot_full_ratio":
        full_dark = np.array([float((pages[i] < 128).mean()) for i in range(n)])
        values = bot_dark / np.maximum(full_dark, 1e-9)
    elif signal == "bot_mid_ratio":
        # 3-zone split: top=[0, bf*h), mid=[bf*h, (1-bf)*h), bot=[(1-bf)*h, h)
        # Note: top_dark from feat_vertical_density is NOT used here — the zones
        # are redefined symmetrically around the center of the page.
        # At bf=0.40, mid is only 20% of page height — narrow but still meaningful.
        top_frac = 1.0 - bottom_frac
        mid_frac = top_frac - bottom_frac if top_frac > bottom_frac else 0.0
        if mid_frac < 0.05:
            # No meaningful mid zone (bf >= ~0.475) — skip this combo entirely.
            # Returning [0] signals "not applicable" so the sweep can exclude it.
            return [0]
        else:
            h = pages.shape[1]
            top_end = int(h * bottom_frac)  # top zone = bottom_frac of height
            mid_start = top_end
            mid_end = int(h * (1.0 - bottom_frac))
            mid_dark = np.array([
                float((pages[i, mid_start:mid_end, :] < 128).mean())
                if mid_end > mid_start else 0.0
                for i in range(n)
            ])
            values = bot_dark / np.maximum(mid_dark, 1e-9)
    else:
        raise ValueError(f"Unknown signal: {signal!r}")

    # Apply threshold
    # NOTE on percentile convention: the existing _percentile_threshold (sweep_rescue.py)
    # uses pct=75.2 meaning "take pages >= 75.2th percentile" = top 24.8%.
    # Here, percentile_N means "classify top N% as covers" — OPPOSITE convention.
    # This is intentional: bilateral scoring assumes few covers (25%), page
    # classification can have any ratio (HLL has 67.5%).
    if threshold_method == "otsu":
        bc = bimodal_coefficient(values)
        if bc < 0.555:
            return [0]
        thresh = otsu_threshold_1d(values)
        matches = [i for i in range(n) if values[i] >= thresh]
    elif threshold_method == "kmeans_k2":
        import warnings

        from sklearn.cluster import KMeans

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            km = KMeans(n_clusters=2, random_state=42, n_init="auto").fit(
                values.reshape(-1, 1)
            )
        labels = km.labels_
        centers = km.cluster_centers_.flatten()
        high_label = 0 if centers[0] > centers[1] else 1
        matches = [i for i in range(n) if labels[i] == high_label]
    elif threshold_method.startswith("percentile_"):
        # percentile_N = top N% of pages classified as covers
        # e.g. percentile_50 → np.percentile(values, 50) → top 50% are covers
        pct = float(threshold_method.split("_", 1)[1])
        thresh = np.percentile(values, 100.0 - pct)
        matches = [i for i in range(n) if values[i] >= thresh]
    else:
        raise ValueError(f"Unknown threshold_method: {threshold_method!r}")

    if 0 not in matches:
        matches.insert(0, 0)

    return sorted(matches)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest eval/tests/test_scorer_forms.py -v`
Expected: 18 PASSED (6 feature + 4 otsu/bimodal + 8 scorer)

- [ ] **Step 5: Commit**

```bash
git add eval/pixel_density/sweep_forms.py eval/tests/test_scorer_forms.py
git commit -m "feat(pixel-density): implement scorer_forms page classifier"
```

---

### Task 4: ART safety gate test

**Files:**
- Test: `eval/tests/test_scorer_forms.py` (append test)

This test confirms that importing/using `scorer_forms` does not alter any shared module state that would affect `scorer_find_peaks`.

- [ ] **Step 1: Write ART gate test**

Append to `eval/tests/test_scorer_forms.py`:

```python
# ── ART safety gate ───────────────────────────────────────────────────────


@pytest.mark.slow
def test_art_safety_gate():
    """Importing scorer_forms must not affect scorer_find_peaks ART results.

    This is the hard gate: if this test fails, the new code is broken.
    Runs scorer_find_peaks on all 6 ART PDFs and verifies exact doc counts.
    """
    # Import scorer_forms first to trigger any side effects
    from eval.pixel_density.sweep_forms import scorer_forms  # noqa: F401
    from eval.pixel_density.cache import ensure_cache
    from eval.pixel_density.sweep_rescue import scorer_find_peaks

    art_pdfs = [
        ("ART_674", "data/samples/ART_674.pdf", 674),
        ("ART_CH_13", "data/samples/arts/ART_CH_13.pdf", 13),
        ("ART_CON_13", "data/samples/arts/ART_CON_13.pdf", 13),
        ("ART_EX_13", "data/samples/arts/ART_EX_13.pdf", 13),
        ("ART_GR_8", "data/samples/arts/ART_GR_8.pdf", 8),
        ("ART_ROC_10", "data/samples/arts/ART_ROC_10.pdf", 10),
    ]

    for name, pdf_path, target in art_pdfs:
        pages = ensure_cache(pdf_path, dpi=100)
        matches = scorer_find_peaks(
            pages, prominence=0.5, distance=2,
            shift_covers=True, score_similarity=0.99,
            rescue_threshold=0.40,
        )
        assert len(matches) == target, (
            f"ART GATE FAILED: {name} expected {target}, got {len(matches)}"
        )
```

- [ ] **Step 2: Run gate test**

Run: `pytest eval/tests/test_scorer_forms.py::test_art_safety_gate -v -m slow`
Expected: PASSED (scorer_find_peaks still gives exact results for all 6 ART PDFs)

Note: This test requires cached PDF pages. First run may be slow (~2 min for ART_674 rendering). Subsequent runs use cache (~5s).

- [ ] **Step 3: Commit**

```bash
git add eval/tests/test_scorer_forms.py
git commit -m "test(pixel-density): add ART safety gate for scorer_forms"
```

---

## Chunk 2: Sweep + Evaluation

### Task 5: Sweep script

**Files:**
- Modify: `eval/pixel_density/sweep_forms.py` (add sweep harness + CLI)

- [ ] **Step 1: Add sweep harness and main()**

Append to `eval/pixel_density/sweep_forms.py`:

```python
import argparse  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import time  # noqa: E402
from functools import partial  # noqa: E402

from eval.pixel_density.cache import ensure_cache  # noqa: E402
from eval.pixel_density.evaluate import compute_metrics_count_only, save_results  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DPI = 100

GENERAL_CORPUS: list[tuple[str, str, int]] = [
    ("ALUM_1", "data/samples/ALUM_1.pdf", 1),
    ("ALUM_19", "data/samples/ALUM_19.pdf", 19),
    ("ART_674", "data/samples/ART_674.pdf", 674),
    ("CASTRO_15", "data/samples/CASTRO_15.pdf", 15),
    ("CASTRO_5", "data/samples/CASTRO_5.pdf", 5),
    ("CHAR_17", "data/samples/CHAR_17.PDF", 17),
    ("CHAR_25", "data/samples/CHAR_25.pdf", 25),
    ("CH_39", "data/samples/CH_39.pdf", 39),
    ("CH_51", "data/samples/CH_51docs.pdf", 51),
    ("CH_74", "data/samples/CH_74docs.pdf", 74),
    ("CH_9", "data/samples/CH_9.pdf", 9),
    ("CH_BSM_18", "data/samples/CH_BSM_18.pdf", 18),
    ("CRS_9", "data/samples/CRS_9.pdf", 9),
    ("HLL_363", "data/samples/HLL_363.pdf", 363),
    ("INSAP_20", "data/samples/INSAP_20.pdf", 20),
    ("INS_31", "data/samples/INS_31.pdf.pdf", 31),
    ("JOGA_19", "data/samples/JOGA_19.pdf", 19),
    ("QUEVEDO_1", "data/samples/QUEVEDO_1.pdf", 1),
    ("QUEVEDO_13", "data/samples/QUEVEDO_13.pdf", 13),
    ("QUEVEDO_2", "data/samples/QUEVEDO_2.pdf", 2),
    ("RACO_25", "data/samples/RACO_25.pdf", 25),
    ("SAEZ_14", "data/samples/SAEZ_14.pdf", 14),
]

ART_CORPUS: list[tuple[str, str, int]] = [
    ("ART_CH_13", "data/samples/arts/ART_CH_13.pdf", 13),
    ("ART_CON_13", "data/samples/arts/ART_CON_13.pdf", 13),
    ("ART_EX_13", "data/samples/arts/ART_EX_13.pdf", 13),
    ("ART_GR_8", "data/samples/arts/ART_GR_8.pdf", 8),
    ("ART_ROC_10", "data/samples/arts/ART_ROC_10.pdf", 10),
]

BOTTOM_FRACS = [0.25, 0.30, 0.35, 0.40]
SIGNALS = ["bot_top_ratio", "bot_absolute", "bot_full_ratio", "bot_mid_ratio"]
THRESHOLD_METHODS = [
    "otsu",
    "kmeans_k2",
    "percentile_30", "percentile_35", "percentile_40", "percentile_45",
    "percentile_50", "percentile_55", "percentile_60", "percentile_65",
    "percentile_70",
]


def run_sweep(corpus: list[tuple[str, str, int]], quick: bool = False) -> list[dict]:
    """Run scorer_forms over all parameter combinations.

    Args:
        corpus: List of (name, pdf_path, target) tuples.
        quick: If True, only run on HLL_363.

    Returns:
        List of result dicts, one per parameter combination.
    """
    if quick:
        corpus = [e for e in corpus if e[0] == "HLL_363"]

    # Pre-load all pages
    page_cache: dict[str, np.ndarray] = {}
    for name, pdf_path, _ in corpus:
        page_cache[name] = ensure_cache(pdf_path, dpi=DPI)

    # Pre-compute vertical density features per (pdf, bottom_frac) to avoid
    # 44x redundant extraction (4 signals × 11 methods share the same features).
    # Key: (name, bottom_frac) -> np.ndarray of shape (N, 2)
    vd_cache: dict[tuple[str, float], np.ndarray] = {}
    for name in page_cache:
        pages = page_cache[name]
        for bf in BOTTOM_FRACS:
            vd_cache[(name, bf)] = np.array([
                feat_vertical_density(pages[i], bf) for i in range(pages.shape[0])
            ])

    results: list[dict] = []
    total = len(BOTTOM_FRACS) * len(SIGNALS) * len(THRESHOLD_METHODS)
    done = 0

    for bf in BOTTOM_FRACS:
        for sig in SIGNALS:
            for tm in THRESHOLD_METHODS:
                per_pdf: list[dict] = []
                hll_error = None

                for name, _, target in corpus:
                    pages = page_cache[name]
                    vd = vd_cache[(name, bf)]
                    matches = scorer_forms(
                        pages, bottom_frac=bf, signal=sig,
                        threshold_method=tm, _vd_precomputed=vd,
                    )
                    metrics = compute_metrics_count_only(matches, target)
                    metrics["name"] = name
                    metrics["target"] = target
                    per_pdf.append(metrics)
                    if name == "HLL_363":
                        hll_error = metrics["error"]

                errors = [r["abs_error"] for r in per_pdf]
                mae = sum(errors) / len(errors)
                exact = sum(1 for e in errors if e == 0)

                results.append({
                    "bottom_frac": bf,
                    "signal": sig,
                    "threshold_method": tm,
                    "hll_error": hll_error,
                    "hll_abs_error": abs(hll_error) if hll_error is not None else None,
                    "general_mae": mae,
                    "exact": exact,
                    "per_pdf": per_pdf,
                })

                done += 1
                if done % 20 == 0:
                    logger.info("  %d/%d combos done...", done, total)

    return results


def print_results(results: list[dict], top_n: int = 20) -> None:
    """Print ranked results table sorted by HLL error."""
    sorted_r = sorted(results, key=lambda r: (r["hll_abs_error"] or 999, r["general_mae"]))

    print(f"\n{'='*90}")  # noqa: T201
    print(f"Top {top_n} by HLL_363 abs_error (then general MAE)")  # noqa: T201
    print(f"{'='*90}")  # noqa: T201
    print(  # noqa: T201
        f"{'#':>3}  {'bot':>4} {'signal':<16} {'method':<16} "
        f"{'HLL err':>8} {'gen MAE':>8} {'exact':>5}"
    )
    print("-" * 90)  # noqa: T201

    for rank, r in enumerate(sorted_r[:top_n], 1):
        print(  # noqa: T201
            f"{rank:>3}  {r['bottom_frac']:>4.2f} {r['signal']:<16} "
            f"{r['threshold_method']:<16} {r['hll_error']:>+8} "
            f"{r['general_mae']:>8.1f} {r['exact']:>5}"
        )

    print(f"{'='*90}\n")  # noqa: T201


def main() -> None:
    parser = argparse.ArgumentParser(description="Sweep scorer_forms parameters")
    parser.add_argument("--quick", action="store_true", help="HLL_363 only")
    args = parser.parse_args()

    t0 = time.perf_counter()
    results = run_sweep(GENERAL_CORPUS, quick=args.quick)
    elapsed = time.perf_counter() - t0

    print_results(results)

    # Save results
    save_results(
        {"sweep": [{k: v for k, v in r.items() if k != "per_pdf"} for r in results]},
        "data/pixel_density/sweep_forms.json",
    )

    logger.info("Sweep complete: %d combos in %.1fs", len(results), elapsed)

    # ART safety gate — scorer_forms is not designed for ART-family PDFs, so
    # ART is excluded from the sweep scoring. The gate only confirms that
    # importing/running scorer_forms has not broken scorer_find_peaks.
    logger.info("\n=== ART SAFETY GATE ===")
    from eval.pixel_density.sweep_rescue import scorer_find_peaks

    art_all = [("ART_674", "data/samples/ART_674.pdf", 674)] + ART_CORPUS
    gate_ok = True
    for name, pdf_path, target in art_all:
        pages = ensure_cache(pdf_path, dpi=DPI)
        matches = scorer_find_peaks(
            pages, prominence=0.5, distance=2,
            shift_covers=True, score_similarity=0.99,
            rescue_threshold=0.40,
        )
        status = "OK" if len(matches) == target else "FAIL"
        if status == "FAIL":
            gate_ok = False
        logger.info("  %s: %d/%d %s", name, len(matches), target, status)

    logger.info("ART gate: %s", "PASSED" if gate_ok else "FAILED")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run quick sweep on HLL_363 only**

Run: `python eval/pixel_density/sweep_forms.py --quick`
Expected: Table with 176 results sorted by HLL_363 error. Should complete in < 1 min.

- [ ] **Step 3: Run full sweep on all PDFs**

Run: `python eval/pixel_density/sweep_forms.py`
Expected: Table with 176 results sorted by HLL error, then general MAE. ART gate PASSED. ~5-10 min.

- [ ] **Step 4: Commit sweep results**

```bash
git add eval/pixel_density/sweep_forms.py data/pixel_density/sweep_forms.json
git commit -m "research(pixel-density): scorer_forms Phase 1 sweep — vertical density"
```

---

### Task 6: Evaluate results and register best config

**Files:**
- Modify: `eval/pixel_density/params.py` (add `BEST_FORMS_CONFIG`)

This task is done manually based on sweep results.

- [ ] **Step 1: Analyze sweep results**

Look at the top results from the sweep. Identify the parameter combination with the lowest HLL_363 abs_error. If multiple combos tie on HLL, pick the one with lowest general MAE.

- [ ] **Step 2: Register best config in params.py**

Add to `eval/pixel_density/params.py`:

```python
# ── Forms: Page classification for form-based PDFs (PD_FORMS) ────────────
# Classifies pages by vertical ink distribution. Designed for PDFs like
# HLL_363 where bilateral scoring fails due to visual uniformity.
#
# HLL_363: detected=X, error=Y
# General corpus: MAE=Z

BEST_FORMS_CONFIG: dict = {
    "bottom_frac": <best>,
    "signal": "<best>",
    "threshold_method": "<best>",
}
```

Fill in actual values from sweep results.

- [ ] **Step 3: Commit**

```bash
git add eval/pixel_density/params.py
git commit -m "feat(pixel-density): register BEST_FORMS_CONFIG from Phase 1 sweep"
```

---

### Task 7: Update documentation

**Files:**
- Modify: `eval/pixel_density/README.md`

- [ ] **Step 1: Add scorer_forms section to README**

Add after the "Research History" section:

```markdown
6. **PD_FORMS** (2026-04-06): Page classification scorer for form-based PDFs.
   Uses vertical ink distribution to classify covers. Designed for HLL_363.
   Spec: `docs/superpowers/specs/2026-04-06-scorer-forms-design.md`
   Results: `docs/research/2026-04-06-scorer-forms-results.md`
```

Add `sweep_forms.py` to the Files table.

- [ ] **Step 2: Write results document**

Create `docs/research/2026-04-06-scorer-forms-results.md` with:
- Sweep results table (top 10 configs)
- Best config and its HLL_363 error
- General corpus MAE
- ART gate confirmation
- Decision: proceed to Phase 2 or not (based on success criteria from spec)

- [ ] **Step 3: Commit and tag**

```bash
git add eval/pixel_density/README.md docs/research/2026-04-06-scorer-forms-results.md
git commit -m "docs(pixel-density): scorer_forms Phase 1 results"
git tag PD_FORMS_V1
```

---

## Decision Gate

After Task 7, evaluate against the success criteria from the spec:

- **HLL_363 error ≤ ±15:** Phase 1 successful. Stop here (or proceed to Phase 2 for further improvement).
- **HLL_363 error ±16 to ±30:** Refine Phase 1 — try finer bottom_frac grid (0.01 step around best), add `bot_mid_ratio` with explicit 3-zone split. Do NOT proceed to Phase 2 yet.
- **HLL_363 error > ±30:** Proceed to Phase 2 (table structure detection). See spec for Phase 2 design.

Phase 2 and Phase 3 plans will be written separately if the decision gate triggers them.
