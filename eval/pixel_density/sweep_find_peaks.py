"""PD find_peaks — prominence sweep + cross-validation on ART family.

Tests prominence values on ART_674 (page-level) and the 6-PDF ART corpus
(count-level). Also compares against V2_RC baseline.

Usage
-----
    python eval/pixel_density/sweep_find_peaks.py
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
    scorer_rescue_c,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DPI = 100
PROMINENCE_VALUES = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0, 1.3, 1.5, 2.0]
SHIFT_OPTIONS = [False, True]

ART_FULL_CORPUS: list[tuple[str, str, int]] = [
    ("ART_674", "data/samples/ART_674.pdf", 674),
    *ART_CORPUS,
]


def main() -> None:
    """Run find_peaks prominence sweep on ART corpus."""
    print("=" * 70)  # noqa: T201
    print("PD find_peaks -- prominence sweep on ART family")  # noqa: T201
    print("=" * 70)  # noqa: T201

    gt_covers = load_art674_gt()
    tess_only = load_tess_only_pages()
    art_pages = ensure_cache("data/samples/ART_674.pdf", dpi=DPI)

    all_results: list[dict] = []
    t_total = time.perf_counter()

    # V2_RC baseline
    logger.info("\n--- V2_RC baseline ---")
    m_baseline = scorer_rescue_c(art_pages)
    bl_metrics = compute_metrics(m_baseline, gt_covers, 674, tess_only_pages=tess_only)

    def _baseline_scorer(pages: np.ndarray) -> list[int]:
        return scorer_rescue_c(pages)

    bl_xval = cross_validate(_baseline_scorer, ART_FULL_CORPUS)
    bl_mae = sum(r["abs_error"] for r in bl_xval) / len(bl_xval)
    bl_exact = sum(1 for r in bl_xval if r["abs_error"] == 0)

    all_results.append({
        "method": "V2_RC",
        "prominence": None,
        "shift": None,
        "art674_f1": bl_metrics["f1"],
        "art674_precision": bl_metrics["precision"],
        "art674_recall": bl_metrics["recall"],
        "art674_tp": bl_metrics["tp"],
        "art674_fp": bl_metrics["fp"],
        "art674_fn": bl_metrics["fn"],
        "art674_matches": bl_metrics["matches"],
        "art674_tess_only": bl_metrics.get("tess_only_recovered", 0),
        "art_mae": bl_mae,
        "art_exact": bl_exact,
    })
    print(  # noqa: T201
        f"  V2_RC: F1={bl_metrics['f1']:.4f} "
        f"TP={bl_metrics['tp']} FP={bl_metrics['fp']} FN={bl_metrics['fn']} "
        f"docs={bl_metrics['matches']} | art_MAE={bl_mae:.1f} exact={bl_exact}"
    )

    # find_peaks sweep
    for shift in SHIFT_OPTIONS:
        for prom in PROMINENCE_VALUES:
            label = f"prom={prom:.1f},shift={shift}"
            t0 = time.perf_counter()

            matches = scorer_find_peaks(
                art_pages, prominence=prom, shift_covers=shift,
            )
            page_metrics = compute_metrics(
                matches, gt_covers, 674, tess_only_pages=tess_only,
            )

            def _scorer(
                pages: np.ndarray, p: float = prom, s: bool = shift,
            ) -> list[int]:
                return scorer_find_peaks(pages, prominence=p, shift_covers=s)

            xval = cross_validate(_scorer, ART_FULL_CORPUS)
            mae = sum(r["abs_error"] for r in xval) / len(xval)
            exact = sum(1 for r in xval if r["abs_error"] == 0)
            elapsed = time.perf_counter() - t0

            row = {
                "method": "find_peaks",
                "prominence": prom,
                "shift": shift,
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
    print(f"\n{'=' * 100}")  # noqa: T201
    print("RESULTS (sorted by F1 desc, then art_MAE asc)")  # noqa: T201
    print(f"{'=' * 100}")  # noqa: T201
    header = (
        f"{'method':<12} {'prom':>5} {'shift':>5} | {'F1':>6} {'P':>6} {'R':>6} "
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
        prom_s = f"{r['prominence']:.1f}" if r["prominence"] is not None else "n/a"
        shift_s = str(r["shift"]) if r["shift"] is not None else "n/a"
        print(  # noqa: T201
            f"{r['method']:<12} {prom_s:>5} {shift_s:>5} | "
            f"{r['art674_f1']:>6.4f} {r['art674_precision']:>6.3f} "
            f"{r['art674_recall']:>6.3f} {r['art674_tp']:>4} {r['art674_fp']:>4} "
            f"{r['art674_fn']:>4} {r['art674_matches']:>4} | "
            f"{r['art_mae']:>5.1f} {r['art_exact']:>6}"
        )

    # Per-PDF doc count table for winner vs baseline
    print(f"\n{'=' * 70}")  # noqa: T201
    print("PER-PDF DOC COUNT: V2_RC vs find_peaks winner")  # noqa: T201
    print(f"{'=' * 70}")  # noqa: T201

    winner = sorted_results[0]
    prom_w = winner.get("prominence", 0.5) or 0.5
    shift_w = winner.get("shift", True) if winner.get("shift") is not None else True

    print(f"{'PDF':<14} {'Tgt':>4} | {'V2_RC':>5} {'err':>5} | {'winner':>6} {'err':>5}")  # noqa: T201
    print("-" * 55)  # noqa: T201
    for name, path, target in ART_FULL_CORPUS:
        pages = ensure_cache(path, dpi=DPI)
        m_bl = scorer_rescue_c(pages)
        m_win = scorer_find_peaks(pages, prominence=prom_w, shift_covers=shift_w)
        print(  # noqa: T201
            f"{name:<14} {target:>4} | {len(m_bl):>5} {len(m_bl)-target:>+5} "
            f"| {len(m_win):>6} {len(m_win)-target:>+5}"
        )

    # Save
    output = {
        "sweep": "pd_find_peaks",
        "timestamp": datetime.now().isoformat(),
        "results": all_results,
        "winner": {
            "prominence": prom_w,
            "shift": shift_w,
            "f1": winner["art674_f1"],
            "art_mae": winner["art_mae"],
        },
    }
    save_results(output, "data/pixel_density/sweep_find_peaks.json")
    logger.info("\nTotal time: %.0fs", time.perf_counter() - t_total)


if __name__ == "__main__":
    main()
