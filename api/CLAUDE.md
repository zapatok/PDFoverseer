# api/ — FastAPI Backend

## Routes

- `routes/months.py` — `GET /api/months` (list available months), `GET /api/months/{session_id}` (month inventory: 4 hospitals × 20 cells with folder + `pdf_count_hint`).
- `routes/sessions/` — session lifecycle and editing. A **package**, not a single file:
  - `lifecycle.py` — `POST /api/sessions` (open/return a session), `GET /api/sessions/{id}` (persisted state).
  - `scan.py` — `POST /api/sessions/{id}/scan` (pase 1), `POST /api/sessions/{id}/scan-ocr` (pase 2 batch; returns `{accepted, total, total_pdfs}` and streams progress over the WS), `POST /api/sessions/{id}/cancel`, single-file OCR, `POST .../apply-ratio` (RN).
  - `writes.py` — single-cell edit endpoints: override, per-file override, near-match clear, worker-count, note, confirm. Each enforces the M3 per-cell lock via `participant_id`.
  - `files.py` — per-cell file listing + serving one PDF.
  - `reorg.py` — reorg-op create/delete + manifest export (Incr J).
  - `_common.py` — shared kernel (DI, session-id/cell-coord validation, broadcast helpers) the sub-routers import from.
- `routes/siglas.py` — `GET /api/siglas/{sigla}/scan-info` — what the pase-2 OCR looks for.
- `routes/output.py` — `POST /api/sessions/{id}/output` — generate the RESUMEN Excel (atomic tmp→bak→rename).
- `routes/history.py` — historical per-cell counts (range queries over `historical_counts`).
- `routes/presence.py` — `POST /api/sessions/{id}/presence/{heartbeat,focus,leave}` — multiplayer M2 HTTP up-channel (no locking/enforcement here; that lives in the `sessions/` write routes, M3).
- `routes/ws.py` — `WS /ws/sessions/{session_id}` — progress events (`scan_started`, `cell_scanning`, `pdf_progress`, `cell_done`/`cell_error`, `scan_complete`/`scan_cancelled`), `cell_updated`/`session_refresh`/`presence` broadcasts, + 15 s keepalive ping.

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `INFORME_MENSUAL_ROOT` | `A:/informe mensual` | Root of the source month folders (read-only corpus) |
| `OVERSEER_DB_PATH` | `A:/PROJECTS/PDFoverseer/data/overseer.db` | SQLite path: session state + `historical_counts` |
| `OVERSEER_OUTPUT_DIR` | `A:/PROJECTS/PDFoverseer/data/outputs` | Where the generated RESUMEN Excel is written |
| `TESSERACT_CMD` | system PATH | Override the Tesseract binary path |
| `HOST` | `127.0.0.1` | Server bind address (`server.py`) |
| `PORT` | `8000` | Server port |

## Security

- **Session IDs:** validated as `YYYY-MM` (regex `^(\d{4})-(0[1-9]|1[0-2])$`) before use; malformed IDs are rejected with HTTP 400.
- **Read-only corpus:** the app only reads from `INFORME_MENSUAL_ROOT`; it never writes there. Generated output goes to `OVERSEER_OUTPUT_DIR`.
- **Server bind:** defaults to `127.0.0.1` — set `HOST=0.0.0.0` explicitly to expose on the network.
