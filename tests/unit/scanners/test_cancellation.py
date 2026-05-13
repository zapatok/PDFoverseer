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


# --- cross-process tests (mp.Event–backed token) ---

import multiprocessing as mp  # noqa: E402


def _worker_check_then_signal(event, ready, done):
    """Subprocess worker that waits for ready, then checks cancellation, then signals done."""
    ready.wait()
    token = CancellationToken.from_event(event)
    try:
        token.check()
    except Exception as exc:  # noqa: BLE001
        done.put(type(exc).__name__)
        return
    done.put("ok")


def test_event_backed_token_visible_across_processes() -> None:
    """Setting cancel in parent must be visible in a child subprocess."""
    ctx = mp.get_context("spawn")
    event = ctx.Event()
    ready = ctx.Event()
    done = ctx.Queue()
    proc = ctx.Process(target=_worker_check_then_signal, args=(event, ready, done))
    proc.start()
    event.set()  # cancel BEFORE the child checks
    ready.set()
    result = done.get(timeout=10)
    proc.join(timeout=5)
    assert result == "CancelledError"


def test_event_backed_token_uncancelled_passes() -> None:
    ctx = mp.get_context("spawn")
    event = ctx.Event()
    ready = ctx.Event()
    done = ctx.Queue()
    proc = ctx.Process(target=_worker_check_then_signal, args=(event, ready, done))
    proc.start()
    ready.set()  # don't cancel
    result = done.get(timeout=10)
    proc.join(timeout=5)
    assert result == "ok"
