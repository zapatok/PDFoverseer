"""_ocr_worker reintenta scans OCR fallidos en silencio — FASE 5 Feature 3."""

import core.scanners as scanner_registry
from core.orchestrator import ocr_worker
from core.scanners.cancellation import CancelledError


class _FlakyScanner:
    """count_ocr falla `fail_times` veces y después tiene éxito."""

    def __init__(self, fail_times):
        self.fail_times = fail_times
        self.calls = 0

    def count_ocr(self, folder, *, cancel, on_pdf=None, skip=None):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("transient tesseract crash")
        return "OK_RESULT"


def _setup(monkeypatch, scanner):
    monkeypatch.setattr(ocr_worker, "_WORKER_EVENT", None)
    monkeypatch.setattr(scanner_registry, "get", lambda sigla: scanner)
    monkeypatch.setattr(ocr_worker.time, "sleep", lambda s: None)


def test_recovers_after_retries(monkeypatch):
    scanner = _FlakyScanner(fail_times=2)
    _setup(monkeypatch, scanner)

    h, s, result, err = ocr_worker._ocr_worker(("HRB", "art", "/tmp/x", []))

    assert err is None
    assert result == "OK_RESULT"
    assert scanner.calls == 3  # 2 fallos + 1 éxito


def test_gives_up_after_two_retries(monkeypatch):
    scanner = _FlakyScanner(fail_times=99)
    _setup(monkeypatch, scanner)

    h, s, result, err = ocr_worker._ocr_worker(("HRB", "art", "/tmp/x", []))

    assert result is None
    assert "transient tesseract crash" in err
    assert scanner.calls == 3  # intento inicial + 2 reintentos


def test_retry_does_not_double_tick_on_pdf(monkeypatch):
    """U9: a cell retried after a transient failure must not re-emit on_pdf for
    a filename already ticked in an earlier attempt — attempt 1 ticks all 3
    files then fails (a bug unrelated to any specific file, e.g. assembling the
    final ScanResult); attempt 2 ticks the same 3 files again and succeeds. The
    caller must see each filename exactly once."""

    class _PartialFlakyScanner:
        def __init__(self):
            self.calls = 0

        def count_ocr(self, folder, *, cancel, on_pdf=None, skip=None):
            self.calls += 1
            for name in ("a.pdf", "b.pdf", "c.pdf"):
                if on_pdf is not None:
                    on_pdf(name, 1, "pagination", [])
            if self.calls == 1:
                raise RuntimeError("transient tesseract crash")
            return "OK_RESULT"

    scanner = _PartialFlakyScanner()
    _setup(monkeypatch, scanner)

    ticks: list[str] = []
    h, s, result, err = ocr_worker._ocr_worker(
        ("HRB", "art", "/tmp/x", []),
        on_pdf=lambda name, count, method, nm: ticks.append(name),
    )

    assert err is None
    assert result == "OK_RESULT"
    assert scanner.calls == 2  # 1 failure + 1 success
    assert ticks == ["a.pdf", "b.pdf", "c.pdf"]  # not 6 — deduped across attempts


def test_cancelled_does_not_retry(monkeypatch):
    class _CancelScanner:
        def __init__(self):
            self.calls = 0

        def count_ocr(self, folder, *, cancel, on_pdf=None, skip=None):
            self.calls += 1
            raise CancelledError()

    scanner = _CancelScanner()
    _setup(monkeypatch, scanner)

    h, s, result, err = ocr_worker._ocr_worker(("HRB", "art", "/tmp/x", []))

    assert err == "cancelled"
    assert scanner.calls == 1  # sin reintento
