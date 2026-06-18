# Multiplayer M1 — Fundación de sincronización · Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que dos navegadores (en máquinas distintas de la LAN) abiertos en el mismo mes vean en vivo lo que edita el otro, sin presencia ni locks todavía.

**Architecture:** Broadcast-on-write server-autoritativo sobre el WS por-sesión que ya existe. Cada endpoint que escribe una celda difunde `cell_updated` con el **snapshot completo** de la celda; el frontend **reemplaza la celda entera** en su store. Las operaciones que tocan varias celdas (escaneo pase-1, ops de reorg) difunden `session_refresh` (re-fetch completo). Como TODOS los handlers de ruta son `def` síncronos, la difusión se marshalea al event loop guardado (`app.state.loop`) vía `asyncio.run_coroutine_threadsafe`, igual que el escaneo ya hace hoy. Auto-sanación: el cliente re-fetchea la sesión completa al reconectar el WS y al recuperar foco de pestaña. Exposición LAN: el host del backend se deriva de `window.location.hostname` (hoy hay 3 fuentes hardcodeadas a `127.0.0.1`).

**Tech Stack:** FastAPI (rutas síncronas + WS), Python 3.10+, pytest + `fastapi.testclient.TestClient` (con `websocket_connect`); React + Zustand, Vitest.

**Spec:** `docs/superpowers/specs/2026-06-18-multiplayer-colaboracion-design.md` (§3, §4, §11, §12 M1). Decisiones: §15.

**Convenciones del repo (recordatorio para el implementador):**
- `ruff check .` debe dar **0 violaciones** antes de cada commit. Tipos 3.10+ (`X | None`, `list[X]`).
- Sin `print()` en `api/` (usar `logging`). Sin `except:` desnudo. Sin mock de DB en tests (usar fixtures reales / DB temporal).
- Commits en inglés, `type(scope): message`. Trailer **verbatim**: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Trabajar **directo en `po_overhaul`**. Un commit por tarea.
- **NO** tocar datos en vivo de MAYO (`2026-05`). Los tests usan DB temporal (`OVERSEER_DB_PATH` → `tmp_path`), nunca la real.

---

## Contexto del código que vas a tocar (léelo antes de empezar)

**Backend — `api/routes/sessions.py`:**
- `GET /sessions/{id}` (`def get`, ~L362) devuelve `mgr.get_session_state(session_id)`: un dict con `cells[hospital][sigla]` = el **dict crudo de la celda**. Ese es el shape exacto que `cell_updated.cell` debe llevar.
- El escaneo pase-2 (`scan_ocr`, ~L487) corre en un hilo del pool. Su closure `_safe_broadcast` (~L560) ya hace `asyncio.run_coroutine_threadsafe(broadcast(session_id, event), loop)` con `loop = app.state.loop` y guarda `loop.is_closed()`. El drain `on_progress` (~L571) llama `_safe_broadcast(_apply_scan_event(mgr, session_id, event))`. `_apply_scan_event` (~L416, módulo-nivel, testeable) en `cell_done` hace `finalize_cell_ocr` y devuelve el evento enriquecido.
- El escaneo pase-1 (`scan`, ~L376, **síncrono**) recorre `mgr.apply_cell_result(...)` para todas las celdas y luego `refresh_reorg_deltas(...)`. No emite eventos WS por celda hoy.
- Endpoints de escritura de **una** celda: `apply_ratio` (~L273), `patch_override` (~L685), `patch_per_file_override` (~L730), `clear_near_matches` (~L783), `patch_worker_count` (~L812), `patch_note` (~L863), `patch_confirm` (~L899), `scan_file_ocr` (~L624, ya tiene `request`). Ops de reorg (session-wide vía `refresh_reorg_deltas`): `create_reorg_op` (~L1066), `delete_reorg_op` (~L1104).
- **Quiénes YA reciben `request: Request`:** `scan_ocr`, `scan_file_ocr`, `cancel`. **Quiénes NO (hay que agregárselo):** `apply_ratio`, `patch_override`, `patch_per_file_override`, `clear_near_matches`, `patch_worker_count`, `patch_note`, `patch_confirm`, `create_reorg_op`, `delete_reorg_op`. `request: Request` se agrega como **primer parámetro** (FastAPI lo inyecta por tipo; el orden entre params sin default es libre).
- `app.state.loop = asyncio.get_running_loop()` se fija en el startup (`api/main.py:39`), así que `request.app.state.loop` está disponible en cualquier ruta.
- Import ya presente: `from api.routes.ws import broadcast`, `import asyncio`.

**WS — `api/routes/ws.py`:** `broadcast(session_id, event)` (async) manda el JSON a `_CONNECTIONS[session_id]`. Keepalive `{"type":"ping"}` cada 15 s.

**Patrón de test WS probado (míralo): `tests/unit/api/test_ws_broadcast.py`** — usa `TestClient(app)` + `client.websocket_connect("/ws/sessions/{id}")` + `ws.receive_text()` + `json.loads`. `app` se crea con `create_app()` y `OVERSEER_DB_PATH` → `tmp_path`.

**Frontend:**
- `frontend/src/lib/ws.js` — `createWSClient(sessionId, {onEvent, factory, initialBackoffMs})`. Reconecta con backoff. Hoy define su propio `WS_BASE` (IIFE, L13-18) con `127.0.0.1` hardcodeado. El handler `open` solo resetea backoff (NO re-fetchea).
- `frontend/src/lib/api.js` — L1 `const BASE = "http://127.0.0.1:8000/api";`.
- `frontend/src/lib/constants.js` — L1-2 `API_BASE`/`WS_BASE` hardcodeados (otra def de `WS_BASE`, independiente de ws.js).
- `frontend/src/store/session.js` — Zustand. `openMonth` (~L58) crea el WS con `onEvent: get()._handleWSEvent` y hace `api.getSession`. `_handleWSEvent` (~L638) tiene casos `cell_scanning`/`cell_done`/etc. `cell_done` (~L649) hace merge **parcial** (6 campos) + borra de `scanningCells` + sube `filesTick`. `_ws` guarda el cliente WS.

---

## Chunk 1: Backend — broadcast-on-write

### Task 1: Event builder `_cell_updated_event` + helper `_emit`

**Files:**
- Modify: `api/routes/sessions.py` (agregar 2 helpers módulo-nivel, cerca de `_apply_scan_event`)
- Test: `tests/unit/api/test_multiplayer_sync.py` (crear)

- [ ] **Step 1: Escribe el test que falla (el builder arma el evento con la celda completa)**

Crear `tests/unit/api/test_multiplayer_sync.py`:

```python
"""M1 multiplayer — broadcast-on-write: cell_updated + session_refresh."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.routes.sessions import _cell_updated_event, get_manager


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "mp_test.db"))
    return create_app()


def _recv_type(ws, expected_type, tries=5):
    """Lee frames del WS hasta hallar el tipo esperado (salta el keepalive ``ping``
    u otros eventos que lleguen antes). Evita flakes y mantiene TODOS los tests WS
    consistentes (un solo patrón de recepción)."""
    for _ in range(tries):
        evt = json.loads(ws.receive_text())
        if evt.get("type") == expected_type:
            return evt
    raise AssertionError(f"no se recibió {expected_type} en {tries} frames")


def test_cell_updated_event_carries_full_cell(app) -> None:
    """_cell_updated_event devuelve el snapshot COMPLETO de la celda (no parcial)."""
    mgr = app.state.manager
    mgr.open_session(year=2026, month=4, month_root=__import__("pathlib").Path("."))
    mgr.apply_user_override("2026-04", "HPV", "odi", value=7)
    mgr.set_note("2026-04", "HPV", "odi", text="ojo", status="por_resolver")

    event = _cell_updated_event(mgr, "2026-04", "HPV", "odi")

    assert event["type"] == "cell_updated"
    assert event["hospital"] == "HPV"
    assert event["sigla"] == "odi"
    assert event["actor"] is None  # M1: sin identidad todavía
    # snapshot completo: incluye override Y note (un merge de 6 campos los perdería)
    assert event["cell"]["user_override"] == 7
    assert event["cell"]["note"] == "ojo"
    assert event["cell"]["note_status"] == "por_resolver"


def test_cell_updated_event_missing_cell_returns_none(app) -> None:
    """Celda ausente → None (no revienta)."""
    mgr = app.state.manager
    mgr.open_session(year=2026, month=4, month_root=__import__("pathlib").Path("."))
    assert _cell_updated_event(mgr, "2026-04", "HPV", "nope") is None
```

- [ ] **Step 2: Corre el test para verque falla**

Run: `pytest tests/unit/api/test_multiplayer_sync.py -v`
Expected: FAIL — `ImportError: cannot import name '_cell_updated_event'`.

- [ ] **Step 3: Implementa los helpers**

En `api/routes/sessions.py`, justo **después** de `_apply_scan_event` (~L463), agrega:

```python
def _cell_updated_event(
    mgr: SessionManager, session_id: str, hospital: str, sigla: str
) -> dict | None:
    """Arma el evento ``cell_updated`` con el snapshot COMPLETO de la celda (M1).

    Lleva la celda entera (no un merge por campos) porque un cambio remoto puede
    tocar cualquier campo; el frontend reemplaza la celda completa. ``actor`` es
    ``None`` en M1 (la identidad llega en M2). Devuelve ``None`` si la celda no
    existe (nunca revienta el camino de escritura).
    """
    try:
        cell = mgr.get_session_state(session_id)["cells"][hospital][sigla]
    except KeyError:
        return None
    return {
        "type": "cell_updated",
        "hospital": hospital,
        "sigla": sigla,
        "actor": None,
        "cell": cell,
    }


def _emit(request: Request, session_id: str, event: dict) -> None:
    """Programa un broadcast WS desde un handler de ruta síncrono (M1).

    Los handlers son ``def`` síncronos → corren en un hilo del threadpool sin event
    loop, así que marshaleamos al loop guardado del app, igual que
    ``scan_ocr._safe_broadcast``. Se descarta el evento si el loop ya se cerró
    (teardown de TestClient) en vez de reventar el hilo.
    """
    loop = request.app.state.loop
    try:
        if not loop.is_closed():
            asyncio.run_coroutine_threadsafe(broadcast(session_id, event), loop)
    except RuntimeError:
        pass


def _broadcast_cell_updated(
    request: Request, mgr: SessionManager, session_id: str, hospital: str, sigla: str
) -> None:
    """Difunde ``cell_updated`` para una celda tras escribirla (M1, punto único)."""
    event = _cell_updated_event(mgr, session_id, hospital, sigla)
    if event is not None:
        _emit(request, session_id, event)


def _broadcast_session_refresh(request: Request, session_id: str) -> None:
    """Difunde ``session_refresh`` tras una operación que toca varias celdas (M1)."""
    _emit(request, session_id, {"type": "session_refresh"})
```

- [ ] **Step 4: Corre el test para verque pasa**

Run: `pytest tests/unit/api/test_multiplayer_sync.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: ruff + commit**

```bash
ruff check api/routes/sessions.py tests/unit/api/test_multiplayer_sync.py
git add api/routes/sessions.py tests/unit/api/test_multiplayer_sync.py
git commit -m "feat(multiplayer): cell_updated event builder + sync broadcast helpers (M1)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `patch_override` difunde `cell_updated` (establece el patrón de wiring)

**Files:**
- Modify: `api/routes/sessions.py` (`patch_override`, ~L685)
- Test: `tests/unit/api/test_multiplayer_sync.py`

- [ ] **Step 1: Escribe el test que falla (WS recibe cell_updated tras el PATCH override)**

Agrega a `tests/unit/api/test_multiplayer_sync.py`:

```python
def _open_session(client: TestClient) -> None:
    """Abre la sesión 2026-04 vía API (usa el corpus real montado en el repo)."""
    r = client.post("/api/sessions", json={"year": 2026, "month": 4})
    assert r.status_code == 200


def test_patch_override_broadcasts_cell_updated(app) -> None:
    """Un PATCH de override entrega cell_updated (celda completa) por el WS."""
    with TestClient(app) as client:
        _open_session(client)
        with client.websocket_connect("/ws/sessions/2026-04") as ws:
            r = client.patch(
                "/api/sessions/2026-04/cells/HPV/odi/override",
                json={"value": 9},
            )
            assert r.status_code == 200
            evt = _recv_type(ws, "cell_updated")
            assert evt["hospital"] == "HPV"
            assert evt["sigla"] == "odi"
            assert evt["cell"]["user_override"] == 9
```

> Nota: `_open_session` abre la sesión real (mes ABRIL del corpus). Si en el entorno de CI el corpus no está, usar `app.state.manager.open_session(...)` directo como en Task 1 y golpear el endpoint igual; el override no requiere PDFs en disco.

- [ ] **Step 2: Corre el test → FALLA**

Run: `pytest tests/unit/api/test_multiplayer_sync.py::test_patch_override_broadcasts_cell_updated -v`
Expected: FAIL — `ws.receive_text()` se cuelga/timeoutea (no llega cell_updated) o recibe solo el `ping`.

- [ ] **Step 3: Implementa — agrega `request` + el broadcast**

En `patch_override` (~L686), agrega `request: Request` como primer parámetro:

```python
@router.patch("/sessions/{session_id}/cells/{hospital}/{sigla}/override")
def patch_override(
    request: Request,
    session_id: str,
    hospital: str,
    sigla: str,
    ...
```

Y **después** de `mgr.apply_user_override(...)` (~L716) y de cualquier `refresh_all_reliable`/recálculo que ya haga la ruta, justo antes del `return`, agrega:

```python
    _broadcast_cell_updated(request, mgr, session_id, hospital, sigla)
```

(Colócalo después de TODA mutación de la celda en esa ruta, para que el snapshot incluya el `all_reliable` recomputado.)

- [ ] **Step 4: Corre el test → PASA**

Run: `pytest tests/unit/api/test_multiplayer_sync.py::test_patch_override_broadcasts_cell_updated -v`
Expected: PASS.

- [ ] **Step 5: ruff + commit**

```bash
ruff check api/routes/sessions.py
git add api/routes/sessions.py tests/unit/api/test_multiplayer_sync.py
git commit -m "feat(multiplayer): patch_override broadcasts cell_updated (M1)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Wire los demás endpoints de una-celda a `cell_updated`

Aplica el **mismo patrón** de Task 2 (agregar `request: Request` como primer param si falta + `_broadcast_cell_updated(request, mgr, session_id, hospital, sigla)` después de toda mutación, antes del `return`) a:

- `apply_ratio` (~L274, el `def`; L273 es el modelo `ApplyRatioRequest`) — agregar `request`.
- `patch_per_file_override` (~L730) — agregar `request`.
- `clear_near_matches` (~L783) — agregar `request`.
- `patch_worker_count` (~L812) — agregar `request`.
- `patch_note` (~L863) — agregar `request`.
- `patch_confirm` (~L899) — agregar `request`.
- `scan_file_ocr` (~L624) — **CASO ESPECIAL, NO uses el patrón "antes del return".** Aquí la escritura del `per_file` ocurre en un **hilo de fondo** (`_run` → `scan_one_file_ocr` → `on_progress`), DESPUÉS de que el handler ya retornó `{"accepted": True, ...}`. Emitir `cell_updated` en el `return` síncrono (~L682) difundiría un snapshot **viejo** (aún sin el merge). La emisión va **dentro del closure `on_progress`** (~L652), justo **después** del `apply_per_file_ocr_result(...)` (~L656-664), usando el `loop` ya capturado (igual que el `broadcast` de L653 — NO `_emit(request,...)`):

  ```python
      def on_progress(event: dict) -> None:
          asyncio.run_coroutine_threadsafe(broadcast(session_id, event), loop)
          if event.get("type") == "file_scan_done":
              r = event["result"]
              mgr.apply_per_file_ocr_result(
                  session_id, hospital, sigla, filename,
                  count=r["ocr_count"], method=r["method"],
                  near_matches=r.get("near_matches") or [],
              )
              # M1: tras fusionar el per_file, difunde la celda completa para los demás clientes.
              cu = _cell_updated_event(mgr, session_id, hospital, sigla)
              if cu is not None:
                  asyncio.run_coroutine_threadsafe(broadcast(session_id, cu), loop)
  ```

**Files:**
- Modify: `api/routes/sessions.py`
- Test: `tests/unit/api/test_multiplayer_sync.py`

- [ ] **Step 1: Escribe tests que fallan (2 representativos: note y worker-count)**

```python
def test_patch_note_broadcasts_cell_updated(app) -> None:
    with TestClient(app) as client:
        _open_session(client)
        with client.websocket_connect("/ws/sessions/2026-04") as ws:
            r = client.patch(
                "/api/sessions/2026-04/cells/HRB/odi/note",
                json={"text": "revisar colado", "status": "por_resolver"},
            )
            assert r.status_code == 200
            evt = _recv_type(ws, "cell_updated")
            assert evt["cell"]["note"] == "revisar colado"


def test_patch_worker_count_broadcasts_cell_updated(app) -> None:
    with TestClient(app) as client:
        _open_session(client)
        with client.websocket_connect("/ws/sessions/2026-04") as ws:
            r = client.patch(
                "/api/sessions/2026-04/cells/HLL/charla/worker-count",
                json={"status": "en_progreso"},
            )
            assert r.status_code == 200
            evt = _recv_type(ws, "cell_updated")
            assert evt["cell"]["worker_status"] == "en_progreso"
```

- [ ] **Step 2: Corre → FALLAN** (`pytest tests/unit/api/test_multiplayer_sync.py -v`).
- [ ] **Step 3: Implementa el wiring en los 7 endpoints** (request + `_broadcast_cell_updated`).
- [ ] **Step 4: Corre → PASAN** + corre TODO el archivo para no romper nada:

Run: `pytest tests/unit/api/test_multiplayer_sync.py -v`
Expected: PASS (todos).

- [ ] **Step 5: ruff + commit**

```bash
ruff check api/routes/sessions.py
git add api/routes/sessions.py tests/unit/api/test_multiplayer_sync.py
git commit -m "feat(multiplayer): all single-cell write endpoints broadcast cell_updated (M1)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Escaneo pase-2 emite `cell_updated` por celda terminada

**Files:**
- Modify: `api/routes/sessions.py` (`on_progress` dentro de `scan_ocr`, ~L571)
- Test: `tests/unit/api/test_multiplayer_sync.py`

El escaneo ya difunde `cell_done` (parcial, para progreso). Agregamos `cell_updated` (celda completa) tras cada `cell_done`, reusando `_cell_updated_event` + el `_safe_broadcast` existente.

- [ ] **Step 1: Escribe el test que falla (el drain emite cell_updated tras cell_done)**

Testeamos la lógica de drain sin el ProcessPool: simulamos `on_progress` llamando `_apply_scan_event` + el nuevo emit. Como `on_progress` es un closure, extraemos la decisión a un helper módulo-nivel testeable `_scan_followup_event`:

```python
def test_scan_followup_emits_cell_updated_after_cell_done(app) -> None:
    """Tras un cell_done, el drain del escaneo debe emitir un cell_updated completo."""
    from api.routes.sessions import _scan_followup_event
    mgr = app.state.manager
    mgr.open_session(year=2026, month=4, month_root=__import__("pathlib").Path("."))
    mgr.apply_user_override("2026-04", "HPV", "odi", value=3)

    done_event = {"type": "cell_done", "hospital": "HPV", "sigla": "odi", "result": {}}
    followup = _scan_followup_event(mgr, "2026-04", done_event)
    assert followup is not None
    assert followup["type"] == "cell_updated"
    assert followup["cell"]["user_override"] == 3

    # un evento que no es cell_done no genera followup
    assert _scan_followup_event(mgr, "2026-04", {"type": "file_result"}) is None
```

- [ ] **Step 2: Corre → FALLA** (`ImportError: _scan_followup_event`).

- [ ] **Step 3: Implementa el helper + úsalo en on_progress**

Agrega módulo-nivel (cerca de `_cell_updated_event`):

```python
def _scan_followup_event(mgr: SessionManager, session_id: str, event: dict) -> dict | None:
    """Tras un ``cell_done`` del escaneo, arma el ``cell_updated`` con la celda
    completa (el ``cell_done`` solo lleva los 6 campos del progreso). Cualquier otro
    evento → ``None`` (no genera seguimiento). M1.
    """
    if event.get("type") != "cell_done":
        return None
    return _cell_updated_event(mgr, session_id, event["hospital"], event["sigla"])
```

**Modifica la función existente** `on_progress` (dentro de `scan_ocr`, ~L571) — NO la redefinas, solo agrega las 3 líneas del `followup` tras el `_safe_broadcast` que ya tiene, para que quede así:

```python
    def on_progress(event: dict) -> None:
        _safe_broadcast(_apply_scan_event(mgr, session_id, event))
        followup = _scan_followup_event(mgr, session_id, event)   # ← nuevo
        if followup is not None:                                   # ← nuevo
            _safe_broadcast(followup)                              # ← nuevo
```

- [ ] **Step 4: Corre → PASA** (`pytest tests/unit/api/test_multiplayer_sync.py -v`).

- [ ] **Step 5: ruff + commit**

```bash
ruff check api/routes/sessions.py
git add api/routes/sessions.py tests/unit/api/test_multiplayer_sync.py
git commit -m "feat(multiplayer): pase-2 scan emits cell_updated per finished cell (M1)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `session_refresh` tras pase-1 + ops de reorg

**Files:**
- Modify: `api/routes/sessions.py` (`scan` ~L376, `create_reorg_op` ~L1066, `delete_reorg_op` ~L1104)
- Test: `tests/unit/api/test_multiplayer_sync.py`

- [ ] **Step 1: Escribe el test que falla (WS recibe session_refresh tras POST /scan)**

```python
def test_scan_broadcasts_session_refresh(app) -> None:
    """Un pase-1 (POST /scan) toca muchas celdas → difunde session_refresh."""
    with TestClient(app) as client:
        _open_session(client)
        with client.websocket_connect("/ws/sessions/2026-04") as ws:
            r = client.post("/api/sessions/2026-04/scan", json={"scope": "all"})
            assert r.status_code == 200
            evt = _recv_type(ws, "session_refresh")  # salta pings (helper de Task 1)
            assert evt["type"] == "session_refresh"
```

- [ ] **Step 2: Corre → FALLA** (timeout / nunca llega session_refresh).

- [ ] **Step 3: Implementa**

- `scan` (~L376): agregar `request: Request` como primer param; tras `refresh_reorg_deltas(...)` y antes del `return`, agregar `_broadcast_session_refresh(request, session_id)`.
- `create_reorg_op` (~L1066) y `delete_reorg_op` (~L1104): agregar `request: Request`; tras `refresh_reorg_deltas(...)` (que ya llaman) y antes del `return`, agregar `_broadcast_session_refresh(request, session_id)`.

- [ ] **Step 4: Corre → PASA** (`pytest tests/unit/api/test_multiplayer_sync.py -v`).

- [ ] **Step 5: ruff + commit**

```bash
ruff check api/routes/sessions.py
git add api/routes/sessions.py tests/unit/api/test_multiplayer_sync.py
git commit -m "feat(multiplayer): pase-1 scan + reorg ops broadcast session_refresh (M1)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Verificación de no-regresión backend

**Files:** ninguno (solo corridas).

- [ ] **Step 1: Suite backend completa**

Run: `pytest -q`
Expected: todo verde (los ~775 de antes + los nuevos de `test_multiplayer_sync.py`; 0 fallos). Si algún test existente de `scan_ocr`/`scan` se rompe por la firma `request` nueva, NO es esperable (los tests llaman por HTTP, no construyen el handler) — investiga antes de seguir.

- [ ] **Step 2: ruff global**

Run: `ruff check .`
Expected: `All checks passed!`

> Sin commit (no hay cambios); es un gate.

---

## Chunk 2: Frontend — merge en vivo, auto-sanación, host LAN

### Task 7: Módulo de config — host del backend desde `window.location`

**Files:**
- Create: `frontend/src/lib/config.js`
- Modify: `frontend/src/lib/ws.js`, `frontend/src/lib/api.js`, `frontend/src/lib/constants.js`
- Test: `frontend/src/lib/config.test.js` (crear)

- [ ] **Step 1: Escribe el test que falla**

Crear `frontend/src/lib/config.test.js`:

```js
import { describe, it, expect } from "vitest";
import { backendHost, makeApiBase, makeWsBase } from "./config";

describe("config host derivation", () => {
  it("usa el hostname de la página (LAN), no 127.0.0.1", () => {
    expect(backendHost("192.168.1.50")).toBe("192.168.1.50");
  });
  it("cae a 127.0.0.1 cuando no hay hostname (SSR/test)", () => {
    expect(backendHost("")).toBe("127.0.0.1");
    expect(backendHost(undefined)).toBe("127.0.0.1");
  });
  it("arma API y WS base con el host derivado y puerto 8000", () => {
    expect(makeApiBase("192.168.1.50", "http:")).toBe("http://192.168.1.50:8000/api");
    expect(makeWsBase("192.168.1.50", "http:")).toBe("ws://192.168.1.50:8000");
    expect(makeWsBase("192.168.1.50", "https:")).toBe("wss://192.168.1.50:8000");
  });
});
```

- [ ] **Step 2: Corre → FALLA**

Run: `cd frontend && npx vitest run src/lib/config.test.js`
Expected: FAIL — no existe `./config`.

- [ ] **Step 3: Implementa `config.js`**

```js
/**
 * Single source of truth for the backend host (M1 multiplayer / LAN).
 *
 * The host is derived from the page's own hostname so a LAN client (Carla's
 * browser, loaded from the server's IP) hits THAT server — not her own
 * localhost. Falls back to 127.0.0.1 for SSR/tests. Backend port is 8000.
 */
const PORT = 8000;

export function backendHost(hostname) {
  return hostname || "127.0.0.1";
}

export function makeApiBase(hostname, pageProto) {
  const proto = pageProto === "https:" ? "https:" : "http:";
  return `${proto}//${backendHost(hostname)}:${PORT}/api`;
}

export function makeWsBase(hostname, pageProto) {
  const proto = pageProto === "https:" ? "wss:" : "ws:";
  return `${proto}//${backendHost(hostname)}:${PORT}`;
}

const _hostname = typeof window !== "undefined" ? window.location?.hostname : "";
const _proto = typeof window !== "undefined" ? window.location?.protocol : "http:";

export const API_BASE = makeApiBase(_hostname, _proto);
export const WS_BASE = makeWsBase(_hostname, _proto);
```

- [ ] **Step 4: Corre → PASA**

Run: `cd frontend && npx vitest run src/lib/config.test.js`
Expected: PASS.

- [ ] **Step 5: Repunta las 3 fuentes hardcodeadas a `config.js`**

- `frontend/src/lib/constants.js`: reemplaza **solo las líneas 1-2** (las defs de `API_BASE`/`WS_BASE`) por un re-export. **CONSERVA intactas** las demás exports del archivo (`CTA_LLENAR_MANUAL`, `OCR_CONFIRM_PDF_THRESHOLD`, `OCR_EST_SECONDS_PER_PDF` y cualquier otra) — NO reescribas el archivo entero. Queda:
  ```js
  export { API_BASE, WS_BASE } from "./config";

  export const CTA_LLENAR_MANUAL = "Llenar manualmente →";
  // ... (resto de constantes existentes SIN cambios) ...
  ```
- `frontend/src/lib/api.js` L1:
  ```js
  import { API_BASE } from "./config";
  const BASE = API_BASE;
  ```
- `frontend/src/lib/ws.js` L13-18: borra el IIFE local de `WS_BASE` e importa:
  ```js
  import { WS_BASE } from "./config";
  ```
  (Mantén el resto de `ws.js` igual; `WS_BASE` se usa en `createWSClient` para armar la URL.)

- [ ] **Step 6: Verifica que no quedó ningún `127.0.0.1` hardcodeado en src/lib**

Run: `cd frontend && npx vitest run && grep -rn "127.0.0.1" src/lib/ || echo "no hardcoded host"`
Expected: vitest verde; el grep solo debe encontrar `config.js` (el fallback) — ninguna otra.

- [ ] **Step 7: Commit**

```bash
cd .. && git add frontend/src/lib/config.js frontend/src/lib/config.test.js frontend/src/lib/ws.js frontend/src/lib/api.js frontend/src/lib/constants.js
git commit -m "feat(multiplayer): derive backend host from window.location (LAN) (M1)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Store — `cell_updated` reemplaza la celda completa

**Files:**
- Modify: `frontend/src/store/session.js` (`_handleWSEvent`, ~L638)
- Test: `frontend/src/store/session.cellUpdated.test.js` (crear)

- [ ] **Step 1: Escribe el test que falla**

Mira un test de store existente (`frontend/src/store/session.autoscan.test.js`) para el patrón de setup del store. Crear `frontend/src/store/session.cellUpdated.test.js`:

```js
import { describe, it, expect, beforeEach } from "vitest";
import { useSessionStore } from "./session";

function seedSession() {
  useSessionStore.setState({
    session: {
      session_id: "2026-04",
      cells: { HPV: { odi: { user_override: 1, note: "vieja", per_file: { "a.pdf": 1 } } } },
    },
    filesTick: {},
  });
}

describe("_handleWSEvent cell_updated", () => {
  beforeEach(seedSession);

  it("reemplaza la celda ENTERA con el snapshot del evento", () => {
    const newCell = { user_override: 5, note: "nueva", note_status: "resuelto", per_file: { "a.pdf": 2 } };
    useSessionStore.getState()._handleWSEvent({
      type: "cell_updated", hospital: "HPV", sigla: "odi", actor: null, cell: newCell,
    });
    const cell = useSessionStore.getState().session.cells.HPV.odi;
    expect(cell).toEqual(newCell);          // reemplazo total
    expect(cell.note).toBe("nueva");
  });

  it("sube filesTick para que FileList/lightbox re-fetcheen", () => {
    useSessionStore.getState()._handleWSEvent({
      type: "cell_updated", hospital: "HPV", sigla: "odi", actor: null, cell: { per_file: {} },
    });
    expect(useSessionStore.getState().filesTick["HPV|odi"]).toBe(1);
  });

  it("no revienta si no hay sesión", () => {
    useSessionStore.setState({ session: null });
    expect(() =>
      useSessionStore.getState()._handleWSEvent({
        type: "cell_updated", hospital: "HPV", sigla: "odi", cell: {} })
    ).not.toThrow();
  });
});
```

- [ ] **Step 2: Corre → FALLA**

Run: `cd frontend && npx vitest run src/store/session.cellUpdated.test.js`
Expected: FAIL (no existe el caso `cell_updated`; la celda no se reemplaza).

- [ ] **Step 3: Implementa el caso `cell_updated`**

En `_handleWSEvent` (`frontend/src/store/session.js`), agrega un caso (junto a `cell_done`):

```js
      case "cell_updated": {
        const session = state.session;
        if (!session) break;
        const cells = { ...session.cells };
        const hosp = { ...(cells[event.hospital] || {}) };
        hosp[event.sigla] = event.cell;           // reemplazo de celda COMPLETA (§4)
        cells[event.hospital] = hosp;
        const tickKey = cellKey(event.hospital, event.sigla);
        const filesTick = {
          ...state.filesTick,
          [tickKey]: (state.filesTick[tickKey] ?? 0) + 1,
        };
        set({ session: { ...session, cells }, filesTick });
        break;
      }
```

- [ ] **Step 4: Corre → PASA**

Run: `cd frontend && npx vitest run src/store/session.cellUpdated.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd .. && git add frontend/src/store/session.js frontend/src/store/session.cellUpdated.test.js
git commit -m "feat(multiplayer): cell_updated replaces the whole cell in the store (M1)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Store — `refetchSession` + caso `session_refresh`

**Files:**
- Modify: `frontend/src/store/session.js` (agregar action `refetchSession` + caso `session_refresh` en `_handleWSEvent`)
- Test: `frontend/src/store/session.refetch.test.js` (crear)

- [ ] **Step 1: Escribe el test que falla**

Crear `frontend/src/store/session.refetch.test.js`. Mockea `api.getSession` (mock del módulo `../lib/api`, NO de la DB — el repo prohíbe mockear DB, no el cliente HTTP del frontend):

```js
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../lib/api", () => ({
  api: { getSession: vi.fn(async () => ({ session_id: "2026-04", cells: { HPV: { odi: { user_override: 42 } } } })) },
}));

import { useSessionStore } from "./session";
import { api } from "../lib/api";

describe("session_refresh / refetchSession", () => {
  beforeEach(() => {
    api.getSession.mockClear();
    useSessionStore.setState({ session: { session_id: "2026-04", cells: {} } });
  });

  it("refetchSession reemplaza la sesión con la del servidor", async () => {
    await useSessionStore.getState().refetchSession("2026-04");
    expect(api.getSession).toHaveBeenCalledWith("2026-04");
    expect(useSessionStore.getState().session.cells.HPV.odi.user_override).toBe(42);
  });

  it("session_refresh dispara un refetch de la sesión activa", async () => {
    useSessionStore.getState()._handleWSEvent({ type: "session_refresh" });
    // refetchSession es fire-and-forget async; espera a que se complete sin asumir
    // un nº fijo de microtasks (robusto si el mock cambia a uno con latencia).
    await vi.waitFor(() => expect(api.getSession).toHaveBeenCalledWith("2026-04"));
  });
});
```

- [ ] **Step 2: Corre → FALLA** (`refetchSession` no existe; sin caso `session_refresh`).

- [ ] **Step 3: Implementa**

Agrega la action en el store (junto a las demás):

```js
  refetchSession: async (sessionId) => {
    try {
      const session = await api.getSession(sessionId);
      set({ session });
    } catch (error) {
      console.error("refetchSession failed", error);
    }
  },
```

Y el caso en `_handleWSEvent`:

```js
      case "session_refresh": {
        const sid = state.session?.session_id;
        if (sid) get().refetchSession(sid);
        break;
      }
```

- [ ] **Step 4: Corre → PASA**

Run: `cd frontend && npx vitest run src/store/session.refetch.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd .. && git add frontend/src/store/session.js frontend/src/store/session.refetch.test.js
git commit -m "feat(multiplayer): refetchSession action + session_refresh handler (M1)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Auto-sanación — re-fetch al reconectar el WS

**Files:**
- Modify: `frontend/src/lib/ws.js` (callback `onReconnect`), `frontend/src/store/session.js` (pasar `onReconnect`)
- Test: `frontend/src/lib/ws.reconnect.test.js` (crear)

`ws.js` hoy reconecta pero NO avisa. Agregamos un callback `onReconnect` que se dispara en el `open` **posterior** al primer connect (es decir, en una reconexión real), para que el store re-fetchee y recupere lo que se perdió mientras estuvo caído.

- [ ] **Step 1: Escribe el test que falla**

Mira el patrón de `factory` (inyección de WebSocket fake) que `createWSClient` ya soporta. Crear `frontend/src/lib/ws.reconnect.test.js`:

```js
import { describe, it, expect, vi } from "vitest";
import { createWSClient } from "./ws";

function makeFakeWS() {
  const listeners = {};
  return {
    addEventListener: (t, fn) => { (listeners[t] ||= []).push(fn); },
    close: () => {},
    _fire: (t, e = {}) => (listeners[t] || []).forEach((fn) => fn(e)),
  };
}

describe("createWSClient onReconnect", () => {
  it("NO llama onReconnect en el primer open; SÍ en el open tras una reconexión", () => {
    const sockets = [];
    const factory = () => { const s = makeFakeWS(); sockets.push(s); return s; };
    const onReconnect = vi.fn();
    createWSClient("2026-04", { onEvent: () => {}, factory, onReconnect, initialBackoffMs: 1 });

    sockets[0]._fire("open");          // primer connect
    expect(onReconnect).not.toHaveBeenCalled();

    sockets[0]._fire("close");         // se cae → agenda reconexión
    return new Promise((r) => setTimeout(r, 5)).then(() => {
      sockets[1]._fire("open");        // reconectado
      expect(onReconnect).toHaveBeenCalledTimes(1);
    });
  });
});
```

- [ ] **Step 2: Corre → FALLA** (`onReconnect` no se invoca).

- [ ] **Step 3: Implementa**

En `createWSClient` agrega `onReconnect` a las opciones y una bandera de "ya conectó una vez":

```js
export function createWSClient(sessionId, { onEvent, factory, onReconnect, initialBackoffMs = 1000 } = {}) {
  ...
  let hasConnected = false;
  ...
    socket.addEventListener("open", () => {
      backoff = initialBackoffMs;
      if (hasConnected) onReconnect?.();   // open posterior al primero = reconexión
      hasConnected = true;
    });
```

En el store (`openMonth`, donde se crea el WS, ~L65), pasa el callback:

```js
      const ws = createWSClient(sessionId, {
        onEvent: get()._handleWSEvent,
        onReconnect: () => get().refetchSession(sessionId),
      });
```

- [ ] **Step 4: Corre → PASA**

Run: `cd frontend && npx vitest run src/lib/ws.reconnect.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd .. && git add frontend/src/lib/ws.js frontend/src/store/session.js frontend/src/lib/ws.reconnect.test.js
git commit -m "feat(multiplayer): refetch session on WS reconnect (auto-heal) (M1)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Auto-sanación — re-fetch al recuperar foco de pestaña

**Files:**
- Modify: `frontend/src/store/session.js` (`openMonth` agrega listener `visibilitychange`; teardown lo quita)
- Test: `frontend/src/store/session.visibility.test.js` (crear)

Cuando la pestaña vuelve a estar visible (Carla la tenía en segundo plano), re-fetcheamos por si se perdió algún evento. El listener se monta en `openMonth` y se limpia al cambiar de mes / cerrar WS.

- [ ] **Step 1: Escribe el test que falla**

```js
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../lib/api", () => ({
  api: {
    getSession: vi.fn(async () => ({ session_id: "2026-04", cells: {} })),
    createSession: vi.fn(async () => ({})),
    listMonths: vi.fn(async () => ({ months: [] })),
  },
}));
vi.mock("../lib/ws", () => ({ createWSClient: () => ({ close: () => {} }) }));

import { useSessionStore } from "./session";
import { api } from "../lib/api";

describe("refetch on visibilitychange", () => {
  beforeEach(() => api.getSession.mockClear());

  it("re-fetchea cuando la pestaña vuelve a visible", async () => {
    await useSessionStore.getState().openMonth("2026-04", 2026, 4);
    api.getSession.mockClear();

    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
    await Promise.resolve();

    expect(api.getSession).toHaveBeenCalledWith("2026-04");
  });
});
```

- [ ] **Step 2: Corre → FALLA**.

- [ ] **Step 3: Implementa**

En el state inicial del store agrega `_visHandler: null`. En `openMonth`, tras crear el WS:

```js
      // Auto-heal: re-fetch on tab refocus (a dropped event leaves us stale).
      const prevVis = get()._visHandler;
      if (prevVis) document.removeEventListener("visibilitychange", prevVis);
      const visHandler = () => {
        if (document.visibilityState === "visible") get().refetchSession(sessionId);
      };
      document.addEventListener("visibilitychange", visHandler);
      set({ _visHandler: visHandler });
```

(Inclúyelo en el mismo `set({...})` que ya hace `openMonth` o en uno adicional — lo importante es que `_visHandler` quede guardado.) Y donde se hace teardown del WS (`get()._ws?.close()` al re-abrir o salir), quita también el listener:

```js
      get()._ws?.close();
      const prevVisHandler = get()._visHandler;
      if (prevVisHandler) document.removeEventListener("visibilitychange", prevVisHandler);
```

- [ ] **Step 4: Corre → PASA**

Run: `cd frontend && npx vitest run src/store/session.visibility.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd .. && git add frontend/src/store/session.js frontend/src/store/session.visibility.test.js
git commit -m "feat(multiplayer): refetch session on tab refocus (auto-heal) (M1)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: Verificación de no-regresión frontend + build

**Files:** ninguno (gate).

- [ ] **Step 1: Vitest completo**

Run: `cd frontend && npx vitest run`
Expected: todo verde (los ~175 de antes + los nuevos).

- [ ] **Step 2: Build de producción** (la UI de LAN sale del build estático servido por FastAPI en `:8000/ui`)

Run: `cd frontend && npm run build`
Expected: build OK, sin errores.

> Sin commit (gate).

---

## Smoke manual (lo corre Daniel, no es tarea de subagente)

M1 no tiene smoke de navegador automatizable (el MCP no alcanza a Brave). Criterio de aceptación del spec (§12 M1):

1. Backend con `HOST=0.0.0.0`: `HOST=0.0.0.0 python server.py`.
2. Desde una **segunda máquina** de la LAN, abrir `http://<IP-del-server>:8000/ui` (build estático).
3. En la máquina 1, editar una celda (override / nota). **Verificar** que en la máquina 2 el conteo/nota cambia **en vivo** sin recargar.
4. Cortar el WiFi de la máquina 2 unos segundos y reconectar → al volver, su vista se re-sincroniza (auto-heal).

---

## Notas de diseño (por qué así)

- **Punto único de choque = dos helpers** (`_broadcast_cell_updated` / `_broadcast_session_refresh`) llamados al final de cada ruta de escritura (enfoque (b) del spec §4: la ruta conoce hospital/sigla). Un setter nuevo en el futuro debe acordarse de llamar al helper — es el costo de (b) frente a un decorador; aceptable y explícito.
- **Una sola vía de emisión real:** como TODOS los handlers son `def` síncronos, tanto las rutas de edición como el escaneo usan el puente `run_coroutine_threadsafe(broadcast(...), app.state.loop)`. (El spec §4 mencionaba `await` directo para rutas async; en este código no hay rutas async, así que el puente es universal.)
- **`actor: None` en M1:** sin identidad todavía; el editor recibe su propio `cell_updated` y lo re-aplica (idempotente, mismo dato). El filtrado por `actor` llega en M2 con `participant_id`.
- **`cell_done` se deja intacto** (sigue manejando `scanningCells`/`filesTick`); `cell_updated` (celda completa) lo complementa y gana el estado final porque ambos derivan del mismo `finalize_cell_ocr`.
