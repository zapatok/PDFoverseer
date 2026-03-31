"""
simulate_realistic_injection.py -- Stage 4: Realistic bilateral integration simulation.

Uses Stage 0 audit data + VLM ground truth to inject only bilateral-detected
pages that are (a) VLM-confirmed covers (curr=1), and (b) pipeline_inferred
or pipeline_ocr from the baseline.  Uses correct total=4 from VLM GT.

Scenarios:
  A) baseline — tess fixture as-is
  B) inject VLM-confirmed covers (all 86 bilateral-only + vlm_curr_1)
  C) inject only pipeline_inferred covers (65 pages — conservative)
  D) inject only pipeline_uncovered+inferred covers (no OCR-assigned pages)

Usage
-----
    python simulate_realistic_injection.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from eval.inference_tuning.inference import run_pipeline  # noqa: E402
from eval.inference_tuning.params import PRODUCTION_PARAMS  # noqa: E402
from eval.pixel_density.pixel_density import compute_ratios_grid  # noqa: E402
from eval.pixel_density.sweep_bilateral import bilateral_scores, kmeans_matches  # noqa: E402
from eval.shared.types import PageRead  # noqa: E402

PDF_PATH     = "data/samples/ART_674.pdf"
TESS_FIXTURE = "eval/fixtures/real/ART_674_tess.json"
VLM_FIXTURE  = "eval/fixtures/real/ART_674.json"
AUDIT_PATH   = "data/pixel_density/audit_coverage.json"
TARGET       = 674
DPI          = 100
GRID         = 8
SCORE_FN     = "harmonic"

SYNTH_CONFIDENCE = 0.70
SYNTH_METHOD     = "bilateral"


# ── Data loading ─────────────────────────────────────────────────────────────


def load_tess_reads() -> list[PageRead]:
    data = json.loads(Path(TESS_FIXTURE).read_text(encoding="utf-8"))
    return [PageRead(**r) for r in data["reads"]]


def load_vlm_map() -> dict[int, dict]:
    """1-based pdf_page -> {curr, total}."""
    data = json.loads(Path(VLM_FIXTURE).read_text(encoding="utf-8"))
    return {
        r["pdf_page"]: {"curr": r.get("curr"), "total": r.get("total")}
        for r in data["reads"]
    }


def load_audit() -> dict:
    return json.loads(Path(AUDIT_PATH).read_text(encoding="utf-8"))


# ── Injection ────────────────────────────────────────────────────────────────


def inject_pages(
    base_reads: list[PageRead],
    pages_0b: list[int],
    vlm_map: dict[int, dict],
) -> tuple[list[PageRead], int]:
    """Inject synthetic curr=1 reads for given pages using VLM total values.

    Skips pages where VLM GT is missing (can't determine correct total).
    Returns (combined reads, count injected).
    """
    synthetic = []
    for idx_0b in pages_0b:
        pdf_page = idx_0b + 1
        vlm = vlm_map.get(pdf_page)
        if vlm is None:
            continue  # Skip — no VLM data for this page
        synthetic.append(PageRead(
            pdf_page=pdf_page,
            curr=1,
            total=vlm["total"],
            method=SYNTH_METHOD,
            confidence=SYNTH_CONFIDENCE,
        ))

    combined = list(base_reads) + synthetic
    combined.sort(key=lambda r: r.pdf_page)
    return combined, len(synthetic)


# ── Scenario runner ──────────────────────────────────────────────────────────


def run_scenario(label: str, reads: list[PageRead]) -> dict:
    t0 = time.perf_counter()
    docs = run_pipeline(reads, PRODUCTION_PARAMS)
    elapsed = time.perf_counter() - t0

    n_docs = len(docs)
    n_complete = sum(1 for d in docs if d.is_complete)
    n_inferred = sum(len(d.inferred_pages) for d in docs)

    return {
        "label": label,
        "reads": len(reads),
        "curr1": sum(1 for r in reads if r.curr == 1),
        "docs": n_docs,
        "complete": n_complete,
        "inferred": n_inferred,
        "error": n_docs - TARGET,
        "elapsed": elapsed,
    }


# ── Report ───────────────────────────────────────────────────────────────────


def print_report(results: list[dict]) -> None:
    sep = "=" * 80
    print(f"\n{sep}")
    print("Stage 4: Realistic Integration Simulation")
    print(sep)

    hdr = (f"  {'Scenario':<42} {'curr1':>5} {'DOC':>5} {'error':>6} "
           f"{'complete':>8} {'inferred':>8} {'time':>5}")
    print(hdr)
    print(f"  {'-'*72}")

    baseline = results[0]
    for r in results:
        print(f"  {r['label']:<42} {r['curr1']:>5} {r['docs']:>5} {r['error']:>+6} "
              f"{r['complete']:>8} {r['inferred']:>8} {r['elapsed']:>5.1f}s")

    print(f"\n{sep}")
    print("  Comparison vs baseline:")
    for r in results[1:]:
        delta_docs = r["docs"] - baseline["docs"]
        delta_complete = r["complete"] - baseline["complete"]
        delta_inferred = r["inferred"] - baseline["inferred"]
        print(f"  {r['label']:<42} docs={delta_docs:>+3}  "
              f"complete={delta_complete:>+3}  inferred={delta_inferred:>+4}")

    # Decision criteria
    print(f"\n{sep}")
    print("  Decision Criteria:")
    for r in results[1:]:
        error_improved = abs(r["error"]) < abs(baseline["error"])
        no_regression = r["complete"] >= baseline["complete"]
        error_direction = r["error"] <= 0
        passed = error_improved and no_regression and error_direction
        print(f"  {r['label']:<42}")
        print(f"    Error closer to 0?     {'YES' if error_improved else 'NO':>3}  "
              f"({baseline['error']:+d} -> {r['error']:+d})")
        print(f"    No complete regression? {'YES' if no_regression else 'NO':>3}  "
              f"({baseline['complete']} -> {r['complete']})")
        print(f"    Error direction <= 0?   {'YES' if error_direction else 'NO':>3}  "
              f"({r['error']:+d})")
        print(f"    INTEGRATE? {'YES' if passed else 'NO'}")
    print(sep)


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    print("=" * 60)
    print("Stage 4: Realistic Integration Simulation")
    print("=" * 60)

    # Load data
    print("\nLoading data...")
    base_reads = load_tess_reads()
    vlm_map = load_vlm_map()
    audit = load_audit()

    bo = audit["bilateral_only"]
    vlm_curr_1 = bo["vlm_curr_1"]
    pipeline_inferred = bo["pipeline_inferred"]
    pipeline_ocr = bo["pipeline_ocr"]

    print(f"  Tess reads: {len(base_reads)}")
    print(f"  Bilateral-only VLM-confirmed covers: {len(vlm_curr_1)}")
    print(f"    of which pipeline_inferred: {len([p for p in vlm_curr_1 if p in pipeline_inferred])}")
    print(f"    of which pipeline_ocr:      {len([p for p in vlm_curr_1 if p in pipeline_ocr])}")

    # Also run the naive injection for comparison
    print("\nAlso loading bilateral for naive comparison...")
    t0 = time.perf_counter()
    vectors = compute_ratios_grid(PDF_PATH, DPI, GRID)
    print(f"  {len(vectors)} pages in {time.perf_counter()-t0:.1f}s")
    scores = bilateral_scores(vectors, SCORE_FN)
    matches, threshold = kmeans_matches(scores)
    tess_set = {r.pdf_page - 1 for r in base_reads if r.curr == 1}
    all_bilateral_only = sorted(set(matches) - tess_set)

    # Scenarios
    print("\nRunning scenarios...\n")
    results = []

    # A) Baseline
    print("  [A] Baseline (tess only)...")
    results.append(run_scenario("A: baseline (tess only)", base_reads))

    # B) Inject all VLM-confirmed bilateral covers (total=4)
    inject_set_b = vlm_curr_1
    reads_b, n_b = inject_pages(base_reads, inject_set_b, vlm_map)
    print(f"  [B] VLM-confirmed covers ({n_b} injected, total=4)...")
    results.append(run_scenario(f"B: vlm_confirmed ({n_b} inject, total=4)", reads_b))

    # C) Inject only pipeline_inferred covers (conservative)
    inject_set_c = [p for p in vlm_curr_1 if p in pipeline_inferred]
    reads_c, n_c = inject_pages(base_reads, inject_set_c, vlm_map)
    print(f"  [C] Pipeline-inferred only ({n_c} injected)...")
    results.append(run_scenario(f"C: inferred_only ({n_c} inject, total=4)", reads_c))

    # D) Naive injection (all 172 bilateral-only, total=1) for comparison
    naive_synth = [
        PageRead(pdf_page=idx + 1, curr=1, total=1,
                 method="bilateral", confidence=0.70)
        for idx in all_bilateral_only
    ]
    reads_d = sorted(list(base_reads) + naive_synth, key=lambda r: r.pdf_page)
    print(f"  [D] Naive injection ({len(naive_synth)} bilateral-only, total=1)...")
    results.append(run_scenario(f"D: naive_all ({len(naive_synth)} inject, total=1)", reads_d))

    # E) Inject all VLM-confirmed, PLUS original naive bilateral-only
    # This tests the combined effect
    inject_set_e = vlm_curr_1
    reads_e, n_e = inject_pages(base_reads, inject_set_e, vlm_map)
    # Also add the non-VLM-confirmed bilateral-only as total=1
    non_confirmed = [p for p in all_bilateral_only if p not in set(vlm_curr_1)]
    naive_non_confirmed = [
        PageRead(pdf_page=idx + 1, curr=1, total=1,
                 method="bilateral", confidence=0.50)
        for idx in non_confirmed
    ]
    reads_e = sorted(reads_e + naive_non_confirmed, key=lambda r: r.pdf_page)
    print("  [E] VLM-confirmed(total=4) + rest(total=1)...")
    results.append(run_scenario(
        f"E: confirmed+rest ({n_e}@t4 + {len(non_confirmed)}@t1)", reads_e))

    print_report(results)


if __name__ == "__main__":
    main()
