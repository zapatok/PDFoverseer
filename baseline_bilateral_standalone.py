"""
baseline_bilateral_standalone.py -- Best standalone pixel density doc count.

Comprehensive sweep of preprocessing variants x score functions x threshold
methods.  Reports the best operating point measured against VLM ground truth.

Metrics:
  - |error| = |matches - 674|
  - VLM precision = TP / (TP + FP)  where TP = matches that ARE vlm covers
  - VLM recall    = TP / (TP + FN)  where FN = vlm covers NOT in matches
  - F1 = harmonic mean of precision and recall

Usage
-----
    python baseline_bilateral_standalone.py
    python baseline_bilateral_standalone.py --quick   # skip CLAHE (saves ~2min)
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans

from sweep_bilateral import bilateral_scores
from sweep_preprocessing import compute_variant_vectors

PDF_PATH    = "data/samples/ART_674.pdf"
VLM_FIXTURE = "eval/fixtures/real/ART_674.json"
TARGET      = 674
DPI         = 100
GRID        = 8

SCORE_FNS = ["harmonic", "min", "mean"]

# Variants worth testing (otsu variants excluded — too many FPs)
VARIANT_NAMES = ["baseline", "clahe", "red_channel", "ink_sum", "ink_only", "clahe_ink_sum"]


# ── VLM ground truth ─────────────────────────────────────────────────────────


def load_vlm_covers() -> set[int]:
    """Return 0-based page indices where VLM says curr==1."""
    data = json.loads(Path(VLM_FIXTURE).read_text(encoding="utf-8"))
    return {r["pdf_page"] - 1 for r in data["reads"] if r.get("curr") == 1}


# ── Threshold methods ────────────────────────────────────────────────────────


def threshold_kmeans_k2(scores: np.ndarray) -> tuple[list[int], str]:
    """Standard K-Means k=2; return high-cluster indices."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        km = KMeans(n_clusters=2, random_state=42, n_init="auto")
        km.fit(scores.reshape(-1, 1))
    centers = km.cluster_centers_.flatten()
    high = 1 if centers[1] > centers[0] else 0
    matches = [i for i, lbl in enumerate(km.labels_) if lbl == high]
    # Always include page 0
    if 0 not in matches:
        matches.insert(0, 0)
    return matches, "kmeans_k2"


def threshold_percentile_target(
    scores: np.ndarray, target: int = TARGET,
) -> tuple[list[int], str]:
    """Pick the percentile that yields closest to target matches."""
    n = len(scores)
    # Target percentile: we want ~target pages above it
    target_pct = 100.0 * (1.0 - target / n)

    best_matches: list[int] = []
    best_error = float("inf")
    best_pct = 0.0

    # Search in 0.1 increments around target_pct
    for pct_10x in range(max(0, int(target_pct * 10) - 50),
                         min(1000, int(target_pct * 10) + 50)):
        pct = pct_10x / 10.0
        thresh = np.percentile(scores, pct)
        matches = [i for i in range(n) if scores[i] >= thresh]
        error = abs(len(matches) - target)
        if error < best_error:
            best_error = error
            best_matches = matches
            best_pct = pct

    # Always include page 0
    if 0 not in best_matches:
        best_matches.insert(0, 0)
    return best_matches, f"pct_{best_pct:.1f}"


def threshold_adaptive_kmeans(
    scores: np.ndarray, target: int = TARGET,
) -> tuple[list[int], str]:
    """K-Means k=3, pick the top-N clusters that get closest to target."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        km = KMeans(n_clusters=3, random_state=42, n_init="auto")
        km.fit(scores.reshape(-1, 1))

    centers = km.cluster_centers_.flatten()
    sorted_clusters = np.argsort(centers)  # low to high

    # Try top-1, top-2
    best_matches: list[int] = []
    best_error = float("inf")
    best_label = ""

    for n_top in [1, 2]:
        top_clusters = set(sorted_clusters[-n_top:].tolist())
        matches = [i for i, lbl in enumerate(km.labels_) if lbl in top_clusters]
        error = abs(len(matches) - target)
        if error < best_error:
            best_error = error
            best_matches = matches
            best_label = f"kmeans_k3_top{n_top}"

    if 0 not in best_matches:
        best_matches.insert(0, 0)
    return best_matches, best_label


THRESHOLD_METHODS = [
    threshold_kmeans_k2,
    threshold_percentile_target,
    threshold_adaptive_kmeans,
]


# ── Evaluation ───────────────────────────────────────────────────────────────


def evaluate(
    matches: list[int],
    vlm_covers: set[int],
    target: int = TARGET,
) -> dict:
    """Compute all metrics for a set of detected covers."""
    match_set = set(matches)
    tp = len(match_set & vlm_covers)
    fp = len(match_set - vlm_covers)
    fn = len(vlm_covers - match_set)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "matches": len(matches),
        "error": len(matches) - target,
        "abs_error": abs(len(matches) - target),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true",
                        help="Skip CLAHE variant (saves ~2 min rendering)")
    args = parser.parse_args()

    variants = [v for v in VARIANT_NAMES if not (args.quick and v == "clahe")]

    print("=" * 70)
    print("Standalone Bilateral Pixel Density — Best Baseline")
    print(f"PDF: {PDF_PATH}  Target: {TARGET} docs  DPI: {DPI}  Grid: {GRID}x{GRID}")
    print("=" * 70)

    vlm_covers = load_vlm_covers()
    print(f"VLM ground truth: {len(vlm_covers)} covers\n")

    # Pre-render all variant vectors
    variant_vectors: dict[str, list[np.ndarray]] = {}
    for vname in variants:
        print(f"Rendering {vname}...")
        t0 = time.perf_counter()
        variant_vectors[vname] = compute_variant_vectors(PDF_PATH, vname, DPI, GRID)
        print(f"  {len(variant_vectors[vname])} pages in {time.perf_counter()-t0:.1f}s")

    # Sweep: variant x score_fn x threshold_method
    results: list[dict] = []

    for vname in variants:
        vectors = variant_vectors[vname]
        for score_fn in SCORE_FNS:
            scores = bilateral_scores(vectors, score_fn)

            for thresh_fn in THRESHOLD_METHODS:
                matches, thresh_label = thresh_fn(scores)
                metrics = evaluate(matches, vlm_covers)
                result = {
                    "variant": vname,
                    "score_fn": score_fn,
                    "threshold": thresh_label,
                    **metrics,
                }
                results.append(result)

    # Sort by F1 (primary), then abs_error (secondary)
    results.sort(key=lambda r: (-r["f1"], r["abs_error"]))

    # Report
    print(f"\n{'='*100}")
    print("Results (sorted by F1, then |error|)")
    print(f"{'='*100}")
    hdr = (f"{'#':>3}  {'Variant':<12} {'Score':>8} {'Threshold':<16} "
           f"{'Match':>5} {'Error':>6} {'Prec':>6} {'Rec':>6} {'F1':>6}  "
           f"{'TP':>4} {'FP':>4} {'FN':>4}")
    print(hdr)
    print("-" * len(hdr))

    for rank, r in enumerate(results, 1):
        print(f"{rank:>3}  {r['variant']:<12} {r['score_fn']:>8} {r['threshold']:<16} "
              f"{r['matches']:>5} {r['error']:>+6} "
              f"{r['precision']:>6.3f} {r['recall']:>6.3f} {r['f1']:>6.3f}  "
              f"{r['tp']:>4} {r['fp']:>4} {r['fn']:>4}")

    # Best by different criteria
    print(f"\n{'='*70}")
    print("Best by criterion:")
    best_f1 = results[0]
    best_error = min(results, key=lambda r: r["abs_error"])
    best_precision = max(results, key=lambda r: r["precision"])
    best_recall = max(results, key=lambda r: r["recall"])

    for label, r in [("F1", best_f1), ("|error|", best_error),
                     ("Precision", best_precision), ("Recall", best_recall)]:
        print(f"  {label:<12}: {r['variant']}/{r['score_fn']}/{r['threshold']}  "
              f"matches={r['matches']}  error={r['error']:+d}  "
              f"P={r['precision']:.3f}  R={r['recall']:.3f}  F1={r['f1']:.3f}")

    print(f"{'='*70}")

    # Save
    out_path = "data/pixel_density/standalone_baseline.json"
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(
        json.dumps(results, indent=2, default=float), encoding="utf-8",
    )
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
