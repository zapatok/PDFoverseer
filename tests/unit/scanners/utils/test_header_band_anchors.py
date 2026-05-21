"""Tests for the multi-flavor anchor-based cover detector."""

from __future__ import annotations

from core.scanners.utils.header_band_anchors import _normalize_text


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
