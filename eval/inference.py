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
    ds_period_weight, ds_neighbor_weight,     — Phase 5 (D-S evidence weights)
      ds_prior_weight, ds_boost_max
    ph5b_conf_min, ph5b_ratio_min            — Phase 5b (period-contradiction)
    min_conf_for_new_doc                      — Phase 6 (orphan suppression)
    window, hom_threshold                     — Global
"""
from __future__ import annotations
import copy
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
    # Internal flag set during inference (not in fixture JSON — has default):
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


def run_pipeline(reads: list[PageRead], params: dict) -> list[Document]:
    """Full pipeline: deepcopy → detect period → infer → build docs → undercount recovery."""
    reads = copy.deepcopy(reads)
    period_info = _detect_period(reads)
    _infer(reads, params, period_info)
    docs = _build_documents(reads)
    docs = _undercount_recovery(reads, docs)
    return docs


# ── Period Detection ─────────────────────────────────────────────────────────

def _detect_period(reads: list[PageRead]) -> dict:
    """
    Detect repeating period in page numbering via:
      1. Spacing between curr=1 occurrences
      2. Most common declared total
      3. Autocorrelation of curr value sequence
    Returns dict with 'period', 'confidence', 'expected_total'.
    """
    n = len(reads)
    result: dict = {"period": None, "confidence": 0.0, "expected_total": None}
    if n < 4:
        return result

    confirmed = [
        (i, r) for i, r in enumerate(reads)
        if r.curr is not None and r.method not in ("failed", "excluded")
    ]
    if len(confirmed) < 3:
        return result

    # Method 1: Spacing between curr=1
    starts = [i for i, r in confirmed if r.curr == 1]
    gap_period, gap_conf = None, 0.0
    if len(starts) >= 2:
        gaps = [starts[j + 1] - starts[j] for j in range(len(starts) - 1)]
        if gaps:
            gc = Counter(gaps)
            gap_period, freq = gc.most_common(1)[0]
            gap_conf = freq / len(gaps)

    # Method 2: Most common total
    totals = [r.total for _, r in confirmed if r.total is not None]
    mode_total, total_conf = None, 0.0
    if totals:
        tc = Counter(totals)
        mode_total, freq = tc.most_common(1)[0]
        total_conf = freq / len(totals)

    # Method 3: Autocorrelation on curr sequence
    acorr_period, acorr_conf = None, 0.0
    curr_vals = np.array([
        float(r.curr) if r.curr is not None and r.method not in ("failed",)
        else np.nan for r in reads
    ])
    valid_mask = ~np.isnan(curr_vals)

    if valid_mask.sum() >= 6:
        valid_idx = np.where(valid_mask)[0]
        filled = np.interp(np.arange(n), valid_idx, curr_vals[valid_mask])
        centered = filled - filled.mean()
        energy = np.sum(centered ** 2)

        if energy > 0:
            acorr = np.correlate(centered, centered, mode="full")[n - 1:]
            acorr = acorr / energy
            for lag in range(2, min(n // 2, 50)):
                if lag + 1 < len(acorr):
                    if (acorr[lag] > acorr[lag - 1]
                            and acorr[lag] >= acorr[lag + 1]
                            and acorr[lag] > 0.3):
                        acorr_period = lag
                        acorr_conf = float(acorr[lag])
                        break

    # Combine evidence
    candidates: dict[int, float] = {}
    if gap_period is not None and gap_conf > 0.3:
        candidates[gap_period] = candidates.get(gap_period, 0) + gap_conf * 0.45
    if mode_total is not None and total_conf > 0.3:
        candidates[mode_total] = candidates.get(mode_total, 0) + total_conf * 0.30
    if acorr_period is not None and acorr_conf > 0.3:
        candidates[acorr_period] = candidates.get(acorr_period, 0) + acorr_conf * 0.25

    if not candidates:
        result["expected_total"] = mode_total
        return result

    best = max(candidates, key=candidates.get)
    return {
        "period": best,
        "confidence": min(candidates[best], 1.0),
        "expected_total": mode_total or best,
    }


def _period_evidence(
    i: int, reads: list[PageRead], period: int,
) -> dict | None:
    """Find pages at the same cycle position (±k*period) and return mass function."""
    n = len(reads)
    candidates: dict[tuple, float] = {}

    for mult in range(1, 8):
        for sign in (-1, 1):
            pos = i + sign * mult * period
            if 0 <= pos < n:
                r = reads[pos]
                if r.curr is not None and r.method not in ("failed", "excluded"):
                    h = (r.curr, r.total)
                    dist_w = 1.0 / mult
                    method_w = (1.0 if r.method in ("direct", "super_resolution", "easyocr", "manual")
                                else 0.5)
                    candidates[h] = candidates.get(h, 0) + dist_w * method_w

    if not candidates:
        return None
    total_w = sum(candidates.values())
    return {h: w / total_w for h, w in candidates.items()}


# ── Phase 1–5 Inference ──────────────────────────────────────────────────────

def _infer(reads: list[PageRead], params: dict, period_info: dict | None = None) -> None:
    """Mutates reads in-place. Mirrors _infer_missing in core/analyzer.py."""
    n = len(reads)
    if n == 0:
        return

    fwd_conf         = params["fwd_conf"]
    new_doc_base     = params["new_doc_base"]
    new_doc_hom_mul  = params["new_doc_hom_mul"]
    back_conf        = params["back_conf"]
    xval_cap         = params["xval_cap"]
    ds_period_weight   = params["ds_period_weight"]
    ds_neighbor_weight = params["ds_neighbor_weight"]
    ds_prior_weight    = params["ds_prior_weight"]
    ds_boost_max       = params["ds_boost_max"]
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

    # ── Phase 0: Anomaly Downgrade (Soft Dropout) ───────────────────
    anomaly_dropout = params.get("anomaly_dropout", 0.0)
    if anomaly_dropout > 0.0:
        for i in range(n):
            r = reads[i]
            if r.method in ("failed", "inferred", "excluded") or r.total is None:
                continue
            lt, hom = _local_total(i)
            if r.total == 1 and hom >= hom_threshold and lt > 1:
                r.confidence -= hom
                if r.confidence < anomaly_dropout:
                    r.method = "failed"
                    r.curr = None
                    r.total = None

    # ── Phase 1 & 2: Bidirectional Soft Clash Resolution ────────────
    clash_w_local = params.get("clash_w_local", 1.0)
    clash_w_period = params.get("clash_w_period", 1.0)
    clash_boundary_pen = params.get("clash_boundary_pen", 5.0)

    gaps = []
    start_idx = None
    for i in range(n):
        if reads[i].method == "failed":
            if start_idx is None:
                start_idx = i
        else:
            if start_idx is not None:
                gaps.append((start_idx, i))
                start_idx = None
    if start_idx is not None:
        gaps.append((start_idx, n))

    for gap_start, gap_end in gaps:
        # Generate hyp_fwd
        hyp_fwd = []
        prev_c, prev_t = None, None
        if gap_start > 0:
            prev = reads[gap_start - 1]
            if prev.curr is not None and prev.total is not None:
                prev_c, prev_t = prev.curr, prev.total
        
        for i in range(gap_start, gap_end):
            lt, hom = _local_total(i)
            if prev_c is not None and prev_t is not None:
                if prev_c < prev_t:
                    c, t = prev_c + 1, prev_t
                else:
                    c, t = 1, lt
            else:
                c, t = 1, lt
            hyp_fwd.append((c, t, hom))
            prev_c, prev_t = c, t

        # Generate hyp_bwd
        hyp_bwd = []
        nxt_c, nxt_t = None, None
        if gap_end < n:
            nxt = reads[gap_end]
            if nxt.curr is not None and nxt.total is not None:
                nxt_c, nxt_t = nxt.curr, nxt.total
        
        for i in range(gap_end - 1, gap_start - 1, -1):
            lt, hom = _local_total(i)
            if nxt_c is not None and nxt_t is not None:
                if nxt_c > 1:
                    c, t = nxt_c - 1, nxt_t
                else:
                    c, t = lt, lt
            else:
                c, t = lt, lt
            hyp_bwd.insert(0, (c, t, hom))
            nxt_c, nxt_t = c, t

        # Score hypotheses
        def seq_cost(seq):
            cost = 0.0
            for offset, (c, t, hom) in enumerate(seq):
                idx = gap_start + offset
                lt_val, _ = _local_total(idx)
                if t != lt_val:
                    cost += hom * clash_w_local
                if c == 1 and period_info and period_info.get("period"):
                    p_conf = period_info.get("confidence", 0.0)
                    ex_t = period_info.get("expected_total", period_info["period"])
                    if p_conf > 0.3 and t != ex_t:
                        cost += p_conf * clash_w_period
            return cost
        
        cost_fwd = seq_cost(hyp_fwd)
        cost_bwd = seq_cost(hyp_bwd)

        # Boundary divergence penalty
        if gap_end < n:
            r_nxt = reads[gap_end]
            fwd_last_c, fwd_last_t, _ = hyp_fwd[-1]
            if r_nxt.curr is not None and r_nxt.total is not None:
                if not ((fwd_last_t == r_nxt.total and fwd_last_c == r_nxt.curr - 1) or 
                        (fwd_last_c == fwd_last_t and r_nxt.curr == 1)):
                    cost_fwd += clash_boundary_pen
        
        if gap_start > 0:
            r_prev = reads[gap_start - 1]
            bwd_first_c, bwd_first_t, _ = hyp_bwd[0]
            if r_prev.curr is not None and r_prev.total is not None:
                if not ((r_prev.total == bwd_first_t and r_prev.curr == bwd_first_c - 1) or
                        (r_prev.curr == r_prev.total and bwd_first_c == 1)):
                    cost_bwd += clash_boundary_pen

        if cost_fwd <= cost_bwd:
            best_hyp = hyp_fwd
        else:
            best_hyp = hyp_bwd

        # Apply
        for offset, (c, t, hom) in enumerate(best_hyp):
            r = reads[gap_start + offset]
            r.method = "inferred"
            r.curr, r.total = c, t
            if best_hyp is hyp_bwd:
                r.confidence = back_conf
            else:
                if offset == 0 and gap_start > 0:
                    rp = reads[gap_start - 1]
                    if rp.curr == rp.total:
                        r.confidence = new_doc_base + hom * new_doc_hom_mul
                        continue
                if c == 1:
                    r.confidence = new_doc_base + hom * new_doc_hom_mul
                else:
                    r.confidence = fwd_conf

    # ── Phase 1b: Orphan candidate marking ──────────────────────────
    # An inferred curr==1 page whose immediate next page is also curr==1
    # (confirmed or inferred) is a "Phase 1 orphan candidate": it claims
    # to start a new multi-page doc but the very next page restarts again,
    # which is inconsistent. Phase 3 will cap its confidence via xval_cap.
    # This flag lets Phase 6 suppress only these pages (not Phase 4 fallbacks).
    for i in range(n - 1):
        r = reads[i]
        if r.method == "inferred" and r.curr == 1:
            nxt = reads[i + 1]
            if nxt.curr == 1:
                r._ph1_orphan_candidate = True

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

    # ── Phase 4: Fallback for unresolved failures ─────────────────────
    phase4_conf = params.get("phase4_conf", 0.0)
    if phase4_conf > 0.0:
        for i, r in enumerate(reads):
            if r.method == "failed":
                lt, hom = _local_total(i)
                r.curr   = 1
                r.total  = lt
                r.method = "inferred"
                r.confidence = phase4_conf

    # ── Phase 5: D-S post-validation ─────────────────────────────────
    # Does NOT change curr/total — only boosts confidence when
    # independent evidence (period + neighbors) confirms the assignment.
    period = period_info.get("period") if period_info else None
    period_conf = period_info.get("confidence", 0.0) if period_info else 0.0

    if period is not None and period_conf > 0.3:
        for i in range(n):
            r = reads[i]
            if r.method != "inferred" or r.confidence > 0.60:
                continue

            h = (r.curr, r.total)
            support = 0.0

            # Evidence 1: Period-aligned pages agree?
            palign = _period_evidence(i, reads, period)
            if palign and h in palign:
                support += palign[h] * period_conf

            # Evidence 2: Neighbor consistency (both sides)
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

            # Evidence 3: Prior supports this total?
            prior_support = prior.get(r.total, 0.0)

            # Combine: period + neighbors + prior
            if support > 0.2 or neighbors_agree == 2:
                boost = min(support * ds_period_weight
                            + neighbors_agree * ds_neighbor_weight
                            + prior_support * ds_prior_weight,
                            ds_boost_max)
                r.confidence = min(r.confidence + boost, 0.75)

    # ── Phase 5b: Period-contradiction correction ────────────────────
    # Direct OCR reads whose total contradicts the dominant period are
    # rewritten when the period evidence is overwhelmingly strong.
    # Example: INS_31 — 29/31 pages read as 1/1 (P=1), but pages 30-31
    # read as "1/4" and "2/4". Phase 5b corrects them to 1/1.
    ph5b_conf_min  = params.get("ph5b_conf_min", 0.0)
    ph5b_ratio_min = params.get("ph5b_ratio_min", 0.85)

    if (ph5b_conf_min > 0
            and period is not None
            and period_conf >= ph5b_conf_min):
        expected_total = period_info.get("expected_total", period)
        reads_with_total = [r for r in reads if r.total is not None
                           and r.method not in ("failed", "excluded")]
        if reads_with_total:
            agreeing = sum(1 for r in reads_with_total
                          if r.total == expected_total)
            ratio = agreeing / len(reads_with_total)

            if ratio >= ph5b_ratio_min:
                corrected_indices: set[int] = set()
                for idx_r, r in enumerate(reads):
                    if (r.method not in ("failed", "inferred", "excluded")
                            and r.total is not None
                            and r.total != expected_total):
                        # Preserve curr if it fits within the expected total;
                        # otherwise reset to 1.
                        if r.curr is not None and 1 <= r.curr <= expected_total:
                            r.total = expected_total
                        else:
                            r.curr = 1
                            r.total = expected_total
                        r.method = "inferred"
                        r.confidence = 0.50
                        corrected_indices.add(idx_r)

                # Re-propagate: fix inferred pages downstream of corrected pages
                # whose curr/total was derived from the now-corrected values.
                if corrected_indices:
                    for idx_r in sorted(corrected_indices):
                        j = idx_r + 1
                        while j < n:
                            rj = reads[j]
                            if rj.method != "inferred":
                                break
                            prev = reads[j - 1]
                            if prev.curr is not None and prev.total is not None:
                                if prev.curr == prev.total:
                                    rj.curr = 1
                                    rj.total = expected_total
                                    rj.confidence = new_doc_base + _local_total(j)[1] * new_doc_hom_mul
                                elif prev.curr < prev.total:
                                    rj.curr = prev.curr + 1
                                    rj.total = prev.total
                                else:
                                    break
                            else:
                                break
                            j += 1

    # ── Phase 6: Orphan suppression ──────────────────────────────────
    # Suppress Phase-1 orphan candidates whose final confidence (after Phase 3
    # xval_cap and Phase 5 D-S) is below the threshold.
    # ONLY targets _ph1_orphan_candidate pages — pages assigned curr=1 by Phase 1
    # that are immediately followed by another curr=1 (structural inconsistency).
    # Phase-4 fallbacks (also curr=1) are never _ph1_orphan_candidate and are
    # therefore not suppressed, preventing regressions on data-poor regions.
    min_conf_for_new_doc = params["min_conf_for_new_doc"]
    if min_conf_for_new_doc > 0.0:
        for r in reads:
            if (r.method == "inferred" and r.curr == 1
                    and r._ph1_orphan_candidate
                    and r.confidence < min_conf_for_new_doc):
                r.method = "excluded"
                r.curr   = None
                r.total  = None


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
            # Guard: if the next doc contains a confirmed (OCR-read) curr==1
            # page, it is a genuine new-document start — do NOT merge it.
            has_confirmed_start = any(
                reads_by_page[pp].curr == 1
                and reads_by_page[pp].method not in ("inferred", "failed", "excluded")
                for pp in next_pages if pp in reads_by_page
            )
            if has_confirmed_start:
                continue
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
