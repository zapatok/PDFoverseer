# eval/pixel_density/sweep_pelt.py
"""Phase 2: PELT segmentation sweep.

Feeds PELT a matrix of per-page feature vectors and finds optimal
segmentation. Each segment = one document, first page = cover.

Usage
-----
    python eval/pixel_density/sweep_pelt.py
    python eval/pixel_density/sweep_pelt.py --features histogram_32
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from collections.abc import Callable  # noqa: E402

import numpy as np  # noqa: E402

from eval.pixel_density.cache import ensure_cache  # noqa: E402
from eval.pixel_density.evaluate import (  # noqa: E402
    compute_metrics,
    compute_metrics_count_only,
    load_art674_gt,
    load_tess_only_pages,
    report_table,
    save_results,
)
from eval.pixel_density.features import (  # noqa: E402
    feat_dark_ratio_grid,
    feat_histogram,
    feat_histogram_tile,
)
from eval.pixel_density.segmentation import calibrate_penalty, pelt_segment  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

ART_PDF = "data/samples/ART_674.pdf"
HLL_PDF = "data/samples/HLL_363.pdf"
ART_TARGET = 674
HLL_TARGET = 363
DPI = 100

FEATURE_CONFIGS = {
    "grid_8x8": {
        "extractor": lambda img: feat_dark_ratio_grid(img, grid_n=8),
        "dims": 64,
    },
    "histogram_32": {
        "extractor": lambda img: feat_histogram(img, bins=32),
        "dims": 32,
    },
    "histogram_tile_4x4": {
        "extractor": lambda img: feat_histogram_tile(img, grid_n=4, bins=16),
        "dims": 256,
    },
}

PELT_MODELS = ["l2", "rbf"]


def _extract_feature_matrix(
    pages: np.ndarray, extractor: Callable[..., np.ndarray],
) -> np.ndarray:
    """Extract feature vectors for all pages into a matrix.

    Args:
        pages: (n_pages, H, W) uint8 from cache.
        extractor: Function img -> 1-D vector.

    Returns:
        (n_pages, dims) float64 matrix.
    """
    vectors = [extractor(pages[i]) for i in range(pages.shape[0])]
    return np.vstack(vectors)


def _pelt_to_matches(change_points: list[int], n_pages: int) -> list[int]:
    """Convert PELT change-points to cover page indices.

    First page of each segment is a cover. Page 0 is always a cover.
    """
    matches = [0] + [cp for cp in change_points if cp > 0]
    return sorted(set(matches))


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 2: PELT segmentation sweep")
    parser.add_argument("--features", type=str, default=None,
                        help="Comma-separated feature names (default: all)")
    args = parser.parse_args()

    feature_names = (args.features.split(",") if args.features
                     else list(FEATURE_CONFIGS.keys()))

    print("=" * 70)
    print("Phase 2: PELT Segmentation Sweep")
    print(f"Features: {feature_names}")
    print("=" * 70)

    gt_covers = load_art674_gt()
    tess_only = load_tess_only_pages()
    print(f"GT: {len(gt_covers)} covers, {len(tess_only)} TESS-ONLY pages\n")

    art_pages = ensure_cache(ART_PDF, dpi=DPI)

    results_art: list[dict] = []

    for feat_name, pelt_model in product(feature_names, PELT_MODELS):
        if feat_name not in FEATURE_CONFIGS:
            logger.warning("Unknown feature: %s, skipping", feat_name)
            continue

        config = FEATURE_CONFIGS[feat_name]
        logger.info("Extracting %s features...", feat_name)
        matrix = _extract_feature_matrix(art_pages, config["extractor"])

        logger.info("Running PELT (%s, model=%s) on %d pages × %d dims...",
                     feat_name, pelt_model, *matrix.shape)

        t0 = time.perf_counter()

        min_size = 2
        penalty, n_segments = calibrate_penalty(
            matrix, target_docs=ART_TARGET, model=pelt_model, min_size=min_size,
        )

        cps = pelt_segment(matrix, model=pelt_model, min_size=min_size,
                           penalty=penalty)
        matches = _pelt_to_matches(cps, art_pages.shape[0])

        elapsed = time.perf_counter() - t0

        metrics = compute_metrics(matches, gt_covers, ART_TARGET,
                                  tess_only_pages=tess_only)
        result = {
            "params": {
                "features": feat_name,
                "pelt_model": pelt_model,
                "penalty": round(penalty, 4),
                "min_size": min_size,
                "n_segments": n_segments,
            },
            **metrics,
            "time_s": round(elapsed, 2),
        }
        results_art.append(result)

        logger.info("  → matches=%d error=%+d F1=%.3f penalty=%.4f in %.1fs",
                     metrics["matches"], metrics["error"], metrics["f1"],
                     penalty, elapsed)

    results_art.sort(key=lambda r: (-r["f1"], r["abs_error"]))
    report_table(results_art, sort_key="f1", top_n=10)

    if results_art:
        best_f1 = results_art[0]["f1"]
        print("\n--- Gate Check ---")
        print(f"Best F1: {best_f1:.4f} (baseline: 0.922) → "
              f"{'PASS' if best_f1 > 0.922 else 'FAIL'}")

        for r in results_art:
            n_seg = r["params"]["n_segments"]
            if n_seg > ART_TARGET * 1.15:
                logger.warning("Over-segmentation: %s/%s → %d segments "
                               "(%.0f%% over target)",
                               r["params"]["features"], r["params"]["pelt_model"],
                               n_seg, (n_seg / ART_TARGET - 1) * 100)

    results_hll: list[dict] = []
    if Path(HLL_PDF).exists():
        hll_pages = ensure_cache(HLL_PDF, dpi=DPI)
        print("\n--- HLL_363 (PELT calibration convergence check) ---")
        for feat_name, pelt_model in product(feature_names[:2], ["l2"]):
            if feat_name not in FEATURE_CONFIGS:
                continue
            config = FEATURE_CONFIGS[feat_name]
            matrix = _extract_feature_matrix(hll_pages, config["extractor"])
            penalty, n_segments = calibrate_penalty(
                matrix, target_docs=HLL_TARGET, model=pelt_model, min_size=1,
            )
            cps = pelt_segment(matrix, model=pelt_model, min_size=1, penalty=penalty)
            matches = _pelt_to_matches(cps, hll_pages.shape[0])
            metrics = compute_metrics_count_only(matches, HLL_TARGET)
            result = {
                "params": {"features": feat_name, "pelt_model": pelt_model,
                           "penalty": round(penalty, 4)},
                **metrics,
            }
            results_hll.append(result)
            print(f"  {feat_name}/{pelt_model}: segments={n_segments} "
                  f"matches={metrics['matches']} error={metrics['error']:+d}")

    output = {
        "sweep": "pelt_segmentation",
        "timestamp": datetime.now().isoformat(),
        "results_art674": results_art,
        "results_hll363": results_hll,
    }
    save_results(output, "data/pixel_density/sweep_pelt.json")


if __name__ == "__main__":
    main()
