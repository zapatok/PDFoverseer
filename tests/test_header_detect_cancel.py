"""count_form_codes honra cancelación por página — FASE 5 Feature 2."""

from pathlib import Path

import pytest
from PIL import Image

from core.scanners.cancellation import CancellationToken, CancelledError
from core.scanners.utils import header_detect


def _patch_render(monkeypatch, render_calls, pages):
    monkeypatch.setattr(header_detect, "get_page_count", lambda p: pages)

    def fake_render(pdf_path, page_idx, *, bbox, dpi):
        render_calls.append(page_idx)
        return Image.new("RGB", (10, 10))

    monkeypatch.setattr(header_detect, "render_page_region", fake_render)
    monkeypatch.setattr(header_detect.pytesseract, "image_to_string", lambda *a, **k: "")


def test_precancelled_token_stops_before_first_page(monkeypatch):
    render_calls: list[int] = []
    _patch_render(monkeypatch, render_calls, pages=20)
    token = CancellationToken()
    token.cancel()

    with pytest.raises(CancelledError):
        header_detect.count_form_codes(Path("dummy.pdf"), sigla_code="ODI", cancel=token)

    assert render_calls == []


def test_cancel_mid_loop_stops_within_a_few_pages(monkeypatch):
    render_calls: list[int] = []
    _patch_render(monkeypatch, render_calls, pages=20)
    token = CancellationToken()
    real_render = header_detect.render_page_region

    def render_then_maybe_cancel(pdf_path, page_idx, *, bbox, dpi):
        img = real_render(pdf_path, page_idx, bbox=bbox, dpi=dpi)
        if len(render_calls) >= 3:
            token.cancel()
        return img

    monkeypatch.setattr(header_detect, "render_page_region", render_then_maybe_cancel)

    with pytest.raises(CancelledError):
        header_detect.count_form_codes(Path("dummy.pdf"), sigla_code="ODI", cancel=token)

    assert len(render_calls) <= 5


def test_no_cancel_param_still_works(monkeypatch):
    render_calls: list[int] = []
    _patch_render(monkeypatch, render_calls, pages=3)

    result = header_detect.count_form_codes(Path("dummy.pdf"), sigla_code="ODI")

    assert result.pages_total == 3
    assert len(render_calls) == 3
