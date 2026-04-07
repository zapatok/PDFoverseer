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
        ok = " OK" if isinstance(err, int) and abs(err) <= 15 else "  "
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
