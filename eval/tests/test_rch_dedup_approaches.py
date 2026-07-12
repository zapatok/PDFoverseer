"""Tests for the RCH de-dup approach prototypes (Track D / D2, Task 6).

Pure-data tests (no OCR/PDF I/O): each synthetic case's ``RchPageSpec`` list
IS the per-page pagination read a perfect OCR would produce, so it converts
directly to the ``parsed`` shape the engine functions consume — fast,
deterministic, matches the "Pure functions … unit-tested directly" idiom
already used for ``parse_pagination``/``dominant_total``/``recover_sequence``.

One integration test (``test_make_rch_pdf_roundtrips_through_production_pagination_reader``)
renders an actual PDF via ``make_rch_pdf`` and reads it back through the
production ``pagination_count`` corner OCR, as a sanity check that the
generator's text placement is genuinely OCR-readable (guards against the
generator drifting from what real Tesseract/tesserocr output looks like).

The 4 non-adversarial cases (uniform_2pp, mixed_2_3pp, illegible_cover,
appendix_no_pagination) reproduce the pattern Fase 0 actually MEASURED
(docs/research/2026-07-12-rch-corner-survey.md) — none of them trigger
``detect_repeated_pattern``. The 2 adversarial cases
(bug_repeated_pagination, bug_all_pages_read_1) are NOT measured; they exist
solely to prove the fallback/arithmetic trigger paths engage when the
pattern they guard against actually appears (an untested safety net proves
nothing).
"""

from __future__ import annotations

import pytest

from eval.pagination_count.engine import (
    count_by_arithmetic_dedup,
    count_by_hybrid_fallback,
    count_by_region_discriminator,
    count_starts,
    detect_repeated_pattern,
    recover_sequence,
)
from eval.pagination_count.samples import (
    RchPageSpec,
    make_rch_pdf,
    rch_case_appendix_no_pagination,
    rch_case_bug_all_pages_read_1,
    rch_case_bug_repeated_pagination,
    rch_case_illegible_cover,
    rch_case_mixed_2_3pp,
    rch_case_uniform_2pp,
)


def _to_parsed(pages: list[RchPageSpec]) -> list[tuple[int | None, int | None, str | None]]:
    """Convert a synthetic page-spec list into the engine's ``parsed`` shape."""
    return [
        (p.printed_curr, p.printed_total, p.code if p.printed_curr is not None else None)
        for p in pages
    ]


def _anchor_hits(pages: list[RchPageSpec]) -> list[bool]:
    return [p.cover_anchors for p in pages]


# ---------------------------------------------------------------------------
# detect_repeated_pattern — measured cases stay silent, the bug case fires
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case_pages",
    [
        rch_case_uniform_2pp(6),
        rch_case_mixed_2_3pp(),
        rch_case_illegible_cover(),
        rch_case_appendix_no_pagination(),
    ],
    ids=["uniform_2pp", "mixed_2_3pp", "illegible_cover", "appendix_no_pagination"],
)
def test_detect_repeated_pattern_absent_on_measured_cases(case_pages):
    """None of the 4 Fase-0-measured cases trigger the bug signature."""
    assert detect_repeated_pattern(_to_parsed(case_pages)) is False


def test_detect_repeated_pattern_fires_on_bug_case():
    """The adversarial case (continuation repeats 'Página 1 de 2') is detected."""
    assert detect_repeated_pattern(_to_parsed(rch_case_bug_repeated_pagination())) is True


def test_detect_repeated_pattern_ignores_non_adjacent_duplicates():
    """Two curr==1 reads that are NOT adjacent do not trigger (different documents)."""
    parsed = [(1, 2, "A"), (2, 2, "A"), (1, 2, "A"), (2, 2, "A")]
    assert detect_repeated_pattern(parsed) is False


# ---------------------------------------------------------------------------
# Approach 1 — arithmetic de-dup (spec candidate 1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case_pages",
    [
        rch_case_uniform_2pp(6),
        rch_case_mixed_2_3pp(),
        rch_case_illegible_cover(),
        rch_case_appendix_no_pagination(),
    ],
    ids=["uniform_2pp", "mixed_2_3pp", "illegible_cover", "appendix_no_pagination"],
)
def test_arithmetic_dedup_never_fires_on_measured_cases(case_pages):
    """Fase 0 found no real sample where EVERY page reads curr==1 — the
    approach's one trigger condition never holds on measured data, so it
    returns None (not applicable) rather than a (potentially wrong) count."""
    assert count_by_arithmetic_dedup(_to_parsed(case_pages)) is None


def test_arithmetic_dedup_fires_on_the_extreme_adversarial_case():
    """When literally every page reads curr==1 (unmeasured worst case), the
    approach fires and recovers the true document count via ceil(pages/M)."""
    pages = rch_case_bug_all_pages_read_1(n_docs=3, doc_len=2)
    assert count_by_arithmetic_dedup(_to_parsed(pages)) == 3


def test_arithmetic_dedup_empty_input():
    assert count_by_arithmetic_dedup([]) is None


# ---------------------------------------------------------------------------
# Approach 2 — region discriminator (spec candidate 2, corrected region)
# ---------------------------------------------------------------------------


def test_region_discriminator_counts_confirmed_covers_uniform():
    pages = rch_case_uniform_2pp(6)
    parsed = _to_parsed(pages)
    assert count_by_region_discriminator(parsed, _anchor_hits(pages)) == 6


def test_region_discriminator_counts_confirmed_covers_mixed():
    pages = rch_case_mixed_2_3pp()
    parsed = _to_parsed(pages)
    assert count_by_region_discriminator(parsed, _anchor_hits(pages)) == 3


def test_region_discriminator_is_undercount_safe_on_unconfirmed_candidate():
    """A curr==1 candidate with no anchor confirmation silently drops — never
    inflates the count (the undercount-safe property Task 6 Step 3 requires)."""
    parsed = [(1, 2, "A"), (2, 2, "A")]
    assert count_by_region_discriminator(parsed, [False, False]) == 0


def test_region_discriminator_ignores_illegible_cover_recovery_fabrication():
    """Unlike plain recovery-based counting, the discriminator does NOT confirm
    the recovered appendix page as a document start (no anchor text there) —
    it under-counts safely instead of fabricating a 3rd document."""
    pages = rch_case_appendix_no_pagination()
    parsed = _to_parsed(pages)
    # Plain recovery-based counting fabricates a 3rd start from the trailing
    # appendix pages (F7 in production — flagged LOW, not fixed by any of
    # these 3 approaches); the discriminator, given honest anchor_hits (no
    # cover text was placed on the appendix), stays at the true 2 real covers.
    assert count_starts(recover_sequence(parsed), None) == 3
    assert count_by_region_discriminator(parsed, _anchor_hits(pages)) == 2


def test_region_discriminator_length_mismatch_raises():
    with pytest.raises(ValueError, match="same length"):
        count_by_region_discriminator([(1, 2, "A")], [True, False])


# ---------------------------------------------------------------------------
# Approach 3 — hybrid detect-and-fallback (spec candidate 3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case_pages,expected",
    [
        (rch_case_uniform_2pp(6), 6),
        (rch_case_mixed_2_3pp(), 3),
        (rch_case_illegible_cover(), 3),
        (rch_case_appendix_no_pagination(), 3),
    ],
    ids=["uniform_2pp", "mixed_2_3pp", "illegible_cover", "appendix_no_pagination"],
)
def test_hybrid_fallback_matches_plain_pagination_on_measured_cases(case_pages, expected):
    """No repeated pattern on any measured case → hybrid takes the plain
    (recovery-based) branch, identical to today's production pagination
    count — full speed, no anchors OCR needed."""
    parsed = _to_parsed(case_pages)
    assert count_by_hybrid_fallback(parsed, anchors_fallback_count=None) == expected


def test_hybrid_fallback_avoids_the_overcount_when_the_bug_fires():
    """Plain pagination WOULD overcount (3 instead of the true 2) when the
    bug fires; the hybrid approach detects it and defers to the (correct)
    anchors count instead."""
    parsed = _to_parsed(rch_case_bug_repeated_pagination())
    assert count_starts(recover_sequence(parsed), None) == 3  # plain: wrong
    assert count_by_hybrid_fallback(parsed, anchors_fallback_count=2) == 2  # hybrid: correct


def test_hybrid_fallback_requires_a_fallback_count_when_pattern_fires():
    parsed = _to_parsed(rch_case_bug_repeated_pagination())
    with pytest.raises(ValueError, match="anchors_fallback_count"):
        count_by_hybrid_fallback(parsed, anchors_fallback_count=None)


# ---------------------------------------------------------------------------
# Generator sanity — the synthetic PDF is genuinely OCR-readable
# ---------------------------------------------------------------------------


def test_make_rch_pdf_roundtrips_through_production_pagination_reader(tmp_path):
    """The generator's corner text round-trips through the REAL production
    pagination engine (not just the pure-data shortcut used above) — guards
    against the fixture generator silently drifting from genuine OCR output."""
    from core.scanners.cancellation import CancellationToken
    from core.scanners.utils.pagination_count import count_documents_by_pagination

    pdf_path = tmp_path / "rch_uniform.pdf"
    make_rch_pdf(pdf_path, rch_case_uniform_2pp(3))

    result = count_documents_by_pagination(pdf_path, cancel=CancellationToken())

    assert result.count == 3
    assert result.pages_total == 6
    assert result.dominant_total == 2
