"""
simulate_bilateral_union.py — Project inference result with bilateral + Tesseract union.

Injects bilateral-detected covers as synthetic curr==1 reads into the Tesseract
fixture, then runs the production inference engine to estimate the doc count.

Three scenarios:
  baseline     — fixture as-is (527 tess reads)
  union_all    — baseline + all 172 bilateral-only reads (incl. potential FPs)
  union_scored — baseline + bilateral-only reads filtered by score >= min_score

Usage
-----
    python simulate_bilateral_union.py
    python simulate_bilateral_union.py --min-score 0.40
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from eval.inference_tuning.params import PRODUCTION_PARAMS  # noqa: E402
from eval.inference_tuning.inference import run_pipeline    # noqa: E402
from eval.shared.types import PageRead                      # noqa: E402
from pixel_density import compute_ratios_grid               # noqa: E402
from sweep_bilateral import bilateral_scores, kmeans_matches # noqa: E402

PDF_PATH = "data/samples/ART_674.pdf"
FIXTURE  = "eval/fixtures/real/ART_674_tess.json"
TARGET   = 674
DPI      = 100
GRID     = 8
SCORE_FN = "harmonic"

SYNTH_CONFIDENCE = 0.70   # confidence assigned to synthetic bilateral reads
SYNTH_TOTAL      = 1      # ART forms are single-page docs; total=None crashes _undercount_recovery
SYNTH_METHOD     = "bilateral"


# ── Bilateral detection ────────────────────────────────────────────────────────

def get_bilateral(pdf_path: str) -> tuple[list[int], np.ndarray, float]:
    """Return (0-based cover indices, scores array, threshold)."""
    print(f"  Rendering bilateral (dpi={DPI} grid={GRID}x{GRID})...")
    t0 = time.perf_counter()
    vectors = compute_ratios_grid(pdf_path, DPI, GRID)
    print(f"  {len(vectors)} pages in {time.perf_counter()-t0:.1f}s")
    scores  = bilateral_scores(vectors, SCORE_FN)
    matches, threshold = kmeans_matches(scores)
    print(f"  bilateral: {len(matches)} covers  threshold={threshold:.4f}")
    return matches, scores, threshold


# ── Fixture loading ────────────────────────────────────────────────────────────

def load_reads(fixture_path: str) -> list[PageRead]:
    data = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
    return [PageRead(**r) for r in data["reads"]]


# ── Diff ──────────────────────────────────────────────────────────────────────

def compute_diff(bilateral: list[int], reads: list[PageRead]) -> dict:
    tess_set    = {r.pdf_page - 1 for r in reads if r.curr == 1}
    bilat_set   = set(bilateral)
    return {
        "shared":         sorted(bilat_set & tess_set),
        "bilateral_only": sorted(bilat_set - tess_set),
        "tess_only":      sorted(tess_set - bilat_set),
    }


# ── Inject synthetic reads ────────────────────────────────────────────────────

def inject_bilateral(
    base_reads: list[PageRead],
    bilateral_only: list[int],   # 0-based
    scores: np.ndarray,
    min_score: float = 0.0,
) -> list[PageRead]:
    """Append synthetic curr==1 reads for bilateral-only pages, sorted by pdf_page."""
    filtered = [idx for idx in bilateral_only if scores[idx] >= min_score]
    synthetic = [
        PageRead(
            pdf_page=idx + 1,
            curr=1,
            total=SYNTH_TOTAL,
            method=SYNTH_METHOD,
            confidence=SYNTH_CONFIDENCE,
        )
        for idx in filtered
    ]
    combined = base_reads + synthetic
    combined.sort(key=lambda r: r.pdf_page)
    return combined, len(filtered)


# ── Run inference + summarise ─────────────────────────────────────────────────

def run_scenario(label: str, reads: list[PageRead], target: int) -> dict:
    t0   = time.perf_counter()
    docs = run_pipeline(reads, PRODUCTION_PARAMS)
    elapsed = time.perf_counter() - t0

    n_docs     = len(docs)
    n_complete = sum(1 for d in docs if d.is_complete)
    n_inferred = sum(len(d.inferred_pages) for d in docs)
    error      = n_docs - target

    return {
        "label":     label,
        "reads":     len(reads),
        "curr1":     sum(1 for r in reads if r.curr == 1),
        "docs":      n_docs,
        "complete":  n_complete,
        "inferred":  n_inferred,
        "error":     error,
        "elapsed":   elapsed,
    }


# ── Report ────────────────────────────────────────────────────────────────────

def print_report(results: list[dict], target: int, diff: dict, threshold: float) -> None:
    sep = "-" * 70
    print(f"\n{sep}")
    print(f"Bilateral+Tesseract union simulation  (target={target})")
    print(f"{sep}")
    print(f"  SHARED         : {len(diff['shared'])} pages")
    print(f"  BILATERAL-ONLY : {len(diff['bilateral_only'])} pages  (injected as synthetic reads)")
    print(f"  TESS-ONLY      : {len(diff['tess_only'])} pages  (already in fixture)")
    print(f"  bilateral threshold : {threshold:.4f}")
    print(f"  synthetic conf      : {SYNTH_CONFIDENCE}  total=None")
    print(f"{sep}")
    hdr = f"  {'scenario':<22} {'curr1 reads':>11} {'DOC':>5} {'error':>7} {'complete':>9} {'inferred':>9}"
    print(hdr)
    print(f"  {'-'*64}")
    for r in results:
        print(
            f"  {r['label']:<22} {r['curr1']:>11} {r['docs']:>5} {r['error']:>+7} "
            f"{r['complete']:>9} {r['inferred']:>9}"
        )
    print(f"{sep}")

    # Interpretation
    baseline = results[0]
    for r in results[1:]:
        delta = r["docs"] - baseline["docs"]
        sign  = "+" if delta >= 0 else ""
        print(f"  {r['label']} vs baseline: {sign}{delta} docs  (error {baseline['error']:+d} -> {r['error']:+d})")
    print(sep)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-score", type=float, default=0.40,
                        help="Min bilateral score to include in union_scored scenario (default: 0.40)")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print("simulate_bilateral_union.py")
    print(f"{'='*60}\n")

    print("Step 1: bilateral detection")
    bilateral, scores, threshold = get_bilateral(PDF_PATH)

    print("\nStep 2: load fixture")
    base_reads = load_reads(FIXTURE)
    print(f"  {len(base_reads)} total reads")

    print("\nStep 3: compute diff")
    diff = compute_diff(bilateral, base_reads)
    print(f"  shared={len(diff['shared'])}  bilateral_only={len(diff['bilateral_only'])}  tess_only={len(diff['tess_only'])}")

    print("\nStep 4: run scenarios")
    results = []

    # Scenario A: baseline (tess only, no injection)
    print("  [A] baseline...")
    results.append(run_scenario("baseline (tess)", base_reads, TARGET))

    # Scenario B: union all bilateral-only injected
    print("  [B] union_all (inject all 172)...")
    reads_all, n_all = inject_bilateral(base_reads, diff["bilateral_only"], scores, min_score=0.0)
    results.append(run_scenario(f"union_all ({n_all} injected)", reads_all, TARGET))

    # Scenario C: union filtered by min_score
    print(f"  [C] union_scored (score>={args.min_score:.2f})...")
    reads_scored, n_scored = inject_bilateral(base_reads, diff["bilateral_only"], scores, min_score=args.min_score)
    results.append(run_scenario(f"union_score>={args.min_score:.2f} ({n_scored})", reads_scored, TARGET))

    print_report(results, TARGET, diff, threshold)


if __name__ == "__main__":
    main()
