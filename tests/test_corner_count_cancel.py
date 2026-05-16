"""count_paginations honra cancelación por página — FASE 5 Feature 2."""

from pathlib import Path

import pytest
from PIL import Image

from core.scanners.cancellation import CancellationToken, CancelledError
from core.scanners.utils import corner_count


def _patch_render(monkeypatch, render_calls, pages):
    """Render/OCR instantáneos y get_page_count fijo — el test es de flujo de
    control, no de OCR real."""
    monkeypatch.setattr(corner_count, "get_page_count", lambda p: pages)

    def fake_render(pdf_path, page_idx, *, bbox, dpi):
        render_calls.append(page_idx)
        return Image.new("RGB", (10, 10))

    monkeypatch.setattr(corner_count, "render_page_region", fake_render)
    monkeypatch.setattr(corner_count.pytesseract, "image_to_string", lambda *a, **k: "")


def test_precancelled_token_stops_before_first_page(monkeypatch):
    render_calls: list[int] = []
    _patch_render(monkeypatch, render_calls, pages=20)
    token = CancellationToken()
    token.cancel()

    with pytest.raises(CancelledError):
        corner_count.count_paginations(Path("dummy.pdf"), cancel=token)

    assert render_calls == []  # cortó antes de renderizar la página 0


def test_cancel_mid_loop_stops_within_a_few_pages(monkeypatch):
    render_calls: list[int] = []
    _patch_render(monkeypatch, render_calls, pages=20)

    # Token que se cancela cuando ya se renderizaron 3 páginas.
    token = CancellationToken()

    real_render = corner_count.render_page_region

    def render_then_maybe_cancel(pdf_path, page_idx, *, bbox, dpi):
        img = real_render(pdf_path, page_idx, bbox=bbox, dpi=dpi)
        if len(render_calls) >= 3:
            token.cancel()
        return img

    monkeypatch.setattr(corner_count, "render_page_region", render_then_maybe_cancel)

    with pytest.raises(CancelledError):
        corner_count.count_paginations(Path("dummy.pdf"), cancel=token)

    # Se detuvo a mitad: renderizó ~3-4 páginas, no las 20.
    assert len(render_calls) <= 5


def test_no_cancel_param_still_works(monkeypatch):
    """Backward compat: cancel es opcional, default None."""
    render_calls: list[int] = []
    _patch_render(monkeypatch, render_calls, pages=3)

    result = corner_count.count_paginations(Path("dummy.pdf"))

    assert result.pages_total == 3
    assert len(render_calls) == 3
