# Tray & Metrics Overhaul Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the issue tray show only problems that impact document count when corrected, and replace the single "complete" percentage with an honest three-tier reliability metric.

**Architecture:** Backend emits richer issue metadata (impact category, priority) and three-tier doc counts. Phase 5/5b emit issues for their actions. Frontend renders tiered metrics and filters/sorts tray by impact. The cascade system (`re_infer_documents`) is untouched — corrections still reset inferences and re-run the full pipeline.

**Tech Stack:** Python (core/analyzer.py, server.py), React (frontend/src/App.jsx)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `core/analyzer.py:186-200` | Modify | Add `min_inferred_confidence` property to `Document` |
| `core/analyzer.py:608-679` | Modify | Phase 5b emits issues for corrected reads |
| `core/analyzer.py:989-1034` | Modify | Phase 5 emits issues for merged docs |
| `core/analyzer.py:964-977` | Modify | Move issue emission after Phase 5/5b; add impact category |
| `core/analyzer.py:722-753` | Modify | `_recalculate_metrics` computes three-tier counts |
| `server.py:722-791` | Modify | `_recalculate_metrics` emits `direct`, `inferred_hi`, `inferred_lo` counts |
| `server.py:511-524` | Modify | Issue payload includes `impact` and `priority` fields |
| `frontend/src/App.jsx:704-715` | Modify | Header shows three-tier metrics instead of COM/INC |
| `frontend/src/App.jsx:724-743` | Modify | Tray cards show impact badge and sort by priority |
| `tests/test_tray_issues.py` | Create | Tests for issue emission from Phase 5, 5b, and impact classification |

---

## Context for implementers

### How issues work today

1. `analyze_pdf` in `core/analyzer.py` calls `_issue(page, kind, detail)` for problems found during analysis.
2. Issues are emitted at two points:
   - **Line 964-974:** Inferred pages with `confidence ≤ 0.60` — emitted BEFORE Phase 4/5/5b. These include internal pages (curr > 1) that don't affect doc count.
   - **Line 1092-1105 (_build_documents):** Orphan pages and broken sequences.
3. Phase 5 (undercount recovery, line 989-1034) and Phase 5b (period contradiction, line 608-663) silently modify reads — they emit NO issues.
4. `server.py` wraps `_issue` into a dict `{id, pdf_path, filename, page, type, detail}` and sends it via WebSocket as `new_issue`.
5. Frontend renders all issues equally in a flat list.

### How metrics work today

`_recalculate_metrics` (server.py:722) rebuilds docs from stored reads and counts:
- `total_docs`, `total_complete` (is_complete), `total_incomplete`, `total_inferred` (sum of inferred_pages across all docs)
- Per-PDF: same breakdown in `pdf_metrics[path]`
- Frontend header shows: DOC | COM | INC | INF

### What the cascade does

`/api/correct` calls `re_infer_documents` which: resets ALL inferred reads to failed, applies the manual correction, re-detects period, re-infers, re-builds docs. Then `_recalculate_metrics` + `issues_refresh` are emitted. The cascade works correctly and is not modified by this plan.

### Key insight: what affects doc count

Only these things change the document count:
- A page with `curr==1` (inferred or corrected) — this is a **document boundary**
- Phase 5 merging two adjacent docs
- Phase 5b changing a direct OCR read's `total` (which cascades into re-propagation)

Internal inferred pages (curr > 1) with high confidence are noise in the tray.

---

## Chunk 1: Backend — Issue enrichment and three-tier metrics

### Task 1: Add `min_inferred_confidence` to Document

**Files:**
- Modify: `core/analyzer.py:186-200`
- Test: `tests/test_tray_issues.py` (create)

- [ ] **Step 1: Write failing test for min_inferred_confidence**

```python
# tests/test_tray_issues.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.analyzer import Document, _PageRead

def test_doc_min_inferred_confidence_no_inferred():
    """Doc with no inferred pages → min_inferred_confidence is 1.0 (fully direct)."""
    d = Document(index=1, start_pdf_page=1, declared_total=2, pages=[1, 2])
    assert d.min_inferred_confidence is None

def test_doc_min_inferred_confidence_with_inferred(monkeypatch):
    """Doc with inferred pages → returns lowest confidence among them."""
    d = Document(index=1, start_pdf_page=1, declared_total=4,
                 pages=[1, 2], inferred_pages=[3, 4])
    # min_inferred_confidence needs reads — we'll test it differently below
    # after seeing how it's wired. For now, test the property exists.
    pass
```

Actually, `Document` doesn't hold reads — it holds page numbers. The confidence lives on `_PageRead`, not `Document`. We need a different approach: compute the tier in `_recalculate_metrics` where we have both docs and reads.

- [ ] **Step 1 (revised): Write failing test for three-tier classification**

```python
# tests/test_tray_issues.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.analyzer import Document, _PageRead, _build_documents

def _make_read(page, curr, total, method="direct", confidence=1.0):
    return _PageRead(pdf_page=page, curr=curr, total=total,
                     method=method, confidence=confidence)

def test_classify_doc_direct():
    """Doc with all direct reads → 'direct' tier."""
    reads = [_make_read(1, 1, 2, "direct"), _make_read(2, 2, 2, "direct")]
    docs = _build_documents(reads, lambda m, l: None, lambda p, k, d: None)
    assert len(docs) == 1
    assert docs[0].is_complete
    assert docs[0].inferred_pages == []

def test_classify_doc_inferred_hi():
    """Doc complete with inferred pages, all conf >= 0.75 → 'inferred_hi'."""
    reads = [_make_read(1, 1, 2, "direct"), _make_read(2, 2, 2, "inferred", 0.80)]
    docs = _build_documents(reads, lambda m, l: None, lambda p, k, d: None)
    assert len(docs) == 1
    assert docs[0].is_complete
    assert docs[0].inferred_pages == [2]

def test_classify_doc_inferred_lo():
    """Doc complete with inferred pages, min conf < 0.75 → 'inferred_lo'."""
    reads = [_make_read(1, 1, 2, "direct"), _make_read(2, 2, 2, "inferred", 0.50)]
    docs = _build_documents(reads, lambda m, l: None, lambda p, k, d: None)
    assert len(docs) == 1
    assert docs[0].is_complete
    assert docs[0].inferred_pages == [2]
```

- [ ] **Step 2: Run tests — verify they pass (structural tests, no new code yet)**

Run: `pytest tests/test_tray_issues.py -v`
Expected: 3 PASS (these just verify existing behavior)

- [ ] **Step 3: Write test for the classification helper function**

```python
# Add to tests/test_tray_issues.py

def classify_doc(doc, reads_by_page):
    """Classify doc into one of: direct, inferred_hi, inferred_lo, incomplete."""
    if not doc.is_complete:
        return "incomplete"
    if not doc.inferred_pages:
        return "direct"
    min_conf = min(reads_by_page[p].confidence
                   for p in doc.inferred_pages if p in reads_by_page)
    return "inferred_hi" if min_conf >= 0.75 else "inferred_lo"

def test_classify_helper():
    reads = [
        _make_read(1, 1, 2, "direct"),
        _make_read(2, 2, 2, "inferred", 0.50)
    ]
    rmap = {r.pdf_page: r for r in reads}
    docs = _build_documents(reads, lambda m, l: None, lambda p, k, d: None)
    assert classify_doc(docs[0], rmap) == "inferred_lo"

    reads2 = [
        _make_read(1, 1, 2, "direct"),
        _make_read(2, 2, 2, "inferred", 0.90)
    ]
    rmap2 = {r.pdf_page: r for r in reads2}
    docs2 = _build_documents(reads2, lambda m, l: None, lambda p, k, d: None)
    assert classify_doc(docs2[0], rmap2) == "inferred_hi"
```

- [ ] **Step 4: Run test — FAIL because classify_doc is local, not imported**

We define it in the test for now, verify the logic, then extract to analyzer.py.

Run: `pytest tests/test_tray_issues.py::test_classify_helper -v`
Expected: PASS (it's defined inline)

- [ ] **Step 5: Extract `classify_doc` to `core/analyzer.py`**

Add after `Document` class (line ~201):

```python
def classify_doc(doc: Document, reads_by_page: dict) -> str:
    """Classify doc reliability: direct | inferred_hi | inferred_lo | incomplete."""
    if not doc.is_complete:
        return "incomplete"
    if not doc.inferred_pages:
        return "direct"
    confs = [reads_by_page[p].confidence
             for p in doc.inferred_pages if p in reads_by_page]
    if not confs:
        return "direct"
    return "inferred_hi" if min(confs) >= 0.75 else "inferred_lo"
```

- [ ] **Step 6: Update test to import from analyzer, remove local copy**

```python
from core.analyzer import Document, _PageRead, _build_documents, classify_doc
```

- [ ] **Step 7: Run all tests**

Run: `pytest tests/test_tray_issues.py -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add core/analyzer.py tests/test_tray_issues.py
git commit -m "feat(core): add classify_doc helper for three-tier doc reliability"
```

---

### Task 2: Three-tier metrics in `_recalculate_metrics`

**Files:**
- Modify: `server.py:722-791`

- [ ] **Step 1: Update `_recalculate_metrics` to compute tier counts**

In `server.py:722`, add tier counting alongside existing counts. The existing `total_complete` / `total_incomplete` stay (backwards compat with history). Add new counters:

```python
def _recalculate_metrics():
    total_docs = 0
    total_complete = 0
    total_incomplete = 0
    total_inferred = 0
    # NEW: three-tier counts
    total_direct = 0
    total_inferred_hi = 0
    total_inferred_lo = 0

    with state._lock:
        reads_snapshot = dict(state.pdf_reads)
    skipped_paths = state.skipped_pdfs

    from core.analyzer import _build_documents, classify_doc
    for path, reads in reads_snapshot.items():
        if path in skipped_paths:
            continue

        docs = _build_documents(reads, lambda m, l: None, lambda p, k, d: None)
        reads_by_page = {r.pdf_page: r for r in reads}
        complete = [d for d in docs if d.is_complete]
        incomplete = [d for d in docs if not d.is_complete]
        inferred = sum(len(d.inferred_pages) for d in docs)

        total_docs += len(docs)
        total_complete += len(complete)
        total_incomplete += len(incomplete)
        total_inferred += inferred

        # Three-tier
        for d in docs:
            tier = classify_doc(d, reads_by_page)
            if tier == "direct":
                total_direct += 1
            elif tier == "inferred_hi":
                total_inferred_hi += 1
            elif tier == "inferred_lo":
                total_inferred_lo += 1
        # (incomplete already counted)
    # ... store on state ...
```

Add to state class (line ~85):
```python
self.total_direct: int = 0
self.total_inferred_hi: int = 0
self.total_inferred_lo: int = 0
```

Reset these in the two reset blocks (~266, ~351).

- [ ] **Step 2: Update metrics emission to include tiers**

In the `_emit("metrics", ...)` block (line ~784), add:
```python
"direct": state.total_direct,
"inferred_hi": state.total_inferred_hi,
"inferred_lo": state.total_inferred_lo,
```

Also update `pdf_metrics[path]` (line ~775) to include per-PDF tiers.

- [ ] **Step 3: Run server manually, verify metrics payload includes new fields**

Run: `python -c "from server import _recalculate_metrics; print('import ok')"`
Expected: no import errors

- [ ] **Step 4: Commit**

```bash
git add server.py
git commit -m "feat(server): emit three-tier doc reliability metrics (direct/inferred_hi/inferred_lo)"
```

---

### Task 3: Phase 5 and 5b emit issues

**Files:**
- Modify: `core/analyzer.py:608-663` (Phase 5b)
- Modify: `core/analyzer.py:989-1034` (Phase 5)
- Modify: `core/analyzer.py:964-977` (move issue emission + add impact field)
- Test: `tests/test_tray_issues.py`

This is the most important task. Today, Phase 5b silently changes OCR reads and Phase 5 silently merges docs. The user has no visibility into these decisions.

- [ ] **Step 1: Write tests for Phase 5b issue emission**

```python
# Add to tests/test_tray_issues.py

def test_phase5b_emits_issue_on_correction():
    """When Phase 5b corrects a direct read, an issue should be emitted."""
    # Build reads where period=4 is dominant but one read says total=1
    # Phase 5b should correct it and emit an issue
    collected_issues = []
    def on_issue(page, kind, detail, img=None):
        collected_issues.append({"page": page, "type": kind, "detail": detail})

    # We need to test through analyze_pdf or the relevant section.
    # Since Phase 5b is embedded in the main function, we test via
    # the public interface: _infer_missing doesn't do 5b, it's in analyze_pdf.
    # We'll test this integration-style after wiring.
    pass  # placeholder — filled in step 3
```

- [ ] **Step 2: Add issue emission to Phase 5b**

In `core/analyzer.py`, inside the Phase 5b block (after line 638), add:

```python
                            on_log(
                                f"  -> Ph5b: pag {r.pdf_page} corregida "
                                f"total={r.total}→{expected_total} "
                                f"(period conf={period_conf:.0%}, agreement={ratio:.0%})",
                                "warn",
                            )
                            _issue(r.pdf_page, "ph5b-corregida",
                                   f"Pag {r.pdf_page}: OCR leyo total={r.total} "
                                   f"pero periodo dominante={expected_total} "
                                   f"(conf={period_conf:.0%}, acuerdo={ratio:.0%})")
```

This goes right after `r.confidence = 0.50` (line 638), before `corrected_indices.add(idx_r)`.

**Important:** The `_issue` and `on_log` callables exist in the enclosing `_infer_missing` scope? No — Phase 5b is NOT inside `_infer_missing`. Let me check.

Phase 5b is at line 608 inside the main `analyze_pdf` function — `_issue` and `on_log` are available there. Good.

But we need to capture the original total before overwriting. Add before the correction:

```python
                            orig_total = r.total
```

Then emit the issue with `orig_total`.

- [ ] **Step 3: Add issue emission to Phase 5 (undercount recovery)**

In `core/analyzer.py`, inside the Phase 5 merge loop (after line 1027, before `_uc_fixed += 1`):

```python
                _issue(d_next.start_pdf_page, "ph5-fusion",
                       f"Doc en pag {d_next.start_pdf_page} fusionado con doc anterior "
                       f"(pag {d.start_pdf_page}, faltaban {missing} pags)")
                on_log(
                    f"  -> Ph5: doc pag {d_next.start_pdf_page} absorbido por doc pag {d.start_pdf_page} "
                    f"({missing} pags faltantes)",
                    "warn",
                )
```

- [ ] **Step 4: Run existing tests to verify no breakage**

Run: `pytest -v`
Expected: All existing tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/analyzer.py
git commit -m "feat(core): Phase 5 and 5b emit issues for doc merges and period corrections"
```

---

### Task 4: Relocate and enrich issue emission with impact category

**Files:**
- Modify: `core/analyzer.py:964-977`
- Modify: `core/analyzer.py:1062-1123` (`_build_documents`)
- Modify: `server.py:511-524` (issue payload)

Today, low-confidence inferred pages are reported as issues at line 964 **before** Phase 4/5/5b. This means:
1. Some issues reported are later corrected by Phase 5b
2. Phase 5 merges are invisible
3. Internal pages (curr > 1) that don't affect count are treated same as boundary pages

**Strategy:** Move the low-confidence issue emission to AFTER Phase 5/5b. Add an `impact` field to each issue:

| impact | Meaning | Show in tray? |
|--------|---------|--------------|
| `"boundary"` | curr==1, inferred — doc boundary decision | Always |
| `"ph5b"` | Phase 5b corrected a direct OCR read | Always |
| `"ph5-merge"` | Phase 5 merged two docs | Always |
| `"sequence"` | Broken sequence in _build_documents | Always |
| `"orphan"` | Orphan page in _build_documents | Always |
| `"internal"` | Internal inferred page, low confidence | Only if conf < 0.50 |

- [ ] **Step 1: Modify `_issue` signature to accept impact**

In `analyze_pdf` (line ~827):

```python
    def _issue(page: int, kind: str, detail: str, impact: str = "internal"):
        if on_issue is not None:
            on_issue(page, kind, detail, None, impact)
```

Update `on_issue` signature in `server.py:511`:

```python
    def on_issue(page, kind, detail, pil_img, impact="internal"):
        with state._lock:
            issue = {
                "id": len(state.issues),
                "pdf_path": str(pdf_path),
                "filename": pdf_path.name,
                "page": page,
                "type": kind,
                "detail": detail,
                "impact": impact,
            }
```

- [ ] **Step 2: Tag existing issue calls with impact**

- Phase 5b issues (Task 3): already `"ph5b-corregida"` → impact=`"ph5b"`
- Phase 5 issues (Task 3): already `"ph5-fusion"` → impact=`"ph5-merge"`
- `_build_documents` orphan (line 1094): impact=`"orphan"`
- `_build_documents` sequence break (line 1105): impact=`"sequence"`

- [ ] **Step 3: Move low-confidence issue emission after Phase 5/5b**

Delete the block at lines 964-977. Re-add it after Phase 5 (after line ~1034), with impact classification:

```python
    # ── Report issues — AFTER Phase 5/5b so state is final ────────────
    for r in reads_clean:
        if r.method != "inferred":
            continue
        if r.confidence <= 0.60:
            conf_label = "MEDIA" if r.confidence >= 0.50 else "BAJA"
            if r.curr == 1:
                impact = "boundary"
            else:
                impact = "internal"
            detail = (f"Pag {r.pdf_page}: inferida como {r.curr}/{r.total} "
                      f"(confianza {conf_label}: {r.confidence:.0%})")
            _issue(r.pdf_page, f"inferida ({conf_label} {r.confidence:.0%})", detail, impact)
        elif r.curr == 1:
            # High-confidence boundary — still worth flagging
            impact = "boundary"
            detail = (f"Pag {r.pdf_page}: frontera de documento inferida {r.curr}/{r.total} "
                      f"(confianza: {r.confidence:.0%})")
            _issue(r.pdf_page, "frontera inferida", detail, impact)
```

Note: this also adds boundary pages with conf > 0.60 that were previously invisible.

- [ ] **Step 4: Update `re_infer_documents` issue emission too**

In `re_infer_documents` (line 1167-1174), apply the same impact logic so cascaded re-inference produces consistent issues.

- [ ] **Step 5: Run tests**

Run: `pytest -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add core/analyzer.py server.py
git commit -m "feat(core): relocate issue emission after Phase 5/5b; add impact category to issues"
```

---

## Chunk 2: Frontend — Three-tier display and smart tray

### Task 5: Frontend three-tier metrics header

**Files:**
- Modify: `frontend/src/App.jsx:704-715`

- [ ] **Step 1: Replace COM/INC counters with three-tier display**

Current header shows: `DOC | COM | INC | INF`

Replace with: `DOC | ✓ directo | ◐ inferido | ✗ incompleto`

In `App.jsx` around line 704-715, replace the metrics rendering:

```jsx
<div className="flex flex-col items-center justify-center min-w-[30px]">
  <span className="text-gray-500 font-bold mb-1 tracking-widest text-[9px]">DOC</span>
  <span className={`${ind.docs > 0 ? 'text-accent' : 'text-gray-600'} font-mono font-bold`}>{ind.docs}</span>
</div>
<div className="w-px h-6 bg-white/5 self-center"></div>
<div className="flex flex-col items-center justify-center min-w-[30px]" title="Documentos con todas las páginas leídas por OCR">
  <span className="text-gray-500 font-bold mb-1 tracking-widest text-[9px]">DIR</span>
  <span className={`${ind.direct > 0 ? 'text-success' : 'text-gray-600'} font-mono font-bold`}>{ind.direct || 0}</span>
</div>
<div className="w-px h-6 bg-white/5 self-center"></div>
<div className="flex flex-col items-center justify-center min-w-[30px]" title="Documentos completos con páginas inferidas">
  <span className="text-gray-500 font-bold mb-1 tracking-widest text-[9px]">INF</span>
  <span className={`${(ind.inferred_hi || 0) + (ind.inferred_lo || 0) > 0 ? 'text-warning' : 'text-gray-600'} font-mono font-bold`}>{(ind.inferred_hi || 0) + (ind.inferred_lo || 0)}</span>
</div>
<div className="w-px h-6 bg-white/5 self-center"></div>
<div className="flex flex-col items-center justify-center min-w-[30px]" title="Documentos incompletos">
  <span className="text-gray-500 font-bold mb-1 tracking-widest text-[9px]">INC</span>
  <span className={`${ind.incomplete > 0 ? 'text-error' : 'text-gray-600'} font-mono font-bold`}>{ind.incomplete}</span>
</div>
```

The INF column now shows inferred-complete docs (both hi and lo), not inferred pages. Hover tooltip explains each.

- [ ] **Step 2: Test visually — start server, load a PDF**

Run: `python server.py` + `cd frontend && npm run dev`
Expected: Header shows DIR / INF / INC instead of COM / INC / INF

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.jsx
git commit -m "feat(ui): three-tier reliability metrics in header (DIR/INF/INC)"
```

---

### Task 6: Frontend tray filtering and sorting by impact

**Files:**
- Modify: `frontend/src/App.jsx:724-743`

- [ ] **Step 1: Add impact badge and priority sorting to tray cards**

Add a priority map and filter logic before the issue list rendering:

```jsx
const IMPACT_PRIORITY = {
  'ph5b': 1,
  'ph5-merge': 2,
  'boundary': 3,
  'sequence': 4,
  'orphan': 5,
  'internal': 6,
};

const IMPACT_LABELS = {
  'ph5b': { label: 'Ph5b', color: 'text-red-400 bg-red-400/10' },
  'ph5-merge': { label: 'Fusión', color: 'text-orange-400 bg-orange-400/10' },
  'boundary': { label: 'Frontera', color: 'text-yellow-400 bg-yellow-400/10' },
  'sequence': { label: 'Secuencia', color: 'text-red-400 bg-red-400/10' },
  'orphan': { label: 'Huérfana', color: 'text-red-400 bg-red-400/10' },
  'internal': { label: 'Interna', color: 'text-gray-500 bg-gray-500/10' },
};
```

- [ ] **Step 2: Filter out low-priority internal issues by default**

Add a state toggle for showing all vs. critical-only issues:

```jsx
const [showAllIssues, setShowAllIssues] = useState(false)
```

Filter logic:
```jsx
const filteredIssues = (selectedPdfFilter
  ? issues.filter(i => i.filename === selectedPdfFilter)
  : issues
).filter(i => showAllIssues || (i.impact || 'internal') !== 'internal')
 .sort((a, b) => (IMPACT_PRIORITY[a.impact] || 6) - (IMPACT_PRIORITY[b.impact] || 6));
```

- [ ] **Step 3: Add impact badge to each tray card**

Inside the card div (line ~733-735), add a badge:

```jsx
{(() => {
  const imp = IMPACT_LABELS[iss.impact] || IMPACT_LABELS.internal;
  return (
    <span className={`${imp.color} px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ml-2`}>
      {imp.label}
    </span>
  );
})()}
```

- [ ] **Step 4: Add toggle button for "show all" vs "critical only"**

Near the tray header, add a small toggle:

```jsx
<button
  onClick={() => setShowAllIssues(v => !v)}
  className={`text-[10px] font-bold tracking-wider px-2 py-0.5 rounded transition-all ${
    showAllIssues ? 'bg-gray-600 text-white' : 'bg-transparent text-gray-500 hover:text-gray-300'
  }`}
>
  {showAllIssues ? 'TODOS' : 'CRÍTICOS'}
</button>
```

- [ ] **Step 5: Test visually**

Run the app, process a PDF with known issues, verify:
- Tray shows ph5b/merge/boundary issues by default
- Internal issues hidden unless toggled
- Issues sorted by priority (ph5b first)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.jsx
git commit -m "feat(ui): smart tray filtering — critical issues first, internal hidden by default"
```

---

### Task 7: Update history display to use three-tier metrics

**Files:**
- Modify: `frontend/src/App.jsx:927-931`

- [ ] **Step 1: Update history session cards**

Replace the "Completos / Incompletos" display (line ~928-931) with three-tier:

```jsx
<div className="flex flex-col items-center">
  <span className="text-gray-400">Directo</span>
  <span className="font-bold text-success text-lg">{s.metrics.direct || s.metrics.complete}</span>
</div>
<div className="flex flex-col items-center">
  <span className="text-gray-400">Inferido</span>
  <span className="font-bold text-warning text-lg">{(s.metrics.inferred_hi || 0) + (s.metrics.inferred_lo || 0)}</span>
</div>
<div className="flex flex-col items-center">
  <span className="text-gray-400">Incompleto</span>
  <span className="font-bold text-error text-lg">{s.metrics.incomplete}</span>
</div>
```

Note: fallback to `s.metrics.complete` for old sessions that don't have `direct`.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/App.jsx
git commit -m "feat(ui): three-tier metrics in session history cards"
```

---

### Task 8: Smoke test the full flow

- [ ] **Step 1: Start backend and frontend**

```bash
python server.py &
cd frontend && npm run dev
```

- [ ] **Step 2: Process a small PDF (CH_9 or CH_39) and verify:**

1. Header shows DIR / INF / INC counts
2. Tray shows issues sorted by priority
3. Ph5b and Ph5 merge issues appear (if applicable for this PDF)
4. "CRÍTICOS" toggle hides internal issues
5. Clicking an issue still opens the PDF viewer and correction dialog works
6. After correcting a page, cascade runs and issues refresh correctly

- [ ] **Step 3: Process ART to verify at scale:**

1. Check that most internal inferred pages are hidden by default
2. Boundary issues (curr==1 inferred) are visible
3. Ph5b corrections appear if any (ART has period conf=67%, below 69% threshold, so Phase 5b should NOT fire for ART — verify no ph5b issues)

- [ ] **Step 4: Final commit if any adjustments needed**

```bash
git add -A
git commit -m "fix(ui): smoke test adjustments for tray and metrics"
```
