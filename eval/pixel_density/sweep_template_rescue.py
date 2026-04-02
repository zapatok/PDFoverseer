"""PD template rescue — threshold sweep on ART corpus.

Tests rescue threshold values with find_peaks+shift as the base.
Validates that rescue improves ART_674 without regressing small ARTs.

Usage
-----
    python eval/pixel_density/sweep_template_rescue.py
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np  # noqa: E402

from eval.pixel_density.cache import ensure_cache  # noqa: E402
from eval.pixel_density.evaluate import (  # noqa: E402
    compute_metrics,
    load_art674_gt,
    load_tess_only_pages,
    save_results,
)
from eval.pixel_density.sweep_rescue import (  # noqa: E402
    ART_CORPUS,
    cross_validate,
    scorer_find_peaks,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DPI = 100
RESCUE_THRESHOLDS = [0.0, 0.30, 0.35, 0.38, 0.40, 0.42, 0.45, 0.48, 0.50, 0.55]

ART_FULL_CORPUS: list[tuple[str, str, int]] = [
    ("ART_674", "data/samples/ART_674.pdf", 674),
    *ART_CORPUS,
]


def main() -> None:
    """Run template rescue threshold sweep on ART corpus."""
    print("=" * 70)  # noqa: T201
    print("PD template rescue -- threshold sweep on ART family")  # noqa: T201
    print("=" * 70)  # noqa: T201

    gt_covers = load_art674_gt()
    tess_only = load_tess_only_pages()
    art_pages = ensure_cache("data/samples/ART_674.pdf", dpi=DPI)

    all_results: list[dict] = []
    t_total = time.perf_counter()

    for thresh in RESCUE_THRESHOLDS:
        label = f"rescue={thresh:.2f}"
        t0 = time.perf_counter()

        # ART_674 page-level
        matches = scorer_find_peaks(art_pages, rescue_threshold=thresh)
        page_metrics = compute_metrics(
            matches, gt_covers, 674, tess_only_pages=tess_only,
        )

        # ART corpus cross-validation (doc count)
        def _scorer(
            pages: np.ndarray, t: float = thresh,
        ) -> list[int]:
            return scorer_find_peaks(pages, rescue_threshold=t)

        xval = cross_validate(_scorer, ART_FULL_CORPUS)
        mae = sum(r["abs_error"] for r in xval) / len(xval)
        exact = sum(1 for r in xval if r["abs_error"] == 0)
        elapsed = time.perf_counter() - t0

        row = {
            "rescue_threshold": thresh,
            "art674_f1": page_metrics["f1"],
            "art674_precision": page_metrics["precision"],
            "art674_recall": page_metrics["recall"],
            "art674_tp": page_metrics["tp"],
            "art674_fp": page_metrics["fp"],
            "art674_fn": page_metrics["fn"],
            "art674_matches": page_metrics["matches"],
            "art674_tess_only": page_metrics.get("tess_only_recovered", 0),
            "art_mae": mae,
            "art_exact": exact,
            "elapsed": elapsed,
        }
        all_results.append(row)

        print(  # noqa: T201
            f"  {label}: F1={page_metrics['f1']:.4f} "
            f"TP={page_metrics['tp']} FP={page_metrics['fp']} "
            f"FN={page_metrics['fn']} docs={page_metrics['matches']} "
            f"| art_MAE={mae:.1f} exact={exact} ({elapsed:.1f}s)"
        )

    # Results table
    print(f"\n{'=' * 90}")  # noqa: T201
    print("RESULTS (sorted by F1 desc, then art_MAE asc)")  # noqa: T201
    print(f"{'=' * 90}")  # noqa: T201
    header = (
        f"{'thresh':>7} | {'F1':>6} {'P':>6} {'R':>6} "
        f"{'TP':>4} {'FP':>4} {'FN':>4} {'docs':>4} | "
        f"{'aMAE':>5} {'aExact':>6}"
    )
    print(header)  # noqa: T201
    print("-" * len(header))  # noqa: T201

    sorted_results = sorted(
        all_results,
        key=lambda r: (-r["art674_f1"], r["art_mae"]),
    )
    for r in sorted_results:
        print(  # noqa: T201
            f"{r['rescue_threshold']:>7.2f} | "
            f"{r['art674_f1']:>6.4f} {r['art674_precision']:>6.3f} "
            f"{r['art674_recall']:>6.3f} {r['art674_tp']:>4} {r['art674_fp']:>4} "
            f"{r['art674_fn']:>4} {r['art674_matches']:>4} | "
            f"{r['art_mae']:>5.1f} {r['art_exact']:>6}"
        )

    # Per-PDF doc count
    print(f"\n{'=' * 60}")  # noqa: T201
    print("PER-PDF DOC COUNT")  # noqa: T201
    print(f"{'=' * 60}")  # noqa: T201

    # Compare: no rescue vs best rescue
    winner = sorted_results[0]
    best_thresh = winner["rescue_threshold"]

    print(f"{'PDF':<14} {'Tgt':>4} | {'no_rsc':>6} {'err':>5} | {'rescue':>6} {'err':>5}")  # noqa: T201
    print("-" * 55)  # noqa: T201
    for name, path, target in ART_FULL_CORPUS:
        pages = ensure_cache(path, dpi=DPI)
        m_ctrl = scorer_find_peaks(pages, rescue_threshold=0.0)
        m_best = scorer_find_peaks(pages, rescue_threshold=best_thresh)
        print(  # noqa: T201
            f"{name:<14} {target:>4} | {len(m_ctrl):>6} {len(m_ctrl)-target:>+5} "
            f"| {len(m_best):>6} {len(m_best)-target:>+5}"
        )

    # Save
    output = {
        "sweep": "pd_template_rescue",
        "timestamp": datetime.now().isoformat(),
        "base": "find_peaks p=0.5 d=2 shift=True sim=0.99",
        "results": all_results,
        "winner": {
            "rescue_threshold": best_thresh,
            "f1": winner["art674_f1"],
            "art_mae": winner["art_mae"],
        },
    }
    save_results(output, "data/pixel_density/sweep_template_rescue.json")
    logger.info("\nTotal time: %.0fs", time.perf_counter() - t_total)


if __name__ == "__main__":
    main()
