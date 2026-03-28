# Inference Engine Tuning — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix ground truth and scoring, expand synthetic fixtures, then run iterative parameter sweeps until ≤2 errors on all 7 real PDFs.

**Architecture:** Three setup tasks (ground truth → scoring reform → fixture expansion) followed by an autonomous iterative sweep loop where Claude runs the sweep, reads results, and modifies fixtures or `eval/inference.py` as needed. Nothing touches `core/analyzer.py` until a validated winning config is found.

**Tech Stack:** Python, pytest, `eval/sweep.py` (3-pass LHS+grid+beam), `eval/inference.py` (parameterized inference engine), `eval/ground_truth.json`, `eval/fixtures/synthetic/`

---

## Chunk 1: Ground Truth + Scoring Reform

### Task 1: Fix ground_truth.json

**Files:**
- Modify: `eval/ground_truth.json`

- [ ] **Step 1: Update doc_count for 5 real PDFs**

Replace the current incorrect values with verified counts from filenames:

```json
{
  "ART":    {"doc_count": 674, "complete_count": 615, "inferred_count": 1156},
  "CH_9":   {"doc_count": 9,   "complete_count": 8,   "inferred_count": 0},
  "CH_39":  {"doc_count": 39,  "complete_count": 37,  "inferred_count": 1},
  "CH_51":  {"doc_count": 51,  "complete_count": 43,  "inferred_count": 0},
  "CH_74":  {"doc_count": 74,  "complete_count": 58,  "inferred_count": 5},
  "HLL":    {"doc_count": 363, "complete_count": 221, "inferred_count": 42},
  "INS_31": {"doc_count": 31,  "complete_count": 29,  "inferred_count": 7}
}
```

Note: `complete_count` and `inferred_count` for real fixtures are kept as reference fields but are NOT used as pass criteria in the new scoring (see Task 3). The values above reflect the most recent production scan for ART/CH_*/INS_31, and an older scan for HLL — this is acceptable since these fields are unused in real-fixture scoring.

- [ ] **Step 2: Commit**

```bash
git add eval/ground_truth.json
git commit -m "fix(eval): correct doc_count ground truth for 5 real PDFs; update HLL ancillary counts"
```

---

### Task 2: Write failing tests for new scoring logic

**Files:**
- Create: `eval/tests/test_sweep_scoring.py`

- [ ] **Step 1: Write the failing tests**

```python
# eval/tests/test_sweep_scoring.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from eval.sweep import score_config
from eval.inference import PageRead, run_pipeline
from eval.params import PRODUCTION_PARAMS


def _real_fx(name, n_pages, curr=1, total=1):
    """Build a minimal real fixture with n_pages identical reads."""
    return {
        "name": name,
        "source": "real",
        "reads": [
            PageRead(pdf_page=i + 1, curr=curr, total=total,
                     method="direct", confidence=1.0)
            for i in range(n_pages)
        ],
    }


def _syn_fx(name, n_pages, curr=1, total=1):
    """Build a minimal synthetic fixture."""
    return {
        "name": name,
        "source": "synthetic",
        "reads": [
            PageRead(pdf_page=i + 1, curr=curr, total=total,
                     method="direct", confidence=1.0)
            for i in range(n_pages)
        ],
    }


def test_real_exact_scores_5():
    """Real fixture with exact doc count earns +5."""
    gt = {"r_ok": {"doc_count": 1, "complete_count": 1, "inferred_count": 0}}
    result = score_config(PRODUCTION_PARAMS, [_real_fx("r_ok", 1)], gt, set())
    assert result["composite_score"] == 5


def test_synthetic_exact_scores_5():
    """Synthetic fixture exact match earns +3 doc + +2 complete = 5."""
    gt = {"s_ok": {"doc_count": 1, "complete_count": 1, "inferred_count": 0}}
    result = score_config(PRODUCTION_PARAMS, [_syn_fx("s_ok", 1)], gt, set())
    assert result["composite_score"] == 5


def test_real_delta_penalizes_3_per_doc():
    """Real fixture off by 2 docs → penalty = 2 × 3 = -6."""
    # 3 pages each 1/1 → 3 docs; GT says 1 → delta = 2
    gt = {"r_bad": {"doc_count": 1, "complete_count": 1, "inferred_count": 0}}
    result = score_config(PRODUCTION_PARAMS, [_real_fx("r_bad", 3)], gt, set())
    assert result["composite_score"] == -6


def test_synthetic_delta_penalizes_1_per_doc():
    """Synthetic fixture off by 2 docs → penalty = 2 × 1 = -2."""
    gt = {"s_bad": {"doc_count": 1, "complete_count": 1, "inferred_count": 0}}
    result = score_config(PRODUCTION_PARAMS, [_syn_fx("s_bad", 3)], gt, set())
    # doc_delta=2: -2; complete_exact: 0 (doc count wrong); inf_delta: 0
    assert result["composite_score"] == -2


def test_real_wrong_complete_count_not_penalized():
    """Real fixture: wrong complete_count in GT does not affect score."""
    gt = {"r_comp": {"doc_count": 1, "complete_count": 999, "inferred_count": 0}}
    result = score_config(PRODUCTION_PARAMS, [_real_fx("r_comp", 1)], gt, set())
    # Only doc_exact +5 — complete_count irrelevant for real fixtures
    assert result["composite_score"] == 5


def test_regression_penalizes_5():
    """Fixture that was passing but now fails → -5 regression."""
    gt = {"r_reg": {"doc_count": 1, "complete_count": 1, "inferred_count": 0}}
    fx = [_real_fx("r_reg", 3)]  # 3 docs, GT=1 → fails
    result = score_config(PRODUCTION_PARAMS, fx, gt, baseline_passes={"r_reg"})
    # delta penalty + regression: -6 - 5 = -11
    assert result["composite_score"] == -11
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd a:/PROJECTS/PDFoverseer && python -m pytest eval/tests/test_sweep_scoring.py -v
```

Expected: FAIL (score_config doesn't yet branch on `source`)

---

### Task 3: Update score_config to branch on fixture source

**Files:**
- Modify: `eval/sweep.py:54-96`

- [ ] **Step 1: Replace score_config**

```python
def score_config(params: dict, fixtures: list[dict], gt: dict[str, dict],
                 baseline_passes: set[str]) -> dict:
    doc_exact = complete_exact = inf_delta = regressions = 0
    real_doc_delta = syn_doc_delta = 0   # kept separate; composite weights differ
    fixture_results = {}

    for fx in fixtures:
        name = fx["name"]
        if name not in gt:
            continue
        truth = gt[name]
        is_real = fx.get("source", "synthetic") == "real"
        docs = run_pipeline(fx["reads"], params)

        got_docs     = len(docs)
        got_complete = sum(1 for d in docs if d.is_complete)
        got_inferred = sum(len(d.inferred_pages) for d in docs)

        d_doc = abs(got_docs - truth["doc_count"])

        if is_real:
            # Real fixtures: doc count only, heavier weights
            passed = (d_doc == 0)
            if d_doc == 0:
                doc_exact += 5
            else:
                real_doc_delta += d_doc          # raw; multiplied in composite
        else:
            # Synthetic fixtures: original behavior
            d_comp = (got_docs == truth["doc_count"]
                      and got_complete == truth["complete_count"])
            d_inf = abs(got_inferred - truth["inferred_count"])
            passed = (d_doc == 0 and d_comp)
            if d_doc == 0:
                doc_exact += 3
            if d_comp:
                complete_exact += 2
            syn_doc_delta += d_doc
            inf_delta += d_inf

        if name in baseline_passes and not passed:
            regressions += 1

        fixture_results[name] = "pass" if passed else "fail"

    composite = (doc_exact + complete_exact
                 - real_doc_delta * 3    # heavier penalty for real fixtures
                 - syn_doc_delta         # original penalty for synthetic
                 - inf_delta
                 - regressions * 5)
    return {
        "doc_count_exact":      doc_exact,
        "doc_count_delta":      real_doc_delta + syn_doc_delta,  # raw total for display
        "complete_count_exact": complete_exact,
        "inferred_delta":       inf_delta,
        "regression_count":     regressions,
        "composite_score":      composite,
        "_fixture_results":     fixture_results,
    }
```

- [ ] **Step 2: Run scoring tests**

```bash
cd a:/PROJECTS/PDFoverseer && python -m pytest eval/tests/test_sweep_scoring.py -v
```

Expected: all 6 PASS

- [ ] **Step 3: Run full test suite**

```bash
cd a:/PROJECTS/PDFoverseer && python -m pytest eval/tests/ -v
```

Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add eval/sweep.py eval/tests/test_sweep_scoring.py
git commit -m "feat(eval): source-aware scoring — real fixtures +5/−3×delta, complete_count excluded"
```

---

## Chunk 2: Synthetic Fixture Expansion

### Task 4: Create failure-pattern fixtures (4)

**Files:**
- Create: `eval/fixtures/synthetic/many_1page_stream.json`
- Create: `eval/fixtures/synthetic/period1_then_multipage.json`
- Create: `eval/fixtures/synthetic/mixed_1_and_2page.json`
- Create: `eval/fixtures/synthetic/high_failure_period2.json`
- Modify: `eval/ground_truth.json`

**Construction logic for each fixture:**

**`many_1page_stream`** — 50 docs of 1 page, ~40% OCR failed.
Pattern: pages where `pdf_page % 5 in (4, 0)` → failed (2 of every 5 = 40% failed).
Expected: doc_count=50 (period=1, all failed pages inferred), complete_count=50, inferred_count=20.

**`period1_then_multipage`** — 28 pages 1/1 (direct) + pages 29,30,31 reading 1/4, 2/4, 3/4 (direct).
This is the INS_31 pattern: dominant period=1 but last 3 pages are a 4-page doc.
Expected: doc_count=29 (28 single-page docs + 1 incomplete 4-pager), complete_count=28, inferred_count=0.
⚠️ Phase 5b interaction: when Phase 5b is enabled during sweep, it will correct pages 29-31 back to 1/1 (28/31 = 90% ratio ≥ 0.85 threshold), changing the engine output to doc_count=31. This will penalize Phase 5b for this fixture — which is intentional, since the fixture tests "real multi-page doc at end" not "misread at end". The verify step (Step 5) will set the actual GT from PRODUCTION_PARAMS (Phase 5b disabled).

**`mixed_1_and_2page`** — Alternating 1-page and 2-page docs, some failures.
Sequence: [1/1], [1/2,2/2], [1/1], [1/2,2/2], … × 5, with every 7th page failed.
That gives: 5 single-page + 5 two-page = 10 docs, 15 pages total, ~2 failed.
Expected: doc_count=10, complete_count=10, inferred_count=2.

**`high_failure_period2`** — period=2, 60%+ failed pages.
10 docs × 2 pages = 20 pages. Pages where `pdf_page % 5 in (3, 4, 5)` → failed (60% failed).
Expected: doc_count=10, complete_count=10, inferred_count=12.

- [ ] **Step 1: Create `many_1page_stream.json`**

```python
import json
reads = []
for i in range(50):
    p = i + 1
    if p % 5 in (4, 0):  # pages 4,5,9,10,... → failed (40%)
        reads.append({"pdf_page": p, "curr": None, "total": None,
                      "method": "failed", "confidence": 0.0})
    else:
        reads.append({"pdf_page": p, "curr": 1, "total": 1,
                      "method": "direct", "confidence": 1.0})
data = {"name": "many_1page_stream", "source": "synthetic", "reads": reads}
# Write to eval/fixtures/synthetic/many_1page_stream.json
```

- [ ] **Step 2: Create `period1_then_multipage.json`**

```python
reads = []
# 28 pages: 1/1 direct
for i in range(28):
    reads.append({"pdf_page": i + 1, "curr": 1, "total": 1,
                  "method": "direct", "confidence": 1.0})
# 3 pages: 1/4, 2/4, 3/4 direct (the multi-page doc)
for curr in [1, 2, 3]:
    reads.append({"pdf_page": 28 + curr, "curr": curr, "total": 4,
                  "method": "direct", "confidence": 1.0})
data = {"name": "period1_then_multipage", "source": "synthetic", "reads": reads}
```

- [ ] **Step 3: Create `mixed_1_and_2page.json`**

```python
reads = []
p = 1
for doc_idx in range(10):
    if doc_idx % 2 == 0:  # 1-page doc
        reads.append({"pdf_page": p, "curr": 1, "total": 1,
                      "method": "direct", "confidence": 1.0})
        p += 1
    else:  # 2-page doc
        reads.append({"pdf_page": p,     "curr": 1, "total": 2,
                      "method": "direct", "confidence": 1.0})
        reads.append({"pdf_page": p + 1, "curr": 2, "total": 2,
                      "method": "direct", "confidence": 1.0})
        p += 2
# Now replace every 7th read with failed
for i, r in enumerate(reads):
    if (i + 1) % 7 == 0:
        reads[i] = {"pdf_page": r["pdf_page"], "curr": None, "total": None,
                    "method": "failed", "confidence": 0.0}
# Result: 5 single-page + 5 two-page = 10 docs, 15 pages, ~2 failed reads
data = {"name": "mixed_1_and_2page", "source": "synthetic", "reads": reads}
```

- [ ] **Step 4: Create `high_failure_period2.json`**

```python
reads = []
for doc_idx in range(10):  # 10 docs × 2 pages = 20 pages
    for curr in [1, 2]:
        p = doc_idx * 2 + curr
        if p % 5 in (3, 4, 0):  # 60% failed
            reads.append({"pdf_page": p, "curr": None, "total": None,
                          "method": "failed", "confidence": 0.0})
        else:
            reads.append({"pdf_page": p, "curr": curr, "total": 2,
                          "method": "direct", "confidence": 1.0})
data = {"name": "high_failure_period2", "source": "synthetic", "reads": reads}
```

- [ ] **Step 5: Verify expected counts by running the engine**

```bash
cd a:/PROJECTS/PDFoverseer && python -c "
import json
from pathlib import Path
from eval.inference import run_pipeline, PageRead
from eval.params import PRODUCTION_PARAMS as P

for name in ['many_1page_stream','period1_then_multipage','mixed_1_and_2page','high_failure_period2']:
    data = json.loads(Path(f'eval/fixtures/synthetic/{name}.json').read_text())
    reads = [PageRead(**r) for r in data['reads']]
    docs = run_pipeline(reads, P)
    complete = sum(1 for d in docs if d.is_complete)
    inferred = sum(len(d.inferred_pages) for d in docs)
    print(f'{name}: docs={len(docs)} complete={complete} inferred={inferred}')
"
```

Use the output to set correct ground_truth values (adjust construction if results differ significantly from design intent).

- [ ] **Step 6: Update ground_truth.json with verified counts**

Add 4 new entries using values from Step 5.

- [ ] **Step 7: Commit**

```bash
git add eval/fixtures/synthetic/many_1page_stream.json \
        eval/fixtures/synthetic/period1_then_multipage.json \
        eval/fixtures/synthetic/mixed_1_and_2page.json \
        eval/fixtures/synthetic/high_failure_period2.json \
        eval/ground_truth.json
git commit -m "feat(eval): add 4 failure-pattern synthetic fixtures"
```

---

### Task 5: Create positive anchor and real-world fixtures (7)

**Files:**
- Create: `eval/fixtures/synthetic/clean_period2.json`
- Create: `eval/fixtures/synthetic/clean_period4.json`
- Create: `eval/fixtures/synthetic/all_1page_clean.json`
- Create: `eval/fixtures/synthetic/variable_doc_sizes.json`
- Create: `eval/fixtures/synthetic/single_long_doc.json`
- Create: `eval/fixtures/synthetic/two_zones_diff_period.json`
- Create: `eval/fixtures/synthetic/sparse_reads.json`
- Modify: `eval/ground_truth.json`

**Construction logic:**

**`clean_period2`** — 10 docs × 2 pages = 20 pages, all direct.
Expected: doc_count=10, complete_count=10, inferred_count=0.

**`clean_period4`** — 5 docs × 4 pages = 20 pages, all direct.
Expected: doc_count=5, complete_count=5, inferred_count=0.

**`all_1page_clean`** — 20 docs × 1 page = 20 pages, all direct.
Expected: doc_count=20, complete_count=20, inferred_count=0.

**`variable_doc_sizes`** — 3×[1p] + 3×[2p] + 2×[3p] + 2×[1p] = 10 docs, 17 pages, all direct.
Expected: doc_count=10, complete_count=10, inferred_count=0.

**`single_long_doc`** — 1 doc of 40 pages, pages 10,20,30 are failed.
Expected: doc_count=1, complete_count=1, inferred_count=3.

**`two_zones_diff_period`** — First 20 pages: 10 docs × 2 pages. Last 20 pages: 5 docs × 4 pages. All direct.
Expected: doc_count=15, complete_count=15, inferred_count=0.

**`sparse_reads`** — 10 pages, all 1/1 docs, 8 failed, only pages 3 and 7 readable (direct 1/1).
Expected: doc_count=10, complete_count=10, inferred_count=8.

- [ ] **Step 1: Create all 7 fixture JSON files**

For each fixture, write a Python snippet matching the construction logic above and save to `eval/fixtures/synthetic/<name>.json`.

`clean_period2`:
```python
reads = []
for doc in range(10):
    for curr in [1, 2]:
        reads.append({"pdf_page": doc*2+curr, "curr": curr, "total": 2,
                      "method": "direct", "confidence": 1.0})
```

`clean_period4`:
```python
reads = []
for doc in range(5):
    for curr in [1, 2, 3, 4]:
        reads.append({"pdf_page": doc*4+curr, "curr": curr, "total": 4,
                      "method": "direct", "confidence": 1.0})
```

`all_1page_clean`:
```python
reads = [{"pdf_page": i+1, "curr": 1, "total": 1, "method": "direct", "confidence": 1.0}
         for i in range(20)]
```

`variable_doc_sizes`:
```python
specs = [(1,1),(1,1),(1,1),(1,2),(2,2),(1,2),(2,2),(1,2),(2,2),(1,3),(2,3),(3,3),(1,3),(2,3),(3,3),(1,1),(1,1)]
reads = [{"pdf_page": i+1, "curr": c, "total": t, "method": "direct", "confidence": 1.0}
         for i,(c,t) in enumerate(specs)]
```

`single_long_doc`:
```python
reads = []
for i in range(40):
    p = i + 1
    if p in (10, 20, 30):
        reads.append({"pdf_page": p, "curr": None, "total": None,
                      "method": "failed", "confidence": 0.0})
    else:
        reads.append({"pdf_page": p, "curr": p, "total": 40,
                      "method": "direct", "confidence": 1.0})
```

`two_zones_diff_period`:
```python
reads = []
# Zone 1: 10 docs × 2 pages
for doc in range(10):
    for curr in [1, 2]:
        reads.append({"pdf_page": doc*2+curr, "curr": curr, "total": 2,
                      "method": "direct", "confidence": 1.0})
# Zone 2: 5 docs × 4 pages
for doc in range(5):
    for curr in [1, 2, 3, 4]:
        reads.append({"pdf_page": 20+doc*4+curr, "curr": curr, "total": 4,
                      "method": "direct", "confidence": 1.0})
```

`sparse_reads`:
```python
reads = []
for i in range(10):
    p = i + 1
    if p in (3, 7):  # only 2 readable pages
        reads.append({"pdf_page": p, "curr": 1, "total": 1,
                      "method": "direct", "confidence": 1.0})
    else:
        reads.append({"pdf_page": p, "curr": None, "total": None,
                      "method": "failed", "confidence": 0.0})
```

- [ ] **Step 2: Verify expected counts**

```bash
cd a:/PROJECTS/PDFoverseer && python -c "
import json
from pathlib import Path
from eval.inference import run_pipeline, PageRead
from eval.params import PRODUCTION_PARAMS as P

names = ['clean_period2','clean_period4','all_1page_clean',
         'variable_doc_sizes','single_long_doc','two_zones_diff_period','sparse_reads']
for name in names:
    data = json.loads(Path(f'eval/fixtures/synthetic/{name}.json').read_text())
    reads = [PageRead(**r) for r in data['reads']]
    docs = run_pipeline(reads, P)
    complete = sum(1 for d in docs if d.is_complete)
    inferred = sum(len(d.inferred_pages) for d in docs)
    print(f'{name}: docs={len(docs)} complete={complete} inferred={inferred}')
"
```

- [ ] **Step 3: Update ground_truth.json with all 7 new entries**

- [ ] **Step 4: Commit**

```bash
git add eval/fixtures/synthetic/ eval/ground_truth.json
git commit -m "feat(eval): add 7 positive anchor and real-world synthetic fixtures"
```

---

## Chunk 3: Iterative Sweep Loop

### Task 6: Run sweep iteration and analyze

This task repeats autonomously up to 10 times. Each iteration follows the same pattern.

**Files potentially modified each iteration:**
- `eval/inference.py` — if engine changes needed
- `eval/fixtures/synthetic/*.json` — if new fixtures needed
- `eval/ground_truth.json` — if new fixtures added
- `eval/params.py` — if new params needed

- [ ] **Step 1: Run sweep**

```bash
cd a:/PROJECTS/PDFoverseer && python eval/sweep.py
```

Sweep writes results to `eval/results/sweep_YYYYMMDD_HHMMSS.json`. Takes ~5-10 minutes.

- [ ] **Step 2: Read results and count real PDF errors**

```bash
cd a:/PROJECTS/PDFoverseer && python eval/report.py
```

Then check top-config against real PDF ground truth:

```bash
cd a:/PROJECTS/PDFoverseer && python -c "
import json, glob
from pathlib import Path
from eval.inference import run_pipeline, PageRead
from eval.params import PRODUCTION_PARAMS

# Load latest sweep result
latest = sorted(glob.glob('eval/results/sweep_*.json'))[-1]
result = json.loads(Path(latest).read_text())
top_params = result['top_configs'][0]['params']

# Check against real fixtures
real_gt = {
    'ART': 674, 'CH_9': 9, 'CH_39': 39, 'CH_51': 51,
    'CH_74': 74, 'HLL': 363, 'INS_31': 31,
}
import os
for name, expected in real_gt.items():
    fx_path = Path(f'eval/fixtures/real/{name}.json')
    data = json.loads(fx_path.read_text())
    reads = [PageRead(**r) for r in data['reads']]
    docs = run_pipeline(reads, top_params)
    got = len(docs)
    status = 'OK' if got == expected else f'ERR {got-expected:+d}'
    print(f'{name:8} expected={expected} got={got} [{status}]')
"
```

- [ ] **Step 3: Decision logic**

Count real PDF errors from Step 2:

**If errors ≤ 2:**
- Record candidate params and scores
- Try to push lower: run one more sweep with tighter PARAM_SPACE around top config
- If at 0 errors: done — port to core
- If still 1-2 errors after one tighter sweep: accept as best result, proceed to Task 7

**If errors > 2 and iteration ≤ 3:**
- Identify which real fixtures fail and direction (over/under count)
- Is the failure pattern represented in synthetic fixtures?
  - **No pattern found** → design and add a new synthetic fixture, update ground_truth.json, go to Step 1
  - **Pattern exists but engine fails** → modify `eval/inference.py` (see engine mod candidates below), go to Step 1

**If errors > 2 and iteration > 3 with no improvement:**
- Escalate to Phase 4 engine modifications:
  1. Enable Phase 5b (set `ph5b_conf_min=0.50`, `ph5b_ratio_min=0.85` as sweepable params)
  2. If still failing: implement contextual new_doc threshold

**Engine modification candidates (Phase 4):**

*Phase 5b — already implemented, just needs enabling in params.py:*
```python
# In eval/params.py PARAM_SPACE, change:
"ph5b_conf_min": [0.0, 0.50, 0.60, 0.70],
# To include it in active sweep (it's already there)
```

*Contextual new_doc threshold — if needed:*
In `eval/inference.py`, Phase 1 new-doc detection, before opening a new doc check if the NEXT read is also curr=1 (two consecutive curr=1 reads strongly suggests a real boundary vs. an orphan).

- [ ] **Step 4: Commit after each iteration**

```bash
git add -A
git commit -m "eval(iter-N): <what changed — fixture added / param adjusted / engine modified>"
```

Repeat from Step 1.

---

### Task 7: Port winning config to core

**Only execute after real PDF errors = 0 or after exhausting 10 iterations with best ≤2 errors.**

**Files:**
- Modify: `core/analyzer.py`

- [ ] **Step 1: Compare eval/inference.py with core/analyzer.py**

Identify all parameterized values in the winning config and find their hardcoded equivalents in core.

- [ ] **Step 2: Apply winning params to core**

Update `MIN_CONF_FOR_NEW_DOC` and all Phase 5 D-S weights. If Phase 5b was activated, port Phase 5b logic from `eval/inference.py` to `core/analyzer.py`.

- [ ] **Step 3: Run full test suite**

```bash
cd a:/PROJECTS/PDFoverseer && python -m pytest eval/tests/ -v
```

Expected: all PASS before proceeding.

- [ ] **Step 4: Update INFERENCE_ENGINE_VERSION**

```python
INFERENCE_ENGINE_VERSION = "6ph-t2"  # or next appropriate version
```

- [ ] **Step 5: Verify production server uses new engine**

```bash
# Kill any running server, restart, check first log line
taskkill //F //IM python.exe
python server.py
```

Wait for the first `[AI:XXXXXXXX]` log line. Confirm hash has changed and `INF:6ph-t2` appears.
Stop server with Ctrl+C once confirmed.

- [ ] **Step 6: Commit**

```bash
git add core/analyzer.py
git commit -m "perf(core): port tuned params from eval sweep — INF:6ph-t2"
```
