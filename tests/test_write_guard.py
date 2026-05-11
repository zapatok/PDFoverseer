from pathlib import Path

import pytest


def test_write_to_informe_mensual_raises(tmp_path):
    """The autouse write-guard should raise when a test attempts to write
    inside A:\\informe mensual\\ or A:\\estadistica mensual\\."""
    forbidden = Path("A:/informe mensual/test_should_not_exist.txt")
    with pytest.raises(PermissionError, match="write-guard"):
        forbidden.write_text("nope")


def test_write_to_tmp_path_allowed(tmp_path):
    """Writes to tmp_path are allowed."""
    target = tmp_path / "allowed.txt"
    target.write_text("ok")
    assert target.read_text() == "ok"
