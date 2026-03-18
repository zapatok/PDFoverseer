# Inference Engine Tuning v2 — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refresh eval fixtures from current OCR, add HLL-targeted synthetic fixtures, extend the Phase 5 guard for high-confidence inferred boundaries, and run the parameter sweep to reduce production inference errors (ART +2, CH_74 +2, HLL +9).

**Architecture:** Two parallel tracks converge into a 3-pass LHS → fine grid → beam search sweep. Track A re-extracts real fixtures from the 7 real PDFs using the current OCR pipeline. Track B adds 4 new HLL-targeted synthetics and extends the undercount recovery guard in `eval/inference.py`. All changes stay in `eval/` until the sweep validates them, then port to `core/analyzer.py`.

**Tech Stack:** Python 3.10+, pytest, `eval/sweep.py` (LHS + fine grid + beam search), `eval/report.py`, venv-cuda for OCR extraction.

**Spec:** `docs/superpowers/specs/2026-03-18-inference-tuning-v2.md`

---

## Chunk 1: Fixture Refresh

### Task 1: Extract fresh real fixtures from all 7 PDFs

**Files:**
- Run: `eval/extract_fixtures.py` (no code changes)
- Produces: `eval/fixtures/real/ART.json`, `CH_9.json`, `CH_39.json`, `CH_51.json`, `CH_74.json`, `HLL.json`, `INS_31.json`

- [ ] **Step 1: Activate the GPU venv and run extraction**

```bash
source .venv-cuda/Scripts/activate
python eval/extract_fixtures.py
```

This runs the full Tesseract + EasyOCR pipeline on all 7 PDFs (captures raw reads before inference). Expect 10–30 minutes. The script logs each page as it's processed.

- [ ] **Step 2: Verify all 7 fixtures were written**

Run this to check page counts and failure rates:

```bash
python - <<'EOF'
import json
from pathlib import Path
for f in sorted(Path('eval/fixtures/real').glob('*.json')):
    d = json.loads(f.read_text())
    n = len(d['reads'])
    failed = sum(1 for r in d['reads'] if r['curr'] is None)
    print(f"{f.stem}: {n} reads, {failed} failed ({100*failed//n if n else 0}%)")
EOF
```

Expected approximate failure rates (from logsmaster): ART ~24%, HLL ~6%, CH_74 ~1%, others ~0–2%.

- [ ] **Step 3: Commit**

```bash
git add eval/fixtures/real/
git commit -m "feat(eval): refresh real fixtures from current OCR pipeline"
```

---

### Task 2: Update ground_truth.json for real fixtures

**Files:**
- Modify: `eval/ground_truth.json`

- [ ] **Step 1: Compute reference complete_count / inferred_count and update ground_truth**

```bash
python - <<'EOF'
import json, sys
from pathlib import Path
sys.path.insert(0, '.')
from eval.inference import run_pipeline, PageRead
from eval.params import PRODUCTION_PARAMS as P

def load_fixture(path):
    data = json.loads(Path(path).read_text())
    return [PageRead(**{k: v for k, v in r.items() if not k.startswith('_')})
            for r in data['reads']]

gt = json.loads(Path('eval/ground_truth.json').read_text())

# Validated human ground truth (doc counts from logsmaster 2026-03-18):
real_doc_counts = {
    "ART": 674, "CH_9": 9, "CH_39": 39,
    "CH_51": 51, "CH_74": 74, "HLL": 363, "INS_31": 31,
}

for name, expected_docs in real_doc_counts.items():
    path = f'eval/fixtures/real/{name}.json'
    reads = load_fixture(path)
    docs = run_pipeline(reads, P)
    complete = sum(1 for d in docs if d.is_complete)
    inferred = sum(len(d.inferred_pages) for d in docs)
    print(f"{name}: engine={len(docs)} (GT={expected_docs}), complete={complete}, inferred={inferred}")
    gt[name]['doc_count']      = expected_docs  # ground truth (not engine output)
    gt[name]['complete_count'] = complete        # reference only — not used in scoring
    gt[name]['inferred_count'] = inferred        # reference only — not used in scoring

Path('eval/ground_truth.json').write_text(json.dumps(gt, indent=2))
print("\nground_truth.json updated.")
EOF
```

Note: `doc_count` is the VALIDATED human count. `complete_count` and `inferred_count` are engine outputs with PRODUCTION_PARAMS recorded as reference — the sweep only uses `doc_count` for real fixtures. If the engine count for any fixture differs significantly from the human ground truth, that confirms the problem we're solving.

- [ ] **Step 2: Verify the file**

```bash
python -c "
import json
d = json.load(open('eval/ground_truth.json'))
real = ['ART','CH_9','CH_39','CH_51','CH_74','HLL','INS_31']
for k in real:
    print(k, d[k])
"
```

- [ ] **Step 3: Commit**

```bash
git add eval/ground_truth.json
git commit -m "feat(eval): update ground_truth.json with current baseline values"
```

---

## Chunk 2: Param Space + Phase 5 Guard

### Task 3: Update eval/params.py

**Files:**
- Modify: `eval/params.py`
- Modify: `eval/tests/test_inference.py`

- [ ] **Step 1: Write failing tests**

Add to `eval/tests/test_inference.py`:

```python
from eval.params import PRODUCTION_PARAMS as PROD_PARAMS, PARAM_SPACE


def test_params_ph5_guard_conf_in_prod():
    """ph5_guard_conf must be in PRODUCTION_PARAMS with value 0.0 (disabled baseline)."""
    assert "ph5_guard_conf" in PROD_PARAMS
    assert PROD_PARAMS["ph5_guard_conf"] == 0.0


def test_params_ph5b_conf_min_has_040():
    """ph5b_conf_min param space must include 0.40 to cover HLL's ~43% period confidence."""
    assert 0.40 in PARAM_SPACE["ph5b_conf_min"]


def test_params_min_conf_locked():
    """min_conf_for_new_doc must be locked to [0.0] — no sweep needed (binary tradeoff)."""
    assert PARAM_SPACE["min_conf_for_new_doc"] == [0.0]
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest eval/tests/test_inference.py::test_params_ph5_guard_conf_in_prod \
       eval/tests/test_inference.py::test_params_ph5b_conf_min_has_040 \
       eval/tests/test_inference.py::test_params_min_conf_locked -v
```

Expected: 3 FAILED.

- [ ] **Step 3: Update PARAM_SPACE in eval/params.py**

Make three changes:

```python
# 1. Add 0.40 to ph5b_conf_min (covers HLL's ~43% period confidence):
"ph5b_conf_min": [0.0, 0.40, 0.50, 0.60, 0.69, 0.70],

# 2. Add new ph5_guard_conf param:
"ph5_guard_conf": [0.0, 0.70, 0.80, 0.90],

# 3. Lock min_conf_for_new_doc (replace existing 4-value list):
"min_conf_for_new_doc": [0.0],
```

- [ ] **Step 4: Add ph5_guard_conf to PRODUCTION_PARAMS**

```python
"ph5_guard_conf": 0.0,   # disabled — baseline (guard not yet in core/analyzer.py)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest eval/tests/test_inference.py::test_params_ph5_guard_conf_in_prod \
       eval/tests/test_inference.py::test_params_ph5b_conf_min_has_040 \
       eval/tests/test_inference.py::test_params_min_conf_locked -v
```

Expected: 3 PASSED.

- [ ] **Step 6: Commit**

```bash
git add eval/params.py eval/tests/test_inference.py
git commit -m "feat(eval): extend param space — ph5_guard_conf, ph5b 0.40, lock min_conf_for_new_doc"
```

---

### Task 4: Implement Phase 5 guard in eval/inference.py

**Background:** `_undercount_recovery` can absorb a "next doc" into the preceding undercounted doc when their declared totals match and the next doc has few pages. The current guard only protects next-doc starts confirmed by OCR (direct/SR/easyocr). A high-confidence inferred curr=1 start — e.g., one created by Phase 1 after it "sees" the previous doc complete — is NOT protected and can be wrongly absorbed. `ph5_guard_conf` extends the guard: inferred curr=1 starts with confidence ≥ threshold are also treated as confirmed boundaries.

**Files:**
- Modify: `eval/inference.py` — `_undercount_recovery` signature and guard, `run_pipeline` call
- Modify: `eval/tests/test_inference.py`

- [ ] **Step 1: Write failing tests**

Add to `eval/tests/test_inference.py`:

```python
def test_ph5_guard_baseline_no_change():
    """ph5_guard_conf=0.0 (disabled) produces identical result to PRODUCTION_PARAMS."""
    reads = make_reads([
        (0, 1, 2, "H", 0.95), (1, 2, 2, "H", 0.92),
        (2, 1, 2, "H", 0.91), (3, 2, 2, "H", 0.90),
    ])
    docs_prod  = run_pipeline(reads, PROD_PARAMS)
    docs_guard = run_pipeline(reads, {**PROD_PARAMS, "ph5_guard_conf": 0.0})
    assert len(docs_prod) == len(docs_guard)


def test_ph5_guard_protects_inferred_boundary():
    """With guard enabled, high-conf inferred curr=1 is NOT merged by undercount recovery.

    Setup:
      reads[0]: pdf=0, confirmed 1/3  — doc1 start
      reads[1]: pdf=1, pre-set inferred 3/3 — doc1 "last page" (inconsistent sequence
                with reads[0]; Phase 3 caps its confidence to xval_cap but keeps it
                in doc1.inferred_pages. doc1: declared=3, pages=[0], inferred=[1],
                found_total=2, missing=1.)
      reads[2]: pdf=2, pre-set inferred 1/3 at conf=0.90 — doc2 start.
                Consistent with reads[1] (prev.curr==prev.total → new-doc start valid).
                Phase 3 does NOT cap it. Confidence stays 0.90.

    doc2: declared=3, pages=[], inferred=[2], found_total=1.
    Undercount recovery condition: missing(1) >= found_total(1) ✓, declared match ✓.
    Current guard: reads[2].method=="inferred" → has_confirmed_start=False → merge fires.
    New guard (ph5_guard_conf=0.80): reads[2].conf(0.90) >= 0.80 → protected → no merge.
    """
    reads = [
        PageRead(pdf_page=0, curr=1, total=3, method="direct",   confidence=0.95),
        PageRead(pdf_page=1, curr=3, total=3, method="inferred", confidence=0.95),
        PageRead(pdf_page=2, curr=1, total=3, method="inferred", confidence=0.90),
    ]
    docs_no_guard   = run_pipeline(reads, {**PROD_PARAMS, "ph5_guard_conf": 0.0})
    docs_with_guard = run_pipeline(reads, {**PROD_PARAMS, "ph5_guard_conf": 0.80})

    assert len(docs_no_guard)   == 1, "Without guard: over-merge expected (recovery fires)"
    assert len(docs_with_guard) == 2, "With guard: boundary preserved (recovery blocked)"
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest eval/tests/test_inference.py::test_ph5_guard_baseline_no_change \
       eval/tests/test_inference.py::test_ph5_guard_protects_inferred_boundary -v
```

Expected: `test_ph5_guard_protects_inferred_boundary` FAILS with AssertionError (guard not yet implemented — with-guard call also produces 1 doc). `test_ph5_guard_baseline_no_change` may unexpectedly PASS at this step (the current 2-arg function ignores the extra dict key) — that is acceptable; the critical test is the second one.

- [ ] **Step 3: Modify _undercount_recovery in eval/inference.py**

Change the function signature and extend the guard condition. The full modified function:

```python
def _undercount_recovery(reads: list[PageRead], docs: list[Document], params: dict) -> list[Document]:
    """Mirrors the undercount recovery loop in analyze_pdf."""
    reads_by_page = {r.pdf_page: r for r in reads}
    ph5_guard_conf = params.get("ph5_guard_conf", 0.0)
    fixed = 0
    for di in range(len(docs) - 1):
        d, d_next = docs[di], docs[di + 1]
        missing = d.declared_total - d.found_total
        if missing <= 0 or d.declared_total <= 1:
            continue
        if (d_next.found_total <= missing
                and d_next.declared_total == d.declared_total):
            next_pages = d_next.pages + d_next.inferred_pages
            # Guard: do NOT merge if next doc has a confirmed OCR curr==1 start
            # OR a high-confidence inferred curr==1 start (via ph5_guard_conf).
            has_confirmed_start = any(
                reads_by_page[pp].curr == 1
                and (
                    reads_by_page[pp].method not in ("inferred", "failed", "excluded")
                    or (ph5_guard_conf > 0.0
                        and reads_by_page[pp].method == "inferred"
                        and reads_by_page[pp].confidence >= ph5_guard_conf)
                )
                for pp in next_pages if pp in reads_by_page
            )
            if has_confirmed_start:
                continue
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

- [ ] **Step 4: Update the call site in run_pipeline**

Find (line ~63):
```python
docs = _undercount_recovery(reads, docs)
```

Replace with:
```python
docs = _undercount_recovery(reads, docs, params)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest eval/tests/test_inference.py::test_ph5_guard_baseline_no_change \
       eval/tests/test_inference.py::test_ph5_guard_protects_inferred_boundary -v
```

Expected: 2 PASSED.

- [ ] **Step 6: Run full test suite to confirm no regressions**

```bash
pytest eval/tests/ -v
```

Expected: all pre-existing tests still PASS.

- [ ] **Step 7: Commit**

```bash
git add eval/inference.py eval/tests/test_inference.py
git commit -m "feat(eval): add ph5_guard_conf — protect high-conf inferred boundaries from undercount recovery"
```

---

## Chunk 3: New Synthetic Fixtures

Each fixture follows the same TDD pattern: write failing test → generate fixture JSON → add ground truth → run test → commit.

### Task 5: period2_low_conf

**Scenario:** 20 × 2-page docs (40 pages). Period=2 is correct but degraded: pages 6, 14, 22, 30 are misread as 1/1 instead of 1/2 or 2/2, breaking the autocorrelation signal.

**Files:**
- Create: `eval/fixtures/synthetic/period2_low_conf.json`
- Modify: `eval/ground_truth.json`
- Modify: `eval/tests/test_inference.py`

- [ ] **Step 1: Write failing test**

```python
def test_period2_low_conf_loads():
    """period2_low_conf fixture loads and runs without error."""
    import json
    from pathlib import Path
    data = json.loads(Path("eval/fixtures/synthetic/period2_low_conf.json").read_text())
    reads_raw = [PageRead(**{k: v for k, v in r.items() if not k.startswith("_")})
                 for r in data["reads"]]
    docs = run_pipeline(reads_raw, PROD_PARAMS)
    assert len(docs) >= 1
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
pytest eval/tests/test_inference.py::test_period2_low_conf_loads -v
```

Expected: FAIL (FileNotFoundError).

- [ ] **Step 3: Generate the fixture**

```bash
python - <<'EOF'
import json
from pathlib import Path

reads = []
misread_pages = {6, 14, 22, 30}
for doc_i in range(20):
    for page_within in range(2):
        pdf_page = doc_i * 2 + page_within
        if pdf_page in misread_pages:
            curr, total, conf = 1, 1, 0.85
        else:
            curr, total, conf = page_within + 1, 2, 0.90
        reads.append({"pdf_page": pdf_page, "curr": curr, "total": total,
                      "method": "direct", "confidence": conf})

fixture = {"name": "period2_low_conf", "source": "synthetic", "reads": reads}
Path("eval/fixtures/synthetic/period2_low_conf.json").write_text(json.dumps(fixture, indent=2))
print(f"Written: {len(reads)} reads")
EOF
```

- [ ] **Step 4: Verify actual counts and add ground truth entry**

Run the pipeline on the new fixture to get the actual values:

```bash
python - <<'EOF'
import json, sys
sys.path.insert(0, '.')
from pathlib import Path
from eval.inference import run_pipeline, PageRead
from eval.params import PRODUCTION_PARAMS as P
data = json.loads(Path("eval/fixtures/synthetic/period2_low_conf.json").read_text())
reads = [PageRead(**{k: v for k, v in r.items() if not k.startswith("_")}) for r in data["reads"]]
docs = run_pipeline(reads, P)
complete = sum(1 for d in docs if d.is_complete)
inferred = sum(len(d.inferred_pages) for d in docs)
print(f"doc_count={len(docs)}, complete_count={complete}, inferred_count={inferred}")
EOF
```

Add the entry to `eval/ground_truth.json` using the values printed above (expected approximately `doc_count=20, complete_count=16, inferred_count=0` but use the actual output):

```json
"period2_low_conf": {"doc_count": 20, "complete_count": <actual>, "inferred_count": <actual>}
```

- [ ] **Step 5: Run test to confirm PASS**

```bash
pytest eval/tests/test_inference.py::test_period2_low_conf_loads -v
```

- [ ] **Step 6: Commit**

```bash
git add eval/fixtures/synthetic/period2_low_conf.json eval/ground_truth.json eval/tests/test_inference.py
git commit -m "feat(eval): add period2_low_conf synthetic fixture — HLL-like low-confidence period"
```

---

### Task 6: period2_noisy_splits

**Scenario:** 15 × 2-page docs (30 pages). Pages 4, 12, 20 misread as curr=1, total=1 — false new-doc signals in the middle of 2-page documents.

**Files:**
- Create: `eval/fixtures/synthetic/period2_noisy_splits.json`
- Modify: `eval/ground_truth.json`
- Modify: `eval/tests/test_inference.py`

- [ ] **Step 1: Write failing test**

```python
def test_period2_noisy_splits_loads():
    """period2_noisy_splits fixture loads and runs without error."""
    import json
    from pathlib import Path
    data = json.loads(Path("eval/fixtures/synthetic/period2_noisy_splits.json").read_text())
    reads_raw = [PageRead(**{k: v for k, v in r.items() if not k.startswith("_")})
                 for r in data["reads"]]
    docs = run_pipeline(reads_raw, PROD_PARAMS)
    assert len(docs) >= 1
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
pytest eval/tests/test_inference.py::test_period2_noisy_splits_loads -v
```

- [ ] **Step 3: Generate the fixture**

```bash
python - <<'EOF'
import json
from pathlib import Path

reads = []
misread_pages = {4, 12, 20}
for doc_i in range(15):
    for page_within in range(2):
        pdf_page = doc_i * 2 + page_within
        if pdf_page in misread_pages:
            curr, total, conf = 1, 1, 0.88
        else:
            curr, total, conf = page_within + 1, 2, 0.90
        reads.append({"pdf_page": pdf_page, "curr": curr, "total": total,
                      "method": "direct", "confidence": conf})

fixture = {"name": "period2_noisy_splits", "source": "synthetic", "reads": reads}
Path("eval/fixtures/synthetic/period2_noisy_splits.json").write_text(json.dumps(fixture, indent=2))
print(f"Written: {len(reads)} reads")
EOF
```

- [ ] **Step 4: Verify actual counts and add ground truth entry**

```bash
python - <<'EOF'
import json, sys
sys.path.insert(0, '.')
from pathlib import Path
from eval.inference import run_pipeline, PageRead
from eval.params import PRODUCTION_PARAMS as P
data = json.loads(Path("eval/fixtures/synthetic/period2_noisy_splits.json").read_text())
reads = [PageRead(**{k: v for k, v in r.items() if not k.startswith("_")}) for r in data["reads"]]
docs = run_pipeline(reads, P)
complete = sum(1 for d in docs if d.is_complete)
inferred = sum(len(d.inferred_pages) for d in docs)
print(f"doc_count={len(docs)}, complete_count={complete}, inferred_count={inferred}")
EOF
```

Add to `eval/ground_truth.json` using the actual output (expected approximately `doc_count=15, complete_count=12, inferred_count=0`):

```json
"period2_noisy_splits": {"doc_count": 15, "complete_count": <actual>, "inferred_count": <actual>}
```

- [ ] **Step 5: Run test to confirm PASS**

```bash
pytest eval/tests/test_inference.py::test_period2_noisy_splits_loads -v
```

- [ ] **Step 6: Commit**

```bash
git add eval/fixtures/synthetic/period2_noisy_splits.json eval/ground_truth.json eval/tests/test_inference.py
git commit -m "feat(eval): add period2_noisy_splits synthetic fixture"
```

---

### Task 7: mixed_1_2_dense

**Scenario:** 30 docs alternating 1-page (even-indexed) and 2-page (odd-indexed) — 45 pages total. All reads clean. No dominant period: Phase 5b must NOT activate (protects against false correction).

**Files:**
- Create: `eval/fixtures/synthetic/mixed_1_2_dense.json`
- Modify: `eval/ground_truth.json`
- Modify: `eval/tests/test_inference.py`

- [ ] **Step 1: Write failing test**

```python
def test_mixed_1_2_dense_loads():
    """mixed_1_2_dense: 30 docs alternating 1-page and 2-page, all clean reads."""
    import json
    from pathlib import Path
    data = json.loads(Path("eval/fixtures/synthetic/mixed_1_2_dense.json").read_text())
    reads_raw = [PageRead(**{k: v for k, v in r.items() if not k.startswith("_")})
                 for r in data["reads"]]
    docs = run_pipeline(reads_raw, PROD_PARAMS)
    assert len(docs) >= 1
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
pytest eval/tests/test_inference.py::test_mixed_1_2_dense_loads -v
```

- [ ] **Step 3: Generate the fixture**

```bash
python - <<'EOF'
import json
from pathlib import Path

reads = []
pdf_page = 0
for doc_i in range(30):
    if doc_i % 2 == 0:   # 1-page doc
        reads.append({"pdf_page": pdf_page, "curr": 1, "total": 1,
                      "method": "direct", "confidence": 0.92})
        pdf_page += 1
    else:                 # 2-page doc
        reads.append({"pdf_page": pdf_page,     "curr": 1, "total": 2,
                      "method": "direct", "confidence": 0.91})
        reads.append({"pdf_page": pdf_page + 1, "curr": 2, "total": 2,
                      "method": "direct", "confidence": 0.91})
        pdf_page += 2

fixture = {"name": "mixed_1_2_dense", "source": "synthetic", "reads": reads}
Path("eval/fixtures/synthetic/mixed_1_2_dense.json").write_text(json.dumps(fixture, indent=2))
print(f"Written: {len(reads)} reads, {pdf_page} pdf pages, 30 docs")
EOF
```

- [ ] **Step 4: Verify actual counts and add ground truth entry**

```bash
python - <<'EOF'
import json, sys
sys.path.insert(0, '.')
from pathlib import Path
from eval.inference import run_pipeline, PageRead
from eval.params import PRODUCTION_PARAMS as P
data = json.loads(Path("eval/fixtures/synthetic/mixed_1_2_dense.json").read_text())
reads = [PageRead(**{k: v for k, v in r.items() if not k.startswith("_")}) for r in data["reads"]]
docs = run_pipeline(reads, P)
complete = sum(1 for d in docs if d.is_complete)
inferred = sum(len(d.inferred_pages) for d in docs)
print(f"doc_count={len(docs)}, complete_count={complete}, inferred_count={inferred}")
EOF
```

Add to `eval/ground_truth.json` using the actual output (expected `doc_count=30, complete_count=30, inferred_count=0` since all reads are clean):

```json
"mixed_1_2_dense": {"doc_count": 30, "complete_count": <actual>, "inferred_count": <actual>}
```

- [ ] **Step 5: Run test to confirm PASS**

```bash
pytest eval/tests/test_inference.py::test_mixed_1_2_dense_loads -v
```

- [ ] **Step 6: Commit**

```bash
git add eval/fixtures/synthetic/mixed_1_2_dense.json eval/ground_truth.json eval/tests/test_inference.py
git commit -m "feat(eval): add mixed_1_2_dense synthetic fixture"
```

---

### Task 8: period2_boundary_fp

**Scenario:** 10 × 2-page docs (20 pages). Pages 5, 11, 17 are misread as curr=1 instead of curr=2 — they are OCR false-positive document starts in the middle of 2-page documents.

**Files:**
- Create: `eval/fixtures/synthetic/period2_boundary_fp.json`
- Modify: `eval/ground_truth.json`
- Modify: `eval/tests/test_inference.py`

- [ ] **Step 1: Write failing test**

```python
def test_period2_boundary_fp_loads():
    """period2_boundary_fp: 10 x 2-page docs, 3 false-positive curr=1 mid-doc pages."""
    import json
    from pathlib import Path
    data = json.loads(Path("eval/fixtures/synthetic/period2_boundary_fp.json").read_text())
    reads_raw = [PageRead(**{k: v for k, v in r.items() if not k.startswith("_")})
                 for r in data["reads"]]
    docs = run_pipeline(reads_raw, PROD_PARAMS)
    assert len(docs) >= 1
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
pytest eval/tests/test_inference.py::test_period2_boundary_fp_loads -v
```

- [ ] **Step 3: Generate the fixture**

```bash
python - <<'EOF'
import json
from pathlib import Path

false_pos_pages = {5, 11, 17}   # should be curr=2, OCR misread as curr=1
reads = []
for doc_i in range(10):
    for page_within in range(2):
        pdf_page = doc_i * 2 + page_within
        if pdf_page in false_pos_pages:
            curr, conf = 1, 0.87   # misread (should be curr=2)
        else:
            curr, conf = page_within + 1, 0.90
        reads.append({"pdf_page": pdf_page, "curr": curr, "total": 2,
                      "method": "direct", "confidence": conf})

fixture = {"name": "period2_boundary_fp", "source": "synthetic", "reads": reads}
Path("eval/fixtures/synthetic/period2_boundary_fp.json").write_text(json.dumps(fixture, indent=2))
print(f"Written: {len(reads)} reads")
EOF
```

- [ ] **Step 4: Verify actual counts and add ground truth entry**

```bash
python - <<'EOF'
import json, sys
sys.path.insert(0, '.')
from pathlib import Path
from eval.inference import run_pipeline, PageRead
from eval.params import PRODUCTION_PARAMS as P
data = json.loads(Path("eval/fixtures/synthetic/period2_boundary_fp.json").read_text())
reads = [PageRead(**{k: v for k, v in r.items() if not k.startswith("_")}) for r in data["reads"]]
docs = run_pipeline(reads, P)
complete = sum(1 for d in docs if d.is_complete)
inferred = sum(len(d.inferred_pages) for d in docs)
print(f"doc_count={len(docs)}, complete_count={complete}, inferred_count={inferred}")
EOF
```

Add to `eval/ground_truth.json` using the actual output (pages 5, 11, 17 are the second pages of docs 3, 6, 9 — 1-indexed — their misread as curr=1 makes those docs incomplete; expected approximately `doc_count=10, complete_count=7, inferred_count=0`):

```json
"period2_boundary_fp": {"doc_count": 10, "complete_count": <actual>, "inferred_count": <actual>}
```

- [ ] **Step 5: Run test to confirm PASS**

```bash
pytest eval/tests/test_inference.py::test_period2_boundary_fp_loads -v
```

- [ ] **Step 6: Run full test suite**

```bash
pytest eval/tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add eval/fixtures/synthetic/period2_boundary_fp.json eval/ground_truth.json eval/tests/test_inference.py
git commit -m "feat(eval): add period2_boundary_fp synthetic fixture — Phase 5 guard test case"
```

---

## Chunk 4: Sweep Execution + Port

### Task 9: Run the parameter sweep and review results

**Files:**
- Run: `eval/sweep.py`, `eval/report.py` (no code changes)
- Produces: `eval/results/sweep_YYYYMMDD_HHMMSS.json`

- [ ] **Step 1: Verify baseline sanity before full sweep**

```bash
python - <<'EOF'
import sys
sys.path.insert(0, '.')
from eval.sweep import load_fixtures, load_ground_truth, score_config
from eval.params import PRODUCTION_PARAMS as P

fixtures = load_fixtures()
gt = load_ground_truth()
result = score_config(P, fixtures, gt, set())
print(f"Baseline composite score: {result['composite_score']}")
print(f"Doc exact: {result['doc_count_exact']}, Regressions: {result['regression_count']}")
real_names = {'ART','CH_9','CH_39','CH_51','CH_74','HLL','INS_31'}
for name, status in result['_fixture_results'].items():
    if name in real_names or status == 'fail':
        print(f"  {name}: {status}")
EOF
```

All 7 real fixtures must show "pass" before running the sweep. If any fail, the fresh fixtures or ground truth entries have an issue — fix before proceeding.

- [ ] **Step 2: Run the full 3-pass sweep**

```bash
source .venv-cuda/Scripts/activate
python eval/sweep.py
```

Runs ~2700 configs × ~31 fixtures. Expect a few minutes. Saves JSON to `eval/results/`.

- [ ] **Step 3: Review the ranked report**

```bash
python eval/report.py
```

Look for:
- Top configs with `regression_count == 0` (hard requirement — any config with regressions is disqualified)
- Improvement in composite score vs baseline
- Whether HLL is "pass" in top configs (primary target)
- What params changed from baseline in top configs

- [ ] **Step 4: Inspect fixture breakdown for HLL and ART**

```bash
python - <<'EOF'
import json
from pathlib import Path
results_dir = Path("eval/results")
latest = sorted(results_dir.glob("sweep_*.json"))[-1]
data = json.loads(latest.read_text())
print(f"Baseline: {data['baseline']}\n")
for c in data["top_configs"][:5]:
    r = c["rank"]
    s = c["scores"]
    p = c["params"]
    from eval.params import PRODUCTION_PARAMS as P
    diff = {k: v for k, v in p.items() if v != P.get(k)}
    print(f"Rank {r}: score={s['composite_score']}, regressions={s['regression_count']}")
    print(f"  Changed params: {diff}")
    bd = c["fixture_breakdown"]   # per-config breakdown (not at top-level of result JSON)
    print(f"  HLL={bd.get('HLL','?')}, ART={bd.get('ART','?')}")
EOF
```

- [ ] **Step 5: Commit sweep result**

```bash
git add eval/results/
git commit -m "feat(eval): sweep results — inference tuning v2"
```

---

### Task 10: Apply winning params and port to core/analyzer.py

**Prerequisite:** Proceed only if the sweep found a rank-1 config with `regression_count == 0` and improved composite score. If HLL is still failing in all top configs, see the "If HLL still fails" note below.

**Files:**
- Modify: `eval/params.py` — update `PRODUCTION_PARAMS` to winning values
- Modify: `core/analyzer.py` — port winning params and logic changes
- Modify: `eval/tests/test_inference.py` — update baseline test if needed

- [ ] **Step 1: Confirm winning params with a validation run**

Copy the rank-1 params from the report and run:

```bash
python - <<'EOF'
import sys
sys.path.insert(0, '.')
from eval.sweep import load_fixtures, load_ground_truth, score_config
from eval.params import PRODUCTION_PARAMS as P

# Paste winning params from rank-1 config:
winning = {
    **P,
    # "ph5b_conf_min": 0.40,  # example — use actual rank-1 values
    # "ph5_guard_conf": 0.80,
}

fixtures = load_fixtures()
gt = load_ground_truth()
result = score_config(winning, fixtures, gt, set())
print(f"Winning score: {result['composite_score']}, Regressions: {result['regression_count']}")
for name, status in result['_fixture_results'].items():
    if status == 'fail':
        print(f"  FAIL: {name}")
EOF
```

- [ ] **Step 2: Update PRODUCTION_PARAMS in eval/params.py**

Replace changed param values with the winning values.

- [ ] **Step 3: Read the _infer_missing function to locate hardcoded constants**

Most inference parameters in `core/analyzer.py` exist as **inline literals**, not named variables. Only three are named module-level constants:

```bash
grep -n "PH5B_CONF_MIN\|PH5B_RATIO_MIN\|MIN_CONF_FOR_NEW_DOC" core/analyzer.py
```

For all other params (fwd_conf, back_conf, xval_cap, fallback values, DS weights, hom_threshold), read the `_infer_missing` function body directly:

```bash
grep -n "r\.confidence = \|hom_threshold\|0\.85\|= 0\.50\|= 0\.95\|= 0\.90\|= 0\.40\|= 0\.15\|= 0\.08\|= 0\.05\|= 0\.25\|= 0\.23" core/analyzer.py | grep -v "^#" | head -40
```

Cross-reference each literal against `PRODUCTION_PARAMS` in `eval/params.py` to identify which lines correspond to which parameters. The winning params will differ from `PRODUCTION_PARAMS` values — update those specific lines.

- [ ] **Step 4: Port changed parameter values to core/analyzer.py**

For each parameter that changed in the winning config vs. `PRODUCTION_PARAMS`:
- Named constants (`PH5B_CONF_MIN`, `PH5B_RATIO_MIN`, `MIN_CONF_FOR_NEW_DOC`): update the value in the constant definition line.
- Inline literals: find the line from the grep above where the old value appears in the context of that phase, and replace the literal with the new value.

Cross-check: `PRODUCTION_PARAMS` in `eval/params.py` shows the baseline value for each param. If a param changed, find every occurrence of the old literal in the relevant phase and update it.

- [ ] **Step 5: Port ph5_guard_conf logic if winning ph5_guard_conf > 0.0**

If the winning config has `ph5_guard_conf > 0.0`, port the guard logic to `core/analyzer.py`:

a. Add a constant: `PH5_GUARD_CONF = <winning_value>` near other inference constants.

b. Locate `_undercount_recovery` in `core/analyzer.py`. Find the existing guard:
```python
has_confirmed_start = any(
    reads_by_page[pp].curr == 1
    and reads_by_page[pp].method not in ("inferred", "failed", "excluded")
    for pp in next_pages if pp in reads_by_page
)
```

c. Replace with (mirrors the eval/inference.py change from Task 4):
```python
has_confirmed_start = any(
    reads_by_page[pp].curr == 1
    and (
        reads_by_page[pp].method not in ("inferred", "failed", "excluded")
        or (PH5_GUARD_CONF > 0.0
            and reads_by_page[pp].method == "inferred"
            and reads_by_page[pp].confidence >= PH5_GUARD_CONF)
    )
    for pp in next_pages if pp in reads_by_page
)
```

- [ ] **Step 6: Run full test suite**

```bash
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add core/analyzer.py eval/params.py
git commit -m "feat(core): port inference tuning v2 — winning params + ph5 guard to production"
```

- [ ] **Step 8: Run production validation**

Start the backend and run against the real PDFs. Compare against logsmaster baseline:

| PDF | Baseline | Target |
|-----|---------|--------|
| ART | 676 (+2) | ≤ 676 |
| CH_9 | 9 | 9 (exact) |
| CH_39 | 39 | 39 (exact) |
| CH_51 | 51 | 51 (exact) |
| CH_74 | 76 (+2) | ≤ 76 |
| HLL | 372 (+9) | ≤ 366 (target ≤ +3) |
| INS_31 | 31 | 31 (exact) |

If any PDF regresses (goes above baseline), revert `core/analyzer.py` and investigate.

- [ ] **Step 9: Final commit with results summary**

```bash
git commit --allow-empty -m "docs(eval): inference tuning v2 complete — <summarize results here>"
```

---

## If HLL Still Fails After Sweep

If the sweep finds no config that reduces HLL's +9 error without regressions, the parametric space may be exhausted. Next steps (Phase C — structural changes, deferred):

- Investigate why HLL's period is detected at only ~43% confidence — is the autocorrelation function's window too small? Too sensitive to noise?
- Consider adding a smoothed or median-based period estimator
- Consider making `_detect_period` return multiple candidate periods with confidence weights, letting Phase 5b choose per-region rather than globally

File a memory note and raise with the user before attempting Phase C changes.
