"""Tests for the multi-flavor anchor-based cover detector."""

from __future__ import annotations

from core.scanners.patterns import Flavor
from core.scanners.utils.header_band_anchors import (
    FlavorMatchResult,
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
