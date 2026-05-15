"""History endpoint for FASE 4 multi-month view. Spec §5.2 + §6.4."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, Query

from api.routes.sessions import get_manager
from api.state import SessionManager
from core.db.historical_repo import query_range

router = APIRouter()


@router.get("/sessions/{session_id}/history")
def get_history(
    session_id: str,
    n: int = Query(default=12, ge=1, le=48),
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Returns N months of historical_counts grouped by (hospital, sigla).

    Args:
        session_id: Session identifier (used for routing; window is time-based).
        n: Number of months to return, counting back from today inclusive.
        mgr: Injected SessionManager (DI via get_manager).

    Returns:
        Dict mapping "HOSPITAL|sigla" keys to lists of monthly records,
        each with year, month, count, confidence, method fields.
    """
    today = datetime.utcnow()
    to_year, to_month = today.year, today.month
    to_idx = to_year * 12 + (to_month - 1)
    from_idx = to_idx - (n - 1)
    from_year, from_month_zero = divmod(from_idx, 12)
    from_month = from_month_zero + 1

    rows = query_range(
        mgr._conn,
        from_year=from_year,
        from_month=from_month,
        to_year=to_year,
        to_month=to_month,
    )

    # HistoricalCount is a frozen dataclass — use attribute access.
    grouped: dict[str, list] = defaultdict(list)
    for row in rows:
        key = f"{row.hospital}|{row.sigla}"
        grouped[key].append(
            {
                "year": row.year,
                "month": row.month,
                "count": row.count,
                "confidence": row.confidence,
                "method": row.method,
            }
        )
    return dict(grouped)
