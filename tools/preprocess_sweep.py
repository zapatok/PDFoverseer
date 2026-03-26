"""
preprocess_sweep.py — OCR Preprocessing Variant Sweep
=====================================================
Standalone research script. Tests N preprocessing variants on failed pages
and ranks which variants recover the most OCR reads.

Usage:
    python tools/preprocess_sweep.py <path-to-PDF>
    python tools/preprocess_sweep.py <path-to-PDF> --max-pages 20  # quick test
    python tools/preprocess_sweep.py <path-to-PDF> --workers 8

Output: data/preprocess_sweep/sweep_results.csv + summary.txt
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pytesseract

# Project imports
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from core.image import _deskew, _render_clip  # noqa: E402
from core.utils import TESS_CONFIG, _parse  # noqa: E402

# ── Tesseract path (match core/ocr.py) ─────────────────────────
pytesseract.pytesseract.tesseract_cmd = os.getenv(
    "TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

OUTPUT_DIR = Path("data/preprocess_sweep")
FIXTURES_DIR = Path("eval/fixtures/real")


# ============================================================================
# Variant definition & matrix
# ============================================================================

@dataclass(frozen=True)
class Variant:
    binarize: str        # none | otsu | adapt_gauss_15 | adapt_gauss_31 | adapt_mean_15
    color_filter: str    # blue_only | sat_filter | lum_only | no_filter
    contrast: str        # unsharp_1_03 | clahe_2 | clahe_4 | none
    morphology: str      # none | close_2 | open_1
    dpi: int             # 150 | 200 | 300

    @property
    def tag(self) -> str:
        return f"{self.binarize}_{self.color_filter}_{self.contrast}_{self.morphology}_dpi{self.dpi}"


BINARIZE_OPTIONS   = ["none", "otsu", "adapt_gauss_15", "adapt_gauss_31", "adapt_mean_15"]
COLOR_OPTIONS      = ["blue_only", "sat_filter", "lum_only", "no_filter"]
CONTRAST_OPTIONS   = ["unsharp_1_03", "clahe_2", "clahe_4", "none"]
MORPHOLOGY_OPTIONS = ["none", "close_2", "open_1"]
DPI_OPTIONS        = [150, 200, 300]


def build_variant_matrix() -> list[Variant]:
    return [
        Variant(b, c, ct, m, d)
        for b, c, ct, m, d in itertools.product(
            BINARIZE_OPTIONS, COLOR_OPTIONS, CONTRAST_OPTIONS,
            MORPHOLOGY_OPTIONS, DPI_OPTIONS,
        )
    ]


# ============================================================================
# Preprocessing stages
# ============================================================================

def _apply_color_filter(bgr: np.ndarray, method: str) -> np.ndarray:
    """Apply color filtering and return grayscale."""
    if method == "blue_only":
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array([90, 50, 50]), np.array([150, 255, 255]))
        clean = cv2.inpaint(bgr, mask, 3, cv2.INPAINT_NS)
        return cv2.cvtColor(clean, cv2.COLOR_BGR2GRAY)
    elif method == "sat_filter":
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        mask = hsv[:, :, 1] > 50
        bgr_clean = bgr.copy()
        bgr_clean[mask] = 255
        return cv2.cvtColor(bgr_clean, cv2.COLOR_BGR2GRAY)
    elif method == "lum_only":
        hls = cv2.cvtColor(bgr, cv2.COLOR_BGR2HLS)
        return hls[:, :, 1]
    else:  # no_filter
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)


def _apply_contrast(gray: np.ndarray, method: str) -> np.ndarray:
    if method == "unsharp_1_03":
        blurred = cv2.GaussianBlur(gray, (0, 0), 1.0)
        return cv2.addWeighted(gray, 1.3, blurred, -0.3, 0)
    elif method == "clahe_2":
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(gray)
    elif method == "clahe_4":
        clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
        return clahe.apply(gray)
    else:  # none
        return gray


def _apply_binarize(gray: np.ndarray, method: str) -> np.ndarray:
    if method == "otsu":
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return binary
    elif method == "adapt_gauss_15":
        return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 15, 10)
    elif method == "adapt_gauss_31":
        return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 31, 10)
    elif method == "adapt_mean_15":
        return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                     cv2.THRESH_BINARY, 15, 10)
    else:  # none
        return gray


def _apply_morphology(img: np.ndarray, method: str, binarized: bool) -> np.ndarray:
    if not binarized or method == "none":
        return img
    if method == "close_2":
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        return cv2.morphologyEx(img, cv2.MORPH_CLOSE, kernel, iterations=2)
    elif method == "open_1":
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        return cv2.morphologyEx(img, cv2.MORPH_OPEN, kernel, iterations=1)
    return img


def apply_variant(bgr: np.ndarray, v: Variant) -> np.ndarray:
    """Apply a preprocessing variant to a BGR image, return grayscale/binary for OCR."""
    gray = _apply_color_filter(bgr, v.color_filter)
    gray = _apply_contrast(gray, v.contrast)
    result = _apply_binarize(gray, v.binarize)
    result = _apply_morphology(result, v.morphology, binarized=(v.binarize != "none"))
    return result


# ============================================================================
# Ground truth & scoring
# ============================================================================

def load_ground_truth(pdf_name: str) -> dict[int, tuple[int, int]]:
    """Load GT fixture, return {pdf_page: (curr, total)}."""
    fixture_path = FIXTURES_DIR / f"{pdf_name}.json"
    with open(fixture_path) as f:
        data = json.load(f)
    return {r["pdf_page"]: (r["curr"], r["total"]) for r in data["reads"]}


def score_result(parsed: tuple, gt: tuple) -> str:
    """Score a single OCR parse against ground truth."""
    if parsed[0] is None:
        return "failed"
    if parsed == gt:
        return "correct"
    return "wrong"


# ============================================================================
# Sweep runner
# ============================================================================

def _ocr_with_variant(bgr: np.ndarray, variant: Variant) -> tuple[int | None, int | None]:
    """Apply variant preprocessing + Tesseract, return parsed (curr, total)."""
    processed = apply_variant(bgr, variant)
    text = pytesseract.image_to_string(processed, lang="eng", config=TESS_CONFIG)
    return _parse(text.strip())


def _identify_failed_pages(
    pdf_path: Path,
    gt: dict[int, tuple[int, int]],
) -> list[int]:
    """Return list of pdf_pages where baseline preprocessing fails to parse correctly."""
    import fitz
    doc = fitz.open(str(pdf_path))
    failed = []
    baseline = Variant("none", "blue_only", "unsharp_1_03", "none", 150)
    for pdf_page in sorted(gt.keys()):
        page_idx = pdf_page - 1
        if page_idx >= len(doc):
            continue
        bgr = _render_clip(doc[page_idx])
        bgr = _deskew(bgr)
        parsed = _ocr_with_variant(bgr, baseline)
        if parsed != gt[pdf_page]:
            failed.append(pdf_page)
    doc.close()
    return failed


def run_sweep(
    pdf_path: Path,
    variants: list[Variant] | None = None,
    max_pages: int = 0,
    workers: int = 6,
) -> dict:
    """
    Run the full preprocessing sweep.
    Returns dict with 'variant_stats' and 'page_results'.
    """
    import fitz

    pdf_name = Path(pdf_path).stem
    gt = load_ground_truth(pdf_name)

    if variants is None:
        variants = build_variant_matrix()

    # Find failed pages
    print(f"[sweep] Identifying failed pages among {len(gt)} GT pages...")
    failed_pages = _identify_failed_pages(pdf_path, gt)
    if max_pages > 0:
        failed_pages = failed_pages[:max_pages]
    print(f"[sweep] {len(failed_pages)} failed pages to test × {len(variants)} variants")

    # Pre-render all failed pages at each needed DPI
    dpis_needed = sorted(set(v.dpi for v in variants))
    print(f"[sweep] Pre-rendering at DPIs: {dpis_needed}")
    doc = fitz.open(str(pdf_path))
    page_images = {}  # (pdf_page, dpi) → bgr
    for pdf_page in failed_pages:
        page = doc[pdf_page - 1]
        for dpi in dpis_needed:
            bgr = _render_clip(page, dpi=dpi)
            bgr = _deskew(bgr)
            page_images[(pdf_page, dpi)] = bgr
    doc.close()
    print(f"[sweep] Pre-rendered {len(page_images)} images")

    # Run sweep (parallelized per page×variant)
    page_results = []  # list of (pdf_page, variant_tag, score, parsed, gt_val)
    variant_stats = {v.tag: {"recovered": 0, "wrong": 0, "failed": 0} for v in variants}

    total_jobs = len(failed_pages) * len(variants)
    done = 0
    t0 = time.time()

    def _eval_one(pdf_page: int, variant: Variant):
        bgr = page_images[(pdf_page, variant.dpi)]
        parsed = _ocr_with_variant(bgr, variant)
        gt_val = gt[pdf_page]
        sc = score_result(parsed, gt_val)
        return pdf_page, variant.tag, sc, parsed, gt_val

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = []
        for pdf_page in failed_pages:
            for v in variants:
                futures.append(pool.submit(_eval_one, pdf_page, v))

        for fut in as_completed(futures):
            pdf_page, vtag, sc, parsed, gt_val = fut.result()
            page_results.append((pdf_page, vtag, sc, parsed, gt_val))
            stat_key = "recovered" if sc == "correct" else sc
            variant_stats[vtag][stat_key] += 1
            done += 1
            if done % 1000 == 0:
                elapsed = time.time() - t0
                rate = done / elapsed
                eta = (total_jobs - done) / rate
                print(f"  [{done}/{total_jobs}] {rate:.0f} eval/s, ETA {eta:.0f}s")

    elapsed = time.time() - t0
    print(f"[sweep] Done: {total_jobs} evals in {elapsed:.1f}s ({total_jobs/elapsed:.0f}/s)")

    return {
        "variant_stats": variant_stats,
        "page_results": page_results,
        "failed_count": len(failed_pages),
        "elapsed": elapsed,
    }


# ============================================================================
# Report generator
# ============================================================================

def write_report(results: dict, out_dir: Path = OUTPUT_DIR) -> None:
    """Write sweep results to CSV + human-readable summary."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # Detailed CSV: every page × variant result
    csv_path = out_dir / "sweep_detail.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["pdf_page", "variant", "score", "parsed_curr", "parsed_total",
                     "gt_curr", "gt_total"])
        for pdf_page, vtag, sc, parsed, gt_val in results["page_results"]:
            w.writerow([pdf_page, vtag, sc,
                        parsed[0] or "", parsed[1] or "",
                        gt_val[0], gt_val[1]])

    # Ranked summary: variants sorted by recovered count (desc), then wrong (asc)
    stats = results["variant_stats"]
    ranked = sorted(stats.items(), key=lambda kv: (-kv[1]["recovered"], kv[1]["wrong"]))

    summary_path = out_dir / "sweep_summary.txt"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("OCR Preprocessing Sweep Results\n")
        f.write(f"{'=' * 60}\n")
        f.write(f"Failed pages tested: {results['failed_count']}\n")
        f.write(f"Variants tested: {len(stats)}\n")
        f.write(f"Total evaluations: {results['failed_count'] * len(stats)}\n")
        f.write(f"Elapsed: {results['elapsed']:.1f}s\n\n")

        f.write(f"{'Rank':>4} {'Recovered':>9} {'Wrong':>6} {'Failed':>6}  Variant\n")
        f.write(f"{'-'*4} {'-'*9} {'-'*6} {'-'*6}  {'-'*40}\n")
        for rank, (vtag, st) in enumerate(ranked[:50], 1):
            f.write(f"{rank:4d} {st['recovered']:9d} {st['wrong']:6d} {st['failed']:6d}  {vtag}\n")

        # Baseline comparison
        baseline_tag = "none_blue_only_unsharp_1_03_none_dpi150"
        if baseline_tag in stats:
            bl = stats[baseline_tag]
            f.write(f"\n--- Baseline ({baseline_tag}) ---\n")
            f.write(f"Recovered: {bl['recovered']}, Wrong: {bl['wrong']}, Failed: {bl['failed']}\n")

            # Best vs baseline
            best_tag, best_st = ranked[0]
            delta = best_st["recovered"] - bl["recovered"]
            f.write(f"\n--- Best ({best_tag}) ---\n")
            f.write(f"Recovered: {best_st['recovered']} (+{delta} vs baseline)\n")
            f.write(f"Wrong: {best_st['wrong']}, Failed: {best_st['failed']}\n")

    # Also print summary to stdout
    with open(summary_path) as f:
        print(f.read())

    print(f"\n[report] Detail CSV: {csv_path}")
    print(f"[report] Summary: {summary_path}")


# ============================================================================
# CLI
# ============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="OCR Preprocessing Sweep — test variants on failed pages"
    )
    parser.add_argument("pdf_path", help="Path to PDF file (must have GT fixture)")
    parser.add_argument("--max-pages", type=int, default=0,
                        help="Limit failed pages to test (0 = all)")
    parser.add_argument("--workers", type=int, default=6,
                        help="Parallel Tesseract workers (default: 6)")
    parser.add_argument("--out", default=str(OUTPUT_DIR),
                        help=f"Output directory (default: {OUTPUT_DIR})")
    args = parser.parse_args()

    results = run_sweep(
        Path(args.pdf_path),
        max_pages=args.max_pages,
        workers=args.workers,
    )
    write_report(results, Path(args.out))


if __name__ == "__main__":
    main()
