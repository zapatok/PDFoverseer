"""
Inference engine: period detection, Dempster-Shafer fusion, phases 0-6.

Confidence thresholds (MIN_CONF_FOR_NEW_DOC, PH5B_CONF_MIN, CLASH_BOUNDARY_PEN,
etc.) were tuned via eval/sweep.py — a Latin Hypercube Sample followed by a
fine grid search over 7 real PDF fixtures. See eval/sweep.py for sweep design.
"""
from __future__ import annotations

from typing import Optional
from collections import Counter
import numpy as np

from core.utils import Document, _PageRead, MIN_CONF_FOR_NEW_DOC, ANOMALY_DROPOUT, PHASE4_FALLBACK_CONF, CLASH_BOUNDARY_PEN, PH5B_CONF_MIN, PH5B_RATIO_MIN

# ── Period Detection ─────────────────────────────────────────────────────────

def _detect_period(reads: list[_PageRead]) -> dict:
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

    # Only use OCR-confirmed reads
    confirmed = [
        (i, r) for i, r in enumerate(reads)
        if r.curr is not None and r.method not in ("failed", "excluded")
    ]
    if len(confirmed) < 3:
        return result

    # ── Method 1: Spacing between curr=1 ─────────────────────────────
    starts = [i for i, r in confirmed if r.curr == 1]
    gap_period, gap_conf = None, 0.0
    if len(starts) >= 2:
        gaps = [starts[j + 1] - starts[j] for j in range(len(starts) - 1)]
        if gaps:
            gc = Counter(gaps)
            gap_period, freq = gc.most_common(1)[0]
            gap_conf = freq / len(gaps)

    # ── Method 2: Most common total ──────────────────────────────────
    totals = [r.total for _, r in confirmed if r.total is not None]
    mode_total, total_conf = None, 0.0
    if totals:
        tc = Counter(totals)
        mode_total, freq = tc.most_common(1)[0]
        total_conf = freq / len(totals)

    # ── Method 3: Autocorrelation on curr sequence ───────────────────
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

    # ── Combine evidence ─────────────────────────────────────────────
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


# ── Dempster-Shafer Evidence Fusion ──────────────────────────────────────────

def _ds_combine(m1: dict, m2: dict) -> dict:
    """Dempster-Shafer combination of two mass functions.

    Keys are hypothesis tuples ``(curr, total)`` or the string ``'unknown'``
    representing the full frame of discernment (Theta).
    """
    combined: dict = {}
    conflict = 0.0

    for h1, v1 in m1.items():
        for h2, v2 in m2.items():
            product = v1 * v2
            if h1 == "unknown":
                combined[h2] = combined.get(h2, 0) + product
            elif h2 == "unknown":
                combined[h1] = combined.get(h1, 0) + product
            elif h1 == h2:
                combined[h1] = combined.get(h1, 0) + product
            else:
                conflict += product

    norm = 1.0 - conflict
    if norm < 0.01:
        return {"unknown": 1.0}
    return {k: v / norm for k, v in combined.items()}


def _period_evidence(
    i: int, reads: list[_PageRead], period: int,
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


# ── Tier 4: Inference Engine (D-S fusion) ────────────────────────────────────

def _infer_missing(
    reads: list[_PageRead],
    period_info: dict | None = None,
) -> list[_PageRead]:
    """
    Constraint propagation inference for pages where OCR failed.

    Phase 1: Forward propagation  (prev → curr)
    Phase 2: Backward propagation (next → curr)
    Phase 3: Period-enhanced validation (boost/penalize via period alignment)
    Phase 4: Cross-validation     (neighbor consistency check)
    Phase 5: Fallback             (remaining failures → best prior)
    """
    n = len(reads)
    if n == 0:
        return reads

    # Prior P(total=N)
    total_counts = Counter(r.total for r in reads if r.total is not None)
    total_sum = sum(total_counts.values()) or 1
    prior: dict[int, float] = {k: v / total_sum for k, v in total_counts.items()}
    if not prior:
        prior = {2: 0.85, 3: 0.10, 1: 0.05}
    best_total = max(prior, key=prior.get)

    period = period_info.get("period") if period_info else None
    period_conf = period_info.get("confidence", 0.0) if period_info else 0.0

    _lt_cache: dict[int, tuple[int, float]] = {}

    def _local_total(idx: int, window: int = 5) -> tuple[int, float]:
        """Return (most_common_total, homogeneity) from ±window confirmed reads.
        Only overrides best_total when local region is highly homogeneous (≥85%).
        Mixed regions fall back to best_total to avoid bias."""
        if idx in _lt_cache:
            return _lt_cache[idx]
        lo, hi = max(0, idx - window), min(n, idx + window + 1)
        local = [reads[j].total for j in range(lo, hi)
                 if reads[j].total is not None
                 and reads[j].method not in ("failed", "inferred")]
        if not local:
            result = (best_total, 0.0)
        else:
            tc = Counter(local)
            mode_val, mode_freq = tc.most_common(1)[0]
            homogeneity = mode_freq / len(local)
            result = (mode_val, homogeneity) if homogeneity >= 0.85 else (best_total, homogeneity)
        _lt_cache[idx] = result
        return result

    # ── Phase 0: Anomaly Downgrade (Soft Dropout) ───────────────────
    # Reduces confidence for reads whose declared total conflicts with the local
    # majority total (e.g., a stray curr=1/total=1 page in a 3-page document).
    # Disabled by default (ANOMALY_DROPOUT=0.0) — only useful when OCR quality
    # is so poor that single-page "documents" appear as noise.
    if ANOMALY_DROPOUT > 0.0:
        for i in range(n):
            r = reads[i]
            if r.method in ("failed", "inferred", "excluded") or r.total is None:
                continue
            lt, hom = _local_total(i)
            if r.total == 1 and hom >= 0.85 and lt > 1:
                r.confidence -= hom
                if r.confidence < ANOMALY_DROPOUT:
                    r.method = "failed"
                    r.curr = None
                    r.total = None

    # ── Phase 1 & 2: Bidirectional Soft Clash Resolution ────────────
    # Fills contiguous runs of "failed" pages by generating two hypotheses:
    # forward (left→right propagation) and backward (right→left). Each hypothesis
    # is scored by how well it fits the local total and period alignment; the
    # lower-cost hypothesis wins. CLASH_BOUNDARY_PEN penalizes hypotheses that
    # produce a discontinuity at the boundary with the next known read.
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

            if i == gap_end - 1 and gap_end < n:
                r_nxt = reads[gap_end]
                if r_nxt.curr == 1:
                    t = c

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
                    cost += hom * 0.75
                if c == 1 and period_info and period_info.get("period"):
                    p_conf = period_info.get("confidence", 0.0)
                    ex_t = period_info.get("expected_total", period_info["period"])
                    if p_conf > 0.3 and t != ex_t:
                        cost += p_conf * 2.5
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
                    cost_fwd += CLASH_BOUNDARY_PEN
        
        if gap_start > 0:
            r_prev = reads[gap_start - 1]
            bwd_first_c, bwd_first_t, _ = hyp_bwd[0]
            if r_prev.curr is not None and r_prev.total is not None:
                if not ((r_prev.total == bwd_first_t and r_prev.curr == bwd_first_c - 1) or
                        (r_prev.curr == r_prev.total and bwd_first_c == 1)):
                    cost_bwd += CLASH_BOUNDARY_PEN

        if cost_fwd < cost_bwd:
            best_hyp = hyp_fwd
        elif cost_bwd < cost_fwd:
            best_hyp = hyp_bwd
        else:
            # Tie-break: prefer the hypothesis that creates a document boundary
            # (curr=1). False boundaries can be removed later (Phase 6, undercount
            # recovery) but false continuations cannot be split.
            bwd_has_boundary = any(c == 1 for c, t, h in hyp_bwd)
            fwd_has_boundary = any(c == 1 for c, t, h in hyp_fwd)
            if bwd_has_boundary and not fwd_has_boundary:
                best_hyp = hyp_bwd
            else:
                best_hyp = hyp_fwd

        # Apply
        for offset, (c, t, hom) in enumerate(best_hyp):
            r = reads[gap_start + offset]
            r.method = "inferred"
            r.curr = c
            r.total = t
            if best_hyp is hyp_bwd:
                r.confidence = 0.85
            else:
                if offset == 0 and gap_start > 0:
                    rp = reads[gap_start - 1]
                    if rp.curr == rp.total:
                        r.confidence = 0.60 + hom * 0.30
                        continue
                if c == 1:
                    r.confidence = 0.60 + hom * 0.30
                else:
                    r.confidence = 0.99

    # ── Phase 1b: Orphan candidate marking ──────────────────────────
    # Marks inferred curr=1 pages that are immediately followed by another curr=1
    # as orphan candidates. These are reviewed in Phase 6 for suppression.
    for i in range(n - 1):
        r = reads[i]
        if r.method == "inferred" and r.curr == 1:
            nxt = reads[i + 1]
            if nxt.curr == 1:
                r._ph1_orphan_candidate = True

    # ── Phase 3: Cross-validation ───────────────────────────────────
    # Checks each inferred page against its immediate neighbors. If neither
    # left nor right neighbor is sequentially consistent, confidence is capped
    # at 0.45. Known failure mode: edge pages with only one neighbor and an
    # unrelated adjacent document may be downgraded unnecessarily.
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
            r.confidence = min(r.confidence, 0.50)

    # ── Phase 4: Fallback for unresolved failures ────────────────────
    # Catches pages still marked "failed" after the bidirectional gap solver —
    # typically gaps at the very start/end of the PDF with no neighbours.
    # Disabled by default (PHASE4_FALLBACK_CONF = 0.0).
    if PHASE4_FALLBACK_CONF > 0.0:
        for i, r in enumerate(reads):
            if r.method == "failed":
                lt, hom = _local_total(i)
                r.curr   = 1
                r.total  = lt
                r.method = "inferred"
                r.confidence = PHASE4_FALLBACK_CONF

    # ── Phase 5: Dempster-Shafer post-validation for uncertain pages (≤0.60) ──
    # Boosts confidence of low-confidence inferred pages using two evidence
    # sources: period alignment (autocorrelation score × period confidence) and
    # neighbor agreement (each agreeing neighbor contributes +0.10). Also adds
    # a small prior-probability boost based on the global total distribution.
    # Threshold 0.3 for period_conf prevents noise from weak periods.
    if period is not None and period_conf > 0.3:
        for i in range(n):
            r = reads[i]
            if r.method != "inferred" or r.confidence > 0.60:
                continue

            h = (r.curr, r.total)
            support = 0.0

            palign = _period_evidence(i, reads, period)
            if palign and h in palign:
                support += palign[h] * period_conf

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

            if support > 0.2 or neighbors_agree == 2:
                boost = min(support * 0.10 + neighbors_agree * 0.10
                            + prior_support * 0.07, 0.18)
                r.confidence = min(r.confidence + boost, 0.75)

    # ── Phase 5b: Period-contradiction correction ─────────────────────────────
    # When ≥95% of OCR-confirmed reads agree on expected_total (the period's
    # typical page count), reads with a different total are corrected to match.
    # Requires period_conf ≥ PH5B_CONF_MIN (0.50) to avoid false corrections.
    # sweep2 raised ratio from 0.93→0.95 to avoid over-correcting mixed-period PDFs.
    if period is not None and period_conf >= PH5B_CONF_MIN:
        expected_total = period_info.get("expected_total")
        if expected_total is not None:
            reads_with_total = [r for r in reads
                                if r.method not in ("failed", "inferred", "excluded")
                                and r.total is not None]
            if reads_with_total:
                agreeing = sum(1 for r in reads_with_total
                               if r.total == expected_total)
                ratio = agreeing / len(reads_with_total)

                if ratio >= PH5B_RATIO_MIN:
                    corrected_indices: set[int] = set()
                    for idx_r, r in enumerate(reads):
                        if (r.method not in ("failed", "inferred", "excluded")
                                and r.total is not None
                                and r.total != expected_total):
                            if r.curr is not None and 1 <= r.curr <= expected_total:
                                r.total = expected_total
                            else:
                                r.curr = 1
                                r.total = expected_total
                            r.method = "inferred"
                            r.confidence = 0.50
                            corrected_indices.add(idx_r)

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
                                        lt, hom = _local_total(j)
                                        rj.confidence = 0.60 + hom * 0.30
                                    elif prev.curr < prev.total:
                                        rj.curr = prev.curr + 1
                                        rj.total = prev.total
                                    else:
                                        break
                                else:
                                    break
                                j += 1

    # ── Phase 6: Orphan suppression ─────────────────────────────────
    # Excludes inferred curr=1 pages that were flagged as orphan candidates in
    # Phase 1b and whose confidence is below MIN_CONF_FOR_NEW_DOC (0.65). These
    # are likely false document boundaries caused by a failed page right before
    # a new document starts. Excluded pages are kept in the reads list with
    # method="excluded" so they remain visible in the UI but don't affect counts.
    if MIN_CONF_FOR_NEW_DOC > 0.0:
        for r in reads:
            if (r.method == "inferred" and r.curr == 1
                    and r._ph1_orphan_candidate
                    and r.confidence < MIN_CONF_FOR_NEW_DOC):
                r.method = "excluded"
                r.curr   = None
                r.total  = None

    return reads


def _build_documents(
    reads: list[_PageRead],
    on_log: callable,
    on_issue: callable | None = None,
    period_info: dict | None = None,
) -> list[Document]:
    documents:  list[Document]        = []
    current:    Document | None       = None
    orphans:    list[int]             = []
    seq_breaks: list[tuple[int,int,int]] = []

    def doc_is_manual(doc: Document) -> bool:
        for p in doc.pages + doc.inferred_pages:
            if reads[p - 1].method in ("manual", "excluded"):
                return True
        return False

    for r in reads:
        if r.method == "excluded":
            continue

        curr, tot, pdf_page = r.curr, r.total, r.pdf_page
        is_inferred = r.method == "inferred"

        if curr == 1:
            if current is not None:
                if not doc_is_manual(current):
                    if not current.sequence_ok or not (current.found_total == current.declared_total):
                        msg = f"Incompleto: tiene {current.found_total}p, declaró {current.declared_total}p"
                        if current.found_total == current.declared_total:
                            msg = "Páginas desordenadas o duplicadas"
                        if on_issue:
                            on_issue(current.pages[-1] if current.pages else current.start_pdf_page, "sequence", msg)
                    elif period_info and period_info.get("period", 1) > 1 and current.declared_total == 1:
                        if on_issue:
                            on_issue(current.start_pdf_page, "boundary", f"Anomalía: Doc de 1 página en lote P={period_info.get('period')}")
                documents.append(current)
            current = Document(
                index          = len(documents) + 1,
                start_pdf_page = pdf_page,
                declared_total = tot,
                pages          = [] if is_inferred else [pdf_page],
                inferred_pages = [pdf_page] if is_inferred else [],
            )

        elif curr is not None:
            if current is None:
                orphans.append(pdf_page)
                on_log(f"  -> pag {pdf_page}: huerfana curr={curr} sin doc activo", "warn")
                if on_issue: on_issue(pdf_page, "huerfana", f"curr={curr} sin doc activo")
            else:
                expected = current.found_total + 1
                if is_inferred:
                    current.inferred_pages.append(pdf_page)
                elif curr == expected and tot == current.declared_total:
                    current.pages.append(pdf_page)
                else:
                    current.sequence_ok = False
                    current.pages.append(pdf_page)
                    seq_breaks.append((pdf_page, curr, expected))

    if current is not None:
        if not doc_is_manual(current):
            if not current.sequence_ok or not (current.found_total == current.declared_total):
                msg = f"Incompleto: tiene {current.found_total}p, declaró {current.declared_total}p"
                if current.found_total == current.declared_total:
                    msg = "Páginas desordenadas o duplicadas"
                if on_issue:
                    on_issue(current.pages[-1] if current.pages else current.start_pdf_page, "sequence", msg)
            elif period_info and period_info.get("period", 1) > 1 and current.declared_total == 1:
                if on_issue:
                    on_issue(current.start_pdf_page, "boundary", f"Anomalía: Doc de 1 página en lote P={period_info.get('period')}")
        documents.append(current)

    if seq_breaks:
        from collections import defaultdict as _dd
        grp: dict = _dd(list)
        for pp, c, e in seq_breaks:
            grp[(c, e)].append(pp)
        for (c, e), pages in grp.items():
            pages_str = ", ".join(map(str, pages))
            on_log(f"  -> secuencia rota curr={c}/expected={e}: pags {pages_str}", "error")

    if orphans:
        on_log(f"Paginas huerfanas: {orphans}", "warn")
    return documents


def classify_doc(doc: Document, reads_by_page: dict) -> str:
    """Classify doc reliability: direct | inferred_hi | inferred_lo | incomplete."""
    if not doc.is_complete:
        return "incomplete"
    if not doc.inferred_pages:
        return "direct"
    confs = [reads_by_page[p].confidence
             for p in doc.inferred_pages if p in reads_by_page]
    if not confs:
        return "direct"
    return "inferred_hi" if min(confs) >= 0.75 else "inferred_lo"

