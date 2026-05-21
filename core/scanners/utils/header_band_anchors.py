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
from typing import TYPE_CHECKING

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
