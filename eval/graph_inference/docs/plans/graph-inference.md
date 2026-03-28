# Graph Inference (HMM + Viterbi) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an isolated HMM+Viterbi inference module that decodes globally optimal document boundaries from raw OCR page reads, compatible with the existing eval/sweep harness.

**Architecture:** Each PDF page is an observation of a hidden state `(curr, total)`. A Viterbi decoder finds the globally optimal state sequence, then document boundaries are extracted from state transitions. The module is self-contained in `eval/` (no imports from `core/`), following the established pattern of `eval/inference.py`.

**Tech Stack:** Pure Python + numpy (already a dependency). No new dependencies.

**Note:** `core/graph_inference.py` (production copy) is deferred until after sweep tuning identifies good default parameters. This plan covers only the `eval/` module for experimentation.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `eval/graph_inference.py` | HMM engine: state space, emission, transition, Viterbi, document extraction, `run_pipeline()` |
| `eval/graph_params.py` | Parameter space (`GRAPH_PARAM_SPACE`) + defaults (`GRAPH_DEFAULT_PARAMS`) |
| `eval/graph_sweep.py` | Sweep runner — reuses `score_config` logic from `eval/sweep.py` with graph engine |
| `eval/tests/test_graph_inference.py` | Unit + integration tests for the graph engine |

---

## Chunk 1: State Space, Emission Model, and Data Types

### Task 1: Data types and state space builder

**Files:**
- Create: `eval/graph_inference.py`
- Create: `eval/tests/test_graph_inference.py`

- [ ] **Step 1: Write failing test for state space builder**

```python
# eval/tests/test_graph_inference.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from eval.graph_inference import build_state_space, PageRead, Document


def test_state_space_max_total_3():
    """max_total=3 → states: (1,1),(1,2),(2,2),(1,3),(2,3),(3,3) + NULL."""
    states, idx = build_state_space(max_total=3)
    # 1+2+3 = 6 real states + NULL
    assert len(states) == 7
    assert states[0] is None  # NULL state at index 0
    assert (1, 1) in states
    assert (3, 3) in states
    assert idx[(1, 1)] >= 1
    assert idx[None] == 0


def test_state_space_max_total_30():
    """max_total=30 → 30*31/2 = 465 real states + NULL = 466."""
    states, idx = build_state_space(max_total=30)
    assert len(states) == 466
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd a:/PROJECTS/PDFoverseer && python -m pytest eval/tests/test_graph_inference.py::test_state_space_max_total_3 -v`
Expected: FAIL — `ImportError: cannot import name 'build_state_space'`

- [ ] **Step 3: Write data types and state space builder**

```python
# eval/graph_inference.py
"""
Graph-based inference engine using Hidden Markov Model + Viterbi decoding.
Self-contained — does NOT import from core/. Follows eval/inference.py pattern.

Public API:
    run_pipeline(reads: list[PageRead], params: dict) -> list[Document]

params keys (all required):
    trans_continue, trans_new_doc, trans_skip     — Transition model
    emit_match, emit_conf_scale, emit_partial,    — Emission model
      emit_null
    max_total                                     — State space size
    boundary_bonus                                — Complete-doc transition boost
    period_prior                                  — Modal total prior weight
"""
from __future__ import annotations

import copy
import math
from collections import Counter
from dataclasses import dataclass, field

import numpy as np


@dataclass
class PageRead:
    pdf_page:   int
    curr:       int | None
    total:      int | None
    method:     str
    confidence: float
    _ph1_orphan_candidate: bool = field(default=False, repr=False, compare=False)


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


def build_state_space(max_total: int) -> tuple[list, dict]:
    """Build list of states and index lookup.

    Returns:
        states: list where states[0] = None (NULL), states[1..] = (curr, total) tuples
        idx: dict mapping state -> index (None -> 0, (c,t) -> i)
    """
    states: list = [None]  # index 0 = NULL
    idx = {None: 0}
    for t in range(1, max_total + 1):
        for c in range(1, t + 1):
            idx[(c, t)] = len(states)
            states.append((c, t))
    return states, idx
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd a:/PROJECTS/PDFoverseer && python -m pytest eval/tests/test_graph_inference.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add eval/graph_inference.py eval/tests/test_graph_inference.py
git commit -m "feat(graph): state space builder + data types for HMM engine"
```

---

### Task 2: Emission model

**Files:**
- Modify: `eval/graph_inference.py`
- Modify: `eval/tests/test_graph_inference.py`

- [ ] **Step 1: Write failing tests for emission**

```python
# Add to eval/tests/test_graph_inference.py
from eval.graph_inference import compute_log_emission
import math


def test_emit_exact_match_high_conf():
    """Exact OCR match with high confidence → highest log probability."""
    params = {
        "emit_match": 0.90, "emit_conf_scale": 1.0,
        "emit_partial": 0.10, "emit_null": 0.3, "max_total": 5,
    }
    read = PageRead(0, curr=2, total=3, method="direct", confidence=0.95)
    # State (2,3) should get highest emission
    log_p_match = compute_log_emission(read, (2, 3), params)
    log_p_partial = compute_log_emission(read, (1, 3), params)  # same total, diff curr
    log_p_diff = compute_log_emission(read, (2, 5), params)     # different total
    assert log_p_match > log_p_partial
    assert log_p_partial > log_p_diff


def test_emit_null_observation():
    """Failed read → uniform-ish emission (no information)."""
    params = {
        "emit_match": 0.90, "emit_conf_scale": 1.0,
        "emit_partial": 0.10, "emit_null": 0.3, "max_total": 5,
    }
    read = PageRead(0, curr=None, total=None, method="failed", confidence=0.0)
    log_p_a = compute_log_emission(read, (1, 3), params)
    log_p_b = compute_log_emission(read, (2, 5), params)
    # Both should be equal (uniform for null reads)
    assert abs(log_p_a - log_p_b) < 1e-9


def test_emit_null_state():
    """NULL hidden state with any observation."""
    params = {
        "emit_match": 0.90, "emit_conf_scale": 1.0,
        "emit_partial": 0.10, "emit_null": 0.3, "max_total": 5,
    }
    read = PageRead(0, curr=2, total=3, method="direct", confidence=0.95)
    log_p = compute_log_emission(read, None, params)
    assert math.isfinite(log_p)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd a:/PROJECTS/PDFoverseer && python -m pytest eval/tests/test_graph_inference.py::test_emit_exact_match_high_conf -v`
Expected: FAIL — `ImportError: cannot import name 'compute_log_emission'`

- [ ] **Step 3: Implement emission model**

Add to `eval/graph_inference.py`:

```python
_LOG_FLOOR = -20.0  # log-probability floor (≈ e^-20 ≈ 2e-9)


def compute_log_emission(read: PageRead, state, params: dict) -> float:
    """Compute log P(observation | hidden state).

    Cases:
    - NULL state: low flat probability
    - NULL observation (failed read): uniform across all states
    - Exact match: emit_match * confidence^emit_conf_scale
    - Partial match (same total): emit_partial
    - Contradiction (different total): residual
    """
    # NULL hidden state — low probability regardless of observation
    if state is None:
        return _LOG_FLOOR

    c_state, t_state = state
    c_obs, t_obs = read.curr, read.total
    conf = read.confidence

    # No observation — uninformative, uniform
    if c_obs is None or t_obs is None:
        return math.log(params["emit_null"])

    emit_conf_scale = params["emit_conf_scale"]
    scaled_conf = max(conf, 0.01) ** emit_conf_scale

    # Exact match
    if c_obs == c_state and t_obs == t_state:
        return math.log(max(params["emit_match"] * scaled_conf, 1e-15))

    # Partial match — same total, different curr (OCR misread curr digit)
    if t_obs == t_state:
        return math.log(max(params["emit_partial"] * scaled_conf, 1e-15))

    # Contradiction — different total entirely
    residual = max(1.0 - params["emit_match"] - params["emit_partial"], 0.01)
    n_other_totals = max(params["max_total"] - 1, 1)
    return math.log(max(residual / n_other_totals * scaled_conf, 1e-15))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd a:/PROJECTS/PDFoverseer && python -m pytest eval/tests/test_graph_inference.py -v`
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add eval/graph_inference.py eval/tests/test_graph_inference.py
git commit -m "feat(graph): emission model for HMM — match/partial/null/contradiction"
```

---

## Chunk 2: Transition Model and Viterbi Decoder

### Task 3: Transition model

**Files:**
- Modify: `eval/graph_inference.py`
- Modify: `eval/tests/test_graph_inference.py`

- [ ] **Step 1: Write failing tests for transition**

```python
# Add to eval/tests/test_graph_inference.py
from eval.graph_inference import compute_log_transition


def test_trans_continue_highest():
    """(1,3) → (2,3) should have highest probability (continue doc)."""
    params = {
        "trans_continue": 0.85, "trans_new_doc": 0.10, "trans_skip": 0.03,
        "max_total": 5, "boundary_bonus": 2.0, "period_prior": 0.0,
    }
    states, idx = build_state_space(5)
    modal_total = None
    log_cont = compute_log_transition((1, 3), (2, 3), params, modal_total)
    log_new = compute_log_transition((1, 3), (1, 2), params, modal_total)
    assert log_cont > log_new


def test_trans_complete_doc_bonus():
    """After complete doc (3,3), transition to (1,t') gets boundary_bonus."""
    params = {
        "trans_continue": 0.85, "trans_new_doc": 0.10, "trans_skip": 0.03,
        "max_total": 5, "boundary_bonus": 3.0, "period_prior": 0.0,
    }
    modal_total = None
    # From (3,3) — document complete → new doc should be boosted
    log_new_after_complete = compute_log_transition((3, 3), (1, 2), params, modal_total)
    # From (1,3) — mid-document → new doc should NOT be boosted
    log_new_mid_doc = compute_log_transition((1, 3), (1, 2), params, modal_total)
    assert log_new_after_complete > log_new_mid_doc


def test_trans_period_prior():
    """When modal_total is known, new docs with that total get boosted."""
    params = {
        "trans_continue": 0.85, "trans_new_doc": 0.10, "trans_skip": 0.03,
        "max_total": 5, "boundary_bonus": 2.0, "period_prior": 0.4,
    }
    modal_total = 3
    log_to_modal = compute_log_transition((2, 2), (1, 3), params, modal_total)
    log_to_other = compute_log_transition((2, 2), (1, 5), params, modal_total)
    assert log_to_modal > log_to_other
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd a:/PROJECTS/PDFoverseer && python -m pytest eval/tests/test_graph_inference.py::test_trans_continue_highest -v`
Expected: FAIL — `ImportError: cannot import name 'compute_log_transition'`

- [ ] **Step 3: Implement transition model**

Add to `eval/graph_inference.py`:

```python
def _raw_transition_weight(state_from, state_to, params: dict,
                            modal_total: int | None) -> float:
    """Compute unnormalized transition weight (will be row-normalized later).

    Transition types:
    - Continue:  (c, t) → (c+1, t)          — trans_continue
    - Skip:      (c, t) → (c+k, t), k>1     — trans_skip / (t - c - 1)
    - New doc:   any → (1, t')               — trans_new_doc / max_total
    - Complete→New: (t, t) → (1, t')         — boosted by boundary_bonus
    - Period prior: → (1, modal_total)       — boosted by period_prior
    - NULL transitions: near-zero weight
    """
    # Transitions involving NULL
    if state_from is None or state_to is None:
        return 1e-10

    c_from, t_from = state_from
    c_to, t_to = state_to

    max_total = params["max_total"]

    # Continue in same document: (c, t) → (c+1, t)
    if t_to == t_from and c_to == c_from + 1:
        return params["trans_continue"]

    # Skip within same document: (c, t) → (c+k, t), k > 1
    if t_to == t_from and c_to > c_from + 1:
        remaining = t_from - c_from - 1  # possible skip positions
        if remaining <= 0:
            return 1e-10
        return params["trans_skip"] / remaining

    # New document: any → (1, t')
    if c_to == 1:
        base = params["trans_new_doc"] / max_total

        # Boundary bonus: complete doc → new doc
        if c_from == t_from:
            base *= params["boundary_bonus"]

        # Period prior: boost if target total matches modal total
        if modal_total is not None and t_to == modal_total:
            base = base * (1.0 - params["period_prior"]) + params["period_prior"]

        return max(base, 1e-15)

    # All other transitions (invalid — e.g., total change without curr=1)
    return 1e-10
```

**Note:** Raw weights are normalized per-row inside `_build_log_transition_matrix` so each row sums to 1.0. This ensures a proper HMM. The `compute_log_transition` function below is a convenience for tests only — the Viterbi loop uses the precomputed matrix.

```python
def compute_log_transition(state_from, state_to, params: dict,
                           modal_total: int | None) -> float:
    """Log transition weight (unnormalized — for unit tests only).
    The actual Viterbi uses the row-normalized matrix from _build_log_transition_matrix.
    """
    w = _raw_transition_weight(state_from, state_to, params, modal_total)
    return math.log(max(w, 1e-15))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd a:/PROJECTS/PDFoverseer && python -m pytest eval/tests/test_graph_inference.py -v`
Expected: 8 PASSED

- [ ] **Step 5: Commit**

```bash
git add eval/graph_inference.py eval/tests/test_graph_inference.py
git commit -m "feat(graph): transition model — continue/skip/new-doc/boundary-bonus/period-prior"
```

---

### Task 4: Viterbi decoder

**Files:**
- Modify: `eval/graph_inference.py`
- Modify: `eval/tests/test_graph_inference.py`

- [ ] **Step 1: Write failing test for Viterbi**

```python
# Add to eval/tests/test_graph_inference.py
from eval.graph_inference import viterbi_decode


def test_viterbi_clean_two_docs():
    """Two clean 2-page docs → Viterbi should decode perfectly."""
    reads = [
        PageRead(0, 1, 2, "direct", 0.95),
        PageRead(1, 2, 2, "direct", 0.92),
        PageRead(2, 1, 2, "direct", 0.91),
        PageRead(3, 2, 2, "direct", 0.90),
    ]
    params = {
        "trans_continue": 0.85, "trans_new_doc": 0.10, "trans_skip": 0.03,
        "emit_match": 0.90, "emit_conf_scale": 1.0, "emit_partial": 0.10,
        "emit_null": 0.3, "max_total": 5, "boundary_bonus": 2.0,
        "period_prior": 0.0,
    }
    path = viterbi_decode(reads, params)
    assert len(path) == 4
    assert path[0] == (1, 2)
    assert path[1] == (2, 2)
    assert path[2] == (1, 2)
    assert path[3] == (2, 2)


def test_viterbi_missing_middle():
    """3-page doc with failed middle read → should infer (2, 3)."""
    reads = [
        PageRead(0, 1, 3, "direct", 0.95),
        PageRead(1, None, None, "failed", 0.0),
        PageRead(2, 3, 3, "direct", 0.90),
    ]
    params = {
        "trans_continue": 0.85, "trans_new_doc": 0.10, "trans_skip": 0.03,
        "emit_match": 0.90, "emit_conf_scale": 1.0, "emit_partial": 0.10,
        "emit_null": 0.3, "max_total": 5, "boundary_bonus": 2.0,
        "period_prior": 0.0,
    }
    path = viterbi_decode(reads, params)
    assert path[0] == (1, 3)
    assert path[1] == (2, 3)  # inferred from context
    assert path[2] == (3, 3)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd a:/PROJECTS/PDFoverseer && python -m pytest eval/tests/test_graph_inference.py::test_viterbi_clean_two_docs -v`
Expected: FAIL — `ImportError: cannot import name 'viterbi_decode'`

- [ ] **Step 3: Implement Viterbi decoder**

Add to `eval/graph_inference.py`:

```python
def _detect_modal_total(reads: list[PageRead]) -> int | None:
    """Find most common declared total from confirmed reads."""
    totals = [r.total for r in reads
              if r.total is not None and r.method not in ("failed", "excluded")]
    if not totals:
        return None
    return Counter(totals).most_common(1)[0][0]


def viterbi_decode(reads: list[PageRead], params: dict) -> list:
    """Run Viterbi algorithm on the HMM.

    Args:
        reads: list of PageRead observations (one per PDF page)
        params: dict with all HMM parameters

    Returns:
        path: list of states, one per page. Each state is (curr, total) or None.
    """
    n = len(reads)
    if n == 0:
        return []

    max_total = int(params["max_total"])
    states, state_idx = build_state_space(max_total)
    S = len(states)
    modal_total = _detect_modal_total(reads)

    # Log-probability matrices
    # V[t, s] = log P(best path ending in state s at time t)
    V = np.full((n, S), -np.inf, dtype=np.float64)
    backptr = np.zeros((n, S), dtype=np.int32)

    # Initialization (t=0): uniform prior over non-NULL states, weighted by emission
    log_prior = math.log(1.0 / (S - 1))  # exclude NULL
    for s in range(1, S):  # skip NULL for init
        V[0, s] = log_prior + compute_log_emission(reads[0], states[s], params)
    V[0, 0] = _LOG_FLOOR + compute_log_emission(reads[0], None, params)

    # Recursion
    for t in range(1, n):
        obs = reads[t]
        # Precompute emissions for all states at time t
        log_emit = np.array([compute_log_emission(obs, states[s], params)
                             for s in range(S)])

        for s_to in range(S):
            best_score = -np.inf
            best_prev = 0
            state_to = states[s_to]
            for s_from in range(S):
                state_from = states[s_from]
                log_tr = compute_log_transition(state_from, state_to, params,
                                                modal_total)
                score = V[t - 1, s_from] + log_tr
                if score > best_score:
                    best_score = score
                    best_prev = s_from
            V[t, s_to] = best_score + log_emit[s_to]
            backptr[t, s_to] = best_prev

    # Backtrace
    path_idx = [0] * n
    path_idx[n - 1] = int(np.argmax(V[n - 1]))
    for t in range(n - 2, -1, -1):
        path_idx[t] = int(backptr[t + 1, path_idx[t + 1]])

    return [states[i] for i in path_idx]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd a:/PROJECTS/PDFoverseer && python -m pytest eval/tests/test_graph_inference.py -v`
Expected: 10 PASSED

- [ ] **Step 5: Commit**

```bash
git add eval/graph_inference.py eval/tests/test_graph_inference.py
git commit -m "feat(graph): Viterbi decoder with numpy — O(N×S²) dynamic programming"
```

---

## Chunk 3: Document Extraction and run_pipeline

### Task 5: Document extraction from state path

**Files:**
- Modify: `eval/graph_inference.py`
- Modify: `eval/tests/test_graph_inference.py`

- [ ] **Step 1: Write failing tests for document extraction**

```python
# Add to eval/tests/test_graph_inference.py
from eval.graph_inference import extract_documents


def test_extract_two_complete_docs():
    """Two 2-page docs from Viterbi path."""
    reads = [
        PageRead(0, 1, 2, "direct", 0.95),
        PageRead(1, 2, 2, "direct", 0.92),
        PageRead(2, 1, 2, "direct", 0.91),
        PageRead(3, 2, 2, "direct", 0.90),
    ]
    path = [(1, 2), (2, 2), (1, 2), (2, 2)]
    docs = extract_documents(reads, path)
    assert len(docs) == 2
    assert docs[0].declared_total == 2
    assert docs[0].is_complete
    assert docs[1].start_pdf_page == 2


def test_extract_with_inferred_page():
    """3-page doc where middle page was failed → inferred."""
    reads = [
        PageRead(0, 1, 3, "direct", 0.95),
        PageRead(1, None, None, "failed", 0.0),
        PageRead(2, 3, 3, "direct", 0.90),
    ]
    path = [(1, 3), (2, 3), (3, 3)]
    docs = extract_documents(reads, path)
    assert len(docs) == 1
    assert docs[0].declared_total == 3
    assert len(docs[0].pages) == 2        # pages 0 and 2 had OCR
    assert len(docs[0].inferred_pages) == 1  # page 1 was inferred
    assert docs[0].is_complete


def test_extract_with_skip():
    """Doc with a skip: (1,3) → (3,3) — page 2 missing from observations."""
    reads = [
        PageRead(0, 1, 3, "direct", 0.95),
        PageRead(1, 3, 3, "direct", 0.90),
    ]
    path = [(1, 3), (3, 3)]
    docs = extract_documents(reads, path)
    assert len(docs) == 1
    assert docs[0].declared_total == 3
    assert not docs[0].sequence_ok  # gap in sequence
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd a:/PROJECTS/PDFoverseer && python -m pytest eval/tests/test_graph_inference.py::test_extract_two_complete_docs -v`
Expected: FAIL — `ImportError: cannot import name 'extract_documents'`

- [ ] **Step 3: Implement document extraction**

Add to `eval/graph_inference.py`:

```python
def extract_documents(reads: list[PageRead], path: list) -> list[Document]:
    """Extract Document objects from Viterbi-decoded state path.

    A new document starts when:
    - total changes between consecutive pages
    - curr resets (curr_i+1 <= curr_i, unless it's a valid skip)
    - curr_i+1 == 1

    Pages where the OCR reading was None/failed but the state was assigned
    are marked as inferred.
    """
    if not path:
        return []

    docs: list[Document] = []
    doc_start = 0

    for i in range(1, len(path)):
        prev_state = path[i - 1]
        curr_state = path[i]

        # NULL states are boundaries
        if prev_state is None or curr_state is None:
            if prev_state is not None:
                docs.append(_make_doc(len(docs), reads, path, doc_start, i))
            doc_start = i
            continue

        c_prev, t_prev = prev_state
        c_curr, t_curr = curr_state

        # New document boundary
        is_new_doc = (
            t_curr != t_prev           # total changed
            or c_curr == 1             # explicit restart
            or c_curr <= c_prev        # regression (not a skip forward)
        )

        if is_new_doc and not (t_curr == t_prev and c_curr == c_prev + 1):
            # But don't split on valid continuation
            docs.append(_make_doc(len(docs), reads, path, doc_start, i))
            doc_start = i

    # Last document
    if doc_start < len(path) and path[doc_start] is not None:
        docs.append(_make_doc(len(docs), reads, path, doc_start, len(path)))

    return docs


def _make_doc(index: int, reads: list[PageRead], path: list,
              start: int, end: int) -> Document:
    """Build a Document from a segment of the decoded path."""
    segment_states = path[start:end]
    segment_reads = reads[start:end]

    # Declared total = total from the state (should be consistent)
    totals = [s[1] for s in segment_states if s is not None]
    declared_total = Counter(totals).most_common(1)[0][0] if totals else 1

    pages = []
    inferred_pages = []
    currs_seen = []

    for j, (rd, st) in enumerate(zip(segment_reads, segment_states)):
        pdf_page = rd.pdf_page
        if rd.curr is not None and rd.method not in ("failed", "excluded"):
            pages.append(pdf_page)
        else:
            inferred_pages.append(pdf_page)
        if st is not None:
            currs_seen.append(st[0])

    # Check sequence continuity
    sequence_ok = True
    for j in range(1, len(currs_seen)):
        if currs_seen[j] != currs_seen[j - 1] + 1:
            sequence_ok = False
            break

    return Document(
        index=index,
        start_pdf_page=reads[start].pdf_page,
        declared_total=declared_total,
        pages=pages,
        inferred_pages=inferred_pages,
        sequence_ok=sequence_ok,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd a:/PROJECTS/PDFoverseer && python -m pytest eval/tests/test_graph_inference.py -v`
Expected: 13 PASSED

- [ ] **Step 5: Commit**

```bash
git add eval/graph_inference.py eval/tests/test_graph_inference.py
git commit -m "feat(graph): document extraction from Viterbi path — boundaries/inferred/sequence"
```

---

### Task 6: run_pipeline integration + end-to-end tests

**Files:**
- Modify: `eval/graph_inference.py`
- Modify: `eval/tests/test_graph_inference.py`

- [ ] **Step 1: Write failing end-to-end tests**

```python
# Add to eval/tests/test_graph_inference.py
from eval.graph_inference import run_pipeline

BASIC_PARAMS = {
    "trans_continue": 0.85, "trans_new_doc": 0.10, "trans_skip": 0.03,
    "emit_match": 0.90, "emit_conf_scale": 1.0, "emit_partial": 0.10,
    "emit_null": 0.3, "max_total": 10, "boundary_bonus": 2.0,
    "period_prior": 0.0,
}


def test_e2e_simple_two_docs():
    """End-to-end: two clean 2-page docs."""
    reads = [
        PageRead(0, 1, 2, "direct", 0.95), PageRead(1, 2, 2, "direct", 0.92),
        PageRead(2, 1, 2, "direct", 0.91), PageRead(3, 2, 2, "direct", 0.90),
    ]
    docs = run_pipeline(reads, BASIC_PARAMS)
    assert len(docs) == 2
    assert all(d.is_complete for d in docs)


def test_e2e_infer_missing():
    """End-to-end: infer missing middle page."""
    reads = [
        PageRead(0, 1, 3, "direct", 0.95),
        PageRead(1, None, None, "failed", 0.0),
        PageRead(2, 3, 3, "direct", 0.90),
    ]
    docs = run_pipeline(reads, BASIC_PARAMS)
    assert len(docs) == 1
    assert docs[0].declared_total == 3
    assert docs[0].found_total == 3


def test_e2e_mixed_sizes():
    """End-to-end: mixed 1-page and 3-page docs."""
    reads = [
        PageRead(0, 1, 1, "direct", 0.90),
        PageRead(1, 1, 3, "direct", 0.88),
        PageRead(2, 2, 3, "direct", 0.85),
        PageRead(3, 3, 3, "direct", 0.87),
        PageRead(4, 1, 1, "direct", 0.91),
    ]
    docs = run_pipeline(reads, BASIC_PARAMS)
    assert len(docs) == 3  # 1-page + 3-page + 1-page


def test_e2e_does_not_mutate_input():
    """run_pipeline must not mutate the input reads list."""
    reads = [PageRead(0, 1, 2, "direct", 0.95), PageRead(1, 2, 2, "direct", 0.92)]
    original_conf = reads[0].confidence
    run_pipeline(reads, BASIC_PARAMS)
    assert reads[0].confidence == original_conf
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd a:/PROJECTS/PDFoverseer && python -m pytest eval/tests/test_graph_inference.py::test_e2e_simple_two_docs -v`
Expected: FAIL — `ImportError: cannot import name 'run_pipeline'` (or function not defined yet)

- [ ] **Step 3: Implement run_pipeline**

Add to `eval/graph_inference.py`:

```python
def run_pipeline(reads: list[PageRead], params: dict) -> list[Document]:
    """Full graph inference pipeline: deepcopy → Viterbi → extract documents.

    Args:
        reads: list of PageRead from OCR engine
        params: dict with all HMM parameters (see module docstring)

    Returns:
        list of Document objects, compatible with eval/sweep scoring
    """
    reads = copy.deepcopy(reads)
    path = viterbi_decode(reads, params)
    docs = extract_documents(reads, path)
    return docs
```

- [ ] **Step 4: Run all tests**

Run: `cd a:/PROJECTS/PDFoverseer && python -m pytest eval/tests/test_graph_inference.py -v`
Expected: 17 PASSED

- [ ] **Step 5: Commit**

```bash
git add eval/graph_inference.py eval/tests/test_graph_inference.py
git commit -m "feat(graph): run_pipeline public API + end-to-end tests"
```

---

## Chunk 4: Sweep Integration

### Task 7: Graph parameter space

**Files:**
- Create: `eval/graph_params.py`

- [ ] **Step 1: Create parameter space file**

```python
# eval/graph_params.py
"""
Parameter search space for the graph inference engine (HMM + Viterbi).
Each key maps to a list of discrete candidate values.
GRAPH_DEFAULT_PARAMS are reasonable starting defaults (not yet sweep-tuned).
"""

GRAPH_PARAM_SPACE: dict[str, list] = {
    # Transition model
    "trans_continue":   [0.70, 0.80, 0.85, 0.90, 0.95],
    "trans_new_doc":    [0.05, 0.10, 0.15, 0.20, 0.30],
    "trans_skip":       [0.01, 0.03, 0.05, 0.10],
    # Emission model
    "emit_match":       [0.60, 0.70, 0.80, 0.90, 0.95],
    "emit_conf_scale":  [0.5, 1.0, 1.5, 2.0],
    "emit_partial":     [0.05, 0.10, 0.15, 0.20],
    "emit_null":        [0.1, 0.2, 0.3, 0.5],
    # State space
    "max_total":        [15, 20, 25, 30],
    # Boundary
    "boundary_bonus":   [1.0, 2.0, 3.0, 5.0],
    # Period prior
    "period_prior":     [0.0, 0.1, 0.2, 0.3, 0.5],
}

# Reasonable defaults (not yet tuned)
GRAPH_DEFAULT_PARAMS: dict[str, float | int] = {
    "trans_continue":   0.85,
    "trans_new_doc":    0.10,
    "trans_skip":       0.03,
    "emit_match":       0.90,
    "emit_conf_scale":  1.0,
    "emit_partial":     0.10,
    "emit_null":        0.3,
    "max_total":        20,
    "boundary_bonus":   2.0,
    "period_prior":     0.0,
}
```

- [ ] **Step 2: Commit**

```bash
git add eval/graph_params.py
git commit -m "feat(graph): parameter space and defaults for HMM sweep"
```

---

### Task 8: Graph sweep runner

**Files:**
- Create: `eval/graph_sweep.py`

- [ ] **Step 1: Write the sweep runner**

`eval/graph_sweep.py` reuses the scoring logic from `eval/sweep.py` but swaps in the graph engine.

```python
# eval/graph_sweep.py
"""
Parameter sweep for the graph inference engine (HMM + Viterbi).

Reuses the 3-pass sweep structure and scoring from eval/sweep.py,
but runs eval/graph_inference.run_pipeline instead.

Usage:
    cd a:/PROJECTS/PDFoverseer
    python eval/graph_sweep.py
    # -> writes eval/results/graph_sweep_YYYYMMDD_HHMMSS.json
"""
from __future__ import annotations
import json
import random
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.graph_inference import run_pipeline, PageRead
from eval.graph_params import GRAPH_PARAM_SPACE, GRAPH_DEFAULT_PARAMS

FIXTURES_DIR = Path("eval/fixtures")
GROUND_TRUTH_PATH = Path("eval/ground_truth.json")
RESULTS_DIR = Path("eval/results")
TOP_N = 10
LHS_SAMPLES = 500
PASS2_TOP_N = 20
BEAM_TOP_N = 5
RANDOM_SEED = 42


# -- Fixture loading ----------------------------------------------------------

def load_fixtures() -> list[dict]:
    fixtures = []
    for path in sorted(FIXTURES_DIR.rglob("*.json")):
        if "archived" in path.parts:
            continue
        data = json.loads(path.read_text())
        data["reads"] = [PageRead(**r) for r in data["reads"]]
        fixtures.append(data)
    return fixtures


def load_ground_truth() -> dict[str, dict]:
    return json.loads(GROUND_TRUTH_PATH.read_text())


# -- Scoring (mirrored from sweep.py, uses graph run_pipeline) ----------------

def score_config(params: dict, fixtures: list[dict], gt: dict[str, dict],
                 baseline_passes: set[str]) -> dict:
    doc_exact = complete_exact = inf_delta = regressions = 0
    real_doc_delta = syn_doc_delta = 0
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
            passed = (d_doc == 0)
            if d_doc == 0:
                doc_exact += 5
            else:
                real_doc_delta += d_doc
        else:
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
                 - real_doc_delta * 3
                 - syn_doc_delta
                 - inf_delta
                 - regressions * 5)
    return {
        "doc_count_exact":      doc_exact,
        "doc_count_delta":      real_doc_delta + syn_doc_delta,
        "complete_count_exact": complete_exact,
        "inferred_delta":       inf_delta,
        "regression_count":     regressions,
        "composite_score":      composite,
        "_fixture_results":     fixture_results,
    }


# -- Latin Hypercube Sample ---------------------------------------------------

def lhs_sample(n: int, seed: int = RANDOM_SEED) -> list[dict]:
    rng = random.Random(seed)
    keys = list(GRAPH_PARAM_SPACE.keys())
    indices_per_param: dict[str, list[int]] = {}
    for k, vals in GRAPH_PARAM_SPACE.items():
        m = len(vals)
        slots = [rng.randint(0, m - 1) for _ in range(n)]
        rng.shuffle(slots)
        indices_per_param[k] = slots
    configs = []
    for i in range(n):
        cfg = {k: GRAPH_PARAM_SPACE[k][indices_per_param[k][i]] for k in keys}
        configs.append(cfg)
    return configs


# -- Fine grid (adjacent step) ------------------------------------------------

def adjacent_configs(base: dict) -> list[dict]:
    configs = []
    for k, vals in GRAPH_PARAM_SPACE.items():
        idx = vals.index(base[k])
        for new_idx in [idx - 1, idx + 1]:
            if 0 <= new_idx < len(vals):
                cfg = dict(base)
                cfg[k] = vals[new_idx]
                configs.append(cfg)
    return configs


# -- Sweep runner -------------------------------------------------------------

def run_sweep(fixtures: list[dict], gt: dict) -> dict:
    SYNTHETIC_NAMES = {"ins31_gap", "undercount_chain", "ambiguous_start",
                       "noisy_period", "seq_break", "ds_conflict"}
    active_gt = {k: v for k, v in gt.items()
                 if k in SYNTHETIC_NAMES or v["doc_count"] > 0}
    active_fixtures = [fx for fx in fixtures if fx["name"] in active_gt]

    print("Scoring baseline (graph default params)...")
    baseline_result = score_config(GRAPH_DEFAULT_PARAMS, active_fixtures, active_gt, set())
    baseline_passes = {
        name for name, res in baseline_result["_fixture_results"].items()
        if res == "pass"
    }
    print(f"  baseline composite={baseline_result['composite_score']} "
          f"doc_exact={baseline_result['doc_count_exact']} "
          f"passes={len(baseline_passes)}/{len(active_fixtures)}")

    def run_configs(configs: list[dict], label: str) -> list[tuple[dict, dict]]:
        results = []
        for i, cfg in enumerate(configs):
            s = score_config(cfg, active_fixtures, active_gt, baseline_passes)
            results.append((cfg, s))
            if (i + 1) % 50 == 0:
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

    top_configs = []
    for rank, (cfg, scores) in enumerate(ranked, 1):
        top_configs.append({
            "rank": rank,
            "params": cfg,
            "scores": {k: v for k, v in scores.items() if not k.startswith("_")},
            "fixture_breakdown": scores["_fixture_results"],
        })

    baseline_summary = {k: v for k, v in baseline_result.items() if not k.startswith("_")}
    baseline_summary["fixture_breakdown"] = baseline_result["_fixture_results"]

    return {
        "engine": "graph-hmm-viterbi",
        "run_at": datetime.now().isoformat(),
        "fixtures_count": len(active_fixtures),
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

    out_path = RESULTS_DIR / f"graph_sweep_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(f"\nResults saved to {out_path}")
    if result["top_configs"]:
        print(f"Top config: composite={result['top_configs'][0]['scores']['composite_score']}"
              f" regressions={result['top_configs'][0]['scores']['regression_count']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add eval/graph_sweep.py
git commit -m "feat(graph): sweep runner — 3-pass LHS+grid+beam with graph engine"
```

---

### Task 9: Smoke test with existing fixtures

**Files:**
- Modify: `eval/tests/test_graph_inference.py`

- [ ] **Step 1: Write integration test that loads a real fixture**

```python
# Add to eval/tests/test_graph_inference.py
import json
from pathlib import Path


def test_real_fixture_no_crash():
    """Smoke test: graph engine runs on a real fixture without errors."""
    fixture_path = Path("eval/fixtures/real/CH_9.json")
    if not fixture_path.exists():
        import pytest
        pytest.skip("CH_9.json fixture not found")

    data = json.loads(fixture_path.read_text())
    reads = [PageRead(**r) for r in data["reads"]]
    docs = run_pipeline(reads, BASIC_PARAMS)

    assert len(docs) >= 1
    assert all(isinstance(d, Document) for d in docs)
    # Every page should be assigned to exactly one document
    all_pages = set()
    for d in docs:
        for p in d.pages + d.inferred_pages:
            assert p not in all_pages, f"Page {p} assigned to multiple docs"
            all_pages.add(p)


def test_synthetic_fixture_no_crash():
    """Smoke test: graph engine runs on a synthetic fixture."""
    fixture_path = Path("eval/fixtures/synthetic/clean_period2.json")
    if not fixture_path.exists():
        import pytest
        pytest.skip("clean_period2.json fixture not found")

    data = json.loads(fixture_path.read_text())
    reads = [PageRead(**r) for r in data["reads"]]
    docs = run_pipeline(reads, BASIC_PARAMS)
    assert len(docs) >= 1
```

- [ ] **Step 2: Run all tests including fixtures**

Run: `cd a:/PROJECTS/PDFoverseer && python -m pytest eval/tests/test_graph_inference.py -v`
Expected: All PASSED (19 tests)

- [ ] **Step 3: Commit**

```bash
git add eval/tests/test_graph_inference.py
git commit -m "test(graph): smoke tests with real + synthetic fixtures"
```

---

### Task 10: Performance optimization — vectorized Viterbi inner loop

The naive Python loop over S×S states will be slow for `max_total=30` (466² ≈ 217k iterations per page). This task pre-computes the transition matrix as a numpy array for vectorized max operations.

**Files:**
- Modify: `eval/graph_inference.py`

- [ ] **Step 1: Run benchmark on a real fixture to measure baseline**

Run: `cd a:/PROJECTS/PDFoverseer && python -c "
import json, time
from eval.graph_inference import run_pipeline, PageRead

data = json.loads(open('eval/fixtures/real/CH_9.json').read())
reads = [PageRead(**r) for r in data['reads']]
params = {'trans_continue':0.85,'trans_new_doc':0.10,'trans_skip':0.03,'emit_match':0.90,'emit_conf_scale':1.0,'emit_partial':0.10,'emit_null':0.3,'max_total':20,'boundary_bonus':2.0,'period_prior':0.0}
t0 = time.perf_counter()
docs = run_pipeline(reads, params)
t1 = time.perf_counter()
print(f'{len(reads)} pages, {len(docs)} docs, {t1-t0:.2f}s')
"`

- [ ] **Step 2: Refactor Viterbi to precompute log-transition matrix**

Replace the `viterbi_decode` function with a version that builds the S×S log-transition matrix once, then uses numpy vectorized operations:

```python
def _build_log_transition_matrix(states: list, params: dict,
                                  modal_total: int | None) -> np.ndarray:
    """Precompute S×S log-transition matrix with row normalization.

    Raw weights are computed per-pair, then each row is normalized to sum to 1.0
    before taking the log. This ensures a proper probability distribution.
    """
    S = len(states)
    raw = np.zeros((S, S), dtype=np.float64)
    for i in range(S):
        for j in range(S):
            raw[i, j] = _raw_transition_weight(
                states[i], states[j], params, modal_total)
    # Row-normalize
    row_sums = raw.sum(axis=1, keepdims=True)
    row_sums = np.maximum(row_sums, 1e-15)  # avoid division by zero
    raw /= row_sums
    return np.log(np.maximum(raw, 1e-15))


def viterbi_decode(reads: list[PageRead], params: dict) -> list:
    """Viterbi with precomputed transition matrix + vectorized numpy ops."""
    n = len(reads)
    if n == 0:
        return []

    max_total = int(params["max_total"])
    states, state_idx = build_state_space(max_total)
    S = len(states)
    modal_total = _detect_modal_total(reads)

    # Precompute transition matrix (S×S)
    log_trans = _build_log_transition_matrix(states, params, modal_total)

    # V[t, s] = best log-prob ending in state s at time t
    V = np.full((n, S), -np.inf, dtype=np.float64)
    backptr = np.zeros((n, S), dtype=np.int32)

    # Init
    log_prior = math.log(1.0 / (S - 1))
    log_emit_0 = np.array([compute_log_emission(reads[0], states[s], params)
                           for s in range(S)])
    V[0, 1:] = log_prior + log_emit_0[1:]
    V[0, 0] = _LOG_FLOOR + log_emit_0[0]

    # Recursion — vectorized inner loop
    for t in range(1, n):
        log_emit_t = np.array([compute_log_emission(reads[t], states[s], params)
                               for s in range(S)])
        # scores[i, j] = V[t-1, i] + log_trans[i, j]
        scores = V[t - 1, :, np.newaxis] + log_trans  # shape (S, S)
        backptr[t] = np.argmax(scores, axis=0)         # best prev for each state
        V[t] = np.max(scores, axis=0) + log_emit_t

    # Backtrace
    path_idx = [0] * n
    path_idx[n - 1] = int(np.argmax(V[n - 1]))
    for t in range(n - 2, -1, -1):
        path_idx[t] = int(backptr[t + 1, path_idx[t + 1]])

    return [states[i] for i in path_idx]
```

- [ ] **Step 3: Run all tests to verify nothing broke**

Run: `cd a:/PROJECTS/PDFoverseer && python -m pytest eval/tests/test_graph_inference.py -v`
Expected: All PASSED

- [ ] **Step 4: Run benchmark again and compare**

Same benchmark command as Step 1. Should be significantly faster (target: <2s for ~50 pages with max_total=20).

- [ ] **Step 5: Commit**

```bash
git add eval/graph_inference.py
git commit -m "perf(graph): vectorized Viterbi inner loop with numpy broadcasting"
```

---

### Task 11: First sweep run

**Files:** (no new files — execution only)

- [ ] **Step 1: Run the graph sweep**

Run: `cd a:/PROJECTS/PDFoverseer && python eval/graph_sweep.py`

This will take several minutes. Watch output for:
- Baseline composite score
- Pass 1/2/3 progress
- Top config composite score and regressions

- [ ] **Step 2: Inspect results**

Run: `cd a:/PROJECTS/PDFoverseer && python -c "
import json, glob
files = sorted(glob.glob('eval/results/graph_sweep_*.json'))
if files:
    data = json.loads(open(files[-1]).read())
    print(f'Configs tested: {data[\"total_configs_tested\"]}')
    print(f'Baseline: {data[\"baseline\"][\"composite_score\"]}')
    if data['top_configs']:
        top = data['top_configs'][0]
        print(f'Top: composite={top[\"scores\"][\"composite_score\"]} regressions={top[\"scores\"][\"regression_count\"]}')
        print(f'Params: {json.dumps(top[\"params\"], indent=2)}')
"`

- [ ] **Step 3: Document results in a commit message**

```bash
git add eval/results/
git commit -m "data(graph): first sweep results — graph HMM baseline"
```

---

### Task 12: Edge case tests + 200-page performance validation

**Files:**
- Modify: `eval/tests/test_graph_inference.py`

- [ ] **Step 1: Write edge case tests**

```python
# Add to eval/tests/test_graph_inference.py
import time


def test_e2e_single_page():
    """Single-page PDF → one document."""
    reads = [PageRead(0, 1, 1, "direct", 0.90)]
    docs = run_pipeline(reads, BASIC_PARAMS)
    assert len(docs) == 1
    assert docs[0].declared_total == 1


def test_e2e_all_failed():
    """All OCR failed → should still return without error."""
    reads = [
        PageRead(i, None, None, "failed", 0.0)
        for i in range(5)
    ]
    docs = run_pipeline(reads, BASIC_PARAMS)
    # Should not crash; exact doc count depends on model behavior
    assert isinstance(docs, list)


def test_e2e_empty_input():
    """Empty reads → empty docs."""
    docs = run_pipeline([], BASIC_PARAMS)
    assert docs == []


def test_performance_200_pages():
    """Spec constraint: must handle 200 pages in <30s (conservative)."""
    reads = []
    # 40 documents of 5 pages each = 200 pages
    for doc_idx in range(40):
        for page in range(5):
            pdf_page = doc_idx * 5 + page
            # 80% have good reads, 20% failed
            if pdf_page % 5 != 3:
                reads.append(PageRead(pdf_page, page + 1, 5, "direct", 0.85))
            else:
                reads.append(PageRead(pdf_page, None, None, "failed", 0.0))

    params = {**BASIC_PARAMS, "max_total": 20}
    t0 = time.perf_counter()
    docs = run_pipeline(reads, params)
    elapsed = time.perf_counter() - t0

    assert len(docs) >= 1
    assert elapsed < 30.0, f"200-page Viterbi took {elapsed:.1f}s, must be <30s"
```

- [ ] **Step 2: Run all tests**

Run: `cd a:/PROJECTS/PDFoverseer && python -m pytest eval/tests/test_graph_inference.py -v`
Expected: All PASSED (23+ tests)

- [ ] **Step 3: Commit**

```bash
git add eval/tests/test_graph_inference.py
git commit -m "test(graph): edge cases (single page, all failed, empty) + 200-page perf test"
```
