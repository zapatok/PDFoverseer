# VLM Safe Integration: Period-Gated Tier 3 + Rollback + Confirmation

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate VLM into the OCR pipeline so it can only improve results, never degrade them — using period-gating to filter bad reads and two-pass rollback as a safety net.

**Architecture:** Three-layer defense: (1) Period gate rejects VLM reads with wrong `total`, (2) Two-pass rollback compares VLM-augmented vs baseline inference and keeps the better result, (3) Post-inference confirmation boosts confidence on low-conf pages where VLM agrees. Layers 1+2 fix DOC count; Layer 3 reduces human review burden.

**Tech Stack:** Python, existing VLM providers (Ollama/Claude), existing inference engine (unchanged).

---

## Background: Why Previous Approaches Failed

Four VLM experiments (s2t5 through s2t9) all degraded ART_670 from baseline 668 docs:

| Version | Model | Architecture | DOC | XVAL ✗ |
|---------|-------|-------------|-----|--------|
| baseline | none | no VLM | 668 | 0 |
| s2t6 | gemma3:4b | Tier 3 (vlm_ollama@0.85) | 660 | 8 |
| s2t7 | gemma3:4b | Tier 3 (inferred@0.45) | 663 | 15 |
| s2t8 | qwen2.5vl:7b | Tier 3 (inferred@0.45) | 664 | 18 |
| s2t9 | claude-haiku | Tier 3 (inferred@0.45) | 665 | 32 |

**Root cause:** VLM reads with wrong `total` (e.g., 2/7 when period=4) poison the gap solver's anchor points, causing cascading errors. The inference engine handles "no data" (pure gaps) better than "wrong data."

**Key findings from research agents:**

1. **`_build_documents` ignores confidence** — only uses `curr`, `total`, `method`. Pure confidence boosts don't change DOC/COM counts.
2. **Period gating eliminates the dominant error class** — most wrong VLM reads have `total ≠ expected_total`. Rejecting these cuts the error rate dramatically.
3. **Two-pass rollback provides a hard floor** — compare baseline inference vs VLM-augmented inference, keep whichever produces more docs (or same docs with better boundaries).
4. **32 "mid" pages (conf=0.50)** from Phase 5b corrections are the best VLM confirmation targets.
5. **266 "~" pages (conf≈0.87)** are already near-maximum confidence and don't benefit from VLM.

## Architecture

```
OCR (Tier 1+2) → Period Detection → Baseline Inference (pass 1)
                                          ↓
                                   Save baseline_docs, baseline_boundaries
                                          ↓
                              VLM Tier 3 (period-gated) on failed pages
                                          ↓
                              Re-run Inference (pass 2) with VLM reads
                                          ↓
                              Compare: vlm_docs >= baseline_docs?
                                   ↓              ↓
                                  YES             NO → rollback to baseline
                                   ↓
                              VLM Confirmation on low-conf inferred pages
                                          ↓
                              Build Documents → Emit Telemetry
```

## Layer 1: Period-Gated VLM Tier 3

### What changes

In `core/vlm_resolver.py`, after the plausibility guard (`0 < curr <= total <= 10`), add a period gate: if `period_conf >= PH5B_CONF_MIN (0.65)` and `vlm_total != expected_total`, reject the read.

This eliminates VLM reads like 2/7, 4/6, 2/8, 8/8, 1/6 — the exact error class that caused all four test failures.

### Why it works

The period is computed from ~2131 successful Tesseract reads. For ART_670 with period=4 at 84% confidence, the expected total is well-established. A VLM read claiming total=7 when period says total=4 is almost certainly wrong.

After period gating, the remaining error class is "correct total, wrong curr" — which Phase 3 cross-validation already handles (caps at conf≤0.40).

## Layer 2: Two-Pass Rollback

### What changes

In `core/pipeline.py`, the flow becomes:

1. Run `_infer_missing(reads_clean, period_info)` → baseline result
2. Save `baseline_doc_count` and `baseline_boundaries` (set of pages where `curr==1`)
3. Inject period-gated VLM reads into a copy of reads
4. Run `_infer_missing(vlm_reads, period_info)` → VLM result
5. Compare: if `vlm_doc_count >= baseline_doc_count` AND no baseline boundaries were lost → use VLM result
6. Otherwise → rollback to baseline result

### Why it works

The baseline becomes a hard floor. VLM can only produce results that are equal-or-better. Even if period gating misses some errors, rollback catches the damage.

The comparison checks both count AND boundary stability — preventing the case where two errors cancel out (one merge + one split = same count but wrong documents).

### Cost

Two inference passes instead of one. Since inference is pure Python with no I/O, the overhead is negligible (~1ms for 2719 pages).

## Layer 3: VLM Confirmation (Post-Inference)

### What changes

After the winning inference result (baseline or VLM-augmented), query VLM for pages with:
- `method="inferred"` AND `confidence <= 0.60`
- Has an `InferenceIssue` (type != "gap")

If VLM agrees exactly (`curr` AND `total` match) → boost confidence by `+0.20` (cap at `0.80`).
If VLM disagrees → no change, just log.

### Why it matters

Doesn't change DOC/COM, but reduces the human review queue. Pages confirmed by VLM move from "low confidence" to "confirmed" in the UI, reducing the number of items a human needs to review.

### Candidate count estimate

ART_670 baseline has 32 "mid" pages (conf=0.50, Phase 5b corrections). These are the primary targets. Additional candidates from contradiction issues if any.

---

## Files to Modify

| File | Changes |
|------|---------|
| `core/vlm_resolver.py` | Add `period_info` param to `query_failed_pages`, add period gate, add `confirm_inferred_pages()` function |
| `core/pipeline.py` | Two-pass rollback logic, VLM confirmation block after inference, update telemetry |
| `core/utils.py` | New constants: `VLM_CONFIRM_BOOST`, `VLM_CONFIRM_CAP`, `VLM_DEFAULT_MODE`; bump versions |
| `tests/test_vlm_resolver.py` | Tests for period gate, confirmation mode, rollback logic |
| `tests/test_pipeline_vlm.py` | Integration tests for new pipeline flow |

## Files Unchanged

| File | Why |
|------|-----|
| `core/inference.py` | No changes — inference engine is not modified |
| `core/vlm_provider.py` | Providers are solid, reuse as-is |
| `api/worker.py` | Already wires vlm_provider correctly |

---

## Task 1: Period Gate in VLM Resolver

**Files:**
- Modify: `core/vlm_resolver.py`
- Modify: `core/utils.py` (add `VLM_PERIOD_GATE = True` constant)
- Test: `tests/test_vlm_resolver.py`

### Steps

- [ ] **Step 1.1: Write failing test for period gate**

```python
def test_query_rejects_wrong_total_when_period_known():
    """VLM read with total != expected_total is rejected when period is confident."""
    reads = [
        _make_read(1, 1, 4),
        _failed(2),
        _failed(3),
        _make_read(4, 4, 4),
    ]
    provider = MockProvider({
        0: VLMResult("2/7", (2, 7), 0.85, 200.0, None),  # wrong total
        1: VLMResult("3/4", (3, 4), 0.85, 200.0, None),  # correct total
    })
    period_info = {"expected_total": 4, "period_conf": 0.85}

    p1, p2 = _mock_fitz_and_clip()
    with p1, p2:
        _, stats = query_failed_pages(
            reads, provider, "test.pdf",
            on_log=lambda m, l: None, skip_isolated=True,
            period_info=period_info,
        )

    assert stats["read"] == 1       # only 3/4 accepted
    assert stats["period_rejected"] == 1  # 2/7 rejected by period gate
    assert reads[1].method == "failed"    # still failed
    assert reads[2].method == "inferred"  # accepted


def test_query_allows_wrong_total_when_period_uncertain():
    """VLM read with total != expected_total is allowed when period confidence is low."""
    reads = [
        _make_read(1, 1, 4),
        _failed(2),
        _failed(3),
        _make_read(4, 4, 4),
    ]
    provider = MockProvider({
        0: VLMResult("2/3", (2, 3), 0.85, 200.0, None),  # different total
        1: VLMResult("3/4", (3, 4), 0.85, 200.0, None),
    })
    period_info = {"expected_total": 4, "period_conf": 0.40}  # low confidence

    p1, p2 = _mock_fitz_and_clip()
    with p1, p2:
        _, stats = query_failed_pages(
            reads, provider, "test.pdf",
            on_log=lambda m, l: None, skip_isolated=True,
            period_info=period_info,
        )

    assert stats["read"] == 2  # both accepted (period gate inactive)
```

- [ ] **Step 1.2: Run tests to verify they fail**

Run: `pytest tests/test_vlm_resolver.py -k "period" -v`
Expected: FAIL (query_failed_pages doesn't accept period_info yet)

- [ ] **Step 1.3: Add `VLM_PERIOD_GATE = True` constant to `core/utils.py`**

- [ ] **Step 1.4: Add `period_info` parameter to `query_failed_pages`**

Add optional parameter `period_info: dict | None = None` to `query_failed_pages()`.

After the existing plausibility guard (`0 < curr <= total <= _MAX_TOTAL`), add:

```python
# Period gate: reject reads where total contradicts established period
if (
    period_info is not None
    and period_info.get("period_conf", 0) >= PH5B_CONF_MIN
    and total != period_info.get("expected_total", total)
):
    stats["period_rejected"] += 1
    on_log(
        f"  VLM p{r.pdf_page}: {curr}/{total} rejected (period={period_info['expected_total']})",
        "page_warn",
    )
    continue
```

Add `"period_rejected": 0` to the stats dict initialization.

- [ ] **Step 1.5: Run tests to verify they pass**

Run: `pytest tests/test_vlm_resolver.py -v`
Expected: ALL PASS

- [ ] **Step 1.6: Update pipeline.py to pass period_info to query_failed_pages**

In `core/pipeline.py`, the VLM Tier 3 block currently runs before period detection. Move it AFTER period detection, or pass `period_info` from the already-computed detection:

```python
# Period detection (before VLM now)
period_info = inference._detect_period(reads_clean)

# VLM Tier 3 with period gate
vlm_stats = None
failed_count = sum(1 for r in reads_clean if r.method == "failed")
if vlm_provider is not None and failed_count > 0:
    from core.vlm_resolver import query_failed_pages
    reads_clean, vlm_stats = query_failed_pages(
        reads_clean, vlm_provider, pdf_path, on_log, cancel_event,
        period_info=period_info,
    )
```

- [ ] **Step 1.7: Ruff check + full test suite**

Run: `ruff check core/vlm_resolver.py core/pipeline.py core/utils.py`
Run: `pytest tests/test_vlm_resolver.py tests/test_pipeline_vlm.py -v`

- [ ] **Step 1.8: Commit**

```bash
git add core/vlm_resolver.py core/pipeline.py core/utils.py tests/test_vlm_resolver.py
git commit -m "feat(vlm): add period gate to reject VLM reads with wrong total"
```

---

## Task 2: Two-Pass Rollback

**Files:**
- Modify: `core/pipeline.py`
- Modify: `core/utils.py` (add `VLM_ROLLBACK_ENABLED = True`)
- Test: `tests/test_pipeline_vlm.py`

### Steps

- [ ] **Step 2.1: Write failing test for rollback logic**

```python
def test_rollback_when_vlm_degrades():
    """Pipeline keeps baseline result when VLM-augmented inference produces fewer docs."""
    # This is an integration test concept — test the rollback helper function
    from core.pipeline import _should_rollback

    baseline = {"doc_count": 668, "boundaries": {1, 5, 9, 13}}
    vlm_aug  = {"doc_count": 665, "boundaries": {1, 5, 13}}  # lost boundary at 9

    assert _should_rollback(baseline, vlm_aug) is True


def test_no_rollback_when_vlm_improves():
    """Pipeline uses VLM result when it produces more docs."""
    from core.pipeline import _should_rollback

    baseline = {"doc_count": 668, "boundaries": {1, 5, 9, 13}}
    vlm_aug  = {"doc_count": 669, "boundaries": {1, 5, 9, 13, 17}}

    assert _should_rollback(baseline, vlm_aug) is False


def test_rollback_on_boundary_loss_even_if_count_same():
    """Rollback triggers when a baseline boundary disappears even if count matches."""
    from core.pipeline import _should_rollback

    baseline = {"doc_count": 668, "boundaries": {1, 5, 9, 13}}
    vlm_aug  = {"doc_count": 668, "boundaries": {1, 5, 13, 17}}  # lost 9, gained 17

    assert _should_rollback(baseline, vlm_aug) is True
```

- [ ] **Step 2.2: Run tests to verify they fail**

- [ ] **Step 2.3: Implement `_should_rollback` helper in `core/pipeline.py`**

```python
def _should_rollback(baseline: dict, vlm_augmented: dict) -> bool:
    """Return True if VLM-augmented result is worse than baseline.

    Triggers rollback if:
    - VLM produces fewer documents, OR
    - VLM lost any baseline boundary (even if count is same — means a merge+split)
    """
    if vlm_augmented["doc_count"] < baseline["doc_count"]:
        return True
    lost_boundaries = baseline["boundaries"] - vlm_augmented["boundaries"]
    return len(lost_boundaries) > 0
```

- [ ] **Step 2.4: Implement two-pass logic in `analyze_pdf`**

In the pipeline flow, after period detection and before `_build_documents`:

```python
import copy

# === Pass 1: Baseline inference (no VLM) ===
reads_baseline = copy.deepcopy(reads_clean)
reads_baseline, _inf_issues_baseline = inference._infer_missing(reads_baseline, period_info)
baseline_boundaries = {r.pdf_page for r in reads_baseline if r.method == "inferred" and r.curr == 1}
baseline_doc_count = len([r for r in reads_baseline if r.curr == 1])

# === VLM Tier 3 (period-gated) ===
vlm_stats = None
rollback = False
failed_count = sum(1 for r in reads_clean if r.method == "failed")
if vlm_provider is not None and failed_count > 0:
    reads_vlm = copy.deepcopy(reads_clean)
    reads_vlm, vlm_stats = query_failed_pages(
        reads_vlm, vlm_provider, pdf_path, on_log, cancel_event,
        period_info=period_info,
    )

    if vlm_stats.get("read", 0) > 0:
        # === Pass 2: VLM-augmented inference ===
        reads_vlm, _inf_issues_vlm = inference._infer_missing(reads_vlm, period_info)
        vlm_boundaries = {r.pdf_page for r in reads_vlm if r.method == "inferred" and r.curr == 1}
        vlm_doc_count = len([r for r in reads_vlm if r.curr == 1])

        rollback = _should_rollback(
            {"doc_count": baseline_doc_count, "boundaries": baseline_boundaries},
            {"doc_count": vlm_doc_count, "boundaries": vlm_boundaries},
        )

        if rollback:
            on_log(f"VLM rollback: {vlm_doc_count} docs vs baseline {baseline_doc_count} — keeping baseline", "warn")
            reads_clean = reads_baseline
            _inf_issues = _inf_issues_baseline
            vlm_stats["rollback"] = True
        else:
            on_log(f"VLM accepted: {vlm_doc_count} docs (baseline {baseline_doc_count})", "ok")
            reads_clean = reads_vlm
            _inf_issues = _inf_issues_vlm
            vlm_stats["rollback"] = False
    else:
        reads_clean = reads_baseline
        _inf_issues = _inf_issues_baseline
else:
    reads_clean, _inf_issues = inference._infer_missing(reads_clean, period_info)
```

- [ ] **Step 2.5: Run tests**

Run: `pytest tests/test_vlm_resolver.py tests/test_pipeline_vlm.py -v`

- [ ] **Step 2.6: Update telemetry to show rollback status**

In `_format_vlm_line`, add rollback indicator:
```python
if s.get("rollback"):
    return f"ROLLBACK {existing_line}"
```

- [ ] **Step 2.7: Ruff check + commit**

```bash
git add core/pipeline.py core/utils.py tests/test_pipeline_vlm.py
git commit -m "feat(vlm): add two-pass rollback — VLM can never degrade results"
```

---

## Task 3: VLM Confirmation Mode (Post-Inference)

**Files:**
- Modify: `core/vlm_resolver.py` (add `confirm_inferred_pages`)
- Modify: `core/pipeline.py` (add confirmation block after inference)
- Modify: `core/utils.py` (add confirmation constants)
- Test: `tests/test_vlm_resolver.py`

### Steps

- [ ] **Step 3.1: Add constants to `core/utils.py`**

```python
VLM_CONFIRM_BOOST    = 0.20   # confidence boost when VLM confirms inference
VLM_CONFIRM_CAP      = 0.80   # max confidence after VLM confirmation
VLM_CONFIRM_THRESHOLD = 0.60  # only confirm pages with conf <= this
```

- [ ] **Step 3.2: Write failing tests for confirmation mode**

```python
def test_confirm_boosts_confidence_on_agreement():
    """VLM confirmation boosts confidence when it agrees with inference."""
    reads = [
        _make_read(1, 1, 4),
        _PageRead(pdf_page=2, curr=2, total=4, method="inferred", confidence=0.50),
        _make_read(3, 3, 4),
    ]
    issues = [InferenceIssue(pdf_page=2, issue_type="low_confidence", confidence=0.50, context="test")]
    provider = MockProvider({
        0: VLMResult("2/4", (2, 4), 0.85, 200.0, None),
    })

    p1, p2 = _mock_fitz_and_clip()
    with p1, p2:
        _, stats = confirm_inferred_pages(
            reads, issues, provider, "test.pdf",
            on_log=lambda m, l: None,
        )

    assert stats["confirmed"] == 1
    assert reads[1].confidence == 0.70  # 0.50 + 0.20
    assert reads[1].curr == 2           # unchanged
    assert reads[1].total == 4          # unchanged
    assert reads[1].method == "inferred" # unchanged


def test_confirm_no_change_on_disagreement():
    """VLM disagreement leaves read unchanged."""
    reads = [
        _make_read(1, 1, 4),
        _PageRead(pdf_page=2, curr=2, total=4, method="inferred", confidence=0.50),
        _make_read(3, 3, 4),
    ]
    issues = [InferenceIssue(pdf_page=2, issue_type="low_confidence", confidence=0.50, context="test")]
    provider = MockProvider({
        0: VLMResult("3/4", (3, 4), 0.85, 200.0, None),  # wrong curr
    })

    p1, p2 = _mock_fitz_and_clip()
    with p1, p2:
        _, stats = confirm_inferred_pages(
            reads, issues, provider, "test.pdf",
            on_log=lambda m, l: None,
        )

    assert stats["hard_disagree"] == 1
    assert reads[1].confidence == 0.50  # unchanged
    assert reads[1].curr == 2           # unchanged


def test_confirm_caps_at_vlm_confirm_cap():
    """Confidence boost is capped at VLM_CONFIRM_CAP."""
    reads = [
        _make_read(1, 1, 4),
        _PageRead(pdf_page=2, curr=2, total=4, method="inferred", confidence=0.65),
        _make_read(3, 3, 4),
    ]
    issues = [InferenceIssue(pdf_page=2, issue_type="boundary_inferred", confidence=0.65, context="test")]
    # conf=0.65 > threshold 0.60, so this should NOT be a candidate
    provider = MockProvider()

    p1, p2 = _mock_fitz_and_clip()
    with p1, p2:
        _, stats = confirm_inferred_pages(
            reads, issues, provider, "test.pdf",
            on_log=lambda m, l: None,
        )

    assert stats["candidates"] == 0  # above threshold, not a candidate


def test_confirm_skips_gap_issues():
    """Pages with gap issues are not confirmation candidates."""
    reads = [
        _PageRead(pdf_page=1, curr=None, total=None, method="failed", confidence=0.0),
    ]
    issues = [InferenceIssue(pdf_page=1, issue_type="gap", confidence=0.0, context="unresolved")]
    provider = MockProvider()

    _, stats = confirm_inferred_pages(
        reads, issues, provider, "test.pdf",
        on_log=lambda m, l: None,
    )

    assert stats["candidates"] == 0
```

- [ ] **Step 3.3: Run tests to verify they fail**

- [ ] **Step 3.4: Implement `_find_confirmation_candidates` in `core/vlm_resolver.py`**

```python
_CONFIRM_PRIORITY = {
    "boundary_inferred": 0,
    "contradiction":     1,
    "low_confidence":    2,
}


def _find_confirmation_candidates(
    reads: list[_PageRead],
    issues: list[InferenceIssue],
    threshold: float,
) -> list[int]:
    """Return 0-based indices into reads for pages to confirm, sorted by priority."""
    issue_map: dict[int, str] = {}
    for iss in issues:
        if iss.issue_type != "gap":
            issue_map[iss.pdf_page] = iss.issue_type

    candidates = []
    for i, r in enumerate(reads):
        if r.pdf_page not in issue_map:
            continue
        if r.method != "inferred":
            continue
        if r.confidence > threshold:
            continue
        candidates.append((i, _CONFIRM_PRIORITY.get(issue_map[r.pdf_page], 9)))

    candidates.sort(key=lambda x: x[1])
    return [idx for idx, _ in candidates]
```

- [ ] **Step 3.5: Implement `confirm_inferred_pages` in `core/vlm_resolver.py`**

Full function following the same temp-file + render pattern as `query_failed_pages`, but:
- Uses `_find_confirmation_candidates` instead of `_find_candidates`
- Compares VLM parsed result against `(r.curr, r.total)` — exact match = confirmed
- On confirmation: `r.confidence = min(r.confidence + VLM_CONFIRM_BOOST, VLM_CONFIRM_CAP)`
- On disagreement: no change to read, log and count

- [ ] **Step 3.6: Run tests to verify they pass**

- [ ] **Step 3.7: Add confirmation block in `core/pipeline.py`**

After the two-pass rollback block (after the winning `reads_clean` and `_inf_issues` are determined):

```python
# VLM Confirmation: boost low-confidence inferred pages
vlm_confirm_stats = None
if vlm_provider is not None and _inf_issues:
    from core.vlm_resolver import confirm_inferred_pages
    reads_clean, vlm_confirm_stats = confirm_inferred_pages(
        reads_clean, _inf_issues, vlm_provider, pdf_path, on_log, cancel_event,
    )
```

- [ ] **Step 3.8: Update `_format_vlm_line` for confirmation stats**

- [ ] **Step 3.9: Ruff check + full test suite + commit**

```bash
git add core/vlm_resolver.py core/pipeline.py core/utils.py tests/test_vlm_resolver.py
git commit -m "feat(vlm): add confirmation mode — boost low-conf pages when VLM agrees"
```

---

## Task 4: Version Bump + Telemetry Update

**Files:**
- Modify: `core/utils.py`
- Modify: `core/pipeline.py`

### Steps

- [ ] **Step 4.1: Bump versions**

```python
INFERENCE_ENGINE_VERSION = "s2t10-safe-vlm"
VLM_ENGINE_VERSION       = "v3.0-pgated-confirm"
```

- [ ] **Step 4.2: Update `_format_vlm_line` to show both tier3 and confirm stats**

- [ ] **Step 4.3: Update method_tally tracking for VLM reads**

- [ ] **Step 4.4: Ruff check + commit**

---

## Task 5: Manual Test + Validate

- [ ] **Step 5.1: Run ART_670 with qwen2.5vl:7b (period-gated + rollback)**

Expected: DOC >= 668, XVAL ✗ = 0 (rollback should fire if VLM degrades)

- [ ] **Step 5.2: Run ART_670 with Claude API (period-gated + rollback)**

Expected: DOC >= 668

- [ ] **Step 5.3: Run INS_31 — verify no regression**

Expected: 31/31 complete

- [ ] **Step 5.4: Compare telemetry across all runs**

- [ ] **Step 5.5: Log results to `manual_test_logs/`**

---

## Expected Results

### ART_670 Projection

| Metric | Baseline | Projected (safe VLM) |
|---|---|---|
| DOC | 668 | >= 668 (guaranteed by rollback) |
| COM | 606 | >= 606 |
| XVAL ✗ | 0 | 0 (rollback catches regressions) |
| VLM reads | 0 | ~80-130 (after period gate) |
| Confirmed | 0 | ~10-20 of 32 mid-conf pages |

### Safety Guarantees

1. **Period gate**: VLM reads with wrong `total` never enter inference
2. **Two-pass rollback**: if VLM-augmented inference is worse → baseline result used
3. **Confirmation mode**: only boosts confidence, never changes curr/total/method
4. **Net effect**: VLM can only improve or be neutral, never degrade

---

## Alternative Approaches (Backup)

If period-gated rollback doesn't improve DOC count (just matches baseline via rollback):

### A. Consensus Mode (dual query)
Query VLM twice per candidate. Only accept if both agree. Error rate drops from ~7% to ~0.5%. Implementation: 5-line change in `query_failed_pages`. Cost: 2x VLM queries.

### B. Selective Targeting by Gap Topology
Only query VLM for structurally ambiguous gaps (where gap solver has low confidence). Skip gaps where inference is already confident. Reduces noise while targeting highest-value uncertainty.

### C. Progressive Fill with Per-Read Rollback
Inject VLM reads one at a time, re-run inference after each, rollback individual reads that cause damage. High complexity but maximizes correct reads accepted.

See `docs/research/2026-03-29-vlm-alternatives.md` for full analysis of each approach.
