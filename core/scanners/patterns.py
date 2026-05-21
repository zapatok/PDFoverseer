"""Central registry of patterns per sigla — see A1, A9, A10, A11 in the spec.

Each entry declares how a sigla counts when filename_glob is not enough.
The 18 SIGLAS from core.domain MUST each have an entry here.

See:
    docs/superpowers/specs/2026-05-18-ocr-per-sigla-refinement-design.md
"""

from __future__ import annotations

from typing import Literal, TypedDict

from typing_extensions import NotRequired

ScanStrategy = Literal["anchors", "pagination", "none"]
SCAN_STRATEGIES: tuple[ScanStrategy, ...] = ("anchors", "pagination", "none")


class Flavor(TypedDict):
    """A single template variant within a sigla. See A4, A5, A9.

    `name`: f_<código_canónico>[_<origen>] (A9 convention).
    `anchors`: list of substrings to OCR-match in the top band.
    `min_match`: how many anchors must match for a page to count as cover.
    `anti_anchors`: optional — descalifica shadow covers (A5).
    `anti_min_match`: optional — default 1 (any anti-anchor match descalifica).
    """

    name: str
    anchors: list[str]
    min_match: int
    anti_anchors: NotRequired[list[str]]
    anti_min_match: NotRequired[int]


class SiglaPattern(TypedDict):
    """Per-sigla declarative pattern entry. See A6, A10.

    `filename_glob`: lax full-match regex (A10) — the ^.* prefix allows arbitrary prefixes; matched via re.match.
    `scan_strategy`: "anchors" | "pagination" | "none".
    `cover_flavors`: required if strategy="anchors".
    `top_fraction`: optional — default 0.25 (A2).
    `recursive_glob`: optional — INFORMATIONAL ONLY (count_pdfs_by_sigla
        already uses rglob unconditionally; this field documents intent).
    """

    filename_glob: str
    scan_strategy: ScanStrategy
    cover_flavors: NotRequired[list[Flavor]]
    top_fraction: NotRequired[float]
    recursive_glob: NotRequired[bool]


# Defaults documented as source of truth.
DEFAULT_TOP_FRACTION: float = 0.25
DEFAULT_MIN_MATCH: int = 3
DEFAULT_ANTI_MIN_MATCH: int = 1


PATTERNS: dict[str, SiglaPattern] = {
    "reunion": {
        "filename_glob": r"^.*reunion.*\.pdf$",
        "scan_strategy": "none",
    },
    # ... 17 entries más, llenadas en chunks posteriores
}


def get_pattern(sigla: str) -> SiglaPattern:
    """Return the SiglaPattern for `sigla`. Raises KeyError if unknown."""
    if sigla not in PATTERNS:
        raise KeyError(f"unknown_sigla: {sigla}")
    return PATTERNS[sigla]
