# Graph Inference Engine -- Postmortem

**Date:** 2026-03-28
**Status:** Shelved (not adopted)
**Module:** `eval/graph_inference/`

## Purpose

Explore HMM + Viterbi global sequence decoding as an alternative to the
multi-phase inference engine (`core/inference.py`). The hypothesis: a globally
optimal decoder would outperform greedy bidirectional propagation on documents
with irregular lengths, skipped pages, and broken sequences.

## What Was Built

| File | Role |
|------|------|
| `engine.py` | Pure HMM engine: ~466-state space of `(curr, total)` pairs, log-space transition/emission models, numpy Viterbi decoder, document extraction from decoded paths |
| `hybrid.py` | Two-stage pipeline: existing phases 0-6 signal processing (period detection, gap-fill, D-S fusion) followed by Viterbi global decode |
| `compare.py` | Head-to-head comparison of existing / graph / hybrid engines on all active fixtures with best-known params for each |
| `sweep.py` | Parameter sweep over 10 HMM params (~2M combinations) using the same LHS -> fine grid -> beam search pattern as `eval/inference_tuning/` |
| `params.py` | Parameter space definitions and production defaults |
| `docs/specs/` | Design spec with state/transition/emission model details |
| `docs/plans/` | TDD implementation plan (12 tasks, all completed) |

The engine is self-contained (no imports from `core/`), follows the
`eval/inference_tuning/inference.py` pattern, and shares the same
`PageRead`/`Document` types via `eval/shared/types.py`.

## Results

| Engine | Composite Score | Notes |
|--------|----------------|-------|
| **Existing (multi-phase + D-S)** | **~122** | sweep4, s2t4-helena, 42 fixtures |
| Hybrid (phases 0-6 + Viterbi) | ~90 | Marginally better than pure graph |
| Pure graph (HMM-only) | ~85 | Best rank-1 from graph sweep |

Key weaknesses of the graph approach:

- **ART_670 and complex real fixtures:** The existing engine's targeted
  heuristics (clash boundary penalty, failure zone scaling, phase 5b period
  correction) handle edge cases that a uniform probabilistic model cannot
  express without exponentially expanding the state space.
- **Large failure zones:** When 10+ consecutive pages have no OCR reading, the
  HMM assigns near-uniform probability across states. The existing engine's
  `failure_zone_cbpen_scale` handles this explicitly.
- **OCR misreads:** Single-digit substitutions (e.g., 3/8 confusion) propagate
  through Viterbi as plausible transitions. D-S cross-validation catches these
  by fusing neighbor evidence.

## Why Not Adopted

The multi-phase engine with Dempster-Shafer post-validation handles real-world
OCR noise better than a pure probabilistic model. Specific advantages:

1. **Targeted heuristics** for known failure modes (failure zones, orphan
   suppression, clash boundaries) outperform generic transition probabilities.
2. **D-S evidence fusion** combines multiple independent signals (period,
   neighbor, prior) with principled uncertainty handling -- more expressive than
   a single emission/transition model.
3. **Phase 5b period correction** exploits autocorrelation structure that the
   HMM's Markov assumption (memoryless transitions) cannot capture.

## Residual Value

- **Viterbi decoder** is well-tested and could serve as a future Phase D
  (Bayesian anchor constraint -- see `project_inference_d_bayesian.md`): use
  high-confidence OCR reads as fixed anchors, then Viterbi-decode the gaps.
- **Hybrid architecture** validates that signal preprocessing + global decode
  is a viable pattern if the emission model improves.
- **Sweep infrastructure** (`sweep.py`, `params.py`) is reusable for any
  future engine variant.

## Lessons Learned

1. **Global optimal != locally robust** for noisy OCR data. Viterbi finds the
   single best path, but real fixtures need soft evidence accumulation.
2. **D-S fusion > transition probabilities** for handling contradictory
   signals. Dempster's rule of combination naturally down-weights conflicting
   evidence; HMM transitions must be tuned per-failure-mode.
3. **Domain heuristics are hard to replace.** The existing engine's
   `clash_boundary_pen`, `failure_zone_cbpen_scale`, and `anomaly_dropout`
   encode domain knowledge that took multiple sweep rounds to discover. A
   generic model cannot learn these without labeled training data.
4. **Hybrid is the right direction** but needs a richer emission model --
   possibly one that incorporates D-S mass functions directly as observation
   likelihoods.
