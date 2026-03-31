"""
characterize_density.py -- Stage 1: Density regime analysis for bilateral detector.

Confirms or refutes the non-stationarity hypothesis: does the document have
distinct density segments where bilateral fails because global K-Means assigns
cover peaks to the wrong cluster?

Exports ``detect_density_segments()`` for reuse in Stage 3 (local K-Means).

Usage
-----
    python characterize_density.py
    python characterize_density.py --bimodality   # also run Task 1.2 check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from eval.pixel_density.pixel_density import compute_ratios, compute_ratios_grid  # noqa: E402
from eval.pixel_density.sweep_bilateral import bilateral_scores, kmeans_matches  # noqa: E402

PDF_PATH     = "data/samples/ART_674.pdf"
TESS_FIXTURE = "eval/fixtures/real/ART_674_tess.json"
VLM_FIXTURE  = "eval/fixtures/real/ART_674.json"
DPI          = 100
GRID         = 8
SCORE_FN     = "harmonic"
PLOT_PATH    = "data/pixel_density/density_regime_plot.png"


# ═══════════════════════════════════════════════════════════════════════════════
#  Importable: segment detection
# ═══════════════════════════════════════════════════════════════════════════════


def rolling_mean(values: np.ndarray, window: int = 21) -> np.ndarray:
    """Centre-aligned rolling mean with edge padding."""
    kernel = np.ones(window) / window
    # Pad edges to keep array length
    pad = window // 2
    padded = np.pad(values, (pad, pad), mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def detect_density_segments(
    dark_ratios: np.ndarray,
    delta: float = 0.04,
    window: int = 50,
) -> list[tuple[int, int]]:
    """Detect density segments via rolling-mean changepoints.

    Args:
        dark_ratios: Per-page dark ratio (scalar), length N.
        delta: Minimum shift in rolling mean to trigger a segment boundary.
        window: Rolling mean window for changepoint detection.

    Returns:
        List of (start_page_0b, end_page_0b) tuples (inclusive on both ends).
    """
    rm = rolling_mean(dark_ratios, window=window)

    # Find changepoints: pages where rolling mean shifts by > delta
    boundaries = [0]
    for i in range(1, len(rm)):
        if abs(rm[i] - rm[i - 1]) > delta:
            # Only add if sufficiently far from last boundary
            if i - boundaries[-1] >= window // 2:
                boundaries.append(i)

    # Close last segment
    segments = []
    for j in range(len(boundaries)):
        start = boundaries[j]
        end = boundaries[j + 1] - 1 if j + 1 < len(boundaries) else len(dark_ratios) - 1
        segments.append((start, end))

    return segments


# ═══════════════════════════════════════════════════════════════════════════════
#  3-way diff (shared with inspect_bilateral.py)
# ═══════════════════════════════════════════════════════════════════════════════


def load_tess_covers() -> list[int]:
    """Return 0-based page indices where Tesseract read curr==1."""
    data = json.loads(Path(TESS_FIXTURE).read_text(encoding="utf-8"))
    return sorted(r["pdf_page"] - 1 for r in data["reads"] if r.get("curr") == 1)


def load_vlm_map() -> dict[int, dict]:
    """Load VLM GT: 1-based pdf_page -> {curr, total}."""
    data = json.loads(Path(VLM_FIXTURE).read_text(encoding="utf-8"))
    return {
        r["pdf_page"]: {"curr": r.get("curr"), "total": r.get("total")}
        for r in data["reads"]
    }


def three_way_diff(
    bilateral_0b: list[int], tess_0b: list[int],
) -> tuple[list[int], list[int], list[int]]:
    b, t = set(bilateral_0b), set(tess_0b)
    return sorted(b & t), sorted(b - t), sorted(t - b)


# ═══════════════════════════════════════════════════════════════════════════════
#  Plotting
# ═══════════════════════════════════════════════════════════════════════════════


def plot_regimes(
    dark_ratios: np.ndarray,
    rm: np.ndarray,
    segments: list[tuple[int, int]],
    bilat_scores: np.ndarray,
    threshold: float,
    shared: list[int],
    bilateral_only: list[int],
    tess_only: list[int],
    save_path: str,
) -> None:
    """Two-panel plot: density + bilateral scores with segment boundaries."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(20, 8), sharex=True)
    pages = np.arange(len(dark_ratios))

    # Panel 1: dark_ratio
    ax1.scatter(pages, dark_ratios, s=0.3, c="gray", alpha=0.4, label="raw dark_ratio")
    ax1.plot(pages, rm, c="black", linewidth=1.0, label="rolling mean")

    # Segment boundaries
    for seg_start, _seg_end in segments[1:]:  # skip the first (page 0)
        ax1.axvline(seg_start, c="orange", linewidth=0.8, linestyle="--", alpha=0.7)
        ax2.axvline(seg_start, c="orange", linewidth=0.8, linestyle="--", alpha=0.7)

    # Mark page groups
    if tess_only:
        ax1.scatter(tess_only, dark_ratios[tess_only], s=15, c="red",
                    marker="^", zorder=5, label=f"TESS-ONLY ({len(tess_only)})")
    if bilateral_only:
        ax1.scatter(bilateral_only, dark_ratios[bilateral_only], s=10, c="blue",
                    marker="o", zorder=4, label=f"BILATERAL-ONLY ({len(bilateral_only)})")
    if shared:
        ax1.scatter(shared, dark_ratios[shared], s=3, c="green",
                    zorder=3, label=f"SHARED ({len(shared)})")

    ax1.set_ylabel("dark_ratio")
    ax1.set_title("Pixel Density Regime Analysis (ART_674)")
    ax1.legend(fontsize=8, loc="upper right")

    # Panel 2: bilateral harmonic scores
    ax2.scatter(pages, bilat_scores, s=0.3, c="gray", alpha=0.4, label="bilateral score")
    ax2.axhline(threshold, c="red", linewidth=0.8, linestyle="-", alpha=0.8,
                label=f"threshold={threshold:.4f}")

    if tess_only:
        ax2.scatter(tess_only, bilat_scores[tess_only], s=15, c="red",
                    marker="^", zorder=5, label="TESS-ONLY")
    if bilateral_only:
        ax2.scatter(bilateral_only, bilat_scores[bilateral_only], s=10, c="blue",
                    marker="o", zorder=4, label="BILATERAL-ONLY")
    if shared:
        ax2.scatter(shared, bilat_scores[shared], s=3, c="green",
                    zorder=3, label="SHARED")

    ax2.set_ylabel("bilateral harmonic score")
    ax2.set_xlabel("page index (0-based)")
    ax2.legend(fontsize=8, loc="upper right")

    plt.tight_layout()
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    print(f"\nPlot saved to {save_path}")


# ═══════════════════════════════════════════════════════════════════════════════
#  Segment summary
# ═══════════════════════════════════════════════════════════════════════════════


def segment_summary(
    segments: list[tuple[int, int]],
    rm: np.ndarray,
    shared: list[int],
    bilateral_only: list[int],
    tess_only: list[int],
) -> None:
    """Print per-segment statistics."""
    shared_set = set(shared)
    bilat_set = set(bilateral_only)
    tess_set = set(tess_only)

    print("\nSegment Map:")
    print(f"  {'Seg':>3}  {'Pages':<16}  {'Length':>6}  {'RM_min':>7}  {'RM_max':>7}  {'RM_mean':>7}  "
          f"{'SHARED':>6}  {'B-ONLY':>6}  {'T-ONLY':>6}")
    print(f"  {'-'*3}  {'-'*16}  {'-'*6}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*6}  {'-'*6}  {'-'*6}")

    for i, (s, e) in enumerate(segments, 1):
        seg_rm = rm[s:e + 1]
        n_shared = sum(1 for p in range(s, e + 1) if p in shared_set)
        n_bilat = sum(1 for p in range(s, e + 1) if p in bilat_set)
        n_tess = sum(1 for p in range(s, e + 1) if p in tess_set)
        print(f"  {i:>3}  {s:>6}-{e:<8}  {e - s + 1:>6}  {seg_rm.min():>7.4f}  "
              f"{seg_rm.max():>7.4f}  {seg_rm.mean():>7.4f}  "
              f"{n_shared:>6}  {n_bilat:>6}  {n_tess:>6}")


# ═══════════════════════════════════════════════════════════════════════════════
#  Task 1.2: Bimodality check
# ═══════════════════════════════════════════════════════════════════════════════


def bimodality_check(
    segments: list[tuple[int, int]],
    tess_only: list[int],
    bilat_scores: np.ndarray,
    vlm_map: dict[int, dict],
) -> None:
    """For each segment containing TESS-ONLY pages, check bimodality of
    bilateral scores for VLM covers vs non-covers."""
    tess_set = set(tess_only)

    print("\n\nBimodality Check (Task 1.2)")
    print("=" * 60)

    for i, (s, e) in enumerate(segments, 1):
        seg_tess = [p for p in range(s, e + 1) if p in tess_set]
        if not seg_tess:
            continue

        print(f"\nSegment {i} (pages {s}-{e}):")

        # Classify all pages in segment using VLM GT
        covers = []
        non_covers = []
        for p in range(s, e + 1):
            vlm = vlm_map.get(p + 1)  # 1-based lookup
            if vlm is None:
                continue
            if vlm["curr"] == 1:
                covers.append(p)
            else:
                non_covers.append(p)

        if not covers or not non_covers:
            print(f"  Insufficient data: {len(covers)} covers, {len(non_covers)} non-covers")
            continue

        cover_scores = bilat_scores[covers]
        non_cover_scores = bilat_scores[non_covers]

        print(f"  Covers (VLM curr=1):     {len(covers):>4} pages, "
              f"bilateral scores: min={cover_scores.min():.4f}  "
              f"max={cover_scores.max():.4f}  mean={cover_scores.mean():.4f}")
        print(f"  Non-covers (VLM curr>1): {len(non_covers):>4} pages, "
              f"bilateral scores: min={non_cover_scores.min():.4f}  "
              f"max={non_cover_scores.max():.4f}  mean={non_cover_scores.mean():.4f}")

        # Overlap: fraction of covers scoring below median non-cover score
        median_nc = float(np.median(non_cover_scores))
        overlap = float(np.mean(cover_scores < median_nc))
        print(f"  Median non-cover score: {median_nc:.4f}")
        print(f"  Overlap: {overlap:.1%}  (fraction of covers below median non-cover)")

        bimodal = overlap < 0.50
        print(f"  Bimodal: {'YES' if bimodal else 'NO'}")

        # Also check: could a local threshold separate them?
        max_nc = float(non_cover_scores.max())
        min_cover = float(cover_scores.min())
        gap = min_cover - max_nc
        print(f"  Score gap (min_cover - max_non_cover): {gap:+.4f}  "
              f"({'separable' if gap > 0 else 'overlapping'})")


# ═══════════════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════════════


def main() -> None:
    parser = argparse.ArgumentParser(description="Density regime analysis for bilateral detector.")
    parser.add_argument("--bimodality", action="store_true",
                        help="Also run Task 1.2 bimodality check")
    args = parser.parse_args()

    print("=" * 60)
    print("Stage 1: Density Regime Characterization")
    print("=" * 60)

    # Step 1: Compute dark_ratios (scalar) for rolling mean
    print("\nStep 1: Computing per-page dark_ratio (scalar)...")
    import time
    t0 = time.perf_counter()
    dark_ratios = np.array(compute_ratios(PDF_PATH, DPI))
    print(f"  {len(dark_ratios)} pages in {time.perf_counter() - t0:.1f}s")

    # Step 2: Rolling mean + changepoint detection
    print("\nStep 2: Rolling mean + changepoint detection")
    rm = rolling_mean(dark_ratios, window=21)
    segments = detect_density_segments(dark_ratios, delta=0.04, window=50)
    print(f"  Detected {len(segments)} segments  ({len(segments) - 1} boundaries)")
    for j, (s, e) in enumerate(segments, 1):
        print(f"    Segment {j}: pages {s}-{e}  ({e - s + 1} pages)  "
              f"rm_mean={rm[s:e + 1].mean():.4f}")

    # Step 3: Bilateral scores + 3-way diff
    print("\nStep 3: Bilateral scores")
    t0 = time.perf_counter()
    vectors = compute_ratios_grid(PDF_PATH, DPI, GRID)
    print(f"  Grid vectors: {len(vectors)} pages in {time.perf_counter() - t0:.1f}s")

    bilat_scores = bilateral_scores(vectors, SCORE_FN)
    matches, threshold = kmeans_matches(bilat_scores)
    print(f"  bilateral: {len(matches)} covers  threshold={threshold:.4f}")

    tess_covers = load_tess_covers()
    shared, bilateral_only, tess_only = three_way_diff(matches, tess_covers)
    print(f"  SHARED={len(shared)}  BILATERAL-ONLY={len(bilateral_only)}  TESS-ONLY={len(tess_only)}")

    # Step 4: Segment summary
    segment_summary(segments, rm, shared, bilateral_only, tess_only)

    # Step 5: Plot
    print("\nStep 5: Plotting...")
    plot_regimes(dark_ratios, rm, segments, bilat_scores, threshold,
                 shared, bilateral_only, tess_only, PLOT_PATH)

    # Task 1.2: Bimodality check
    if args.bimodality:
        vlm_map = load_vlm_map()
        bimodality_check(segments, tess_only, bilat_scores, vlm_map)


if __name__ == "__main__":
    main()
