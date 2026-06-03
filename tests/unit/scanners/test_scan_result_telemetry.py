"""ScanResult must carry near-match telemetry (A14)."""

from __future__ import annotations

from core.scanners.base import (
    ConfidenceLevel,
    NearMatchEntry,
    ScanResult,
    ScanTelemetry,
)


def test_scan_result_telemetry_is_optional():
    result = ScanResult(
        count=5,
        confidence=ConfidenceLevel.HIGH,
        method="filename_glob",
        breakdown=None,
        flags=[],
        errors=[],
        duration_ms=10,
        files_scanned=5,
    )
    assert result.telemetry is None


def test_scan_result_with_telemetry():
    tel = ScanTelemetry(
        near_matches=[
            NearMatchEntry(
                pdf_name="foo.pdf",
                page_index=2,
                flavor_name="f_test",
                matched_anchors=["a", "b"],
                missing_anchors=["c"],
            )
        ]
    )
    result = ScanResult(
        count=3,
        confidence=ConfidenceLevel.HIGH,
        method="header_band_anchors",
        breakdown=None,
        flags=[],
        errors=[],
        duration_ms=200,
        files_scanned=1,
        telemetry=tel,
    )
    assert result.telemetry is not None
    assert len(result.telemetry.near_matches) == 1
    assert result.telemetry.near_matches[0].pdf_name == "foo.pdf"
