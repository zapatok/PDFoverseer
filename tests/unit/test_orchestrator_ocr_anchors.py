"""Orchestrator must invoke count_ocr on AnchorsScanner just like the old
specialized scanners."""

from __future__ import annotations

from pathlib import Path

import core.scanners as scanner_registry
from core.orchestrator import _ocr_worker


def test_orchestrator_invokes_anchors_scanner_count_ocr(tmp_path: Path, monkeypatch):
    # reunion is the only populated entry — but reunion has strategy="none"
    # so no count_ocr. Use a stub: register a fake AnchorsScanner for testing.

    scanner_registry.clear()
    from core.scanners.anchors_scanner import AnchorsScanner

    scanner_registry.register(AnchorsScanner(sigla="andamios"))

    called = {"value": False}

    def fake_count_ocr(self, folder, *, cancel, on_pdf=None, skip=None):
        called["value"] = True
        from core.scanners.base import ConfidenceLevel, ScanResult

        return ScanResult(
            count=0,
            confidence=ConfidenceLevel.HIGH,
            method="header_band_anchors",
            breakdown=None,
            flags=[],
            errors=[],
            duration_ms=1,
            files_scanned=0,
        )

    monkeypatch.setattr(AnchorsScanner, "count_ocr", fake_count_ocr)

    hosp, sigla, result, error = _ocr_worker(("HPV", "andamios", str(tmp_path), []))
    assert called["value"]
    assert error is None
    assert result is not None
    assert result.method == "header_band_anchors"

    # Restore registry
    scanner_registry.clear()
    scanner_registry.register_defaults()
