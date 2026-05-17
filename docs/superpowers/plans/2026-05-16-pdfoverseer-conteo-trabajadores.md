# Conteo asistido de trabajadores — Plan de implementación

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir un visor donde una persona recorre los PDFs de una celda charla/chintegral y registra, por página, cuántos trabajadores firmaron (por voz o teclado); el total cae en cascada al Excel mensual.

**Architecture:** Las marcas `(archivo, página, número)` se guardan como campos nuevos del blob JSON de sesión y se autosalvan con debounce. Un visor pdf.js (reemplaza el `<iframe>` del PDFLightbox) recorre todos los PDFs de la celda como un flujo continuo de PgDn. Al exportar, el total por celda se emite como clave de rango con nombre `{HOSP}_workers_{purpose}` y el escritor genérico de Excel lo coloca; las fórmulas de HH se autocalculan.

**Tech Stack:** Python 3.10+ / FastAPI / openpyxl (backend); React + Vite + Zustand / pdfjs-dist / Web Speech API / vitest (frontend).

**Spec:** `docs/superpowers/specs/2026-05-16-conteo-trabajadores-design.md`
**Rama:** `po_overhaul`

---

## Estructura de archivos

Vista completa de lo que el plan crea o modifica. Los Chunks 2–4 (frontend) se detallan al redactarse; aquí se fija la decomposición.

### Backend

| Archivo | Estado | Responsabilidad |
|---|---|---|
| `api/state.py` | modificar | `compute_worker_count` (función de módulo) y `apply_worker_count` (método de `SessionManager`) |
| `api/routes/sessions.py` | modificar | endpoint `PATCH .../worker-count` |
| `api/routes/output.py` | modificar | `_build_worker_values` (cascada) y `_build_worker_warnings` (aviso de completitud) |
| `data/templates/build_template_v1.py` | modificar | corrige `H14`, vacía las 8 celdas de trabajadores, extiende `verify()` |
| `data/templates/RESUMEN_template_v1.xlsx` | regenerar | binario regenerado por el script |

### Frontend

| Archivo | Estado | Responsabilidad |
|---|---|---|
| `frontend/package.json` | modificar | añade `pdfjs-dist` y `vitest` |
| `frontend/vite.config.js` | modificar | bloque `test` para vitest |
| `frontend/src/lib/spanish-numbers.js` | crear | parser de números dictados en español |
| `frontend/src/hooks/usePdfDocument.js` | crear | carga un PDF con pdf.js, expone sus páginas |
| `frontend/src/hooks/useSpeechNumber.js` | crear | envuelve `SpeechRecognition`; aísla la voz |
| `frontend/src/components/PdfPage.jsx` | crear | renderiza una página PDF a `<canvas>` |
| `frontend/src/components/WorkerCountViewer.jsx` | crear | el visor en modo `count_workers` |
| `frontend/src/components/WorkerHud.jsx` | crear | panel lateral: total, archivo, marcas, micrófono |
| `frontend/src/components/WorkerBubble.jsx` | crear | la burbuja flotante (vacía/pendiente/fijada) |
| `frontend/src/components/PDFLightbox.jsx` | modificar | pdf.js reemplaza el `<iframe>`; soporta `mode` |
| `frontend/src/store/session.js` | modificar | `mode` en `lightbox`, estado/acciones de marcas, autosave de worker-count |
| `frontend/src/lib/api.js` | modificar | `patchWorkerCount` y helpers de la sesión de conteo |
| `frontend/src/components/DetailPanel.jsx` | modificar | módulo "Contar trabajadores" en celdas charla/chintegral |

### Tests

| Archivo | Estado | Responsabilidad |
|---|---|---|
| `tests/unit/api/test_state.py` | modificar | tests de `compute_worker_count` y `apply_worker_count` |
| `tests/unit/api/test_routes_sessions.py` | modificar | test del endpoint `PATCH .../worker-count` |
| `tests/unit/api/test_routes_output.py` | modificar | test de la cascada y del aviso de completitud |
| `tests/unit/excel/test_template_formulas.py` | crear | verifica las fórmulas de HH y las celdas vacías |
| `frontend/src/lib/spanish-numbers.cases.json` | crear | casos del parser (fixture vitest, colocado) |
| `frontend/src/lib/spanish-numbers.test.js` | crear | test vitest del parser |

### Convención de rutas

El spec escribe las rutas sin el prefijo `/api`; los routers reales lo llevan. Las rutas concretas de este plan son `/api/sessions/...`.

---

## Pre-requisito: Spike de validación de voz

> **Esto es un spike, no una tarea TDD.** Es una investigación con un punto de decisión. Conviene hacerlo antes de construir la capa de voz (Chunk 4). No bloquea los Chunks 1–3 (backend, visor, conteo por teclado), que funcionan sin voz.

### Spike S1: ¿Funciona el Web Speech API en el navegador objetivo?

**Objetivo:** confirmar que `SpeechRecognition` reconoce números dictados en español en Brave (el navegador donde se usa la app), antes de invertir en la capa de voz.

- [ ] **Paso 1: Crear una página de prueba mínima**

Guardar este HTML como archivo temporal (p. ej. `C:\Users\Daniel\AppData\Local\Temp\voz-spike.html`):

```html
<!doctype html><meta charset="utf-8">
<button id="go">Escuchar</button><pre id="out"></pre>
<script>
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
document.getElementById('go').onclick = () => {
  if (!SR) { out.textContent = 'NO DISPONIBLE'; return; }
  const r = new SR();
  r.lang = 'es-CL'; r.continuous = true; r.interimResults = true;
  r.onresult = e => { out.textContent = [...e.results].map(x => x[0].transcript).join('\n'); };
  r.onerror = e => { out.textContent += '\nERROR: ' + e.error; };
  r.start();
};
</script>
```

- [ ] **Paso 2: Probar en Brave**

Abrir el HTML en Brave (`file:///...`), pulsar "Escuchar", conceder permiso de micrófono y dictar varios números en español: "doce", "veintitrés", "cuarenta y uno", "ciento cinco". Anotar qué transcribe cada uno.

- [ ] **Paso 3: Decisión**

- Reconoce los números de forma fiable → seguir el plan tal cual; la capa de voz del Chunk 4 usa `SpeechRecognition`.
- `ERROR: network` / `not-allowed` persistente, o `NO DISPONIBLE` → registrar el hallazgo. Plan B: (a) usar Chrome para el conteo, o (b) sustituir el motor del hook `useSpeechNumber` por una STT en la nube. **El hook de voz aísla esta decisión** — el resto del plan no cambia, y el conteo por teclado (Chunk 3) funciona sin voz pase lo que pase.

No hay commit — el HTML de prueba es desechable.

---

## Chunk 1: Backend — datos, persistencia, cascada y corrección del template

Construye toda la mitad de backend: el modelo de datos de marcas sobre el blob de sesión, el endpoint para autosalvarlas, la emisión al Excel y la corrección del template. Al terminar el chunk, el backend acepta y persiste conteos de trabajadores y los exporta, aunque todavía no exista UI.

### Task 1: `compute_worker_count` — total derivado de una celda

**Files:**
- Modify: `api/state.py` (añadir función de módulo tras `compute_cell_count`, ~línea 36)
- Test: `tests/unit/api/test_state.py`

- [ ] **Step 1: Write the failing test**

Añadir a `tests/unit/api/test_state.py`. Incluir `compute_worker_count` en el import existente `from api.state import ...`.

```python
def test_compute_worker_count_sums_marks_across_files():
    cell = {
        "per_file": {"a.pdf": 1, "b.pdf": 1},
        "worker_marks": {
            "a.pdf": [{"page": 1, "count": 12}, {"page": 2, "count": 8}],
            "b.pdf": [{"page": 1, "count": 20}],
        },
    }
    assert compute_worker_count(cell) == 40


def test_compute_worker_count_ignores_orphan_files():
    cell = {
        "per_file": {"a.pdf": 1},
        "worker_marks": {
            "a.pdf": [{"page": 1, "count": 12}],
            "renamed_old.pdf": [{"page": 1, "count": 99}],
        },
    }
    assert compute_worker_count(cell) == 12


def test_compute_worker_count_zero_when_no_marks():
    assert compute_worker_count({"per_file": {"a.pdf": 1}}) == 0
    assert compute_worker_count({}) == 0


def test_compute_worker_count_tolerates_malformed_marks():
    # worker_marks viene de un blob JSON sin tipado; debe tolerar basura.
    cell = {
        "per_file": {"a.pdf": 1},
        "worker_marks": {"a.pdf": [{"page": 1, "count": 7}, {"page": 2}, None]},
    }
    assert compute_worker_count(cell) == 7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/api/test_state.py -k worker_count -v`
Expected: FAIL con `ImportError` / `cannot import name 'compute_worker_count'`.

- [ ] **Step 3: Write the implementation**

Añadir a `api/state.py` inmediatamente después de `compute_cell_count`:

```python
def compute_worker_count(cell: dict) -> int:
    """Total de trabajadores firmantes de una celda charla/chintegral.

    Suma los ``count`` de todas las marcas. Solo cuenta archivos presentes en
    ``per_file``: las marcas huérfanas de un PDF renombrado o eliminado se
    ignoran. Si ``per_file`` está vacío (celda sin escanear), no se filtra.

    Args:
        cell: el dict de estado de una celda.

    Returns:
        La suma de trabajadores firmantes; 0 si no hay marcas.
    """
    marks: dict = cell.get("worker_marks") or {}
    per_file: dict = cell.get("per_file") or {}
    total = 0
    for filename, page_marks in marks.items():
        if per_file and filename not in per_file:
            continue
        for mark in page_marks or []:
            if isinstance(mark, dict):
                total += mark.get("count") or 0
    return total
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/api/test_state.py -k worker_count -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add api/state.py tests/unit/api/test_state.py
git commit -m "feat(state): add compute_worker_count derived total"
```

### Task 2: `apply_worker_count` — persistir marcas en el blob

**Files:**
- Modify: `api/state.py` (método nuevo de `SessionManager`, tras `apply_per_file_override`, ~línea 234)
- Test: `tests/unit/api/test_state.py`

- [ ] **Step 1: Write the failing test**

Añadir a `tests/unit/api/test_state.py`. Usa el fixture `manager` ya existente en ese archivo (abre la sesión `2026-04`).

```python
def test_apply_worker_count_persists_all_fields(manager):
    manager.apply_worker_count(
        "2026-04", "HLL", "charla",
        marks={"a.pdf": [{"page": 1, "count": 12}]},
        status="en_progreso",
        cursor={"file": 0, "page": 1},
    )
    cell = manager.get_session_state("2026-04")["cells"]["HLL"]["charla"]
    assert cell["worker_marks"] == {"a.pdf": [{"page": 1, "count": 12}]}
    assert cell["worker_status"] == "en_progreso"
    assert cell["worker_cursor"] == {"file": 0, "page": 1}


def test_apply_worker_count_partial_patch_leaves_other_fields(manager):
    manager.apply_worker_count("2026-04", "HLL", "charla",
                               marks={"a.pdf": [{"page": 1, "count": 5}]})
    manager.apply_worker_count("2026-04", "HLL", "charla", status="terminado")
    cell = manager.get_session_state("2026-04")["cells"]["HLL"]["charla"]
    assert cell["worker_marks"] == {"a.pdf": [{"page": 1, "count": 5}]}
    assert cell["worker_status"] == "terminado"


def test_apply_worker_count_empty_marks_clears(manager):
    manager.apply_worker_count("2026-04", "HLL", "charla",
                               marks={"a.pdf": [{"page": 1, "count": 5}]})
    manager.apply_worker_count("2026-04", "HLL", "charla", marks={})
    cell = manager.get_session_state("2026-04")["cells"]["HLL"]["charla"]
    assert cell["worker_marks"] == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/api/test_state.py -k apply_worker_count -v`
Expected: FAIL con `AttributeError: 'SessionManager' object has no attribute 'apply_worker_count'`.

- [ ] **Step 3: Write the implementation**

Añadir a la clase `SessionManager` en `api/state.py`, después de `apply_per_file_override`. Sigue el patrón de `apply_user_override`: cargar el blob, `setdefault` la celda, mutar, persistir. **No agregar `commit()`** — `update_session_state` no commitea, y los `apply_*` existentes tampoco.

```python
    def apply_worker_count(
        self,
        session_id: str,
        hospital: str,
        sigla: str,
        *,
        marks: dict | None = None,
        status: str | None = None,
        cursor: dict | None = None,
    ) -> None:
        """Mezcla los campos de conteo de trabajadores en una celda.

        Patch parcial: cada argumento que no sea ``None`` se escribe; los que
        son ``None`` se dejan intactos. Para vaciar las marcas, pasar
        ``marks={}``. La celda se crea si no existe.

        Args:
            session_id: id de la sesión (``YYYY-MM``).
            hospital: sigla del hospital (HLL/HLU/HRB/HPV).
            sigla: la sigla de la celda (``charla`` o ``chintegral``).
            marks: dict ``{archivo: [{page, count}, ...]}``, o None.
            status: ``"en_progreso"`` | ``"terminado"``, o None.
            cursor: ``{file, page}`` con la última posición, o None.
        """
        state, _ = self._load_and_migrate(session_id)
        cell = (
            state.setdefault("cells", {})
            .setdefault(hospital, {})
            .setdefault(sigla, {})
        )
        if marks is not None:
            cell["worker_marks"] = marks
        if status is not None:
            cell["worker_status"] = status
        if cursor is not None:
            cell["worker_cursor"] = cursor
        update_session_state(self._conn, session_id, state_json=json.dumps(state))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/api/test_state.py -k apply_worker_count -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add api/state.py tests/unit/api/test_state.py
git commit -m "feat(state): add apply_worker_count partial-patch setter"
```

### Task 3: Endpoint `PATCH .../worker-count`

**Files:**
- Modify: `api/routes/sessions.py` (endpoint nuevo, junto a `patch_override`, ~línea 280)
- Test: `tests/unit/api/test_routes_sessions.py`

- [ ] **Step 1: Write the failing test**

Añadir a `tests/unit/api/test_routes_sessions.py` (usa el fixture `client` existente). Crear la sesión con `POST /api/sessions`; el endpoint crea la celda por sí mismo (`apply_worker_count` usa `setdefault`).

```python
def test_patch_worker_count_persists(client, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", "A:/informe mensual")
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    r = client.patch(
        "/api/sessions/2026-04/cells/HLL/charla/worker-count",
        json={"marks": {"a.pdf": [{"page": 1, "count": 12}]},
              "status": "en_progreso",
              "cursor": {"file": 0, "page": 1}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["worker_status"] == "en_progreso"
    assert body["worker_count"] == 12


def test_patch_worker_count_rejects_bad_status(client, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", "A:/informe mensual")
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    r = client.patch(
        "/api/sessions/2026-04/cells/HLL/charla/worker-count",
        json={"status": "no-es-valido"},
    )
    assert r.status_code == 422


def test_patch_worker_count_session_404(client):
    # Sin crear la sesión: apply_worker_count → KeyError → 404.
    r = client.patch(
        "/api/sessions/2026-04/cells/HLL/charla/worker-count",
        json={"status": "terminado"},
    )
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/api/test_routes_sessions.py -k worker_count -v`
Expected: FAIL con `404` (la ruta no existe todavía).

- [ ] **Step 3: Write the implementation**

Añadir a `api/routes/sessions.py`. Definir un modelo Pydantic para el body — precedente en el mismo archivo: `PerFileOverrideRequest(BaseModel)`. El modelo da el `422` automático si `status` no es válido. Reproducir la validación de `session_id` (`_SESSION_ID_RE`) como en `patch_override`, y extender el import de `api.state`: `from api.state import SessionManager, compute_cell_count` → `from api.state import SessionManager, compute_cell_count, compute_worker_count`. Colocar `WorkerCountPatch` junto a `PerFileOverrideRequest`.

```python
class WorkerCountPatch(BaseModel):
    """Body del PATCH worker-count. Patch parcial: los campos None no se tocan."""

    marks: dict | None = None
    status: Literal["en_progreso", "terminado"] | None = None
    cursor: dict | None = None


@router.patch("/sessions/{session_id}/cells/{hospital}/{sigla}/worker-count")
def patch_worker_count(
    session_id: str,
    hospital: str,
    sigla: str,
    body: WorkerCountPatch,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Autosalva el conteo de trabajadores de una celda (patch parcial)."""
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(status_code=422, detail="session_id inválido")
    try:
        mgr.apply_worker_count(
            session_id, hospital, sigla,
            marks=body.marks, status=body.status, cursor=body.cursor,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Sesión {session_id} no encontrada") from exc
    state = mgr.get_session_state(session_id)
    cell = state["cells"].get(hospital, {}).get(sigla, {})
    return {
        "worker_marks": cell.get("worker_marks"),
        "worker_status": cell.get("worker_status"),
        "worker_cursor": cell.get("worker_cursor"),
        "worker_count": compute_worker_count(cell),
    }
```

`Literal` necesita `from typing import Literal`; `BaseModel` ya se importa para `PerFileOverrideRequest`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/api/test_routes_sessions.py -k worker_count -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add api/routes/sessions.py tests/unit/api/test_routes_sessions.py
git commit -m "feat(api): add PATCH worker-count endpoint"
```

### Task 4: Cascada al Excel — `_build_worker_values`

**Files:**
- Modify: `api/routes/output.py` (función nueva + enganche en el handler `POST .../output`)
- Test: `tests/unit/api/test_routes_output.py`

- [ ] **Step 1: Write the failing test**

Añadir a `tests/unit/api/test_routes_output.py`. Inyecta marcas con el manager (sin escanear: `compute_worker_count` sin `per_file` suma todas las marcas) y verifica el rango con nombre del Excel.

```python
def test_output_emits_worker_totals(client, tmp_path):
    import openpyxl

    client.post("/api/sessions", json={"year": 2026, "month": 4})
    mgr = client.app.dependency_overrides[get_manager]()
    mgr.apply_worker_count(
        "2026-04", "HLL", "charla",
        marks={"c1.pdf": [{"page": 1, "count": 18}, {"page": 2, "count": 22}]},
        status="terminado",
    )
    out = client.post("/api/sessions/2026-04/output", json={}).json()
    wb = openpyxl.load_workbook(out["output_path"])
    sheet, coord = list(wb.defined_names["HLL_workers_chgen"].destinations)[0]
    assert wb[sheet][coord].value == 40
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/api/test_routes_output.py -k worker_totals -v`
Expected: FAIL — la celda del rango `HLL_workers_chgen` está vacía (`None != 40`).

- [ ] **Step 3: Write the implementation**

Extender el import de `api.state` a nivel de módulo en `output.py`: `from api.state import SessionManager` → `from api.state import SessionManager, compute_worker_count`. Luego añadir la función `_build_worker_values` (junto a `_build_cell_values`):

```python
# Sigla del sistema → "purpose" del rango de trabajadores en el Excel.
# El template usa "chgen" para charlas generales, no "charla".
WORKER_PURPOSE: dict[str, str] = {"charla": "chgen", "chintegral": "chintegral"}


def _build_worker_values(state: dict) -> dict[str, int]:
    """Emite ``{HOSP}_workers_{purpose}`` para las celdas charla/chintegral
    que tengan datos de conteo de trabajadores."""
    out: dict[str, int] = {}
    for hosp, sigla_map in state.get("cells", {}).items():
        for sigla, purpose in WORKER_PURPOSE.items():
            cell = sigla_map.get(sigla)
            if not cell:
                continue
            if "worker_marks" not in cell and "worker_status" not in cell:
                continue  # nunca se contó — no emitir; el template queda en blanco
            out[f"{hosp}_workers_{purpose}"] = compute_worker_count(cell)
    return out
```

En el handler de `POST .../output` (`output.py:62-117`), `cell_values` se construye con `_build_cell_values(state)` (~línea 74); justo después de esa línea y antes de llamar a `generate_resumen`, mezclar los valores de trabajadores:

```python
    cell_values.update(_build_worker_values(state))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/api/test_routes_output.py -k worker_totals -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/routes/output.py tests/unit/api/test_routes_output.py
git commit -m "feat(output): cascade worker totals to Excel named ranges"
```

### Task 5: Aviso de completitud — `_build_worker_warnings`

**Files:**
- Modify: `api/routes/output.py` (función nueva + campo en la respuesta)
- Test: `tests/unit/api/test_routes_output.py`

> **Nota de diseño:** la regla única del spec §7.3 es "una celda entra en `worker_warnings` si su `worker_status` no es `terminado` o algún PDF no abrió". El frontend (Chunk 3/4) bloquea el botón "Terminé" cuando un PDF no cargó, así que una celda con un PDF fallido nunca alcanza `terminado`. Por eso el backend solo necesita comprobar `worker_status != "terminado"` — el segundo disyuntor queda cubierto por el primero. Solo se considera una celda que tenga PDFs (`per_file` no vacío): una celda charla sin PDFs no tiene nada que contar.
>
> `_build_worker_values` (Task 4) y `_build_worker_warnings` (Task 5) usan **a propósito** predicados distintos — emitir un total y avisar de incompletitud son preguntas diferentes. Task 4 emite si la celda tiene datos de conteo (`worker_marks`/`worker_status`); Task 5 avisa si la celda tiene PDFs y no está `terminado`. Una celda con PDFs nunca contada: Task 4 no emite (el template queda en blanco) y Task 5 sí avisa — ambos correctos por el spec §7.3/§8.1. No unificar los dos predicados.

- [ ] **Step 1: Write the failing test**

`_build_worker_warnings` solo considera celdas con `per_file` no vacío, así que el `ScanResult` inyectado **debe** traer `per_file` poblado — el `_filename_result` de `test_state.py` deja `per_file=None` y no sirve. Definir este helper en `tests/unit/api/test_routes_output.py`, a nivel de módulo, después del bloque de imports:

```python
def _scan_result(per_file: dict):
    """ScanResult de filename_glob con per_file poblado."""
    from core.scanners.base import ConfidenceLevel, ScanResult

    return ScanResult(
        count=sum(per_file.values()),
        confidence=ConfidenceLevel.HIGH,
        method="filename_glob",
        breakdown={},
        flags=[],
        errors=[],
        files_scanned=len(per_file),
        duration_ms=10,
        per_file=per_file,
    )
```

Y los dos tests:

```python
def test_worker_warnings_flag_incomplete_cell(client, tmp_path):
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    mgr = client.app.dependency_overrides[get_manager]()
    mgr.apply_filename_result(
        "2026-04", "HLL", "charla", _scan_result({"c1.pdf": 3})
    )
    # per_file poblado, sin worker_status → celda incompleta
    out = client.post("/api/sessions/2026-04/output", json={}).json()
    warned = {(w["hospital"], w["sigla"]) for w in out["worker_warnings"]}
    assert ("HLL", "charla") in warned


def test_worker_warnings_silent_when_terminado(client, tmp_path):
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    mgr = client.app.dependency_overrides[get_manager]()
    mgr.apply_filename_result(
        "2026-04", "HLL", "charla", _scan_result({"c1.pdf": 3})
    )
    mgr.apply_worker_count("2026-04", "HLL", "charla", status="terminado")
    out = client.post("/api/sessions/2026-04/output", json={}).json()
    warned = {(w["hospital"], w["sigla"]) for w in out["worker_warnings"]}
    assert ("HLL", "charla") not in warned
```

`apply_filename_result` (`api/state.py:111`) escribe `cell["per_file"]`; es la vía
para que la celda tenga PDFs sin correr un escaneo real. `get_manager` ya se importa
en `test_routes_output.py`. Los dos nombres comparten el prefijo `worker_warnings_`
para que un único `-k worker_warnings` capture ambos.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/api/test_routes_output.py -k worker_warnings -v`
Expected: FAIL con `KeyError: 'worker_warnings'` — la respuesta de `/output` todavía
no trae ese campo.

- [ ] **Step 3: Write the implementation**

Añadir `_build_worker_warnings` a `output.py`, junto a `_build_worker_values`
(Task 4). Reutiliza el `WORKER_PURPOSE` que ya definió la Task 4 — no redefinirlo.

```python
def _build_worker_warnings(state: dict) -> list[dict]:
    """Celdas charla/chintegral con conteo de trabajadores incompleto.

    Una celda avisa si tiene PDFs (``per_file`` no vacío) y su ``worker_status``
    no es ``"terminado"`` — la regla única del spec §7.3. El frontend bloquea
    "Terminé esta categoría" cuando un PDF no abre, así que el disyuntor "algún
    PDF falló" queda cubierto por este mismo predicado.

    Args:
        state: el blob de estado de la sesión.

    Returns:
        Lista de ``{"hospital", "sigla"}``; vacía si nada está incompleto.
    """
    out: list[dict] = []
    for hosp, sigla_map in state.get("cells", {}).items():
        for sigla in WORKER_PURPOSE:
            cell = sigla_map.get(sigla)
            if not cell or not cell.get("per_file"):
                continue
            if cell.get("worker_status") != "terminado":
                out.append({"hospital": hosp, "sigla": sigla})
    return out
```

En el handler de `POST .../output`, añadir `worker_warnings` al dict de respuesta
(`output.py:112-117`):

```python
    return {
        "output_path": str(result.output_path),
        "cells_written": result.cells_written,
        "warnings": result.warnings,
        "worker_warnings": _build_worker_warnings(state),
        "duration_ms": result.duration_ms,
    }
```

`worker_warnings` es un campo **nuevo y distinto** de `warnings` (spec §7.3):
`warnings` son diagnósticos del escritor de Excel; `worker_warnings` es el aviso de
completitud para el usuario. No se mezclan.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/api/test_routes_output.py -k worker_warnings -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add api/routes/output.py tests/unit/api/test_routes_output.py
git commit -m "feat(output): add worker_warnings completeness field to output response"
```

### Task 6: Corrección del template — `build_template_v1.py`

**Files:**
- Modify: `data/templates/build_template_v1.py` (paso nuevo en `build()`, extensión de `verify()`)
- Regenerate: `data/templates/RESUMEN_template_v1.xlsx`
- Create: `tests/unit/excel/test_template_formulas.py`

> **Estado actual del template, verificado con openpyxl:** `H14 = "=H29*0.5"`
> (errada — apunta a la fila de chgen, 29, en vez de la de chintegral, 30);
> `J14/L14/N14 = "={col}30*0.5"` (correctas); `H13/J13/L13/N13 = "={col}29*0.25"`
> (correctas); `H29/H30` ya en blanco; `J29=479 L29=5255 N29=4851 J30=123 L30=373
> N30=784` (valores ABRIL obsoletos). El fix toca exactamente 7 celdas.

- [ ] **Step 1: Write the failing test**

Crear `tests/unit/excel/test_template_formulas.py`. Verifica el template ya
commiteado vía `DEFAULT_TEMPLATE` (la misma referencia que usa `test_template.py`);
la prueba falla hasta que el Step 4 regenere el binario.

```python
"""El template debe traer las fórmulas de HH correctas y las celdas de
trabajadores en blanco (spec §8.2)."""

import openpyxl
import pytest

from core.excel.template import DEFAULT_TEMPLATE

HH_COLS = ("H", "J", "L", "N")


@pytest.fixture(scope="module")
def ws():
    # data_only=False (por defecto) → las fórmulas se leen como texto
    return openpyxl.load_workbook(DEFAULT_TEMPLATE).active


@pytest.mark.parametrize("col", HH_COLS)
def test_hh_chgen_formula_points_to_row_29(ws, col):
    assert ws[f"{col}13"].value == f"={col}29*0.25"


@pytest.mark.parametrize("col", HH_COLS)
def test_hh_chintegral_formula_points_to_row_30(ws, col):
    assert ws[f"{col}14"].value == f"={col}30*0.5"


@pytest.mark.parametrize("col", HH_COLS)
@pytest.mark.parametrize("row", (29, 30))
def test_worker_value_cells_ship_blank(ws, col, row):
    assert ws[f"{col}{row}"].value is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/excel/test_template_formulas.py -v`
Expected: FAIL — `test_hh_chintegral_formula_points_to_row_30[H]` (H14 es `=H29*0.5`)
y los seis `test_worker_value_cells_ship_blank` de J/L/N × 29/30 (valores ABRIL).

- [ ] **Step 3: Modificar `build()` y `verify()`**

En `build()`, después del bucle de rangos de trabajadores y **antes** de
`wb.save(DST)`, añadir el paso de corrección. `HH_COL` y `WORKFORCE_ROW` ya existen
en el módulo — reutilizarlos:

```python
    # Fix HH formula + blank stale workforce values (spec §8.2).
    # The sample's H14 points to row 29 (chgen); chintegral lives in row 30.
    ws["H14"] = "=H30*0.5"
    for hh_col in HH_COL.values():
        for row in WORKFORCE_ROW.values():
            ws[f"{hh_col}{row}"] = None
```

Extender `verify()` con dos comprobaciones nuevas, al final de la función:

```python
    # HH formulas: row 13 = chgen ×0.25, row 14 = chintegral ×0.5
    for col in HH_COL.values():
        if ws[f"{col}13"].value != f"={col}29*0.25":
            raise AssertionError(f"{col}13 HH formula wrong: {ws[f'{col}13'].value!r}")
        if ws[f"{col}14"].value != f"={col}30*0.5":
            raise AssertionError(f"{col}14 HH formula wrong: {ws[f'{col}14'].value!r}")

    # Workforce value cells must ship blank
    for col in HH_COL.values():
        for row in WORKFORCE_ROW.values():
            if ws[f"{col}{row}"].value is not None:
                raise AssertionError(f"Cell {col}{row} should be blank")
```

- [ ] **Step 4: Regenerar el template**

Run: `python data/templates/build_template_v1.py`
Expected: imprime `Built: ...RESUMEN_template_v1.xlsx` con 72 + 8 rangos; `verify()`
no lanza `AssertionError`.

- [ ] **Step 5: Diff de verificación**

Confirmar que la regeneración cambió **solo** las 7 celdas esperadas (spec §8.2/§12 —
mitiga el riesgo de revertir ediciones manuales del template). El "antes" se lee de
git, así que no hace falta copiar nada a mano. Ejecutar este snippet desde la raíz
del repo:

```python
import io, subprocess
import openpyxl

raw = subprocess.run(
    ["git", "show", "HEAD:data/templates/RESUMEN_template_v1.xlsx"],
    capture_output=True, check=True,
).stdout
before = openpyxl.load_workbook(io.BytesIO(raw)).active
after = openpyxl.load_workbook("data/templates/RESUMEN_template_v1.xlsx").active
diffs = [
    (c.coordinate, c.value, after[c.coordinate].value)
    for row in before.iter_rows() for c in row
    if after[c.coordinate].value != c.value
]
for coord, b, a in sorted(diffs):
    print(f"{coord}: {b!r} -> {a!r}")
print(f"total: {len(diffs)} celdas")
```

Expected: exactamente 7 celdas —
`H14: '=H29*0.5' -> '=H30*0.5'` y `J29 J30 L29 L30 N29 N30` (su valor `-> None`).
Si aparece cualquier otra celda, el template se editó a mano tras generarse:
investigar antes de continuar.

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/unit/excel/test_template_formulas.py -v`
Expected: PASS (16 tests — 4 + 4 + 8).

- [ ] **Step 7: Commit**

```bash
git add data/templates/build_template_v1.py data/templates/RESUMEN_template_v1.xlsx tests/unit/excel/test_template_formulas.py
git commit -m "fix(template): correct H14 HH formula and blank stale worker cells"
```

### Cierre del Chunk 1

Los seis tasks dejan el backend completo: acepta marcas de trabajadores, las
persiste en el blob de sesión, las exporta como rangos con nombre y avisa de celdas
incompletas; el template ya calcula bien el HH de charla integral. Antes de pasar al
Chunk 2:

- [ ] **Suite de backend completa**

Run: `pytest tests/unit/api/test_state.py tests/unit/api/test_routes_sessions.py tests/unit/api/test_routes_output.py tests/unit/excel/test_template_formulas.py -v`
Expected: PASS — ningún test saltado.

- [ ] **Lint**

Run: `ruff check .`
Expected: 0 violaciones.

---

## Chunk 2: Frontend — el visor pdf.js (modo `inspect`)

Este chunk reemplaza el `<iframe>` de `PDFLightbox` por un visor `pdfjs-dist` y deja el
modo `inspect` (el uso actual: clic en un archivo de `FileList`) con paridad de
comportamiento. El modo `count_workers` se construye sobre esta base en el Chunk 3.

> **Cómo se verifica este chunk.** Las cuatro tareas son de renderizado en el
> navegador. El proyecto **no tiene runner de tests JS** — vitest se agrega en el
> Chunk 4, y solo para el parser de números. Siguiendo el spec §11, el visor se
> verifica con `npm run build` (Vite resuelve imports y compila el JSX) en cada tarea
> y con un **smoke vía chrome-devtools** al cerrar el chunk. Estas tareas **no** tienen
> el paso "test que falla primero": no es código de lógica pura y no hay con qué
> testearlas por unidad. Es una desviación deliberada del TDD, acotada al frontend de
> render y respaldada por el spec.

### Task 7: Instalar `pdfjs-dist` y configurar el worker

**Files:**
- Modify: `frontend/package.json` (+ `package-lock.json`, vía `npm install`)
- Create: `frontend/src/lib/pdf.js`

- [ ] **Step 1: Instalar la dependencia**

Run (desde `frontend/`): `npm install pdfjs-dist`
Expected: `pdfjs-dist` queda en `dependencies` de `package.json`; `package-lock.json`
actualizado.

- [ ] **Step 2: Crear el punto de configuración de pdf.js**

`pdfjs-dist` necesita un *worker*: un archivo JS aparte que parsea el PDF fuera del
hilo principal. Se configura una sola vez, en un módulo del que todos importan.
Crear `frontend/src/lib/pdf.js`:

```js
// Configuración única de pdf.js. Importar `pdfjsLib` SIEMPRE desde aquí,
// nunca desde "pdfjs-dist" directo — así el workerSrc queda garantizado.
import * as pdfjsLib from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

export { pdfjsLib };
```

El sufijo `?url` es una función de Vite: importa la URL del asset como string. La
ruta `build/pdf.worker.min.mjs` es la de pdfjs-dist v4+. Si `npm install` trajo v3,
el worker es `build/pdf.worker.min.js` (sin `.m`); el Step 3 lo detecta.

- [ ] **Step 3: Verificar que la compilación resuelve el worker**

Run (desde `frontend/`): `npm run build`
Expected: el build de Vite termina sin errores. Si falla con "Failed to resolve
import 'pdfjs-dist/build/pdf.worker.min.mjs'", ajustar la extensión en `pdf.js` a la
que traiga la versión instalada (mirar `frontend/node_modules/pdfjs-dist/build/`).

- [ ] **Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/lib/pdf.js
git commit -m "build(frontend): add pdfjs-dist with worker config"
```

### Task 8: Hook `usePdfDocument`

**Files:**
- Create: `frontend/src/hooks/usePdfDocument.js`

Carga un PDF desde una URL con pdf.js y expone el documento, el número de páginas y
los estados de carga/error. Una sola responsabilidad: la vida del `PDFDocumentProxy`.

- [ ] **Step 1: Crear el hook**

```js
import { useEffect, useState } from "react";

import { pdfjsLib } from "../lib/pdf";

/**
 * Carga un PDF con pdf.js.
 * @param {string|null} url - URL del PDF, o null/"" para no cargar nada.
 * @returns {{doc: object|null, numPages: number, error: Error|null, loading: boolean}}
 */
export function usePdfDocument(url) {
  const [doc, setDoc] = useState(null);
  const [numPages, setNumPages] = useState(0);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!url) return undefined;
    let cancelled = false;
    setDoc(null);
    setError(null);
    setNumPages(0);

    const task = pdfjsLib.getDocument(url);
    task.promise.then(
      (pdf) => {
        if (cancelled) {
          pdf.destroy();
          return;
        }
        setDoc(pdf);
        setNumPages(pdf.numPages);
      },
      (err) => {
        if (!cancelled) setError(err);
      },
    );

    return () => {
      cancelled = true;
      task.destroy();
    };
  }, [url]);

  return { doc, numPages, error, loading: Boolean(url) && !doc && !error };
}
```

`getDocument(url)` devuelve un `PDFDocumentLoadingTask`; su `.promise` resuelve al
`PDFDocumentProxy`. Al cambiar la URL o desmontar, `task.destroy()` aborta la carga;
si el PDF ya había resuelto cuando se canceló, `pdf.destroy()` libera su memoria.

- [ ] **Step 2: Verificar la compilación**

Run (desde `frontend/`): `npm run build`
Expected: build sin errores. El comportamiento del hook se verifica en el smoke del
cierre del chunk — no hay runner de tests JS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/usePdfDocument.js
git commit -m "feat(frontend): add usePdfDocument hook"
```

### Task 9: Componente `PdfPage`

**Files:**
- Create: `frontend/src/components/PdfPage.jsx`

Renderiza **una** página de un documento pdf.js a un `<canvas>`. Recibe el `doc` (el
`PDFDocumentProxy` del hook) y el número de página.

- [ ] **Step 1: Crear el componente**

```jsx
import { useEffect, useRef } from "react";

/**
 * Renderiza una página de un PDF a un canvas.
 *
 * @param {object} props
 * @param {object} props.doc - PDFDocumentProxy de usePdfDocument.
 * @param {number} props.pageNumber - número de página, 1-indexado.
 * @param {number} [props.scale] - escala de render (1.5 por defecto).
 */
export function PdfPage({ doc, pageNumber, scale = 1.5 }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    if (!doc) return undefined;
    let cancelled = false;
    let renderTask = null;

    doc.getPage(pageNumber).then((page) => {
      if (cancelled) return;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const viewport = page.getViewport({ scale });
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      renderTask = page.render({
        canvasContext: canvas.getContext("2d"),
        viewport,
      });
      // Cancelar un render rechaza su promesa con RenderingCancelledException.
      renderTask.promise.catch(() => {});
    });

    return () => {
      cancelled = true;
      if (renderTask) renderTask.cancel();
    };
  }, [doc, pageNumber, scale]);

  return (
    <canvas
      ref={canvasRef}
      className="block max-w-full shadow-sm ring-1 ring-po-border"
    />
  );
}
```

`doc.getPage(n)` es 1-indexado. `page.render()` devuelve un `RenderTask`; renderizar
dos veces el mismo canvas en paralelo lanza error — por eso el cleanup llama
`renderTask.cancel()` antes de que un re-render arranque.

- [ ] **Step 2: Verificar la compilación**

Run (desde `frontend/`): `npm run build`
Expected: build sin errores.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/PdfPage.jsx
git commit -m "feat(frontend): add PdfPage canvas renderer"
```

### Task 10: `PDFLightbox` — pdf.js reemplaza el `<iframe>`

**Files:**
- Modify: `frontend/src/store/session.js` (campo `mode` en `lightbox`)
- Modify: `frontend/src/components/PDFLightbox.jsx`

- [ ] **Step 1: Añadir `mode` al estado `lightbox`**

En `frontend/src/store/session.js`, `openLightbox` (~línea 247) gana un cuarto
parámetro `mode` con valor por defecto `"inspect"`:

```js
  openLightbox: (hospital, sigla, fileIndex = 0, mode = "inspect") =>
    set({ lightbox: { hospital, sigla, fileIndex, mode } }),
```

Los llamadores existentes (clic en `FileList`) pasan 2-3 argumentos, así que `mode`
cae a `"inspect"` — sin cambios para ellos. El spec §4.2 reserva además
`count_workers` (Chunk 3) y `boundaries` (feature 2, fuera de alcance).

- [ ] **Step 2: Reemplazar el `<iframe>` por el visor pdf.js**

En `frontend/src/components/PDFLightbox.jsx`, añadir los imports del visor:

```jsx
import { TransformWrapper, TransformComponent } from "react-zoom-pan-pinch";

import { usePdfDocument } from "../hooks/usePdfDocument";
import { PdfPage } from "./PdfPage";
```

Añadir, a nivel de módulo (junto a `CountSummary`, que ya vive en este archivo), el
componente del modo `inspect` — desplazamiento (arrastre) y zoom (rueda/pinza) sobre
la columna de páginas, vía `react-zoom-pan-pinch`, tal como pide el spec §4.1:

```jsx
function InspectView({ url }) {
  const { doc, numPages, error, loading } = usePdfDocument(url);

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center text-sm text-po-text-muted">
        No se pudo abrir el PDF.
      </div>
    );
  }
  if (loading || !doc) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-po-text-muted">
        Cargando…
      </div>
    );
  }
  return (
    <TransformWrapper minScale={0.5} maxScale={4} doubleClick={{ disabled: true }}>
      <TransformComponent
        wrapperClass="!w-full !h-full"
        contentClass="flex flex-col items-center gap-3 p-4"
      >
        {Array.from({ length: numPages }, (_, i) => (
          <PdfPage key={i + 1} doc={doc} pageNumber={i + 1} />
        ))}
      </TransformComponent>
    </TransformWrapper>
  );
}
```

Reemplazar el bloque del `<iframe>` dentro de `Dialog.Body` (hoy el primer `<div>`):

```jsx
      <div className="flex-1 bg-black">
        <iframe src={pdfUrl} className="w-full h-full border-0" title={filename} />
      </div>
```

por:

```jsx
      <div className="flex-1 overflow-hidden bg-black">
        <InspectView url={pdfUrl} />
      </div>
```

El `<aside>` con `CountSummary` + `OverridePanel` **no cambia**. El modo
`count_workers` se enchufa aquí en el Chunk 3 (un branch sobre `lightbox.mode`); en
este chunk `PDFLightbox` solo renderiza `inspect`. El `<iframe>` usaba `filename` solo
para su `title`, pero `filename` sigue en uso (`Dialog.Title`, cabecera): no queda
ninguna binding huérfana que limpiar.

- [ ] **Step 3: Verificar la compilación**

Run (desde `frontend/`): `npm run build`
Expected: build sin errores. `react-zoom-pan-pinch` ya está en `package.json`
(`^3.7.0`) — no hay que instalar nada.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/store/session.js frontend/src/components/PDFLightbox.jsx
git commit -m "refactor(frontend): replace PDFLightbox iframe with pdf.js viewer"
```

### Cierre del Chunk 2

Smoke del modo `inspect` — confirma la paridad con el `<iframe>` viejo. Conducir vía
chrome-devtools (Brave en modo debug; ver memoria `feedback_browser_testing_via_devtools`).

- [ ] **Arrancar la app**

Backend y frontend corriendo (`python server.py`; `npm run dev` desde `frontend/`).
Abrir el front en `http://localhost:5173` — el `allow_origins` del backend
(`api/main.py`) lista solo ese host; abrirlo como `127.0.0.1` rompería el `fetch` de
pdf.js por CORS.

- [ ] **Smoke del visor**

1. Abrir una sesión con PDFs escaneados; en una celda, abrir `FileList` y hacer clic
   en un archivo.
2. Confirmar que `PDFLightbox` abre y el PDF se renderiza con pdf.js (canvas, no
   `<iframe>`): las páginas se ven apiladas verticalmente.
3. Rueda del ratón sobre el PDF → zoom; arrastrar → desplaza la columna de páginas.
4. El `<aside>` derecho sigue mostrando `CountSummary` y `OverridePanel`.
5. Cerrar con la X → el foco vuelve al disparador (no reintroducir la regresión de
   foco de FASE 5).
6. Si el PDF no aparece y la consola muestra un error CORS o de worker, revisar
   primero el host del front (paso anterior) y la ruta del worker (Task 7 Step 3).

---

## Chunk 3: Frontend — modo `count_workers` (conteo por teclado)

Este chunk construye el modo de conteo: el visor recorre **todos** los PDFs de una
celda charla/chintegral como un flujo continuo de PgDn, una persona marca por página
cuántos trabajadores firmaron, y el total se autosalva. Toda la entrada es por
**teclado** — la voz se agrega aislada en el Chunk 4. Al terminar este chunk se puede
contar una celda de principio a fin desde la UI.

> **Cómo se verifica este chunk.** Igual que el Chunk 2: render de navegador, sin
> runner de tests JS. Cada tarea se verifica con `npm run build` (Vite compila) y el
> chunk cierra con un **smoke vía chrome-devtools** del flujo completo de conteo por
> teclado. Las dos piezas de lógica pura (`computeWorkerCount`, el parser de voz)
> tienen distinto trato: el spec §6.3 declara el total "una suma trivial" que no
> amerita test; el parser sí se testea con vitest (Chunk 4).

### Task 11: `api.js` — `patchWorkerCount`

**Files:**
- Modify: `frontend/src/lib/api.js`

- [ ] **Step 1: Añadir el cliente del endpoint**

En `frontend/src/lib/api.js`, añadir tras `patchPerFileOverride` (~línea 75). Espeja
ese helper: `PATCH` con body JSON, `signal` opcional, lanza con el texto del error.

```js
  patchWorkerCount: async (sessionId, hospital, sigla, patch, opts = {}) => {
    const r = await fetch(
      `${BASE}/sessions/${sessionId}/cells/${hospital}/${sigla}/worker-count`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
        signal: opts.signal,
      }
    );
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
```

`patch` es `{ marks?, status?, cursor? }` — el body que el endpoint del Chunk 1
(Task 3, `WorkerCountPatch`) acepta como patch parcial.

- [ ] **Step 2: Verificar la compilación**

Run (desde `frontend/`): `npm run build`
Expected: build sin errores.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api.js
git commit -m "feat(frontend): add patchWorkerCount API client"
```

### Task 12: Store — `saveWorkerCount` y `openWorkerCount`

**Files:**
- Modify: `frontend/src/store/session.js`

- [ ] **Step 1: Añadir el autosave `saveWorkerCount`**

En `frontend/src/store/session.js`, añadir esta acción tras `savePerFileOverride`
(~línea 245). Es un **espejo exacto** de `savePerFileOverride`: misma maquinaria de
`AbortController` / `_pendingSave` / `pendingSaves` / auto-flush a los 2 s. La clave
lleva el sufijo `|workers` para no colisionar con el autosave de override de la misma
celda.

```js
  saveWorkerCount: async (sessionId, hospital, sigla, patch) => {
    const key = `${hospital}|${sigla}|workers`;
    const controller = new AbortController();

    set((prev) => {
      const existing = prev._pendingSave.get(key);
      if (existing?.controller) existing.controller.abort();
      const nextPending = new Map(prev._pendingSave);
      nextPending.set(key, { controller });
      return {
        _pendingSave: nextPending,
        pendingSaves: { ...prev.pendingSaves, [key]: "saving" },
      };
    });

    try {
      const result = await api.patchWorkerCount(
        sessionId, hospital, sigla, patch, { signal: controller.signal },
      );
      if (controller.signal.aborted) return;

      set((prev) => {
        if (!prev.session) return {};
        const cells = { ...prev.session.cells };
        const hosp = { ...cells[hospital] };
        hosp[sigla] = {
          ...hosp[sigla],
          worker_marks: result.worker_marks,
          worker_status: result.worker_status,
          worker_cursor: result.worker_cursor,
        };
        cells[hospital] = hosp;
        const cleanedPending = new Map(prev._pendingSave);
        if (cleanedPending.get(key)?.controller === controller) {
          cleanedPending.delete(key);
        }
        return {
          session: { ...prev.session, cells },
          _pendingSave: cleanedPending,
          pendingSaves: { ...prev.pendingSaves, [key]: "saved" },
        };
      });

      setTimeout(() => {
        set((prev) => {
          if (prev.pendingSaves[key] !== "saved") return {};
          const np = { ...prev.pendingSaves };
          delete np[key];
          return { pendingSaves: np };
        });
      }, 2000);
    } catch (error) {
      if (controller.signal.aborted) return;
      set((prev) => {
        const cleanedPending = new Map(prev._pendingSave);
        if (cleanedPending.get(key)?.controller === controller) {
          cleanedPending.delete(key);
        }
        return {
          _pendingSave: cleanedPending,
          pendingSaves: { ...prev.pendingSaves, [key]: "error" },
          error: String(error),
        };
      });
    }
  },
```

- [ ] **Step 2: Añadir `openWorkerCount`**

Tras `openLightbox` / `closeLightbox` (~línea 248), añadir la acción que abre el visor
en modo conteo. Lee el `worker_cursor` de la celda para reabrir en el archivo donde se
dejó; la página dentro del archivo la restaura el visor.

```js
  openWorkerCount: (hospital, sigla) => {
    const cell = get().session?.cells?.[hospital]?.[sigla];
    set({
      lightbox: {
        hospital,
        sigla,
        fileIndex: cell?.worker_cursor?.file ?? 0,
        mode: "count_workers",
      },
    });
  },
```

- [ ] **Step 3: Verificar la compilación**

Run (desde `frontend/`): `npm run build`
Expected: build sin errores.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/store/session.js
git commit -m "feat(frontend): add saveWorkerCount autosave and openWorkerCount action"
```

### Task 13: Helper `worker-count.js` — totales derivados

**Files:**
- Create: `frontend/src/lib/worker-count.js`

El total de trabajadores de una celda es derivado (spec §6.3): suma de los `count` de
las marcas. El spec lo declara "una suma trivial" que **no amerita un fixture
espejado** — por eso este helper no lleva test; se verifica en el smoke.

- [ ] **Step 1: Crear el helper**

```js
/**
 * Total de trabajadores de una celda: suma de los `count` de todas las marcas
 * de los archivos presentes en `fileNames`. Espejo en JS de compute_worker_count
 * del backend (api/state.py): las marcas de archivos ausentes (renombrados o
 * eliminados) no se cuentan.
 *
 * @param {object} marks - { filename: [{page, count}, ...] }
 * @param {string[]} fileNames - nombres de los PDFs presentes hoy en la celda.
 * @returns {number}
 */
export function computeWorkerCount(marks, fileNames) {
  const present = new Set(fileNames || []);
  let total = 0;
  for (const [filename, pageMarks] of Object.entries(marks || {})) {
    if (fileNames && !present.has(filename)) continue;
    for (const m of pageMarks || []) {
      if (m && typeof m.count === "number") total += m.count;
    }
  }
  return total;
}

/** Subtotal de un solo archivo: suma de los `count` de sus marcas. */
export function fileSubtotal(marks, filename) {
  let total = 0;
  for (const m of marks?.[filename] || []) {
    if (m && typeof m.count === "number") total += m.count;
  }
  return total;
}
```

- [ ] **Step 2: Verificar la compilación**

Run (desde `frontend/`): `npm run build`
Expected: build sin errores.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/worker-count.js
git commit -m "feat(frontend): add worker-count derived-total helpers"
```

### Task 14: Componente `WorkerBubble`

**Files:**
- Create: `frontend/src/components/WorkerBubble.jsx`

La burbuja flotante con sus tres estados (spec §5.1): **vacía** (anillo punteado
gris), **pendiente** (anillo punteado índigo) y **fijada** (círculo sólido índigo).
Es **solo una pantalla**: no contiene un `<input>`. La entrada de números la captura
el teclado del visor (Task 16), de modo que no haya un campo de texto enfocado que
pelee con los atajos `Supr`/`E` del spec §5.4. Se puede arrastrar; la posición **no se
persiste** (vuelve a su lugar en cada sesión).

- [ ] **Step 1: Crear el componente**

```jsx
import { useRef, useState } from "react";

// Estado → estilo del anillo. La metáfora punteado→sólido = borrador→confirmado
// (spec §5.1); no gasta un tercer color ni choca con el ámbar de "sospechoso".
const RING = {
  empty: "border-2 border-dashed border-po-text-subtle text-po-text-subtle",
  pending: "border-2 border-dashed border-po-accent text-po-text",
  fixed: "border-2 border-po-accent bg-po-accent text-white",
};

/**
 * Burbuja flotante de conteo — solo display. El número lo teclea el visor
 * (Task 16) y lo pasa por `value`; aquí no hay `<input>`, así que `Supr`/`E`
 * nunca compiten con un campo de texto enfocado.
 *
 * @param {object} props
 * @param {"empty"|"pending"|"fixed"} props.state
 * @param {string|number} props.value - número a mostrar; "" cuando está vacía.
 */
export function WorkerBubble({ state, value }) {
  const [pos, setPos] = useState({ x: 0, y: 0 }); // offset de arrastre, no persistido
  const drag = useRef(null);

  const onPointerDown = (e) => {
    drag.current = { x: e.clientX, y: e.clientY, bx: pos.x, by: pos.y };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e) => {
    if (!drag.current) return;
    setPos({
      x: drag.current.bx + (e.clientX - drag.current.x),
      y: drag.current.by + (e.clientY - drag.current.y),
    });
  };
  const onPointerUp = () => { drag.current = null; };

  return (
    <div
      className={`absolute right-6 flex h-20 w-20 cursor-grab select-none items-center justify-center rounded-full ${RING[state]}`}
      style={{ top: "50%", transform: `translate(${pos.x}px, calc(-50% + ${pos.y}px))` }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
    >
      <span className="text-2xl font-semibold tabular-nums">
        {value === "" || value == null ? "·" : value}
      </span>
    </div>
  );
}
```

- [ ] **Step 2: Verificar la compilación**

Run (desde `frontend/`): `npm run build`
Expected: build sin errores.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/WorkerBubble.jsx
git commit -m "feat(frontend): add WorkerBubble three-state floating marker"
```

### Task 15: Componente `WorkerHud`

**Files:**
- Create: `frontend/src/components/WorkerHud.jsx`

El panel lateral del visor de conteo: la tira de tres métricas
(Archivo · Página · Subtotal, según el mockup
`docs/research/2026-05-16-mockup-visor-conteo.html`), el total de la
celda, la lista de marcas del archivo actual, el indicador de autosave y la acción
"Terminé esta categoría".

- [ ] **Step 1: Crear el componente**

```jsx
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import SaveIndicator from "../ui/SaveIndicator";

function Metric({ label, value }) {
  return (
    <div className="rounded-lg bg-po-bg p-2 text-center">
      <p className="text-xs text-po-text-muted">{label}</p>
      <p className="text-lg font-semibold tabular-nums text-po-text">{value}</p>
    </div>
  );
}

/**
 * @param {object} props - ver el visor (Task 16) para el origen de cada prop.
 */
export function WorkerHud({
  files, fileIndex, pageInFile, pageCount,
  subtotal, total, marks, currentFilename,
  status, saveStatus, onFinish,
}) {
  const pageMarks = [...(marks[currentFilename] || [])].sort((a, b) => a.page - b.page);

  return (
    <aside className="flex w-72 flex-col gap-4 border-l border-po-border bg-po-panel p-4">
      <div className="grid grid-cols-3 gap-2">
        <Metric label="Archivo" value={`${fileIndex + 1}/${files.length}`} />
        <Metric label="Página" value={`${pageInFile}/${pageCount || "—"}`} />
        <Metric label="Subtotal" value={subtotal} />
      </div>

      <div>
        <p className="text-xs uppercase tracking-wider text-po-text-muted">Total de trabajadores</p>
        <p className="text-4xl font-semibold tabular-nums text-po-text">{total}</p>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <p className="mb-1 text-xs uppercase tracking-wider text-po-text-muted">
          Marcas · {currentFilename}
        </p>
        {pageMarks.length === 0 ? (
          <p className="text-sm text-po-text-subtle">Sin marcas en este archivo.</p>
        ) : (
          <ul className="text-sm">
            {pageMarks.map((m) => (
              <li key={m.page} className="flex justify-between py-0.5">
                <span className="text-po-text-muted">Página {m.page}</span>
                <span className="font-mono tabular-nums text-po-text">{m.count}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex items-center justify-between gap-2">
        <SaveIndicator status={saveStatus} />
        {status === "terminado" && <Badge variant="jade">Terminado</Badge>}
      </div>
      <Button
        variant={status === "terminado" ? "ghost" : "primary"}
        onClick={onFinish}
      >
        {status === "terminado" ? "Marcar en progreso" : "Terminé esta categoría"}
      </Button>
    </aside>
  );
}
```

- [ ] **Step 2: Verificar la compilación**

Run (desde `frontend/`): `npm run build`
Expected: build sin errores.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/WorkerHud.jsx
git commit -m "feat(frontend): add WorkerHud count side panel"
```

### Task 16: Componente `WorkerCountViewer`

**Files:**
- Create: `frontend/src/components/WorkerCountViewer.jsx`

El visor en modo conteo: ensambla la sesión continua multi-PDF, la página actual
(`PdfPage`), la burbuja, el HUD, los atajos de teclado y el autosave con debounce. Es
el componente más grande del feature; concentra toda la interacción de §5.

**Decisiones de diseño** (todas del spec §4.3–§5.4):
- La lista de archivos y su orden vienen de `GET .../files` (Chunk 2 contexto); cada
  archivo trae su `page_count`, así que el HUD sabe "página X/Y" sin abrir el PDF.
- El paginado es continuo: tras la última página del archivo K, PgDn salta a la
  página 1 del archivo K+1.
- Las marcas viven en estado local del visor durante la sesión y se autosalvan con
  debounce — igual que `OverridePanel` mantiene su `value` local (spec §6.2).
- Al cerrar el visor se fuerza un guardado final para no perder lo último.
- La entrada de números la captura el teclado del visor — **no hay ningún `<input>`
  enfocado**; la burbuja es solo pantalla. Así `Supr` (borrar marca) y la corrección
  del número no se pelean por la tecla Delete: el spec §5.4 reserva `Supr` para la
  marca y, sin campo de texto, no hay ambigüedad. La corrección de dígitos es
  `Backspace` sobre el buffer pendiente.
- El teclado se registra una sola vez con un listener estable sobre `window` que
  delega en una ref siempre fresca — evita re-suscribir en cada render. Va sobre
  `window` (no sobre un nodo) **a propósito**: contar es "teclear sin hacer clic en
  ningún campo" (spec §5.2), así que la captura no puede depender del foco. El visor
  solo se monta en modo `count_workers` —un Dialog modal a pantalla completa—, y el
  handler solo hace `preventDefault` de sus propias teclas; deja pasar Escape y Tab,
  así que la trampa de foco y el cierre con Escape del Dialog (FASE 3) siguen intactos.

- [ ] **Step 1: Crear el componente**

```jsx
import { useEffect, useRef, useState } from "react";

import { api } from "../lib/api";
import { useDebouncedCallback } from "../lib/hooks/useDebouncedCallback";
import { usePdfDocument } from "../hooks/usePdfDocument";
import { useSessionStore } from "../store/session";
import { computeWorkerCount, fileSubtotal } from "../lib/worker-count";
import { PdfPage } from "./PdfPage";
import { WorkerBubble } from "./WorkerBubble";
import { WorkerHud } from "./WorkerHud";

const SAVE_DEBOUNCE_MS = 700;

/** La marca de una página concreta de un archivo, o undefined. */
function markFor(marks, filename, page) {
  return (marks[filename] || []).find((m) => m.page === page);
}

export function WorkerCountViewer({ sessionId, hospital, sigla, initialFileIndex }) {
  const saveWorkerCount = useSessionStore((s) => s.saveWorkerCount);
  const saveStatus = useSessionStore(
    (s) => s.pendingSaves[`${hospital}|${sigla}|workers`] ?? "idle",
  );

  // El estado inicial se lee UNA vez del store (no se suscribe a la celda: el
  // visor es dueño de las marcas durante la sesión, igual que OverridePanel).
  const initCell = useSessionStore.getState().session?.cells?.[hospital]?.[sigla];

  const [files, setFiles] = useState(null); // [{name, page_count, ...}] | null
  const [fileIndex, setFileIndex] = useState(initialFileIndex || 0);
  const [pageInFile, setPageInFile] = useState(initCell?.worker_cursor?.page || 1);
  const [marks, setMarks] = useState(() => initCell?.worker_marks || {});
  const [status, setStatus] = useState(initCell?.worker_status || "en_progreso");
  const [pending, setPending] = useState(null); // buffer de dígitos tecleados, o null

  // --- carga de la lista de archivos (orden = sorted rglob del backend) ---
  useEffect(() => {
    let alive = true;
    api.getCellFiles(sessionId, hospital, sigla).then((f) => {
      if (alive) setFiles(f);
    });
    return () => { alive = false; };
  }, [sessionId, hospital, sigla]);

  // El cursor restaurado puede apuntar a un archivo o una página que ya no
  // existen (un PDF se renombró o se acortó entre sesiones, spec §6.3). En vez
  // de confiar en el estado crudo, la posición se DERIVA acotada a lo que hay
  // hoy (`fileIdx` aquí, `page` tras los guards): así un cursor obsoleto nunca
  // deja `files[idx]` undefined —que crashearía el render— ni pide una página
  // inexistente. El estado crudo se realinea en la primera navegación.
  const fileIdx = files?.length
    ? Math.min(Math.max(fileIndex, 0), files.length - 1)
    : 0;

  // --- PDF del archivo actual ---
  const pdfUrl = files?.length
    ? api.cellPdfUrl(sessionId, hospital, sigla, fileIdx)
    : null;
  const { doc, error } = usePdfDocument(pdfUrl);

  // --- autosave con debounce + flush al cerrar ---
  const flushSave = useDebouncedCallback((m, st, cur) => {
    saveWorkerCount(sessionId, hospital, sigla, { marks: m, status: st, cursor: cur });
  }, SAVE_DEBOUNCE_MS);

  // `latest` recibe, ya pasados los guards, la posición DERIVADA (válida); el
  // efecto de desmontaje la persiste como guardado final.
  const latest = useRef(null);
  useEffect(() => {
    return () => {
      flushSave.cancel();
      if (latest.current) {
        saveWorkerCount(sessionId, hospital, sigla, latest.current);
      }
    };
  }, [sessionId, hospital, sigla, saveWorkerCount, flushSave]);

  // limpia el buffer pendiente al cambiar de página
  useEffect(() => {
    setPending(null);
  }, [fileIndex, pageInFile]);

  // --- atajos de teclado: un listener estable que delega en una ref fresca ---
  const keyHandler = useRef(null);
  useEffect(() => {
    const h = (e) => keyHandler.current?.(e);
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  if (error) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-black p-8 text-center text-sm text-po-text-muted">
        No se pudo abrir el PDF. Se puede saltar este archivo; la celda quedará incompleta.
      </div>
    );
  }
  if (!files) {
    return (
      <div className="flex h-full w-full items-center justify-center text-sm text-po-text-muted">
        Cargando archivos…
      </div>
    );
  }
  if (files.length === 0) {
    return (
      <div className="flex h-full w-full items-center justify-center p-8 text-center text-sm text-po-text-muted">
        Esta celda no tiene PDFs que contar.
      </div>
    );
  }

  const currentFile = files[fileIdx];
  const pageCount = currentFile.page_count || 0;
  // página acotada al archivo actual, por el mismo motivo que `fileIdx`
  const page = Math.min(Math.max(pageInFile, 1), Math.max(pageCount, 1));
  const fileNames = files.map((f) => f.name);
  const total = computeWorkerCount(marks, fileNames);
  const subtotal = fileSubtotal(marks, currentFile.name);
  const fixed = markFor(marks, currentFile.name, page);

  const bubbleState = pending != null && pending !== "" ? "pending" : fixed ? "fixed" : "empty";
  const bubbleValue = pending != null && pending !== "" ? pending : fixed ? fixed.count : "";

  // posición derivada (siempre válida) — la que se muestra y se persiste
  latest.current = { marks, status, cursor: { file: fileIdx, page } };

  // --- navegación continua ---
  const advance = () => {
    if (page < pageCount) setPageInFile(page + 1);
    else if (fileIdx < files.length - 1) { setFileIndex(fileIdx + 1); setPageInFile(1); }
  };
  const retreat = () => {
    if (page > 1) setPageInFile(page - 1);
    else if (fileIdx > 0) {
      const prev = fileIdx - 1;
      setFileIndex(prev);
      setPageInFile(files[prev].page_count || 1);
    }
  };

  // --- mutaciones de marcas (cada una autosalva) ---
  const fixAndAdvance = () => {
    let nextMarks = marks;
    const n = pending == null || pending === "" ? null : parseInt(pending, 10);
    if (n != null && !Number.isNaN(n)) {
      const others = (marks[currentFile.name] || []).filter((m) => m.page !== page);
      nextMarks = { ...marks, [currentFile.name]: [...others, { page, count: n }] };
      setMarks(nextMarks);
    }
    // cursor tras avanzar
    let nf = fileIdx, np = page;
    if (page < pageCount) np = page + 1;
    else if (fileIdx < files.length - 1) { nf = fileIdx + 1; np = 1; }
    flushSave(nextMarks, status, { file: nf, page: np });
    setPending(null);
    advance();
  };
  const deleteMark = () => {
    const nextMarks = {
      ...marks,
      [currentFile.name]: (marks[currentFile.name] || []).filter((m) => m.page !== page),
    };
    setMarks(nextMarks);
    setPending(null);
    flushSave(nextMarks, status, { file: fileIdx, page });
  };
  const editMark = () => {
    // E recarga al buffer la marca ya fijada; si había dígitos sin fijar, los
    // descarta — "editar la página actual" parte del valor guardado (spec §5.3).
    if (fixed) setPending(String(fixed.count));
  };
  const toggleFinish = () => {
    const next = status === "terminado" ? "en_progreso" : "terminado";
    setStatus(next);
    flushSave(marks, next, { file: fileIdx, page });
  };

  // refresca la ref del teclado con los closures de este render. El visor no
  // tiene ningún <input>, así que captura toda la entrada: los dígitos van al
  // buffer pendiente, Backspace lo corrige, y los atajos de §5.4 a la marca.
  keyHandler.current = (e) => {
    if (e.key === "PageDown") { e.preventDefault(); fixAndAdvance(); }
    else if (e.key === "PageUp") { e.preventDefault(); retreat(); }
    else if (e.key === "Delete") { e.preventDefault(); deleteMark(); }
    else if (e.key === "e" || e.key === "E") { e.preventDefault(); editMark(); }
    else if (e.key === "Backspace") {
      e.preventDefault();
      setPending((p) => (p && p.length > 1 ? p.slice(0, -1) : null));
    } else if (/^[0-9]$/.test(e.key)) {
      e.preventDefault();
      setPending((p) => ((p ?? "") + e.key).slice(0, 4)); // tope de 4 dígitos
    }
  };

  return (
    <div className="flex h-full w-full">
      <div className="relative flex-1 overflow-auto bg-black">
        {doc && (
          <div className="flex justify-center p-4">
            <PdfPage doc={doc} pageNumber={page} scale={1.8} />
          </div>
        )}
        <WorkerBubble state={bubbleState} value={bubbleValue} />
      </div>
      <WorkerHud
        files={files}
        fileIndex={fileIdx}
        pageInFile={page}
        pageCount={pageCount}
        subtotal={subtotal}
        total={total}
        marks={marks}
        currentFilename={currentFile.name}
        status={status}
        saveStatus={saveStatus}
        onFinish={toggleFinish}
      />
    </div>
  );
}
```

- [ ] **Step 2: Verificar la compilación**

Run (desde `frontend/`): `npm run build`
Expected: build sin errores.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/WorkerCountViewer.jsx
git commit -m "feat(frontend): add WorkerCountViewer count_workers viewer"
```

### Task 17: `PDFLightbox` — branch del modo `count_workers`

**Files:**
- Modify: `frontend/src/components/PDFLightbox.jsx`

- [ ] **Step 1: Enchufar el visor de conteo**

En `frontend/src/components/PDFLightbox.jsx`, añadir el import:

```jsx
import { WorkerCountViewer } from "./WorkerCountViewer";
```

El `Dialog.Body` que dejó la Task 10 contiene el `<div>` de `InspectView` más el
`<aside>` (`CountSummary` + `OverridePanel`). Envolver ese contenido en un branch
sobre `lightbox.mode`: en `count_workers` el cuerpo es el `WorkerCountViewer` a ancho
completo (trae su propio HUD, sin el `<aside>` de inspección).

```jsx
      <Dialog.Body>
        {lightbox.mode === "count_workers" ? (
          <WorkerCountViewer
            sessionId={session.session_id}
            hospital={lightbox.hospital}
            sigla={lightbox.sigla}
            initialFileIndex={lightbox.fileIndex}
          />
        ) : (
          <>
            <div className="flex-1 overflow-hidden bg-black">
              <InspectView url={pdfUrl} />
            </div>
            <aside className="w-80 border-l border-po-border p-4 overflow-y-auto">
              <CountSummary cell={cell} />
              <h4 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mt-6 mb-2">Ajuste manual</h4>
              <OverridePanel hospital={lightbox.hospital} sigla={lightbox.sigla} cell={cell} />
            </aside>
          </>
        )}
      </Dialog.Body>
```

> El bloque del `else` es el `Dialog.Body` tal como lo dejó la Task 10 — reprodúcelo
> tal cual esté en ese momento; lo de arriba es la forma esperada. El único cambio es
> envolverlo en el ternario y añadir la rama `count_workers`.

- [ ] **Step 2: Verificar la compilación**

Run (desde `frontend/`): `npm run build`
Expected: build sin errores.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/PDFLightbox.jsx
git commit -m "feat(frontend): route count_workers mode to WorkerCountViewer"
```

### Task 18: `DetailPanel` — módulo "Contar trabajadores"

**Files:**
- Modify: `frontend/src/components/DetailPanel.jsx`

El punto de entrada del feature (spec §4.4): en el `DetailPanel` de una celda `charla`
o `chintegral`, un módulo con el total de trabajadores, un chip de estado y la acción
para abrir el visor.

- [ ] **Step 1: Añadir el módulo de conteo**

En `frontend/src/components/DetailPanel.jsx`, añadir imports:

```jsx
import { Users } from "lucide-react";
import { useSessionStore } from "../store/session";
import { computeWorkerCount } from "../lib/worker-count";
```

Añadir, a nivel de módulo (junto a `effectiveCount` / `confidenceVariant`), el
componente del módulo. Los tres estados de §4.4: sin iniciar → solo el botón;
`en_progreso` → total + chip ámbar + "Continuar conteo"; `terminado` → total + chip
jade + "Revisar".

```jsx
function WorkerCountModule({ hospital, sigla, cell }) {
  const openWorkerCount = useSessionStore((s) => s.openWorkerCount);
  const status = cell.worker_status;
  const total = computeWorkerCount(cell.worker_marks, Object.keys(cell.per_file || {}));
  const started = status === "en_progreso" || status === "terminado";

  return (
    <div className="mt-6">
      <h4 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mb-2">
        Conteo de trabajadores
      </h4>
      {started && (
        <div className="flex items-center gap-2 mb-2">
          <span className="text-3xl font-semibold tabular-nums">{total.toLocaleString()}</span>
          <span className="text-xs text-po-text-muted">trabajadores</span>
          <Badge variant={status === "terminado" ? "jade" : "amber"}>
            {status === "terminado" ? "Terminado" : "En progreso"}
          </Badge>
        </div>
      )}
      <Button
        variant={started ? "secondary" : "primary"}
        icon={Users}
        onClick={() => openWorkerCount(hospital, sigla)}
      >
        {!started && "Contar trabajadores"}
        {status === "en_progreso" && "Continuar conteo"}
        {status === "terminado" && "Revisar"}
      </Button>
    </div>
  );
}
```

`Button` ya se usa en el proyecto; añadir `import Button from "../ui/Button";` si
`DetailPanel` no lo importaba.

- [ ] **Step 2: Renderizar el módulo en celdas charla/chintegral**

Al final del JSX de `DetailPanel`, después del bloque de `OverridePanel`, antes de
cerrar el `<div>` contenedor:

```jsx
      {(sigla === "charla" || sigla === "chintegral") && (
        <WorkerCountModule hospital={hospital} sigla={sigla} cell={cell} />
      )}
```

- [ ] **Step 3: Verificar la compilación**

Run (desde `frontend/`): `npm run build`
Expected: build sin errores.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/DetailPanel.jsx
git commit -m "feat(frontend): add worker-count module to charla/chintegral cells"
```

### Cierre del Chunk 3

Smoke del conteo por teclado, de principio a fin. Conducir vía chrome-devtools
(`feedback_browser_testing_via_devtools`).

- [ ] **Arrancar la app**

Backend (`python server.py`) y frontend (`npm run dev` desde `frontend/`) corriendo;
abrir `http://localhost:5173`. Abrir una sesión con celdas `charla`/`chintegral` que
tengan PDFs.

- [ ] **Smoke del flujo de conteo**

1. En `HospitalDetail`, seleccionar una celda `charla` → el `DetailPanel` muestra el
   módulo "Conteo de trabajadores" con el botón "Contar trabajadores".
2. Clic → el visor abre en modo `count_workers`: primera página del primer PDF, la
   burbuja vacía (anillo punteado gris), el HUD con Archivo 1/N · Página 1/M.
3. Teclear un número → la burbuja pasa a pendiente (punteado índigo, con el número).
4. `PgDn` → la marca queda fijada (círculo sólido) y avanza a la página siguiente; el
   HUD actualiza Subtotal y Total, el `SaveIndicator` muestra "Guardando…/Guardado".
5. `PgDn` sin teclear número → solo avanza, sin dejar marca.
6. Al pasar la última página de un PDF, `PgDn` salta al PDF siguiente (Archivo 2/N,
   Página 1).
7. `PgUp` retrocede; en una página ya marcada la burbuja muestra la marca fijada.
   `Supr` la borra; `E` la recarga al buffer para editarla — y si había dígitos sin
   fijar, los descarta en favor del valor guardado.
8. "Terminé esta categoría" → el HUD muestra el chip jade "Terminado".
9. Cerrar el visor con la X. En el `DetailPanel`, el módulo ahora muestra el total, el
   chip de estado y el botón "Revisar" (o "Continuar conteo" si quedó en progreso).
10. Reabrir → el visor retoma en el cursor guardado y todas las marcas siguen ahí.

- [ ] **Compilación final del chunk**

Run (desde `frontend/`): `npm run build`
Expected: build sin errores.

---

## Chunk 4: Frontend — voz, aviso de exportación y cierre

Último chunk: la capa de voz (parser de números en español + hook de
`SpeechRecognition`), el aviso de completitud al exportar el Excel, y el smoke de
integración del feature completo.

> **Pre-requisito.** El Spike S1 (validación del Web Speech API en Brave, al inicio
> de este plan) debe estar hecho. Si el spike encontró que la voz no funciona en
> Brave, igual se construye el hook `useSpeechNumber` —el conteo por teclado del
> Chunk 3 ya funciona sin él— y se aplica el Plan B del spike (contar en Chrome, o
> sustituir el motor del hook). El hook aísla esa decisión.

> **Cómo se verifica este chunk.** El parser de números es lógica pura: lleva
> pruebas vitest exhaustivas (spec §11) — Task 19 instala vitest y es la **única
> tarea TDD del frontend**. El hook de voz y el cableado son render/efectos de
> navegador (la voz es una API del navegador, no testeable por unidad — spec §11):
> se verifican con `npm run build` y el smoke final. Task 21 completa la tabla de
> atajos del §5.4 al añadir `M`.

### Task 19: vitest + parser de números en español

**Files:**
- Modify: `frontend/package.json` (devDep `vitest` + script `test`)
- Modify: `frontend/vite.config.js` (bloque `test`)
- Create: `frontend/src/lib/spanish-numbers.cases.json`
- Create: `frontend/src/lib/spanish-numbers.test.js`
- Create: `frontend/src/lib/spanish-numbers.js`

- [ ] **Step 1: Instalar vitest**

Run (desde `frontend/`): `npm install -D vitest`
Luego añadir a la sección `scripts` de `package.json`: `"test": "vitest run"`.
Expected: `vitest` en `devDependencies`; `npm test` disponible.

- [ ] **Step 2: Configurar vitest en `vite.config.js`**

Reemplazar el contenido de `frontend/vite.config.js` — el import pasa a `vitest/config`
(superset del de `vite`) y se añade el bloque `test`:

```js
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: "./",
  test: {
    environment: "node",
  },
});
```

`environment: "node"` — el parser es lógica pura, no toca el DOM.

- [ ] **Step 3: Crear el fixture de casos**

Crear `frontend/src/lib/spanish-numbers.cases.json` con los casos que pide el spec §11
(dígitos, decenas, centenas, conjunciones, límites 0/999, entradas no numéricas):

```json
[
  { "input": "cero", "expected": 0 },
  { "input": "uno", "expected": 1 },
  { "input": "nueve", "expected": 9 },
  { "input": "diez", "expected": 10 },
  { "input": "doce", "expected": 12 },
  { "input": "quince", "expected": 15 },
  { "input": "dieciséis", "expected": 16 },
  { "input": "diecinueve", "expected": 19 },
  { "input": "veinte", "expected": 20 },
  { "input": "veintitrés", "expected": 23 },
  { "input": "treinta y uno", "expected": 31 },
  { "input": "cuarenta y cinco", "expected": 45 },
  { "input": "noventa y nueve", "expected": 99 },
  { "input": "cien", "expected": 100 },
  { "input": "ciento cinco", "expected": 105 },
  { "input": "ciento veintitrés", "expected": 123 },
  { "input": "doscientos treinta y dos", "expected": 232 },
  { "input": "quinientos", "expected": 500 },
  { "input": "novecientos noventa y nueve", "expected": 999 },
  { "input": "23", "expected": 23 },
  { "input": "105", "expected": 105 },
  { "input": "VEINTE", "expected": 20 },
  { "input": "  cuarenta  ", "expected": 40 },
  { "input": "hola", "expected": null },
  { "input": "", "expected": null },
  { "input": "mil", "expected": null }
]
```

- [ ] **Step 4: Escribir el test que falla**

Crear `frontend/src/lib/spanish-numbers.test.js`:

```js
import { describe, expect, it } from "vitest";

import cases from "./spanish-numbers.cases.json";
import { parseSpanishNumber } from "./spanish-numbers";

describe("parseSpanishNumber", () => {
  it.each(cases)("«$input» → $expected", ({ input, expected }) => {
    expect(parseSpanishNumber(input)).toBe(expected);
  });

  it("la conjunción «y» suelta no es un número", () => {
    expect(parseSpanishNumber("y")).toBe(null);
  });

  it("una suma que supera 999 se descarta", () => {
    expect(parseSpanishNumber("novecientos noventa y nueve y uno")).toBe(null);
  });
});
```

- [ ] **Step 5: Correr el test — debe fallar**

Run (desde `frontend/`): `npm test`
Expected: FAIL — no se puede resolver `./spanish-numbers` (el parser no existe aún).

- [ ] **Step 6: Implementar el parser**

Crear `frontend/src/lib/spanish-numbers.js`:

```js
// Valor de cada palabra-átomo. Un número 0–999 en español es la SUMA de sus
// átomos (centena + decena/forma especial + unidad); la conjunción "y" se
// ignora. Las formas se guardan sin acento — el parser normaliza la entrada.
const WORD_VALUE = {
  cero: 0, uno: 1, un: 1, una: 1, dos: 2, tres: 3, cuatro: 4, cinco: 5,
  seis: 6, siete: 7, ocho: 8, nueve: 9,
  diez: 10, once: 11, doce: 12, trece: 13, catorce: 14, quince: 15,
  dieciseis: 16, diecisiete: 17, dieciocho: 18, diecinueve: 19,
  veinte: 20, veintiuno: 21, veintidos: 22, veintitres: 23, veinticuatro: 24,
  veinticinco: 25, veintiseis: 26, veintisiete: 27, veintiocho: 28, veintinueve: 29,
  treinta: 30, cuarenta: 40, cincuenta: 50, sesenta: 60,
  setenta: 70, ochenta: 80, noventa: 90,
  cien: 100, ciento: 100, doscientos: 200, trescientos: 300, cuatrocientos: 400,
  quinientos: 500, seiscientos: 600, setecientos: 700, ochocientos: 800,
  novecientos: 900,
};

/**
 * Convierte una transcripción de voz o de teclado en un entero 0–999, o null si
 * no es un número reconocible. Acepta dígitos ("23") y palabras en español
 * ("veintitrés", "ciento cinco", "cuarenta y uno").
 *
 * @param {string} text
 * @returns {number|null}
 */
export function parseSpanishNumber(text) {
  if (typeof text !== "string") return null;
  // minúsculas y sin acentos
  const norm = text
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .trim();
  if (norm === "") return null;

  // ¿dígitos? — el Web Speech API suele transcribir "veintitrés" como "23"
  const digitRun = norm.match(/\d+/);
  if (digitRun) {
    const n = parseInt(digitRun[0], 10);
    return n >= 0 && n <= 999 ? n : null;
  }

  // palabras: suma de átomos, ignorando "y"
  let total = 0;
  let matched = 0;
  for (const token of norm.split(/[\s-]+/)) {
    if (token === "" || token === "y") continue;
    const value = WORD_VALUE[token];
    if (value === undefined) continue;
    total += value;
    matched += 1;
  }
  if (matched === 0) return null;
  return total >= 0 && total <= 999 ? total : null;
}
```

- [ ] **Step 7: Correr el test — debe pasar**

Run (desde `frontend/`): `npm test`
Expected: PASS — los casos del fixture y los dos `it` extra.

- [ ] **Step 8: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.js frontend/src/lib/spanish-numbers.js frontend/src/lib/spanish-numbers.test.js frontend/src/lib/spanish-numbers.cases.json
git commit -m "feat(frontend): add Spanish number parser with vitest suite"
```

### Task 20: Hook `useSpeechNumber`

**Files:**
- Create: `frontend/src/hooks/useSpeechNumber.js`

Envuelve el Web Speech API y **aísla** la dependencia de voz (spec §5.2): si más
adelante hay que cambiar de motor (Plan B del spike), solo cambia este archivo.

- [ ] **Step 1: Crear el hook**

```js
import { useEffect, useRef, useState } from "react";

import { parseSpanishNumber } from "../lib/spanish-numbers";

const SR =
  typeof window !== "undefined"
    ? window.SpeechRecognition || window.webkitSpeechRecognition
    : null;

/**
 * Escucha por voz y entrega números reconocidos. Mientras `enabled` es true y
 * el navegador soporta `SpeechRecognition`, el reconocedor corre en modo
 * continuo; al pasar a false se DETIENE de verdad (spec §5.2) — no solo se
 * ignora —, así que conversar no genera marcas falsas.
 *
 * @param {object} opts
 * @param {boolean} opts.enabled - escucha cuando es true.
 * @param {(n: number) => void} opts.onNumber - número reconocido.
 * @returns {{status: "unsupported"|"listening"|"paused"|"error"}}
 */
export function useSpeechNumber({ enabled, onNumber }) {
  const [status, setStatus] = useState(SR ? "paused" : "unsupported");
  const onNumberRef = useRef(onNumber);
  onNumberRef.current = onNumber;

  useEffect(() => {
    if (!SR || !enabled) return undefined;

    const rec = new SR();
    rec.lang = "es-CL";
    rec.continuous = true;
    rec.interimResults = false;
    let stopped = false;

    rec.onresult = (e) => {
      const last = e.results[e.results.length - 1];
      const n = parseSpanishNumber(last[0].transcript);
      if (n != null) onNumberRef.current(n);
    };
    rec.onerror = (e) => {
      if (e.error !== "no-speech") setStatus("error");
    };
    rec.onend = () => {
      // el modo continuo se corta solo tras silencios; reiniciar si sigue activo
      if (!stopped) {
        try { rec.start(); } catch { /* ya estaba arrancando */ }
      }
    };

    try {
      rec.start();
      setStatus("listening");
    } catch {
      setStatus("error");
    }

    return () => {
      stopped = true;
      rec.onend = null;
      rec.stop();
      setStatus(SR ? "paused" : "unsupported");
    };
  }, [enabled]);

  return { status };
}
```

- [ ] **Step 2: Verificar la compilación**

Run (desde `frontend/`): `npm run build`
Expected: build sin errores. El comportamiento de voz se verifica en el smoke final.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useSpeechNumber.js
git commit -m "feat(frontend): add useSpeechNumber speech-recognition hook"
```

### Task 21: Cablear la voz en el visor — hook, chip de micrófono, atajo `M`

**Files:**
- Modify: `frontend/src/components/WorkerCountViewer.jsx`
- Modify: `frontend/src/components/WorkerHud.jsx`

- [ ] **Step 1: Conectar el hook en `WorkerCountViewer`**

Añadir el import:

```jsx
import { useSpeechNumber } from "../hooks/useSpeechNumber";
```

Añadir el estado del micrófono junto a los demás `useState` (tras
`const [pending, setPending] = useState(null); ...`):

```jsx
  const [micPaused, setMicPaused] = useState(false);
```

Añadir el hook de voz junto a los demás hooks, **antes de los guards** — p. ej. tras
el `useEffect` del listener de teclado. Un número reconocido entra como pendiente,
igual que si se tecleara (spec §5.2):

```jsx
  const { status: micStatus } = useSpeechNumber({
    enabled: !micPaused,
    onNumber: (n) => setPending(String(n)),
  });
```

Añadir la rama `M` al `keyHandler.current`, tras la rama de `e`/`E`:

```jsx
    else if (e.key === "m" || e.key === "M") { e.preventDefault(); setMicPaused((p) => !p); }
```

Pasar `micStatus` al `WorkerHud` (añadir el prop a la lista que ya se le pasa):

```jsx
        micStatus={micStatus}
```

- [ ] **Step 2: Chip de micrófono en `WorkerHud`**

En `frontend/src/components/WorkerHud.jsx`, añadir el import de iconos:

```jsx
import { Mic, MicOff } from "lucide-react";
```

Añadir `micStatus` a los props destructurados de `WorkerHud`. Añadir, a nivel de
módulo, el chip — reusa el primitive `Badge`, coherente con el resto de chips
(`feedback_chip_consistency`):

```jsx
const MIC_CHIP = {
  listening: { variant: "jade", icon: Mic, label: "Escuchando" },
  paused: { variant: "amber", icon: MicOff, label: "Voz en pausa" },
  error: { variant: "neutral", icon: MicOff, label: "Voz con error" },
  unsupported: { variant: "neutral", icon: MicOff, label: "Voz no disponible" },
};

function MicChip({ status }) {
  const c = MIC_CHIP[status] ?? MIC_CHIP.unsupported;
  return <Badge variant={c.variant} icon={c.icon}>{c.label}</Badge>;
}
```

Reemplazar la fila del indicador de autosave para que incluya el chip de micrófono:

```jsx
      <div className="flex flex-wrap items-center gap-2">
        <MicChip status={micStatus} />
        <SaveIndicator status={saveStatus} />
        {status === "terminado" && <Badge variant="jade">Terminado</Badge>}
      </div>
```

El chip "Voz no disponible" es, además, el aviso del spec §10 cuando el navegador no
soporta el Web Speech API: es un estado visible y permanente, no bloquea el conteo
por teclado, y no interrumpe con un toast repetido.

- [ ] **Step 3: Verificar la compilación**

Run (desde `frontend/`): `npm run build`
Expected: build sin errores.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/WorkerCountViewer.jsx frontend/src/components/WorkerHud.jsx
git commit -m "feat(frontend): wire voice input into the worker-count viewer"
```

### Task 22: Aviso `worker_warnings` al exportar

**Files:**
- Modify: `frontend/src/views/MonthOverview.jsx`

Al exportar, el backend (Chunk 1, Task 5) devuelve `worker_warnings`: las celdas
charla/chintegral con conteo incompleto. El frontend lo muestra como toast — la
exportación **igual procede**, el aviso es informativo (spec §7.3).

- [ ] **Step 1: Mostrar el aviso tras exportar**

En `frontend/src/views/MonthOverview.jsx`, en el handler `onGenerate`, después del
`toast.success` del Excel guardado:

```jsx
  const onGenerate = async () => {
    try {
      const r = await generateOutput(sessionId);
      toast.success(`Excel guardado en ${r.output_path}`, { icon: <FileSpreadsheet size={16} /> });
      if (r.worker_warnings?.length) {
        const lista = r.worker_warnings.map((w) => `${w.hospital}·${w.sigla}`).join(", ");
        toast.warning(
          `Conteo de trabajadores incompleto en ${r.worker_warnings.length} celda(s): ${lista}`,
        );
      }
    } catch (err) {
      toast.error(`No se pudo generar el Excel: ${String(err)}`);
    }
  };
```

`toast.warning` ya está disponible (sonner); no hace falta importar nada nuevo.

- [ ] **Step 2: Verificar la compilación**

Run (desde `frontend/`): `npm run build`
Expected: build sin errores.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/MonthOverview.jsx
git commit -m "feat(frontend): surface worker_warnings as an export toast"
```

### Cierre del Chunk 4 — smoke de integración del feature completo

Último smoke: el feature de punta a punta. Conducir vía chrome-devtools
(`feedback_browser_testing_via_devtools`).

- [ ] **Suite de backend + parser**

Run: `pytest tests/unit/api/test_state.py tests/unit/api/test_routes_sessions.py tests/unit/api/test_routes_output.py tests/unit/excel/test_template_formulas.py -v`
Expected: PASS.
Run (desde `frontend/`): `npm test`
Expected: PASS (el parser de números).
Run: `ruff check .`
Expected: 0 violaciones.

- [ ] **Build de producción**

Run (desde `frontend/`): `npm run build`
Expected: build sin errores.

- [ ] **Smoke de integración**

Backend (`python server.py`) y frontend (`npm run dev`) corriendo; abrir
`http://localhost:5173`.

1. Seleccionar una celda `charla` → el módulo "Conteo de trabajadores" del
   `DetailPanel` → "Contar trabajadores" → abre el visor.
2. **Teclado:** teclear un número, `PgDn` fija y avanza; `PgUp`, `Supr`, `E`
   funcionan; el HUD y el `SaveIndicator` se actualizan.
3. **Voz:** con el micrófono escuchando (chip "Escuchando"), dictar un número en
   español → entra en la burbuja como pendiente; `PgDn` lo fija. Si Brave bloquea la
   voz, el chip muestra "Voz no disponible" y el teclado sigue funcionando (Plan B
   del spike).
4. `M` pausa el micrófono (chip "Voz en pausa"); hablar no genera marcas; `M` lo
   reanuda.
5. "Terminé esta categoría" → chip jade; cerrar el visor; reabrir → retoma en el
   cursor con las marcas intactas.
6. Volver a `MonthOverview` → "Generar Excel". Si alguna celda charla/chintegral
   quedó incompleta, aparece el toast de `worker_warnings` además del de éxito.
7. Abrir el `RESUMEN_<mes>.xlsx` generado → las filas de HH de charla y charla
   integral reflejan los trabajadores contados; `H14` ya usa `=H30*0.5`.

- [ ] **Cierre del plan**

Con el Chunk 4 terminado, el feature está completo: backend (datos, cascada,
template), visor pdf.js, conteo por teclado y voz, y el aviso de exportación.
Actualizar la sección de PDFoverseer en `CLAUDE.md` con un resumen del feature
(spec, plan, tag) siguiendo el formato de las fases anteriores, y etiquetar el hito.
