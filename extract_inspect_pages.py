"""
extract_inspect_pages.py — Extract full page images for manual inspection.

Renders pages from two clusters into data/pixel_density/:
  bilateral_only/  — bilateral detects as cover, Tesseract never read curr==1
  tess_only/       — Tesseract confirmed curr==1, bilateral misses

Usage
-----
    python extract_inspect_pages.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import fitz  # PyMuPDF

from pixel_density import compute_ratios_grid
from sweep_bilateral import bilateral_scores, kmeans_matches

PDF_PATH  = "data/samples/ART_674.pdf"
FIXTURE   = "eval/fixtures/real/ART_674_tess.json"
DPI       = 100
GRID      = 8
SCORE_FN  = "harmonic"

OUT_BILATERAL = Path("data/pixel_density/bilateral_only")
OUT_TESS      = Path("data/pixel_density/tess_only")
RENDER_DPI    = 100  # full-page render for visual inspection


def run_bilateral() -> list[int]:
    print("Rendering bilateral vectors...")
    t0 = time.perf_counter()
    vectors = compute_ratios_grid(PDF_PATH, DPI, GRID)
    print(f"  {len(vectors)} pages in {time.perf_counter()-t0:.1f}s")
    scores = bilateral_scores(vectors, SCORE_FN)
    matches, threshold = kmeans_matches(scores)
    print(f"  bilateral: {len(matches)} covers (threshold={threshold:.4f})")
    return matches


def load_tess_covers() -> list[int]:
    with open(FIXTURE, encoding="utf-8") as f:
        data = json.load(f)
    covers = sorted(r["pdf_page"] - 1 for r in data["reads"] if r.get("curr") == 1)
    print(f"  tess curr==1: {len(covers)} pages")
    return covers


def extract_pages(pdf: fitz.Document, indices: list[int], out_dir: Path, render_dpi: int) -> None:
    mat = fitz.Matrix(render_dpi / 72, render_dpi / 72)
    for idx in indices:
        page = pdf[idx]
        pix  = page.get_pixmap(matrix=mat)
        pix.save(out_dir / f"p{idx+1:04d}.png")
    print(f"  saved {len(indices)} images to {out_dir}")


def main() -> None:
    print("\nStep 1: bilateral detection")
    bilateral = run_bilateral()

    print("\nStep 2: load Tesseract fixture")
    tess = load_tess_covers()

    b, t = set(bilateral), set(tess)
    bilateral_only = sorted(b - t)
    tess_only      = sorted(t - b)

    print(f"\nShared: {len(b & t)}  |  Bilateral-only: {len(bilateral_only)}  |  Tess-only: {len(tess_only)}")

    print("\nStep 3: extract pages")
    doc = fitz.open(PDF_PATH)
    print(f"  extracting {len(bilateral_only)} bilateral-only pages...")
    extract_pages(doc, bilateral_only, OUT_BILATERAL, RENDER_DPI)
    print(f"  extracting {len(tess_only)} tess-only pages...")
    extract_pages(doc, tess_only, OUT_TESS, RENDER_DPI)
    doc.close()

    print("\nDone.")
    print(f"  bilateral_only: {OUT_BILATERAL}")
    print(f"  tess_only:      {OUT_TESS}")


if __name__ == "__main__":
    main()
