"""Tests for the multi-flavor anchor-based cover detector."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from core.scanners.patterns import Flavor
from core.scanners.utils import ocr_backend
from core.scanners.utils.header_band_anchors import (
    _match_flavor,
    _normalize_text,
)


def test_normalize_text_lowercases():
    assert _normalize_text("CONSTRUCTORA Region SUR") == "constructora region sur"


def test_normalize_text_strips_accents():
    assert "REGIÓN" not in _normalize_text("CONSTRUCTORA REGIÓN SUR")
    assert "region" in _normalize_text("CONSTRUCTORA REGIÓN SUR")


def test_normalize_text_collapses_whitespace():
    assert _normalize_text("LISTA   DE   CHEQUEO") == "lista de chequeo"


def test_normalize_text_collapses_slashes_dashes():
    """SI/NO/NA and F-CRS-LCH-05 should normalize predictably so anchors match
    regardless of OCR noise around separators."""
    assert _normalize_text("SI/NO/NA") == "si no na"
    assert _normalize_text("F-CRS-LCH-05") == "f crs lch 05"


# ---------------------------------------------------------------------------
# Task 2.2: _match_flavor helper
# ---------------------------------------------------------------------------


def test_match_flavor_counts_anchors():
    flavor: Flavor = {
        "name": "f_test",
        "anchors": ["ITEM", "ACTIVIDAD", "CUMPLE"],
        "min_match": 2,
    }
    text = _normalize_text("ITEM ACTIVIDAD CUMPLE")
    result = _match_flavor(text, flavor)
    assert result.matched_anchors == ["item", "actividad", "cumple"]
    assert result.passes
    assert not result.anti_anchored


def test_match_flavor_below_min_match_does_not_pass():
    flavor: Flavor = {
        "name": "f_test",
        "anchors": ["A", "B", "C", "D"],
        "min_match": 3,
    }
    text = _normalize_text("A B only")
    result = _match_flavor(text, flavor)
    assert len(result.matched_anchors) == 2
    assert not result.passes


def test_match_flavor_anti_anchor_disqualifies():
    """A5: any anti-anchor match descalifica even if anchors >= min_match."""
    flavor: Flavor = {
        "name": "f_dif_pts_cover",
        "anchors": [
            "REGISTRO DE CHARLA",
            "Nombre de la Capacitación",
            "Cargo Relator",
            "Tiempo duración charla",
        ],
        "min_match": 3,
        "anti_anchors": ["TEST DE COMPRENSIÓN", "F-PETS-CRS"],
    }
    text = _normalize_text(
        "REGISTRO DE CHARLA Nombre de la Capacitación Cargo Relator "
        "Tiempo duración charla TEST DE COMPRENSIÓN"
    )
    result = _match_flavor(text, flavor)
    assert len(result.matched_anchors) == 4
    assert result.anti_anchored
    assert not result.passes


def test_match_flavor_anti_min_match_threshold():
    """Custom anti_min_match: needs ≥ 2 anti-anchor matches to descalificar."""
    flavor: Flavor = {
        "name": "f_test",
        "anchors": ["A", "B"],
        "min_match": 1,
        "anti_anchors": ["X", "Y", "Z"],
        "anti_min_match": 2,
    }
    text = _normalize_text("A X")
    result = _match_flavor(text, flavor)
    assert result.passes  # only 1 anti-anchor matched; 2 needed


# ---------------------------------------------------------------------------
# Task 2.3: near_match signal + missing_anchors
# ---------------------------------------------------------------------------


def test_match_flavor_near_match_flag():
    """A14: a page with min_match - 1 anchors is a near-match candidate."""
    flavor: Flavor = {
        "name": "f_test",
        "anchors": ["A", "B", "C", "D"],
        "min_match": 3,
    }
    text = _normalize_text("A B nothing-else")
    result = _match_flavor(text, flavor)
    assert not result.passes
    assert result.near_match  # 2 == min_match - 1
    assert result.missing_anchors == ["c", "d"]


def test_match_flavor_near_match_not_emitted_when_min_match_1():
    """A14 guard: min_match=1 means 0 anchors is NOT a near-match (would be noise)."""
    flavor: Flavor = {
        "name": "f_test",
        "anchors": ["XYZZY", "QUUX"],
        "min_match": 1,
    }
    text = _normalize_text("completely unrelated content here")
    result = _match_flavor(text, flavor)
    assert not result.passes
    assert not result.near_match  # 0 matches must NOT be a near-match


# ---------------------------------------------------------------------------
# Task 2.4: count_covers_by_anchors main entry
# ---------------------------------------------------------------------------


def test_count_covers_uses_first_passing_flavor(monkeypatch):
    """A page counts as 1 cover if ANY flavor passes (A4, no double-counting)."""
    import core.scanners.utils.header_band_anchors as mod

    page_texts = [
        "ITEM ACTIVIDAD CUMPLE Página 1 de",  # passes f_lch_xx
        "ITEM ACTIVIDAD",  # near-match
        "TITAN CHECK LIST HERRAMIENTAS ELÉCTRICAS",  # passes f_titan
        "unrelated content",  # no match
    ]

    def fake_get_page_count(_path):
        return len(page_texts)

    current_page = {"idx": 0}

    def fake_render(_path, page_idx, **_):
        # Return placeholder image; real OCR is stubbed below. Track the page so
        # the two-pass retry of the same page returns the same text (a page's
        # band always OCRs to the same text, raw or preprocessed).
        current_page["idx"] = page_idx
        return Image.new("RGB", (10, 10), "white")

    def patched_ocr(img, **kw):
        return page_texts[current_page["idx"]]

    # Pinned so this test is deterministic regardless of an ambient
    # OVERSEER_OCR_BACKEND=tesserocr (Task 3 equivalence-gate runs set it
    # process-wide) — this test exercises the pytesseract stub specifically.
    monkeypatch.setenv("OVERSEER_OCR_BACKEND", "pytesseract")
    monkeypatch.setattr(mod, "get_page_count", fake_get_page_count)
    monkeypatch.setattr(mod, "render_page_region", fake_render)
    monkeypatch.setattr(ocr_backend.pytesseract, "image_to_string", patched_ocr)

    flavors: list[Flavor] = [
        {
            "name": "f_lch_xx",
            "anchors": ["ITEM", "ACTIVIDAD", "CUMPLE", "Página 1 de"],
            "min_match": 3,
        },
        {
            "name": "f_titan",
            "anchors": ["TITAN", "CHECK LIST", "HERRAMIENTAS ELÉCTRICAS"],
            "min_match": 3,
        },
    ]

    from core.scanners.utils.header_band_anchors import count_covers_by_anchors

    result = count_covers_by_anchors(
        Path("/fake.pdf"),
        flavors=flavors,
        top_fraction=0.25,
        # ocr_threads=1: this test pins MATCHING semantics; its current_page
        # stub is shared mutable state, only valid on the sequential path.
        ocr_threads=1,
    )
    assert result.count == 2
    assert result.pages_total == 4
    assert sorted(result.matches_per_flavor.keys()) == ["f_lch_xx", "f_titan"]
    assert result.matches_per_flavor["f_lch_xx"] == 1
    assert result.matches_per_flavor["f_titan"] == 1
    # The near-match on page 1 (index 1) lands in telemetry
    assert len(result.near_matches) == 1
    assert result.near_matches[0].page_index == 1
    assert result.near_matches[0].flavor_name == "f_lch_xx"


def test_count_covers_threaded_equals_sequential(monkeypatch):
    """Threaded page OCR is a pure execution change: identical AnchorCountResult
    fields vs ocr_threads=1, page-ordered near-matches included. The stub is
    page-keyed (image tagged with its index) so it is order-independent; pass-2
    inputs (preprocessed ndarrays, untagged) read as empty — a page that fails
    pass 1 also fails pass 2, deterministically."""
    import core.scanners.utils.header_band_anchors as mod

    page_texts = [
        "ITEM ACTIVIDAD CUMPLE",  # passes
        "ITEM ACTIVIDAD",  # near-match on pass 1, pass 2 "" → near from pass 2? no: pass 2 re-matches "" → no near
        "unrelated",  # no match
        "ITEM ACTIVIDAD CUMPLE",  # passes
        "ITEM ACTIVIDAD",
        "ITEM ACTIVIDAD CUMPLE",  # passes
    ]

    def fake_render(_path, page_idx, **_):
        im = Image.new("RGB", (10, 10), "white")
        im.info["pi"] = page_idx
        return im

    def patched_ocr(img, **kw):
        if isinstance(img, Image.Image):
            return page_texts[img.info["pi"]]
        return ""  # pass-2 preprocessed ndarray — page identity gone, no match

    # Pinned so this test is deterministic regardless of an ambient
    # OVERSEER_OCR_BACKEND=tesserocr (Task 3 equivalence-gate runs set it
    # process-wide) — this test exercises the pytesseract stub specifically.
    monkeypatch.setenv("OVERSEER_OCR_BACKEND", "pytesseract")
    monkeypatch.setattr(mod, "get_page_count", lambda _p: len(page_texts))
    monkeypatch.setattr(mod, "render_page_region", fake_render)
    monkeypatch.setattr(ocr_backend.pytesseract, "image_to_string", patched_ocr)

    flavors: list[Flavor] = [
        {"name": "f_lch_xx", "anchors": ["ITEM", "ACTIVIDAD", "CUMPLE"], "min_match": 3},
    ]
    kw = dict(flavors=flavors, top_fraction=0.25)
    seq = mod.count_covers_by_anchors(Path("/fake.pdf"), ocr_threads=1, **kw)
    thr = mod.count_covers_by_anchors(Path("/fake.pdf"), ocr_threads=6, **kw)
    assert (seq.count, seq.pages_total, seq.matches_per_flavor) == (
        thr.count,
        thr.pages_total,
        thr.matches_per_flavor,
    )
    assert [n.page_index for n in seq.near_matches] == [n.page_index for n in thr.near_matches]
    assert thr.count == 3


def test_count_covers_threaded_on_page_monotonic(monkeypatch):
    """on_page under threads emits the exact 0..n-1 counter sequence."""
    import core.scanners.utils.header_band_anchors as mod

    def fake_render(_path, page_idx, **_):
        im = Image.new("RGB", (10, 10), "white")
        im.info["pi"] = page_idx
        return im

    monkeypatch.setattr(mod, "get_page_count", lambda _p: 8)
    monkeypatch.setattr(mod, "render_page_region", fake_render)
    monkeypatch.setattr(
        ocr_backend.pytesseract,
        "image_to_string",
        lambda img, **kw: "ITEM ACTIVIDAD CUMPLE" if isinstance(img, Image.Image) else "",
    )

    seen = []
    mod.count_covers_by_anchors(
        Path("/fake.pdf"),
        flavors=[{"name": "f", "anchors": ["ITEM", "ACTIVIDAD", "CUMPLE"], "min_match": 3}],
        ocr_threads=6,
        on_page=lambda d, t: seen.append((d, t)),
    )
    assert seen == [(i, 8) for i in range(8)]


def _stub_ocr_text(monkeypatch, backend, text):
    """Stub whatever engine ocr_backend routes *backend* to, always returning *text*."""
    if backend == "tesserocr":

        class _FakeAPI:
            def SetImage(self, img):  # noqa: N802 - matches tesserocr's real method name
                pass

            def GetUTF8Text(self):  # noqa: N802 - matches tesserocr's real method name
                return text

        class _FakeTesserocrModule:
            def PyTessBaseAPI(self, **kw):  # noqa: N802 - matches tesserocr's real class name
                return _FakeAPI()

        monkeypatch.setattr(ocr_backend, "tesserocr", _FakeTesserocrModule())
    else:
        monkeypatch.setattr(ocr_backend.pytesseract, "image_to_string", lambda img, **kw: text)


@pytest.mark.parametrize("backend", ["pytesseract", "tesserocr"])
def test_count_covers_threaded_error_propagates(monkeypatch, backend):
    """§C2: a render error on one page mid-pool (ocr_threads>=2) must propagate
    — never a silently partial/short count — and the executor must not hang.
    Parametrized over both OCR backends (Track D §2-c) — the render error
    fires before any OCR call, so both params use a fixed OCR stub; the point
    is proving this thread-pool guarantee also holds with tesserocr live."""
    if backend == "tesserocr":
        pytest.importorskip("tesserocr")
    monkeypatch.setenv("OVERSEER_OCR_BACKEND", backend)

    import core.scanners.utils.header_band_anchors as mod
    from core.scanners.utils.pdf_render import PdfRenderError

    def fake_render(_path, page_idx, **_):
        if page_idx == 3:
            raise PdfRenderError("boom")
        im = Image.new("RGB", (10, 10), "white")
        im.info["pi"] = page_idx
        return im

    monkeypatch.setattr(mod, "get_page_count", lambda _p: 6)
    monkeypatch.setattr(mod, "render_page_region", fake_render)
    _stub_ocr_text(monkeypatch, backend, "ITEM ACTIVIDAD CUMPLE")

    with pytest.raises(PdfRenderError, match="boom"):
        mod.count_covers_by_anchors(
            Path("/fake.pdf"),
            flavors=[{"name": "f", "anchors": ["ITEM", "ACTIVIDAD", "CUMPLE"], "min_match": 3}],
            ocr_threads=4,
        )
