# api/ — FastAPI Backend

## Routes

- `routes/months.py` — `GET /api/months` (list available months), `GET /api/months/{session_id}` (month inventory: 4 hospitals × 18 cells with folder + `pdf_count_hint`).
- `routes/sessions.py` — session lifecycle and editing:
  - `POST /api/sessions` (open/return a session), `GET /api/sessions/{id}` (persisted state).
  - `POST /api/sessions/{id}/scan` — pase 1 (filename glob).
  - `POST /api/sessions/{id}/scan-ocr` — pase 2 (OCR batch); returns `{accepted, total, total_pdfs}` and streams progress over the WS.
  - `POST /api/sessions/{id}/cancel` — cooperative cancel of the running batch.
  - per-cell / per-file edit endpoints (override, per-file count, cell files listing).
- `routes/output.py` — `POST /api/sessions/{id}/output` — generate the RESUMEN Excel (atomic tmp→bak→rename).
- `routes/history.py` — historical per-cell counts (range queries over `historical_counts`).
- `routes/ws.py` — `WS /ws/sessions/{session_id}` — progress events (`scan_started`, `cell_scanning`, `pdf_progress`, `cell_done`/`cell_error`, `scan_complete`/`scan_cancelled`) + 15 s keepalive ping.

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
