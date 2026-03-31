"""
sweep_bilateral.py — Exhaustive parameter sweep for bilateral pixel-density mode.

Sweeps dpi × grid_n × score_fn and ranks results by |matches - target|.

Usage
-----
    python sweep_bilateral.py data/samples/ART_674.pdf --target 674
    python sweep_bilateral.py data/samples/ART_674.pdf --target 674 --save results_bilateral.txt
"""

from __future__ import annotations

import argparse
import sys
import time
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np

from eval.pixel_density.pixel_density import compute_ratios_grid, l2_distance

# ── Parameter space ───────────────────────────────────────────────────────────

DPI_VALUES   = [100]
GRID_VALUES  = [6, 8]
SCORE_FNS    = ["min", "harmonic"]

# ── Score functions ───────────────────────────────────────────────────────────

def bilateral_scores(vectors: list[np.ndarray], score_fn: str) -> np.ndarray:
    """Compute per-page bilateral score using the chosen aggregation function.

    For each page i:
      left  = L2(i-1 → i)   (0 for i=0)
      right = L2(i → i+1)   (0 for i=N-1)
    Edge pages fall back to their single available jump.

    score_fn:
      min      — min(left, right)          AND gate, strictest
      mean     — (left + right) / 2        softer, rewards one strong side
      harmonic — 2*left*right/(left+right) penalises imbalance more than mean
    """
    n = len(vectors)
    left  = np.zeros(n)
    right = np.zeros(n)

    for i in range(1, n):
        left[i] = l2_distance(vectors[i], vectors[i - 1])
    for i in range(n - 1):
        right[i] = l2_distance(vectors[i], vectors[i + 1])

    # Edge fallback
    left[0]    = right[0]
    right[-1]  = left[-1]

    if score_fn == "min":
        return np.minimum(left, right)
    elif score_fn == "mean":
        return (left + right) / 2.0
    elif score_fn == "harmonic":
        denom = left + right
        with np.errstate(invalid="ignore", divide="ignore"):
            h = np.where(denom > 0, 2 * left * right / denom, 0.0)
        return h
    else:
        raise ValueError(f"Unknown score_fn: {score_fn!r}")


def kmeans_matches(scores: np.ndarray) -> tuple[list[int], float]:
    """K-Means k=2 on 1D scores; returns indices of high cluster + threshold."""
    import warnings

    from sklearn.cluster import KMeans
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        km = KMeans(n_clusters=2, random_state=42, n_init="auto").fit(scores.reshape(-1, 1))

    labels  = km.labels_
    centers = km.cluster_centers_.flatten()
    high    = 1 if centers[1] > centers[0] else 0
    low     = 1 - high

    matches = [i for i, lbl in enumerate(labels) if lbl == high]
    if 0 not in matches:
        matches.insert(0, 0)

    low_scores  = scores[labels == low]
    high_scores = scores[labels == high]
    max_low  = float(np.max(low_scores))  if len(low_scores)  > 0 else 0.0
    min_high = float(np.min(high_scores)) if len(high_scores) > 0 else 0.0
    threshold = (max_low + min_high) / 2.0

    return matches, threshold


# ── Sweep ─────────────────────────────────────────────────────────────────────

def run_sweep(pdf_path: str, target: int) -> list[dict]:
    total = len(DPI_VALUES) * len(GRID_VALUES) * len(SCORE_FNS)
    print(f"Sweeping {total} combos on {Path(pdf_path).name}  (target={target})\n")

    # Cache rendered vectors per (dpi, grid_n) — rendering is the expensive part
    cache: dict[tuple[int, int], list[np.ndarray]] = {}
    results: list[dict] = []
    done = 0

    for dpi, grid_n in product(DPI_VALUES, GRID_VALUES):
        key = (dpi, grid_n)
        if key not in cache:
            t0 = time.perf_counter()
            cache[key] = compute_ratios_grid(pdf_path, dpi, grid_n)
            elapsed = time.perf_counter() - t0
            print(f"  rendered dpi={dpi} grid={grid_n}×{grid_n}  ({len(cache[key])} pages, {elapsed:.1f}s)")

        vectors = cache[key]

        for score_fn in SCORE_FNS:
            scores  = bilateral_scores(vectors, score_fn)
            matches, threshold = kmeans_matches(scores)
            error   = abs(len(matches) - target)
            signed  = len(matches) - target

            results.append({
                "dpi":       dpi,
                "grid":      grid_n,
                "score_fn":  score_fn,
                "matches":   len(matches),
                "error":     error,
                "signed":    signed,
                "threshold": threshold,
            })
            done += 1

    results.sort(key=lambda r: (r["error"], r["dpi"], r["grid"]))
    return results


def print_results(results: list[dict], target: int, save_path: str | None = None) -> None:
    header = f"{'rank':>4}  {'dpi':>4}  {'grid':>6}  {'score_fn':>10}  {'matches':>8}  {'signed':>7}  {'error':>6}  {'threshold':>10}"
    sep    = "-" * len(header)
    lines  = [sep, header, sep]

    for rank, r in enumerate(results, 1):
        lines.append(
            f"{rank:>4}  {r['dpi']:>4}  {r['grid']:>4}×{r['grid']:<1}  "
            f"{r['score_fn']:>10}  {r['matches']:>8}  "
            f"{r['signed']:>+7}  {r['error']:>6}  {r['threshold']:>10.4f}"
        )

    lines.append(sep)
    lines.append(f"Target: {target}  |  Best error: {results[0]['error']} matches")
    lines.append(sep)

    output = "\n".join(lines)

    if save_path:
        Path(save_path).write_text(output, encoding="utf-8")
        print(f"Results saved to {save_path}")
    else:
        print(output)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bilateral pixel-density parameter sweep.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument("--target", type=int, required=True,
                        help="Expected number of document cover pages")
    parser.add_argument("--save",   metavar="PATH", default=None,
                        help="Save ranked results table to this file")
    args = parser.parse_args()

    t0      = time.perf_counter()
    results = run_sweep(args.pdf_path, args.target)
    elapsed = time.perf_counter() - t0

    print(f"\nTotal sweep time: {elapsed:.1f}s\n")
    print_results(results, args.target, args.save)


if __name__ == "__main__":
    main()
