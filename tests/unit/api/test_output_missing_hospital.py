"""Contract for _build_cell_values: it emits the FULL canonical grid.

Updated 2026-06-06: a hospital or cell with no data must write an explicit 0 — not
be skipped — so the RESUMEN shows 0 instead of a blank for anything not yet counted
(Daniel's report: uncounted cells appeared empty). Excluded cells are the only ones
still skipped. This supersedes the earlier "skip missing hospital, leave template
default" behavior.
"""

from api.routes.output import _build_cell_values
from core.domain import HOSPITALS, SIGLAS

_GRID = len(HOSPITALS) * len(SIGLAS)


def _cells(filename_count: int) -> dict:
    return {
        sigla: {
            "filename_count": filename_count,
            "ocr_count": None,
            "user_override": None,
            "excluded": False,
        }
        for sigla in SIGLAS
    }


def test_build_cell_values_emits_zero_for_missing_hospital():
    """3 hospitals with cells, HLL omitted → HLL keys present and 0 (not skipped)."""
    state = {"cells": {"HPV": _cells(5), "HRB": _cells(3), "HLU": _cells(1)}}
    out = _build_cell_values(state)
    assert len(out) == _GRID  # full grid, nothing skipped
    assert all(out[f"HLL_{s}_count"] == 0 for s in SIGLAS)  # missing hospital → 0
    assert out[f"HPV_{SIGLAS[0]}_count"] == 5


def test_build_cell_values_completely_empty_state_emits_all_zeros():
    """state["cells"] = {} → full grid of 0s (no crash, no blanks)."""
    out = _build_cell_values({"cells": {}})
    assert len(out) == _GRID
    assert set(out.values()) == {0}


def test_build_cell_values_handles_missing_cells_key():
    """state without a "cells" key → full grid of 0s (no crash)."""
    out = _build_cell_values({})
    assert len(out) == _GRID
    assert set(out.values()) == {0}
