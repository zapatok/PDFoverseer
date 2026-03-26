# api/

Backend layer: session state, WebSocket, database I/O, background worker, and HTTP routes.

## Modules

### state.py
`SessionState` + `SessionManager`. One `SessionState` per client session — holds scan progress,
document counts, issue list, OCR metrics, pause/cancel events. `SessionManager` manages the
session map with TTL-based eviction (`SESSION_TTL` env var, default 3600s). `get_session()`
is a FastAPI dependency that validates UUID4 format before returning the session.

### database.py
SQLite read/write for the `page_reads` table. Functions: `save_reads()`, `has_reads()`,
`get_reads()`, `clear_session()`. Database path: `data/sessions.db`.

### websocket.py
WebSocket connection manager + `_emit()` helper. `_emit()` is the single point of contact
for pushing real-time events to the frontend. All log messages, progress updates, and issue
notifications go through `_emit()`.

### worker.py
Background scan thread. `run_scan()` iterates the session's `pdf_list`, calls `analyze_pdf()`
per file, and uses callbacks to feed results back via `_emit()`. `_recalculate_metrics()`
rebuilds aggregate counts from raw `page_reads` after corrections.

## routes/

### routes/pipeline.py
`/api/start`, `/api/stop`, `/api/state` — scan lifecycle control.

### routes/files.py
`/api/browse`, `/api/add_folder`, `/api/add_files`, `/api/preview` — file discovery and
PDF preview. All paths validated against `PDF_ROOT` env var to prevent directory traversal.

### routes/sessions.py
`/api/sessions`, `/api/reset`, `/api/correct`, `/api/exclude`, `/api/restore` — session
management and manual correction of document boundaries.
