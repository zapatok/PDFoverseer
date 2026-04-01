"""PD V2 Rescue — cross-validation of three rescue lines.

Rescue A: edge_density standalone with V1 threshold (pct_75.2)
Rescue B: score fusion (V1 base + edge boost)
Rescue C: multi-descriptor (dark_ratio + edge_density) with V1 threshold

Usage
-----
    python eval/pixel_density/sweep_rescue.py
    python eval/pixel_density/sweep_rescue.py --rescue A     # single line
    python eval/pixel_density/sweep_rescue.py --rescue A B C  # specific lines
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np  # noqa: E402

from eval.pixel_density.cache import ensure_cache  # noqa: E402
from eval.pixel_density.evaluate import (  # noqa: E402
    compute_metrics,
    compute_metrics_count_only,
    load_art674_gt,
    load_tess_only_pages,
    save_results,
)
from eval.pixel_density.features import (  # noqa: E402
    extract_features,
    feat_dark_ratio_grid,
    feat_edge_density_grid,
)
from eval.pixel_density.metrics import bilateral_l2  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DPI = 100

# ── PDF corpus ──────────────────────────────────────────────────────────────

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


# ── Cross-validation harness ───────────────────────────────────────────────


def cross_validate(
    scorer: Callable[[np.ndarray], list[int]],
    corpus: list[tuple[str, str, int]],
) -> list[dict]:
    """Run a scorer over multiple PDFs, return per-PDF count metrics.

    Args:
        scorer: Function (pages_array) -> list of detected cover page indices.
        corpus: List of (name, pdf_path, target_doc_count) tuples.

    Returns:
        List of dicts with name, target, matches, error, abs_error.
    """
    results: list[dict] = []
    for name, pdf_path, target in corpus:
        pages = ensure_cache(pdf_path, dpi=DPI)
        matches = scorer(pages)
        metrics = compute_metrics_count_only(matches, target)
        results.append({"name": name, **metrics, "target": target})
    return results


# ── Shared utilities ───────────────────────────────────────────────────────


def _percentile_threshold(scores: np.ndarray, pct: float) -> list[int]:
    """Threshold at given percentile, ensuring page 0 is always included."""
    thresh = np.percentile(scores, pct)
    matches = [i for i in range(len(scores)) if scores[i] >= thresh]
    if 0 not in matches:
        matches.insert(0, 0)
    return matches


def _normalize_01(scores: np.ndarray) -> np.ndarray:
    """Min-max normalize scores to [0, 1]."""
    mn, mx = scores.min(), scores.max()
    if mx - mn < 1e-12:
        return np.zeros_like(scores)
    return (scores - mn) / (mx - mn)


def _robust_z_normalize(matrix: np.ndarray) -> np.ndarray:
    """Robust z-score normalization using median and MAD.

    Args:
        matrix: 2-D array (n_samples, n_features).

    Returns:
        Normalized matrix, same shape.
    """
    median = np.median(matrix, axis=0)
    mad = np.median(np.abs(matrix - median), axis=0)
    mad[mad < 1e-12] = 1.0
    return (matrix - median) / (mad * 1.4826)


# ── Scorers ────────────────────────────────────────────────────────────────


def scorer_v1(pages: np.ndarray, pct: float = 75.2) -> list[int]:
    """V1-count baseline: dark_ratio_grid 8x8, L2 bilateral, min, pct_75.2.

    Applies CLAHE preprocessing to match the production V1 pipeline.

    Args:
        pages: Array of shape (N, H, W), uint8 grayscale pages.
        pct: Percentile threshold (default: 75.2).

    Returns:
        List of detected cover page indices (0-based).
    """
    import cv2

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    vectors = []
    for i in range(pages.shape[0]):
        enhanced = clahe.apply(pages[i])
        vectors.append(feat_dark_ratio_grid(enhanced, grid_n=8))
    scores = bilateral_l2(vectors, "min")
    return _percentile_threshold(scores, pct)


def scorer_rescue_a(pages: np.ndarray, pct: float = 75.2) -> list[int]:
    """Rescue A: edge_density_grid 4x4, L2 bilateral, min, pct_75.2.

    No CLAHE preprocessing — Canny edge detection operates on raw grayscale,
    and CLAHE (contrast enhancement) would alter edge magnitudes unpredictably.

    Args:
        pages: Array of shape (N, H, W), uint8 grayscale pages.
        pct: Percentile threshold (default: 75.2).

    Returns:
        List of detected cover page indices (0-based).
    """
    vectors = [feat_edge_density_grid(pages[i], grid_n=4) for i in range(pages.shape[0])]
    scores = bilateral_l2(vectors, "min")
    return _percentile_threshold(scores, pct)


def scorer_rescue_b(
    pages: np.ndarray,
    edge_weight: float = 0.2,
    pct: float = 75.2,
) -> list[int]:
    """Rescue B: V1 base + edge_density boost, fused scores with pct threshold.

    Args:
        pages: Array of shape (N, H, W), uint8 grayscale pages.
        edge_weight: Weight for edge_density scores (V1 gets 1 - edge_weight).
        pct: Percentile threshold (default: 75.2).

    Returns:
        List of detected cover page indices (0-based).
    """
    import cv2

    v1_weight = 1.0 - edge_weight

    # V1 scores (CLAHE + dark_ratio)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    v1_vectors = []
    for i in range(pages.shape[0]):
        enhanced = clahe.apply(pages[i])
        v1_vectors.append(feat_dark_ratio_grid(enhanced, grid_n=8))
    v1_scores = _normalize_01(bilateral_l2(v1_vectors, "min"))

    # Edge density scores
    edge_vectors = [feat_edge_density_grid(pages[i], grid_n=4) for i in range(pages.shape[0])]
    edge_scores = _normalize_01(bilateral_l2(edge_vectors, "min"))

    # Fuse
    fused = v1_weight * v1_scores + edge_weight * edge_scores
    return _percentile_threshold(fused, pct)


def scorer_rescue_c(pages: np.ndarray, pct: float = 75.2) -> list[int]:
    """Rescue C: dark_ratio + edge_density, robust-z norm, L2 bilateral, pct_75.2.

    Same feature combination as V2, but with V1's percentile threshold
    instead of KMeans.

    Args:
        pages: Array of shape (N, H, W), uint8 grayscale pages.
        pct: Percentile threshold (default: 75.2).

    Returns:
        List of detected cover page indices (0-based).
    """
    feat_list = ["dark_ratio_grid", "edge_density_grid"]
    vectors = [extract_features(pages[i], feat_list) for i in range(pages.shape[0])]
    matrix = np.vstack(vectors)
    normed = _robust_z_normalize(matrix)
    normed_list = [normed[i] for i in range(normed.shape[0])]
    scores = bilateral_l2(normed_list, "min")
    return _percentile_threshold(scores, pct)
