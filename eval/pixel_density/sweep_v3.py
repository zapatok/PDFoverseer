"""PD V3 parameter sweep — floor threshold + consecutive suppression.

Tests floor values on ART_674 (page-level) and 27-PDF corpus (count-level).
Floor=0.0 is the control (V2_RC equivalent).

Usage
-----
    python eval/pixel_density/sweep_v3.py
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
    GENERAL_CORPUS,
    compute_summary,
    cross_validate,
    scorer_v3,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DPI = 100
FLOOR_VALUES = [0.0, 5.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0]
SUPPRESS_OPTIONS = [False, True]


def main() -> None:
    """Run V3 parameter sweep."""
    print("=" * 70)  # noqa: T201
    print("PD V3 Parameter Sweep -- floor + consecutive suppression")  # noqa: T201
    print("=" * 70)  # noqa: T201

    full_corpus = GENERAL_CORPUS + ART_CORPUS  # noqa: F841
    gt_covers = load_art674_gt()
    tess_only = load_tess_only_pages()
    art_pages = ensure_cache("data/samples/ART_674.pdf", dpi=DPI)

    all_results: list[dict] = []
    t_total = time.perf_counter()

    for suppress in SUPPRESS_OPTIONS:
        for floor_val in FLOOR_VALUES:
            label = f"floor={floor_val:.1f},suppress={suppress}"
            logger.info("\n--- %s ---", label)
            t0 = time.perf_counter()

            # 1. ART_674 page-level
            matches_art = scorer_v3(
                art_pages, floor=floor_val, suppress_consecutive=suppress,
            )
            page_metrics = compute_metrics(
                matches_art, gt_covers, 674, tess_only_pages=tess_only,
            )

            # 2. Cross-validation (count-only)
            def _scorer(pages: np.ndarray, f: float = floor_val, s: bool = suppress) -> list[int]:
                return scorer_v3(pages, floor=f, suppress_consecutive=s)

            gen_results = cross_validate(_scorer, GENERAL_CORPUS)
            art_results = cross_validate(_scorer, ART_CORPUS)

            gen_summary = compute_summary(gen_results)
            art_summary = compute_summary(art_results)

            elapsed = time.perf_counter() - t0

            row = {
                "floor": floor_val,
                "suppress": suppress,
                "art674_f1": page_metrics["f1"],
                "art674_precision": page_metrics["precision"],
                "art674_recall": page_metrics["recall"],
                "art674_tp": page_metrics["tp"],
                "art674_fp": page_metrics["fp"],
                "art674_fn": page_metrics["fn"],
                "art674_matches": page_metrics["matches"],
                "art674_tess_only": page_metrics.get("tess_only_recovered", 0),
                "gen_mae": gen_summary["mae"],
                "gen_exact": gen_summary["exact"],
                "art_family_mae": art_summary["mae"],
                "art_family_exact": art_summary["exact"],
                "elapsed": elapsed,
            }
            all_results.append(row)

            print(  # noqa: T201
                f"  {label}: F1={page_metrics['f1']:.4f} "
                f"TP={page_metrics['tp']} FP={page_metrics['fp']} FN={page_metrics['fn']} "
                f"| gen_MAE={gen_summary['mae']:.1f} art_MAE={art_summary['mae']:.1f} "
                f"({elapsed:.1f}s)"
            )

    # Report: sort by F1 desc, then by gen_MAE asc
    print(f"\n{'=' * 100}")  # noqa: T201
    print("SWEEP RESULTS (sorted by ART_674 F1 desc, then gen_MAE asc)")  # noqa: T201
    print(f"{'=' * 100}")  # noqa: T201
    header = (
        f"{'floor':>6} {'supp':>5} | {'F1':>6} {'P':>6} {'R':>6} "
        f"{'TP':>4} {'FP':>4} {'FN':>4} {'TESS':>4} | "
        f"{'gMAE':>5} {'gExact':>6} {'aMAE':>5} {'aExact':>6}"
    )
    print(header)  # noqa: T201
    print("-" * len(header))  # noqa: T201

    sorted_results = sorted(
        all_results,
        key=lambda r: (-r["art674_f1"], r["gen_mae"]),
    )
    for r in sorted_results:
        print(  # noqa: T201
            f"{r['floor']:>6.1f} {str(r['suppress']):>5} | "
            f"{r['art674_f1']:>6.4f} {r['art674_precision']:>6.3f} {r['art674_recall']:>6.3f} "
            f"{r['art674_tp']:>4} {r['art674_fp']:>4} {r['art674_fn']:>4} "
            f"{r['art674_tess_only']:>4} | "
            f"{r['gen_mae']:>5.1f} {r['gen_exact']:>6} {r['art_family_mae']:>5.1f} "
            f"{r['art_family_exact']:>6}"
        )

    # Identify winner
    # Criteria: must not regress gen_MAE vs floor=0.0 control, then maximize F1
    control = next(r for r in all_results if r["floor"] == 0.0 and not r["suppress"])
    control_gen_mae = control["gen_mae"]
    print(f"\nControl (V2_RC): F1={control['art674_f1']:.4f} gen_MAE={control_gen_mae:.1f}")  # noqa: T201

    candidates = [
        r for r in sorted_results
        if r["gen_mae"] <= control_gen_mae + 0.5  # allow 0.5 MAE tolerance
    ]
    if candidates:
        winner = candidates[0]
        print(  # noqa: T201
            f"Winner: floor={winner['floor']:.1f} suppress={winner['suppress']} "
            f"F1={winner['art674_f1']:.4f} gen_MAE={winner['gen_mae']:.1f}"
        )
    else:
        print("No candidate improves over control without regressing gen_MAE")  # noqa: T201

    # Save
    output = {
        "sweep": "pd_v3_floor_suppress",
        "timestamp": datetime.now().isoformat(),
        "control": control,
        "results": all_results,
    }
    save_results(output, "data/pixel_density/sweep_v3.json")
    logger.info("\nTotal time: %.0fs", time.perf_counter() - t_total)


if __name__ == "__main__":
    main()
