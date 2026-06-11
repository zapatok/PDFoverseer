"""Per-sigla "what the pase-2 scanner looks for", derived from patterns.py.

Powers the method (i) tooltip in the UI (rev-2 §5). The text is *derived* from the
flavor anchors — never hand-authored — so it can never drift from the scanner.
"""

from __future__ import annotations

from core.scanners.patterns import PATTERNS, count_type_for

# Generic V4 pagination anchors reused inside some flavors; not operator-facing
# field names, so they are skipped when picking the distinctive anchors to show.
_PAGINATION_ANCHOR_PREFIXES = ("pagina 1 de", "pagina n de")

_MAX_ANCHORS_SHOWN = 3


def scan_info_for(sigla: str) -> dict:
    """What the pase-2 scanner looks for in `sigla`'s pages.

    Args:
        sigla: the category key (e.g. ``"odi"``).

    Returns:
        ``{"sigla", "kind", "count_type"}`` where ``kind`` is
        ``"anchors" | "pagination" | "none"`` and ``count_type`` is
        ``"documents" | "documents_workers" | "checks"``; for ``"anchors"`` also
        ``"looks_for"``: up to 3 distinctive anchor strings.
    """
    pattern = PATTERNS.get(sigla)
    strategy = pattern.get("scan_strategy") if pattern else "none"
    count_type = count_type_for(sigla)

    if strategy == "anchors" and pattern is not None:
        seen: set[str] = set()
        looks_for: list[str] = []
        for flavor in pattern.get("cover_flavors", []):
            for anchor in flavor.get("anchors", []):
                lowered = anchor.lower()
                if lowered in seen or any(
                    lowered.startswith(p) for p in _PAGINATION_ANCHOR_PREFIXES
                ):
                    continue
                seen.add(lowered)
                looks_for.append(anchor)
                if len(looks_for) == _MAX_ANCHORS_SHOWN:
                    break
            if len(looks_for) == _MAX_ANCHORS_SHOWN:
                break
        return {
            "sigla": sigla,
            "kind": "anchors",
            "looks_for": looks_for,
            "count_type": count_type,
        }

    return {"sigla": sigla, "kind": strategy, "count_type": count_type}  # pagination | none
