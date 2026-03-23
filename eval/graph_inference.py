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
