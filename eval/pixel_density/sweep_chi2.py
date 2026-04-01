# eval/pixel_density/sweep_chi2.py
"""Phase 1: Chi-squared histogram bilateral sweep.

Sweeps bins × mode × score_fn × threshold on ART_674 (primary) and HLL_363
(secondary). Reports F1, precision, recall, error, and TESS-ONLY recovery.

Usage
-----
    python eval/pixel_density/sweep_chi2.py
    python eval/pixel_density/sweep_chi2.py --quick  # skip tile mode
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np

from eval.pixel_density.cache import ensure_cache
from eval.pixel_density.evaluate import (
    compute_metrics,
    compute_metrics_count_only,
    load_art674_gt,
    load_tess_only_pages,
    report_table,
    save_results,
)
from eval.pixel_density.features import feat_histogram, feat_histogram_tile
from eval.pixel_density.metrics import bilateral_chi2, bilateral_scores, chi2_tile_distance
from eval.pixel_density.sweep_bilateral import kmeans_matches

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

ART_PDF = "data/samples/ART_674.pdf"
HLL_PDF = "data/samples/HLL_363.pdf"
ART_TARGET = 674
HLL_TARGET = 363
DPI = 100

# ── Parameter space ─────────────────────────────────────────────────────────

BINS_VALUES = [16, 32, 64]
MODES = ["global", "tile_4x4"]
SCORE_FNS = ["min", "harmonic"]
PERCENTILES = [70.0, 72.0, 74.0, 76.0, 78.0, 80.0]


def _extract_histograms(
    pages: np.ndarray, bins: int, mode: str,
) -> list[np.ndarray]:
    """Extract histogram features from cached page arrays.

    Args:
        pages: (n_pages, H, W) uint8 array from cache.
        bins: Number of histogram bins.
        mode: "global" or "tile_4x4".

    Returns:
        List of 1-D feature vectors.
    """
    features: list[np.ndarray] = []
    for i in range(pages.shape[0]):
        img = pages[i]
        if mode == "global":
            features.append(feat_histogram(img, bins=bins))
        elif mode == "tile_4x4":
            features.append(feat_histogram_tile(img, grid_n=4, bins=bins))
        else:
            raise ValueError(f"Unknown mode: {mode!r}")
    return features


def _threshold_percentile(
    scores: np.ndarray, pct: float,
) -> tuple[list[int], str]:
    """Threshold by percentile: pages above pct-th percentile are covers."""
    thresh = np.percentile(scores, pct)
    matches = [i for i in range(len(scores)) if scores[i] >= thresh]
    if 0 not in matches:
        matches.insert(0, 0)
    return matches, f"pct_{pct:.1f}"


def _run_art674(pages: np.ndarray, gt_covers: set[int],
                tess_only: set[int]) -> list[dict]:
    """Run all combos on ART_674."""
    results: list[dict] = []
    combos = list(product(BINS_VALUES, MODES, SCORE_FNS))
    logger.info("ART_674: %d feature combos × %d thresholds = %d total",
                len(combos), 1 + len(PERCENTILES),
                len(combos) * (1 + len(PERCENTILES)))

    for bins, mode, score_fn in combos:
        t0 = time.perf_counter()
        features = _extract_histograms(pages, bins, mode)

        if mode == "global":
            scores = bilateral_chi2(features, score_fn)
        else:
            def _tile_dist(a: np.ndarray, b: np.ndarray) -> float:
                return chi2_tile_distance(
                    a.reshape(-1, bins), b.reshape(-1, bins),
                )
            scores = bilateral_scores(features, _tile_dist, score_fn)

        elapsed = time.perf_counter() - t0

        # K-Means threshold
        matches_km, _ = kmeans_matches(scores)
        metrics = compute_metrics(matches_km, gt_covers, ART_TARGET,
                                  tess_only_pages=tess_only)
        results.append({
            "params": {"bins": bins, "mode": mode, "score_fn": score_fn,
                       "threshold": "kmeans_k2"},
            **metrics,
            "time_s": round(elapsed, 2),
        })

        # Percentile thresholds
        for pct in PERCENTILES:
            matches_pct, label = _threshold_percentile(scores, pct)
            metrics = compute_metrics(matches_pct, gt_covers, ART_TARGET,
                                      tess_only_pages=tess_only)
            results.append({
                "params": {"bins": bins, "mode": mode, "score_fn": score_fn,
                           "threshold": label},
                **metrics,
                "time_s": round(elapsed, 2),
            })

    return results


def _run_hll363(pages: np.ndarray, best_params: list[dict]) -> list[dict]:
    """Run top ART_674 configs on HLL_363 (count-only evaluation)."""
    results: list[dict] = []
    for p in best_params:
        bins = p["bins"]
        mode = p["mode"]
        score_fn = p["score_fn"]
        threshold = p["threshold"]

        features = _extract_histograms(pages, bins, mode)
        if mode == "global":
            scores = bilateral_chi2(features, score_fn)
        else:
            def _tile_dist(a: np.ndarray, b: np.ndarray) -> float:
                return chi2_tile_distance(
                    a.reshape(-1, bins), b.reshape(-1, bins),
                )
            scores = bilateral_scores(features, _tile_dist, score_fn)

        if threshold == "kmeans_k2":
            matches, _ = kmeans_matches(scores)
        elif threshold.startswith("pct_"):
            pct = float(threshold.split("_")[1])
            matches, _ = _threshold_percentile(scores, pct)
        else:
            continue

        metrics = compute_metrics_count_only(matches, HLL_TARGET)
        results.append({"params": p, **metrics})

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 1: Chi² histogram bilateral sweep")
    parser.add_argument("--quick", action="store_true", help="Skip tile mode")
    args = parser.parse_args()

    modes = ["global"] if args.quick else list(MODES)  # noqa: F841

    print("=" * 70)
    print("Phase 1: Chi² Histogram Bilateral Sweep")
    print("=" * 70)

    gt_covers = load_art674_gt()
    tess_only = load_tess_only_pages()
    print(f"GT: {len(gt_covers)} covers, {len(tess_only)} TESS-ONLY pages\n")

    art_pages = ensure_cache(ART_PDF, dpi=DPI)

    t0 = time.perf_counter()
    art_results = _run_art674(art_pages, gt_covers, tess_only)
    art_elapsed = time.perf_counter() - t0

    art_results.sort(key=lambda r: (-r["f1"], r["abs_error"]))
    report_table(art_results, sort_key="f1", top_n=15)

    best_f1 = art_results[0]["f1"]
    best_tess = max(r.get("tess_only_recovered", 0) for r in art_results)
    print("\n--- Gate Check ---")
    print(f"Best F1: {best_f1:.4f} (baseline: 0.922) -- "
          f"{'PASS' if best_f1 > 0.922 else 'FAIL'}")
    print(f"Max TESS-ONLY recovered: {best_tess}/27 -- "
          f"{'PASS' if best_tess >= 1 else 'FAIL'}")

    hll_results: list[dict] = []
    if Path(HLL_PDF).exists():
        hll_pages = ensure_cache(HLL_PDF, dpi=DPI)
        top5_params = [r["params"] for r in art_results[:5]]
        hll_results = _run_hll363(hll_pages, top5_params)
        hll_results.sort(key=lambda r: r["abs_error"])
        print("\n--- HLL_363 (top 5 ART configs) ---")
        for r in hll_results:
            print(f"  {r['params']} -- matches={r['matches']} error={r['error']:+d}")

    # Save raw per-page scores for best config (needed by Phase 4)
    best_params = art_results[0]["params"]
    best_features = _extract_histograms(art_pages, best_params["bins"],
                                         best_params["mode"])
    if best_params["mode"] == "global":
        best_scores = bilateral_chi2(best_features, best_params["score_fn"])
    else:
        bins = best_params["bins"]

        def _td(a: np.ndarray, b: np.ndarray) -> float:
            return chi2_tile_distance(a.reshape(-1, bins), b.reshape(-1, bins))
        best_scores = bilateral_scores(best_features, _td,
                                        best_params["score_fn"])

    output = {
        "sweep": "chi2_bilateral",
        "timestamp": datetime.now().isoformat(),
        "art674_total_time_s": round(art_elapsed, 1),
        "best_config_params": best_params,
        "best_config_scores": best_scores.tolist(),
        "results_art674": art_results,
        "results_hll363": hll_results,
    }
    save_results(output, "data/pixel_density/sweep_chi2.json")
    print(f"\nDone in {art_elapsed:.1f}s")


if __name__ == "__main__":
    main()
