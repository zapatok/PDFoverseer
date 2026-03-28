# Inference Tuning Postmortem

**Module:** `eval/inference_tuning/`
**Date:** 2026-03-28
**Status:** Sweep4 in production (s2t4-helena ported to core/)

## Purpose

Offline parameter sweep system for the multi-phase document boundary inference engine.
`eval/inference_tuning/inference.py` is a parameterized copy of the full inference pipeline
(phases 1-5 + undercount recovery + Dempster-Shafer post-validation). Production code in
`core/inference.py` is never touched until a sweep result is validated and manually ported.

The harness runs fixtures (serialized `_PageRead` lists) through the engine with candidate
parameter combinations and scores them against ground truth. No OCR, no fitz, no Tesseract
in the sweep itself -- pure data replay.

## Sweep History

| Sweep | Date | Fixtures | Composite | Key Change |
|-------|------|----------|-----------|------------|
| sweep1 | 2026-03-15 | 13 (7 real + 6 syn) | baseline | Initial harness, 3-pass LHS/grid/beam |
| sweep2 | 2026-03-18 | 27 (7 real + 20 syn) | 111 | Fixture refresh, HLL-targeted synthetics, ph5_guard_conf |
| sweep3 | 2026-03-27 | 35 (7 real + 21 syn + 7 degraded) | 146 | Degraded fixtures, clash_boundary_pen tuning |
| sweep4 | 2026-03-27 | 42 (21 real + 13 syn + 8 degraded) | 122 (+11 vs baseline) | Full 21-PDF real set, failure_zone_cbpen_scale, s2t4-helena |

Sweep4 expanded real fixtures from 7 to 21 PDFs, recalibrated scoring, and introduced
`failure_zone_cbpen_scale` to handle large OCR failure zones without regressing on clean PDFs.

## 3-Pass Sweep Strategy

1. **Pass 1 -- Latin Hypercube Sample:** 500 well-distributed configs across ~500k param combos. Identifies promising region.
2. **Pass 2 -- Fine grid:** Top-20 from Pass 1, test adjacent values per param. ~2000 configs.
3. **Pass 3 -- Beam search:** Top-5 from Pass 2, single-parameter perturbations. ~200 configs. Final ranked output.

Total: ~2700 configs per sweep. Runtime: <30 seconds (pure Python, no I/O).

## Scoring Formula

```
composite = doc_exact + complete_exact
            - real_doc_delta * 3
            - syn_doc_delta
            - inf_delta
            - regressions * 5
```

| Fixture Type | doc_exact weight | complete_exact weight |
|-------------|-----------------|---------------------|
| Real | 5 | -- (not scored) |
| Synthetic | 3 | 2 |

Regressions carry a x5 penalty -- preserving what works is a hard constraint.

## Fixture Groups

| Group | Count | Purpose |
|-------|-------|---------|
| `fixtures/real/` | 21 PDFs | Ground truth from production AI logs; doc_count only |
| `fixtures/synthetic/` | 13 | Hand-crafted edge cases (period2_low_conf, undercount_chain, etc.) |
| `fixtures/degraded/` | 8 | Real PDFs with ~15-20% OCR failures injected |

Real fixtures are scored on `doc_count` only (complete/inferred are reference).
Synthetic fixtures are scored on all three metrics.

## Production Parameters (sweep4: s2t4-helena)

```python
MIN_CONF_FOR_NEW_DOC     = 0.55
CLASH_BOUNDARY_PEN       = 1.0
FAILURE_ZONE_CBPEN_SCALE = 3.0
FAILURE_ZONE_MIN_LEN     = 10
PHASE4_FALLBACK_CONF     = 0.10
PH5B_CONF_MIN            = 0.65
PH5B_RATIO_MIN           = 0.90
ANOMALY_DROPOUT          = 0.10
```

## Engine Version History

| Version | Sweep | Key Changes |
|---------|-------|-------------|
| s2t-helena | sweep1-2 | Initial 5-phase + D-S post-validation |
| s2t4-helena | sweep3-4 | failure_zone_cbpen_scale, anomaly_dropout, clash tuning |
| s2t5-vlm | current | VLM correction queue for low-confidence inferred pages |

## Key Decisions

### eval-first workflow

All inference changes are prototyped in `eval/inference.py` and validated against the full
fixture set before porting to `core/inference.py`. This was established after sweep1 found
params that scored well on stale fixtures but worsened production -- the fixtures had been
extracted from an older OCR state and no longer matched current engine input.

### Fixture refresh discipline

Stale fixtures caused sweep1's false positive. Track A of the v2 design mandates re-running
`extract_fixtures.py` after any OCR pipeline change before sweeping.

### min_conf_for_new_doc locked to 0.0

Evaluated at 0.0, 0.45, 0.55, 0.65. Any value >0.0 causes real boundary misses with no
compensating benefit. Locked to [0.0] in param space to eliminate 4x dead search space.

### clash_boundary_pen ceiling

`cbpen >= 1.75` improves ART_674 (-6 to -3) but always regresses CHAR_25 (25 to 26).
Root cause: pages 12-13 in CHAR_25 both read curr=1, total=1 (OCR misread); high cbpen
treats them as evidence of two distinct docs. Ceiling locked at 1.5 pending a param that
segments this interaction.

## Regex Guard Sweep

Tested `tot` upper-bound in `_parse()` plausibility guard: `0 < curr <= total <= N`.

| Guard | ART_670 | INS_31 | Result |
|-------|---------|--------|--------|
| tot<=9 | 666/603 | 29/31 | Regression (total=10 rejected) |
| **tot<=10** | **668/606** | **31/31** | **Optimal** |
| tot<=20 | 665/603 | 29/31 | Regression (FPs from high totals) |

`tot<=10` confirmed optimal. Also discovered ruff Unicode corruption: auto-fix replaced
U+2018/U+2019/U+00B4 with U+FFFD in `_OCR_DIGIT` table, silently breaking OCR digit
normalization. Fixed by restoring from pre-corruption commit.

## Phase 5b Tuning

`ph5b_ratio_min` lowered from 0.95 to 0.90 to fix INS_31's last-page inference gap.
At 0.95, Phase 5b rejected correction of OCR misreads where the ratio of period-consistent
pages was marginally below threshold. At 0.90, INS_31 achieves 31/31 docs with zero
regressions across all 41 other fixtures.

## Lessons Learned

1. **eval-first prevents regressions.** The x5 regression penalty forces conservative
   exploration. Every sweep4 candidate that improved ART also passed all existing fixtures.

2. **Fixture diversity matters.** sweep1 with 13 fixtures missed the CHAR_25 interaction
   that sweep3 with 35 fixtures caught. Degraded fixtures exposed failure-zone behavior
   invisible in clean data.

3. **One variable at a time.** The cbpen/CHAR_25 interaction was only isolated by holding
   all other params constant and sweeping cbpen alone. Multi-param jumps obscure causality.

4. **Stale fixtures are worse than no fixtures.** Optimizing against outdated OCR output
   produces params that actively harm production. Refresh fixtures after every OCR change.

5. **Ruff can corrupt load-bearing Unicode.** Non-ASCII literals in regex/translation tables
   must be protected from auto-formatters. Byte-level verification catches silent corruption.

## Future Work

| Phase | Description | Status |
|-------|-------------|--------|
| Phase C | Structural redesign of period detection / Phase 5b | Deferred (param space exhausted for current architecture) |
| Phase D | Bayesian anchor constraint: high-confidence reads as HMM anchors for global sequence optimization | Idea stage |
| Phase E | Global coherence validation post-inference | Deferred until MP+PDM production testing |
| VLM correction | Low-conf inferred pages (conf<0.60) as targeted VLM correction queue | Design ready (s2t5-vlm) |
| Soft alignment | Probabilistic clash resolution replacing hard gap-solver | Spec written, not implemented |
