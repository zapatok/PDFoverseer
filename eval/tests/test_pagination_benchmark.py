"""Tests for eval/pagination_count/benchmark.py and report.py.

DATA-SAFETY: all tests use synthetic PDFs only (make_pagination_pdf fixture from
the root conftest.py, or the module-scoped raw-fitz equivalent below).  No real
corpus files are read.  The synthetic sample list is built inline here; SAMPLES
from samples.py is NOT used (it points at real corpus paths).
"""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from eval.pagination_count.benchmark import extract_sample, run_benchmark
from eval.pagination_count.report import render_report
from eval.pagination_count.samples import Sample

# ---------------------------------------------------------------------------
# Helpers — build a synthetic corpus tree
# ---------------------------------------------------------------------------


def _draw_pagination_pdf(path, docs, landscape=False) -> None:
    """Raw-fitz equivalent of the root conftest's ``make_pagination_pdf`` fixture.

    Duplicated (not imported) on purpose: ``make_pagination_pdf`` is a
    function-scoped fixture (its returned closure is torn down per test), so
    the module-scoped ``benchmark_rows`` fixture below cannot depend on it
    (pytest ScopeMismatch — verified: even a zero-dependency fixture is
    rejected when its own declared scope is narrower than the requester's).
    Keep this in sync with ``conftest.py::make_pagination_pdf`` if that drawing
    logic ever changes.
    """
    doc = fitz.open()
    rect = fitz.paper_rect("a4-l" if landscape else "a4")
    for n_pages, code in docs:
        for c in range(1, n_pages + 1):
            page = doc.new_page(width=rect.width, height=rect.height)
            x = page.rect.width - 230
            page.insert_text((x, 36), f"Codigo: {code}", fontsize=10)
            page.insert_text((x, 52), f"Pagina {c} de {n_pages}", fontsize=10)
            page.insert_text((72, 200), "contenido de prueba", fontsize=12)
    doc.save(path)
    doc.close()


def _build_corpus_samples() -> list[Sample]:
    """The Sample list matching ``_make_corpus`` and the ``benchmark_rows`` fixture."""
    return [
        Sample(
            sigla="art",
            glob="HLL/7.-ART/*art*.pdf",
            page_range=None,
            gt=3,
            gt_source="synthetic",
        ),
        Sample(
            sigla="bodega",
            glob="HLL/9.-Inspeccion Bodega/*bodega*.pdf",
            page_range=None,
            gt=2,
            gt_source="synthetic",
        ),
    ]


def _make_corpus(tmp_path: Path, make_pagination_pdf) -> tuple[Path, list[Sample]]:
    """Build a minimal synthetic corpus tree and matching Sample list.

    Structure::

        tmp_path/
          MAYO/
            HLL/7.-ART/
              art_smp.pdf      (3 docs × 4pp each = 12 pages)
            HLL/9.-Inspeccion Bodega/
              bodega_smp.pdf   (2 docs × 1pp each = 2 pages)

    Samples use globs that match these files.  ``gt`` values match the exact
    number of docs baked into each synthetic PDF.
    """
    mayo = tmp_path / "MAYO"

    # ART: 3 documents × 4 pages
    art_dir = mayo / "HLL" / "7.-ART"
    art_dir.mkdir(parents=True)
    make_pagination_pdf(
        art_dir / "art_smp.pdf",
        docs=[(4, "F-CRS-ART-01")] * 3,
    )

    # BODEGA: 2 documents × 1 page (A7 path — single-page PDFs)
    bodega_dir = mayo / "HLL" / "9.-Inspeccion Bodega"
    bodega_dir.mkdir(parents=True)
    make_pagination_pdf(
        bodega_dir / "bodega_smp.pdf",
        docs=[(1, "F-CRS-BOD-01")] * 2,
    )

    return tmp_path, _build_corpus_samples()


@pytest.fixture(scope="module")
def benchmark_rows(tmp_path_factory) -> list[dict]:
    """Run ``run_benchmark`` ONCE for the whole module and share the rows.

    Module-scoped fixtures can't depend on ``tmp_path``/``make_pagination_pdf``
    (both function-scoped — ScopeMismatch), so the synthetic corpus is built
    here via ``tmp_path_factory`` + ``_draw_pagination_pdf`` directly. Only the
    tests that consume the default (art + bodega) sample set unmodified use
    this; ``test_run_benchmark_skips_missing_glob`` and
    ``test_run_benchmark_temp_dir_cleaned_up`` mutate the sample list / patch
    module internals, so they keep their own independent run.
    """
    root = tmp_path_factory.mktemp("benchmark_corpus")
    mayo = root / "MAYO"
    art_dir = mayo / "HLL" / "7.-ART"
    art_dir.mkdir(parents=True)
    _draw_pagination_pdf(art_dir / "art_smp.pdf", docs=[(4, "F-CRS-ART-01")] * 3)
    bodega_dir = mayo / "HLL" / "9.-Inspeccion Bodega"
    bodega_dir.mkdir(parents=True)
    _draw_pagination_pdf(bodega_dir / "bodega_smp.pdf", docs=[(1, "F-CRS-BOD-01")] * 2)

    samples = _build_corpus_samples()
    return run_benchmark(samples=samples, root=root)


# ---------------------------------------------------------------------------
# extract_sample
# ---------------------------------------------------------------------------


def test_extract_sample_creates_pdf(tmp_path, make_pagination_pdf):
    """extract_sample copies the matched corpus file into dest_dir."""
    root, samples = _make_corpus(tmp_path, make_pagination_pdf)
    dest = tmp_path / "dest"
    dest.mkdir()
    out = extract_sample(samples[0], root, dest)
    assert out.exists()
    assert out.suffix == ".pdf"
    # sigla token in filename so production scanner can glob it
    assert "art" in out.name


def test_extract_sample_page_range(tmp_path, make_pagination_pdf):
    """page_range=(0,4) extracts only 4 pages from a 12-page PDF."""
    import fitz

    root, samples = _make_corpus(tmp_path, make_pagination_pdf)
    dest = tmp_path / "dest2"
    dest.mkdir()
    sliced_sample = Sample(
        sigla="art",
        glob="HLL/7.-ART/*art*.pdf",
        page_range=(0, 4),
        gt=1,
        gt_source="synthetic",
    )
    out = extract_sample(sliced_sample, root, dest)
    with fitz.open(out) as doc:
        assert doc.page_count == 4


def test_extract_sample_raises_when_no_match(tmp_path, make_pagination_pdf):
    """extract_sample raises FileNotFoundError for a non-matching glob."""
    root, _ = _make_corpus(tmp_path, make_pagination_pdf)
    dest = tmp_path / "dest3"
    dest.mkdir()
    bad_sample = Sample(
        sigla="art",
        glob="HLL/7.-ART/*nonexistent*.pdf",
        page_range=None,
        gt=1,
        gt_source="synthetic",
    )
    with pytest.raises(FileNotFoundError):
        extract_sample(bad_sample, root, dest)


# ---------------------------------------------------------------------------
# run_benchmark
# ---------------------------------------------------------------------------


def test_run_benchmark_returns_one_row_per_sample(benchmark_rows):
    """run_benchmark returns exactly one row for each sample in the list."""
    assert len(benchmark_rows) == len(_build_corpus_samples())


def test_run_benchmark_row_has_required_keys(benchmark_rows):
    """Every row contains the full set of required keys."""
    required = {
        "sigla",
        "file",
        "pages",
        "gt",
        "gt_source",
        "current_count",
        "current_method",
        "current_delta",
        "pag_count",
        "pag_delta",
        "recovered",
        "failed",
        "dominant_total",
        "codes",
    }
    for row in benchmark_rows:
        missing = required - row.keys()
        assert not missing, f"Row for {row.get('sigla')} missing keys: {missing}"


def test_run_benchmark_art_pag_count(benchmark_rows):
    """The pagination engine counts exactly 3 documents in the synthetic ART PDF
    (3 × 4-page documents with clean 'Pagina C de 4' text)."""
    art_rows = [r for r in benchmark_rows if r["sigla"] == "art"]
    assert len(art_rows) == 1
    row = art_rows[0]
    assert row["pag_count"] == 3, f"Expected pag_count=3, got {row['pag_count']}"
    assert row["pag_delta"] == 0, f"Expected pag_delta=0, got {row['pag_delta']}"


def test_run_benchmark_delta_computed_correctly(benchmark_rows):
    """current_delta and pag_delta are count - gt."""
    for row in benchmark_rows:
        assert row["current_delta"] == row["current_count"] - row["gt"]
        assert row["pag_delta"] == row["pag_count"] - row["gt"]


def test_run_benchmark_skips_missing_glob(tmp_path, make_pagination_pdf):
    """Samples whose glob finds no file are silently skipped (no exception)."""
    root, samples = _make_corpus(tmp_path, make_pagination_pdf)
    bad = Sample(
        sigla="art",
        glob="HLL/7.-ART/*ghost*.pdf",
        page_range=None,
        gt=1,
        gt_source="synthetic",
    )
    # Should not raise; bad sample is dropped
    rows = run_benchmark(samples=[bad, samples[0]], root=root)
    # Only the good sample produces a row
    assert len(rows) == 1
    assert rows[0]["sigla"] == "art"


def test_run_benchmark_temp_dir_cleaned_up(tmp_path, make_pagination_pdf):
    """Extracted PDFs do not persist after run_benchmark returns."""
    import tempfile

    root, samples = _make_corpus(tmp_path, make_pagination_pdf)
    created_tmps: list[str] = []
    _orig = tempfile.TemporaryDirectory

    class _Tracked(_orig):
        def __enter__(self):
            result = super().__enter__()
            created_tmps.append(result)
            return result

    import eval.pagination_count.benchmark as bm_mod

    orig_td = bm_mod.tempfile.TemporaryDirectory
    bm_mod.tempfile.TemporaryDirectory = _Tracked  # type: ignore[attr-defined]
    try:
        run_benchmark(samples=samples, root=root)
    finally:
        bm_mod.tempfile.TemporaryDirectory = orig_td  # type: ignore[attr-defined]

    # All tracked temp dirs should be cleaned up
    for td in created_tmps:
        assert not Path(td).exists(), f"Temp dir still exists: {td}"


# ---------------------------------------------------------------------------
# render_report
# ---------------------------------------------------------------------------


def _make_rows() -> list[dict]:
    """Minimal synthetic rows for report tests — no real data."""
    return [
        {
            "sigla": "art",
            "pages": 12,
            "gt": 3,
            "gt_source": "synthetic",
            "note": "",
            "current_count": 3,
            "current_method": "v4",
            "current_delta": 0,
            "pag_count": 3,
            "pag_delta": 0,
            "recovered": 0,
            "failed": 0,
            "dominant_total": 4,
            "codes": {"F-CRS-ART-01": 12},
        },
        {
            "sigla": "odi",
            "pages": 21,
            "gt": 21,
            "gt_source": "DB filename_glob",
            "note": "",
            "current_count": 18,
            "current_method": "anchors",
            "current_delta": -3,
            "pag_count": 21,
            "pag_delta": 0,
            "recovered": 2,
            "failed": 0,
            "dominant_total": 1,
            "codes": {},
        },
        {
            "sigla": "odi",
            "pages": 10,
            "gt": 10,
            "gt_source": "eye",
            "note": "second odi sample",
            "current_count": 8,
            "current_method": "anchors",
            "current_delta": -2,
            "pag_count": 9,
            "pag_delta": -1,
            "recovered": 1,
            "failed": 0,
            "dominant_total": 1,
            "codes": {},
        },
    ]


def test_render_report_contains_markdown_table_header(tmp_path):
    """render_report returns a string containing the expected table header."""
    report = render_report(_make_rows())
    assert "| sigla |" in report
    assert "| pages |" in report
    assert "| GT |" in report
    assert "| current (Δ) |" in report
    assert "| pagination (Δ) |" in report


def test_render_report_contains_migrate_verdict():
    """A sigla where |pag_delta| <= |current_delta| gets MIGRATE verdict."""
    rows = _make_rows()
    report = render_report(rows)
    # 'odi' has Σ|current_delta|=5, Σ|pag_delta|=1 → MIGRATE
    assert "MIGRATE" in report


def test_render_report_contains_keep_verdict():
    """A sigla where |pag_delta| > |current_delta| gets KEEP verdict."""
    rows = [
        {
            "sigla": "charla",
            "pages": 36,
            "gt": 36,
            "gt_source": "eye",
            "note": "RCH control",
            "current_count": 36,
            "current_method": "anchors",
            "current_delta": 0,
            "pag_count": 18,  # pagination mis-counts RCH "1 de 2" bug
            "pag_delta": -18,
            "recovered": 0,
            "failed": 0,
            "dominant_total": 2,
            "codes": {},
        }
    ]
    report = render_report(rows)
    assert "KEEP" in report


def test_render_report_migrate_when_equal_delta():
    """When |pag_delta| == |current_delta|, verdict is still MIGRATE (tie goes to new)."""
    rows = [
        {
            "sigla": "ext",
            "pages": 38,
            "gt": 38,
            "gt_source": "DB filename_glob",
            "note": "",
            "current_count": 36,
            "current_method": "anchors",
            "current_delta": -2,
            "pag_count": 36,
            "pag_delta": -2,
            "recovered": 0,
            "failed": 0,
            "dominant_total": 1,
            "codes": {},
        }
    ]
    report = render_report(rows)
    assert "MIGRATE" in report


def test_render_report_all_siglas_in_rollup():
    """Every sigla that appears in the rows appears in the per-sigla roll-up."""
    rows = _make_rows()
    report = render_report(rows)
    # Both 'art' and 'odi' should appear in the roll-up section
    rollup_section = report.split("## Per-sigla verdict")[1]
    assert "art" in rollup_section
    assert "odi" in rollup_section
