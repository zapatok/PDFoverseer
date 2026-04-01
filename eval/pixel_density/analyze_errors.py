"""FP/FN error analysis for PD_V2_RC on ART_674.

Computes V2_RC scores, identifies FP/FN pages, extracts diagnostic context
(score, gap to threshold, position in document, neighbor scores), and
renders page images for visual inspection.

Usage
-----
    python eval/pixel_density/analyze_errors.py
    python eval/pixel_density/analyze_errors.py --render   # also save PNGs
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np  # noqa: E402

from eval.pixel_density.cache import ensure_cache  # noqa: E402
from eval.pixel_density.evaluate import load_art674_gt  # noqa: E402
from eval.pixel_density.features import extract_features  # noqa: E402
from eval.pixel_density.metrics import bilateral_l2  # noqa: E402
from eval.pixel_density.sweep_rescue import (  # noqa: E402
    _percentile_threshold,
    _robust_z_normalize,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DPI = 100
PDF_PATH = "data/samples/ART_674.pdf"
OUT_DIR = Path("data/pixel_density/error_analysis")
OUT_FP = OUT_DIR / "false_positives"
OUT_FN = OUT_DIR / "false_negatives"


def compute_v2rc_scores(pages: np.ndarray) -> tuple[np.ndarray, list[int], float]:
    """Run V2_RC scorer, return (scores, matches, threshold).

    Args:
        pages: Rendered page array (N, H, W), uint8.

    Returns:
        Tuple of (bilateral scores array, detected cover indices, threshold value).
    """
    feat_list = ["dark_ratio_grid", "edge_density_grid"]
    vectors = [extract_features(pages[i], feat_list) for i in range(pages.shape[0])]
    matrix = np.vstack(vectors)
    normed = _robust_z_normalize(matrix)
    normed_list = [normed[i] for i in range(normed.shape[0])]
    scores = bilateral_l2(normed_list, "min")
    thresh = float(np.percentile(scores, 75.2))
    matches = _percentile_threshold(scores, 75.2)
    return scores, matches, thresh


def classify_pages(
    matches: list[int],
    gt_covers: set[int],
) -> tuple[list[int], list[int], list[int]]:
    """Classify detected pages into TP, FP, FN.

    Args:
        matches: Detected cover page indices (0-based).
        gt_covers: Ground-truth cover page indices (0-based).

    Returns:
        Tuple of (tp_pages, fp_pages, fn_pages), each sorted.
    """
    match_set = set(matches)
    tp = sorted(match_set & gt_covers)
    fp = sorted(match_set - gt_covers)
    fn = sorted(gt_covers - match_set)
    return tp, fp, fn


def find_doc_position(page_idx: int, gt_covers: set[int]) -> tuple[int, int | None]:
    """Find position of page within its GT document.

    Args:
        page_idx: 0-based page index.
        gt_covers: Ground-truth cover page indices.

    Returns:
        (position_within_doc (1-based), cover_page_of_this_doc or None).
    """
    covers_before = sorted(c for c in gt_covers if c <= page_idx)
    if not covers_before:
        return page_idx + 1, None
    nearest = covers_before[-1]
    return page_idx - nearest + 1, nearest


def build_diagnostic(
    pages_list: list[int],
    label: str,
    scores: np.ndarray,
    thresh: float,
    gt_covers: set[int],
) -> list[dict]:
    """Build per-page diagnostic records.

    Args:
        pages_list: Page indices to diagnose.
        label: "FP" or "FN".
        scores: Full bilateral score array.
        thresh: Threshold value.
        gt_covers: Ground-truth cover page indices.

    Returns:
        List of diagnostic dicts.
    """
    n = len(scores)
    records = []
    for p in pages_list:
        pos, doc_cover = find_doc_position(p, gt_covers)
        left_score = float(scores[p - 1]) if p > 0 else None
        right_score = float(scores[p + 1]) if p < n - 1 else None
        records.append({
            "page_0based": p,
            "page_1based": p + 1,
            "label": label,
            "score": float(scores[p]),
            "gap_to_threshold": float(scores[p]) - thresh,
            "position_in_doc": pos,
            "doc_cover_page": doc_cover,
            "left_neighbor_score": left_score,
            "right_neighbor_score": right_score,
        })
    return records


def render_pages(
    pdf_path: str,
    page_indices: list[int],
    out_dir: Path,
    render_dpi: int = 100,
) -> None:
    """Render specific pages as PNGs for visual inspection.

    Args:
        pdf_path: Path to PDF.
        page_indices: 0-based page indices to render.
        out_dir: Output directory.
        render_dpi: Rendering DPI.
    """
    import fitz

    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    mat = fitz.Matrix(render_dpi / 72, render_dpi / 72)
    for idx in page_indices:
        page = doc[idx]
        pix = page.get_pixmap(matrix=mat)
        pix.save(str(out_dir / f"p{idx:04d}.png"))
    doc.close()
    logger.info("Rendered %d pages to %s", len(page_indices), out_dir)


def print_diagnostic_table(records: list[dict], label: str) -> None:
    """Print a formatted diagnostic table.

    Args:
        records: Diagnostic dicts from build_diagnostic().
        label: "FP" or "FN".
    """
    header = (
        f"{'page':>6} {'score':>7} {'gap':>8} {'pos':>4} "
        f"{'left':>7} {'right':>7} {'doc_cover':>10}"
    )
    print(f"\n{'=' * 60}")  # noqa: T201
    print(f"{label} pages ({len(records)})")  # noqa: T201
    print(f"{'=' * 60}")  # noqa: T201
    print(header)  # noqa: T201
    print("-" * 60)  # noqa: T201
    for r in records:
        left_s = f"{r['left_neighbor_score']:.4f}" if r["left_neighbor_score"] is not None else "n/a"
        right_s = f"{r['right_neighbor_score']:.4f}" if r["right_neighbor_score"] is not None else "n/a"
        doc_c = str(r["doc_cover_page"]) if r["doc_cover_page"] is not None else "n/a"
        print(  # noqa: T201
            f"{r['page_1based']:>6} {r['score']:>7.4f} {r['gap_to_threshold']:>+8.4f} "
            f"{r['position_in_doc']:>4} {left_s:>7} {right_s:>7} {doc_c:>10}"
        )


def main() -> None:
    """Run FP/FN error analysis on ART_674."""
    parser = argparse.ArgumentParser(description="PD V2_RC error analysis")
    parser.add_argument("--render", action="store_true",
                        help="Render FP/FN pages as PNGs for visual inspection")
    args = parser.parse_args()

    # 1. Compute scores
    logger.info("Loading pages...")
    art_pages = ensure_cache(PDF_PATH, dpi=DPI)
    logger.info("Computing V2_RC scores...")
    scores, matches, thresh = compute_v2rc_scores(art_pages)
    gt_covers = load_art674_gt()

    # 2. Classify
    tp, fp, fn = classify_pages(matches, gt_covers)
    logger.info("TP=%d, FP=%d, FN=%d, threshold=%.4f", len(tp), len(fp), len(fn), thresh)

    # 3. Diagnostics
    fp_diag = build_diagnostic(fp, "FP", scores, thresh, gt_covers)
    fn_diag = build_diagnostic(fn, "FN", scores, thresh, gt_covers)

    print_diagnostic_table(fp_diag, "FALSE POSITIVES")
    print_diagnostic_table(fn_diag, "FALSE NEGATIVES")

    # 4. Summary statistics
    fp_scores = np.array([r["score"] for r in fp_diag])
    fn_scores = np.array([r["score"] for r in fn_diag])
    tp_scores = scores[tp]

    print(f"\n{'=' * 60}")  # noqa: T201
    print("Score distribution summary")  # noqa: T201
    print(f"{'=' * 60}")  # noqa: T201
    for lbl, arr in [("TP", tp_scores), ("FP", fp_scores), ("FN", fn_scores)]:
        if arr.size > 0:
            print(f"  {lbl}: min={arr.min():.4f} max={arr.max():.4f} mean={arr.mean():.4f}")  # noqa: T201
        else:
            print(f"  {lbl}: (none)")  # noqa: T201

    # FP position analysis
    fp_positions = [r["position_in_doc"] for r in fp_diag]
    pos_counts: dict[int, int] = {}
    for pos in fp_positions:
        pos_counts[pos] = pos_counts.get(pos, 0) + 1
    print("\n  FP by position in document:")  # noqa: T201
    for pos in sorted(pos_counts):
        print(f"    pos {pos}: {pos_counts[pos]}")  # noqa: T201

    # Consecutive FP pairs
    fp_set = set(fp)
    consecutive_pairs = [(p, p + 1) for p in fp if (p + 1) in fp_set]
    print(f"\n  Consecutive FP pairs: {len(consecutive_pairs)}")  # noqa: T201
    for a, b in consecutive_pairs:
        print(f"    pages {a+1}-{b+1}")  # noqa: T201

    # 5. Save JSON
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        "threshold": thresh,
        "tp_count": len(tp),
        "fp_count": len(fp),
        "fn_count": len(fn),
        "fp_diagnostics": fp_diag,
        "fn_diagnostics": fn_diag,
    }
    out_path = OUT_DIR / "diagnostics.json"
    out_path.write_text(json.dumps(output, indent=2, default=float), encoding="utf-8")
    logger.info("Diagnostics saved to %s", out_path)

    # 6. Render if requested
    if args.render:
        render_pages(PDF_PATH, fp, OUT_FP, render_dpi=100)
        render_pages(PDF_PATH, fn, OUT_FN, render_dpi=100)


if __name__ == "__main__":
    main()
