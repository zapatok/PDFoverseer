# scorer_forms V2 — Multi-Feature KMeans Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `scorer_forms_v2` — a multi-feature KMeans k=2 page classifier — and sweep 63 feature subsets on CH-family PDFs to find the best config for combined F1 > 0.85 (up from V1's ~0.69).

**Architecture:** `scorer_forms_v2` builds a per-page joint feature matrix from up to 6 feature groups (max 100d), robust-z normalizes it, and applies KMeans k=2 with cover assignment via page 0's cluster. A standalone sweep script (`sweep_forms_v2.py`) pre-extracts per-PDF feature caches once, then evaluates all 63 non-empty subsets against CH-family page-level GT (derived from OCR fixture JSON), ranks by combined pooled F1, and cross-validates the top-10 on HLL_363 count error.

**Tech Stack:** numpy, sklearn.cluster.KMeans, skimage (LBP), cv2 (Canny/CC), scipy.stats (skew) — all existing dependencies

---

## Chunk 1: scorer_forms_v2 function + unit tests

### Task 1: Write failing unit tests for scorer_forms_v2

**Files:**
- Modify: `eval/tests/test_scorer_forms.py`

- [ ] **Step 1: Add tests after the existing `scorer_forms` tests (before the ART gate section)**

```python
# ── scorer_forms_v2 ────────────────────────────────────────────────────────


def test_scorer_forms_v2_returns_list():
    """Returns a list of ints."""
    from eval.pixel_density.sweep_forms import scorer_forms_v2

    rng = np.random.default_rng(42)
    pages = rng.integers(0, 256, (10, 100, 80), dtype=np.uint8)
    result = scorer_forms_v2(pages, ["cc_stats"])
    assert isinstance(result, list)
    assert all(isinstance(i, int) for i in result)


def test_scorer_forms_v2_includes_page_0():
    """Page 0 is always in the result."""
    from eval.pixel_density.sweep_forms import scorer_forms_v2

    rng = np.random.default_rng(42)
    pages = rng.integers(0, 256, (10, 100, 80), dtype=np.uint8)
    result = scorer_forms_v2(pages, ["cc_stats", "edge_density_grid"])
    assert 0 in result


def test_scorer_forms_v2_single_page():
    """Single-page PDF returns [0]."""
    from eval.pixel_density.sweep_forms import scorer_forms_v2

    pages = np.full((1, 100, 80), 200, dtype=np.uint8)
    result = scorer_forms_v2(pages, ["cc_stats"])
    assert result == [0]


def test_scorer_forms_v2_sorted_output():
    """Output is sorted ascending."""
    from eval.pixel_density.sweep_forms import scorer_forms_v2

    rng = np.random.default_rng(42)
    pages = rng.integers(0, 256, (20, 100, 80), dtype=np.uint8)
    result = scorer_forms_v2(pages, ["cc_stats", "edge_density_grid"])
    assert result == sorted(result)


def test_scorer_forms_v2_identical_pages():
    """All-identical pages returns [0] via pre-normalization check."""
    from eval.pixel_density.sweep_forms import scorer_forms_v2

    page = np.full((100, 80), 128, dtype=np.uint8)
    pages = np.stack([page] * 8)
    result = scorer_forms_v2(pages, ["cc_stats", "dark_ratio_grid"])
    assert result == [0]


def test_scorer_forms_v2_vertical_density_group():
    """vertical_density feature group works (special-cased, not in registry)."""
    from eval.pixel_density.sweep_forms import scorer_forms_v2

    rng = np.random.default_rng(42)
    pages = rng.integers(0, 256, (10, 100, 80), dtype=np.uint8)
    result = scorer_forms_v2(pages, ["vertical_density"])
    assert 0 in result
    assert isinstance(result, list)


def test_scorer_forms_v2_all_feature_groups():
    """All 6 feature groups together run without error."""
    from eval.pixel_density.sweep_forms import scorer_forms_v2

    rng = np.random.default_rng(42)
    pages = rng.integers(0, 256, (10, 100, 80), dtype=np.uint8)
    groups = [
        "vertical_density", "projection_stats", "edge_density_grid",
        "cc_stats", "dark_ratio_grid", "lbp_histogram",
    ]
    result = scorer_forms_v2(pages, groups)
    assert 0 in result
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest eval/tests/test_scorer_forms.py -k "v2" -v
```

Expected: `AttributeError` or `ImportError` — `scorer_forms_v2` does not exist yet.

- [ ] **Step 3: Commit failing tests**

```bash
git add eval/tests/test_scorer_forms.py
git commit -m "test(forms-v2): add failing unit tests for scorer_forms_v2"
```

---

### Task 2: Implement scorer_forms_v2 in sweep_forms.py

**Files:**
- Modify: `eval/pixel_density/sweep_forms.py`

- [ ] **Step 1: Add `_V2_VALID_GROUPS` constant and `scorer_forms_v2` function**

Place this block after the existing `scorer_forms` function and before `run_sweep`. The `_FEATURE_REGISTRY` tuple format is `(fn, kwargs_dict)` — call as `fn(img, **kwargs)`.

```python
# ── scorer_forms_v2 ────────────────────────────────────────────────────────

_V2_VALID_GROUPS = frozenset([
    "vertical_density", "projection_stats", "edge_density_grid",
    "cc_stats", "dark_ratio_grid", "lbp_histogram",
])


def scorer_forms_v2(
    pages: np.ndarray,
    feature_groups: list[str],
    bottom_frac: float = 0.35,
    random_state: int = 42,
    _features_precomputed: dict[str, np.ndarray] | None = None,
) -> list[int]:
    """Classify pages as covers using multi-feature KMeans k=2.

    Builds a joint feature matrix [N_pages × D_features] from the requested
    feature groups, robust-z normalizes per dimension, and applies KMeans k=2.
    The cluster containing page 0 is treated as covers.

    Args:
        pages: Rendered page images, shape [N, H, W], dtype uint8.
        feature_groups: Feature groups to use. Valid names: vertical_density,
            projection_stats, edge_density_grid, cc_stats, dark_ratio_grid,
            lbp_histogram.
        bottom_frac: Bottom zone fraction for vertical_density feature.
        random_state: KMeans seed for reproducibility.
        _features_precomputed: Optional dict mapping group name → [N, D] array.
            Skips feature extraction for groups present in this dict (sweep
            efficiency — extract once per PDF, reuse across 63 subsets).

    Returns:
        Sorted list of 0-indexed cover page indices. Page 0 always included.
    """
    from eval.pixel_density.features import _FEATURE_REGISTRY, feat_vertical_density

    n_pages = len(pages)

    # Edge case: single page
    if n_pages == 1:
        return [0]

    # Build raw feature matrix [N, D]
    parts: list[np.ndarray] = []
    for group in feature_groups:
        if _features_precomputed is not None and group in _features_precomputed:
            parts.append(_features_precomputed[group])
        elif group == "vertical_density":
            vd = np.array([feat_vertical_density(p, bottom_frac) for p in pages])
            parts.append(vd)
        else:
            fn, kwargs = _FEATURE_REGISTRY[group]
            feats = np.array([fn(p, **kwargs) for p in pages])
            parts.append(feats)

    raw_matrix = np.concatenate(parts, axis=1)  # [N, D]

    # Edge case: all pages identical — check pre-normalization
    if np.all(raw_matrix == raw_matrix[0]):
        return [0]

    # Robust-z normalize per feature dimension
    median = np.median(raw_matrix, axis=0)
    mad = np.median(np.abs(raw_matrix - median), axis=0)
    scale = np.maximum(mad * 1.4826, 1e-9)
    norm_matrix = (raw_matrix - median) / scale

    # KMeans k=2
    import warnings

    from sklearn.cluster import KMeans

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        km = KMeans(n_clusters=2, random_state=random_state, n_init="auto")
        km.fit(norm_matrix)

    cover_label = int(km.labels_[0])
    covers = sorted(
        {i for i, lbl in enumerate(km.labels_) if lbl == cover_label} | {0}
    )
    return [int(i) for i in covers]
```

- [ ] **Step 2: Run the new tests**

```
pytest eval/tests/test_scorer_forms.py -k "v2" -v
```

Expected: All 7 tests PASS.

- [ ] **Step 3: Run full test suite — no regressions**

```
pytest eval/tests/test_scorer_forms.py -v
```

Expected: All tests PASS (19 existing + 7 new = 26 total).

- [ ] **Step 4: Ruff check**

```
ruff check eval/pixel_density/sweep_forms.py
```

Expected: 0 violations.

- [ ] **Step 5: Commit**

```bash
git add eval/pixel_density/sweep_forms.py
git commit -m "feat(forms-v2): add scorer_forms_v2 multi-feature KMeans classifier"
```

---

## Chunk 2: CH GT loader + F1 utilities + feature cache

### Task 3: Write failing tests for sweep utilities

**Files:**
- Modify: `eval/tests/test_scorer_forms.py`

- [ ] **Step 1: Add tests for `load_ch_gt`, `compute_f1`, `extract_all_features`, and precomputed passthrough**

Add after the scorer_forms_v2 tests (still before the ART gate):

```python
# ── sweep_forms_v2 utilities ──────────────────────────────────────────────


def test_load_ch_gt_covers_and_noncov():
    """load_ch_gt returns non-overlapping covers and noncov sets."""
    from eval.pixel_density.sweep_forms_v2 import load_ch_gt

    covers, noncov = load_ch_gt("eval/fixtures/real/CH_39.json")
    assert len(covers) > 0
    assert len(noncov) > 0
    assert covers.isdisjoint(noncov)
    assert 0 in covers  # first page is always a cover


def test_load_ch_gt_zero_indexed():
    """load_ch_gt returns 0-indexed page indices (pdf_page - 1)."""
    from eval.pixel_density.sweep_forms_v2 import load_ch_gt

    covers, noncov = load_ch_gt("eval/fixtures/real/CH_39.json")
    assert all(i >= 0 for i in covers | noncov)


def test_load_ch_gt_excludes_failed():
    """Pages with method=='failed' are excluded from both sets."""
    import json

    from eval.pixel_density.sweep_forms_v2 import load_ch_gt

    with open("eval/fixtures/real/CH_39.json") as f:
        data = json.load(f)

    failed = {r["pdf_page"] - 1 for r in data["reads"] if r["method"] == "failed"}
    covers, noncov = load_ch_gt("eval/fixtures/real/CH_39.json")
    # failed pages must not appear in either set
    assert failed.isdisjoint(covers | noncov)


def test_compute_f1_perfect():
    """Perfect prediction gives F1=1.0."""
    from eval.pixel_density.sweep_forms_v2 import compute_f1

    covers = {0, 2, 4}
    noncov = {1, 3, 5}
    m = compute_f1(list(covers), covers, noncov)
    assert m["f1"] == pytest.approx(1.0)
    assert m["precision"] == pytest.approx(1.0)
    assert m["recall"] == pytest.approx(1.0)


def test_compute_f1_missed_covers():
    """Missing predicted covers reduces recall."""
    from eval.pixel_density.sweep_forms_v2 import compute_f1

    covers = {0, 2, 4}
    noncov = {1, 3, 5}
    m = compute_f1([0], covers, noncov)  # only page 0 predicted (forced)
    assert m["recall"] < 1.0
    assert m["f1"] < 1.0


def test_compute_f1_failed_pages_ignored():
    """Predicting a failed page (not in covers or noncov) does not count as FP."""
    from eval.pixel_density.sweep_forms_v2 import compute_f1

    covers = {0, 2}
    noncov = {1, 3}
    # page 99 is a "failed" page — not in covers or noncov
    m_with = compute_f1([0, 2, 99], covers, noncov)
    m_without = compute_f1([0, 2], covers, noncov)
    # FP count should be the same
    assert m_with["fp"] == m_without["fp"]
    assert m_with["f1"] == pytest.approx(m_without["f1"])


def test_extract_all_features_shape():
    """extract_all_features returns dict with correct per-group shapes."""
    from eval.pixel_density.sweep_forms_v2 import extract_all_features

    rng = np.random.default_rng(42)
    pages = rng.integers(0, 256, (5, 100, 80), dtype=np.uint8)
    feats = extract_all_features(pages, bottom_frac=0.35)

    expected_shapes = {
        "vertical_density": (5, 2),
        "projection_stats": (5, 6),
        "edge_density_grid": (5, 16),
        "cc_stats": (5, 2),
        "dark_ratio_grid": (5, 64),
        "lbp_histogram": (5, 10),
    }
    for group, shape in expected_shapes.items():
        assert group in feats, f"Missing group: {group}"
        assert feats[group].shape == shape, f"{group}: expected {shape}, got {feats[group].shape}"


def test_scorer_forms_v2_precomputed_matches_live():
    """scorer_forms_v2 with precomputed cache gives same result as live extraction."""
    from eval.pixel_density.sweep_forms import scorer_forms_v2
    from eval.pixel_density.sweep_forms_v2 import extract_all_features

    rng = np.random.default_rng(42)
    pages = rng.integers(0, 256, (8, 100, 80), dtype=np.uint8)

    precomp = extract_all_features(pages)
    r_precomp = scorer_forms_v2(pages, ["cc_stats", "edge_density_grid"],
                                _features_precomputed=precomp)
    r_live = scorer_forms_v2(pages, ["cc_stats", "edge_density_grid"])
    assert r_precomp == r_live
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest eval/tests/test_scorer_forms.py -k "load_ch_gt or compute_f1 or extract_all_features or precomputed" -v
```

Expected: `ModuleNotFoundError` — `sweep_forms_v2` does not exist yet.

- [ ] **Step 3: Commit failing tests**

```bash
git add eval/tests/test_scorer_forms.py
git commit -m "test(forms-v2): add failing tests for GT loader, F1 utilities, feature cache"
```

---

### Task 4: Create sweep_forms_v2.py with GT loader, F1, and feature cache

**Files:**
- Create: `eval/pixel_density/sweep_forms_v2.py`

- [ ] **Step 1: Create the file**

```python
"""scorer_forms V2 sweep: 63 feature subsets × CH-family PDFs.

Stage 1: Sweep all 63 non-empty subsets of 6 feature groups on CH_39, CH_51,
         CH_74. Rank by combined pooled page-level F1. Outputs top-10 configs.
Stage 2: Cross-validate top-10 configs on HLL_363 count error (target ≤ 15).

Usage:
    python eval/pixel_density/sweep_forms_v2.py
"""

from __future__ import annotations

import json
import sys
from itertools import combinations
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from eval.pixel_density.features import _FEATURE_REGISTRY, feat_vertical_density  # noqa: E402
from eval.pixel_density.sweep_forms import scorer_forms_v2  # noqa: E402

# ── Constants ─────────────────────────────────────────────────────────────

FEATURE_GROUPS = [
    "vertical_density",
    "projection_stats",
    "edge_density_grid",
    "cc_stats",
    "dark_ratio_grid",
    "lbp_histogram",
]

BOTTOM_FRAC = 0.35

CH_FIXTURES = {
    "CH_39": "eval/fixtures/real/CH_39.json",
    "CH_51": "eval/fixtures/real/CH_51.json",
    "CH_74": "eval/fixtures/real/CH_74.json",
}

CH_PDFS = {
    "CH_39": "data/samples/CH_39.pdf",
    "CH_51": "data/samples/CH_51docs.pdf",
    "CH_74": "data/samples/CH_74docs.pdf",
}

HLL_PDF = "data/samples/HLL_363.pdf"
HLL_TARGET = 363


# ── GT loader ─────────────────────────────────────────────────────────────


def load_ch_gt(fixture_path: str) -> tuple[set[int], set[int]]:
    """Load CH fixture GT as 0-indexed cover/non-cover sets.

    Args:
        fixture_path: Path to CH_N.json fixture file.

    Returns:
        Tuple of (covers, noncov). Pages with method=='failed' are excluded
        from both sets. Indices are 0-based (pdf_page - 1).
    """
    with open(fixture_path) as f:
        data = json.load(f)

    covers: set[int] = set()
    noncov: set[int] = set()
    for read in data["reads"]:
        if read["method"] == "failed":
            continue
        idx = read["pdf_page"] - 1
        if read["curr"] == 1:
            covers.add(idx)
        else:
            noncov.add(idx)
    return covers, noncov


# ── F1 utilities ──────────────────────────────────────────────────────────


def compute_f1(
    predicted: list[int],
    covers: set[int],
    noncov: set[int],
) -> dict[str, float]:
    """Compute precision, recall, F1 for a predicted cover set.

    Failed pages (not in covers or noncov) are silently ignored — predicting
    a failed page does not count as FP or TP.

    Args:
        predicted: Predicted cover page indices (0-based).
        covers: Ground truth cover indices.
        noncov: Ground truth non-cover indices.

    Returns:
        Dict with keys: tp, fp, fn, precision, recall, f1.
    """
    pred_set = set(predicted)
    tp = len(pred_set & covers)
    fp = len(pred_set & noncov)
    fn = len(covers - pred_set)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": precision, "recall": recall, "f1": f1,
    }


# ── Feature cache ─────────────────────────────────────────────────────────


def extract_all_features(
    pages: np.ndarray,
    bottom_frac: float = BOTTOM_FRAC,
) -> dict[str, np.ndarray]:
    """Extract all 6 feature groups for every page.

    Args:
        pages: [N, H, W] uint8 grayscale page images.
        bottom_frac: Bottom zone fraction for vertical_density.

    Returns:
        Dict mapping group name to [N, D] float64 array.
    """
    cache: dict[str, np.ndarray] = {}

    # vertical_density is not in _FEATURE_REGISTRY — special-case it
    cache["vertical_density"] = np.array(
        [feat_vertical_density(p, bottom_frac) for p in pages]
    )

    # All other groups via registry
    for group in FEATURE_GROUPS:
        if group == "vertical_density":
            continue
        fn, kwargs = _FEATURE_REGISTRY[group]
        cache[group] = np.array([fn(p, **kwargs) for p in pages])

    return cache
```

- [ ] **Step 2: Run GT loader and utility tests**

```
pytest eval/tests/test_scorer_forms.py -k "load_ch_gt or compute_f1 or extract_all_features or precomputed" -v
```

Expected: All 8 tests PASS.

- [ ] **Step 3: Ruff check**

```
ruff check eval/pixel_density/sweep_forms_v2.py
```

Expected: 0 violations.

- [ ] **Step 4: Commit**

```bash
git add eval/pixel_density/sweep_forms_v2.py eval/tests/test_scorer_forms.py
git commit -m "feat(forms-v2): add GT loader, F1 utilities, feature cache to sweep_forms_v2"
```

---

## Chunk 3: Sweep loop + reporting

### Task 5: Implement sweep loop and main entry point

**Files:**
- Modify: `eval/pixel_density/sweep_forms_v2.py`

- [ ] **Step 1: Append sweep loop, reporting, and `main()` to sweep_forms_v2.py**

```python
# ── Sweep utilities ───────────────────────────────────────────────────────


def _all_subsets(groups: list[str]) -> list[list[str]]:
    """Return all 2**N - 1 non-empty subsets of groups (63 for N=6)."""
    result: list[list[str]] = []
    for r in range(1, len(groups) + 1):
        for combo in combinations(groups, r):
            result.append(list(combo))
    return result


# ── Stage 1: CH sweep ─────────────────────────────────────────────────────


def run_stage1_sweep(
    ch_pages: dict[str, np.ndarray],
    ch_caches: dict[str, dict[str, np.ndarray]],
    ch_gt: dict[str, tuple[set[int], set[int]]],
    bottom_frac: float = BOTTOM_FRAC,
) -> list[dict]:
    """Sweep all 63 feature subsets on CH-family PDFs.

    For each subset: classifier runs with precomputed feature cache, F1 is
    evaluated against page-level GT, and pooled F1 across all 3 PDFs is
    computed (sum TPs/FPs/FNs then derive F1 — "all pages pooled" semantics).

    Args:
        ch_pages: Dict mapping PDF name to [N, H, W] page array.
        ch_caches: Dict mapping PDF name to precomputed feature dict.
        ch_gt: Dict mapping PDF name to (covers, noncov) tuple.
        bottom_frac: bottom_frac passed to scorer_forms_v2.

    Returns:
        List of result dicts sorted by combined_f1 descending. Each entry:
        {feature_groups, combined_f1, combined_precision, combined_recall,
         per_pdf: {PDF_name: {tp, fp, fn, precision, recall, f1}}}.
    """
    subsets = _all_subsets(FEATURE_GROUPS)
    results = []

    for groups in subsets:
        all_tp = all_fp = all_fn = 0
        per_pdf: dict[str, dict] = {}

        for name in ["CH_39", "CH_51", "CH_74"]:
            predicted = scorer_forms_v2(
                ch_pages[name],
                groups,
                bottom_frac=bottom_frac,
                _features_precomputed=ch_caches[name],
            )
            m = compute_f1(predicted, *ch_gt[name])
            per_pdf[name] = m
            all_tp += m["tp"]
            all_fp += m["fp"]
            all_fn += m["fn"]

        precision = all_tp / (all_tp + all_fp) if (all_tp + all_fp) > 0 else 0.0
        recall = all_tp / (all_tp + all_fn) if (all_tp + all_fn) > 0 else 0.0
        combined_f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )
        results.append({
            "feature_groups": groups,
            "combined_f1": combined_f1,
            "combined_precision": precision,
            "combined_recall": recall,
            "per_pdf": per_pdf,
        })

    results.sort(key=lambda r: r["combined_f1"], reverse=True)
    return results


def print_stage1_results(results: list[dict], top_n: int = 10) -> None:
    """Print top N results from Stage 1 sweep."""
    print(f"\n{'=' * 74}")
    print(f"Stage 1 — CH Family Sweep (top {top_n} of {len(results)})")
    print(f"{'=' * 74}")
    print(f"{'#':>3}  {'F1':>6}  {'P':>6}  {'R':>6}  {'CH39':>6}  {'CH51':>6}  {'CH74':>6}  Feature Groups")
    print("-" * 74)
    for rank, r in enumerate(results[:top_n], 1):
        f39 = r["per_pdf"]["CH_39"]["f1"]
        f51 = r["per_pdf"]["CH_51"]["f1"]
        f74 = r["per_pdf"]["CH_74"]["f1"]
        groups_str = "+".join(r["feature_groups"])
        print(
            f"{rank:>3}  {r['combined_f1']:>6.3f}  "
            f"{r['combined_precision']:>6.3f}  {r['combined_recall']:>6.3f}  "
            f"{f39:>6.3f}  {f51:>6.3f}  {f74:>6.3f}  {groups_str}"
        )


# ── Stage 2: HLL cross-validation ────────────────────────────────────────


def run_stage2_hll(
    top_configs: list[dict],
    hll_pages: np.ndarray,
    hll_target: int = HLL_TARGET,
    bottom_frac: float = BOTTOM_FRAC,
) -> list[dict]:
    """Cross-validate top Stage 1 configs on HLL_363 count error.

    Args:
        top_configs: Top results from run_stage1_sweep (up to 10).
        hll_pages: [N, H, W] page array for HLL_363.
        hll_target: Expected document count.
        bottom_frac: bottom_frac passed to scorer_forms_v2.

    Returns:
        top_configs with added 'hll_count' and 'hll_error' keys.
    """
    hll_cache = extract_all_features(hll_pages, bottom_frac=bottom_frac)
    for r in top_configs:
        predicted = scorer_forms_v2(
            hll_pages,
            r["feature_groups"],
            bottom_frac=bottom_frac,
            _features_precomputed=hll_cache,
        )
        r["hll_count"] = len(predicted)
        r["hll_error"] = len(predicted) - hll_target
    return top_configs


def print_stage2_results(top_configs: list[dict]) -> None:
    """Print Stage 2 HLL_363 cross-validation results."""
    print(f"\n{'=' * 60}")
    print("Stage 2 — HLL_363 Cross-Validation (target: 363, threshold: ±15)")
    print(f"{'=' * 60}")
    print(f"{'#':>3}  {'F1':>6}  {'HLL err':>7}  Feature Groups")
    print("-" * 60)
    for rank, r in enumerate(top_configs, 1):
        err = r.get("hll_error")
        err_str = f"{err:+d}" if isinstance(err, int) else "N/A"
        ok = " ✓" if isinstance(err, int) and abs(err) <= 15 else "  "
        print(f"{rank:>3}  {r['combined_f1']:>6.3f}  {err_str:>7}{ok}  {'+'.join(r['feature_groups'])}")


# ── Entry point ───────────────────────────────────────────────────────────


def main() -> None:
    """Run Stage 1 (CH family sweep) + Stage 2 (HLL_363 cross-validation)."""
    from eval.pixel_density.cache import ensure_cache

    print("[Stage 1] Loading CH-family pages and extracting features...")
    ch_pages: dict[str, np.ndarray] = {}
    ch_caches: dict[str, dict[str, np.ndarray]] = {}
    ch_gt: dict[str, tuple[set[int], set[int]]] = {}

    for name, pdf_path in CH_PDFS.items():
        print(f"  {name}: loading...", end=" ", flush=True)
        pages = ensure_cache(pdf_path, dpi=100)
        ch_pages[name] = pages
        print(f"{len(pages)} pages | extracting features...", end=" ", flush=True)
        ch_caches[name] = extract_all_features(pages)
        ch_gt[name] = load_ch_gt(CH_FIXTURES[name])
        covers, noncov = ch_gt[name]
        print(f"GT: {len(covers)} covers, {len(noncov)} noncov")

    print(f"\n[Stage 1] Running {len(_all_subsets(FEATURE_GROUPS))}-subset sweep...")
    results = run_stage1_sweep(ch_pages, ch_caches, ch_gt)
    print_stage1_results(results, top_n=10)

    print("\n[Stage 2] Loading HLL_363 pages...")
    hll_pages = ensure_cache(HLL_PDF, dpi=100)
    print(f"  HLL_363: {len(hll_pages)} pages")
    top10 = run_stage2_hll(results[:10], hll_pages)
    print_stage2_results(top10)

    best = results[0]
    print(f"\n{'=' * 60}")
    print("Best config (highest CH combined F1):")
    print(f"  feature_groups = {best['feature_groups']}")
    print(f"  combined_f1    = {best['combined_f1']:.4f}")
    if "hll_error" in best:
        print(f"  hll_error      = {best['hll_error']:+d}")
    print("\nNext step: add BEST_FORMS_V2_CONFIG to eval/pixel_density/params.py")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Ruff check**

```
ruff check eval/pixel_density/sweep_forms_v2.py
```

Expected: 0 violations.

- [ ] **Step 3: Run full test suite**

```
pytest eval/tests/test_scorer_forms.py -v
```

Expected: All tests PASS (26 scorer + 8 utility = 34 total).

- [ ] **Step 4: Commit**

```bash
git add eval/pixel_density/sweep_forms_v2.py
git commit -m "feat(forms-v2): add sweep loop and main entry point to sweep_forms_v2"
```

---

## Chunk 4: Integration — run sweep, params, README

### Task 6: Run the sweep and record BEST_FORMS_V2_CONFIG

**Files:**
- Modify: `eval/pixel_density/params.py`

- [ ] **Step 1: Run the full sweep**

```
python eval/pixel_density/sweep_forms_v2.py
```

Expected output: 63 subsets evaluated, top-10 table printed (Stage 1), HLL count errors printed (Stage 2). Note the best config from the output.

- [ ] **Step 2: Choose the best config**

Select the config with the highest CH combined F1 that also has HLL error ≤ 15. If no top-10 config satisfies HLL ≤ 15, use the best CH F1 config regardless and note the HLL regression in the comment.

- [ ] **Step 3: Add BEST_FORMS_V2_CONFIG to params.py**

Parse the `feature_groups` list and F1/error values from the Step 1 sweep output, then add after the `BEST_FORMS_CONFIG` block at the end of `eval/pixel_density/params.py`. Substitute the real values — do NOT commit a syntax-broken placeholder:

```python
# ── Forms V2: Multi-feature KMeans for CH-family PDFs (PD_FORMS_V2) ──────
# Sweep: eval/pixel_density/sweep_forms_v2.py (2026-04-06)
# 63 non-empty subsets of 6 feature groups, ranked by CH pooled F1.
# CH combined F1: 0.XXX  ← fill from sweep Stage 1 output
# HLL_363 error: +N      ← fill from sweep Stage 2 output

BEST_FORMS_V2_CONFIG: dict = {
    "feature_groups": ["REPLACE_WITH_ACTUAL_GROUPS"],  # ← copy list from sweep output
    "bottom_frac": 0.35,
    "random_state": 42,
}
```

The `"feature_groups"` value must be a real Python list copied from the sweep output (e.g., `["cc_stats", "edge_density_grid"]`). Replace `"REPLACE_WITH_ACTUAL_GROUPS"` and the comment F1/error values before committing.

- [ ] **Step 4: Commit**

```bash
git add eval/pixel_density/params.py
git commit -m "feat(forms-v2): add BEST_FORMS_V2_CONFIG from sweep results"
```

---

### Task 7: Update README and run final tests

**Files:**
- Modify: `eval/pixel_density/README.md`

- [ ] **Step 1: Add sweep_forms_v2.py row to the Files table**

In the Files section, after the `sweep_forms.py` row, add:

```
| `sweep_forms_v2.py` | 63-subset multi-feature sweep + Stage 1/2 evaluation | `python eval/pixel_density/sweep_forms_v2.py` |
```

- [ ] **Step 2: Add V2 entry to Research History**

**Must fill before committing** — substitute real values from the sweep output:

```
7. **PD_FORMS_V2** (2026-04-06): Multi-feature KMeans sweep for CH-family PDFs. 63 non-empty subsets of 6 feature groups (vertical_density, projection_stats, edge_density_grid, cc_stats, dark_ratio_grid, lbp_histogram). Best config: REPLACE_WITH_GROUPS. CH combined F1: 0.XXX. HLL_363 error: +N. Spec: `docs/superpowers/specs/2026-04-06-scorer-forms-v2-design.md`.
```

Replace `REPLACE_WITH_GROUPS`, `0.XXX`, and `+N` with actual values from Task 6 sweep output.

- [ ] **Step 3: Run unit test suite (fast)**

```
pytest eval/tests/test_scorer_forms.py -v
```

Expected: All tests PASS (skips slow ART gate).

- [ ] **Step 4: Run ART hard gate (slow)**

The ART gate is `@pytest.mark.slow` and is skipped by plain `pytest`. Run it explicitly:

```
pytest eval/tests/test_scorer_forms.py -m slow -v
```

Expected: `test_art_safety_gate` PASS — 6/6 ART PDFs exact. This gate is non-negotiable per spec; if it fails, the implementation is broken.

- [ ] **Step 5: Final ruff check across the module**

```
ruff check eval/pixel_density/sweep_forms.py eval/pixel_density/sweep_forms_v2.py
```

Expected: 0 violations.

- [ ] **Step 6: Commit**

```bash
git add eval/pixel_density/README.md
git commit -m "docs(forms-v2): add sweep_forms_v2 to file table and research history"
```
