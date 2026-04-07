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
