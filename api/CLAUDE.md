# api/ — FastAPI Backend

## Routes

- `routes/months.py` — `GET /api/months` (list available months), `GET /api/months/{session_id}` (month inventory: 4 hospitals × 20 cells with folder + `pdf_count_hint`).
- `routes/sessions/` — session lifecycle and editing. A **package**, not a single file:
  - `lifecycle.py` — `POST /api/sessions` (open/return a session), `GET /api/sessions/{id}` (persisted state).
  - `scan.py` — `POST /api/sessions/{id}/scan` (pase 1), `POST /api/sessions/{id}/scan-ocr` (pase 2 batch; returns `{accepted, total, total_pdfs}` and streams progress over the WS), `POST /api/sessions/{id}/cancel`, single-file OCR, `POST .../apply-ratio` (RN). Self-lend (v1/v1.1): a scan request carries `participant_id`, which becomes the launcher's identity for the run (`ctx["launcher_id"]`) — the scanner claims its OWN already-held cells instead of skipping them, then re-promotes the launcher back to editor on each self-lent cell when the run ends (`promote_lender`).
  - `writes.py` — single-cell edit endpoints: override, per-file override, near-match clear, worker-count, note, confirm, **colado-suspect dismiss** (`POST .../colado-suspects/{id}/dismiss` — anti-colados; 404 on unknown id). Each enforces the M3 per-cell lock via `participant_id`.
  - `files.py` — per-cell file listing + serving one PDF.
  - `reorg.py` — reorg-op create/delete + manifest export (Incr J).
  - `_common.py` — shared kernel (DI, session-id/cell-coord validation, broadcast helpers) the sub-routers import from.
- `routes/siglas.py` — `GET /api/siglas/{sigla}/scan-info` — what the pase-2 OCR looks for.
- `routes/output.py` — `POST /api/sessions/{id}/output` — generate the RESUMEN Excel (atomic tmp→bak→rename).
- `routes/history.py` — historical per-cell counts (range queries over `historical_counts`).
- `routes/presence.py` — `GET /api/sessions/{id}/presence` (read-only live snapshot, same shape as the WS `presence` event — lets a headless client, e.g. Claude driving the API, poll without a WS connection; no broadcast/lease side-effect), `POST /api/sessions/{id}/presence/{heartbeat,focus,leave}` — multiplayer M2 HTTP up-channel (no locking/enforcement here; that lives in the `sessions/` write routes, M3).
- `routes/ws.py` — `WS /ws/sessions/{session_id}` — progress events (`scan_started`, `cell_scanning`, `pdf_progress`, `pdf_page_progress` [in-flight PDF page counter, throttled 0.3 s], `cell_done`/`cell_error`, `scan_complete`/`scan_cancelled`), `cell_updated`/`session_refresh`/`presence` broadcasts, + 15 s keepalive ping.

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `INFORME_MENSUAL_ROOT` | `A:/informe mensual` | Root of the source month folders (read-only corpus) |
| `OVERSEER_DB_PATH` | `A:/PROJECTS/PDFoverseer/data/overseer.db` | SQLite path: session state + `historical_counts` |
| `OVERSEER_OUTPUT_DIR` | `A:/PROJECTS/PDFoverseer/data/outputs` | Where the generated RESUMEN Excel is written |
| `TESSERACT_CMD` | `C:\Program Files\Tesseract-OCR\tesseract.exe` | Override the Tesseract binary path (hardcoded Windows default in `core/ocr.py` / `pagination_count.py`) |
| `OVERSEER_OCR_THREADS` | `min(6, cpu-2)` | Per-page OCR thread-pool size for both scanner engines (`core/utils.py::OCR_PAGE_THREADS`); `1` forces the legacy sequential per-page path |
| `HOST` | `127.0.0.1` | Server bind address (`server.py`) |
| `PORT` | `8000` | Server port |

## Security

- **Session IDs:** validated as `YYYY-MM` (regex `^(\d{4})-(0[1-9]|1[0-2])$`) before use; malformed IDs are rejected with HTTP 400.
- **Read-only corpus:** the app only reads from `INFORME_MENSUAL_ROOT`; it never writes there. Generated output goes to `OVERSEER_OUTPUT_DIR`.
- **Server bind:** defaults to `127.0.0.1` — set `HOST=0.0.0.0` explicitly to expose on the network.
