# Multiplayer M3b — Claude como participante de pleno derecho + escáner que respeta locks · Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax. Subagents are **Sonnet minimum** (never Haiku).

**Goal:** Claude se conecta con su perfil fijo (`participant_id="claude"`, `kind="agent"`) y puede **hacer lo mismo que cualquier usuario** vía la API — editar cualquier celda (override/nota/trabajadores/confirmar/per-archivo/ratio) reclamándola atómicamente (libre → la toma y escribe; ocupada por otro → **409**, no pisa). Y el **escáner** (pase 1 nombres + pase 2 OCR) actúa como ese mismo participante: por celda, **salta** las que un humano está editando (en vez de pisarlas), emite `cell_skipped`, y reporta el resumen en `scan_complete.skipped`. Los humanos ven el badge de Claude (distinto de los humanos) en la celda que toca y, por M3a, la ven en **solo-lectura** mientras Claude la edita.

**Architecture:** Una sola **primitiva de claim de agente** en el `PresenceRegistry` (M3a) — `agent_focus`/`agent_claim_cell` bajo el `RLock` único de `SessionManager` — con **dos reacciones** según el llamador: los **endpoints de escritura** la usan con auto-claim (libre → reclama + escribe; ocupada → 409, ya en M3a); el **escáner** la usa con skip (ocupada por humano → no toca + `cell_skipped`; libre → reclama como `claude`, escribe, sigue). La presencia de Claude es **efímera** (nunca persiste, §9) y su badge sale gratis por la maquinaria de presencia de M2 + el gating de solo-lectura de M3a (que ya trata a `claude` como holder).

**Tech Stack:** FastAPI (handlers sync, `@_synchronized` + `RLock`, exception handler→409 de M3a), `PresenceRegistry` en memoria, escáner multi-worker (`core/orchestrator.py::scan_cells_ocr` + hilo de drain), React + Zustand v5, vitest.

**Spec:** `docs/superpowers/specs/2026-06-18-multiplayer-colaboracion-design.md` §6.4 (camino Claude = claim-y-escritura atómico), §8 (Claude como participante: identidad fija, por-celda-activa, respeta locks; el borde "usuario tiene la celda abierta" se resuelve **conversacionalmente**, NO con un endpoint de "prestar lock" — no construir tal endpoint), §10 (escaneo masivo vs locks: chequeo justo antes de mutar cada celda, evento `cell_skipped`, `scan_complete.skipped`), §12 (M3). Este plan es **M3b** — cierra la etapa M3 (M3a humanos ✅ shipped, tag `multiplayer-m3a`).

**Branch:** trabajar directo en `po_overhaul`; push al cierre de la ronda.

---

## Decisiones de diseño (leer antes de codear)

1. **Identidad fija del agente, una sola fuente.** `participant_id="claude"`, `name="Claude"`,
   `kind="agent"`, color reservado distinto de los 6 humanos (los humanos eligen entre `COLORS` en
   `identity.js`; Claude usa uno fuera de esa lista, p. ej. un slate/cian). Vive en constantes
   backend (`api/presence.py`) y se refleja en el frontend solo para el render del badge.
2. **Una primitiva, dos reacciones.** El núcleo es "¿esta celda la tiene OTRO participante como
   `editor`?" — ya existe: `_editor_conflict(session_id, h, s, participant_id="claude")` /
   `lock_holder(cell, exclude="claude")` (M3a). M3b añade el **claim de agente**: registrar/refrescar
   a `claude` enfocado en la celda (`mode="editor"`, `kind="agent"`, lease) **bajo el mismo RLock**.
   - **Endpoints de escritura (reacción 409):** si la tiene otro → `CellLockedError`→409 (M3a, sin
     cambio); si está libre y el escritor es el agente → **auto-claim** (Claude pasa a editor → badge)
     y escribe. Para un humano en celda libre, M3a no reclama (el navegador hizo `focus` antes); eso
     **no cambia**.
   - **Escáner (reacción skip):** si la tiene otro humano → **no la toca**, emite `cell_skipped`,
     la acumula para `scan_complete.skipped`; si está libre → la reclama como `claude` (badge salta) y
     escribe.
3. **El gating de solo-lectura ya sirve para Claude (M3a).** `cellLockHolder` devuelve a quien sea el
   `editor` (humano o agente). Cuando Claude edita una celda, los demás ven el banner + controles
   deshabilitados **sin código nuevo**. M3b solo añade que el **badge** distinga al agente
   visualmente (icono de bot en vez de iniciales) — ver Chunk 4.
4. **El escáner decide saltar/reclamar al INICIO de cada celda** (`cell_scanning`), lo registra en un
   `skipped_set` del closure `on_progress`, y **corta** los eventos posteriores de esa celda
   (`pdf_progress`/`file_result`/`cell_done`) sin aplicarlos ni difundirlos. Cobertura del caso
   dominante (alguien YA está editando la celda cuando se lanza el escaneo). **Micro-carrera aceptada:**
   con `max_workers=2`, un humano podría tomar una celda en los ~segundos entre el `cell_scanning` y su
   escritura; el riesgo es last-writer-wins en esa celda (recuperable, no corrupción) y es despreciable
   en una herramienta LAN de 2-3 personas. Mismo razonamiento de exclusividad-de-editor que M3a. (Una
   versión por-escritura totalmente atómica se difiere; no vale la complejidad aquí.)
5. **Pase 1 (nombres) chequea-y-salta sin reclamar el badge.** Es un barrido masivo de ~4 s sobre 72
   celdas; reclamar a `claude` por celda haría parpadear el badge 72 veces. Pase 1 solo **consulta**
   `presence_lock_holder(cell, exclude="claude")` por celda y salta si un humano la tiene; devuelve los
   saltos en la respuesta JSON + emite `cell_skipped`. Esto es **adicional** al clobber-guard
   `_cell_has_work` existente (ese protege ediciones ya commiteadas; este protege una **edición en vivo**
   de una celda que el humano abrió pero aún no tocó).
6. **Presencia de Claude efímera + ciclo de vida del escaneo.** El escáner registra a `claude` al
   reclamar la primera celda y lo **libera** (`presence_leave("claude")`) al emitir `scan_complete`
   (o `scan_cancelled`, o el `scan_complete` de crash). Difunde un snapshot `presence` al reclamar y
   al liberar para que el badge aparezca/desaparezca. Nada se persiste (§9).
7. **Restricción dura heredada:** un solo proceso uvicorn (nunca `--workers N`); el registro vive en
   ese proceso (§11). No tocar.

## File structure

**Backend:**
- `api/presence.py` — constantes de identidad del agente (`AGENT_PARTICIPANT_ID="claude"`,
  `AGENT_NAME="Claude"`, `AGENT_COLOR`, `AGENT_KIND="agent"`) + `is_agent(pid)` helper +
  `agent_focus(session_id, cell)` (registra/refresca a `claude` enfocado en `cell`, `mode="editor"`,
  devuelve `changed: bool`).
- `api/state.py` — `agent_claim_cell(session_id, hospital, sigla) -> dict | None` (`@_synchronized`:
  holder si la tiene otro, si no reclama claude y devuelve None) + un auto-claim del agente en los 6
  métodos de escritura (tras el chequeo de conflicto de M3a).
- `api/routes/sessions.py` — los 6 routes de escritura difunden `presence` tras una escritura de
  agente; el escáner (closure `on_progress` de `scan_ocr` + bucle de `scan`) hace claim/skip y emite
  `cell_skipped` + enriquece `scan_complete` con `skipped`.
- `api/routes/ws.py` / `_emit` — sin cambios (reusa el bridge).
- Tests: `tests/unit/api/test_agent_claim.py` (primitiva + auto-claim de escritura),
  `tests/integration/test_scanner_lock_skip.py` (escáner salta celda bloqueada).

**Frontend:**
- `frontend/src/lib/identity.js` — constantes del agente para el render del badge (`AGENT_*`), o un
  pequeño `lib/agent.js`.
- `frontend/src/components/PresenceBadge.jsx` — render distinto para `kind === "agent"` (icono `Bot`
  de lucide en vez de iniciales).
- `frontend/src/store/session.js` — caso `cell_skipped` + campo `skipped` en `scan_complete`.
- `frontend/src/components/ScanProgress.jsx` — resumen "Completado · N saltadas (en edición)" con
  lista + botón "Re-escanear saltadas"; persistente (sin auto-dismiss) cuando hubo saltos.
- vitest: `presence.test.js` (badge agente si aplica lógica pura), `store/session.skip.test.js`
  (cell_skipped + scan_complete.skipped).

## Constantes / naming
- Identidad del agente SOLO en `api/presence.py` (backend autoritativo); el frontend duplica el color
  + name para el render, marcado como espejo.
- Evento de salto (contrato, §10): `{"type":"cell_skipped","hospital":...,"sigla":...,"reason":"locked","lock_holder":{participant_id,name,color,kind}}`.
- `scan_complete` extendido: `{"type":"scan_complete","scanned":int,"errors":int,"cancelled":int,"skipped":[{"hospital":...,"sigla":...},...]}` (campo `skipped` nuevo; default `[]`).

---

## Chunk 1: Identidad del agente + primitiva de claim

### Task 1: Constantes de agente + `agent_focus` en el registro

**Files:** Modify `api/presence.py`; Test `tests/unit/api/test_agent_claim.py`

- [ ] **Step 1: Escribir el test que falla** `tests/unit/api/test_agent_claim.py`:

```python
from api.presence import (
    PresenceRegistry, AGENT_PARTICIPANT_ID, AGENT_NAME, AGENT_KIND, is_agent,
)

def _reg():
    return PresenceRegistry(now=lambda: 1000.0)

def test_is_agent():
    assert is_agent(AGENT_PARTICIPANT_ID)
    assert not is_agent("some-uuid")
    assert not is_agent(None)

def test_agent_focus_registers_and_claims_free_cell():
    r = _reg()
    changed = r.agent_focus("m", "HRB|odi")
    assert changed is True
    rec = next(p for p in r.snapshot("m") if p["participant_id"] == AGENT_PARTICIPANT_ID)
    assert rec["name"] == AGENT_NAME
    assert rec["kind"] == AGENT_KIND
    assert rec["focused_cell"] == "HRB|odi"
    assert rec["mode"] == "editor"

def test_agent_focus_on_human_held_cell_makes_agent_viewer():
    r = _reg()
    r.heartbeat("m", "p1", name="Daniel", color="#a")
    r.focus("m", "p1", "HRB|odi")          # human editor
    r.agent_focus("m", "HRB|odi")           # agent joins -> viewer (does NOT steal)
    snap = {p["participant_id"]: p for p in r.snapshot("m")}
    assert snap["p1"]["mode"] == "editor"
    assert snap[AGENT_PARTICIPANT_ID]["mode"] == "viewer"

def test_agent_focus_none_releases():
    r = _reg()
    r.agent_focus("m", "HRB|odi")
    r.agent_focus("m", None)
    assert r.lock_holder("m", "HRB|odi", exclude="p9") is None
```

- [ ] **Step 2: Correr, ver que falla** (faltan constantes + `agent_focus`).
- [ ] **Step 3: Implementar** en `api/presence.py` (a nivel módulo, junto a `PRESENCE_TTL_SECONDS`):

```python
AGENT_PARTICIPANT_ID = "claude"
AGENT_NAME = "Claude"
AGENT_COLOR = "#0ea5e9"   # cian/sky — fuera de los 6 colores humanos de identity.js
AGENT_KIND = "agent"

def is_agent(participant_id: str | None) -> bool:
    return participant_id == AGENT_PARTICIPANT_ID
```

Y un método en `PresenceRegistry` que registra-o-refresca al agente y reclama (reusa la lógica de
`focus` pero auto-provee la identidad del agente y crea el record si no existe):

```python
    def agent_focus(self, session_id: str, cell: str | None) -> bool:
        """Register/refresh the Claude agent focused on `cell` (claim under the
        caller's RLock). Free cell -> agent is editor; held by another -> viewer
        (never steals). cell=None releases. Returns True iff the roster changed."""
        changed = self._purge_expired(session_id)
        members = self._participants.setdefault(session_id, {})
        rec = members.get(AGENT_PARTICIPANT_ID)
        if rec is None:
            rec = members[AGENT_PARTICIPANT_ID] = {
                "participant_id": AGENT_PARTICIPANT_ID,
                "name": AGENT_NAME,
                "color": AGENT_COLOR,
                "kind": AGENT_KIND,
                "focused_cell": None,
                "mode": "editor",
                "expires_at": self._now() + PRESENCE_TTL_SECONDS,
            }
            changed = True
        rec["expires_at"] = self._now() + PRESENCE_TTL_SECONDS
        if cell is None:
            new_mode = "editor"
        else:
            new_mode = "viewer" if self._editor_of(session_id, cell, exclude=AGENT_PARTICIPANT_ID) else "editor"
        if rec["focused_cell"] != cell or rec["mode"] != new_mode:
            rec["focused_cell"] = cell
            rec["mode"] = new_mode
            return True
        return changed
```

> Release semantics **espejan `focus` de M3a** (shipped): al soltar (`cell=None`) el `mode` vuelve a
> `"editor"` por defecto — es inocuo porque `_editor_of` exige `focused_cell == cell`, así que un record
> con `focused_cell=None` nunca bloquea nada. El `return changed` (de `_purge_expired`) en el camino
> sin-cambio-de-record es el MISMO patrón que `focus`/`heartbeat` de M2/M3a (un purge SÍ cambió el
> roster → difundir es correcto). No "arreglar" esto; mantener paridad con `focus`.

- [ ] **Step 4: Correr, ver verde.**
- [ ] **Step 5: Commit** — `feat(multiplayer): Claude agent identity + agent_focus claim (M3b)`

### Task 2: `agent_claim_cell` en SessionManager

**Files:** Modify `api/state.py`; Test `tests/unit/api/test_agent_claim.py`

- [ ] **Step 1:** Añadir un método `@_synchronized` (junto a los pass-throughs de presencia ~L720-746)
  que reclama-o-reporta-conflicto atómicamente:

```python
    @_synchronized
    def agent_claim_cell(self, session_id, hospital, sigla):
        """Atomic claim for the Claude scanner/agent. Returns the human holder dict
        if the cell is held by a DIFFERENT participant (caller should SKIP/409), else
        claims the cell for the agent and returns None. Single RLock = no TOCTOU."""
        cell = f"{hospital}|{sigla}"
        holder = self._presence.lock_holder(session_id, cell, exclude=AGENT_PARTICIPANT_ID)
        if holder is not None:
            return holder
        self._presence.agent_focus(session_id, cell)
        return None
```

Importar `AGENT_PARTICIPANT_ID` (y `is_agent`, que usará Task 3) desde `api.presence` en el top de
`state.py` (ya importa de ahí en M3a). Añadir un pass-through `@_synchronized agent_leave(session_id)`
que llama `self._presence.leave(session_id, AGENT_PARTICIPANT_ID)` (para el cleanup del escáner).

- [ ] **Step 2: Test** (manager real + tmp DB, copiando el idiom de `test_presence_locks.py`):
  - celda libre → `agent_claim_cell` devuelve None y deja a claude como editor
    (`presence_lock_holder(cell, exclude="x")` ahora devuelve a claude);
  - celda con editor humano → devuelve el holder humano y NO registra a claude como editor de ella;
  - `agent_leave` quita a claude del snapshot.
  - **Claim atómico (spec §13), test de concurrencia:** lanzar dos `mgr.agent_claim_cell(...)` a la
    MISMA celda libre desde dos hilos (`threading.Thread`) y afirmar que ambos devuelven None pero el
    registro queda consistente (claude editor una sola vez); y un `agent_claim_cell` vs un
    `presence_focus` humano concurrentes a la misma celda libre → **exactamente uno** gana editorship
    (el otro ve al primero como holder / queda viewer). El `RLock` único serializa: usar una
    `threading.Barrier(2)` para soltar ambos hilos a la vez y afirmar el invariante "a-lo-más-un-editor".
- [ ] **Step 3:** Correr, ver verde.
- [ ] **Step 4: Commit** — `feat(multiplayer): SessionManager.agent_claim_cell + agent_leave (M3b)`

> **Chunk 1 review:** plan-document-reviewer + `pytest tests/unit/api/test_agent_claim.py tests/unit/api/test_presence_locks.py -v` + `ruff check api/ tests/`.

---

## Chunk 2: Endpoints de escritura — Claude reclama-y-escribe

### Task 3: Auto-claim del agente en los métodos de escritura

**Files:** Modify `api/state.py`; Test `tests/unit/api/test_agent_claim.py`

Los 6 métodos de escritura (M3a, todos `@_synchronized`, todos con `participant_id` keyword): tras el
chequeo de conflicto que YA tienen (`holder = self._editor_conflict(...); if holder: raise CellLockedError`),
añadir el **auto-claim del agente** como la siguiente línea:

```python
        # M3b: an agent write to a FREE cell claims it (so Claude becomes the editor
        # and its badge shows + others go read-only). Humans don't auto-claim here
        # (their browser focus-claimed first). No-op for humans / held cells.
        if is_agent(participant_id):
            self._presence.agent_focus(session_id, f"{hospital}|{sigla}")
```

(Ubicación: inmediatamente después del bloque `if holder is not None: raise CellLockedError`. El
conflicto ya garantizó que la celda no la tiene otro, así que `agent_focus` aquí siempre deja a claude
como editor.) Aplicar a: `apply_user_override`, `set_note`, `apply_per_file_override`,
`apply_worker_count`, `apply_confirmed`, `clear_near_matches`. (apply-ratio: ver Task 4, via la ruta.)

- [ ] **Step 1: Test** (manager real + tmp DB) en `test_agent_claim.py`:

```python
def test_agent_write_claims_free_cell(tmp_path):
    mgr = _mgr(tmp_path)
    mgr.apply_user_override("2026-04", "HRB", "odi", value=5, participant_id="claude")  # free -> claims
    holder = mgr.presence_lock_holder("2026-04", "HRB|odi", exclude="someone-else")
    assert holder is not None and holder["participant_id"] == "claude" and holder["kind"] == "agent"

def test_agent_write_to_human_held_cell_409s(tmp_path):
    from api.presence import CellLockedError
    mgr = _mgr(tmp_path)
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")
    mgr.presence_focus("2026-04", "p1", "HRB|odi")          # human holds it
    with pytest.raises(CellLockedError):
        mgr.apply_user_override("2026-04", "HRB", "odi", value=5, participant_id="claude")

def test_human_write_free_cell_does_not_claim(tmp_path):
    mgr = _mgr(tmp_path)
    mgr.apply_user_override("2026-04", "HRB", "odi", value=5, participant_id="p1")   # human, no presence
    assert mgr.presence_lock_holder("2026-04", "HRB|odi", exclude="x") is None       # nobody claimed
```

(`_mgr` = el helper de tmp DB; copiar de `test_lock_enforcement.py`.)

- [ ] **Step 2:** Correr, ver verde (y que la suite de M3a `test_lock_enforcement.py` siga verde —
  el auto-claim es aditivo).
- [ ] **Step 3: Commit** — `feat(multiplayer): agent writes auto-claim a free cell (M3b)`

### Task 4: Las rutas de escritura difunden `presence` tras escritura de agente; apply-ratio

**Files:** Modify `api/routes/sessions.py`; Test `tests/unit/api/test_agent_claim.py`

- [ ] **Step 1:** Añadir un helper de difusión de presencia + combinarlo con el broadcast de celda que
  ya hacen las 6 rutas (M3a llama `_broadcast_cell_updated(request, mgr, session_id, h, s)` en cada
  una). Crear:

```python
def _broadcast_presence(request: Request, mgr: SessionManager, session_id: str) -> None:
    """Difunde el snapshot de presencia (badge del agente aparece/salta tras su escritura)."""
    _emit(request, session_id, {
        "type": "presence", "session_id": session_id,
        "participants": mgr.presence_snapshot(session_id),
    })
```

En cada una de las 6 rutas de escritura, **después** del `_broadcast_cell_updated(...)`, añadir:

```python
    if is_agent(participant_id):
        _broadcast_presence(request, mgr, session_id)
```

donde `participant_id` es el que la ruta ya extrae del body (M3a). Importar `is_agent` de `api.presence`.

- [ ] **Step 2: apply-ratio.** La ruta `apply_ratio` usa `mgr.check_cell_lock(...)` (M3a) antes del
  bucle. Cambiar a un patrón que, para el agente, **reclame** la celda libre (no solo cheque): si
  `is_agent(body.participant_id)` → `holder = mgr.agent_claim_cell(session_id, hospital, sigla)`;
  `if holder: raise CellLockedError(hospital, sigla, holder)` (el handler de M3a → 409); si None,
  claude quedó como editor. Para un humano, la rama queda **igual que M3a** (`check_cell_lock`); solo se
  añade la rama `is_agent` con `agent_claim_cell`. Tras el bucle + `_broadcast_cell_updated`, si agente →
  `_broadcast_presence(...)`. (Importar `CellLockedError`.)
  > **Badge tras una escritura de agente:** NO se llama `agent_leave` tras un override/nota/ratio. El
  > badge de Claude queda en esa celda hasta que (a) su próxima escritura mueve el `focused_cell`, o
  > (b) vence el lease de 45 s. Es **conforme al spec** (§6.3: cada escritura renueva el lease + fija
  > `focused_cell`; no hay "release tras cada escritura"). Solo el ESCÁNER libera explícitamente a
  > claude al terminar (Task 5), porque su badge "por-celda-activa" debe desaparecer al acabar el batch.
- [ ] **Step 3: Test de endpoint** (TestClient con `with`):

```python
def test_agent_override_endpoint_claims_and_broadcasts():
    with TestClient(create_app()) as c:
        r = c.patch("/api/sessions/2026-04/cells/HRB/odi/override",
                    json={"value": 5, "participant_id": "claude"})
        assert r.status_code == 200
        snap = c.get("/api/sessions/2026-04").json()  # cell persisted
        # presence: claude is editor of HRB|odi
        # (verificar via un endpoint de presencia o el snapshot; ajustar a lo disponible)

def test_agent_override_409_when_human_holds():
    with TestClient(create_app()) as c:
        c.post("/api/sessions/2026-04/presence/heartbeat", json={"participant_id":"p1","name":"Daniel","color":"#a"})
        c.post("/api/sessions/2026-04/presence/focus", json={"participant_id":"p1","cell":"HRB|odi"})
        r = c.patch("/api/sessions/2026-04/cells/HRB/odi/override",
                    json={"value": 5, "participant_id": "claude"})
        assert r.status_code == 409
        assert r.json()["lock_holder"]["name"] == "Daniel"
```

(Ajustar la verificación de presencia a lo que exista; si no hay GET de presencia, basta con afirmar
200 + el 409, y cubrir el claim a nivel manager en Task 3.)

- [ ] **Step 4:** Correr `pytest tests/ -k "agent or override or ratio or lock or presence" -q` → sin
  regresiones.
- [ ] **Step 5: Commit** — `feat(multiplayer): write routes broadcast Claude presence; apply-ratio agent claim (M3b)`

> **Chunk 2 review:** plan-document-reviewer + `pytest tests/ -q` (sin regresión a M1/M2/M3a/scan) + `ruff check .`.

---

## Chunk 3: El escáner respeta locks y salta (pase 2 + pase 1)

### Task 5: Pase 2 — claim/skip por celda + `cell_skipped` + `scan_complete.skipped`

**Files:** Modify `api/routes/sessions.py` (closure `on_progress` de `scan_ocr`); Test `tests/integration/test_scanner_lock_skip.py`

La lógica vive en el closure `on_progress` de `scan_ocr` (~L628-635) porque ahí está el `mgr`, el
`_safe_broadcast`, y se puede mantener estado por-escaneo. Diseño:

```python
    skipped_cells: list[dict] = []
    skipped_set: set[tuple[str, str]] = set()
    agent_active = {"on": False}

    def on_progress(event: dict) -> None:
        etype = event.get("type")
        h, s = event.get("hospital"), event.get("sigla")

        # 1) Al iniciar una celda: reclamar como claude, o saltarla si un humano la tiene.
        if etype == "cell_scanning":
            holder = mgr.agent_claim_cell(session_id, h, s)
            if holder is not None:
                skipped_set.add((h, s))
                skipped_cells.append({"hospital": h, "sigla": s})
                _safe_broadcast({"type": "cell_skipped", "hospital": h, "sigla": s,
                                 "reason": "locked", "lock_holder": holder})
                return  # no difundir cell_scanning para una celda saltada
            agent_active["on"] = True
            _safe_broadcast({"type": "presence", "session_id": session_id,
                             "participants": mgr.presence_snapshot(session_id)})

        # 2) Cortar TODO evento posterior de una celda saltada (no aplicar ni difundir).
        #    (no incluir "cell_scanning": cada celda emite uno solo, ya manejado en el paso 1).
        if (h, s) in skipped_set and etype in ("pdf_progress", "file_result", "cell_done"):
            return

        # 3) scan_complete/scan_cancelled: soltar a claude; enriquecer skipped SOLO en complete.
        if etype in ("scan_complete", "scan_cancelled"):
            if agent_active["on"]:
                mgr.agent_leave(session_id)
                agent_active["on"] = False
                _safe_broadcast({"type": "presence", "session_id": session_id,
                                 "participants": mgr.presence_snapshot(session_id)})
            if etype == "scan_complete":
                event = {**event, "skipped": skipped_cells}   # cancelado NO lleva skipped (decisión M1)
            _safe_broadcast(event)   # NB: scanner usa _safe_broadcast (hilo de drain), NO _emit
            return

        # 4) Camino normal (M1/1A): aplicar + difundir + followup cell_updated.
        _safe_broadcast(_apply_scan_event(mgr, session_id, event))
        followup = _scan_followup_event(mgr, session_id, event)
        if followup is not None:
            _safe_broadcast(followup)
```

Notas de implementación (confirmadas leyendo el código — NO re-investigar):
- **`scan_complete` SÍ pasa por `on_progress`** en ambos caminos del orchestrator (single-worker y
  multi-worker `scan_cells_ocr`). Por eso enriquecer en el closure es el punto único correcto.
- **`_scan_followup_event` devuelve `None` para todo evento ≠ `cell_done`** (`sessions.py` ~L505), así
  que el paso 3 puede saltarse el followup sin perder nada. El paso 3 reemplaza el pass-through de
  `_apply_scan_event` para `scan_complete` (que solo lo devolvía tal cual) — equivalente, más explícito.
- **`cell_skipped` se emite UNA sola vez por celda** (en el `cell_scanning`); el `skipped_set` corta el
  resto de eventos de esa celda.
- **`agent_claim_cell` corre bajo el `RLock`** (es `@_synchronized`) → chequeo+claim atómico.
- **Threading del broadcast:** dentro de `on_progress` (hilo de drain) usar SIEMPRE `_safe_broadcast`
  (marshalea al loop); `_emit` es solo para los handlers de ruta (hilo del request). No mezclar.
- **CRASH-PATH (C2, obligatorio):** el `except` de `_run` (~L648-664) emite un `scan_complete` crudo
  por `asyncio.run_coroutine_threadsafe(broadcast(...))`, **sin** pasar por `on_progress` → dejaría a
  claude pegado 45 s (badge zombie + celda bloqueada a nadie). En ese `except`, ANTES del broadcast del
  `scan_complete` de crash: `if agent_active["on"]: mgr.agent_leave(session_id)` + difundir el snapshot
  `presence` (mismo `run_coroutine_threadsafe`/`broadcast`). `agent_active` y `skipped_cells` son del
  closure exterior → accesibles desde `_run`. (El `scan_complete` de crash deja `skipped` ausente; el
  frontend usa `event.skipped ?? []`, así que no rompe — ver Task 7.)

- [ ] **Step 1: Implementar el crash-path (C2) junto al closure.** Para que `agent_active`/`skipped_cells`
  sean accesibles desde `_run`, declararlos en el scope del route (antes de `_run`/`on_progress`). En el
  `except` de `_run`, antes del `broadcast({"type":"scan_complete",...})` de crash:
  `if agent_active["on"]: mgr.agent_leave(session_id)` + un `broadcast` del snapshot `presence`. (Mismo
  `try/except RuntimeError` que el resto del crash-path.)
- [ ] **Step 2: Test de integración** `tests/integration/test_scanner_lock_skip.py` (sin mockear DB;
  patrón de `test_presence_two_participants.py`). Como lanzar un OCR real es pesado, **testear el closure
  `on_progress` directamente** con eventos sintéticos: para hacerlo testeable, **extraer el cuerpo del
  closure a una función módulo-nivel** `_handle_scan_progress(mgr, session_id, event, ctx, emit)` donde
  `ctx` lleva `skipped_cells`/`skipped_set`/`agent_active` y `emit` es el sink de broadcast (en prod =
  `_safe_broadcast`; en test = una lista que captura). Construir un `mgr` real (tmp DB), marcar a un
  humano editor de `HRB|odi` (`presence_heartbeat`+`presence_focus`), alimentar la secuencia
  (`cell_scanning`→`file_result`→`cell_done` de `HRB|odi`; `cell_scanning`→…→`cell_done` de `HRB|art`
  libre; luego `scan_complete`) y afirmar: `HRB|odi` → un `cell_skipped` capturado, su conteo NO cambia,
  sus `file_result`/`cell_done` no se aplican ni difunden; `HRB|art` → aplicada + `cell_updated` normal;
  el `scan_complete` final lleva `skipped=[{"hospital":"HRB","sigla":"odi"}]` y se difundió un `presence`
  sin claude (agent_leave). 
- [ ] **Step 3: Test de inertness (sin presencia).** Misma maquinaria, sin ningún participante: la
  secuencia completa para 2 celdas libres → CERO `cell_skipped`, ambas aplicadas, `scan_complete.skipped == []`.
  (Garantiza que el escáner sin colaboradores se comporta idéntico a hoy.)
- [ ] **Step 4:** Correr, ver verde.
- [ ] **Step 5: Commit** — `feat(multiplayer): OCR scanner claims cells as Claude + skips human-edited cells (M3b)`

### Task 6: Pase 1 (nombres) — chequea-y-salta

**Files:** Modify `api/routes/sessions.py` (ruta `scan`); Test `tests/integration/test_scanner_lock_skip.py`

En la ruta `scan` (~L386), el bucle `for (hosp, sigla), r in results.items()` que llama
`apply_cell_result` (~L405-406): antes de aplicar cada celda, consultar
`holder = mgr.presence_lock_holder(session_id, f"{hosp}|{sigla}", exclude=AGENT_PARTICIPANT_ID)`; si
`holder is not None` → **saltar** (no llamar `apply_cell_result`), acumular `{hospital,sigla}` en una
lista `skipped` y emitir `cell_skipped` (`_emit(request, session_id, {...})`). Tras el bucle, incluir
`skipped` en el dict de respuesta JSON (junto a lo que ya devuelve) y mantener el `session_refresh`
broadcast existente. Pase 1 **no** reclama el badge de claude (decisión 5).

- [ ] **Step 1: Test** (TestClient, real): marcar a un humano como editor de una celda, lanzar
  `POST /scan`, afirmar que esa celda quedó en `response.json()["skipped"]` y que su conteo no cambió,
  mientras otra celda sí se escaneó.
- [ ] **Step 2:** Correr, ver verde; `ruff check api/ tests/`.
- [ ] **Step 3: Commit** — `feat(multiplayer): pase-1 filename scan skips cells under live edit (M3b)`

> **Chunk 3 review:** plan-document-reviewer + `pytest tests/ -q` + `ruff check .`. Verificar que el
> escáner sin presencia activa (caso normal, nadie editando) se comporta **idéntico a hoy** (ningún
> skip, `scan_complete.skipped=[]`).

---

## Chunk 4: Frontend — resumen de saltadas + badge de agente

### Task 7: Manejo de `cell_skipped` + `scan_complete.skipped` en el store

**Files:** Modify `frontend/src/store/session.js`; Test `frontend/src/store/session.skip.test.js`

- [ ] **Step 1: Tests** (jsdom, patrón de los tests del store): un evento `cell_skipped` no rompe el
  estado (no toca la celda) y, opcionalmente, acumula en `scanProgress.skipped`; un `scan_complete` con
  `skipped:[{hospital,sigla},...]` deja `scanProgress.skipped` poblado y `terminal:"complete"` **sin**
  auto-dismiss cuando `skipped.length>0`.
- [ ] **Step 2:** En `_handleWSEvent`, añadir el caso `cell_skipped` (registrar en
  `scanProgress.skipped` o un set efímero; no mutar `session.cells`) y extender el caso `scan_complete`
  para copiar `event.skipped ?? []` a `scanProgress.skipped`; cuando haya saltos, **no** programar el
  auto-dismiss de 5 s (queda hasta que el usuario lo cierre o re-escanee).
- [ ] **Step 3:** Correr `npx vitest run src/store/session.skip.test.js` → verde.
- [ ] **Step 4: Commit** — `feat(multiplayer): store handles cell_skipped + scan_complete.skipped (M3b)`

### Task 8: Resumen en ScanProgress + re-escanear saltadas

**Files:** Modify `frontend/src/components/ScanProgress.jsx` (+ store action si hace falta)

- [ ] **Step 1:** Cuando `scanProgress.terminal === "complete"` y `scanProgress.skipped?.length > 0`,
  renderizar el resumen (po-* tokens, tono ámbar/suspect): "Completado · N saltadas (en edición)" + la
  lista de celdas `{hospital} · {sigla}` + un botón **"Re-escanear saltadas"** que llama a la acción de
  escaneo OCR (`scanOcr(sessionId, skipped.map(c => [c.hospital, c.sigla]))`) y un botón de cerrar.
  Reusar `Button`/tokens existentes; no auto-ocultar mientras haya saltadas.
- [ ] **Step 2:** `npm run build`; razonar el caso sin saltos (comportamiento idéntico a hoy:
  `skipped` vacío → resumen no aparece → auto-dismiss normal).
- [ ] **Step 3: Commit** — `feat(multiplayer): ScanProgress shows skipped cells + re-scan action (M3b)`

### Task 9: Badge distinto para el agente

**Files:** Modify `frontend/src/components/PresenceBadge.jsx` (+ `lib` espejo de identidad si hace falta)

- [ ] **Step 1:** Cuando `participant.kind === "agent"`, renderizar un icono `Bot` (lucide-react)
  centrado en vez de las iniciales, manteniendo el color del participante (el `AGENT_COLOR` del backend
  llega en el snapshot de presencia, así que el badge usa `participant.color` igual que hoy — no
  hardcodear). Tooltip = `participant.name` ("Claude"). Tamaños `sm`/`md` como hoy.
- [ ] **Step 2:** Verificar que el roster (PresenceRoster) y el badge por celda (CategoryRow) muestran
  el icono de bot para Claude y las iniciales para humanos. `npm run build` + `npx vitest run`
  (las pruebas existentes de presencia deben seguir verdes; la lógica pura `initials` no cambia).
- [ ] **Step 3: Commit** — `feat(multiplayer): distinct Bot avatar for the Claude agent (M3b)`

> **Chunk 4 review:** plan-document-reviewer + `npx vitest run` + `npm run build` + `ruff check .`. Luego la review holística cross-chunk.

---

## Final verification (antes de declarar done)

- [ ] `pytest -m "not slow" -q` (incl. eval/tests) — verde; full `pytest -q` si da el tiempo.
- [ ] `npx vitest run` — verde incl. los tests nuevos de skip.
- [ ] `npm run build` — OK; reconstruir `frontend/dist`.
- [ ] `ruff check .` — 0.
- [ ] **Regresión sin presencia (requisito duro):** sin un segundo participante, el escáner NO salta
  nada (`scan_complete.skipped=[]`), las escrituras humanas se comportan igual que M3a, y el badge de
  Claude solo aparece cuando el escáner/Claude está activo. Ningún test existente cambia.
- [ ] **Smoke en vivo (data-safe, patrón M3a):** correr aislado en una **copia** de la DB
  (`cp data/overseer.db data/_smoke.db`, 2º server `OVERSEER_DB_PATH=…/_smoke.db PORT=8010`, Brave debug
  `--remote-debugging-port=9222 --user-data-dir=<temp>` con `initScript` que reescribe `:8000→:8010`),
  dos contextos aislados:
  1. **Escáner salta:** Carla abre/edita `HRB|odi` (editor). En otro contexto, lanzar "Escanear
     pendientes/todos". Verificar: el badge de **Claude** (icono bot) salta por las celdas que escanea;
     `HRB|odi` aparece en el resumen "N saltadas"; su conteo NO cambió; el botón "Re-escanear saltadas"
     re-escanea solo esa cuando Carla la suelta.
  2. **Claude edita como participante:** vía API con `participant_id="claude"`, hacer un override a una
     celda libre → 200, el badge de Claude aparece en esa celda y Carla la ve en **solo-lectura** con
     "Claude está editando esta celda"; un override de Claude a una celda que Carla tiene → **409**.
  - Teardown: parar tasks, borrar `_smoke.db*`, verificar `overseer.db` real sha256 sin cambios.

## Out of scope (futuro)
- **Versión por-escritura totalmente atómica del skip del escáner** (cerrar la micro-carrera de la
  decisión 4 con `max_workers>1`): se difiere; el modelo por-celda-al-inicio cubre el caso dominante.
- **OCR de un solo archivo** (`.../files/{filename}/scan-ocr`) respetando locks: se inicia desde el
  visor de quien trabaja la celda (ya la tiene), colisión improbable; follow-up menor si hace falta.
- **Endpoint de "ceder/prestar lock":** explícitamente NO se construye (§8). El borde "el usuario tiene
  abierta la celda que le pediste a Claude" se resuelve conversacionalmente (Claude recibe 409 y avisa).
