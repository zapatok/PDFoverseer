"""
sweep_preprocessing.py -- Stage 2: Preprocessing variant sweep for bilateral detector.

Tests CLAHE, red channel, per-cell Otsu, and CLAHE+Otsu variants against the
baseline bilateral detector.  Reports score distributions for TESS-ONLY, SHARED,
and BILATERAL-ONLY page groups.

Usage
-----
    python sweep_preprocessing.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import cv2
import fitz
import numpy as np

from eval.pixel_density.sweep_bilateral import bilateral_scores, kmeans_matches

PDF_PATH     = "data/samples/ART_674.pdf"
TESS_FIXTURE = "eval/fixtures/real/ART_674_tess.json"
DPI          = 100
GRID         = 8
SCORE_FN     = "harmonic"
TARGET       = 674


# ═══════════════════════════════════════════════════════════════════════════════
#  Rendering
# ═══════════════════════════════════════════════════════════════════════════════


def render_page_gray(page: fitz.Page, dpi: int) -> np.ndarray:
    """Render page as grayscale uint8 array."""
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY, alpha=False)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w)


def render_page_rgb(page: fitz.Page, dpi: int) -> np.ndarray:
    """Render page as RGB uint8 array (H, W, 3)."""
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB, alpha=False)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, 3)


# ═══════════════════════════════════════════════════════════════════════════════
#  Grid computation variants
# ═══════════════════════════════════════════════════════════════════════════════


def grid_baseline(img_gray: np.ndarray, grid_n: int) -> np.ndarray:
    """Baseline: fixed < 128 threshold on grayscale."""
    h, w = img_gray.shape
    result = np.empty(grid_n * grid_n, dtype=np.float64)
    for row in range(grid_n):
        r0, r1 = (row * h) // grid_n, ((row + 1) * h) // grid_n
        for col in range(grid_n):
            c0, c1 = (col * w) // grid_n, ((col + 1) * w) // grid_n
            tile = img_gray[r0:r1, c0:c1]
            result[row * grid_n + col] = float((tile < 128).mean()) if tile.size else 0.0
    return result


def grid_clahe(img_gray: np.ndarray, grid_n: int) -> np.ndarray:
    """CLAHE on grayscale, then fixed < 128 threshold."""
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(img_gray)
    return grid_baseline(enhanced, grid_n)


def grid_clahe_otsu(img_gray: np.ndarray, grid_n: int) -> np.ndarray:
    """CLAHE on grayscale, then per-cell Otsu threshold."""
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(img_gray)
    return _grid_otsu(enhanced, grid_n)


def grid_red_channel(img_rgb: np.ndarray, grid_n: int) -> np.ndarray:
    """Red channel only, fixed < 128 threshold."""
    red = img_rgb[:, :, 0]
    return grid_baseline(red, grid_n)


def grid_otsu(img_gray: np.ndarray, grid_n: int) -> np.ndarray:
    """Per-cell Otsu threshold on grayscale."""
    return _grid_otsu(img_gray, grid_n)


def _grid_otsu(img: np.ndarray, grid_n: int) -> np.ndarray:
    """Per-cell Otsu: compute threshold per tile independently."""
    h, w = img.shape
    result = np.empty(grid_n * grid_n, dtype=np.float64)
    for row in range(grid_n):
        r0, r1 = (row * h) // grid_n, ((row + 1) * h) // grid_n
        for col in range(grid_n):
            c0, c1 = (col * w) // grid_n, ((col + 1) * w) // grid_n
            tile = img[r0:r1, c0:c1]
            if tile.size == 0:
                result[row * grid_n + col] = 0.0
                continue
            thresh_val, _ = cv2.threshold(tile, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            result[row * grid_n + col] = float((tile < thresh_val).mean())
    return result


def grid_ink_sum(img_gray: np.ndarray, grid_n: int) -> np.ndarray:
    """Continuous darkness: mean(255 - pixel) / 255 per tile. No threshold."""
    h, w = img_gray.shape
    result = np.empty(grid_n * grid_n, dtype=np.float64)
    inv = (255.0 - img_gray.astype(np.float64)) / 255.0
    for row in range(grid_n):
        r0, r1 = (row * h) // grid_n, ((row + 1) * h) // grid_n
        for col in range(grid_n):
            c0, c1 = (col * w) // grid_n, ((col + 1) * w) // grid_n
            tile = inv[r0:r1, c0:c1]
            result[row * grid_n + col] = float(tile.mean()) if tile.size else 0.0
    return result


def grid_ink_only(img_gray: np.ndarray, grid_n: int) -> np.ndarray:
    """Dark pixels only: for pixels < 128, mean darkness. White pixels ignored.

    Value = mean((255 - pixel) / 255) for pixels where pixel < 128,
    weighted by the fraction of dark pixels in the tile.
    If no dark pixels exist, the tile value is 0.
    """
    h, w = img_gray.shape
    result = np.empty(grid_n * grid_n, dtype=np.float64)
    for row in range(grid_n):
        r0, r1 = (row * h) // grid_n, ((row + 1) * h) // grid_n
        for col in range(grid_n):
            c0, c1 = (col * w) // grid_n, ((col + 1) * w) // grid_n
            tile = img_gray[r0:r1, c0:c1]
            if tile.size == 0:
                result[row * grid_n + col] = 0.0
                continue
            dark_mask = tile < 128
            n_dark = dark_mask.sum()
            if n_dark == 0:
                result[row * grid_n + col] = 0.0
            else:
                # Mean darkness of dark pixels, scaled by dark fraction
                dark_pixels = tile[dark_mask]
                ink_intensity = float(np.mean((255.0 - dark_pixels) / 255.0))
                dark_fraction = n_dark / tile.size
                result[row * grid_n + col] = ink_intensity * dark_fraction
    return result


def grid_clahe_ink_sum(img_gray: np.ndarray, grid_n: int) -> np.ndarray:
    """CLAHE + continuous darkness (no threshold)."""
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(img_gray)
    return grid_ink_sum(enhanced, grid_n)


# ═══════════════════════════════════════════════════════════════════════════════
#  Variant runner
# ═══════════════════════════════════════════════════════════════════════════════


VARIANTS = {
    "baseline":       {"needs_rgb": False, "fn": grid_baseline},
    "clahe":          {"needs_rgb": False, "fn": grid_clahe},
    "clahe_otsu":     {"needs_rgb": False, "fn": grid_clahe_otsu},
    "red_channel":    {"needs_rgb": True,  "fn": grid_red_channel},
    "otsu":           {"needs_rgb": False, "fn": grid_otsu},
    "ink_sum":        {"needs_rgb": False, "fn": grid_ink_sum},
    "ink_only":       {"needs_rgb": False, "fn": grid_ink_only},
    "clahe_ink_sum":  {"needs_rgb": False, "fn": grid_clahe_ink_sum},
}


def compute_variant_vectors(
    pdf_path: str, variant_name: str, dpi: int, grid_n: int,
) -> list[np.ndarray]:
    """Render all pages and compute grid vectors for a given preprocessing variant."""
    vinfo = VARIANTS[variant_name]
    fn = vinfo["fn"]
    needs_rgb = vinfo["needs_rgb"]

    doc = fitz.open(pdf_path)
    vectors: list[np.ndarray] = []

    for page in doc:
        if needs_rgb:
            img = render_page_rgb(page, dpi)
        else:
            img = render_page_gray(page, dpi)
        vectors.append(fn(img, grid_n))

    doc.close()
    return vectors


# ═══════════════════════════════════════════════════════════════════════════════
#  3-way diff
# ═══════════════════════════════════════════════════════════════════════════════


def load_tess_covers() -> list[int]:
    data = json.loads(Path(TESS_FIXTURE).read_text(encoding="utf-8"))
    return sorted(r["pdf_page"] - 1 for r in data["reads"] if r.get("curr") == 1)


def three_way_diff(
    bilateral_0b: list[int], tess_0b: list[int],
) -> tuple[list[int], list[int], list[int]]:
    b, t = set(bilateral_0b), set(tess_0b)
    return sorted(b & t), sorted(b - t), sorted(t - b)


# ═══════════════════════════════════════════════════════════════════════════════
#  Scoring & report
# ═══════════════════════════════════════════════════════════════════════════════


def score_stats(scores: np.ndarray, pages: list[int], label: str) -> dict:
    if not pages:
        return {"label": label, "n": 0}
    s = scores[pages]
    return {
        "label": label,
        "n": len(pages),
        "min": float(np.min(s)),
        "max": float(np.max(s)),
        "mean": float(np.mean(s)),
        "std": float(np.std(s)),
    }


def run_variant(
    variant_name: str,
    vectors: list[np.ndarray],
    tess_covers: list[int],
) -> dict:
    """Run bilateral analysis on pre-computed vectors."""
    scores = bilateral_scores(vectors, SCORE_FN)
    matches, threshold = kmeans_matches(scores)

    shared, bilateral_only, tess_only = three_way_diff(matches, tess_covers)

    return {
        "variant": variant_name,
        "matches": len(matches),
        "error": len(matches) - TARGET,
        "threshold": threshold,
        "shared": score_stats(scores, shared, "SHARED"),
        "bilateral_only": score_stats(scores, bilateral_only, "BILATERAL-ONLY"),
        "tess_only": score_stats(scores, tess_only, "TESS-ONLY"),
        "n_shared": len(shared),
        "n_bilateral_only": len(bilateral_only),
        "n_tess_only": len(tess_only),
    }


def print_report(results: list[dict]) -> None:
    sep = "=" * 90
    print(f"\n{sep}")
    print("Stage 2: Preprocessing Variant Sweep Results")
    print(f"{sep}\n")

    # Summary table
    hdr = (f"{'Variant':<14} {'Matches':>7} {'Error':>6} {'Thresh':>7}  "
           f"{'T-ONLY max':>10} {'T-ONLY mean':>11} {'SHARED min':>10} {'SHARED mean':>11}  "
           f"{'SH':>3} {'BO':>3} {'TO':>3}")
    print(hdr)
    print("-" * len(hdr))

    for r in results:
        to = r["tess_only"]
        sh = r["shared"]
        to_max = f"{to['max']:.4f}" if to["n"] else "N/A"
        to_mean = f"{to['mean']:.4f}" if to["n"] else "N/A"
        sh_min = f"{sh['min']:.4f}" if sh["n"] else "N/A"
        sh_mean = f"{sh['mean']:.4f}" if sh["n"] else "N/A"
        print(f"{r['variant']:<14} {r['matches']:>7} {r['error']:>+6} {r['threshold']:>7.4f}  "
              f"{to_max:>10} {to_mean:>11} {sh_min:>10} {sh_mean:>11}  "
              f"{r['n_shared']:>3} {r['n_bilateral_only']:>3} {r['n_tess_only']:>3}")

    # Targets
    print()
    print("Targets:  TESS-ONLY max > 0.5500   TESS-ONLY mean > 0.4800   "
          "SHARED min >= 0.5000   SHARED mean >= 0.6200")

    # Per-variant detail
    for r in results:
        print(f"\n--- {r['variant']} ---")
        for group in ("shared", "bilateral_only", "tess_only"):
            s = r[group]
            if s["n"] > 0:
                print(f"  {s['label']:<16} n={s['n']:>4}  "
                      f"min={s['min']:.4f}  max={s['max']:.4f}  "
                      f"mean={s['mean']:.4f}  std={s['std']:.4f}")
            else:
                print(f"  {s['label']:<16} n=   0")


# ═══════════════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════════════


def main() -> None:
    print("=" * 60)
    print("Stage 2: Preprocessing Variant Sweep")
    print("=" * 60)

    tess_covers = load_tess_covers()
    print(f"Tess covers: {len(tess_covers)} pages with curr==1")

    results = []

    for variant_name in VARIANTS:
        print(f"\n--- {variant_name} ---")
        t0 = time.perf_counter()
        vectors = compute_variant_vectors(PDF_PATH, variant_name, DPI, GRID)
        elapsed = time.perf_counter() - t0
        print(f"  Rendered {len(vectors)} pages in {elapsed:.1f}s")

        r = run_variant(variant_name, vectors, tess_covers)
        results.append(r)
        print(f"  matches={r['matches']}  error={r['error']:+d}  threshold={r['threshold']:.4f}")

    print_report(results)

    # Save results
    out_path = "data/pixel_density/preprocessing_sweep.json"
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    # Strip numpy types for JSON
    clean_results = json.loads(json.dumps(results, default=lambda o: float(o) if isinstance(o, np.floating) else int(o) if isinstance(o, np.integer) else o))
    Path(out_path).write_text(json.dumps(clean_results, indent=2), encoding="utf-8")
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
