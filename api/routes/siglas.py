"""GET /api/siglas/{sigla}/scan-info — what the pase-2 OCR looks for (rev-2 §5)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from core.domain import SIGLAS
from core.scanners.scan_info import scan_info_for

router = APIRouter()


@router.get("/siglas/{sigla}/scan-info")
def get_scan_info(sigla: str) -> dict:
    """Return the per-sigla scan-info dict (kind + distinctive anchors).

    Args:
        sigla: one of the 20 category keys.

    Returns:
        ``{"sigla", "kind", "looks_for"?}`` (see ``scan_info_for``).
    """
    if sigla not in SIGLAS:
        raise HTTPException(400, f"Unknown sigla: {sigla}")
    return scan_info_for(sigla)
