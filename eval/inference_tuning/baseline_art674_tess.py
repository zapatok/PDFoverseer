#!/usr/bin/env python
"""
Baseline eval for ART_674 with PRODUCTION_PARAMS — Tesseract fixture.

Usage:
    python eval/baseline_art674_tess.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.inference import PageRead, run_pipeline
from eval.params import PRODUCTION_PARAMS

FIXTURE_PATH = Path("eval/fixtures/real/ART_674_tess.json")
GT = {"doc_count": 674, "complete_count": 662, "inferred_count": 35}

REGION_UNREADABLE = (1753, 1933)
TOTAL_PAGES = 2719

# AI log reference values (logINS_31_fix.txt, ART_670.pdf with Tesseract)
AI_LOG = {"doc": 668, "complete": 606, "inferred_pages": 603}


def region_label(pdf_page: int) -> str:
    if pdf_page < REGION_UNREADABLE[0]:
        return "p1-1752"
    if pdf_page <= REGION_UNREADABLE[1]:
        return "p1753-1933"
    return "p1934-2719"


def main() -> None:
    # Load fixture
    data = json.loads(FIXTURE_PATH.read_text())
    reads = [PageRead(**r) for r in data["reads"]]

    print(f"Fixture: {len(reads)} reads  (total PDF pages: {TOTAL_PAGES}, "
          f"missing: {TOTAL_PAGES - len(reads)})\n")

    # Reads breakdown by region
    region_reads: dict[str, dict] = {
        "p1-1752":    {"total": 0, "failed": 0},
        "p1753-1933": {"total": 0, "failed": 0},
        "p1934-2719": {"total": 0, "failed": 0},
    }
    for r in reads:
        lbl = region_label(r.pdf_page)
        region_reads[lbl]["total"] += 1
        if r.method == "failed":
            region_reads[lbl]["failed"] += 1

    totals_in_fixture = Counter(r.total for r in reads if r.total is not None)
    print("-- Reads by region (fixture) --")
    for lbl, d in region_reads.items():
        fail_pct = 100 * d["failed"] / d["total"] if d["total"] else 0
        print(f"  {lbl:<15}  {d['total']:4d} reads  {d['failed']:3d} failed ({fail_pct:.0f}%)")
    print(f"  {'TOTAL':<15}  {len(reads):4d} reads  "
          f"{sum(d['failed'] for d in region_reads.values()):3d} failed")
    print("\n  Most common declared totals: "
          + ", ".join(f"total={k}:{v}" for k, v in totals_in_fixture.most_common(5)))
    print()

    # Run pipeline
    docs = run_pipeline(reads, PRODUCTION_PARAMS)

    got_docs     = len(docs)
    got_complete = sum(1 for d in docs if d.is_complete)
    got_inferred = sum(len(d.inferred_pages) for d in docs)

    # --- Summary vs GT ---
    print("-- Baseline vs Ground Truth --")
    print(f"  {'Metric':<18}  {'Eval':>6}  {'GT':>6}  {'Delta':>7}")
    print(f"  {'-'*18}  {'-'*6}  {'-'*6}  {'-'*7}")
    print(f"  {'doc_count':<18}  {got_docs:>6}  {GT['doc_count']:>6}  {got_docs - GT['doc_count']:>+7}")
    print(f"  {'complete_count':<18}  {got_complete:>6}  {GT['complete_count']:>6}  {got_complete - GT['complete_count']:>+7}")
    print(f"  {'inferred_pages':<18}  {got_inferred:>6}  {GT['inferred_count']:>6}  {got_inferred - GT['inferred_count']:>+7}")
    print()

    # --- Per-region doc breakdown ---
    region_docs: dict[str, dict] = {
        "p1-1752":    {"docs": 0, "complete": 0},
        "p1753-1933": {"docs": 0, "complete": 0},
        "p1934-2719": {"docs": 0, "complete": 0},
    }
    for d in docs:
        lbl = region_label(d.start_pdf_page)
        region_docs[lbl]["docs"] += 1
        if d.is_complete:
            region_docs[lbl]["complete"] += 1

    print("-- Per-region doc breakdown --")
    print(f"  {'Region':<15}  {'Eval docs':>9}  {'Complete':>8}  {'Incomplete':>10}")
    print(f"  {'-'*15}  {'-'*9}  {'-'*8}  {'-'*10}")
    for lbl in ("p1-1752", "p1753-1933", "p1934-2719"):
        d = region_docs[lbl]["docs"]
        c = region_docs[lbl]["complete"]
        print(f"  {lbl:<15}  {d:>9}  {c:>8}  {d-c:>10}")
    td = sum(v["docs"] for v in region_docs.values())
    tc = sum(v["complete"] for v in region_docs.values())
    print(f"  {'TOTAL':<15}  {td:>9}  {tc:>8}  {td-tc:>10}")
    print()

    # --- Incomplete doc detail ---
    incomplete_docs = [d for d in docs if not d.is_complete]
    print(f"-- Incomplete docs ({len(incomplete_docs)} total) --")
    print(f"  {'#':>4}  {'start_page':>10}  {'region':<15}  {'declared':>8}  {'found':>5}  {'missing':>7}")
    print(f"  {'-'*4}  {'-'*10}  {'-'*15}  {'-'*8}  {'-'*5}  {'-'*7}")
    for d in incomplete_docs:
        missing = d.declared_total - d.found_total
        lbl = region_label(d.start_pdf_page)
        print(f"  {d.index:>4}  {d.start_pdf_page:>10}  {lbl:<15}  {d.declared_total:>8}  {d.found_total:>5}  {missing:>7}")
    print()

    # --- Comparison with AI log ---
    print("-- Comparison with AI log (logINS_31_fix.txt) --")
    print(f"  {'Metric':<18}  {'Eval':>6}  {'AI log':>6}  {'Diff':>6}")
    print(f"  {'-'*18}  {'-'*6}  {'-'*6}  {'-'*6}")
    print(f"  {'doc_count':<18}  {got_docs:>6}  {AI_LOG['doc']:>6}  {got_docs - AI_LOG['doc']:>+6}")
    print(f"  {'complete_count':<18}  {got_complete:>6}  {AI_LOG['complete']:>6}  {got_complete - AI_LOG['complete']:>+6}")
    print(f"  {'inferred_pages':<18}  {got_inferred:>6}  {AI_LOG['inferred_pages']:>6}  {got_inferred - AI_LOG['inferred_pages']:>+6}")


if __name__ == "__main__":
    main()
