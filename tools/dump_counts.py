"""Dump every cell's effective counts as JSON — the audit-remediation output guard."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.state import SessionManager  # noqa: E402
from core.cell_count import compute_cell_count, compute_worker_count  # noqa: E402
from core.db.connection import open_connection  # noqa: E402
from core.scanners.patterns import count_type_for  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="path to a COPY of overseer.db")
    args = ap.parse_args()
    conn = open_connection(Path(args.db))
    rows = conn.execute("SELECT session_id FROM sessions ORDER BY session_id").fetchall()
    mgr = SessionManager(conn)
    out: dict = {}
    for (sid,) in rows:
        state = mgr.get_session_state(sid)
        cells = {}
        for hosp, sigla_map in state.get("cells", {}).items():
            for sigla, cell in sigla_map.items():
                cells[f"{hosp}|{sigla}"] = {
                    "count": compute_cell_count(cell, count_type_for(sigla)),
                    "worker": compute_worker_count(cell),
                }
        out[sid] = cells
    print(json.dumps(out, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
