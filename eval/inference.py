# eval/inference.py
"""
Parameterized copy of the full inference pipeline from core/analyzer.py.
Does NOT import from core/ — self-contained for sweep isolation.

Public API:
    run_pipeline(reads: list[PageRead], params: dict) -> list[Document]

params keys (all required):
    fwd_conf, new_doc_base, new_doc_hom_mul  — Phase 1
    back_conf                                 — Phase 2
    xval_cap                                  — Phase 3
    fallback_base, fallback_hom_base, fallback_hom_mul  — Phase 4
    ds_boost_max                              — Phase 5 (period evidence not ported)
    window, hom_threshold                     — Global
"""
from __future__ import annotations
import copy
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class PageRead:
    pdf_page:   int
    curr:       int | None
    total:      int | None
    method:     str
    confidence: float


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


def run_pipeline(reads: list[PageRead], params: dict) -> list[Document]:
    """Full pipeline: deepcopy → infer → build docs → undercount recovery."""
    reads = copy.deepcopy(reads)
    _infer(reads, params)
    docs = _build_documents(reads)
    docs = _undercount_recovery(reads, docs)
    return docs


# ── Phase 1–5 Inference ──────────────────────────────────────────────────────

def _infer(reads: list[PageRead], params: dict) -> None:
    """Mutates reads in-place. Mirrors _infer_missing in core/analyzer.py."""
    n = len(reads)
    if n == 0:
        return

    fwd_conf         = params["fwd_conf"]
    new_doc_base     = params["new_doc_base"]
    new_doc_hom_mul  = params["new_doc_hom_mul"]
    back_conf        = params["back_conf"]
    xval_cap         = params["xval_cap"]
    fallback_base    = params["fallback_base"]
    fallback_hom_base = params["fallback_hom_base"]
    fallback_hom_mul  = params["fallback_hom_mul"]
    # ds_support_min omitted: period evidence not ported — support stays 0.0 always.
    # D-S phase only fires via neighbors_agree == 2.
    ds_boost_max     = params["ds_boost_max"]
    window           = params["window"]
    hom_threshold    = params["hom_threshold"]

    total_counts = Counter(r.total for r in reads if r.total is not None)
    total_sum = sum(total_counts.values()) or 1
    prior: dict[int, float] = {k: v / total_sum for k, v in total_counts.items()}
    if not prior:
        prior = {2: 0.85, 3: 0.10, 1: 0.05}
    best_total = max(prior, key=prior.get)

    def _local_total(idx: int) -> tuple[int, float]:
        lo, hi = max(0, idx - window), min(n, idx + window + 1)
        local = [reads[j].total for j in range(lo, hi)
                 if reads[j].total is not None
                 and reads[j].method not in ("failed", "inferred")]
        if not local:
            return best_total, 0.0
        tc = Counter(local)
        mode_val, mode_freq = tc.most_common(1)[0]
        hom = mode_freq / len(local)
        if hom >= hom_threshold:
            return mode_val, hom
        return best_total, hom

    # ── Phase 1: Forward propagation ────────────────────────────────
    for i in range(n):
        r = reads[i]
        if r.method != "failed":
            continue
        if i > 0:
            prev = reads[i - 1]
            if prev.curr is not None and prev.total is not None:
                if prev.curr < prev.total:
                    r.curr, r.total = prev.curr + 1, prev.total
                    r.method, r.confidence = "inferred", fwd_conf
                elif prev.curr == prev.total:
                    lt, hom = _local_total(i)
                    r.curr, r.total = 1, lt
                    r.method = "inferred"
                    r.confidence = new_doc_base + hom * new_doc_hom_mul

    # ── Phase 2: Backward propagation ───────────────────────────────
    for i in range(n - 2, -1, -1):
        r = reads[i]
        if r.method != "failed":
            continue
        if i < n - 1:
            nxt = reads[i + 1]
            if nxt.curr is not None and nxt.total is not None:
                if nxt.curr > 1:
                    r.curr, r.total = nxt.curr - 1, nxt.total
                    r.method, r.confidence = "inferred", back_conf
                elif nxt.curr == 1 and i > 0:
                    prev = reads[i - 1]
                    if (prev.curr is not None and prev.total is not None
                            and prev.curr < prev.total):
                        r.curr, r.total = prev.curr + 1, prev.total
                        r.method, r.confidence = "inferred", back_conf

    # ── Phase 3: Cross-validation ────────────────────────────────────
    for i in range(n):
        r = reads[i]
        if r.method != "inferred":
            continue
        consistent = True
        if i > 0:
            prev = reads[i - 1]
            if prev.curr is not None and prev.total is not None:
                if not ((prev.total == r.total and prev.curr == r.curr - 1) or
                        (prev.curr == prev.total and r.curr == 1)):
                    consistent = False
        if i < n - 1:
            nxt = reads[i + 1]
            if nxt.curr is not None and nxt.total is not None:
                if not ((nxt.total == r.total and nxt.curr == r.curr + 1) or
                        (r.curr == r.total and nxt.curr == 1)):
                    consistent = False
        if not consistent:
            r.confidence = min(r.confidence, xval_cap)

    # ── Phase 4: Fallback for remaining failures ─────────────────────
    for i, r in enumerate(reads):
        if r.method == "failed":
            lt, hom = _local_total(i)
            r.curr, r.total = 1, lt
            r.method = "inferred"
            r.confidence = (fallback_base if hom < hom_threshold
                            else fallback_hom_base + hom * fallback_hom_mul)

    # ── Phase 5: D-S post-validation ─────────────────────────────────
    # Does NOT change curr/total — only boosts confidence when neighbor
    # evidence confirms the inferred assignment.
    # Period evidence not ported (requires OCR context); support stays 0.0.
    # D-S fires only when both neighbors agree (neighbors_agree == 2).
    for i in range(n):
        r = reads[i]
        if r.method != "inferred" or r.confidence > 0.60:
            continue

        neighbors_agree = 0

        if i > 0:
            prev = reads[i - 1]
            if prev.curr is not None and prev.total is not None:
                if ((prev.total == r.total and prev.curr == r.curr - 1) or
                        (prev.curr == prev.total and r.curr == 1)):
                    neighbors_agree += 1
        if i < n - 1:
            nxt = reads[i + 1]
            if nxt.curr is not None and nxt.total is not None:
                if ((nxt.total == r.total and nxt.curr == r.curr + 1) or
                        (r.curr == r.total and nxt.curr == 1)):
                    neighbors_agree += 1

        prior_support = prior.get(r.total, 0.0)

        if neighbors_agree == 2:
            boost = min(neighbors_agree * 0.08 + prior_support * 0.05, ds_boost_max)
            r.confidence = min(r.confidence + boost, 0.75)


# ── Build Documents ──────────────────────────────────────────────────────────

def _build_documents(reads: list[PageRead]) -> list[Document]:
    """Groups reads into Document objects. No logging callbacks."""
    documents: list[Document] = []
    current: Document | None  = None

    for r in reads:
        if r.method == "excluded":
            continue
        curr, tot, pdf_page = r.curr, r.total, r.pdf_page
        is_inferred = r.method == "inferred"

        if curr == 1:
            if current is not None:
                documents.append(current)
            current = Document(
                index          = len(documents) + 1,
                start_pdf_page = pdf_page,
                declared_total = tot,
                pages          = [] if is_inferred else [pdf_page],
                inferred_pages = [pdf_page] if is_inferred else [],
            )
        elif curr is not None:
            if current is not None:
                if is_inferred:
                    current.inferred_pages.append(pdf_page)
                elif curr == current.found_total + 1 and tot == current.declared_total:
                    current.pages.append(pdf_page)
                else:
                    current.sequence_ok = False
                    current.pages.append(pdf_page)

    if current is not None:
        documents.append(current)
    return documents


# ── Undercount Recovery ──────────────────────────────────────────────────────

def _undercount_recovery(reads: list[PageRead], docs: list[Document]) -> list[Document]:
    """Mirrors the undercount recovery loop in analyze_pdf."""
    reads_by_page = {r.pdf_page: r for r in reads}
    fixed = 0
    for di in range(len(docs) - 1):
        d, d_next = docs[di], docs[di + 1]
        missing = d.declared_total - d.found_total
        if missing <= 0 or d.declared_total <= 1:
            continue
        if (d_next.found_total <= missing
                and d_next.declared_total == d.declared_total):
            next_pages = d_next.pages + d_next.inferred_pages
            for pp in next_pages:
                r = reads_by_page.get(pp)
                if r and r.method == "inferred":
                    r.curr = d.found_total + 1
                    r.total = d.declared_total
                    r.confidence = min(r.confidence + 0.10, 0.85)
            d.inferred_pages.extend(next_pages)
            d_next.pages.clear()
            d_next.inferred_pages.clear()
            d_next.declared_total = 0
            fixed += 1
    if fixed:
        docs = [d for d in docs if d.declared_total > 0]
        for i, d in enumerate(docs):
            d.index = i + 1
    return docs
