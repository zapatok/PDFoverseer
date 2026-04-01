"""
inspect_bilateral.py — Page-level comparison: bilateral pixel density vs Tesseract OCR.

Runs the best bilateral config (dpi=100, grid=8x8, harmonic) on ART_674.pdf and
produces a 3-way diff against Tesseract curr==1 pages from the fixture:

  SHARED       - bilateral and Tesseract both detect as cover
  BILATERAL-ONLY - bilateral finds it, Tesseract OCR never read curr==1 there
  TESS-ONLY    - Tesseract confirmed curr==1, bilateral misses it

Usage
-----
    python inspect_bilateral.py
    python inspect_bilateral.py --save inspect_results.txt
    python inspect_bilateral.py --diagnose
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np

from eval.pixel_density.pixel_density import compute_ratios_grid
from eval.pixel_density.sweep_bilateral import bilateral_scores, kmeans_matches

PDF_PATH    = "data/samples/ART_674.pdf"
FIXTURE     = "eval/fixtures/real/ART_674_tess.json"
DPI         = 100
GRID        = 8
SCORE_FN    = "harmonic"
TARGET      = 674


def run_bilateral(pdf_path: str) -> tuple[list[int], np.ndarray, float]:
    """Run best bilateral config; return (0-based cover indices, scores array, threshold)."""
    print(f"Rendering dpi={DPI} grid={GRID}x{GRID}...")
    t0 = time.perf_counter()
    vectors = compute_ratios_grid(pdf_path, DPI, GRID)
    elapsed = time.perf_counter() - t0
    print(f"  {len(vectors)} pages rendered in {elapsed:.1f}s")

    scores = bilateral_scores(vectors, SCORE_FN)
    matches, threshold = kmeans_matches(scores)
    print(f"  bilateral: {len(matches)} covers  (threshold={threshold:.4f})")
    return matches, scores, threshold


def load_tess_covers(fixture_path: str) -> list[int]:
    """Return 0-based page indices where Tesseract read curr==1."""
    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)
    # pdf_page is 1-based -> convert to 0-based
    covers = [r["pdf_page"] - 1 for r in data["reads"] if r.get("curr") == 1]
    print(f"  fixture: {len(covers)} curr==1 pages")
    return sorted(covers)


def compare(bilateral: list[int], tess: list[int]) -> dict:
    b = set(bilateral)
    t = set(tess)
    return {
        "shared":         sorted(b & t),
        "bilateral_only": sorted(b - t),
        "tess_only":      sorted(t - b),
    }


def fmt_pages(pages: list[int], label: str, max_show: int = 30) -> list[str]:
    """Format a page list as 1-based for display."""
    lines = []
    pages_1b = [p + 1 for p in pages]
    lines.append(f"{label} ({len(pages_1b)} pages):")
    if not pages_1b:
        lines.append("  (none)")
    elif len(pages_1b) <= max_show:
        lines.append("  " + ", ".join(str(p) for p in pages_1b))
    else:
        shown = pages_1b[:max_show]
        lines.append(f"  {', '.join(str(p) for p in shown)} ... (+{len(pages_1b)-max_show} more)")
    return lines


def report(diff: dict, bilateral: list[int], tess: list[int], target: int) -> str:
    sep = "-" * 70
    lines = [
        sep,
        f"Bilateral pixel density  (dpi={DPI}, grid={GRID}x{GRID}, {SCORE_FN})  vs  Tesseract OCR",
        sep,
        f"  Target (ground truth)  : {target}",
        f"  Bilateral covers       : {len(bilateral)}  (error vs target: {len(bilateral)-target:+d})",
        f"  Tesseract curr==1      : {len(tess)}  (error vs target: {len(tess)-target:+d})",
        sep,
        f"  SHARED (both agree)    : {len(diff['shared'])}",
        f"  BILATERAL only         : {len(diff['bilateral_only'])}  (potential inferred covers or FPs)",
        f"  TESS only              : {len(diff['tess_only'])}  (confirmed covers bilateral misses)",
        sep,
        "",
    ]

    lines += fmt_pages(diff["shared"],         "SHARED        ")
    lines += [""]
    lines += fmt_pages(diff["bilateral_only"],  "BILATERAL-ONLY")
    lines += [""]
    lines += fmt_pages(diff["tess_only"],       "TESS-ONLY     ")
    lines += [sep]

    return "\n".join(lines)


def diagnose_tess_only(
    diff: dict,
    scores: np.ndarray,
    threshold: float,
    n_pages: int,
) -> str:
    """For each TESS-ONLY page: show its harmonic score, neighbor scores, and groups.

    Columns: page (1-based) | own_score | gap_to_threshold | left_score [group] | right_score [group]
    Groups: S=shared, B=bilateral_only, T=tess_only, -=none
    """
    shared_set   = set(diff["shared"])
    bilat_set    = set(diff["bilateral_only"])
    tess_set     = set(diff["tess_only"])

    def group(idx: int) -> str:
        if idx in shared_set:
            return "S"
        if idx in bilat_set:
            return "B"
        if idx in tess_set:
            return "T"
        return "-"

    sep = "-" * 78
    hdr = f"{'page':>6}  {'score':>7}  {'gap':>8}  {'left_score':>10} {'lg':>2}  {'right_score':>11} {'rg':>2}"
    lines = [
        sep,
        "TESS-ONLY diagnostic: harmonic scores + neighbor context",
        f"threshold = {threshold:.4f}",
        sep,
        hdr,
        sep,
    ]

    score_vals = []
    for idx in sorted(diff["tess_only"]):
        s      = float(scores[idx])
        gap    = s - threshold
        l_idx  = idx - 1 if idx > 0          else None
        r_idx  = idx + 1 if idx < n_pages - 1 else None
        l_s    = f"{scores[l_idx]:.4f}" if l_idx is not None else "  n/a"
        r_s    = f"{scores[r_idx]:.4f}" if r_idx is not None else "  n/a"
        l_g    = group(l_idx) if l_idx is not None else " "
        r_g    = group(r_idx) if r_idx is not None else " "
        lines.append(
            f"{idx+1:>6}  {s:>7.4f}  {gap:>+8.4f}  {l_s:>10} {l_g:>2}  {r_s:>11} {r_g:>2}"
        )
        score_vals.append(s)

    lines.append(sep)
    arr = np.array(score_vals)
    lines.append(f"  TESS-ONLY scores  min={arr.min():.4f}  max={arr.max():.4f}  mean={arr.mean():.4f}  median={np.median(arr):.4f}")

    shared_scores = scores[list(diff["shared"])]
    lines.append(f"  SHARED scores     min={shared_scores.min():.4f}  max={shared_scores.max():.4f}  mean={shared_scores.mean():.4f}  median={np.median(shared_scores):.4f}")
    lines.append(sep)

    below = sum(1 for v in score_vals if v < threshold)
    lines.append(f"  {below}/{len(score_vals)} tess-only pages score BELOW threshold ({threshold:.4f})")
    lines.append(sep)

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bilateral vs Tesseract page-level diff.")
    parser.add_argument("--save",     metavar="PATH", default=None,
                        help="Save main report to this file")
    parser.add_argument("--diagnose", action="store_true",
                        help="Print per-page score diagnostic for TESS-ONLY pages")
    parser.add_argument("--diagnose-save", metavar="PATH", default=None,
                        help="Save diagnostic report to this file")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print("inspect_bilateral.py")
    print(f"{'='*60}\n")

    bilateral, scores, threshold = run_bilateral(PDF_PATH)
    print()
    tess = load_tess_covers(FIXTURE)
    print()

    diff = compare(bilateral, tess)
    output = report(diff, bilateral, tess, TARGET)

    if args.save:
        Path(args.save).write_text(output, encoding="utf-8")
        print(f"Report saved to {args.save}")
    else:
        print(output)

    if args.diagnose or args.diagnose_save:
        diag = diagnose_tess_only(diff, scores, threshold, n_pages=len(scores))
        if args.diagnose_save:
            Path(args.diagnose_save).write_text(diag, encoding="utf-8")
            print(f"Diagnostic saved to {args.diagnose_save}")
        else:
            print(diag)


if __name__ == "__main__":
    main()
