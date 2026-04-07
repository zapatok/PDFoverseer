# api/ — FastAPI Backend

## Routes

- `routes/files.py` — `/api/browse`, `/api/add_folder`, `/api/add_files`, `/api/preview`
- `routes/sessions.py` — `/api/sessions`, `/api/reset`, `/api/correct`, etc.
- `routes/pipeline.py` — `/api/start`, `/api/stop`, `/api/state`

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `HOST` | `127.0.0.1` | Server bind address (`server.py`) |
| `PORT` | `8000` | Server port |
| `TESSERACT_CMD` | system PATH | Override Tesseract binary path |
| `PDF_ROOT` | _(required)_ | Allowed root dir for PDF path validation |
| `SESSION_TTL` | `3600` | Session TTL in seconds before eviction |

## Security

- **Path validation:** `routes/files.py` validates all submitted paths against `PDF_ROOT` to prevent directory traversal
- **subprocess.call** in `api_open_pdf` uses list form `[opener, str(path)]` — no shell injection possible; path is pre-validated against `pdf_list`
- **Session IDs:** validated as UUID4 format before use; invalid IDs rejected with HTTP 400 / WS close 4003
- **Server bind:** defaults to `127.0.0.1` — set `HOST=0.0.0.0` explicitly to expose on network
