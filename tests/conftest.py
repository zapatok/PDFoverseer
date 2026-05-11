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
