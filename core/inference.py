"""Inference engine: period detection, Dempster-Shafer fusion, phases 1-6.

This is the MASTER-branch algorithm ported to the modular architecture.
Parameters are the sweep-validated values from master (6ph-t2).
"""
from __future__ import annotations

from collections import Counter
import numpy as np

from core.utils import Document, _PageRead, MIN_CONF_FOR_NEW_DOC

# ── Parameters (master sweep-validated) ──────────────────────────────────────
# Phase 5b thresholds from master
PH5B_CONF_MIN  = 0.69   # min period confidence to activate
PH5B_RATIO_MIN = 0.93   # min fraction of reads that must agree with period

# ── Period Detection ──────────────────────────────────────────────────────────

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

    # ── Combine evidence ──────────────────────────────────────────────
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
    """Dempster-Shafer combination of two mass functions."""
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
                    method_w = (1.0 if r.method in ("direct", "SR", "easyocr", "manual")
                                else 0.5)
                    candidates[h] = candidates.get(h, 0) + dist_w * method_w

    if not candidates:
        return None
    total_w = sum(candidates.values())
    return {h: w / total_w for h, w in candidates.items()}


# ── Tier 4: Inference Engine (master 6-phase D-S) ────────────────────────────

def _infer_missing(
    reads: list[_PageRead],
    period_info: dict | None = None,
) -> list[_PageRead]:
    """
    Constraint propagation inference for pages where OCR failed.
    Master-branch algorithm: 6 phases, sweep-validated parameters.

    Phase 1: Forward propagation  (prev → curr)
    Phase 2: Backward propagation (next → curr)
    Phase 1b: Orphan candidate marking
    Phase 3: Cross-validation     (neighbor consistency, xval_cap=0.50)
    Phase 4: Fallback             (remaining failures → best prior)
    Phase 5: D-S post-validation  (uncertain pages ≤0.60)
    Phase 5b: Period-contradiction correction (conf_min=0.69, ratio_min=0.93)
    Phase 6: Orphan suppression
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

    def _local_total(idx: int, window: int = 5) -> tuple[int, float]:
        """Return (most_common_total, homogeneity) from ±window confirmed reads.
        Only overrides best_total when local region is highly homogeneous (≥85%).
        Mixed regions fall back to best_total to avoid bias."""
        lo, hi = max(0, idx - window), min(n, idx + window + 1)
        local = [reads[j].total for j in range(lo, hi)
                 if reads[j].total is not None
                 and reads[j].method not in ("failed", "inferred")]
        if not local:
            return best_total, 0.0
        tc = Counter(local)
        mode_val, mode_freq = tc.most_common(1)[0]
        homogeneity = mode_freq / len(local)
        if homogeneity >= 0.85:
            return mode_val, homogeneity
        return best_total, homogeneity

    # ── Phase 1: Forward propagation ─────────────────────────────────
    for i in range(n):
        r = reads[i]
        if r.method != "failed":
            continue
        if i > 0:
            prev = reads[i - 1]
            if prev.curr is not None and prev.total is not None:
                if prev.curr < prev.total:
                    r.curr = prev.curr + 1
                    r.total = prev.total
                    r.method = "inferred"
                    r.confidence = 0.95
                elif prev.curr == prev.total:
                    lt, hom = _local_total(i)
                    r.curr = 1
                    r.total = lt
                    r.method = "inferred"
                    r.confidence = 0.70 + hom * 0.30  # 0.70..1.00

    # ── Phase 2: Backward propagation ────────────────────────────────
    for i in range(n - 2, -1, -1):
        r = reads[i]
        if r.method != "failed":
            continue
        if i < n - 1:
            nxt = reads[i + 1]
            if nxt.curr is not None and nxt.total is not None:
                if nxt.curr > 1:
                    r.curr = nxt.curr - 1
                    r.total = nxt.total
                    r.method = "inferred"
                    r.confidence = 0.90
                elif nxt.curr == 1 and i > 0:
                    prev = reads[i - 1]
                    if (prev.curr is not None and prev.total is not None
                            and prev.curr < prev.total):
                        r.curr = prev.curr + 1
                        r.total = prev.total
                        r.method = "inferred"
                        r.confidence = 0.90

    # ── Phase 1b: Orphan candidate marking ───────────────────────────
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
            r.confidence = min(r.confidence, 0.50)  # xval_cap=0.50 (master value)

    # ── Phase 4: Fallback for remaining failures ──────────────────────
    for i, r in enumerate(reads):
        if r.method == "failed":
            lt, hom = _local_total(i)
            r.curr = 1
            r.total = lt
            r.method = "inferred"
            r.confidence = 0.40 if hom < 0.85 else 0.40 + hom * 0.15

    # ── Phase 5: D-S post-validation for uncertain pages (≤0.60) ─────
    # Does NOT change curr/total assignments — only boosts confidence
    # when independent evidence (period + neighbors) confirms them.
    if period is not None and period_conf > 0.3:
        for i in range(n):
            r = reads[i]
            if r.method != "inferred" or r.confidence > 0.60:
                continue  # only validate uncertain pages

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

            # Combine: period + neighbors + prior (master boost weights)
            if support > 0.2 or neighbors_agree == 2:
                boost = min(support * 0.10 + neighbors_agree * 0.10
                            + prior_support * 0.05, 0.23)
                r.confidence = min(r.confidence + boost, 0.75)

    # ── Phase 5b: Period-contradiction correction ─────────────────────
    # Master parameters: PH5B_CONF_MIN=0.69, PH5B_RATIO_MIN=0.93
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

    # ── Phase 6: Orphan suppression ──────────────────────────────────
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
                if on_issue:
                    on_issue(pdf_page, "huerfana", f"curr={curr} sin doc activo")
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
