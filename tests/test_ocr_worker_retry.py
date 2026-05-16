"""_ocr_worker reintenta scans OCR fallidos en silencio — FASE 5 Feature 3."""

import core.scanners as scanner_registry
from core import orchestrator
from core.scanners.cancellation import CancelledError


class _FlakyScanner:
    """count_ocr falla `fail_times` veces y después tiene éxito."""

    def __init__(self, fail_times):
        self.fail_times = fail_times
        self.calls = 0

    def count_ocr(self, folder, *, cancel):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("transient tesseract crash")
        return "OK_RESULT"


def _setup(monkeypatch, scanner):
    monkeypatch.setattr(orchestrator, "_WORKER_EVENT", None)
    monkeypatch.setattr(scanner_registry, "get", lambda sigla: scanner)
    monkeypatch.setattr(orchestrator.time, "sleep", lambda s: None)


def test_recovers_after_retries(monkeypatch):
    scanner = _FlakyScanner(fail_times=2)
    _setup(monkeypatch, scanner)

    h, s, result, err = orchestrator._ocr_worker(("HRB", "art", "/tmp/x"))

    assert err is None
    assert result == "OK_RESULT"
    assert scanner.calls == 3  # 2 fallos + 1 éxito


def test_gives_up_after_two_retries(monkeypatch):
    scanner = _FlakyScanner(fail_times=99)
    _setup(monkeypatch, scanner)

    h, s, result, err = orchestrator._ocr_worker(("HRB", "art", "/tmp/x"))

    assert result is None
    assert "transient tesseract crash" in err
    assert scanner.calls == 3  # intento inicial + 2 reintentos


def test_cancelled_does_not_retry(monkeypatch):
    class _CancelScanner:
        def __init__(self):
            self.calls = 0

        def count_ocr(self, folder, *, cancel):
            self.calls += 1
            raise CancelledError()

    scanner = _CancelScanner()
    _setup(monkeypatch, scanner)

    h, s, result, err = orchestrator._ocr_worker(("HRB", "art", "/tmp/x"))

    assert err == "cancelled"
    assert scanner.calls == 1  # sin reintento
