# Graph-Based Inference Engine — HMM + Viterbi

**Date:** 2026-03-23
**Status:** Approved
**Scope:** New isolated module for document boundary inference using Hidden Markov Model with Viterbi decoding

## Problem

The current inference engine (`core/inference.py`) uses greedy bidirectional propagation — locally optimal decisions that can miss the globally best document segmentation. Documents have irregular lengths (2–5+ pages), skipped pages, broken sequences, and isolated pages mixed together. A global optimization approach can handle this uncertainty better.

## Decision

**HMM + Viterbi** — no training data required, globally optimal decoding, directly maps to the problem structure.

Rejected alternatives:
- **Linear-Chain CRF:** Needs labeled training data we don't have
- **Factor Graphs + BP:** Over-engineered for first iteration; HMM is a special case

## Architecture

### Hidden State

Each PDF page has a hidden state `(curr, total)` representing its true position in a document:
- Valid states: `{(c, t) | 1 ≤ c ≤ t ≤ MAX_TOTAL}` — approximately 465 states for MAX_TOTAL=30
- Special `NULL` state for pages with no valid reading
- Total state space: ~466 states

### Observation

Each page produces an OCR observation: `(curr_ocr, total_ocr, confidence, method)` or `(None, None, ...)` for failed reads.

### Transition Model

Probabilities for state-to-state transitions (all sweep-tunable):

| Transition | Description | Expected range |
|-----------|-------------|----------------|
| `(c, t) → (c+1, t)` | Next page, same document | High (0.7–0.95) |
| `(c, t) → (1, t')` | New document starts | Low (0.05–0.30), distributed across totals |
| `(c, t) → (c+k, t)` | Skip within document | Low (0.01–0.10) |
| `NULL → any` | Recovery from unreadable page | Uniform, weighted by context |
| `(t, t) → (1, t')` | Complete document → new start | Boosted (boundary_bonus) |

### Emission Model

P(observation | hidden state), sweep-tunable:

| Case | Description | Probability source |
|------|-------------|--------------------|
| OCR matches state exactly | `obs=(c,t)`, state=`(c,t)` | `emit_match × f(confidence)` |
| Same total, different curr | `obs=(c',t)`, state=`(c,t)` | `emit_partial` |
| No reading | `obs=(None,None)` | `emit_null` (uniform) |
| Contradiction | Different total entirely | Low residual probability |

Confidence scaling: `f(conf) = conf^emit_conf_scale`

### Viterbi Decoding

Standard Viterbi algorithm on the HMM:
- **Complexity:** O(N × S²) where N=pages, S=states
- **For 100 pages, S=466:** ~21M operations — sub-second
- **Output:** Optimal state sequence `[(c₁,t₁), (c₂,t₂), ...]`

### Document Extraction

From the decoded state sequence, document boundaries are identified where:
1. `total` changes between consecutive pages
2. `curr` resets to 1 (or near 1 with skips)
3. `curr` of page i+1 ≤ curr of page i (regression = new doc)

Each contiguous segment with the same `total` becomes a `Document` with inferred pages filled from gaps.

## Module Structure

```
core/
  graph_inference.py      # HMM + Viterbi engine, production-ready
eval/
  graph_inference.py      # Parameterized copy for sweep (self-contained)
  graph_params.py         # Parameter space + production defaults
  graph_sweep.py          # Sweep runner (reuses scoring from sweep.py)
```

### Public API

```python
# Identical interface to existing engine
def run_pipeline(reads: list[PageRead], params: dict) -> list[Document]
```

Where `PageRead` and `Document` match the existing dataclasses.

## Parameters (sweep-tunable)

| Parameter | Role | Candidate values |
|-----------|------|-----------------|
| `trans_continue` | P(next page same doc) | [0.70, 0.80, 0.85, 0.90, 0.95] |
| `trans_new_doc` | P(new document starts) | [0.05, 0.10, 0.15, 0.20, 0.30] |
| `trans_skip` | P(page skip within doc) | [0.01, 0.03, 0.05, 0.10] |
| `emit_match` | P(OCR correct given state) | [0.60, 0.70, 0.80, 0.90, 0.95] |
| `emit_conf_scale` | Confidence exponent | [0.5, 1.0, 1.5, 2.0] |
| `emit_partial` | P(same total, wrong curr) | [0.05, 0.10, 0.15, 0.20] |
| `emit_null` | P(no reading) | [0.1, 0.2, 0.3, 0.5] |
| `max_total` | Max pages per document | [15, 20, 25, 30] |
| `boundary_bonus` | Bonus for curr=1 after complete doc | [1.0, 2.0, 3.0, 5.0] |
| `period_prior` | Weight of modal total as prior | [0.0, 0.1, 0.2, 0.3, 0.5] |

Total: 10 parameters, ~2M combinations → LHS sampling + beam search

## Integration Points

### Current pipeline (`core/pipeline.py` lines 294–324):
```python
# Currently:
period = inference._detect_period(reads_clean, ...)
inference._infer_missing(reads_clean, period, ...)
docs = inference._build_documents(reads_clean, ...)

# Future swap:
docs = graph_inference.run_pipeline(reads_clean, params)
```

### Eval harness:
New `eval/graph_sweep.py` reuses `score_config()` from `eval/sweep.py` — just swaps which `run_pipeline` is called.

## Testing Strategy

1. **Unit tests:** Verify Viterbi on hand-crafted small sequences (3–5 pages)
2. **Eval harness:** Run graph_sweep against existing fixtures, compare composite scores
3. **Manual verification:** User tests with short real PDFs for quick validation

## Constraints

- No external dependencies (pure Python, numpy optional for performance)
- Must handle PDFs up to 200 pages without timeout
- Same `Document` output format as current engine
- No modification to existing `core/inference.py`
