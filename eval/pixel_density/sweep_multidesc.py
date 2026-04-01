# eval/pixel_density/sweep_multidesc.py
"""Phase 3: Multi-descriptor bilateral sweep.

Stage A: Individual feature evaluation (each feature solo → bilateral → F1).
Stage B: Combine top features with dark_ratio_grid baseline (z-score + L2).

Usage
-----
    python eval/pixel_density/sweep_multidesc.py
    python eval/pixel_density/sweep_multidesc.py --stage A  # individual only
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np  # noqa: E402
from scipy.stats import zscore  # noqa: E402

from eval.pixel_density.cache import ensure_cache  # noqa: E402
from eval.pixel_density.evaluate import (  # noqa: E402
    compute_metrics,
    load_art674_gt,
    load_tess_only_pages,
    report_table,
    save_results,
)
from eval.pixel_density.features import _FEATURE_REGISTRY, extract_features  # noqa: E402
from eval.pixel_density.metrics import bilateral_chi2, bilateral_l2  # noqa: E402
from eval.pixel_density.sweep_bilateral import kmeans_matches  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

ART_PDF = "data/samples/ART_674.pdf"
ART_TARGET = 674
DPI = 100

CHI2_FEATURES = {"histogram", "histogram_tile", "lbp_histogram"}

NORMALIZATIONS = ["zscore", "robust_z", "minmax"]

SCORE_FNS = ["min", "harmonic"]


def _extract_all_features(
    pages: np.ndarray, feature_name: str,
) -> list[np.ndarray]:
    """Extract a single feature type for all pages."""
    fn, kwargs = _FEATURE_REGISTRY[feature_name]
    return [fn(pages[i], **kwargs) for i in range(pages.shape[0])]


def _normalize_matrix(
    matrix: np.ndarray, method: str,
) -> np.ndarray:
    """Normalize feature matrix column-wise.

    Args:
        matrix: (n_pages, dims) float64.
        method: "zscore", "robust_z" (median/MAD), or "minmax".

    Returns:
        Normalized matrix, same shape.
    """
    if method == "zscore":
        result = zscore(matrix, axis=0, nan_policy="omit")
        return np.nan_to_num(result, 0.0)
    elif method == "robust_z":
        median = np.median(matrix, axis=0)
        mad = np.median(np.abs(matrix - median), axis=0)
        mad[mad == 0] = 1.0
        return (matrix - median) / (1.4826 * mad)
    elif method == "minmax":
        mn = matrix.min(axis=0)
        mx = matrix.max(axis=0)
        rng = mx - mn
        rng[rng == 0] = 1.0
        return (matrix - mn) / rng
    else:
        raise ValueError(f"Unknown normalization: {method!r}")


def _percentile_threshold(
    scores: np.ndarray, pct: float,
) -> list[int]:
    """Threshold at given percentile."""
    thresh = np.percentile(scores, pct)
    matches = [i for i in range(len(scores)) if scores[i] >= thresh]
    if 0 not in matches:
        matches.insert(0, 0)
    return matches


def stage_a(
    pages: np.ndarray, gt_covers: set[int], tess_only: set[int],
    best_pct: float = 75.2,
) -> list[dict]:
    """Stage A: Individual feature evaluation."""
    results: list[dict] = []

    for feat_name in _FEATURE_REGISTRY:
        logger.info("Stage A: %s", feat_name)
        features = _extract_all_features(pages, feat_name)

        if feat_name in CHI2_FEATURES:
            scores = bilateral_chi2(features, "min")
        else:
            scores = bilateral_l2(features, "min")

        # K-Means threshold
        matches_km, _ = kmeans_matches(scores)
        metrics = compute_metrics(matches_km, gt_covers, ART_TARGET,
                                  tess_only_pages=tess_only)
        results.append({
            "params": {"feature": feat_name, "threshold": "kmeans_k2"},
            **metrics,
        })

        # Percentile threshold
        matches_pct = _percentile_threshold(scores, best_pct)
        metrics = compute_metrics(matches_pct, gt_covers, ART_TARGET,
                                  tess_only_pages=tess_only)
        results.append({
            "params": {"feature": feat_name, "threshold": f"pct_{best_pct}"},
            **metrics,
        })

    results.sort(key=lambda r: (-r["f1"], r["abs_error"]))
    return results


def stage_b(
    pages: np.ndarray, gt_covers: set[int], tess_only: set[int],
    top_features: list[str], best_pct: float = 75.2,
) -> list[dict]:
    """Stage B: Combine dark_ratio_grid + top individual features."""
    results: list[dict] = []
    base = "dark_ratio_grid"

    combos: list[list[str]] = []
    for feat in top_features:
        if feat != base:
            combos.append([base, feat])
    if len(top_features) >= 2:
        top2 = [f for f in top_features[:2] if f != base]
        if top2:
            combos.append([base] + top2)
    if len(top_features) >= 3:
        top3 = [f for f in top_features[:3] if f != base]
        if top3:
            combos.append([base] + top3)
    combos.append(list(_FEATURE_REGISTRY.keys()))  # all features

    for feat_list in combos:
        all_vectors: list[np.ndarray] = []
        for i in range(pages.shape[0]):
            all_vectors.append(extract_features(pages[i], feat_list))
        matrix = np.vstack(all_vectors)

        for norm in NORMALIZATIONS:
            normed = _normalize_matrix(matrix, norm)
            normed_list = [normed[i] for i in range(normed.shape[0])]

            for score_fn in SCORE_FNS:
                scores = bilateral_l2(normed_list, score_fn)

                # K-Means
                matches_km, _ = kmeans_matches(scores)
                metrics = compute_metrics(matches_km, gt_covers, ART_TARGET,
                                          tess_only_pages=tess_only)
                feat_label = "+".join(feat_list)
                results.append({
                    "params": {"features": feat_label, "norm": norm,
                               "score_fn": score_fn, "threshold": "kmeans_k2"},
                    **metrics,
                })

                # Percentile
                matches_pct = _percentile_threshold(scores, best_pct)
                metrics = compute_metrics(matches_pct, gt_covers, ART_TARGET,
                                          tess_only_pages=tess_only)
                results.append({
                    "params": {"features": feat_label, "norm": norm,
                               "score_fn": score_fn,
                               "threshold": f"pct_{best_pct}"},
                    **metrics,
                })

    results.sort(key=lambda r: (-r["f1"], r["abs_error"]))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 3: Multi-descriptor bilateral sweep")
    parser.add_argument("--stage", choices=["A", "B", "AB"], default="AB",
                        help="Run stage A, B, or both (default: AB)")
    args = parser.parse_args()

    print("=" * 70)
    print("Phase 3: Multi-Descriptor Bilateral Sweep")
    print("=" * 70)

    gt_covers = load_art674_gt()
    tess_only = load_tess_only_pages()
    print(f"GT: {len(gt_covers)} covers, {len(tess_only)} TESS-ONLY pages\n")

    art_pages = ensure_cache(ART_PDF, dpi=DPI)

    results_a: list[dict] = []
    results_b: list[dict] = []

    if "A" in args.stage:
        t0 = time.perf_counter()
        results_a = stage_a(art_pages, gt_covers, tess_only)
        print(f"\n--- Stage A: Individual Features ({time.perf_counter()-t0:.1f}s) ---")
        report_table(results_a, sort_key="f1", top_n=14)

        best_a_f1 = results_a[0]["f1"] if results_a else 0
        print(f"Best individual F1: {best_a_f1:.4f} (baseline: 0.922) → "
              f"{'PASS' if best_a_f1 > 0.922 else 'FAIL'}")

    if "B" in args.stage:
        if results_a:
            seen: set[str] = set()
            top_features: list[str] = []
            for r in results_a:
                feat = r["params"]["feature"]
                if feat not in seen:
                    seen.add(feat)
                    top_features.append(feat)
        else:
            top_features = list(_FEATURE_REGISTRY.keys())

        t0 = time.perf_counter()
        results_b = stage_b(art_pages, gt_covers, tess_only, top_features)
        print(f"\n--- Stage B: Combinations ({time.perf_counter()-t0:.1f}s) ---")
        report_table(results_b, sort_key="f1", top_n=15)

        best_b_f1 = results_b[0]["f1"] if results_b else 0
        best_a_f1 = results_a[0]["f1"] if results_a else 0.922
        print(f"Best combination F1: {best_b_f1:.4f} vs best individual: "
              f"{best_a_f1:.4f} → "
              f"{'PASS' if best_b_f1 > best_a_f1 else 'FAIL'}")

    output = {
        "sweep": "multidesc_bilateral",
        "timestamp": datetime.now().isoformat(),
        "results_stage_a": results_a,
        "results_stage_b": results_b,
    }
    save_results(output, "data/pixel_density/sweep_multidesc.json")


if __name__ == "__main__":
    main()
