"""Validate compute_cell_count Python against shared fixtures.
Frontend (cellCount.js) is asserted against the same fixtures during smoke."""

import json
from pathlib import Path

import pytest

from api.state import compute_cell_count

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "cell_count_cases.json"


@pytest.mark.parametrize(
    "case",
    json.loads(FIXTURE_PATH.read_text(encoding="utf-8")),
    ids=lambda c: c["name"],
)
def test_compute_cell_count_against_shared_fixture(case):
    count_type = case.get("count_type", "documents")
    present = set(case["present_files"]) if "present_files" in case else None
    assert compute_cell_count(case["cell"], count_type, present) == case["expected"], (
        f"case={case['name']}"
    )
