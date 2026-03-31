"""
pixel_density.py — Detect document first pages by pixel darkness density.

Standalone experiment script.  No imports from the main PDFoverseer project.

Scalar mode (default)
---------------------
One dark_ratio scalar per page.  Matching is based on an asymmetric band
[lower, upper] derived from the natural spread of the reference pages.

Grid mode  (--grid NxN)
-----------------------
The page thumbnail is split into an N×N tile grid; each tile produces its own
dark_ratio, giving a vector of length N² per page.  Matching is based on an
asymmetric L2 distance band [lower, upper] derived from the refs' dispersion.

Auto-threshold modes
--------------------
Default   : ref-spread band — derived purely from how much the ref pages
            differ from each other; no period / document-count assumptions.
--period-mode : legacy period-based bisection (kept for comparison).
--threshold   : explicit override (symmetric, as before).

Usage
-----
    python pixel_density.py path/to/file.pdf 1 5 9
    python pixel_density.py path/to/file.pdf 1 5 9 --period-mode
    python pixel_density.py path/to/file.pdf 1 --threshold 0.05
    python pixel_density.py path/to/file.pdf 1 5 9 --save-plot out.png
    python pixel_density.py path/to/file.pdf 1 5 9 --no-plot
    python pixel_density.py path/to/file.pdf 1 3 5 --grid 4x4
    python pixel_density.py path/to/file.pdf 1 3 5 --grid 4x4 --no-plot
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import fitz
import matplotlib.pyplot as plt
import numpy as np


# ═══════════════════════════════════════════════════════════════════════════════
#  SCALAR MODE — pure functions
# ═══════════════════════════════════════════════════════════════════════════════

def dark_ratio(img: np.ndarray) -> float:
    """Fraction of pixels with value < 128 (0 = white, 1 = black)."""
    return float((img < 128).mean())


# ── Ref-spread threshold (new default) ────────────────────────────────────────

def ref_band(
    ratios: list[float],
    ref_indices: list[int],
) -> tuple[float, float, float]:
    """Derive an asymmetric matching band from the refs' natural spread.

    ``ref_value`` is the mean of the reference dark_ratios.
    ``lower`` is the midpoint between ref_min and ref_value.
    ``upper`` is the midpoint between ref_value and ref_max.

    With very similar refs the band is tight; with spread-out refs it opens up.
    Degenerate case (single ref): lower == upper == ref_value.

    Returns
    -------
    ref_value, lower, upper
    """
    ref_values = [ratios[i] for i in ref_indices]
    ref_value = float(np.mean(ref_values))
    ref_min = min(ref_values)
    ref_max = max(ref_values)
    lower = (ref_min + ref_value) / 2
    upper = (ref_value + ref_max) / 2
    return ref_value, lower, upper


def find_matches_in_band(
    ratios: list[float],
    lower: float,
    upper: float,
) -> list[int]:
    """Return page indices whose dark_ratio falls in [lower, upper]."""
    return [i for i, r in enumerate(ratios) if lower <= r <= upper]


# ── Break detection (Option 4, --break-mode) ──────────────────────────────────

def page_breaks(
    ratios: list[float],
    min_drop: float,
) -> list[int]:
    """Detect pages where the *decrease* in dark_ratio from the previous page
    exceeds *min_drop*.

    By definition, page 1 (index 0) is always returned as a match, as it represents
    the start of the first document.

    If ratio[i] - ratio[i-1] <= -min_drop, index i is considered a break.
    """
    matches = [0]
    for i in range(1, len(ratios)):
        drop = ratios[i-1] - ratios[i]
        if drop >= min_drop:
            matches.append(i)
    return matches


# ── Period-based threshold (legacy, --period-mode) ────────────────────────────

def find_matches_by_value(
    ratios: list[float],
    ref_value: float,
    threshold: float,
) -> list[int]:
    epsilon = 1e-9
    return [i for i, r in enumerate(ratios) if abs(r - ref_value) <= threshold + epsilon]


def find_matches(
    ratios: list[float],
    ref_idx: int,
    threshold: float,
) -> list[int]:
    return find_matches_by_value(ratios, ratios[ref_idx], threshold)


def auto_threshold(
    ratios: list[float],
    ref_value: float,
    ref_indices: list[int],
) -> tuple[float, float, int]:
    """Binary-search for the threshold that yields ~(n/period) matches."""
    n = len(ratios)
    sorted_refs = sorted(ref_indices)
    if len(sorted_refs) >= 2:
        gaps = [sorted_refs[i + 1] - sorted_refs[i] for i in range(len(sorted_refs) - 1)]
        period = float(np.median(gaps))
    else:
        period = 4.0
    expected = max(int(round(n / period)), 1)
    lo = 0.0
    hi = max(abs(r - ref_value) for r in ratios)
    epsilon = 1e-9
    for _ in range(60):
        mid = (lo + hi) / 2
        count = sum(1 for r in ratios if abs(r - ref_value) <= mid + epsilon)
        if count < expected:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2, period, expected


# ═══════════════════════════════════════════════════════════════════════════════
#  GRID MODE — pure functions
# ═══════════════════════════════════════════════════════════════════════════════

def dark_ratio_grid(img: np.ndarray, grid_n: int) -> np.ndarray:
    """Split *img* into a grid_n × grid_n tile grid; return a 1-D float64
    vector of length grid_n² with the dark_ratio of each tile (row-major)."""
    h, w = img.shape[:2]
    result = np.empty(grid_n * grid_n, dtype=np.float64)
    for row in range(grid_n):
        r0 = (row * h) // grid_n
        r1 = ((row + 1) * h) // grid_n
        for col in range(grid_n):
            c0 = (col * w) // grid_n
            c1 = ((col + 1) * w) // grid_n
            tile = img[r0:r1, c0:c1]
            result[row * grid_n + col] = float((tile < 128).mean()) if tile.size else 0.0
    return result


def median_vector(vectors: list[np.ndarray]) -> np.ndarray:
    """Component-wise median across a list of equal-length vectors."""
    return np.median(np.stack(vectors, axis=0), axis=0)


def l2_distance(v: np.ndarray, ref: np.ndarray) -> float:
    """Euclidean distance between two vectors."""
    return float(np.linalg.norm(v - ref))


# ── Ref-spread threshold — grid (new default) ─────────────────────────────────

def ref_band_vector(
    vectors: list[np.ndarray],
    ref_vector: np.ndarray,
    ref_indices: list[int],
) -> tuple[float, float]:
    """Derive an asymmetric L2 distance band from the refs' natural dispersion.

    Computes the L2 distance from each ref page to *ref_vector* (the median
    reference), then:
        dist_mean   = mean of those distances
        lower = midpoint(dist_min, dist_mean)
        upper = midpoint(dist_mean, dist_max)

    A page matches if lower ≤ L2(page, ref_vector) ≤ upper.

    Returns
    -------
    lower, upper
    """
    distances = [l2_distance(vectors[i], ref_vector) for i in ref_indices]
    dist_mean = float(np.mean(distances))
    dist_min = min(distances)
    dist_max = max(distances)
    lower = (dist_min + dist_mean) / 2
    upper = (dist_mean + dist_max) / 2
    return lower, upper


def find_matches_vector_in_band(
    vectors: list[np.ndarray],
    ref_vector: np.ndarray,
    lower: float,
    upper: float,
) -> list[int]:
    """Return page indices whose L2 distance to *ref_vector* is in [lower, upper]."""
    return [i for i, v in enumerate(vectors) if lower <= l2_distance(v, ref_vector) <= upper]


# ── Break detection — grid (Option 4, --break-mode) ───────────────────────────

def page_breaks_vector(
    vectors: list[np.ndarray],
    min_l2_jump: float,
) -> list[int]:
    """Detect pages where the *L2 distance* from the previous page's vector
    exceeds *min_l2_jump*.

    Unlike scalars where we look for a drop in darkness, vectors don't have a
    simple "drop" direction. We just look for any large spatial change.
    Page 1 (index 0) is always returned.
    """
    matches = [0]
    for i in range(1, len(vectors)):
        jump = l2_distance(vectors[i], vectors[i-1])
        if jump >= min_l2_jump:
            matches.append(i)
    return matches


# ── Clustering — grid (Option 3, --cluster-mode) ───────────────────────────

def cluster_pages_vector(vectors: list[np.ndarray]) -> tuple[list[int], float, np.ndarray]:
    """Cluster all page vectors into 2 groups using KMeans.
    
    Returns the indices of the smaller cluster (assumed to be cover pages),
    and the scalar threshold equivalent (the maximum distance from the cover
    cluster center to its furthest member).
    """
    from sklearn.cluster import KMeans
    import warnings
    # Suppress sklearn's memory leak warning on Windows with MKL
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        X = np.stack(vectors)
        kmeans = KMeans(n_clusters=2, random_state=42, n_init="auto").fit(X)
        
    labels = kmeans.labels_
    count_0 = np.sum(labels == 0)
    count_1 = np.sum(labels == 1)
    
    # Cover pages are assumed to be the minority class
    cover_label = 0 if count_0 < count_1 else 1
    matches = [i for i, lbl in enumerate(labels) if lbl == cover_label]
    
    # Calculate threshold-equivalent (max distance to centroid) for plotting
    cover_center = kmeans.cluster_centers_[cover_label]
    max_dist = max(l2_distance(vectors[m], cover_center) for m in matches)
    
    # Pre-emptively fix if clustering separated something wildly wrong
    # (e.g. if the "minority" is just 2 blank pages at the end)
    # But for now, we just trust k=2
    return matches, max_dist, cover_center


# ── Bilateral (N-1, N, N+1 window, --bilateral-mode) ─────────────────────────

def bilateral_mode_vector(
    vectors: list[np.ndarray],
) -> tuple[list[int], float, float]:
    """Delta clustering using a 3-page window: min(L2(N-1→N), L2(N→N+1)).

    A true cover page is a visual outlier on *both* sides:
      - high L2 from the last slide of the previous talk (left jump)
      - high L2 from the first content slide of the new talk (right jump)

    A disruptive infographic inside a talk has a high jump on one side but
    a low jump on the other (same author). Taking min() enforces the AND
    condition, filtering those false positives out.

    Edge pages (i=0, i=N-1) fall back to their single available jump.
    """
    if len(vectors) < 2:
        return [0], 0.0, 0.0

    n = len(vectors)
    left_jumps  = np.zeros(n)
    right_jumps = np.zeros(n)

    for i in range(1, n):
        left_jumps[i] = l2_distance(vectors[i], vectors[i - 1])
    for i in range(n - 1):
        right_jumps[i] = l2_distance(vectors[i], vectors[i + 1])

    # Edge fallback: use the only available side
    left_jumps[0]   = right_jumps[0]
    right_jumps[-1] = left_jumps[-1]

    bilateral = np.minimum(left_jumps, right_jumps)

    from sklearn.cluster import KMeans
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        X = bilateral.reshape(-1, 1)
        kmeans = KMeans(n_clusters=2, random_state=42, n_init="auto").fit(X)

    labels  = kmeans.labels_
    centers = kmeans.cluster_centers_.flatten()

    high_label = 1 if centers[1] > centers[0] else 0
    low_label  = 1 - high_label

    matches = [i for i, lbl in enumerate(labels) if lbl == high_label]

    if 0 not in matches:
        matches.insert(0, 0)

    low_scores  = bilateral[labels == low_label]
    high_scores = bilateral[labels == high_label]

    max_low  = float(np.max(low_scores))  if len(low_scores)  > 0 else 0.0
    min_high = float(np.min(high_scores)) if len(high_scores) > 0 else 0.0
    threshold = (max_low + min_high) / 2.0

    return matches, threshold, bilateral


# ── Hybrid (Option 4 + Option 3, --hybrid-mode) ──────────────────────────────

def hybrid_mode_vector(
    vectors: list[np.ndarray]
) -> tuple[list[int], float, float]:
    """Combines Break detection with Clustering (Delta Clustering).
    
    Instead of clustering absolute page vectors, we cluster the 1D sequence
    of *L2 distance jumps* between adjacent pages.
    
    1. Calculate L2 jump for every page i relative to i-1.
    2. Cluster the 1D array of jumps into 2 groups (High Jump vs Low Jump).
    3. The cluster with the higher centroid is the "Break" cluster.
    
    Returns: (matches, threshold_jump, max_jump_in_low_cluster)
    """
    if len(vectors) < 2:
        return [0], 0.0, 0.0

    # Calculate all jumps (page 0 has jump 0 or could just use a massive fake jump.
    # Let's use 0.0 for page 0 so it stays in the "low" cluster, we just hardcode 0
    # as a match at the end if we want).
    jumps = np.zeros(len(vectors))
    for i in range(1, len(vectors)):
        jumps[i] = l2_distance(vectors[i], vectors[i-1])

    from sklearn.cluster import KMeans
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # KMeans expects 2D array: shape (n_samples, n_features=1)
        X_jumps = jumps.reshape(-1, 1)
        kmeans = KMeans(n_clusters=2, random_state=42, n_init="auto").fit(X_jumps)
        
    labels = kmeans.labels_
    centers = kmeans.cluster_centers_.flatten()
    
    # The cluster with the higher average jump is our 'break' cluster
    high_label = 1 if centers[1] > centers[0] else 0
    low_label  = 0 if high_label == 1 else 1
    
    matches = [i for i, lbl in enumerate(labels) if lbl == high_label]
    
    # Always include 0 as a cover page heuristically if it's missing
    if 0 not in matches:
        matches.insert(0, 0)
        
    # Find the boundary (threshold) between the two clusters
    # E.g. max jump in the 'low' cluster
    low_jumps = jumps[labels == low_label]
    high_jumps = jumps[labels == high_label]
    
    max_low = float(np.max(low_jumps)) if len(low_jumps) > 0 else 0.0
    min_high = float(np.min(high_jumps)) if len(high_jumps) > 0 else 0.0
    
    # We return the midpoint between the highest non-break and the lowest break
    threshold = (max_low + min_high) / 2.0
    
    return matches, threshold, max_low


# ── Period-based threshold — grid (legacy, --period-mode) ────────────────────

def find_matches_vector(
    vectors: list[np.ndarray],
    ref_vector: np.ndarray,
    threshold: float,
) -> list[int]:
    """Return page indices whose L2 distance to *ref_vector* ≤ threshold."""
    epsilon = 1e-9
    return [i for i, v in enumerate(vectors) if l2_distance(v, ref_vector) <= threshold + epsilon]


def auto_threshold_vector(
    vectors: list[np.ndarray],
    ref_vector: np.ndarray,
    ref_indices: list[int],
) -> tuple[float, float, int]:
    """Same bisection strategy as *auto_threshold*, but using L2 distances."""
    n = len(vectors)
    sorted_refs = sorted(ref_indices)
    if len(sorted_refs) >= 2:
        gaps = [sorted_refs[i + 1] - sorted_refs[i] for i in range(len(sorted_refs) - 1)]
        period = float(np.median(gaps))
    else:
        period = 4.0
    expected = max(int(round(n / period)), 1)
    distances = [l2_distance(v, ref_vector) for v in vectors]
    lo = 0.0
    hi = max(distances) if distances else 1.0
    epsilon = 1e-9
    for _ in range(60):
        mid = (lo + hi) / 2
        count = sum(1 for d in distances if d <= mid + epsilon)
        if count < expected:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2, period, expected


# ═══════════════════════════════════════════════════════════════════════════════
#  I/O layer — PDF rendering
# ═══════════════════════════════════════════════════════════════════════════════

def render_thumbnail(page: fitz.Page, dpi: int = 15) -> np.ndarray:
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY, alpha=False)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w)


def compute_ratios(pdf_path: str, dpi: int) -> list[float]:
    doc = fitz.open(pdf_path)
    ratios: list[float] = []
    for page in doc:
        img = render_thumbnail(page, dpi)
        ratios.append(dark_ratio(img))
    doc.close()
    return ratios


def compute_ratios_grid(pdf_path: str, dpi: int, grid_n: int) -> list[np.ndarray]:
    """Like *compute_ratios* but returns a list of grid_n² vectors."""
    doc = fitz.open(pdf_path)
    vectors: list[np.ndarray] = []
    for page in doc:
        img = render_thumbnail(page, dpi)
        vectors.append(dark_ratio_grid(img, grid_n))
    doc.close()
    return vectors


# ═══════════════════════════════════════════════════════════════════════════════
#  Visualisation — scalar
# ═══════════════════════════════════════════════════════════════════════════════

def show_plot(
    ratios: list[float],
    ref_indices: list[int],
    ref_value: float,
    matches: list[int],
    lower: float,
    upper: float,
    save_path: str | None = None,
) -> None:
    pages = list(range(1, len(ratios) + 1))
    fig, ax = plt.subplots(figsize=(16, 4))
    ax.plot(pages, ratios, color="grey", linewidth=0.5, label="dark ratio")
    ax.axhspan(
        lower, upper,
        alpha=0.15, color="blue",
        label=f"band [{lower:.4f} – {upper:.4f}] (mean={ref_value:.4f})",
    )
    for i, ref_idx in enumerate(ref_indices):
        label = f"ref pages ({', '.join(str(r + 1) for r in ref_indices)})" if i == 0 else None
        ax.axvline(ref_idx + 1, color="blue", linewidth=1.2, alpha=0.7, label=label)
    match_pages  = [m + 1     for m in matches]
    match_ratios = [ratios[m] for m in matches]
    ax.scatter(match_pages, match_ratios, color="red", s=4, zorder=5, label=f"matches ({len(matches)})")
    ax.set_xlabel("Page")
    ax.set_ylabel("Dark ratio")
    ax.set_title(
        f"Pixel density — {len(matches)} matches / {len(ratios)} pages "
        f"(band [{lower:.4f} – {upper:.4f}], {len(ref_indices)} refs)"
    )
    ax.legend(loc="upper right")
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150)
        plt.close(fig)
        print(f"Plot saved to {save_path}")
    else:
        plt.show()


# ═══════════════════════════════════════════════════════════════════════════════
#  Visualisation — grid (Y = L2 distance to ref)
# ═══════════════════════════════════════════════════════════════════════════════

def show_plot_grid(
    vectors: list[np.ndarray],
    ref_indices: list[int],
    ref_vector: np.ndarray,
    matches: list[int],
    lower: float,
    upper: float,
    grid_n: int,
    save_path: str | None = None,
) -> None:
    distances = [l2_distance(v, ref_vector) for v in vectors]
    pages = list(range(1, len(vectors) + 1))
    fig, ax = plt.subplots(figsize=(16, 4))
    ax.plot(pages, distances, color="grey", linewidth=0.5, label="L2 distance to ref")
    ax.axhspan(
        lower, upper,
        alpha=0.15, color="blue",
        label=f"band [{lower:.4f} – {upper:.4f}]",
    )
    for i, ref_idx in enumerate(ref_indices):
        label = f"ref pages ({', '.join(str(r + 1) for r in ref_indices)})" if i == 0 else None
        ax.axvline(ref_idx + 1, color="blue", linewidth=1.2, alpha=0.7, label=label)
    match_pages = [m + 1        for m in matches]
    match_dists = [distances[m] for m in matches]
    ax.scatter(match_pages, match_dists, color="red", s=4, zorder=5, label=f"matches ({len(matches)})")
    ax.set_xlabel("Page")
    ax.set_ylabel("L2 distance to ref vector")
    ax.set_title(
        f"Pixel density grid {grid_n}×{grid_n} — {len(matches)} matches / {len(vectors)} pages "
        f"(band [{lower:.4f} – {upper:.4f}])"
    )
    ax.legend(loc="upper right")
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150)
        plt.close(fig)
        print(f"Plot saved to {save_path}")
    else:
        plt.show()


# ═══════════════════════════════════════════════════════════════════════════════
#  Visualisation — break mode (scalar/grid unified mostly)
# ═══════════════════════════════════════════════════════════════════════════════

def show_plot_breaks(
    values: list[float],
    matches: list[int],
    min_jump: float,
    title: str,
    ylabel: str,
    save_path: str | None = None,
) -> None:
    """Plot for --break-mode. *values* is either ratios (scalar) or inter-page L2 distances (grid)."""
    pages = list(range(1, len(values) + 1))
    fig, ax = plt.subplots(figsize=(16, 4))
    ax.plot(pages, values, color="grey", linewidth=0.5, label=ylabel)
    
    match_pages  = [m + 1     for m in matches]
    match_values = [values[m] for m in matches]
    ax.scatter(match_pages, match_values, color="red", s=4, zorder=5, label=f"matches ({len(matches)})")
    
    ax.set_xlabel("Page")
    ax.set_ylabel(ylabel)
    ax.set_title(f"{title} — {len(matches)} matches / {len(values)} pages (jump threshold: {min_jump:.4f})")
    ax.legend(loc="upper right")
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150)
        plt.close(fig)
        print(f"Plot saved to {save_path}")
    else:
        plt.show()


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_grid(value: str) -> int:
    """Parse 'NxN' or 'NXN' and return N (must be equal on both sides)."""
    parts = value.lower().split("x")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"--grid must be NxN, got {value!r}")
    try:
        rows, cols = int(parts[0]), int(parts[1])
    except ValueError:
        raise argparse.ArgumentTypeError(f"--grid must be NxN integers, got {value!r}")
    if rows != cols or rows < 1:
        raise argparse.ArgumentTypeError(f"--grid requires equal N≥1 (e.g. 4x4), got {value!r}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect document first pages by pixel darkness density.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument("ref_page", type=int, nargs="*",
                        help="Reference page number(s) (1-indexed); ignored in --break-mode/--cluster-mode")
    parser.add_argument("--dpi",         type=int,   default=50)
    parser.add_argument("--threshold",   type=float, default=None,
                        help="Manual override: symmetric scalar diff, max L2, or min jump")
    parser.add_argument("--period-mode", action="store_true",
                        help="Use legacy period-based bisection instead of ref-spread band")
    parser.add_argument("--break-mode",  action="store_true",
                        help="Use consecutive-page drop-off detection (Option 4)")
    parser.add_argument("--cluster-mode", action="store_true",
                        help="Use unsupervised k-means(k=2) clustering (Option 3). Grid mode only.")
    parser.add_argument("--hybrid-mode", action="store_true",
                        help="Combine Option 4 (find breaks) and Option 3 (cluster those breaks). Grid only.")
    parser.add_argument("--bilateral-mode", action="store_true",
                        help="3-page window: cluster min(L2(N-1→N), L2(N→N+1)). Filters infographic false positives. Grid only.")
    parser.add_argument("--grid",        type=_parse_grid, default=None, metavar="NxN",
                        help="Enable grid mode: split each page into an N×N tile grid and "
                             "match by L2 distance on the N²-dim vector (e.g. --grid 4x4)")
    parser.add_argument("--save-plot",   metavar="PATH", default=None)
    parser.add_argument("--no-plot",     action="store_true")
    args = parser.parse_args()

    grid_n: int | None = args.grid

    if (args.cluster_mode or args.hybrid_mode or args.bilateral_mode) and not grid_n:
        parser.error("--cluster-mode, --hybrid-mode, and --bilateral-mode require --grid NxN to be specified")

    # ── render ────────────────────────────────────────────────────────────────
    mode_label = f"grid {grid_n}×{grid_n}" if grid_n else "scalar"
    print(f"Rendering {Path(args.pdf_path).name} at {args.dpi} DPI  [{mode_label}] ...")

    if grid_n:
        vectors = compute_ratios_grid(args.pdf_path, args.dpi, grid_n)
        n_pages = len(vectors)
    else:
        ratios = compute_ratios(args.pdf_path, args.dpi)
        n_pages = len(ratios)

    if not args.break_mode and not args.cluster_mode and not args.hybrid_mode and not args.bilateral_mode and not args.ref_page:
        parser.error("ref_page is required unless --break-mode, --cluster-mode, or --hybrid-mode is specified")

    # ── validate ref pages ────────────────────────────────────────────────────
    ref_indices: list[int] = []
    if not (args.break_mode or args.cluster_mode or args.hybrid_mode or args.bilateral_mode):
        for rp in args.ref_page:
            idx = rp - 1
            if idx < 0 or idx >= n_pages:
                print(f"Error: ref_page {rp} is out of range (PDF has {n_pages} pages).", file=sys.stderr)
                sys.exit(1)
            ref_indices.append(idx)

    # ═════════════════════════════════════════════════════════════════════════
    #  GRID PATH
    # ═════════════════════════════════════════════════════════════════════════
    if grid_n:
        if args.bilateral_mode:
            matches, threshold, bilateral = bilateral_mode_vector(vectors)
            print(f"Bilateral Delta Clustering (grid {grid_n}×{grid_n}): K-Means on min(left_L2, right_L2)")
            print(f"Threshold between clusters: {threshold:.4f}")
            print(f"Matches: {len(matches)} / {n_pages} pages")
            if not args.no_plot:
                show_plot_breaks(
                    bilateral.tolist(), matches, threshold,
                    f"Pixel density bilateral {grid_n}×{grid_n}",
                    "min(L2 left, L2 right)",
                    args.save_plot,
                )
            return

        if args.hybrid_mode:
            matches, threshold, max_low = hybrid_mode_vector(vectors)
            print(f"Hybrid Delta Clustering (grid 4+3): K-Means on L2 Jumps")
            print(f"Algorithm separated jumps precisely at L2 = {threshold:.4f} (max interior jump was {max_low:.4f})")
            print(f"Matches: {len(matches)} / {n_pages} pages")
            if not args.no_plot:
                # We reuse the break plot logic because this is fundamentally a jump analysis
                show_plot_breaks(vectors, matches, threshold, grid_n, args.save_plot)
            return

        if args.cluster_mode:
            matches, max_dist, cover_center = cluster_pages_vector(vectors)
            print(f"Cluster-mode (grid): separated k=2, cover cluster size = {len(matches)}")
            print(f"Centroid tolerance equivalent: L2 ≤ {max_dist:.4f}")
            print(f"Matches: {len(matches)} / {n_pages} pages")
            if not args.no_plot:
                show_plot_grid(vectors, [], cover_center, matches, 0.0, max_dist, grid_n, args.save_plot)
            return

        if args.break_mode:
            min_jump = args.threshold if args.threshold is not None else 0.20
            matches = page_breaks_vector(vectors, min_jump)
            print(f"Break-mode (grid): L2 jump ≥ {min_jump:.4f}")
            print(f"Matches: {len(matches)} / {n_pages} pages")
            if not args.no_plot:
                distances = [0.0] + [l2_distance(vectors[i], vectors[i-1]) for i in range(1, n_pages)]
                show_plot_breaks(distances, matches, min_jump, f"Pixel density grid {grid_n}×{grid_n} breaks", "L2 jump from prev page", args.save_plot)
            return

        ref_vecs   = [vectors[i] for i in ref_indices]
        ref_vector = median_vector(ref_vecs)

        if args.threshold is not None:
            # Manual symmetric override: L2 ≤ threshold
            threshold = args.threshold
            lower_l2 = 0.0
            upper_l2 = threshold
            matches = find_matches_vector(vectors, ref_vector, threshold)
            print(f"Threshold (manual): L2 ≤ {threshold:.4f}")

        elif args.period_mode:
            threshold, period, expected = auto_threshold_vector(vectors, ref_vector, ref_indices)
            lower_l2 = 0.0
            upper_l2 = threshold
            matches = find_matches_vector(vectors, ref_vector, threshold)
            print(f"Period-mode: period ~{period:.1f} -> ~{expected} expected -> threshold L2 ≤ {threshold:.4f}")

        else:
            lower_l2, upper_l2 = ref_band_vector(vectors, ref_vector, ref_indices)
            matches = find_matches_vector_in_band(vectors, ref_vector, lower_l2, upper_l2)
            for rp, idx in zip(args.ref_page, ref_indices):
                d = l2_distance(vectors[idx], ref_vector)
                print(f"  ref p{rp}: L2={d:.4f}")
            print(f"Ref-spread band: [{lower_l2:.4f} – {upper_l2:.4f}]")

        print(f"Matches: {len(matches)} / {n_pages} pages")

        if not args.no_plot:
            show_plot_grid(vectors, ref_indices, ref_vector, matches,
                           lower_l2, upper_l2, grid_n, args.save_plot)

    # ═════════════════════════════════════════════════════════════════════════
    #  SCALAR PATH
    # ═════════════════════════════════════════════════════════════════════════
    else:
        if args.break_mode:
            min_drop = args.threshold if args.threshold is not None else 0.15
            matches = page_breaks(ratios, min_drop)
            print(f"Break-mode (scalar): dark_ratio drop ≥ {min_drop:.4f}")
            print(f"Matches: {len(matches)} / {n_pages} pages")
            if not args.no_plot:
                show_plot_breaks(ratios, matches, min_drop, "Pixel density scalar breaks", "Dark ratio", args.save_plot)
            return

        for rp, idx in zip(args.ref_page, ref_indices):
            print(f"  ref p{rp}: dark_ratio={ratios[idx]:.4f}")

        if args.threshold is not None:
            # Manual symmetric override
            ref_value = float(np.mean([ratios[i] for i in ref_indices]))
            threshold = args.threshold
            lower_s = ref_value - threshold
            upper_s = ref_value + threshold
            matches = find_matches_by_value(ratios, ref_value, threshold)
            print(f"Threshold (manual): ±{threshold:.4f}  [{lower_s:.4f} – {upper_s:.4f}]")

        elif args.period_mode:
            ref_value = float(np.median([ratios[i] for i in ref_indices]))
            threshold, period, expected = auto_threshold(ratios, ref_value, ref_indices)
            lower_s = ref_value - threshold
            upper_s = ref_value + threshold
            matches = find_matches_by_value(ratios, ref_value, threshold)
            print(f"Period-mode: period ~{period:.1f} -> ~{expected} expected "
                  f"-> ±{threshold:.4f}  [{lower_s:.4f} – {upper_s:.4f}]")

        else:
            ref_value, lower_s, upper_s = ref_band(ratios, ref_indices)
            matches = find_matches_in_band(ratios, lower_s, upper_s)
            print(f"Ref-spread band: [{lower_s:.4f} – {upper_s:.4f}]  (mean={ref_value:.4f})")

        print(f"Matches: {len(matches)} / {n_pages} pages")

        if not args.no_plot:
            show_plot(ratios, ref_indices, ref_value if 'ref_value' in dir() else
                      float(np.mean([ratios[i] for i in ref_indices])),
                      matches, lower_s, upper_s, args.save_plot)


if __name__ == "__main__":
    main()
