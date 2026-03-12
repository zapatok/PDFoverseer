"""
Test harness for inference engine scenarios.
Simulates OCR reads as arrays and exercises _infer_missing, _build_documents,
re_infer_documents, and the confidence metric calculation.

No actual PDFs or OCR — just synthetic _PageRead arrays.
"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.analyzer import _PageRead, _infer_missing, _build_documents, re_infer_documents, Document
from copy import deepcopy

# ── Helpers ──────────────────────────────────────────────────────────────────

def make_reads(spec: list[tuple]) -> list[_PageRead]:
    """Build _PageRead list from compact spec.
    Each tuple: (curr, total, method)  or  (curr, total)
    """
    reads = []
    for i, item in enumerate(spec):
        if len(item) == 3:
            c, t, m = item
        else:
            c, t = item
            m = "direct" if c is not None else "failed"
        conf = 1.0 if m in ("direct", "SR", "manual") else 0.0
        reads.append(_PageRead(pdf_page=i+1, curr=c, total=t, method=m, confidence=conf))
    return reads


def calc_confidence_v1(docs: list[Document]) -> float:
    """Current server-side confidence formula (OCR only)."""
    if not docs:
        return 1.0
    pages_ok = sum(1 for d in docs if d.found_total >= d.declared_total)
    return pages_ok / len(docs)


def calc_confidence_v3(docs: list[Document], reads: list[_PageRead]) -> float:
    """V3: OCR-complete OR doc has a manually verified page."""
    if not docs:
        return 1.0
    manual_pages = {r.pdf_page for r in reads if r.method == "manual"}
    ok = 0
    for d in docs:
        if d.found_total >= d.declared_total:
            ok += 1
        else:
            doc_all_pages = set(d.pages) | set(d.inferred_pages) | {d.start_pdf_page}
            if doc_all_pages & manual_pages:
                ok += 1
    return ok / len(docs)


_collected_issues = []

def _noop_log(msg, lvl="info"):
    pass

def _collect_issue(page, kind, detail):
    _collected_issues.append({"page": page, "type": kind, "detail": detail})

def _collect_issue_4arg(page, kind, detail, pil_img):
    _collected_issues.append({"page": page, "type": kind, "detail": detail})


def run_scenario(name: str, spec: list[tuple], expected_docs: int, description: str = ""):
    """Run a full scenario and print diagnostics."""
    global _collected_issues
    _collected_issues = []

    reads = make_reads(spec)

    # Run inference on failed pages
    failed_before = sum(1 for r in reads if r.method == "failed")
    reads = _infer_missing(reads)
    inferred_after = sum(1 for r in reads if r.method == "inferred")

    # Collect issues from inferred pages (low confidence)
    for r in reads:
        if r.method == "inferred" and r.confidence <= 0.60:
            conf_label = "MEDIA" if r.confidence >= 0.50 else "BAJA"
            _collected_issues.append({
                "page": r.pdf_page,
                "type": f"inferida ({conf_label} {r.confidence:.0%})",
                "detail": f"Pag {r.pdf_page}: inferida como {r.curr}/{r.total}"
            })

    # Build documents
    docs = _build_documents(reads, _noop_log, _collect_issue)

    cv1 = calc_confidence_v1(docs)
    cv3 = calc_confidence_v3(docs, reads)

    complete = sum(1 for d in docs if d.is_complete)
    incomplete = sum(1 for d in docs if not d.is_complete)
    issues_by_type = {}
    for iss in _collected_issues:
        t = iss["type"]
        issues_by_type[t] = issues_by_type.get(t, 0) + 1

    status = "OK" if len(docs) == expected_docs else "FAIL"
    print(f"\n{'='*70}")
    print(f"[{status}] SCENARIO: {name}")
    if description:
        print(f"  {description}")
    print(f"  Pages: {len(spec)} | Failed->Inferred: {failed_before}->{inferred_after}")
    print(f"  Docs found: {len(docs)} (expected {expected_docs}) | Complete: {complete} | Incomplete: {incomplete}")
    print(f"  Confidence v1 (OCR only): {cv1:.0%}")
    print(f"  Confidence v3 (OCR+manual): {cv3:.0%}")
    print(f"  Issues ({len(_collected_issues)}): {issues_by_type}")

    for d in docs:
        inf_tag = f" inf={d.inferred_pages}" if d.inferred_pages else ""
        print(f"    Doc {d.index}: start={d.start_pdf_page} declared={d.declared_total} "
              f"found={d.found_total} seq_ok={d.sequence_ok} complete={d.is_complete}"
              f"{inf_tag}")

    return docs, reads, list(_collected_issues)


def simulate_correction(name: str, reads: list[_PageRead], corrections: dict):
    """Simulate user corrections and compare v1 vs v3 confidence."""
    global _collected_issues
    _collected_issues = []

    reads_copy = deepcopy(reads)

    # Before correction
    docs_before = _build_documents(deepcopy(reads_copy), _noop_log, lambda p,k,d: None)
    cv1_before = calc_confidence_v1(docs_before)

    # Apply correction
    docs_after, new_reads = re_infer_documents(
        reads=reads_copy,
        corrections=corrections,
        on_log=_noop_log,
        on_issue=_collect_issue_4arg
    )

    cv1_after = calc_confidence_v1(docs_after)
    cv3_after = calc_confidence_v3(docs_after, new_reads)

    # Count issues that would exist with the new _build_documents logic
    # (incompleto suppressed for docs with manual pages)
    manual_pages = {r.pdf_page for r in new_reads if r.method == "manual"}
    filtered_issues = []
    for iss in _collected_issues:
        # incompleto issues that belong to a doc with manual pages should be suppressed
        if iss["type"] == "incompleto":
            # Check if this issue page is in a doc that has manual pages
            for d in docs_after:
                doc_pages = set(d.pages) | set(d.inferred_pages) | {d.start_pdf_page}
                if iss["page"] in doc_pages and (doc_pages & manual_pages):
                    break
            else:
                filtered_issues.append(iss)
        else:
            filtered_issues.append(iss)

    # Also compute: what if we emitted incompleto for non-manual docs?
    incompleto_remaining = 0
    for d in docs_after:
        doc_pages = set(d.pages) | set(d.inferred_pages) | {d.start_pdf_page}
        has_manual = bool(doc_pages & manual_pages)
        if d.found_total < d.declared_total and not has_manual:
            incompleto_remaining += 1

    v1_delta = cv1_after - cv1_before
    print(f"\n  CORRECTION: {name}")
    print(f"    Corrections: {corrections}")
    print(f"    v1: {cv1_before:.0%} -> {cv1_after:.0%} ({'+' if v1_delta>=0 else ''}{v1_delta:.0%})")
    print(f"    v3: {cv3_after:.0%}")
    print(f"    Issues from re_infer: {len(_collected_issues)} | Incompleto still pending: {incompleto_remaining}")

    for d in docs_after:
        doc_pages = set(d.pages) | set(d.inferred_pages) | {d.start_pdf_page}
        has_manual = bool(doc_pages & manual_pages)
        tag = " [MANUAL]" if has_manual else ""
        print(f"      Doc {d.index}: declared={d.declared_total} found={d.found_total} "
              f"complete={d.is_complete}{tag}")

    return docs_after, new_reads


# ============================================================================
# SCENARIOS
# ============================================================================

print("\n" + "="*70)
print("  INFERENCE ENGINE TEST SUITE — v1 vs v3")
print("="*70)

# ── 1. Charla Diaria ─────────────────────────────────────────────────────
docs1, reads1, iss1 = run_scenario(
    "Charla Diaria — 5 pages all read '1/2' (form field)",
    [(1,2), (1,2), (1,2), (1,2), (1,2)],
    expected_docs=5,
    description="5 single-page docs. OCR reads form field '1 de 2'."
)
# Progressive corrections: 1, then 3, then all 5
simulate_correction("Verify page 1 (same 1/2 data)", reads1, {1: (1, 2)})
simulate_correction("Verify pages 1-3 (same 1/2)", reads1, {1:(1,2), 2:(1,2), 3:(1,2)})
simulate_correction("Verify all 5 pages (same 1/2)", reads1,
                    {1:(1,2), 2:(1,2), 3:(1,2), 4:(1,2), 5:(1,2)})
simulate_correction("Correct page 1 to 1/1", reads1, {1: (1, 1)})
simulate_correction("Correct all to 1/1", reads1,
                    {1:(1,1), 2:(1,1), 3:(1,1), 4:(1,1), 5:(1,1)})


# ── 2. Inspeccion ────────────────────────────────────────────────────────
insp_spec = []
for i in range(31):
    pg = i + 1
    if pg in [3,5,10,14,23,24,25,26,27,28,29]:
        insp_spec.append((None, None, "failed"))
    elif pg == 30:
        insp_spec.append((1, 4, "direct"))
    elif pg == 31:
        insp_spec.append((None, None, "failed"))
    else:
        insp_spec.append((1, 1, "direct"))

docs2, reads2, iss2 = run_scenario(
    "Inspeccion — 31 pages, all 1-page docs, OCR failures + misread pg30",
    insp_spec, expected_docs=31,
    description="Pages 3,5,10,14,23-29,31 failed. Page 30 misreads '1/4'."
)
simulate_correction("Correct page 30 to 1/1", reads2, {30: (1, 1)})


# ── 3. Clean multi-page ─────────────────────────────────────────────────
docs3, reads3, iss3 = run_scenario(
    "Clean 3-page docs — perfect OCR",
    [(1,3),(2,3),(3,3), (1,3),(2,3),(3,3), (1,3),(2,3),(3,3)],
    expected_docs=3
)


# ── 4. Mixed sizes ──────────────────────────────────────────────────────
docs4, reads4, iss4 = run_scenario(
    "Mixed sizes — 1pg, 3pg, 2pg, 1pg all correct",
    [(1,1), (1,3),(2,3),(3,3), (1,2),(2,2), (1,1)],
    expected_docs=4
)


# ── 5. Multi-page, middle fails ─────────────────────────────────────────
docs5, reads5, iss5 = run_scenario(
    "3-page doc, page 2 fails — inference fills gap",
    [(1,3,"direct"), (None,None,"failed"), (3,3,"direct")],
    expected_docs=1
)


# ── 6. Truncated doc ────────────────────────────────────────────────────
docs6, reads6, iss6 = run_scenario(
    "Truncated: declares 3 pages, PDF has only 2",
    [(1,3,"direct"), (2,3,"direct")],
    expected_docs=1,
    description="Doc says 3 but only 2 exist."
)
simulate_correction("Verify as-is (same 1/3)", reads6, {1: (1, 3)})
simulate_correction("Correct to 1/2", reads6, {1: (1, 2)})


# ── 7. Mixed with failures ──────────────────────────────────────────────
docs7, reads7, iss7 = run_scenario(
    "2pg doc + failed + 1pg + 3pg-with-gap",
    [(1,2),(2,2), (None,None,"failed"), (1,1), (1,3),(None,None,"failed"),(3,3)],
    expected_docs=4,
    description="Tests inference between docs of different sizes."
)


# ── 8. Total failure ────────────────────────────────────────────────────
docs8, reads8, iss8 = run_scenario(
    "Complete OCR failure — 5 pages all failed",
    [(None,None,"failed")] * 5,
    expected_docs=5,
    description="No OCR data. Engine must guess."
)
simulate_correction("Correct page 1 to 1/1", reads8, {1: (1, 1)})
simulate_correction("Correct pages 1,2,3 to 1/1", reads8, {1:(1,1), 2:(1,1), 3:(1,1)})


# ── 9. Mostly good + 2 misreads ─────────────────────────────────────────
docs9, reads9, iss9 = run_scenario(
    "8 correct 1/1 + 2 misread as 1/2",
    [(1,1)]*4 + [(1,2)] + [(1,1)]*3 + [(1,2)] + [(1,1)],
    expected_docs=10,
    description="Pages 5 and 9 misread as 1/2."
)
simulate_correction("Correct page 5 only", reads9, {5: (1,1)})
simulate_correction("Correct both 5 and 9", reads9, {5:(1,1), 9:(1,1)})
simulate_correction("Verify page 5 with same 1/2", reads9, {5: (1,2)})


# ── 10. Mix 1-page + 2-page correct ─────────────────────────────────────
docs10, reads10, iss10 = run_scenario(
    "Mix 1pg + 2pg docs, all correct",
    [(1,1), (1,2),(2,2), (1,1), (1,2),(2,2), (1,1)],
    expected_docs=5
)


# ── 11. Misread total consistently ──────────────────────────────────────
docs11, reads11, iss11 = run_scenario(
    "3 pages all read X/4 instead of X/3",
    [(1,4), (2,4), (3,4)],
    expected_docs=1,
    description="OCR reads total=4, but only 3 pages exist."
)
simulate_correction("Verify as-is (same 1/4)", reads11, {1: (1, 4)})
simulate_correction("Correct to 1/3", reads11, {1: (1, 3)})


# ── 12. Stress test ─────────────────────────────────────────────────────
import random
random.seed(42)
stress_spec = []
for i in range(50):
    if random.random() < 0.30:
        stress_spec.append((None, None, "failed"))
    else:
        stress_spec.append((1, 1, "direct"))

docs12, reads12, iss12 = run_scenario(
    "Stress: 50 single-page, 30% failure",
    stress_spec, expected_docs=50
)


# ── 13. NEW: Legitimate multi-page incomplete + correction ───────────────
docs13, reads13, iss13 = run_scenario(
    "2-page doc + 3-page doc where pg3 missing",
    [(1,2),(2,2), (1,3),(2,3)],
    expected_docs=2,
    description="Doc 1: 2pg complete. Doc 2: declares 3pg, only 2 found."
)
simulate_correction("Correct doc2 start (pg3) to 1/2", reads13, {3: (1, 2)})
simulate_correction("Verify doc2 start (same 1/3)", reads13, {3: (1, 3)})


# ── 14. NEW: Sequential corrections on same PDF ─────────────────────────
# Simulate: correct page 1, THEN correct page 2 (incremental)
print(f"\n{'='*70}")
print("[MULTI-STEP] Charla sequential corrections (simulating real user flow)")

reads_seq = deepcopy(reads1)
print("  Initial state: 5 docs all 1/2, v1=0%, v3=0%")

# Step 1: correct page 1
_collected_issues = []
docs_s1, reads_seq = re_infer_documents(reads_seq, {1: (1, 2)}, _noop_log, _collect_issue_4arg)
cv1_s1 = calc_confidence_v1(docs_s1)
cv3_s1 = calc_confidence_v3(docs_s1, reads_seq)
manual_s1 = {r.pdf_page for r in reads_seq if r.method == "manual"}
incompleto_s1 = sum(1 for d in docs_s1
                    if d.found_total < d.declared_total
                    and not (set(d.pages) | set(d.inferred_pages) | {d.start_pdf_page}) & manual_s1)
print(f"  After verify pg1: v1={cv1_s1:.0%} v3={cv3_s1:.0%} incompleto_pending={incompleto_s1}")

# Step 2: correct page 3
_collected_issues = []
docs_s2, reads_seq = re_infer_documents(reads_seq, {3: (1, 2)}, _noop_log, _collect_issue_4arg)
cv1_s2 = calc_confidence_v1(docs_s2)
cv3_s2 = calc_confidence_v3(docs_s2, reads_seq)
manual_s2 = {r.pdf_page for r in reads_seq if r.method == "manual"}
incompleto_s2 = sum(1 for d in docs_s2
                    if d.found_total < d.declared_total
                    and not (set(d.pages) | set(d.inferred_pages) | {d.start_pdf_page}) & manual_s2)
print(f"  After verify pg3: v1={cv1_s2:.0%} v3={cv3_s2:.0%} incompleto_pending={incompleto_s2}")

# Step 3: correct page 5
_collected_issues = []
docs_s3, reads_seq = re_infer_documents(reads_seq, {5: (1, 2)}, _noop_log, _collect_issue_4arg)
cv1_s3 = calc_confidence_v1(docs_s3)
cv3_s3 = calc_confidence_v3(docs_s3, reads_seq)
manual_s3 = {r.pdf_page for r in reads_seq if r.method == "manual"}
incompleto_s3 = sum(1 for d in docs_s3
                    if d.found_total < d.declared_total
                    and not (set(d.pages) | set(d.inferred_pages) | {d.start_pdf_page}) & manual_s3)
print(f"  After verify pg5: v1={cv1_s3:.0%} v3={cv3_s3:.0%} incompleto_pending={incompleto_s3}")


# ============================================================================
# SUMMARY
# ============================================================================

print(f"\n\n{'='*70}")
print("  SUMMARY TABLE")
print("="*70)
print(f"{'Scenario':<50} {'Docs':>5} {'Exp':>5} {'v1':>6} {'v3':>6} {'Iss':>4}")
print("-"*80)

all_results = [
    ("1. Charla Diaria (5x'1/2')", docs1, 5, iss1),
    ("2. Inspeccion (31pg, misread pg30)", docs2, 31, iss2),
    ("3. Clean 3-page docs", docs3, 3, iss3),
    ("4. Mixed sizes perfect", docs4, 4, iss4),
    ("5. 3-page, middle fails", docs5, 1, iss5),
    ("6. Truncated doc (2 of 3)", docs6, 1, iss6),
    ("7. Mixed with failures", docs7, 4, iss7),
    ("8. Total OCR failure", docs8, 5, iss8),
    ("9. 8 good + 2 misreads", docs9, 10, iss9),
    ("10. Mix 1pg + 2pg correct", docs10, 5, iss10),
    ("11. Misread total (X/4 not X/3)", docs11, 1, iss11),
    ("12. Stress 50pg 30% fail", docs12, 50, iss12),
    ("13. Multi-page incomplete", docs13, 2, iss13),
]

for name, docs, expected, issues in all_results:
    n = len(docs)
    cv1 = calc_confidence_v1(docs)
    cv3 = calc_confidence_v3(docs, [])  # v3 at scan time = v1 (no manual pages)
    match = "OK" if n == expected else "!!"
    print(f"[{match}] {name:<48} {n:>5} {expected:>5} {cv1:>5.0%} {cv3:>5.0%} {len(issues):>4}")

print(f"\nNote: v3 at scan time = v1 (no manual pages yet).")
print(f"The difference appears after corrections (see CORRECTION sections above).")
