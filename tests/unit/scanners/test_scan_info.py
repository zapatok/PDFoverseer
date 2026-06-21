"""scan_info_for derives per-sigla 'what the OCR looks for' from patterns.py."""

from __future__ import annotations

from core.scanners.scan_info import scan_info_for


def test_scan_info_anchors_pagination_none():
    # chps stays anchors (acta de reunión) and its flavor includes "pagina 1 de",
    # so it exercises the pagination-anchor filter. (odi migrated to pagination in v4.)
    chps = scan_info_for("chps")
    assert chps["kind"] == "anchors"
    assert 1 <= len(chps["looks_for"]) <= 3
    # The pagination anchor ("pagina 1 de") is a generic V4 pattern, not a field
    # the operator would recognise — it must be skipped.
    assert all("pagina 1 de" not in a.lower() for a in chps["looks_for"])

    assert scan_info_for("insgral")["kind"] == "pagination"
    assert scan_info_for("odi")["kind"] == "pagination"  # v4: migrated from anchors
    assert scan_info_for("reunion")["kind"] == "none"


def test_scan_info_unknown_sigla_is_none():
    assert scan_info_for("does_not_exist")["kind"] == "none"
