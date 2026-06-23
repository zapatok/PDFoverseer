"""Tests for the central patterns registry."""

from __future__ import annotations

import re

import pytest

from core.domain import SIGLAS
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


def test_all_18_siglas_have_a_pattern():
    """Completeness gate — patterns.py must cover exactly the 18 SIGLAS."""
    assert set(PATTERNS) == set(SIGLAS), (
        "patterns.py must cover exactly the 18 SIGLAS; "
        f"missing={sorted(set(SIGLAS) - set(PATTERNS))} "
        f"extra={sorted(set(PATTERNS) - set(SIGLAS))}"
    )


def test_anchors_strategy_requires_cover_flavors():
    """Sanity check: every entry with strategy='anchors' has cover_flavors."""
    for sigla, pattern in PATTERNS.items():
        if pattern["scan_strategy"] == "anchors":
            assert "cover_flavors" in pattern, f"{sigla} declares anchors but has no cover_flavors"
            assert len(pattern["cover_flavors"]) >= 1


def test_flavor_naming_convention_a9():
    """A9: flavor names start with 'f_' and are snake_case."""
    rx = re.compile(r"^f_[a-z0-9_]+$")
    for sigla, pattern in PATTERNS.items():
        for flavor in pattern.get("cover_flavors", []):
            assert rx.match(flavor["name"]), (
                f"{sigla}: flavor name '{flavor['name']}' violates A9 (must match {rx.pattern})"
            )


def test_v4_pagination_migration_state():
    """v4 pagination-first migration GO-list (benchmark 2026-06-21, see
    docs/research/2026-06-21-pagination-benchmark-results.md). Pins which siglas
    moved anchors→pagination so an accidental revert is caught. Migrated siglas keep
    their anchor flavors on the entry (unused) for one-line reversibility."""
    pagination_expected = {
        "odi",
        "ext",
        "bodega",
        "caliente",
        "exc",
        "herramientas_elec",
        "art",
        "andamios",
        "irl",
        "altura",
        "insgral",
        "espacios",  # Incr B: new pagination sigla (F-PETS-CRS-08-01 compilations)
    }
    anchors_expected = {"charla", "chintegral", "dif_pts", "senal", "chps", "maquinaria"}
    none_expected = {"reunion", "revdocmaq"}  # revdocmaq: no samples → filename glob
    for sigla in pagination_expected:
        assert PATTERNS[sigla]["scan_strategy"] == "pagination", f"{sigla} must be pagination"
    for sigla in anchors_expected:
        assert PATTERNS[sigla]["scan_strategy"] == "anchors", (
            f"{sigla} must stay anchors (RCH '1 de 2' bug / landscape / checks)"
        )
    for sigla in none_expected:
        assert PATTERNS[sigla]["scan_strategy"] == "none", f"{sigla} must be none"


def test_irl_pagination_has_cover_code():
    """IRL counts only its F-CRS-ODI-01 covers (ignores appendix page-1s)."""
    assert PATTERNS["irl"]["scan_strategy"] == "pagination"
    assert PATTERNS["irl"].get("cover_code") == "F-CRS-ODI-01"


def test_cover_code_only_on_pagination_siglas():
    """cover_code is a pagination-only field; anchors siglas must not set it."""
    for sigla, pattern in PATTERNS.items():
        if pattern.get("cover_code"):
            assert pattern["scan_strategy"] == "pagination", (
                f"{sigla} sets cover_code but is not pagination"
            )
