"""
audit_bilateral_coverage.py — Stage 0: Data Audit for bilateral pixel density.

Cross-references bilateral-detected pages against:
  A) Baseline inference pipeline (run_pipeline on ART_674_tess.json) — page→status map
  B) VLM ground truth (ART_674.json) — correct curr/total per page

Answers four open questions from the improvement plan:
  1. How many bilateral-only pages are already covered by baseline inference?
  2. What is the correct total for each bilateral-only page (from VLM GT)?
  3. How many bilateral-only pages have no coverage whatsoever?
  4. Do baseline and bilateral agree on document boundary placement?

Usage
-----
    python audit_bilateral_coverage.py
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from eval.inference_tuning.inference import run_pipeline  # noqa: E402
from eval.inference_tuning.params import PRODUCTION_PARAMS  # noqa: E402
from eval.pixel_density.pixel_density import compute_ratios_grid  # noqa: E402
from eval.pixel_density.sweep_bilateral import bilateral_scores, kmeans_matches  # noqa: E402
from eval.shared.types import PageRead  # noqa: E402

PDF_PATH     = "data/samples/ART_674.pdf"
TESS_FIXTURE = "eval/fixtures/real/ART_674_tess.json"
VLM_FIXTURE  = "eval/fixtures/real/ART_674.json"
TOTAL_PAGES  = 2719
TARGET       = 674
DPI          = 100
GRID         = 8
SCORE_FN     = "harmonic"


# ── Part A: Run baseline pipeline, build page→status map ─────────────────────


def build_page_status_map(docs: list) -> dict[int, dict]:
    """Build a 1-based pdf_page → status dict from pipeline Document objects.

    Status keys: doc_index, method ('ocr'|'inferred'), position_in_doc, declared_total.
    """
    page_map: dict[int, dict] = {}

    for d in docs:
        # OCR pages (direct reads assigned to this document)
        for pos, pdf_page in enumerate(d.pages, start=1):
            page_map[pdf_page] = {
                "doc_index": d.index,
                "method": "ocr",
                "position_in_doc": pos,
                "declared_total": d.declared_total,
            }
        # Inferred pages
        for pos_offset, pdf_page in enumerate(d.inferred_pages):
            # Position in doc: after all OCR pages
            page_map[pdf_page] = {
                "doc_index": d.index,
                "method": "inferred",
                "position_in_doc": len(d.pages) + pos_offset + 1,
                "declared_total": d.declared_total,
            }

    return page_map


# ── Part B: Bilateral detection + 3-way diff ────────────────────────────────


def run_bilateral() -> tuple[list[int], np.ndarray, float]:
    """Run best bilateral config; return (0-based cover indices, scores, threshold)."""
    print(f"  Rendering bilateral (dpi={DPI} grid={GRID}x{GRID})...")
    t0 = time.perf_counter()
    vectors = compute_ratios_grid(PDF_PATH, DPI, GRID)
    elapsed = time.perf_counter() - t0
    print(f"  {len(vectors)} pages in {elapsed:.1f}s")
    scores = bilateral_scores(vectors, SCORE_FN)
    matches, threshold = kmeans_matches(scores)
    print(f"  bilateral: {len(matches)} covers  threshold={threshold:.4f}")
    return matches, scores, threshold


def compute_diff(bilateral_0b: list[int], tess_reads: list[PageRead]) -> dict:
    """3-way diff between bilateral covers and Tesseract curr==1 pages."""
    tess_set = {r.pdf_page - 1 for r in tess_reads if r.curr == 1}
    bilat_set = set(bilateral_0b)
    return {
        "shared": sorted(bilat_set & tess_set),
        "bilateral_only": sorted(bilat_set - tess_set),
        "tess_only": sorted(tess_set - bilat_set),
    }


# ── VLM ground truth lookup ─────────────────────────────────────────────────


def load_vlm_gt() -> dict[int, dict]:
    """Load VLM ground truth fixture; return 1-based pdf_page → {curr, total, confidence}."""
    data = json.loads(Path(VLM_FIXTURE).read_text(encoding="utf-8"))
    vlm_map: dict[int, dict] = {}
    for r in data["reads"]:
        vlm_map[r["pdf_page"]] = {
            "curr": r.get("curr"),
            "total": r.get("total"),
            "confidence": r.get("confidence", 0.0),
        }
    return vlm_map


# ── Analysis ─────────────────────────────────────────────────────────────────


def analyze_pages(
    page_list_0b: list[int],
    label: str,
    page_map: dict[int, dict],
    vlm_map: dict[int, dict],
    scores: np.ndarray,
) -> dict:
    """Analyze a set of pages (0-based) against pipeline status and VLM GT."""
    pipeline_ocr = []
    pipeline_inferred = []
    pipeline_uncovered = []
    vlm_curr_1 = []
    vlm_curr_other = []
    vlm_missing = []

    for idx_0b in page_list_0b:
        pdf_page = idx_0b + 1  # convert to 1-based

        # Pipeline status
        status = page_map.get(pdf_page)
        if status is None:
            pipeline_uncovered.append(idx_0b)
        elif status["method"] == "ocr":
            pipeline_ocr.append(idx_0b)
        elif status["method"] == "inferred":
            pipeline_inferred.append(idx_0b)

        # VLM GT
        vlm = vlm_map.get(pdf_page)
        if vlm is None:
            vlm_missing.append(idx_0b)
        elif vlm["curr"] == 1:
            vlm_curr_1.append(idx_0b)
        else:
            vlm_curr_other.append(idx_0b)

    result = {
        "total_pages": len(page_list_0b),
        "pipeline_ocr": pipeline_ocr,
        "pipeline_inferred": pipeline_inferred,
        "pipeline_uncovered": pipeline_uncovered,
        "vlm_curr_1": vlm_curr_1,
        "vlm_curr_other": vlm_curr_other,
        "vlm_missing": vlm_missing,
    }

    # Score stats
    if page_list_0b:
        page_scores = scores[page_list_0b]
        result["score_min"] = float(np.min(page_scores))
        result["score_max"] = float(np.max(page_scores))
        result["score_mean"] = float(np.mean(page_scores))

    return result


def print_analysis(label: str, analysis: dict) -> None:
    """Pretty-print the analysis for a page group."""
    print(f"\n{label} ({analysis['total_pages']} pages):")
    print(f"  pipeline_inferred : {len(analysis['pipeline_inferred']):>4}  "
          f"(already covered by baseline inference)")
    print(f"  pipeline_ocr      : {len(analysis['pipeline_ocr']):>4}  "
          f"(boundary placement diff: both detect, different role)")
    print(f"  pipeline_uncovered: {len(analysis['pipeline_uncovered']):>4}  "
          f"(genuinely missed by both OCR and inference)")
    print()
    print("  VLM ground truth cross-ref:")
    print(f"    vlm_curr_1      : {len(analysis['vlm_curr_1']):>4}  "
          f"(VLM confirms these are cover pages)")
    print(f"    vlm_curr_other  : {len(analysis['vlm_curr_other']):>4}  "
          f"(VLM says NOT cover pages — FPs)")
    print(f"    vlm_missing     : {len(analysis['vlm_missing']):>4}  "
          f"(in the VLM gaps)")

    if "score_min" in analysis:
        print(f"\n  Bilateral scores: min={analysis['score_min']:.4f}  "
              f"max={analysis['score_max']:.4f}  mean={analysis['score_mean']:.4f}")


# ── VLM total distribution for bilateral-only vlm_curr_1 pages ──────────────


def print_vlm_totals(vlm_curr_1_0b: list[int], vlm_map: dict[int, dict]) -> None:
    """Print the total distribution for confirmed covers."""
    totals = Counter()
    for idx_0b in vlm_curr_1_0b:
        pdf_page = idx_0b + 1
        vlm = vlm_map.get(pdf_page)
        if vlm and vlm["total"] is not None:
            totals[vlm["total"]] += 1
    if totals:
        print("\n  VLM total distribution for confirmed covers:")
        for t in sorted(totals):
            print(f"    total={t}: {totals[t]} pages")


# ── Document boundary agreement ──────────────────────────────────────────────


def boundary_agreement(
    bilateral_0b: list[int],
    docs: list,
) -> tuple[int, int]:
    """Count how many pipeline doc starts match bilateral cover pages."""
    bilateral_set = set(bilateral_0b)
    doc_starts_0b = {d.start_pdf_page - 1 for d in docs}

    agree = bilateral_set & doc_starts_0b
    pipeline_only_starts = doc_starts_0b - bilateral_set
    return len(agree), len(pipeline_only_starts)


# ── Save JSON ────────────────────────────────────────────────────────────────


def save_results(
    bilateral_analysis: dict,
    tess_analysis: dict,
    pipeline_stats: dict,
    boundary_stats: dict,
    output_path: str,
) -> None:
    """Save structured audit results to JSON."""
    # Convert numpy types to plain Python for JSON serialization
    def clean(obj):
        if isinstance(obj, (np.integer, np.int64)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float64)):
            return float(obj)
        if isinstance(obj, list):
            return [clean(x) for x in obj]
        if isinstance(obj, dict):
            return {k: clean(v) for k, v in obj.items()}
        return obj

    data = {
        "pipeline": clean(pipeline_stats),
        "bilateral_only": clean(bilateral_analysis),
        "tess_only": clean(tess_analysis),
        "boundary_agreement": clean(boundary_stats),
    }
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"\nResults saved to {output_path}")


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    sep = "-" * 60
    print(f"\n{'='*60}")
    print("Stage 0: Coverage Audit")
    print(f"{'='*60}\n")

    # Step 1: Load tess fixture and run baseline pipeline
    print("Step 1: Load tess fixture + run baseline pipeline")
    tess_data = json.loads(Path(TESS_FIXTURE).read_text(encoding="utf-8"))
    tess_reads = [PageRead(**r) for r in tess_data["reads"]]
    print(f"  {len(tess_reads)} reads loaded")

    t0 = time.perf_counter()
    docs = run_pipeline(tess_reads, PRODUCTION_PARAMS)
    elapsed = time.perf_counter() - t0
    print(f"  Pipeline: {len(docs)} docs in {elapsed:.1f}s")

    n_complete = sum(1 for d in docs if d.is_complete)
    n_inferred = sum(len(d.inferred_pages) for d in docs)
    print(f"  complete={n_complete}  inferred_pages={n_inferred}")

    # Sanity check vs AI_LOG
    print("\n  Sanity check (expected ~668 docs, ~603 inferred pages):")
    print(f"    docs={len(docs)}  inferred_pages={n_inferred}")
    if abs(n_inferred - 603) > 10:
        print(f"  WARNING: inferred_pages deviates from expected 603 by {abs(n_inferred-603)}")

    # Build page→status map
    page_map = build_page_status_map(docs)
    covered_pages = len(page_map)
    uncovered_pages = TOTAL_PAGES - covered_pages
    print(f"  Pages in pipeline docs: {covered_pages}/{TOTAL_PAGES}  "
          f"(uncovered: {uncovered_pages})")

    # Step 2: Run bilateral detection
    print(f"\n{sep}")
    print("Step 2: Bilateral detection + 3-way diff")
    bilateral_0b, scores, threshold = run_bilateral()

    diff = compute_diff(bilateral_0b, tess_reads)
    print("\n  3-way diff:")
    print(f"    SHARED         : {len(diff['shared'])}")
    print(f"    BILATERAL-ONLY : {len(diff['bilateral_only'])}")
    print(f"    TESS-ONLY      : {len(diff['tess_only'])}")

    # Step 3: Load VLM ground truth
    print(f"\n{sep}")
    print("Step 3: Load VLM ground truth")
    vlm_map = load_vlm_gt()
    print(f"  {len(vlm_map)} VLM reads loaded")

    # Step 4: Cross-reference
    print(f"\n{sep}")
    print("Step 4: Cross-reference bilateral-only and tess-only vs pipeline + VLM")

    bilateral_analysis = analyze_pages(
        diff["bilateral_only"], "Bilateral-only", page_map, vlm_map, scores,
    )
    tess_analysis = analyze_pages(
        diff["tess_only"], "Tess-only", page_map, vlm_map, scores,
    )

    print_analysis("Bilateral-only", bilateral_analysis)
    print_vlm_totals(bilateral_analysis["vlm_curr_1"], vlm_map)

    print_analysis("Tess-only", tess_analysis)
    print_vlm_totals(tess_analysis["vlm_curr_1"], vlm_map)

    # Step 5: Boundary agreement
    print(f"\n{sep}")
    print("Step 5: Document boundary agreement")
    agree, pipeline_only = boundary_agreement(bilateral_0b, docs)
    print(f"  Pipeline doc starts that match bilateral covers: {agree}/{len(docs)}")
    print(f"  Pipeline doc starts NOT in bilateral covers    : {pipeline_only}/{len(docs)}")

    # Summary
    pipeline_stats = {
        "docs": len(docs),
        "complete": n_complete,
        "inferred_pages": n_inferred,
        "covered_pages": covered_pages,
        "uncovered_pages": uncovered_pages,
    }
    boundary_stats = {
        "agree": agree,
        "pipeline_only_starts": pipeline_only,
        "total_pipeline_docs": len(docs),
    }

    save_results(
        bilateral_analysis, tess_analysis,
        pipeline_stats, boundary_stats,
        "data/pixel_density/audit_coverage.json",
    )


if __name__ == "__main__":
    main()
