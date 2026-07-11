"""cell_page_counts: cache por firma stat (2026-07-10) — el endpoint de files
pagaba ~0.75 s abriendo los 1,300 PDFs de HPV|art en CADA request."""

from api.routes.sessions import _common


def _make_pdf(path, pages=1):
    real_open = _common.fitz.open
    doc = real_open()
    for _ in range(pages):
        doc.new_page()
    doc.save(path)
    doc.close()


def _counting_open(monkeypatch):
    real_open = _common.fitz.open
    calls = {"n": 0}

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real_open(*args, **kwargs)

    monkeypatch.setattr(_common.fitz, "open", counting)
    return calls


def test_second_call_hits_cache_no_reopen(tmp_path, monkeypatch):
    _make_pdf(tmp_path / "a.pdf", pages=1)
    _make_pdf(tmp_path / "b.pdf", pages=3)
    calls = _counting_open(monkeypatch)

    first = _common.cell_page_counts(tmp_path)
    assert first == {"a.pdf": 1, "b.pdf": 3}
    assert calls["n"] == 2

    second = _common.cell_page_counts(tmp_path)
    assert second == first
    assert calls["n"] == 2  # cache hit: cero opens


def test_rewritten_file_invalidates_only_itself(tmp_path, monkeypatch):
    _make_pdf(tmp_path / "a.pdf", pages=1)
    _make_pdf(tmp_path / "b.pdf", pages=1)
    _common.cell_page_counts(tmp_path)  # poblar cache

    _make_pdf(tmp_path / "a.pdf", pages=2)  # rewrite → stat cambia
    calls = _counting_open(monkeypatch)
    out = _common.cell_page_counts(tmp_path)
    assert out == {"a.pdf": 2, "b.pdf": 1}
    assert calls["n"] == 1  # solo a.pdf se re-abre


def test_unreadable_pdf_reports_zero_and_is_not_cached(tmp_path, monkeypatch):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")

    out = _common.cell_page_counts(tmp_path)
    assert out == {"bad.pdf": 0}

    # Sigue intentándose en el próximo request (el 0 no queda cacheado):
    # si el archivo se vuelve legible con la MISMA firma no importa — lo que
    # pineamos es que el path de error no envenena el cache.
    calls = _counting_open(monkeypatch)
    out2 = _common.cell_page_counts(tmp_path)
    assert out2 == {"bad.pdf": 0}
    assert calls["n"] == 1  # re-open intentado (no hubo hit)
