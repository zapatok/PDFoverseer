"""GET /api/months and /api/months/{year}-{month}."""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from core.orchestrator import enumerate_month

router = APIRouter()


def _informe_root() -> Path:
    return Path(os.environ.get("INFORME_MENSUAL_ROOT", "A:/informe mensual"))


_MONTH_NAMES = {
    "ENERO": 1,
    "FEBRERO": 2,
    "MARZO": 3,
    "ABRIL": 4,
    "MAYO": 5,
    "JUNIO": 6,
    "JULIO": 7,
    "AGOSTO": 8,
    "SEPTIEMBRE": 9,
    "OCTUBRE": 10,
    "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}


@router.get("/months")
def list_months() -> dict:
    """Enumerate month subfolders inside the INFORME_MENSUAL root.

    Returns:
        Dict with a ``months`` key listing each recognised month folder
        (name, year, month, session_id, path).
    """
    root = _informe_root()
    if not root.exists():
        return {"months": []}
    months = []
    for sub in sorted(root.iterdir()):
        if not sub.is_dir() or sub.name.startswith("."):
            continue
        upper = sub.name.upper()
        m_num = _MONTH_NAMES.get(upper)
        if m_num is None:
            continue
        # Year inferred from current year — Daniel works on current year by default;
        # future enhancement: parse from a YYYY parent folder.
        year = datetime.now().year
        months.append(
            {
                "name": sub.name,
                "year": year,
                "month": m_num,
                "session_id": f"{year:04d}-{m_num:02d}",
                "path": str(sub),
            }
        )
    return {"months": months}


_SESSION_ID_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


@router.get("/months/{session_id}")
def get_month(session_id: str) -> dict:
    """Return the full hospital/cell inventory for a month session.

    Args:
        session_id: Session identifier of the form ``YYYY-MM``.

    Returns:
        Dict with the resolved month root, hospitals present/missing, and
        the per-hospital list of 18 :class:`CellInventory` entries.
    """
    m = _SESSION_ID_RE.match(session_id)
    if not m:
        raise HTTPException(400, f"Invalid session_id format: {session_id}")
    year, month = int(m.group(1)), int(m.group(2))
    root = _informe_root()
    target_name = next(
        (name for name, num in _MONTH_NAMES.items() if num == month),
        None,
    )
    if target_name is None:
        raise HTTPException(404, f"Unknown month: {month}")
    if not root.exists():
        raise HTTPException(404, f"INFORME_MENSUAL root not found: {root}")
    month_dir = next(
        (p for p in root.iterdir() if p.is_dir() and p.name.upper() == target_name),
        None,
    )
    if month_dir is None:
        raise HTTPException(404, f"Month folder not found: {target_name}")
    inv = enumerate_month(month_dir)
    return {
        "session_id": session_id,
        "year": year,
        "month": month,
        "month_root": str(inv.month_root),
        "hospitals_present": inv.hospitals_present,
        "hospitals_missing": inv.hospitals_missing,
        "cells": {
            hosp: [
                {
                    "hospital": c.hospital,
                    "sigla": c.sigla,
                    "folder_path": str(c.folder_path),
                    "folder_exists": c.folder_exists,
                    "pdf_count_hint": c.pdf_count_hint,
                }
                for c in cell_list
            ]
            for hosp, cell_list in inv.cells.items()
        },
    }
