# Eval Harness Design — Inference Engine Parameter Sweep
**Date:** 2026-03-15
**Status:** Approved

## Overview

An offline parameter sweep harness that finds optimal tuning for the inference engine in `core/analyzer.py`. Runs autonomously (no token cost per iteration); human reviews the final ranked report.

## Architecture

```
eval/
  fixtures/
    real/          ← reads_clean from 7 real PDFs, serialized to JSON
      ART.json, CH_9.json, CH_39.json, CH_51.json, CH_74.json, HLL.json, INS_31.json
    synthetic/     ← hand-crafted edge cases with known ground truth
      ins31_gap.json, undercount_chain.json, ambiguous_start.json, noisy_period.json, seq_break.json, ds_conflict.json
  ground_truth.json   ← {fixture_name: {doc_count, complete_count, inferred_count}}
  inference.py        ← parameterized copy of the full engine pipeline (does NOT touch analyzer.py)
  params.py           ← parameter search space definition
  sweep.py            ← runs fixtures × param combos, saves results/sweep_*.json
  report.py           ← reads sweep result, prints ranked table + regression flags
  results/            ← sweep outputs (gitignored)
```

**Key principle:** `inference.py` is an independent copy of the inference logic from `analyzer.py`, refactored to accept a `params: dict` argument. Production code is untouched until a sweep result justifies updating the constants.

## inference.py Scope

`inference.py` must replicate the **full pipeline** that produces `Document` objects, not just `_infer_missing`:

1. `_local_total(reads, window, hom_threshold)` — homogeneity-based period detection
2. `_infer_from_neighbors(reads, params)` — 5-phase inference (fwd, back, xval, fallback, D-S)
3. `_build_documents(reads)` — groups reads into Document objects
4. **Undercount recovery loop** (from `analyze_pdf`) — merges absorbed documents, reassigns curr/total on inferred reads

Output type: `list[Document]` — same structure as production, so `doc_count`, `complete_count`, and `inferred_count` can be computed directly.

This is required for the baseline validation (step 8) to match actual AI log values.

## Fixture Format

Each fixture is a JSON file with the following schema:

```json
{
  "name": "INS_31",
  "source": "real",
  "reads": [
    {"pdf_page": 0, "curr": 1, "total": 31, "method": "H", "confidence": 0.95},
    {"pdf_page": 1, "curr": 2, "total": 31, "method": "H", "confidence": 0.92},
    {"pdf_page": 28, "curr": 1, "total": 2, "method": "H", "confidence": 0.88},
    {"pdf_page": 29, "curr": null, "total": null, "method": "?", "confidence": 0.0}
  ]
}
```

Fields map directly to the `_PageRead` dataclass: `pdf_page`, `curr`, `total`, `method`, `confidence`. No OCR or fitz dependency — pure data.

## Ground Truth Schema

```json
{
  "INS_31":          {"doc_count": 4, "complete_count": 3, "inferred_count": 2},
  "ins31_gap":       {"doc_count": 2, "complete_count": 1, "inferred_count": 1},
  "ambiguous_start": {"doc_count": 3, "complete_count": 2, "inferred_count": 4}
}
```

**`inferred_count` definition:** The number of pages where `curr` or `total` was `null` in the raw reads and was filled in by the inference pipeline (phases 1–5 or the undercount recovery loop). A page modified by the undercount loop that was already counted as inferred by phase inference is counted once. Ground truth values for real fixtures are taken from the validated AI log output (`INF:` field); synthetic values are defined at fixture creation time and derive from the fixture's known answer.

## Metrics

| Metric | Description |
|---|---|
| `doc_count_exact` | Number of fixtures where doc count matches exactly |
| `doc_count_delta` | Sum of `\|got - expected\|` across all fixtures (partial credit) |
| `complete_count_exact` | Number of fixtures where complete count matches exactly |
| `inferred_delta` | Sum of `\|inferred_got - inferred_expected\|` (penalizes over/under inference) |
| `regression_count` | Fixtures that passed with baseline (production) params but fail with candidate |
| `composite_score` | `doc_exact*3 + complete_exact*2 - doc_delta - inferred_delta - regression_count*5` |

Regressions carry a ×5 penalty — preserving what works is a hard constraint.

## Parameter Space

Defined in `params.py`. All values are candidate replacements for the hardcoded constants in `analyzer.py`:

```python
PARAM_SPACE = {
    # Phase 1 — Forward propagation
    "fwd_conf":         [0.90, 0.93, 0.95, 0.97],   # forward confidence threshold
    "new_doc_base":     [0.50, 0.60, 0.70],           # new-doc start base confidence
    "new_doc_hom_mul":  [0.20, 0.30, 0.40],           # homogeneity multiplier for new-doc conf

    # Phase 2 — Backward propagation
    "back_conf":        [0.85, 0.90, 0.95],            # backward confidence threshold

    # Phase 3 — Cross-validation
    "xval_cap":         [0.40, 0.50, 0.60],            # cap applied when forward/backward disagree

    # Phase 4 — Fallback
    "fallback_base":    [0.30, 0.40, 0.50],            # fallback base confidence
    "fallback_hom_mul": [0.15, 0.20, 0.25],            # homogeneity multiplier for fallback

    # Phase 5 — D-S post-validation
    "ds_support_min":   [0.15, 0.20, 0.25],            # minimum D-S support to apply boost
    "ds_boost_max":     [0.20, 0.25, 0.30],            # maximum boost from D-S evidence

    # Global
    "window":           [3, 5, 7],                      # local_total window size
    "hom_threshold":    [0.80, 0.85, 0.90],             # homogeneity cutoff (used in Ph1, Ph4, local_total)
}
```

Total space: ~500k combinations — too large for brute force.

## Sweep Strategy (3 Passes)

**Pass 1 — Latin Hypercube Sample:** 500 randomly well-distributed configs across the full parameter space. Identifies the promising region.

**Pass 2 — Fine grid around top-20 from Pass 1:** For each parameter in the top-20 configs, test adjacent values in the `PARAM_SPACE` list (i.e., index ± 1 in the discrete list for that param — not arithmetic ±). ~2000 configs.

**Pass 3 — Beam search:** Take top-5 from Pass 2, apply all single-parameter adjacent-step perturbations. ~200 configs. Final ranked output.

**Total:** ~2700 configs × 12 fixtures ≈ 32k engine runs. Expected runtime: <30 seconds in pure Python.

## Output Format

Results saved to `results/sweep_YYYYMMDD_HHMMSS.json`:

```json
{
  "baseline": {
    "composite_score": 24,
    "doc_count_exact": 7,
    "regression_count": 0
  },
  "top_configs": [
    {
      "rank": 1,
      "params": {"fwd_conf": 0.93, "window": 7, "hom_threshold": 0.85},
      "scores": {"composite_score": 31, "doc_count_exact": 10, "regression_count": 0}
    }
  ],
  "fixture_breakdown": {
    "INS_31": {"baseline": "pass", "rank1": "pass", "rank2": "fail"}
  }
}
```

`report.py` renders a terminal table of the top-10 configs (by `composite_score`) and flags any with `regression_count > 0`. `sweep.py` writes exactly `top_n: 10` entries into `top_configs` — configs are ranked by `composite_score` descending, ties broken by `doc_count_delta` ascending.

## Synthetic Fixtures to Create

| Name | Edge case modeled | What it uniquely tests |
|---|---|---|
| `ins31_gap` | Last-page read as 1/2, next page undetected | Ph4/Ph5 gap recovery at end-of-doc |
| `undercount_chain` | Total consistently underreported across a long doc | Undercount recovery loop correctness |
| `ambiguous_start` | First N pages have no curr/total, boundary unclear | Ph1 new-doc detection without leading signal |
| `noisy_period` | Mixed period lengths within one document | `hom_threshold` sensitivity, local_total stability |
| `seq_break` | Sequence break mid-doc, then correct continuation resumes | Ph2 backward prop recovery after break — distinct from noisy_period (which has no break, just mixed totals) |
| `ds_conflict` | Forward and backward props disagree weakly (conf ~0.5 each); neighborhood agreement is the deciding factor | D-S phase 5 in isolation — exercises `ds_support_min` and `ds_boost_max` independently from fallback |

## Implementation Sequence

1. Extract and serialize `reads_clean` from 7 real PDFs → `fixtures/real/*.json`
2. Write `ground_truth.json` from validated AI log values (doc_count, complete_count, inferred_count per fixture)
3. Write `inference.py` — full pipeline copy: `_local_total`, `_infer_from_neighbors`, `_build_documents`, undercount recovery loop; accepts `params: dict`
4. Write `params.py` (search space as above)
5. Write synthetic fixtures manually; record their ground truth in `ground_truth.json`
6. Write `sweep.py` (3-pass LHS → fine grid → beam search)
7. Write `report.py` (terminal table, regression flags)
8. Validate: run sweep with production param values as baseline → scores for real fixtures must match current AI log results exactly
