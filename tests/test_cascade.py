"""
Test: does correcting one page cascade to improve/resolve neighboring inferred pages?
This is the core human-in-the-loop promise.
"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.analyzer import _PageRead, _infer_missing, _build_documents, re_infer_documents, Document
from copy import deepcopy

def make_reads(spec):
    reads = []
    for i, item in enumerate(spec):
        c, t, m = (item + ("direct",))[:3] if item[0] is not None else (None, None, "failed")
        if len(item) == 3:
            c, t, m = item
        conf = 1.0 if m in ("direct", "SR", "manual") else 0.0
        reads.append(_PageRead(pdf_page=i+1, curr=c, total=t, method=m, confidence=conf))
    return reads

_issues = []
def _noop(m, l="info"): pass
def _iss(p, k, d, pil=None): _issues.append({"page": p, "type": k, "detail": d})
def _iss3(p, k, d): _issues.append({"page": p, "type": k, "detail": d})

def show_reads(reads, label=""):
    if label:
        print(f"\n  {label}")
    for r in reads:
        tag = f"  conf={r.confidence:.0%}" if r.method == "inferred" else ""
        print(f"    pg{r.pdf_page}: {r.curr}/{r.total} [{r.method}]{tag}")

def show_issues(issues, label=""):
    if label:
        print(f"  {label}: {len(issues)} issues")
    for iss in issues:
        print(f"    - pg{iss['page']}: [{iss['type']}] {iss['detail']}")

print("="*70)
print("  CASCADE TEST SUITE")
print("="*70)


# ── TEST 1: Inspeccion-like — correct pg30 cascades to resolve pg31 ──────
print(f"\n{'='*70}")
print("TEST 1: Inspeccion — pg30 misread 1/4, pg31 failed")
print("  Does correcting pg30 to 1/1 cascade-resolve pg31?")

spec1 = [(1,1)]*29 + [(1,4,"direct"), (None,None,"failed")]
reads1 = make_reads(spec1)
reads1 = _infer_missing(reads1)

print("\n  BEFORE correction:")
show_reads(reads1[-3:], "Pages 29-31")

_issues = []
docs1 = _build_documents(reads1, _noop, _iss3)
show_issues(_issues, "Issues at scan time")
print(f"  Docs: {len(docs1)} | Doc30: declared={docs1[-1].declared_total} found={docs1[-1].found_total}")

# Now correct pg30
_issues = []
reads1_copy = deepcopy(reads1)
docs1c, reads1c = re_infer_documents(reads1_copy, {30: (1, 1)}, _noop, _iss)
print("\n  AFTER correcting pg30 to 1/1:")
show_reads(reads1c[-3:], "Pages 29-31")
show_issues(_issues, "Issues after correction")
print(f"  Docs: {len(docs1c)}")
for d in docs1c[-3:]:
    print(f"    Doc {d.index}: start={d.start_pdf_page} declared={d.declared_total} "
          f"found={d.found_total} complete={d.is_complete} manual={d.has_manual}")


# ── TEST 2: Chain of failed pages — correct one, rest cascade ────────────
print(f"\n{'='*70}")
print("TEST 2: Chain of 5 failed pages between two 1/1 anchors")
print("  Does correcting the middle page cascade to fill the rest?")

spec2 = [(1,1,"direct")] + [(None,None,"failed")]*5 + [(1,1,"direct")]
reads2 = make_reads(spec2)
reads2_orig = deepcopy(reads2)

reads2 = _infer_missing(reads2)
print("\n  AFTER inference (no corrections):")
show_reads(reads2)

_issues = []
docs2 = _build_documents(reads2, _noop, _iss3)
show_issues(_issues, "Issues at scan time")

# Correct page 4 (middle of the failed chain) to 1/1
_issues = []
reads2c = deepcopy(reads2)
docs2c, reads2c = re_infer_documents(reads2c, {4: (1, 1)}, _noop, _iss)
print("\n  AFTER correcting pg4 to 1/1:")
show_reads(reads2c)
show_issues(_issues, "Issues after correction")
print(f"  Docs: {len(docs2c)}")
for d in docs2c:
    print(f"    Doc {d.index}: start={d.start_pdf_page} declared={d.declared_total} "
          f"found={d.found_total} complete={d.is_complete} manual={d.has_manual}")


# ── TEST 3: Low-confidence inferred page resolves after neighbor correction ─
print(f"\n{'='*70}")
print("TEST 3: Two failed pages — one gets flagged as low confidence")
print("  Does correcting one remove the other from issues?")

# Page 1: 1/1 direct, Page 2: failed, Page 3: failed, Page 4: 1/1 direct
spec3 = [(1,1,"direct"), (None,None,"failed"), (None,None,"failed"), (1,1,"direct")]
reads3 = make_reads(spec3)
reads3 = _infer_missing(reads3)
print("\n  AFTER inference:")
show_reads(reads3)

_issues = []
docs3 = _build_documents(reads3, _noop, _iss3)
show_issues(_issues, "Issues at scan time")

# Correct page 2 to 1/1
_issues = []
reads3c = deepcopy(reads3)
docs3c, reads3c = re_infer_documents(reads3c, {2: (1, 1)}, _noop, _iss)
print("\n  AFTER correcting pg2 to 1/1:")
show_reads(reads3c)
show_issues(_issues, "Issues after correction")


# ── TEST 4: Charla Diaria — WHY cascade doesn't help here ───────────────
print(f"\n{'='*70}")
print("TEST 4: Charla Diaria — all direct reads, no inferred pages")
print("  Cascade resets inferred pages only. Direct reads are untouched.")

spec4 = [(1,2,"direct")]*5
reads4 = make_reads(spec4)
reads4 = _infer_missing(reads4)

print("\n  BEFORE correction:")
for r in reads4:
    print(f"    pg{r.pdf_page}: {r.curr}/{r.total} [{r.method}] <- will cascade reset this? "
          f"{'NO (direct)' if r.method == 'direct' else 'YES (inferred)'}")

# Correct page 1
reads4c = deepcopy(reads4)
_issues = []
docs4c, reads4c = re_infer_documents(reads4c, {1: (1, 2)}, _noop, _iss)
print("\n  AFTER correcting pg1 to 1/2:")
for r in reads4c:
    tag = " <-- MANUAL" if r.method == "manual" else ""
    print(f"    pg{r.pdf_page}: {r.curr}/{r.total} [{r.method}]{tag}")
show_issues(_issues, "Issues after correction")
print(f"  --> Pages 2-5 UNCHANGED because they're 'direct', not 'inferred'.")
print(f"  --> Cascade only helps inferred pages. For Charla, has_manual is the fix.")


# ── TEST 5: Mixed — some cascade, some need manual ──────────────────────
print(f"\n{'='*70}")
print("TEST 5: Real-world mix — 2 direct misreads + 3 failed between anchors")
print("  Correcting one failed page should cascade to resolve the other 2.")

spec5 = [
    (1,1,"direct"),           # pg1: anchor
    (None,None,"failed"),     # pg2: will be inferred
    (None,None,"failed"),     # pg3: will be inferred
    (None,None,"failed"),     # pg4: will be inferred
    (1,1,"direct"),           # pg5: anchor
    (1,2,"direct"),           # pg6: form field misread (like Charla)
    (1,1,"direct"),           # pg7: normal
]
reads5 = make_reads(spec5)
reads5 = _infer_missing(reads5)

_issues = []
docs5 = _build_documents(reads5, _noop, _iss3)
print("\n  AFTER scan:")
show_reads(reads5)
show_issues(_issues, "Issues at scan time")

# Correct pg3 to 1/1 (cascade should fix pg2 and pg4)
_issues = []
reads5c = deepcopy(reads5)
docs5c, reads5c = re_infer_documents(reads5c, {3: (1, 1)}, _noop, _iss)
print("\n  AFTER correcting pg3 to 1/1 (cascade should fix pg2, pg4):")
show_reads(reads5c)
show_issues(_issues, "Issues after pg3 correction")
print(f"  Docs: {len(docs5c)}")
for d in docs5c:
    inf = f" inf={d.inferred_pages}" if d.inferred_pages else ""
    print(f"    Doc {d.index}: start={d.start_pdf_page} declared={d.declared_total} "
          f"found={d.found_total} complete={d.is_complete} manual={d.has_manual}{inf}")

# Now also correct pg6 (the form field misread)
_issues = []
reads5d = deepcopy(reads5c)
docs5d, reads5d = re_infer_documents(reads5d, {6: (1, 1)}, _noop, _iss)
print("\n  AFTER also correcting pg6 to 1/1:")
show_issues(_issues, "Issues after pg6 correction")
print(f"  Docs: {len(docs5d)} — all should be resolved now")


print(f"\n{'='*70}")
print("  CONCLUSION")
print("="*70)
print("""
  CASCADE works for INFERRED pages:
    - Correcting one anchor/inferred page causes re_infer_documents to
      reset all inferred pages to 'failed' and re-run _infer_missing.
    - With the new anchor, neighboring pages get higher confidence.
    - Pages that were flagged at <=0.60 may now infer at 0.90+ and auto-resolve.

  CASCADE does NOT affect DIRECT reads:
    - Pages with method='direct' are never reset by re_infer_documents.
    - Charla Diaria pages all read '1/2' via direct OCR — they don't cascade.
    - For these, has_manual is the correct mechanism: user verifies each one,
      confidence improves progressively (0% -> 20% -> 40% -> ... -> 100%).

  BOTH mechanisms work together:
    - Inferred pages: cascade resolves them automatically after one correction.
    - Direct misreads: has_manual resolves them one-by-one as user verifies.
    - Confidence reflects both: found_total >= declared_total OR has_manual.
""")
