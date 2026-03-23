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

import copy           # used in run_pipeline (Task 6)
import math           # used in emission/transition/Viterbi (Tasks 2-4)
from collections import Counter  # used in modal total detection (Task 4)
from dataclasses import dataclass, field

import numpy as np    # used in Viterbi decoder (Tasks 4, 10)


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


def compute_log_transition(state_from, state_to, params: dict,
                           modal_total: int | None) -> float:
    """Log transition weight (unnormalized — for unit tests only).
    The actual Viterbi uses the row-normalized matrix from _build_log_transition_matrix.
    """
    w = _raw_transition_weight(state_from, state_to, params, modal_total)
    return math.log(max(w, 1e-15))


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
