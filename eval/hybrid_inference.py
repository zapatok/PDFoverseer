"""
Hybrid inference: existing engine phases 0-6 (signal processing)
→ HMM+Viterbi (global sequence decoding).

Self-contained — does NOT import from core/.

Public API:
    run_pipeline(reads: list[PageRead], params: dict) -> list[Document]

params must contain all keys required by eval/inference.py (phases 0-6)
AND all keys required by eval/graph_inference.py (HMM/Viterbi).
These key sets are disjoint so a merged dict works directly.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.graph_inference import extract_documents, viterbi_decode  # noqa: E402
from eval.inference import Document, PageRead, _detect_period, _infer  # noqa: E402


def run_pipeline(reads: list[PageRead], params: dict) -> list[Document]:
    """Signal processing (phases 0-6) → global Viterbi decoding.

    Phase breakdown:
        _detect_period  — autocorrelation + gap + mode-total period detection
        _infer          — phases 0-6: gap-fill, DS fusion, 5b correction,
                          orphan suppression (mutates reads in-place)
        viterbi_decode  — globally optimal state-path on calibrated reads
        extract_documents — build Document objects from decoded path
    """
    reads = copy.deepcopy(reads)
    period_info = _detect_period(reads)
    _infer(reads, params, period_info)
    path = viterbi_decode(reads, params)
    docs = extract_documents(reads, path)
    return docs
