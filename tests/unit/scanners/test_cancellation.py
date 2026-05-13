import pytest

from core.scanners.cancellation import CancellationToken, CancelledError


def test_token_starts_uncancelled() -> None:
    token = CancellationToken()
    assert token.cancelled is False
    token.check()  # no-op, must not raise


def test_cancel_flips_flag() -> None:
    token = CancellationToken()
    token.cancel()
    assert token.cancelled is True


def test_check_after_cancel_raises() -> None:
    token = CancellationToken()
    token.cancel()
    with pytest.raises(CancelledError):
        token.check()


def test_cancel_is_idempotent() -> None:
    token = CancellationToken()
    token.cancel()
    token.cancel()
    assert token.cancelled is True


def test_cancelled_error_is_exception() -> None:
    assert issubclass(CancelledError, Exception)
