"""Pytest fixtures for PDFoverseer tests.

Critical fixture: write-guard. Any attempt to write inside
A:\\informe mensual\\ or A:\\estadistica mensual\\ fails LOUD so tests
cannot accidentally corrupt the source corpus.
"""

import os
import shutil
from pathlib import Path

import pytest

_FORBIDDEN_ROOTS = (
    Path("A:/informe mensual").resolve(),
    Path("A:/estadistica mensual").resolve(),
)

# Single source of truth for "is the live read-only corpus available?" —
# tests declare the dependency with @pytest.mark.corpus (registered in
# pyproject.toml) instead of re-defining per-file skipif guards.
_CORPUS_ABRIL = Path("A:/informe mensual/ABRIL")


def pytest_collection_modifyitems(config, items):
    """Auto-skip ``corpus``-marked tests when the live corpus is absent."""
    if _CORPUS_ABRIL.exists():
        return
    skip = pytest.mark.skip(reason="live corpus not present")
    for item in items:
        if "corpus" in item.keywords:
            item.add_marker(skip)


def _is_forbidden(target):
    try:
        resolved = Path(target).resolve()
    except (OSError, ValueError):
        return False
    return any(str(resolved).lower().startswith(str(root).lower()) for root in _FORBIDDEN_ROOTS)


@pytest.fixture(autouse=True)
def _write_guard(monkeypatch):
    """Block writes targeting the source corpus folders."""
    original_write_text = Path.write_text
    original_write_bytes = Path.write_bytes
    original_unlink = Path.unlink
    original_copy = shutil.copy
    original_copy2 = shutil.copy2
    original_copytree = shutil.copytree
    original_move = shutil.move
    original_rename = os.rename
    original_replace = os.replace

    def _guard_write_text(self, *args, **kwargs):
        if _is_forbidden(self):
            raise PermissionError(f"write-guard: writes to {self} are forbidden in tests")
        return original_write_text(self, *args, **kwargs)

    def _guard_write_bytes(self, *args, **kwargs):
        if _is_forbidden(self):
            raise PermissionError(f"write-guard: writes to {self} are forbidden in tests")
        return original_write_bytes(self, *args, **kwargs)

    def _guard_unlink(self, *args, **kwargs):
        if _is_forbidden(self):
            raise PermissionError(f"write-guard: unlink of {self} is forbidden in tests")
        return original_unlink(self, *args, **kwargs)

    def _guard_copy(src, dst, *args, **kwargs):
        if _is_forbidden(dst):
            raise PermissionError(f"write-guard: copy to {dst} is forbidden in tests")
        return original_copy(src, dst, *args, **kwargs)

    def _guard_copy2(src, dst, *args, **kwargs):
        if _is_forbidden(dst):
            raise PermissionError(f"write-guard: copy2 to {dst} is forbidden in tests")
        return original_copy2(src, dst, *args, **kwargs)

    def _guard_copytree(src, dst, *args, **kwargs):
        if _is_forbidden(dst):
            raise PermissionError(f"write-guard: copytree to {dst} is forbidden in tests")
        return original_copytree(src, dst, *args, **kwargs)

    def _guard_move(src, dst, *args, **kwargs):
        if _is_forbidden(dst):
            raise PermissionError(f"write-guard: move to {dst} is forbidden in tests")
        return original_move(src, dst, *args, **kwargs)

    def _guard_rename(src, dst, *args, **kwargs):
        if _is_forbidden(dst):
            raise PermissionError(f"write-guard: rename to {dst} is forbidden in tests")
        return original_rename(src, dst, *args, **kwargs)

    def _guard_replace(src, dst, *args, **kwargs):
        if _is_forbidden(dst):
            raise PermissionError(f"write-guard: replace to {dst} is forbidden in tests")
        return original_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", _guard_write_text)
    monkeypatch.setattr(Path, "write_bytes", _guard_write_bytes)
    monkeypatch.setattr(Path, "unlink", _guard_unlink)
    monkeypatch.setattr(shutil, "copy", _guard_copy)
    monkeypatch.setattr(shutil, "copy2", _guard_copy2)
    monkeypatch.setattr(shutil, "copytree", _guard_copytree)
    monkeypatch.setattr(shutil, "move", _guard_move)
    monkeypatch.setattr(os, "rename", _guard_rename)
    monkeypatch.setattr(os, "replace", _guard_replace)
    yield


@pytest.fixture(autouse=True)
def _db_path_isolation(tmp_path, monkeypatch):
    """Default OVERSEER_DB_PATH to a per-test tmp file for every test.

    2026-07 incident: several tests called ``api.main.create_app()`` without
    setting ``OVERSEER_DB_PATH`` (``api/main.py::_db_path()`` falls back to
    the real ``data/overseer.db``), so they opened the PRODUCTION database
    and wrote to it on every fast-suite run — confirmed writer:
    ``test_agent_broadcast.py::test_agent_override_endpoint_200_on_free_cell``
    PATCHed the real 2026-04 HRB|odi cell with ``user_override=3``.

    Only sets the default when the variable is not already present — this
    respects an explicit opt-in (e.g. an outer/higher-scoped fixture, or a
    manual ``OVERSEER_DB_PATH=... pytest ...`` invocation). A previous test's
    ``monkeypatch.setenv`` is always undone at teardown before this fixture
    runs again, so a plain absence-check is sufficient — no leakage between
    tests. A test's OWN ``monkeypatch.setenv("OVERSEER_DB_PATH", ...)`` inside
    its body or a sibling fixture still wins: this autouse fixture only sets
    the value at setup time, and (being autouse) it always runs before
    same-scope non-autouse fixtures / the test body, so a later explicit
    ``setenv`` simply overwrites this default via the same monkeypatch stack.
    """
    if os.environ.get("OVERSEER_DB_PATH") is None:
        monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "test_overseer.db"))
    yield
