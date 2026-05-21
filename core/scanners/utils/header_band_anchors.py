"""Multi-flavor anchor-based cover detection (A2 + A4 + A5 + A14).

OCRea la banda superior de cada página, cuenta páginas que matcheen
≥ min_match anchors de algún flavor declarado en patterns.py. Devuelve
también near-matches (páginas con min_match - 1 anchors) como señal para
mantenimiento (A14).

Sub-utilities:
- `_normalize_text`: lowercase + strip accents + collapse whitespace/separators.
- `_match_flavor`: returns matched_anchors + matched_anti_anchors for a flavor.
- `count_covers_by_anchors`: main entry point — iterates pages.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.scanners.patterns import (
    DEFAULT_ANTI_MIN_MATCH,
    DEFAULT_MIN_MATCH,
    Flavor,
)

if TYPE_CHECKING:
    pass


_SEPARATORS_RX = re.compile(r"[/\-_]+")
_WHITESPACE_RX = re.compile(r"\s+")


def _normalize_text(text: str) -> str:
    """Lowercase, strip accents, collapse separators (/-_) → space, collapse spaces."""
    # Strip combining marks (accents) using NFKD decomposition
    nfkd = unicodedata.normalize("NFKD", text)
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    lower = no_accents.lower()
    no_seps = _SEPARATORS_RX.sub(" ", lower)
    collapsed = _WHITESPACE_RX.sub(" ", no_seps)
    return collapsed.strip()


@dataclass(frozen=True)
class FlavorMatchResult:
    """Per-page match outcome for a single flavor."""

    matched_anchors: list[str]
    matched_anti_anchors: list[str]
    passes: bool  # True iff matched_anchors >= min_match AND anti_anchored is False
    anti_anchored: bool  # True iff matched_anti_anchors >= anti_min_match


def _match_flavor(normalized_text: str, flavor: Flavor) -> FlavorMatchResult:
    """Count how many anchors / anti-anchors of a flavor match the page text."""
    matched_anchors: list[str] = []
    for anchor in flavor["anchors"]:
        normalized = _normalize_text(anchor)
        if normalized and normalized in normalized_text:
            matched_anchors.append(normalized)

    matched_anti: list[str] = []
    for anti in flavor.get("anti_anchors", []):
        normalized = _normalize_text(anti)
        if normalized and normalized in normalized_text:
            matched_anti.append(normalized)

    min_match = flavor.get("min_match", DEFAULT_MIN_MATCH)
    anti_min = flavor.get("anti_min_match", DEFAULT_ANTI_MIN_MATCH)
    anti_anchored = len(matched_anti) >= anti_min
    passes = len(matched_anchors) >= min_match and not anti_anchored
    return FlavorMatchResult(
        matched_anchors=matched_anchors,
        matched_anti_anchors=matched_anti,
        passes=passes,
        anti_anchored=anti_anchored,
    )
