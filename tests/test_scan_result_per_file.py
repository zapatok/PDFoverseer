"""ScanResult.per_file field — FASE 4."""

import json
from dataclasses import asdict

from core.scanners.base import ConfidenceLevel, ScanResult


def test_scan_result_default_per_file_is_none():
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
    assert result.per_file is None


def test_scan_result_with_per_file_serializes_via_asdict():
    result = ScanResult(
        count=24,
        confidence=ConfidenceLevel.HIGH,
        method="header_detect",
        breakdown=None,
        flags=[],
        errors=[],
        duration_ms=8345,
        files_scanned=2,
        per_file={"a.pdf": 20, "b.pdf": 4},
    )
    d = asdict(result)
    assert d["per_file"] == {"a.pdf": 20, "b.pdf": 4}
    assert json.dumps(d["per_file"])
