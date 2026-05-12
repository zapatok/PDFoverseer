from core.scanners.base import ConfidenceLevel, ScanResult


def test_confidence_levels_values():
    assert ConfidenceLevel.HIGH.value == "high"
    assert ConfidenceLevel.MEDIUM.value == "medium"
    assert ConfidenceLevel.LOW.value == "low"
    assert ConfidenceLevel.MANUAL.value == "manual"


def test_scan_result_is_frozen_dataclass():
    r = ScanResult(
        count=5,
        confidence=ConfidenceLevel.HIGH,
        method="filename_glob",
        breakdown=None,
        flags=[],
        errors=[],
        duration_ms=10,
        files_scanned=5,
    )
    assert r.count == 5
    import dataclasses

    assert dataclasses.is_dataclass(r)
