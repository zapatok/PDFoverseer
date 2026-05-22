"""Unit tests for the V4 document-count adapter (core.scanners.utils.v4_count).

These tests monkeypatch ``analyze_pdf`` so they never spawn the real V4
process pool — the real pipeline is exercised by the insgral/altura smoke
tests instead.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from core.scanners.cancellation import CancellationToken, CancelledError
from core.scanners.utils.v4_count import V4CountResult, count_documents_v4


def _read(method: str) -> SimpleNamespace:
    """Minimal stand-in for a pipeline._PageRead — only .method is read."""
    return SimpleNamespace(method=method, pdf_page=1, curr=1, total=1, confidence=1.0)


def test_count_documents_v4_tallies_reads(monkeypatch, tmp_path: Path) -> None:
    docs = [object(), object(), object()]
    reads = [_read("direct"), _read("direct"), _read("inferred")]
    monkeypatch.setattr(
        "core.scanners.utils.v4_count.analyze_pdf",
        lambda *a, **k: (docs, reads),
    )
    result = count_documents_v4(tmp_path / "x.pdf", cancel=CancellationToken())
    assert isinstance(result, V4CountResult)
    assert result.count == 3
    assert result.pages_total == 3
    assert result.direct_reads == 2
    assert result.inferred_reads == 1
    assert result.failed_reads == 0


def test_count_documents_v4_counts_failed_reads(monkeypatch, tmp_path: Path) -> None:
    docs = [object()]
    reads = [_read("direct"), _read("failed"), _read("inferred")]
    monkeypatch.setattr(
        "core.scanners.utils.v4_count.analyze_pdf",
        lambda *a, **k: (docs, reads),
    )
    result = count_documents_v4(tmp_path / "x.pdf", cancel=CancellationToken())
    assert result.failed_reads == 1
    assert result.direct_reads == 1
    assert result.inferred_reads == 1


def test_count_documents_v4_checks_cancel_before_run(monkeypatch, tmp_path: Path) -> None:
    """An already-cancelled token short-circuits before V4 is invoked."""
    token = CancellationToken()
    token.cancel()

    def _must_not_run(*a, **k):
        raise AssertionError("analyze_pdf must not run when already cancelled")

    monkeypatch.setattr("core.scanners.utils.v4_count.analyze_pdf", _must_not_run)
    with pytest.raises(CancelledError):
        count_documents_v4(tmp_path / "x.pdf", cancel=token)


def test_count_documents_v4_raises_when_cancelled_mid_run(monkeypatch, tmp_path: Path) -> None:
    """V4 returning ([], []) after cancellation surfaces as CancelledError."""
    token = CancellationToken()

    def _fake_analyze(*a, **k):
        token.cancel()
        return ([], [])

    monkeypatch.setattr("core.scanners.utils.v4_count.analyze_pdf", _fake_analyze)
    with pytest.raises(CancelledError):
        count_documents_v4(tmp_path / "x.pdf", cancel=token)


def test_count_documents_v4_raises_on_empty_result(monkeypatch, tmp_path: Path) -> None:
    """V4 returning ([], []) without cancellation is a pipeline failure."""
    monkeypatch.setattr("core.scanners.utils.v4_count.analyze_pdf", lambda *a, **k: ([], []))
    with pytest.raises(RuntimeError):
        count_documents_v4(tmp_path / "x.pdf", cancel=CancellationToken())


def test_count_documents_v4_bridges_cancel_event(monkeypatch, tmp_path: Path) -> None:
    """The token is passed to analyze_pdf as a .is_set()-capable cancel_event."""
    captured: dict[str, object] = {}

    def _fake_analyze(pdf_path, on_progress, on_log, **kwargs):
        captured["cancel_event"] = kwargs.get("cancel_event")
        return ([object()], [_read("direct")])

    monkeypatch.setattr("core.scanners.utils.v4_count.analyze_pdf", _fake_analyze)
    token = CancellationToken()
    count_documents_v4(tmp_path / "x.pdf", cancel=token)
    event = captured["cancel_event"]
    assert hasattr(event, "is_set")
    assert event.is_set() is False
    token.cancel()
    assert event.is_set() is True
