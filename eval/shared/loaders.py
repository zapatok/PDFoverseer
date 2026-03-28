"""Shared fixture/ground-truth loaders for all eval sweeps."""
from __future__ import annotations

import json
from pathlib import Path

from .types import PageRead  # relative import: intra-package, no sys.path needed

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
GROUND_TRUTH_PATH = Path(__file__).parent.parent / "ground_truth.json"


def load_fixtures() -> list[dict]:
    fixtures = []
    for path in sorted(FIXTURES_DIR.rglob("*.json")):
        if "archived" in path.parts:
            continue
        data = json.loads(path.read_text())
        data["reads"] = [PageRead(**r) for r in data["reads"]]
        fixtures.append(data)
    return fixtures


def load_ground_truth() -> dict[str, dict]:
    return json.loads(GROUND_TRUTH_PATH.read_text())
