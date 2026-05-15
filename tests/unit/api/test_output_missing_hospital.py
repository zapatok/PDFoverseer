"""Regression guard for FASE 4 pre-flight: _build_cell_values tolerates a
hospital with no cells in session state.

Pre-condition for HLL manual-entry flow: when HLL has no normalized folder
and the user generates Excel without filling values, the writer must skip
HLL named ranges (leave template defaults in place) without error.
"""

from api.routes.output import _build_cell_values


def test_build_cell_values_skips_missing_hospital():
    """3 hospitales con cells, HLL ausente → output dict no contiene HLL keys."""
    state = {
        "cells": {
            "HPV": {
                f"sigla_{i}": {
                    "filename_count": 5,
                    "ocr_count": None,
                    "user_override": None,
                    "excluded": False,
                }
                for i in range(1, 19)
            },
            "HRB": {
                f"sigla_{i}": {
                    "filename_count": 3,
                    "ocr_count": None,
                    "user_override": None,
                    "excluded": False,
                }
                for i in range(1, 19)
            },
            "HLU": {
                f"sigla_{i}": {
                    "filename_count": 1,
                    "ocr_count": None,
                    "user_override": None,
                    "excluded": False,
                }
                for i in range(1, 19)
            },
            # HLL deliberately omitted
        }
    }

    out = _build_cell_values(state)

    # Sanity: 3 hospitals × 18 siglas = 54 keys (assuming all values are non-None
    # which they are: filename_count >= 1 for every cell).
    assert len(out) == 54
    # HLL keys must not be present
    assert not any(k.startswith("HLL_") for k in out.keys())
    # Other hospitals are present
    assert "HPV_sigla_1_count" in out
    assert "HRB_sigla_1_count" in out
    assert "HLU_sigla_1_count" in out


def test_build_cell_values_handles_completely_empty_state():
    """state["cells"] = {} → output dict is empty (no crash)."""
    state = {"cells": {}}
    out = _build_cell_values(state)
    assert out == {}


def test_build_cell_values_handles_missing_cells_key():
    """state without "cells" key → output dict is empty (no crash)."""
    state = {}
    out = _build_cell_values(state)
    assert out == {}
