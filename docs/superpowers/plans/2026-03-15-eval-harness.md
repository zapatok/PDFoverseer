# Eval Harness Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline parameter sweep harness that autonomously searches for optimal tuning of the 5-phase PDF inference engine and produces a ranked report for human review.

**Architecture:** `eval/inference.py` is a self-contained parameterized copy of the full inference pipeline (phases 1–5 + undercount recovery). `eval/sweep.py` runs 3 passes (LHS sample → fine grid → beam search) over ~500k param combos, testing each against 13 fixtures (7 real + 6 synthetic) and scoring with 6 metrics. `eval/report.py` reads the JSON result and prints a ranked table.

**Tech Stack:** Python 3.11+, stdlib only (`json`, `collections`, `itertools`, `random`, `datetime`). No fitz/tesseract in the sweep itself. fitz + core.analyzer used only in `eval/extract_fixtures.py` (one-time extraction).

**Spec:** `docs/superpowers/specs/2026-03-15-eval-harness-design.md`

---

## Chunk 1: Directory Setup + Real Fixture Extraction

### Task 1: Create eval/ directory structure

**Files:**
- Create: `eval/__init__.py`
- Create: `eval/results/.gitkeep`
- Modify: `.gitignore`

- [ ] **Step 1: Create directories and init files**

```bash
mkdir -p eval/fixtures/real eval/fixtures/synthetic eval/results
touch eval/__init__.py eval/results/.gitkeep
```

- [ ] **Step 2: Add results/ to .gitignore**

Append to `.gitignore`:
```
eval/results/
```

- [ ] **Step 3: Commit**

```bash
git add eval/ .gitignore
git commit -m "feat(eval): scaffold eval/ directory structure"
```

---

### Task 2: Write eval/extract_fixtures.py

**Files:**
- Create: `eval/extract_fixtures.py`

This script imports private OCR functions from `core/analyzer.py` to capture `reads_clean` **before inference** for each of the 7 real PDFs. Run once; output goes to `eval/fixtures/real/*.json`.

- [ ] **Step 1: Write the extraction script**

```python
# eval/extract_fixtures.py
"""
One-time extraction: runs OCR on each real PDF and serializes reads_clean
(pre-inference _PageRead list) to eval/fixtures/real/<name>.json.

Usage:
    cd a:/PROJECTS/PDFoverseer
    python eval/extract_fixtures.py

Requires: fitz, tesseract, core/analyzer.py imports.
PDFs must exist on disk. Paths are hardcoded below — update if needed.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

# Add project root to sys.path so core.analyzer is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import fitz
from core.analyzer import (
    _render_clip,
    _tess_ocr,
    _parse,
    _PageRead,
    DPI,
)

# ── Configure: map fixture name → PDF path ──────────────────────────────────
PDF_PATHS: dict[str, Path] = {
    "ART":   Path("data/pdfs/ART.pdf"),        # update paths as needed
    "CH_9":  Path("data/pdfs/CH_9docs.pdf"),
    "CH_39": Path("data/pdfs/CH_39docs.pdf"),
    "CH_51": Path("data/pdfs/CH_51docs.pdf"),
    "CH_74": Path("data/pdfs/CH_74docs.pdf"),
    "HLL":   Path("data/pdfs/HLL.pdf"),
    "INS_31":Path("data/pdfs/INS_31docs.pdf"),
}

OUT_DIR = Path("eval/fixtures/real")


def _scan_pdf(pdf_path: Path) -> list[dict]:
    """OCR each page, return list of _PageRead dicts (pre-inference)."""
    reads = []
    doc = fitz.open(str(pdf_path))
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        try:
            img = _render_clip(page, dpi=DPI)
            import cv2, numpy as np
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            text = _tess_ocr(gray)
            curr, total = _parse(text)
            method = "H" if curr is not None else "failed"
            confidence = 0.95 if curr is not None else 0.0
        except Exception:
            curr, total, method, confidence = None, None, "failed", 0.0
        reads.append({
            "pdf_page": page_num,
            "curr": curr,
            "total": total,
            "method": method,
            "confidence": confidence,
        })
    doc.close()
    return reads


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, path in PDF_PATHS.items():
        if not path.exists():
            print(f"SKIP {name}: {path} not found")
            continue
        print(f"Scanning {name} ({path.name})...", end=" ", flush=True)
        reads = _scan_pdf(path)
        out = OUT_DIR / f"{name}.json"
        out.write_text(json.dumps({"name": name, "source": "real", "reads": reads}, indent=2))
        print(f"done — {len(reads)} pages → {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Update PDF_PATHS to match actual file locations**

Check where the 7 PDFs live on disk:
```bash
find . -name "*.pdf" | grep -v __pycache__ | head -20
```
Update the `PDF_PATHS` dict in `extract_fixtures.py` to match actual paths.

- [ ] **Step 3: Run extraction**

```bash
cd a:/PROJECTS/PDFoverseer
python eval/extract_fixtures.py
```

Expected output (one line per PDF):
```
Scanning ART (ART.pdf)... done — 347 pages → eval/fixtures/real/ART.json
Scanning CH_9 (CH_9docs.pdf)... done — 9 pages → eval/fixtures/real/CH_9.json
...
```

If any PDF is not found, update the path and retry.

- [ ] **Step 4: Sanity-check one fixture**

```bash
python -c "
import json
d = json.load(open('eval/fixtures/real/CH_9.json'))
print('pages:', len(d['reads']))
print('first read:', d['reads'][0])
print('failed count:', sum(1 for r in d['reads'] if r['method'] == 'failed'))
"
```

Expected: `pages: 9`, `first read` shows `curr/total` values matching what was seen in the AI log.

- [ ] **Step 5: Commit**

```bash
git add eval/extract_fixtures.py eval/fixtures/real/
git commit -m "feat(eval): extraction script + real fixture JSON files"
```

---

### Task 3: Write eval/ground_truth.json

**Files:**
- Create: `eval/ground_truth.json`

Ground truth values come from the validated `[UI:]` log lines for each real PDF. The `INF:` value in the `[UI:]` line = `inferred_count`. `DOC:` = `doc_count`. `COM:` = `complete_count`.

- [ ] **Step 1: Write ground_truth.json**

Fill in exact values from the `[UI:]` AI log output. Known values from session:
- CH_9:  DOC:9  COM:8  INC:1  INF:0
- CH_39: DOC:40 COM:37 INC:3  INF:2

For the other 5 PDFs, scan them via the server and read the `[UI:]` lines, then fill in.

```json
{
  "ART":   {"doc_count": 674, "complete_count": 648, "inferred_count": 0},
  "CH_9":  {"doc_count": 9,   "complete_count": 8,   "inferred_count": 0},
  "CH_39": {"doc_count": 40,  "complete_count": 37,  "inferred_count": 2},
  "CH_51": {"doc_count": 0,   "complete_count": 0,   "inferred_count": 0},
  "CH_74": {"doc_count": 0,   "complete_count": 0,   "inferred_count": 0},
  "HLL":   {"doc_count": 0,   "complete_count": 0,   "inferred_count": 0},
  "INS_31":{"doc_count": 4,   "complete_count": 3,   "inferred_count": 2},
  "ins31_gap":       {"doc_count": 2, "complete_count": 1, "inferred_count": 1},
  "undercount_chain":{"doc_count": 1, "complete_count": 1, "inferred_count": 1},
  "ambiguous_start": {"doc_count": 3, "complete_count": 3, "inferred_count": 2},
  "noisy_period":    {"doc_count": 2, "complete_count": 1, "inferred_count": 2},
  "seq_break":       {"doc_count": 1, "complete_count": 1, "inferred_count": 1},
  "ds_conflict":     {"doc_count": 1, "complete_count": 0, "inferred_count": 3}
}
```

**IMPORTANT:** Replace the `0` placeholder values for ART, CH_51, CH_74, HLL with actual `[UI:]` values before running the sweep. These are stubs — the baseline validation (Task 10) will catch any wrong values.

- [ ] **Step 2: Commit**

```bash
git add eval/ground_truth.json
git commit -m "feat(eval): ground truth stubs (real values from UI log)"
```

---

## Chunk 2: inference.py — Parameterized Engine Copy

### Task 4: Write eval/inference.py

**Files:**
- Create: `eval/inference.py`
- Create: `eval/tests/test_inference.py`

`inference.py` is a self-contained copy of the full pipeline. It imports **nothing** from `core/analyzer.py` — it redefines the necessary dataclasses locally and accepts a `params: dict` everywhere hardcoded constants appear.

- [ ] **Step 1: Write the failing tests first**

```python
# eval/tests/test_inference.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from eval.inference import run_pipeline, PageRead

PROD_PARAMS = {
    "fwd_conf": 0.95, "new_doc_base": 0.60, "new_doc_hom_mul": 0.30,
    "back_conf": 0.90, "xval_cap": 0.50,
    "fallback_base": 0.40, "fallback_hom_base": 0.30, "fallback_hom_mul": 0.20,
    "ds_boost_max": 0.25,
    "window": 5, "hom_threshold": 0.85,
}


def make_reads(specs):
    """specs: list of (pdf_page, curr, total, method, confidence)"""
    return [PageRead(pdf_page=p, curr=c, total=t, method=m, confidence=cf)
            for p, c, t, m, cf in specs]


def test_simple_two_doc():
    """Two 2-page docs, no inference needed."""
    reads = make_reads([
        (0, 1, 2, "H", 0.95), (1, 2, 2, "H", 0.92),
        (2, 1, 2, "H", 0.91), (3, 2, 2, "H", 0.90),
    ])
    docs = run_pipeline(reads, PROD_PARAMS)
    assert len(docs) == 2
    assert all(d.is_complete for d in docs)


def test_infer_missing_middle():
    """Page 1 is failed; should be inferred from neighbors."""
    reads = make_reads([
        (0, 1, 3, "H", 0.95),
        (1, None, None, "failed", 0.0),
        (2, 3, 3, "H", 0.90),
    ])
    docs = run_pipeline(reads, PROD_PARAMS)
    assert len(docs) == 1
    assert docs[0].declared_total == 3
    assert docs[0].found_total == 3


def test_metrics_complete_count():
    """Sanity: complete_count via is_complete."""
    reads = make_reads([
        (0, 1, 2, "H", 0.95), (1, 2, 2, "H", 0.92),   # complete
        (2, 1, 3, "H", 0.90),                            # incomplete (only 1 of 3)
    ])
    docs = run_pipeline(reads, PROD_PARAMS)
    complete = sum(1 for d in docs if d.is_complete)
    assert complete == 1


def test_inferred_count():
    """inferred_count = pages assigned by inference, counted once."""
    reads = make_reads([
        (0, 1, 2, "H", 0.95),
        (1, None, None, "failed", 0.0),
    ])
    docs = run_pipeline(reads, PROD_PARAMS)
    inferred = sum(len(d.inferred_pages) for d in docs)
    assert inferred == 1
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd a:/PROJECTS/PDFoverseer
python -m pytest eval/tests/test_inference.py -v 2>&1 | head -30
```

Expected: `ImportError` or `ModuleNotFoundError` — `eval/inference.py` doesn't exist yet.

- [ ] **Step 3: Write eval/inference.py**

```python
# eval/inference.py
"""
Parameterized copy of the full inference pipeline from core/analyzer.py.
Does NOT import from core/ — self-contained for sweep isolation.

Public API:
    run_pipeline(reads: list[PageRead], params: dict) -> list[Document]

params keys (all required):
    fwd_conf, new_doc_base, new_doc_hom_mul  — Phase 1
    back_conf                                 — Phase 2
    xval_cap                                  — Phase 3
    fallback_base, fallback_hom_base, fallback_hom_mul  — Phase 4
    ds_boost_max                              — Phase 5 (ds_support_min omitted: period evidence not ported)
    window, hom_threshold                     — Global
"""
from __future__ import annotations
import copy
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class PageRead:
    pdf_page:   int
    curr:       int | None
    total:      int | None
    method:     str
    confidence: float


@dataclass
class Document:
    index:          int
    start_pdf_page: int
    declared_total: int
    pages:          list[int] = field(default_factory=list)
    inferred_pages: list[int] = field(default_factory=list)
    sequence_ok:    bool      = True

    @property
    def found_total(self) -> int:
        return len(self.pages) + len(self.inferred_pages)

    @property
    def is_complete(self) -> bool:
        return self.sequence_ok and self.found_total == self.declared_total


def run_pipeline(reads: list[PageRead], params: dict) -> list[Document]:
    """Full pipeline: deepcopy → infer → build docs → undercount recovery."""
    reads = copy.deepcopy(reads)
    _infer(reads, params)
    docs = _build_documents(reads)
    docs = _undercount_recovery(reads, docs)
    return docs


# ── Phase 1–5 Inference ──────────────────────────────────────────────────────

def _infer(reads: list[PageRead], params: dict) -> None:
    """Mutates reads in-place. Mirrors _infer_missing in core/analyzer.py."""
    n = len(reads)
    if n == 0:
        return

    fwd_conf        = params["fwd_conf"]
    new_doc_base    = params["new_doc_base"]
    new_doc_hom_mul = params["new_doc_hom_mul"]
    back_conf       = params["back_conf"]
    xval_cap        = params["xval_cap"]
    fallback_base    = params["fallback_base"]
    fallback_hom_base= params["fallback_hom_base"]
    fallback_hom_mul = params["fallback_hom_mul"]
    # ds_support_min omitted: period evidence not ported — support stays 0.0 always.
    # D-S phase only fires via neighbors_agree == 2.
    ds_boost_max    = params["ds_boost_max"]
    window          = params["window"]
    hom_threshold   = params["hom_threshold"]

    total_counts = Counter(r.total for r in reads if r.total is not None)
    total_sum = sum(total_counts.values()) or 1
    prior: dict[int, float] = {k: v / total_sum for k, v in total_counts.items()}
    if not prior:
        prior = {2: 0.85, 3: 0.10, 1: 0.05}
    best_total = max(prior, key=prior.get)

    def _local_total(idx: int) -> tuple[int, float]:
        lo, hi = max(0, idx - window), min(n, idx + window + 1)
        local = [reads[j].total for j in range(lo, hi)
                 if reads[j].total is not None
                 and reads[j].method not in ("failed", "inferred")]
        if not local:
            return best_total, 0.0
        tc = Counter(local)
        mode_val, mode_freq = tc.most_common(1)[0]
        hom = mode_freq / len(local)
        if hom >= hom_threshold:
            return mode_val, hom
        return best_total, hom

    # ── Phase 1: Forward propagation ────────────────────────────────
    for i in range(n):
        r = reads[i]
        if r.method != "failed":
            continue
        if i > 0:
            prev = reads[i - 1]
            if prev.curr is not None and prev.total is not None:
                if prev.curr < prev.total:
                    r.curr, r.total = prev.curr + 1, prev.total
                    r.method, r.confidence = "inferred", fwd_conf
                elif prev.curr == prev.total:
                    lt, hom = _local_total(i)
                    r.curr, r.total = 1, lt
                    r.method = "inferred"
                    r.confidence = new_doc_base + hom * new_doc_hom_mul

    # ── Phase 2: Backward propagation ───────────────────────────────
    for i in range(n - 2, -1, -1):
        r = reads[i]
        if r.method != "failed":
            continue
        if i < n - 1:
            nxt = reads[i + 1]
            if nxt.curr is not None and nxt.total is not None:
                if nxt.curr > 1:
                    r.curr, r.total = nxt.curr - 1, nxt.total
                    r.method, r.confidence = "inferred", back_conf
                elif nxt.curr == 1 and i > 0:
                    prev = reads[i - 1]
                    if (prev.curr is not None and prev.total is not None
                            and prev.curr < prev.total):
                        r.curr, r.total = prev.curr + 1, prev.total
                        r.method, r.confidence = "inferred", back_conf

    # ── Phase 3: Cross-validation ────────────────────────────────────
    for i in range(n):
        r = reads[i]
        if r.method != "inferred":
            continue
        consistent = True
        if i > 0:
            prev = reads[i - 1]
            if prev.curr is not None and prev.total is not None:
                if not ((prev.total == r.total and prev.curr == r.curr - 1) or
                        (prev.curr == prev.total and r.curr == 1)):
                    consistent = False
        if i < n - 1:
            nxt = reads[i + 1]
            if nxt.curr is not None and nxt.total is not None:
                if not ((nxt.total == r.total and nxt.curr == r.curr + 1) or
                        (r.curr == r.total and nxt.curr == 1)):
                    consistent = False
        if not consistent:
            r.confidence = min(r.confidence, xval_cap)

    # ── Phase 4: Fallback ────────────────────────────────────────────
    for i, r in enumerate(reads):
        if r.method == "failed":
            lt, hom = _local_total(i)
            r.curr, r.total = 1, lt
            r.method = "inferred"
            r.confidence = (fallback_base if hom < hom_threshold
                            else fallback_hom_base + hom * fallback_hom_mul)
            # Production: fallback_base=0.40 (low-hom), fallback_hom_base=0.30 + hom*0.20 (high-hom)
            # Both branches are independently tunable.

    # ── Phase 5: D-S post-validation ────────────────────────────────
    for i in range(n):
        r = reads[i]
        if r.method != "inferred" or r.confidence > 0.60:
            continue

        support = 0.0
        neighbors_agree = 0

        if i > 0:
            prev = reads[i - 1]
            if prev.curr is not None and prev.total is not None:
                if ((prev.total == r.total and prev.curr == r.curr - 1) or
                        (prev.curr == prev.total and r.curr == 1)):
                    neighbors_agree += 1
        if i < n - 1:
            nxt = reads[i + 1]
            if nxt.curr is not None and nxt.total is not None:
                if ((nxt.total == r.total and nxt.curr == r.curr + 1) or
                        (r.curr == r.total and nxt.curr == 1)):
                    neighbors_agree += 1

        prior_support = prior.get(r.total, 0.0)

        # Period evidence (support) not ported — period detection requires fitz/OCR context.
        # D-S fires only via neighbors_agree == 2 (both-side neighbor agreement).
        if neighbors_agree == 2:
            boost = min(neighbors_agree * 0.08 + prior_support * 0.05, ds_boost_max)
            r.confidence = min(r.confidence + boost, 0.75)


# ── Build Documents ──────────────────────────────────────────────────────────

def _build_documents(reads: list[PageRead]) -> list[Document]:
    """Groups reads into Document objects. No logging callbacks."""
    documents: list[Document] = []
    current: Document | None  = None

    for r in reads:
        if r.method == "excluded":
            continue
        curr, tot, pdf_page = r.curr, r.total, r.pdf_page
        is_inferred = r.method == "inferred"

        if curr == 1:
            if current is not None:
                documents.append(current)
            current = Document(
                index          = len(documents) + 1,
                start_pdf_page = pdf_page,
                declared_total = tot,
                pages          = [] if is_inferred else [pdf_page],
                inferred_pages = [pdf_page] if is_inferred else [],
            )
        elif curr is not None:
            if current is not None:
                if is_inferred:
                    current.inferred_pages.append(pdf_page)
                elif curr == current.found_total + 1 and tot == current.declared_total:
                    current.pages.append(pdf_page)
                else:
                    current.sequence_ok = False
                    current.pages.append(pdf_page)

    if current is not None:
        documents.append(current)
    return documents


# ── Undercount Recovery ──────────────────────────────────────────────────────

def _undercount_recovery(reads: list[PageRead], docs: list[Document]) -> list[Document]:
    """Mirrors the undercount recovery loop in analyze_pdf."""
    reads_by_page = {r.pdf_page: r for r in reads}
    fixed = 0
    for di in range(len(docs) - 1):
        d, d_next = docs[di], docs[di + 1]
        missing = d.declared_total - d.found_total
        if missing <= 0 or d.declared_total <= 1:
            continue
        if (d_next.found_total <= missing
                and d_next.declared_total == d.declared_total):
            next_pages = d_next.pages + d_next.inferred_pages
            for pp in next_pages:
                r = reads_by_page.get(pp)
                if r and r.method == "inferred":
                    r.curr = d.found_total + 1
                    r.total = d.declared_total
                    r.confidence = min(r.confidence + 0.10, 0.85)
            d.inferred_pages.extend(next_pages)
            d_next.pages.clear()
            d_next.inferred_pages.clear()
            d_next.declared_total = 0
            fixed += 1
    if fixed:
        docs = [d for d in docs if d.declared_total > 0]
        for i, d in enumerate(docs):
            d.index = i + 1
    return docs
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd a:/PROJECTS/PDFoverseer
python -m pytest eval/tests/test_inference.py -v
```

Expected:
```
PASSED test_simple_two_doc
PASSED test_infer_missing_middle
PASSED test_metrics_complete_count
PASSED test_inferred_count
4 passed in 0.xXs
```

If any test fails, compare the failing assertion against the logic in `core/analyzer.py` at the corresponding phase and fix the discrepancy in `inference.py`.

- [ ] **Step 5: Commit**

```bash
git add eval/inference.py eval/tests/
git commit -m "feat(eval): parameterized inference engine + tests"
```

---

## Chunk 3: params.py + Synthetic Fixtures

### Task 5: Write eval/params.py

**Files:**
- Create: `eval/params.py`

- [ ] **Step 1: Write params.py**

```python
# eval/params.py
"""
Parameter search space for the inference engine sweep.
Each key maps to a list of discrete candidate values.
PRODUCTION_PARAMS mirrors the hardcoded constants in core/analyzer.py.
"""

PARAM_SPACE: dict[str, list] = {
    # Phase 1 — Forward propagation
    "fwd_conf":         [0.90, 0.93, 0.95, 0.97],
    "new_doc_base":     [0.50, 0.60, 0.70],
    "new_doc_hom_mul":  [0.20, 0.30, 0.40],
    # Phase 2 — Backward propagation
    "back_conf":        [0.85, 0.90, 0.95],
    # Phase 3 — Cross-validation
    "xval_cap":         [0.40, 0.50, 0.60],
    # Phase 4 — Fallback
    "fallback_base":     [0.30, 0.40, 0.50],    # low-hom confidence
    "fallback_hom_base": [0.20, 0.30, 0.40],    # high-hom formula intercept (was hardcoded 0.30)
    "fallback_hom_mul":  [0.15, 0.20, 0.25],    # high-hom multiplier
    # Phase 5 — D-S post-validation (period evidence not ported; support=0 always)
    # ds_support_min omitted — inert without period detection
    "ds_boost_max":     [0.20, 0.25, 0.30],
    # Global
    "window":           [3, 5, 7],
    "hom_threshold":    [0.80, 0.85, 0.90],
}

# Current production values (hardcoded constants in analyzer.py)
PRODUCTION_PARAMS: dict[str, float | int] = {
    "fwd_conf":         0.95,
    "new_doc_base":     0.60,
    "new_doc_hom_mul":  0.30,
    "back_conf":        0.90,
    "xval_cap":          0.50,
    "fallback_base":     0.40,
    "fallback_hom_base": 0.30,
    "fallback_hom_mul":  0.20,
    "ds_boost_max":      0.25,
    "window":           5,
    "hom_threshold":    0.85,
}
```

- [ ] **Step 2: Verify PRODUCTION_PARAMS values against analyzer.py**

Open `core/analyzer.py` and confirm each hardcoded constant matches. Check:
- Ph1 fwd: `r.confidence = 0.95` ✓
- Ph1 new-doc: `0.60 + hom * 0.30` ✓
- Ph2 back: `r.confidence = 0.90` ✓
- Ph3 cap: `min(r.confidence, 0.50)` ✓
- Ph4: `0.40 if hom < 0.85 else 0.30 + hom * 0.20` → `fallback_base=0.40`, `fallback_hom_base=0.30`, `fallback_hom_mul=0.20` ✓
- Ph5: period evidence not ported; D-S fires only via `neighbors_agree==2`; `ds_boost_max=0.25` ✓
- `window=5`, `hom >= 0.85` ✓

- [ ] **Step 3: Commit**

```bash
git add eval/params.py
git commit -m "feat(eval): parameter space + production baseline values"
```

---

### Task 6: Write synthetic fixtures

**Files:**
- Create: `eval/fixtures/synthetic/ins31_gap.json`
- Create: `eval/fixtures/synthetic/undercount_chain.json`
- Create: `eval/fixtures/synthetic/ambiguous_start.json`
- Create: `eval/fixtures/synthetic/noisy_period.json`
- Create: `eval/fixtures/synthetic/seq_break.json`
- Create: `eval/fixtures/synthetic/ds_conflict.json`

Each fixture is hand-crafted JSON with known ground truth. After writing them, verify ground truth values in `eval/ground_truth.json` match.

- [ ] **Step 1: Write ins31_gap.json**

Pattern: INS_31 signature — penultimate page reads as `1/2`, last page is undetected.
Ground truth: 2 docs, 1 complete, 1 inferred page.

```json
{
  "name": "ins31_gap",
  "source": "synthetic",
  "reads": [
    {"pdf_page": 0, "curr": 1, "total": 5, "method": "H", "confidence": 0.95},
    {"pdf_page": 1, "curr": 2, "total": 5, "method": "H", "confidence": 0.93},
    {"pdf_page": 2, "curr": 3, "total": 5, "method": "H", "confidence": 0.92},
    {"pdf_page": 3, "curr": 4, "total": 5, "method": "H", "confidence": 0.91},
    {"pdf_page": 4, "curr": 5, "total": 5, "method": "H", "confidence": 0.90},
    {"pdf_page": 5, "curr": 1, "total": 2, "method": "H", "confidence": 0.88},
    {"pdf_page": 6, "curr": null, "total": null, "method": "failed", "confidence": 0.0}
  ]
}
```

- [ ] **Step 2: Write undercount_chain.json**

Pattern: A 5-page doc where page 2 (index 2, `3/5`) is missing. Phase 1 forward-propagates it from the previous `2/5` read. After inference the doc is complete (5/5 found). Tests that undercount recovery does not corrupt an already-complete doc.
Ground truth: 1 doc, 1 complete, 1 inferred page.

```json
{
  "name": "undercount_chain",
  "source": "synthetic",
  "reads": [
    {"pdf_page": 0, "curr": 1, "total": 5, "method": "H", "confidence": 0.95},
    {"pdf_page": 1, "curr": 2, "total": 5, "method": "H", "confidence": 0.93},
    {"pdf_page": 2, "curr": null, "total": null, "method": "failed", "confidence": 0.0},
    {"pdf_page": 3, "curr": 4, "total": 5, "method": "H", "confidence": 0.91},
    {"pdf_page": 4, "curr": 5, "total": 5, "method": "H", "confidence": 0.90}
  ]
}
```

Ground truth for `undercount_chain` is `{"doc_count": 1, "complete_count": 1, "inferred_count": 1}` — already set correctly in `ground_truth.json` stub above.

- [ ] **Step 3: Write ambiguous_start.json**

Pattern: 3 docs. Doc 1 starts cleanly. Doc 2's first 2 pages are failed — engine must infer they are `1/3` and `2/3` from the following `3/3`. Doc 3 starts cleanly.
Ground truth: 3 docs, 3 complete, 2 inferred pages.

```json
{
  "name": "ambiguous_start",
  "source": "synthetic",
  "reads": [
    {"pdf_page": 0, "curr": 1, "total": 2, "method": "H", "confidence": 0.95},
    {"pdf_page": 1, "curr": 2, "total": 2, "method": "H", "confidence": 0.93},
    {"pdf_page": 2, "curr": null, "total": null, "method": "failed", "confidence": 0.0},
    {"pdf_page": 3, "curr": null, "total": null, "method": "failed", "confidence": 0.0},
    {"pdf_page": 4, "curr": 3, "total": 3, "method": "H", "confidence": 0.92},
    {"pdf_page": 5, "curr": 1, "total": 4, "method": "H", "confidence": 0.91},
    {"pdf_page": 6, "curr": 2, "total": 4, "method": "H", "confidence": 0.90},
    {"pdf_page": 7, "curr": 3, "total": 4, "method": "H", "confidence": 0.89},
    {"pdf_page": 8, "curr": 4, "total": 4, "method": "H", "confidence": 0.88}
  ]
}
```

Ground truth: `{"doc_count": 3, "complete_count": 3, "inferred_count": 2}`.
Trace: Ph2 back-fills page 3 as `2/3` (from `3/3` next), then page 2 as `1/3`. `_build_documents` starts Doc 2 at page 2 (`curr=1`, inferred) → page 3 → `inferred_pages` → page 4 (`3/3`, H, confirmed) passes sequence check → all 3 docs complete.

- [ ] **Step 4: Write noisy_period.json**

Pattern: One doc where the total oscillates between 5 and 6 (mixed reads). The region is inhomogeneous. Tests `hom_threshold` sensitivity — a lower threshold might pick a wrong local_total.
Ground truth: 1 doc with declared_total from the majority read, 0 inferred pages.

```json
{
  "name": "noisy_period",
  "source": "synthetic",
  "reads": [
    {"pdf_page": 0, "curr": 1, "total": 5, "method": "H", "confidence": 0.95},
    {"pdf_page": 1, "curr": 2, "total": 6, "method": "H", "confidence": 0.93},
    {"pdf_page": 2, "curr": 3, "total": 5, "method": "H", "confidence": 0.92},
    {"pdf_page": 3, "curr": 4, "total": 5, "method": "H", "confidence": 0.91},
    {"pdf_page": 4, "curr": 5, "total": 5, "method": "H", "confidence": 0.90}
  ]
}
```

Ground truth: `{"doc_count": 1, "complete_count": 0, "inferred_count": 0}`.
(Doc starts at curr=1/total=5; curr=2/total=6 causes `sequence_ok=False` since total changes. complete=0.)

- [ ] **Step 5: Write seq_break.json**

Pattern: Mid-doc sequence break (curr=3 follows curr=1 in same doc), then correct continuation. Tests Ph2 backward recovery after the break.
Ground truth: 1 doc, 1 complete, 1 inferred page.
Trace: Ph1 fwd fills page 1 (failed) as `2/4` from prev `1/4`. `_build_documents`: page 1 is inferred → `inferred_pages`, pages 2-3 are H and pass sequence → `pages`. Doc: found=4, declared=4, sequence_ok=True → complete.

```json
{
  "name": "seq_break",
  "source": "synthetic",
  "reads": [
    {"pdf_page": 0, "curr": 1, "total": 4, "method": "H", "confidence": 0.95},
    {"pdf_page": 1, "curr": null, "total": null, "method": "failed", "confidence": 0.0},
    {"pdf_page": 2, "curr": 3, "total": 4, "method": "H", "confidence": 0.92},
    {"pdf_page": 3, "curr": 4, "total": 4, "method": "H", "confidence": 0.91}
  ]
}
```

Ground truth: `{"doc_count": 1, "complete_count": 1, "inferred_count": 1}`.
(Ph1 fwd fills page 1 as `2/4`; doc becomes 4/4 complete.)

- [ ] **Step 6: Write ds_conflict.json**

Pattern: Pages 1-3 are failed, sandwiched between weakly-confident reads (`1/4` and `4/4`, conf 0.55). Ph1 fwd fills pages 1-3 as `2/4, 3/4, 4/4`. Ph3 xval flags page 3 (inferred `4/4`) as inconsistent because next page is also `4/4` (H) — cap to 0.50. Ph5 D-S: pages 1-2 have both neighbors agreeing → boost via `neighbors_agree==2`. Tests `ds_boost_max` sweep effect on uncertain inferred pages.
Ground truth: 1 doc, 0 complete (found=5 > declared=4), 3 inferred pages.

```json
{
  "name": "ds_conflict",
  "source": "synthetic",
  "reads": [
    {"pdf_page": 0, "curr": 1, "total": 4, "method": "H", "confidence": 0.55},
    {"pdf_page": 1, "curr": null, "total": null, "method": "failed", "confidence": 0.0},
    {"pdf_page": 2, "curr": null, "total": null, "method": "failed", "confidence": 0.0},
    {"pdf_page": 3, "curr": null, "total": null, "method": "failed", "confidence": 0.0},
    {"pdf_page": 4, "curr": 4, "total": 4, "method": "H", "confidence": 0.55}
  ]
}
```

Ground truth: `{"doc_count": 1, "complete_count": 0, "inferred_count": 3}`.
(found=5 > declared=4 → `is_complete` = False → complete_count = 0.)

- [ ] **Step 7: Verify all synthetic ground_truth values by dry-running pipeline**

```python
# Quick verification script — run interactively
import json, sys
sys.path.insert(0, ".")
from eval.inference import run_pipeline, PageRead
from eval.params import PRODUCTION_PARAMS

for fname in ["ins31_gap", "undercount_chain", "ambiguous_start",
              "noisy_period", "seq_break", "ds_conflict"]:
    data = json.load(open(f"eval/fixtures/synthetic/{fname}.json"))
    reads = [PageRead(**r) for r in data["reads"]]
    docs = run_pipeline(reads, PRODUCTION_PARAMS)
    inferred = sum(len(d.inferred_pages) for d in docs)
    complete = sum(1 for d in docs if d.is_complete)
    print(f"{fname}: doc={len(docs)} complete={complete} inferred={inferred}")
```

Compare output against ground_truth.json. If values differ, either fix the fixture JSON or update the ground truth — the fixture is the source of truth for what the engine *should* do; the ground truth records the *expected* result with production params.

- [ ] **Step 8: Commit**

```bash
git add eval/fixtures/synthetic/ eval/ground_truth.json
git commit -m "feat(eval): synthetic fixtures + updated ground truth"
```

---

## Chunk 4: sweep.py + report.py + Validation

### Task 7: Write eval/sweep.py

**Files:**
- Create: `eval/sweep.py`

- [ ] **Step 1: Write sweep.py**

```python
# eval/sweep.py
"""
3-pass parameter sweep for the inference engine.

Pass 1: Latin Hypercube Sample — 500 configs
Pass 2: Fine grid around top-20 from Pass 1 — adjacent index ±1 per param
Pass 3: Beam search from top-5 of Pass 2

Usage:
    cd a:/PROJECTS/PDFoverseer
    python eval/sweep.py
    # → writes eval/results/sweep_YYYYMMDD_HHMMSS.json
"""
from __future__ import annotations
import json
import random
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.inference import run_pipeline, PageRead
from eval.params import PARAM_SPACE, PRODUCTION_PARAMS

FIXTURES_DIR = Path("eval/fixtures")
GROUND_TRUTH_PATH = Path("eval/ground_truth.json")
RESULTS_DIR = Path("eval/results")
TOP_N = 10
LHS_SAMPLES = 500
PASS2_TOP_N = 20
BEAM_TOP_N = 5
RANDOM_SEED = 42


# ── Fixture loading ──────────────────────────────────────────────────────────

def load_fixtures() -> list[dict]:
    fixtures = []
    for path in sorted(FIXTURES_DIR.rglob("*.json")):
        data = json.loads(path.read_text())
        data["reads"] = [PageRead(**r) for r in data["reads"]]
        fixtures.append(data)
    return fixtures


def load_ground_truth() -> dict[str, dict]:
    return json.loads(GROUND_TRUTH_PATH.read_text())


# ── Scoring ──────────────────────────────────────────────────────────────────

def score_config(params: dict, fixtures: list[dict], gt: dict[str, dict],
                 baseline_passes: set[str]) -> dict:
    """
    Returns scores dict:
      doc_count_exact, doc_count_delta, complete_count_exact,
      inferred_delta, regression_count, composite_score
    And per-fixture pass/fail.
    """
    doc_exact = doc_delta = complete_exact = inf_delta = regressions = 0
    fixture_results = {}

    for fx in fixtures:
        name = fx["name"]
        if name not in gt:
            continue
        truth = gt[name]
        docs = run_pipeline(fx["reads"], params)

        got_docs     = len(docs)
        got_complete = sum(1 for d in docs if d.is_complete)
        got_inferred = sum(len(d.inferred_pages) for d in docs)

        d_doc  = abs(got_docs     - truth["doc_count"])
        d_comp = got_docs == truth["doc_count"] and got_complete == truth["complete_count"]
        d_inf  = abs(got_inferred - truth["inferred_count"])

        passed = (d_doc == 0 and d_comp)

        if d_doc == 0:
            doc_exact += 1
        doc_delta     += d_doc
        if d_comp:
            complete_exact += 1
        inf_delta     += d_inf
        if name in baseline_passes and not passed:
            regressions += 1

        fixture_results[name] = "pass" if passed else "fail"

    composite = doc_exact * 3 + complete_exact * 2 - doc_delta - inf_delta - regressions * 5
    return {
        "doc_count_exact": doc_exact,
        "doc_count_delta": doc_delta,
        "complete_count_exact": complete_exact,
        "inferred_delta": inf_delta,
        "regression_count": regressions,
        "composite_score": composite,
        "_fixture_results": fixture_results,
    }


# ── Latin Hypercube Sample ───────────────────────────────────────────────────

def lhs_sample(n: int, seed: int = RANDOM_SEED) -> list[dict]:
    """Generate n well-distributed configs from PARAM_SPACE using LHS."""
    rng = random.Random(seed)
    keys = list(PARAM_SPACE.keys())
    # For each param, divide n slots and sample one per slot
    indices_per_param: dict[str, list[int]] = {}
    for k, vals in PARAM_SPACE.items():
        m = len(vals)
        # Map n slots → m values
        slots = [rng.randint(0, m - 1) for _ in range(n)]
        rng.shuffle(slots)
        indices_per_param[k] = slots

    configs = []
    for i in range(n):
        cfg = {k: PARAM_SPACE[k][indices_per_param[k][i]] for k in keys}
        configs.append(cfg)
    return configs


# ── Fine grid (adjacent step) ────────────────────────────────────────────────

def adjacent_configs(base: dict) -> list[dict]:
    """All single-param adjacent-step perturbations of base config."""
    configs = []
    for k, vals in PARAM_SPACE.items():
        idx = vals.index(base[k])
        for new_idx in [idx - 1, idx + 1]:
            if 0 <= new_idx < len(vals):
                cfg = dict(base)
                cfg[k] = vals[new_idx]
                configs.append(cfg)
    return configs


# ── Sweep runner ─────────────────────────────────────────────────────────────

def run_sweep(fixtures: list[dict], gt: dict) -> dict:
    # Baseline
    print("Scoring baseline (production params)...")
    baseline_result = score_config(PRODUCTION_PARAMS, fixtures, gt, set())
    baseline_passes = {
        name for name, res in baseline_result["_fixture_results"].items()
        if res == "pass"
    }
    print(f"  baseline composite={baseline_result['composite_score']} "
          f"doc_exact={baseline_result['doc_count_exact']} "
          f"passes={len(baseline_passes)}/{len(fixtures)}")

    def run_configs(configs: list[dict], label: str) -> list[tuple[dict, dict]]:
        results = []
        for i, cfg in enumerate(configs):
            s = score_config(cfg, fixtures, gt, baseline_passes)
            results.append((cfg, s))
            if (i + 1) % 100 == 0:
                print(f"  {label}: {i+1}/{len(configs)}", end="\r")
        print(f"  {label}: {len(configs)}/{len(configs)} done")
        return results

    def top_k(results: list[tuple[dict, dict]], k: int) -> list[tuple[dict, dict]]:
        return sorted(results, key=lambda x: (
            -x[1]["composite_score"], x[1]["doc_count_delta"]
        ))[:k]

    # Pass 1: LHS
    print(f"\nPass 1: Latin Hypercube Sample ({LHS_SAMPLES} configs)...")
    p1_configs = lhs_sample(LHS_SAMPLES)
    p1_results = run_configs(p1_configs, "Pass1")
    top20 = top_k(p1_results, PASS2_TOP_N)

    # Pass 2: Fine grid
    print(f"\nPass 2: Fine grid around top-{PASS2_TOP_N}...")
    p2_configs_set: list[dict] = []
    seen = set()
    for cfg, _ in top20:
        for adj in adjacent_configs(cfg):
            key = tuple(sorted(adj.items()))
            if key not in seen:
                seen.add(key)
                p2_configs_set.append(adj)
    p2_results = run_configs(p2_configs_set, "Pass2")
    top5 = top_k(p1_results + p2_results, BEAM_TOP_N)

    # Pass 3: Beam search
    print(f"\nPass 3: Beam search from top-{BEAM_TOP_N}...")
    p3_configs: list[dict] = []
    seen3 = set()
    for cfg, _ in top5:
        for adj in adjacent_configs(cfg):
            key = tuple(sorted(adj.items()))
            if key not in seen3:
                seen3.add(key)
                p3_configs.append(adj)
    p3_results = run_configs(p3_configs, "Pass3")

    # Final ranking
    all_results = p1_results + p2_results + p3_results
    ranked = top_k(all_results, TOP_N)

    # Build output
    top_configs = []
    for rank, (cfg, scores) in enumerate(ranked, 1):
        top_configs.append({
            "rank": rank,
            "params": cfg,
            "scores": {k: v for k, v in scores.items() if not k.startswith("_")},
            "fixture_breakdown": scores["_fixture_results"],
        })

    # Baseline fixture breakdown
    baseline_summary = {k: v for k, v in baseline_result.items() if not k.startswith("_")}
    baseline_summary["fixture_breakdown"] = baseline_result["_fixture_results"]

    return {
        "run_at": datetime.now().isoformat(),
        "fixtures_count": len(fixtures),
        "total_configs_tested": len(all_results),
        "baseline": baseline_summary,
        "top_configs": top_configs,
    }


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    fixtures = load_fixtures()
    gt = load_ground_truth()
    print(f"Loaded {len(fixtures)} fixtures, {len(gt)} ground truth entries")

    result = run_sweep(fixtures, gt)

    out_path = RESULTS_DIR / f"sweep_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(f"\nResults saved to {out_path}")
    print(f"Top config: composite={result['top_configs'][0]['scores']['composite_score']}"
          f" regressions={result['top_configs'][0]['scores']['regression_count']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add eval/sweep.py
git commit -m "feat(eval): 3-pass sweep engine (LHS → fine grid → beam search)"
```

---

### Task 8: Write eval/report.py

**Files:**
- Create: `eval/report.py`

- [ ] **Step 1: Write report.py**

```python
# eval/report.py
"""
Read the latest sweep result and print a human-readable ranked table.

Usage:
    python eval/report.py                         # latest result
    python eval/report.py eval/results/sweep_X.json  # specific file
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

RESULTS_DIR = Path("eval/results")


def load_result(path: Path | None = None) -> dict:
    if path is None:
        candidates = sorted(RESULTS_DIR.glob("sweep_*.json"))
        if not candidates:
            print("No sweep results found in eval/results/")
            sys.exit(1)
        path = candidates[-1]
    print(f"Report for: {path}\n")
    return json.loads(path.read_text())


def fmt_scores(s: dict) -> str:
    return (f"score={s['composite_score']:+4d}  "
            f"doc✓={s['doc_count_exact']:2d}  "
            f"Δdoc={s['doc_count_delta']:2d}  "
            f"com✓={s['complete_count_exact']:2d}  "
            f"Δinf={s['inferred_delta']:2d}  "
            f"reg={s['regression_count']}")


def print_report(result: dict) -> None:
    baseline = result["baseline"]
    top = result["top_configs"]
    total = result["total_configs_tested"]
    fixtures_n = result["fixtures_count"]

    print(f"Sweep: {result['run_at']}  |  {total} configs  |  {fixtures_n} fixtures\n")
    print(f"{'BASELINE':8s}  {fmt_scores(baseline)}")
    print("-" * 80)

    for cfg in top:
        rank = cfg["rank"]
        scores = cfg["scores"]
        params = cfg["params"]
        flag = " ⚠ REGRESSION" if scores["regression_count"] > 0 else ""
        print(f"Rank {rank:2d}  {fmt_scores(scores)}{flag}")

        # Show params that differ from production
        from eval.params import PRODUCTION_PARAMS
        diffs = {k: v for k, v in params.items() if v != PRODUCTION_PARAMS.get(k)}
        if diffs:
            diff_str = "  ".join(f"{k}={v}" for k, v in diffs.items())
            print(f"         Δparams: {diff_str}")
        else:
            print("         Δparams: (same as production)")

        # Fixture breakdown (only failures)
        fails = [k for k, v in cfg.get("fixture_breakdown", {}).items() if v == "fail"]
        if fails:
            print(f"         fails:   {', '.join(fails)}")
        print()


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    result = load_result(path)
    print_report(result)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add eval/report.py
git commit -m "feat(eval): report.py — ranked table with regression flags"
```

---

### Task 9: Baseline Validation

This is the acceptance test for the entire harness. Run the sweep with only the real fixtures using production params and verify the output matches the `[UI:]` log values.

- [ ] **Step 1: Ensure all real fixture ground truth values are filled in**

Check `eval/ground_truth.json` — replace any `0` placeholder values for ART, CH_51, CH_74, HLL with the actual `[UI:]` log values. Scan those PDFs via the server if needed and read the `[UI:]` lines.

- [ ] **Step 2: Dry-run inference on all real fixtures with production params**

```bash
python -c "
import json, sys
sys.path.insert(0, '.')
from eval.inference import run_pipeline, PageRead
from eval.params import PRODUCTION_PARAMS
import pathlib

gt = json.loads(pathlib.Path('eval/ground_truth.json').read_text())
for path in sorted(pathlib.Path('eval/fixtures/real').glob('*.json')):
    data = json.loads(path.read_text())
    reads = [PageRead(**r) for r in data['reads']]
    docs = run_pipeline(reads, PRODUCTION_PARAMS)
    name = data['name']
    truth = gt.get(name, {})
    got_docs = len(docs)
    got_complete = sum(1 for d in docs if d.is_complete)
    got_inferred = sum(len(d.inferred_pages) for d in docs)
    match = ('✓' if got_docs == truth.get('doc_count') and got_complete == truth.get('complete_count') else '✗')
    print(f'{match} {name:8s}: doc={got_docs}/{truth.get(\"doc_count\",\"?\")} '
          f'complete={got_complete}/{truth.get(\"complete_count\",\"?\")} '
          f'inferred={got_inferred}/{truth.get(\"inferred_count\",\"?\")}')
"
```

Expected: All 7 real fixtures show `✓`. If any show `✗`:
- If `doc` or `complete` is off → there is a divergence between `inference.py` and `analyzer.py`. Compare the failing phase step by step using a small fixture.
- If only `inferred` is off → check the undercount recovery loop for differences.

- [ ] **Step 3: Run the full sweep**

```bash
python eval/sweep.py
```

Expected runtime: < 60 seconds. Check that `eval/results/sweep_*.json` is created.

- [ ] **Step 4: Review the report**

```bash
python eval/report.py
```

Confirm baseline row matches expected values. Review top configs. Any config with `⚠ REGRESSION` in the report should be treated with caution.

- [ ] **Step 5: Final commit**

```bash
git add eval/
git commit -m "feat(eval): harness complete — sweep + report validated against UI log baseline"
```
