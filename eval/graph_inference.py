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
