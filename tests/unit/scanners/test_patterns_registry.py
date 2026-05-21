"""Tests for the central patterns registry."""

from __future__ import annotations

import re

import pytest

from core.scanners.patterns import (
    PATTERNS,
    SCAN_STRATEGIES,
    Flavor,
    SiglaPattern,
    get_pattern,
)


def test_pattern_for_reunion_has_strategy_none():
    pattern = get_pattern("reunion")
    assert pattern["scan_strategy"] == "none"


def test_pattern_for_reunion_filename_glob_is_lax():
    """A10: lax pattern captures HLL mega `2026-04_reunion.pdf` AND
    canonical `2026-04-15_reunion_supervisor.pdf`."""
    pattern = get_pattern("reunion")
    rx = re.compile(pattern["filename_glob"], re.IGNORECASE)
    assert rx.match("2026-04-15_reunion_supervisor.pdf")
    assert rx.match("2026-04_reunion.pdf")  # mega HLL, sin día
    assert rx.match("REUNION_OLD.PDF")  # case-insensitive
    assert not rx.match("notice.pdf")  # debe rechazar


def test_get_pattern_unknown_raises_keyerror():
    with pytest.raises(KeyError, match="unknown_sigla"):
        get_pattern("unknown_sigla")


def test_scan_strategies_is_exhaustive():
    assert set(SCAN_STRATEGIES) == {"anchors", "pagination", "none"}


def test_flavor_typed_dict_shape():
    """TypedDict accepts the canonical fields."""
    flavor: Flavor = {
        "name": "f_test",
        "anchors": ["A", "B", "C"],
        "min_match": 2,
    }
    assert flavor["name"] == "f_test"


def test_flavor_anti_anchors_optional():
    """A5: anti_anchors is opt-in."""
    flavor: Flavor = {
        "name": "f_test",
        "anchors": ["A"],
        "min_match": 1,
        "anti_anchors": ["X"],
        "anti_min_match": 1,
    }
    assert flavor["anti_anchors"] == ["X"]
