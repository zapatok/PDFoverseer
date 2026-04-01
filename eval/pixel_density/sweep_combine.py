# eval/pixel_density/sweep_combine.py
"""Phase 4: Signal combination sweep.

Combines best detectors from Phases 1-3 via score fusion, voting,
and set operations.

Usage
-----
    python eval/pixel_density/sweep_combine.py
    python eval/pixel_density/sweep_combine.py --scores-dir data/pixel_density
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np  # noqa: E402

from eval.pixel_density.evaluate import (  # noqa: E402
    compute_metrics,
    load_art674_gt,
    load_tess_only_pages,
    report_table,
    save_results,
)
from eval.pixel_density.sweep_bilateral import kmeans_matches  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

ART_TARGET = 674


def _normalize_01(scores: np.ndarray) -> np.ndarray:
    """Min-max normalize scores to [0, 1]."""
    mn, mx = scores.min(), scores.max()
    if mx - mn < 1e-12:
        return np.zeros_like(scores)
    return (scores - mn) / (mx - mn)


def score_fusion(
    sources: dict[str, np.ndarray],
    weights: dict[str, float],
) -> np.ndarray:
    """Weighted score fusion.

    Args:
        sources: {name: normalized_scores_array}.
        weights: {name: weight}. Must sum to ~1.0.

    Returns:
        Combined score array.
    """
    combined = np.zeros_like(next(iter(sources.values())))
    for name, scores in sources.items():
        combined += weights.get(name, 0.0) * scores
    return combined


def voting(
    source_matches: dict[str, set[int]],
    min_votes: int,
) -> list[int]:
    """Voting combination: page is cover if >= min_votes detectors agree.

    Args:
        source_matches: {name: set of detected cover pages}.
        min_votes: Minimum detectors that must agree.

    Returns:
        Sorted list of cover page indices.
    """
    all_pages: set[int] = set()
    for matches in source_matches.values():
        all_pages |= matches

    result = []
    for page in sorted(all_pages):
        votes = sum(1 for matches in source_matches.values() if page in matches)
        if votes >= min_votes:
            result.append(page)

    if 0 not in result:
        result.insert(0, 0)
    return result


def set_operation(
    source_matches: dict[str, set[int]],
    op: str,
) -> list[int]:
    """Set intersection or union of detector outputs.

    Args:
        source_matches: {name: set of detected cover pages}.
        op: "intersection" or "union".

    Returns:
        Sorted list of cover page indices.
    """
    sets = list(source_matches.values())
    if op == "intersection":
        result = sets[0].copy()
        for s in sets[1:]:
            result &= s
    elif op == "union":
        result = sets[0].copy()
        for s in sets[1:]:
            result |= s
    else:
        raise ValueError(f"Unknown op: {op!r}")

    result_list = sorted(result)
    if 0 not in result_list:
        result_list.insert(0, 0)
    return result_list


def _weight_grid(n_sources: int, step: float = 0.1) -> list[dict[int, float]]:
    """Generate weight combinations on the simplex.

    Args:
        n_sources: Number of sources to weight.
        step: Weight increment.

    Returns:
        List of weight dicts {source_index: weight}.
    """
    steps = int(1.0 / step)
    if n_sources == 2:
        return [
            {0: i * step, 1: 1.0 - i * step}
            for i in range(steps + 1)
        ]
    if n_sources == 3:
        combos: list[dict[int, float]] = []
        for i in range(steps + 1):
            for j in range(steps + 1 - i):
                k = steps - i - j
                combos.append({0: i * step, 1: j * step, 2: k * step})
        return combos

    coarse = max(step, 0.2)
    coarse_steps = int(1.0 / coarse)
    combos = []
    for i in range(coarse_steps + 1):
        for j in range(coarse_steps + 1 - i):
            remaining = 1.0 - i * coarse - j * coarse
            if n_sources == 4:
                for k_val in range(int(remaining / coarse) + 1):
                    l_val = remaining - k_val * coarse
                    if l_val >= -0.01:
                        combos.append({
                            0: i * coarse, 1: j * coarse,
                            2: k_val * coarse, 3: max(0, l_val),
                        })
    return combos


def main() -> None:
    """Run Phase 4 signal combination sweep."""
    parser = argparse.ArgumentParser(
        description="Phase 4: Signal combination sweep")
    parser.add_argument("--scores-dir", default="data/pixel_density",
                        help="Directory with phase result JSONs")
    args = parser.parse_args()

    print("=" * 70)
    print("Phase 4: Signal Combination Sweep")
    print("=" * 70)

    gt_covers = load_art674_gt()
    tess_only = load_tess_only_pages()
    print(f"GT: {len(gt_covers)} covers, {len(tess_only)} TESS-ONLY pages\n")

    scores_dir = Path(args.scores_dir)

    # ── Load per-page scores from each phase ────────────────────────────────
    sources_scores: dict[str, np.ndarray] = {}

    # Load baseline bilateral (always available)
    from eval.pixel_density.sweep_bilateral import bilateral_scores as bs_l2  # noqa: E402
    from eval.pixel_density.sweep_preprocessing import compute_variant_vectors  # noqa: E402

    vectors = compute_variant_vectors("data/samples/ART_674.pdf", "clahe", 100, 8)
    sources_scores["bilateral_l2"] = _normalize_01(bs_l2(vectors, "min"))

    # Phase 1: chi² bilateral
    chi2_path = scores_dir / "sweep_chi2.json"
    if chi2_path.exists():
        chi2_data = json.loads(chi2_path.read_text(encoding="utf-8"))
        if "best_config_scores" in chi2_data:
            sources_scores["chi2"] = _normalize_01(
                np.array(chi2_data["best_config_scores"]))
            logger.info("Loaded chi2 scores from sweep_chi2.json")

    # Phase 2: PELT (convert change-points to soft scores)
    pelt_path = scores_dir / "sweep_pelt.json"
    if pelt_path.exists():
        from eval.pixel_density.segmentation import pelt_to_scores  # noqa: E402

        pelt_data = json.loads(pelt_path.read_text(encoding="utf-8"))
        if pelt_data.get("results_art674"):
            best_pelt = pelt_data["results_art674"][0]
            if "change_points" in best_pelt:
                pelt_scores = pelt_to_scores(
                    best_pelt["change_points"],
                    n_pages=len(vectors), alpha=1.0,
                )
                sources_scores["pelt"] = _normalize_01(pelt_scores)
                logger.info("Loaded PELT scores from sweep_pelt.json")

    # Phase 3: multi-descriptor bilateral
    md_path = scores_dir / "sweep_multidesc.json"
    if md_path.exists():
        md_data = json.loads(md_path.read_text(encoding="utf-8"))
        if "best_config_scores" in md_data:
            sources_scores["multidesc"] = _normalize_01(
                np.array(md_data["best_config_scores"]))
            logger.info("Loaded multidesc scores from sweep_multidesc.json")

    source_names = list(sources_scores.keys())
    logger.info("Sources loaded: %s", source_names)
    if len(source_names) < 2:
        print("WARNING: Need at least 2 sources for combination. "
              "Run Phases 1-3 first.")
        return

    # ── Score Fusion ────────────────────────────────────────────────────────
    results: list[dict] = []
    weight_combos = _weight_grid(len(source_names), step=0.1)
    logger.info("Score fusion: %d weight combos", len(weight_combos))

    for wc in weight_combos:
        weights = {source_names[i]: wc[i] for i in range(len(source_names))}
        combined = score_fusion(sources_scores, weights)
        matches_km, _ = kmeans_matches(combined)
        metrics = compute_metrics(matches_km, gt_covers, ART_TARGET,
                                  tess_only_pages=tess_only)
        results.append({
            "params": {"strategy": "score_fusion", "weights": weights,
                       "threshold": "kmeans_k2"},
            **metrics,
        })

    # ── Voting ──────────────────────────────────────────────────────────────
    source_matches_sets: dict[str, set[int]] = {}
    for name, scores in sources_scores.items():
        matches_km, _ = kmeans_matches(scores)
        source_matches_sets[name] = set(matches_km)

    for min_votes in range(1, len(source_names) + 1):
        label = ("unanimous" if min_votes == len(source_names)
                 else f"majority_{min_votes}")
        matches = voting(source_matches_sets, min_votes)
        metrics = compute_metrics(matches, gt_covers, ART_TARGET,
                                  tess_only_pages=tess_only)
        results.append({
            "params": {"strategy": f"voting_{label}"},
            **metrics,
        })

    # ── Set operations ──────────────────────────────────────────────────────
    for op in ["intersection", "union"]:
        matches = set_operation(source_matches_sets, op)
        metrics = compute_metrics(matches, gt_covers, ART_TARGET,
                                  tess_only_pages=tess_only)
        results.append({
            "params": {"strategy": op},
            **metrics,
        })

    results.sort(key=lambda r: (-r["f1"], r["abs_error"]))
    report_table(results, sort_key="f1", top_n=15)

    if results:
        best_f1 = results[0]["f1"]
        print("\n--- Gate Check ---")
        print(f"Best ensemble F1: {best_f1:.4f}")
        print("(Compare against best individual from Phases 1-3)")

    output = {
        "sweep": "signal_combination",
        "timestamp": datetime.now().isoformat(),
        "sources": source_names,
        "results_art674": results,
    }
    save_results(output, "data/pixel_density/sweep_combine.json")


if __name__ == "__main__":
    main()
