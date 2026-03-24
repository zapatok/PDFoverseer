"""Extract (curr, total) page numbers from VLM response text."""
from __future__ import annotations

import re

# Ordered by specificity — first match wins.
_PATTERNS: list[re.Pattern] = [
    # "Página 3 de 10", "Pagina 1 de 2", "Pág. 5 de 8", "Pag 12 de 15"
    re.compile(r"P[áa]g(?:ina)?\.?\s*(\d{1,3})\s*de\s*(\d{1,3})", re.IGNORECASE),
    # "Page 3 of 10"
    re.compile(r"Page\s+(\d{1,3})\s+of\s+(\d{1,3})", re.IGNORECASE),
    # "3 out of 10"
    re.compile(r"(\d{1,3})\s+out\s+of\s+(\d{1,3})", re.IGNORECASE),
    # "3 de 10" (bare, no prefix)
    re.compile(r"(?<!\d)(\d{1,3})\s+de\s+(\d{1,3})(?!\d)"),
    # "3/10" (direct format)
    re.compile(r"(?<!\d)(\d{1,3})/(\d{1,3})(?!\d)"),
]


def parse(raw_text: str) -> tuple[int, int] | None:
    """Extract (curr, total) from VLM response text.

    Tries named patterns first, then falls back to finding two
    integers <= 999 if no named pattern matches.
    Returns None if nothing parseable is found.
    """
    if not raw_text:
        return None

    # Try specific patterns first
    for pat in _PATTERNS:
        m = pat.search(raw_text)
        if m:
            curr, total = int(m.group(1)), int(m.group(2))
            if 1 <= curr <= total:
                return (curr, total)

    # Fallback: find exactly two standalone integers <= 999
    nums = [int(x) for x in re.findall(r"\b(\d{1,3})\b", raw_text)
            if int(x) <= 999]
    if len(nums) == 2 and 1 <= nums[0] <= nums[1]:
        return (nums[0], nums[1])

    return None
