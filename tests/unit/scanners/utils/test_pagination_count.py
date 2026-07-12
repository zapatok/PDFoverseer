import pytest

from core.scanners.utils.pagination_count import (
    PageRead,
    count_recovered_starts,
    count_starts,
    detect_repeated_pattern,
    dominant_total,
    extract_code,
    parse_pagination,
    recover_sequence,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Pagina 1 de 4", (1, 4)),
        ("Página 2 de 4", (2, 4)),
        ("r SpA Fecha: 31/12/2025| Página 2 de 4 L", (2, 4)),  # real OCR noise
        ("Pagina 1de1", (1, 1)),  # missing space
        ("Pagina l de 4", (1, 4)),  # l->1 digit-normalize
        ("Pagina 1", (1, None)),  # curr-only (no total)
        ("F-CRS-ART-01 Rev 02", (None, None)),  # no pagination
        ("", (None, None)),
        ("Pagina 12 de 20", (12, 20)),  # full regex wins over curr-only
        ("Pagina 5 de 4", (None, None)),  # implausible C>M → rejected as no-read
        ("Pagina 0 de 4", (None, None)),  # C==0 implausible
    ],
)
def test_parse_pagination(raw, expected):
    assert parse_pagination(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Código: F-CRS-ART-01 Rev 02", "F-CRS-ART-01"),
        ("F-CRS-ODI-01 INFORMACION", "F-CRS-ODI-01"),
        ("F-LCH-CRS-36 EN CALIENTE", "F-LCH-CRS-36"),
        ("no code here", None),
    ],
)
def test_extract_code(raw, expected):
    assert extract_code(raw) == expected


def _currs(reads):
    return [r.curr for r in reads]


def _status(reads):
    return [r.status for r in reads]


def test_dominant_total_mode_ignores_outliers():
    parsed = [
        (1, 4, "A"),
        (2, 4, "A"),
        (3, 4, "A"),
        (4, 4, "A"),
        (1, 4, "A"),
        (2, 3, "A"),
    ]  # one bad total=3
    assert dominant_total(parsed) == 4


def test_dominant_total_none_when_no_totals():
    assert dominant_total([(None, None, None), (1, None, "A")]) is None


def test_recover_no_gaps():
    parsed = [(1, 4, "A"), (2, 4, "A"), (3, 4, "A"), (4, 4, "A")]
    out = recover_sequence(parsed)
    assert _currs(out) == [1, 2, 3, 4]
    assert _status(out) == ["direct"] * 4


def test_recover_run_of_gaps_forward_fill():
    # ART rhythm with 2 unreadable corners mid-run
    parsed = [(1, 4, "A"), (None, None, None), (None, None, None), (4, 4, "A"), (1, 4, "A")]
    out = recover_sequence(parsed)
    assert _currs(out) == [1, 2, 3, 4, 1]
    assert _status(out) == ["direct", "recovered", "recovered", "direct", "direct"]


def test_recovered_page_carries_dominant_total():
    parsed = [(1, 4, "A"), (None, None, None), (3, 4, "A"), (4, 4, "A")]
    out = recover_sequence(parsed)
    assert out[1].status == "recovered" and out[1].curr == 2 and out[1].total == 4


def test_recover_leading_gap_uses_right_neighbor():
    parsed = [(None, None, None), (2, 4, "A"), (3, 4, "A"), (4, 4, "A")]
    out = recover_sequence(parsed)
    assert _currs(out)[0] == 1


def test_recover_orphan_is_failed():
    parsed = [(None, None, None)]  # no dominant total, no neighbor
    out = recover_sequence(parsed)
    assert out[0].status == "failed" and out[0].curr is None


def _reads(specs):  # specs: list of (curr, code, status)
    return [PageRead(c, None, code, st) for c, code, st in specs]


def test_count_starts_plain():
    reads = _reads([(1, "A", "direct"), (2, "A", "direct"), (1, "A", "direct"), (2, "A", "direct")])
    assert count_starts(reads, cover_code=None) == 2


def test_count_starts_cover_code_filters_appendix():
    reads = _reads(
        [
            (1, "F-CRS-ODI-01", "direct"),
            (2, "F-CRS-ODI-01", "direct"),
            (1, "F-CRS-ODI-02", "direct"),
            (1, "F-CRS-ODI-02", "direct"),
        ]
    )
    assert count_starts(reads, cover_code="F-CRS-ODI-01") == 1


def test_count_starts_cover_code_substring_match():
    reads = _reads([(1, "Código-F-CRS-ODI-01-rev", "direct")])
    assert count_starts(reads, cover_code="F-CRS-ODI-01") == 1


def test_count_starts_cover_code_skips_recovered_cover_DOCUMENTED_LIMITATION():
    # A recovered curr==1 has code=None → not counted under cover_code. The scanner
    # compensates by forcing LOW confidence when cover_code is set and recovered
    # reads exist (Task 11), so the operator reviews. This test pins the behavior.
    reads = _reads([(1, None, "recovered"), (2, "F-CRS-ODI-01", "direct")])
    assert count_starts(reads, cover_code="F-CRS-ODI-01") == 0


def test_make_pagination_pdf(tmp_path, make_pagination_pdf):
    from core.scanners.utils.pdf_render import get_page_count

    pdf = make_pagination_pdf(tmp_path / "x.pdf", docs=[(2, "F-CRS-ODI-03"), (2, "F-CRS-ODI-03")])
    assert get_page_count(pdf) == 4
    land = make_pagination_pdf(tmp_path / "l.pdf", docs=[(1, "F-CRS-LCH-22")], landscape=True)
    assert get_page_count(land) == 1


def test_count_documents_synthetic_art(tmp_path, make_pagination_pdf):
    from core.scanners.cancellation import CancellationToken
    from core.scanners.utils.pagination_count import count_documents_by_pagination

    pdf = make_pagination_pdf(tmp_path / "art.pdf", docs=[(4, "F-CRS-ART-01")] * 3)
    r = count_documents_by_pagination(pdf, cancel=CancellationToken())
    assert r.count == 3 and r.failed_reads == 0 and r.dominant_total == 4


def test_count_documents_cover_code_irl(tmp_path, make_pagination_pdf):
    from core.scanners.cancellation import CancellationToken
    from core.scanners.utils.pagination_count import count_documents_by_pagination

    pdf = make_pagination_pdf(
        tmp_path / "irl.pdf",
        docs=[(5, "F-CRS-ODI-01"), (1, "F-CRS-ODI-02"), (1, "F-CRS-ODI-02")],
    )
    r = count_documents_by_pagination(pdf, cancel=CancellationToken(), cover_code="F-CRS-ODI-01")
    assert r.count == 1
    assert r.cover_code_recovery is False  # clean synthetic → no recovery → flag off


def test_count_documents_landscape(tmp_path, make_pagination_pdf):
    from core.scanners.cancellation import CancellationToken
    from core.scanners.utils.pagination_count import count_documents_by_pagination

    pdf = make_pagination_pdf(
        tmp_path / "senal.pdf", docs=[(1, "F-CRS-LCH-22")] * 5, landscape=True
    )
    r = count_documents_by_pagination(pdf, cancel=CancellationToken())
    assert r.count == 5


def test_count_documents_on_page_callback(tmp_path, make_pagination_pdf):
    """U7: on_page is a 0-based monotonic completed-pages counter — the same
    value sequence in sequential and threaded modes (under threads the counter
    is emitted under a lock as pages finish), so a single-file viewer never
    renders "página N+1 de N"."""
    from core.scanners.cancellation import CancellationToken
    from core.scanners.utils.pagination_count import count_documents_by_pagination

    pdf = make_pagination_pdf(tmp_path / "p.pdf", docs=[(2, "F-CRS-ODI-03")])
    seen = []
    count_documents_by_pagination(
        pdf, cancel=CancellationToken(), on_page=lambda d, t: seen.append((d, t))
    )
    assert seen == [(0, 2), (1, 2)]


def test_recover_gap_before_boundary_no_spurious_start():
    # Highest-risk path: a gap right before a real curr==1 boundary must recover to
    # the cycle end (4), NOT invent a second start. dom=4.
    parsed = [(1, 4, "A"), (2, 4, "A"), (3, 4, "A"), (None, None, None), (1, 4, "A")]
    out = recover_sequence(parsed)
    assert _currs(out) == [1, 2, 3, 4, 1]
    assert out[3].status == "recovered"
    assert sum(1 for c in _currs(out) if c == 1) == 2  # exactly two real starts


def test_recover_two_leading_gaps_documented_limitation():
    # Two consecutive leading gaps: only the rightmost of the prefix is recovered
    # (right-neighbor); index 0 stays failed. Undercount-safe, never a spurious start.
    parsed = [(None, None, None), (None, None, None), (3, 4, "A"), (4, 4, "A")]
    out = recover_sequence(parsed)
    assert _status(out) == ["failed", "recovered", "direct", "direct"]
    assert _currs(out) == [None, 2, 3, 4]


def test_dominant_total_tie_prefers_smaller():
    parsed = [(1, 2, "A"), (1, 4, "A")]  # totals 2 and 4 equally frequent
    assert dominant_total(parsed) == 2


# --- F7: recovered document-starts (Task 4.1) ---


def test_count_recovered_starts_counts_recovered_curr_one():
    # dom=2; index1 recovers via left=2%2+1=1 → a recovered curr==1 (fabricated-start risk).
    parsed = [(2, 2, None), (None, None, None), (1, 2, None)]
    reads = recover_sequence(parsed)
    assert count_recovered_starts(reads) == 1


def test_count_recovered_starts_zero_when_no_recovered_reads():
    parsed = [(1, 4, "A"), (2, 4, "A"), (3, 4, "A"), (4, 4, "A")]
    reads = recover_sequence(parsed)
    assert count_recovered_starts(reads) == 0


def test_count_recovered_starts_zero_when_recovered_page_is_not_a_start():
    # Recovered page lands mid-cycle (curr==3), not a start — must not count.
    parsed = [(2, 4, "A"), (None, None, None), (4, 4, "A"), (1, 4, "A")]
    reads = recover_sequence(parsed)
    assert count_recovered_starts(reads) == 0


def test_count_documents_exposes_recovered_start_count(tmp_path, make_pagination_pdf, monkeypatch):
    """F7: the engine result exposes recovered_start_count — mirrors the pure
    recover_sequence case above, through the real OCR orchestrator (corner-text
    mocked for determinism)."""
    from core.scanners.cancellation import CancellationToken
    from core.scanners.utils import pagination_count as pc

    pdf = make_pagination_pdf(tmp_path / "mix.pdf", docs=[(2, "A"), (1, "B")])
    # Keyed by page.number (not an iterator): the stub must be order-independent
    # and thread-safe — the default execution mode OCRs pages concurrently.
    texts = {0: "Pagina 2 de 2", 1: "", 2: "Pagina 1 de 2"}
    monkeypatch.setattr(pc, "_corner_text", lambda page: texts[page.number])

    r = pc.count_documents_by_pagination(pdf, cancel=CancellationToken())
    assert r.recovered_start_count == 1


def test_count_documents_recovered_start_count_zero_when_clean(tmp_path, make_pagination_pdf):
    """No recovered starts on a clean, fully-readable compilation."""
    from core.scanners.cancellation import CancellationToken
    from core.scanners.utils.pagination_count import count_documents_by_pagination

    pdf = make_pagination_pdf(tmp_path / "clean.pdf", docs=[(4, "F-CRS-ART-01")] * 3)
    r = count_documents_by_pagination(pdf, cancel=CancellationToken())
    assert r.recovered_start_count == 0


# --- Threaded page-OCR (perf 2026-07-10) ---


def test_count_documents_threaded_equals_sequential(tmp_path, make_pagination_pdf, monkeypatch):
    """The threaded path is a pure execution change: same PaginationCountResult
    as ocr_threads=1 on the same input, including read stats and codes."""
    from core.scanners.cancellation import CancellationToken
    from core.scanners.utils import pagination_count as pc

    pdf = make_pagination_pdf(
        tmp_path / "eq.pdf", docs=[(3, "F-CRS-ART-01"), (2, "F-CRS-ART-01"), (3, "F-CRS-ART-01")]
    )
    # Deterministic per-page stub with a gap on page 4 (index-keyed, thread-safe).
    texts = {
        0: "Pagina 1 de 3 F-CRS-ART-01",
        1: "Pagina 2 de 3",
        2: "Pagina 3 de 3",
        3: "Pagina 1 de 2 F-CRS-ART-01",
        4: "",
        5: "Pagina 1 de 3 F-CRS-ART-01",
        6: "Pagina 2 de 3",
        7: "Pagina 3 de 3",
    }
    monkeypatch.setattr(pc, "_corner_text", lambda page: texts[page.number])

    seq = pc.count_documents_by_pagination(pdf, cancel=CancellationToken(), ocr_threads=1)
    thr = pc.count_documents_by_pagination(pdf, cancel=CancellationToken(), ocr_threads=6)
    assert seq == thr
    assert thr.count == 3 and thr.recovered_reads == 1


def test_count_documents_threaded_on_page_monotonic(tmp_path, make_pagination_pdf, monkeypatch):
    """Under threads, on_page still emits the exact 0..n-1 counter sequence."""
    from core.scanners.cancellation import CancellationToken
    from core.scanners.utils import pagination_count as pc

    pdf = make_pagination_pdf(tmp_path / "mono.pdf", docs=[(4, "F-CRS-ART-01")] * 2)
    monkeypatch.setattr(pc, "_corner_text", lambda page: f"Pagina {page.number % 4 + 1} de 4")
    seen = []
    pc.count_documents_by_pagination(
        pdf, cancel=CancellationToken(), ocr_threads=6, on_page=lambda d, t: seen.append((d, t))
    )
    assert seen == [(i, 8) for i in range(8)]


def test_count_documents_threaded_cancel_propagates(tmp_path, make_pagination_pdf, monkeypatch):
    """A token cancelled mid-scan raises CancelledError out of the threaded path."""
    from core.scanners.cancellation import CancellationToken, CancelledError
    from core.scanners.utils import pagination_count as pc

    pdf = make_pagination_pdf(tmp_path / "c.pdf", docs=[(4, "F-CRS-ART-01")] * 3)
    cancel = CancellationToken()

    def _text_then_cancel(page):
        cancel.cancel()  # first page read flips the token; queued pages must bail
        return "Pagina 1 de 4"

    monkeypatch.setattr(pc, "_corner_text", _text_then_cancel)
    with pytest.raises(CancelledError):
        pc.count_documents_by_pagination(pdf, cancel=cancel, ocr_threads=2)


@pytest.mark.parametrize("backend", ["pytesseract", "tesserocr"])
def test_count_documents_threaded_error_propagates_and_closes_docs(
    tmp_path, make_pagination_pdf, monkeypatch, backend
):
    """§C2: an unrelated OCR error mid-pool (not a cancellation) must propagate —
    never a silently partial/short count — and every thread-local fitz.Document
    opened by _read_pages_threaded must be closed (no handle leak), even though
    the pool raised mid-way. Parametrized over both OCR backends (Track D §2-c):
    ``_corner_text`` is fully replaced below, so the backend choice doesn't
    change this test's OCR text — the point is proving the thread-pool
    error-propagation + fitz cleanup guarantee holds regardless of which
    backend ``OVERSEER_OCR_BACKEND`` selects."""
    if backend == "tesserocr":
        pytest.importorskip("tesserocr")
    monkeypatch.setenv("OVERSEER_OCR_BACKEND", backend)

    from core.scanners.cancellation import CancellationToken
    from core.scanners.utils import pagination_count as pc

    pdf = make_pagination_pdf(
        tmp_path / "boom.pdf", docs=[(4, "F-CRS-ART-01"), (4, "F-CRS-ART-01"), (4, "F-CRS-ART-01")]
    )

    def _boom(page):
        if page.number == 5:
            raise RuntimeError("ocr exploded")
        return f"Pagina {page.number % 4 + 1} de 4"

    monkeypatch.setattr(pc, "_corner_text", _boom)

    opened_docs = []
    real_open = pc.fitz.open

    def spy_open(*a, **kw):
        doc = real_open(*a, **kw)
        opened_docs.append(doc)
        return doc

    monkeypatch.setattr(pc.fitz, "open", spy_open)

    with pytest.raises(RuntimeError, match="ocr exploded"):
        pc.count_documents_by_pagination(pdf, cancel=CancellationToken(), ocr_threads=4)

    assert opened_docs  # at least one doc opened (main-thread page-count read + workers)
    closed = sum(1 for d in opened_docs if d.is_closed)
    assert closed == len(opened_docs), (
        f"{len(opened_docs) - closed} of {len(opened_docs)} fitz.Document(s) leaked open"
    )


# --- detect_repeated_pattern (Track D / D2, Task 8 — RCH cover de-dup) ---
#
# Ported from eval/pagination_count/engine.py (Task 6 prototype, benchmarked
# in docs/research/2026-07-12-rch-pagination-decision.md). Detects the exact
# signature of the RCH template bug: two ADJACENT pages both reading
# curr == 1 with the same total.


def test_detect_repeated_pattern_false_on_clean_alternation():
    parsed = [(1, 2, "A"), (2, 2, "A"), (1, 2, "A"), (2, 2, "A")]
    assert detect_repeated_pattern(parsed) is False


def test_detect_repeated_pattern_true_on_adjacent_duplicate():
    parsed = [(1, 2, "A"), (1, 2, "A"), (2, 2, "A")]
    assert detect_repeated_pattern(parsed) is True


def test_detect_repeated_pattern_ignores_non_adjacent_duplicates():
    parsed = [(1, 2, "A"), (2, 2, "A"), (1, 2, "A"), (2, 2, "A")]
    assert detect_repeated_pattern(parsed) is False


def test_detect_repeated_pattern_requires_matching_totals():
    # Both curr==1 but different totals — not the RCH bug signature (two
    # genuinely separate 1pp-cover documents back to back).
    parsed = [(1, 2, "A"), (1, 3, "A")]
    assert detect_repeated_pattern(parsed) is False


def test_detect_repeated_pattern_empty_and_single_page():
    assert detect_repeated_pattern([]) is False
    assert detect_repeated_pattern([(1, 2, "A")]) is False


def test_count_documents_exposes_repeated_pattern_detected(
    tmp_path, make_pagination_pdf, monkeypatch
):
    """The engine result surfaces repeated_pattern_detected through the real
    OCR orchestrator (corner-text mocked for determinism) — mirrors
    test_count_documents_exposes_recovered_start_count above."""
    from core.scanners.cancellation import CancellationToken
    from core.scanners.utils import pagination_count as pc

    pdf = make_pagination_pdf(tmp_path / "rch_bug.pdf", docs=[(2, "F-CRS-RCH-01")] * 2)
    # Page 1 (the continuation of doc 1) wrongly repeats "Pagina 1 de 2".
    texts = {
        0: "Pagina 1 de 2",
        1: "Pagina 1 de 2",  # BUG
        2: "Pagina 1 de 2",
        3: "Pagina 2 de 2",
    }
    monkeypatch.setattr(pc, "_corner_text", lambda page: texts[page.number])

    r = pc.count_documents_by_pagination(pdf, cancel=CancellationToken())
    assert r.repeated_pattern_detected is True


def test_count_documents_repeated_pattern_false_when_clean(tmp_path, make_pagination_pdf):
    """No repeated-pattern signature on a clean, correctly-alternating compilation."""
    from core.scanners.cancellation import CancellationToken
    from core.scanners.utils.pagination_count import count_documents_by_pagination

    pdf = make_pagination_pdf(tmp_path / "clean_rch.pdf", docs=[(2, "F-CRS-RCH-01")] * 3)
    r = count_documents_by_pagination(pdf, cancel=CancellationToken())
    assert r.repeated_pattern_detected is False
