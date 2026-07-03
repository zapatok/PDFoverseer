# api/

FastAPI backend: session state, SQLite-backed persistence, the pase-2 OCR batch
orchestrator, WebSocket broadcasts, and multiplayer presence/locks.

## Files

- `main.py` — app factory + lifespan
- `state.py` — `SessionManager`, the bridge between requests and the DB (single `RLock`)
- `presence.py` — in-memory multiplayer presence registry (M2/M3a/M3b) — ephemeral, never persisted
- `reorg.py` — pure reorg-op validation/manifest helpers (no I/O, no FastAPI)
- `batch.py` — pase-2 OCR batch lifecycle (`BatchHandle`, cooperative cancellation)
- `routes/` — one router module per concern: `months`, `siglas`, `output`, `history`, `presence`, `ws`
- `routes/sessions/` — session lifecycle + editing, split into `lifecycle`/`scan`/`writes`/`files`/`reorg` sub-routers over a shared `_common` kernel

**Architecture and conventions live in `api/CLAUDE.md`** — this file intentionally defers to it.
