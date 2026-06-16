# Incremento 3A — maquinaria=chequeos + bug F1 — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Habilitar el conteo de chequeos de `maquinaria` (su número del Excel = tally manual de chequeos, no documentos) reusando el visor de teclado, y arreglar el bug F1 (el total que muestra el visor no coincide con el del detalle/Excel por una divergencia de filtro).

**Architecture:** Las dos piezas comparten el subsistema de marcas (`worker_marks` → suma → filtro → propagación). F1 va **primero** porque su fix (filtro canónico = archivos presentes en la carpeta, vía un helper puro `_sum_marks` en `core/`) es la fundación que usa la rama `checks` de `compute_cell_count`. Luego el backend de maquinaria (count_type plumbing), luego el frontend (mapa estático de count_type + parametrización del visor + gating del render).

**Tech Stack:** Python 3.10+ / FastAPI / PyMuPDF (backend), React + Vite / Vitest (frontend), pytest. Spec: `docs/superpowers/specs/2026-06-16-incremento-3a-maquinaria-checks-f1-design.md`.

**Guardrails:** `ruff check .` = 0 antes de cada commit; sin `/opacity` sobre tokens `po-*` (usar variantes `-bg`/`-border` o `opacity-NN` aparte); tokens de diseño `po-*` en JSX; sin mockear DB (fixtures reales); **no** se tocan `core/{pipeline,ocr,inference,image}.py` ni `vlm/*` ni anchor sets → no aplica `bump-version-tags` ni `SCANNER_PATTERNS_VERSION`. Co-Authored-By trailer: `Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## File Structure

**Backend (modify):**
- `core/cell_count.py` — add pure `_sum_marks(cell, present_files)`; `compute_cell_count(cell, count_type="documents", present_files=None)` con rama `checks`.
- `api/state.py` — `compute_worker_count(cell, present_files=None)` delega en `_sum_marks`.
- `api/routes/sessions.py` — `compute_settled(..., count_type=None)` rama checks; `refresh_all_reliable(..., count_type=None)`; `patch_worker_count` resuelve carpeta → `present_files`, pasa a `compute_worker_count`, y llama `refresh_all_reliable` con count_type; los demás callers de `refresh_all_reliable` pasan `count_type_for(sigla)`.
- `core/excel/writer.py` — `resolve_cell_value(cell, count_type="documents", present_files=None)`.
- `api/routes/output.py` — `_build_cell_values` enhebra `count_type` (vía `count_type_for`) + `present_files` (resuelve carpeta); `_build_worker_values` pasa `present_files`.

**Frontend (modify/create):**
- `frontend/src/lib/sigla-info.js` — add `SIGLA_COUNT_TYPE` map (espejo de `COUNT_TYPE_BY_SIGLA`).
- `frontend/src/lib/cellCount.js` — `_sumMarks(cell, presentFiles)` (mirror) + `computeCellCount(cell, countType, presentFiles)` rama checks.
- `frontend/src/lib/cell-status.js` — `isCellReady(cell, countType)` rama checks; `dotVariantFor(cell, {isScanning, countType})`.
- `frontend/src/components/CategoryRow.jsx` — pasar `countType` a `computeCellCount`/`dotVariantFor`.
- `frontend/src/components/DetailPanel.jsx` — render gate del módulo por count_type (`+ checks`, sin dif_pts); ocultar controles de documento en celdas checks; pasar `countType` al módulo.
- `frontend/src/components/WorkerCountViewer.jsx` — unidad parametrizada (chequeos/trabajadores) + voz off fuera de documents_workers.
- `frontend/src/components/HospitalCard.jsx` — pasar `countType` a `dotVariantFor` (consistencia de la grilla de puntos).

**Tests (create/modify):**
- `tests/fixtures/cell_count_cases.json` — casos `checks` (con `count_type` + `present_files`).
- `tests/test_cell_count_cross_language.py` — leer `count_type`/`present_files` opcionales.
- `tests/unit/api/test_sum_marks_present_files.py` (F1 repro), `tests/unit/api/test_compute_settled_checks.py`, `tests/unit/core/test_compute_cell_count_checks.py`.
- `tests/integration/test_maquinaria_checks.py` (PATCH worker → cuenta/verde/Excel) — **reusa** el fixture existente `session_with_checks_cell` (conftest.py:73, HPV/maquinaria, `maq.pdf`=2pg) + `_make_pdf` (conftest.py:14). El único fixture NUEVO es el de F1 (charla con marca en un PDF no-en-per_file, Task 1.3).
- `frontend/src/lib/cellCount.test.js`, `cell-status.test.js`, `sigla-info.test.js` (completitud count_type).

---

## Chunk 1: F1 fix + fundación core de la suma de marcas

> El filtro canónico = "archivos presentes en la carpeta". Reproduce-first. Esto desbloquea la rama checks de Chunk 2.

### Task 1.1: `_sum_marks` en core + reproducir F1 (test rojo)

**Files:**
- Modify: `core/cell_count.py`
- Test: `tests/unit/api/test_sum_marks_present_files.py` (create)

- [ ] **Step 1: Write the failing test** que reproduce la divergencia (marca sobre un PDF presente pero ausente de `per_file`):

```python
# tests/unit/api/test_sum_marks_present_files.py
"""F1: el total de marcas debe filtrar por archivos PRESENTES en la carpeta,
no por las claves de per_file. Una marca sobre un PDF que existe pero no fue
registrado por pase-1 (no está en per_file) debe contar; una marca huérfana
(PDF ya no presente) NO debe contar."""
from core.cell_count import _sum_marks


def _cell(marks, per_file=None):
    return {"worker_marks": marks, "per_file": per_file or {}}


def test_present_files_counts_marks_on_unregistered_pdf():
    # f_b.pdf existe en la carpeta pero NO está en per_file → su marca DEBE contar.
    cell = _cell(
        marks={"f_a.pdf": [{"page": 1, "count": 10}], "f_b.pdf": [{"page": 1, "count": 36}]},
        per_file={"f_a.pdf": 1},  # pase-1 solo registró f_a
    )
    present = {"f_a.pdf", "f_b.pdf"}
    assert _sum_marks(cell, present) == 46  # 10 + 36, no 10


def test_present_files_drops_orphan_marks():
    # f_old.pdf fue renombrado/borrado → no está presente → su marca NO cuenta.
    cell = _cell(marks={"f_a.pdf": [{"page": 1, "count": 10}], "f_old.pdf": [{"page": 1, "count": 99}]})
    assert _sum_marks(cell, {"f_a.pdf"}) == 10


def test_empty_present_files_is_zero():
    # carpeta vacía (set explícito vacío) → todas las marcas son huérfanas → 0.
    cell = _cell(marks={"f_a.pdf": [{"page": 1, "count": 10}]})
    assert _sum_marks(cell, set()) == 0


def test_none_present_files_falls_back_to_per_file():
    # legacy (present_files=None): filtra por per_file cuando no está vacío.
    cell = _cell(
        marks={"f_a.pdf": [{"page": 1, "count": 10}], "f_b.pdf": [{"page": 1, "count": 36}]},
        per_file={"f_a.pdf": 1},
    )
    assert _sum_marks(cell, None) == 10  # filtra f_b (no en per_file) — comportamiento viejo


def test_none_present_files_no_per_file_sums_all():
    cell = _cell(marks={"f_a.pdf": [{"page": 1, "count": 10}], "f_b.pdf": [{"page": 1, "count": 5}]})
    assert _sum_marks(cell, None) == 15  # per_file vacío → no filtra
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/api/test_sum_marks_present_files.py -v`
Expected: FAIL — `ImportError: cannot import name '_sum_marks'`.

- [ ] **Step 3: Implement `_sum_marks` en `core/cell_count.py`** (función pura; ponerla arriba de `compute_cell_count`):

```python
def _sum_marks(cell: dict, present_files: set[str] | None = None) -> int:
    """Suma de los ``count`` de todas las marcas (``worker_marks``), filtrando a
    los archivos presentes.

    Filtro canónico (F1): si ``present_files`` se entrega (incluido un set vacío),
    solo cuentan las marcas de esos archivos — las huérfanas (PDF renombrado/borrado)
    se descartan. Si ``present_files is None`` (llamador sin carpeta resuelta),
    cae al comportamiento legacy: filtra por las claves de ``per_file`` cuando no
    está vacío, o no filtra si ``per_file`` está vacío.

    Sirve tanto a trabajadores (charla/chintegral) como a chequeos (maquinaria);
    es el mismo mecanismo de marcas por página.
    """
    marks: dict = cell.get("worker_marks") or {}
    if present_files is not None:
        allowed = present_files
        filter_on = True
    else:
        per_file = cell.get("per_file") or {}
        allowed = set(per_file)
        filter_on = bool(per_file)
    total = 0
    for filename, page_marks in marks.items():
        if filter_on and filename not in allowed:
            continue
        for mark in page_marks or []:
            if isinstance(mark, dict):
                total += mark.get("count") or 0
    return total
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/api/test_sum_marks_present_files.py -v` → PASS (5/5).

- [ ] **Step 5: Commit**

```bash
git add core/cell_count.py tests/unit/api/test_sum_marks_present_files.py
git commit -m "feat(3a): core _sum_marks with present-files canonical filter (F1 foundation)"
```

### Task 1.2: `compute_worker_count` delega en `_sum_marks`

**Files:**
- Modify: `api/state.py:53-75`
- Test: `tests/unit/api/test_sum_marks_present_files.py` (extend)

- [ ] **Step 1: Add a failing test** que `compute_worker_count` acepta `present_files`:

```python
# append to tests/unit/api/test_sum_marks_present_files.py
from api.state import compute_worker_count


def test_compute_worker_count_present_files_param():
    cell = {"worker_marks": {"f_a.pdf": [{"page": 1, "count": 10}],
                             "f_b.pdf": [{"page": 1, "count": 36}]},
            "per_file": {"f_a.pdf": 1}}
    assert compute_worker_count(cell, {"f_a.pdf", "f_b.pdf"}) == 46
    assert compute_worker_count(cell) == 10  # legacy default unchanged
```

- [ ] **Step 2: Run** → FAIL (`compute_worker_count() takes 1 positional argument`).

- [ ] **Step 3: Implement** — reemplazar el cuerpo de `compute_worker_count` (api/state.py) para delegar, conservando el docstring (anotar que ahora sirve también a checks):

```python
from core.cell_count import _sum_marks  # add to the existing core.cell_count import line


def compute_worker_count(cell: dict, present_files: set[str] | None = None) -> int:
    """Total de marcas de una celda (trabajadores en charla/chintegral, o
    chequeos en maquinaria — mismo mecanismo). Filtra por archivos presentes;
    ver core.cell_count._sum_marks para la semántica de ``present_files``."""
    return _sum_marks(cell, present_files)
```

> Nota: `api/state.py` ya re-exporta `compute_cell_count` desde `core.cell_count` (línea 11). Agregar `_sum_marks` al mismo import.

- [ ] **Step 4: Run** the full worker-count + sum-marks tests → PASS. `python -m pytest tests/unit/api/ -k "worker or sum_marks" -v`.

- [ ] **Step 5: Commit**

```bash
git add api/state.py tests/unit/api/test_sum_marks_present_files.py
git commit -m "refactor(3a): compute_worker_count delegates to _sum_marks (present_files)"
```

### Task 1.3: el PATCH worker-count y el Excel filtran por archivos presentes

**Files:**
- Modify: `api/routes/sessions.py` (`patch_worker_count` ~721-750), `api/routes/output.py` (`_build_worker_values` ~115-127)
- Test: `tests/integration/test_f1_worker_present_files.py` (create)

- [ ] **Step 1: Failing integration test** — una celda charla con una marca en un PDF presente pero no en per_file; el PATCH devuelve el total con present_files, y el Excel lo refleja.

```python
# tests/integration/test_f1_worker_present_files.py
"""F1 end-to-end: el total del PATCH worker-count y el del Excel cuentan las
marcas sobre archivos presentes en la carpeta, no solo los de per_file."""
# Usa el patrón de fixtures de tests/integration/conftest.py (sesión real + carpeta
# con PDFs reales). Crea una celda charla con dos PDFs en disco (f_a, f_b) donde
# pase-1 solo registró f_a en per_file, y marcas en ambos.
# Asserts:
#  - PATCH .../worker-count devuelve worker_count = suma de AMBOS (no solo f_a).
#  - POST .../output escribe ese mismo total en la columna de trabajadores.
```

> El implementer escribe el cuerpo siguiendo `tests/integration/conftest.py` (fixtures reales, sin mock). Reusar el `client`/`session` existentes; crear los 2 PDFs con el helper de PDFs reales del conftest (p. ej. `_make_pdf`). Glob de nombres que matchee charla: `2026-04-10_charla_a.pdf`, `2026-04-11_charla_b.pdf` — pero forzar que `per_file` solo tenga uno (escanear pase-1 y luego agregar el 2º archivo, o construir el estado con per_file parcial).

- [ ] **Step 2: Run** → FAIL (worker_count y/o Excel cuentan solo f_a).

- [ ] **Step 3: Implement**:
  - En `patch_worker_count` (sessions.py), tras `apply_worker_count`, resolver la carpeta y pasar `present_files` al `compute_worker_count` de la respuesta:

```python
    state = mgr.get_session_state(session_id)
    cell = state["cells"].get(hospital, {}).get(sigla, {})
    month_root = Path(state.get("month_root", ""))
    folder = _find_category_folder(month_root / hospital, sigla)
    present = set(cell_page_counts(folder)) if folder.exists() else None
    return {
        "worker_marks": cell.get("worker_marks"),
        "worker_status": cell.get("worker_status"),
        "worker_cursor": cell.get("worker_cursor"),
        "worker_count": compute_worker_count(cell, present),
    }
```

  - En `_build_worker_values` (output.py), resolver la carpeta por celda worker y pasar `present_files`. El state tiene `month_root`:

```python
def _build_worker_values(state: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    month_root = Path(state.get("month_root", ""))
    for hosp, sigla_map in state.get("cells", {}).items():
        for sigla, purpose in WORKER_PURPOSE.items():
            cell = sigla_map.get(sigla)
            if not cell:
                continue
            if "worker_marks" not in cell and "worker_status" not in cell:
                continue
            folder = _find_category_folder(month_root / hosp, sigla)
            present = set(cell_page_counts(folder)) if folder.exists() else None
            out[f"{hosp}_workers_{purpose}"] = compute_worker_count(cell, present)
    return out
```

> **Imports en output.py (verificado):** `Path` YA está importado (línea 8). Faltan: `count_type_for` (de `core.scanners.patterns`), `_find_category_folder` (de `core.orchestrator`), y `cell_page_counts` (de `api.routes.sessions`). Importar `cell_page_counts` desde `api.routes.sessions` es **cycle-safe** — output.py ya importa `get_manager` de sessions, no se crea ciclo nuevo.

- [ ] **Step 4: Run** → PASS. Correr también la suite de output + sessions: `python -m pytest tests/integration/ -k "f1 or output or worker" -v`.

- [ ] **Step 5: Commit**

```bash
git add api/routes/sessions.py api/routes/output.py tests/integration/test_f1_worker_present_files.py
git commit -m "fix(3a): F1 — worker total filters by present files in PATCH + Excel"
```

### Task 1.4: el frontend (visor + detalle) filtra por los mismos archivos presentes

**Files:**
- Modify: `frontend/src/components/DetailPanel.jsx` (`WorkerCountModule`, ~146-177)
- Test: `frontend/src/lib/worker-count.test.js` (extend si existe; si no, crear) — ya cubre la semántica del filtro; el cambio real es el call-site.

- [ ] **Step 1:** El visor (`WorkerCountViewer.jsx:137-138`) ya filtra por `files.map(f=>f.name)` (archivos del disco) — **correcto, no se toca**. El bug del frontend está en `WorkerCountModule` que filtra por `Object.keys(cell.per_file)`. Cambiarlo para que use los archivos reales de la celda. El módulo ya recibe `cell`; necesita la lista de archivos. Patrón: subir el total al backend o usar la lista de archivos.

  **Decisión de implementación (la más limuda):** el `WorkerCountModule` lee el total autoritativo del **store**, que `saveWorkerCount` ya actualiza con `result.worker_count` (backend, filtrado por presentes — Task 1.3). Agregar `worker_count` al merge del store en `saveWorkerCount` (`session.js:451-453`) y mostrar `cell.worker_count` cuando esté presente, con fallback al cómputo local sobre los archivos de la celda.

  Para el render inicial (sin PATCH aún), `WorkerCountModule` hace un fetch ligero de los nombres (reusa `getCellFiles`, keyed en `filesTick`) y computa `computeWorkerCount(cell.worker_marks, fileNames)` — la MISMA lista que el visor. Eliminar el `Object.keys(cell.per_file)` divergente.

- [ ] **Step 2:** Vitest: un test que `WorkerCountModule` (o la función de total que use) cuenta una marca sobre un archivo presente que no está en `per_file`. (Test de la lógica de total, no del render completo.)

- [ ] **Step 3:** Implementar el cambio de call-site en `WorkerCountModule` + el merge de `worker_count` en `saveWorkerCount`.

- [ ] **Step 4:** `cd frontend && npx vitest run src/lib/worker-count.test.js` → PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/DetailPanel.jsx frontend/src/store/session.js frontend/src/lib/worker-count.test.js
git commit -m "fix(3a): F1 — DetailPanel worker total uses present files, not per_file"
```

---

## Chunk 2: maquinaria backend (count_type = checks)

> La cuenta de una celda checks = el tally de chequeos (no documentos). Usa `_sum_marks` de Chunk 1.

### Task 2.1: `compute_cell_count` rama checks + paridad cross-language

**Files:**
- Modify: `core/cell_count.py` (`compute_cell_count`)
- Modify: `frontend/src/lib/cellCount.js`
- Modify: `tests/test_cell_count_cross_language.py`, `tests/fixtures/cell_count_cases.json`
- Test: `tests/unit/core/test_compute_cell_count_checks.py` (create)

- [ ] **Step 1: Failing tests** (Python unit + nuevos casos en el fixture cross-language):

```python
# tests/unit/core/test_compute_cell_count_checks.py
from core.cell_count import compute_cell_count


def test_checks_uses_tally_not_per_file():
    cell = {"worker_marks": {"m.pdf": [{"page": 1, "count": 5}, {"page": 2, "count": 4}]},
            "per_file": {"m.pdf": 1}, "ocr_count": 99}  # per_file/ocr_count se ignoran
    assert compute_cell_count(cell, "checks", {"m.pdf"}) == 9


def test_checks_respects_user_override():
    cell = {"worker_marks": {"m.pdf": [{"page": 1, "count": 5}]}, "user_override": 3}
    assert compute_cell_count(cell, "checks", {"m.pdf"}) == 3  # override gana


def test_documents_unchanged():
    cell = {"per_file": {"a.pdf": 2, "b.pdf": 3}}
    assert compute_cell_count(cell) == 5  # default count_type=documents, sin cambios
```

Y agregar casos `checks` a `tests/fixtures/cell_count_cases.json` (cada caso gana `count_type` y `present_files` **opcionales**):

```json
{
  "name": "checks_tally_filtered",
  "cell": {"worker_marks": {"m.pdf": [{"page": 1, "count": 5}], "orphan.pdf": [{"page": 1, "count": 9}]}},
  "count_type": "checks",
  "present_files": ["m.pdf"],
  "expected": 5
},
{
  "name": "checks_user_override_wins",
  "cell": {"worker_marks": {"m.pdf": [{"page": 1, "count": 5}]}, "user_override": 2},
  "count_type": "checks",
  "present_files": ["m.pdf"],
  "expected": 2
}
```

Actualizar el harness para leer los campos opcionales:

```python
def test_compute_cell_count_against_shared_fixture(case):
    count_type = case.get("count_type", "documents")
    present = set(case["present_files"]) if "present_files" in case else None
    assert compute_cell_count(case["cell"], count_type, present) == case["expected"], f"case={case['name']}"
```

> **Ojo (paridad JS):** este harness es **solo Python** (corre el JSON contra `compute_cell_count`; el header del archivo dice que el lado JS se valida "during smoke"). Por tanto, agregar casos checks al JSON **no** testea `cellCount.js` automáticamente. Agregar casos `checks` **explícitos** a `frontend/src/lib/cellCount.test.js` (tally filtrado, override gana, set vacío→0) — esa es la red de paridad real del lado JS, y Step 4 la corre.

- [ ] **Step 2: Run** → FAIL (`compute_cell_count() takes 1 positional argument`; harness rojo en casos checks).

- [ ] **Step 3: Implement** la nueva firma + rama checks en `core/cell_count.py`:

```python
def compute_cell_count(cell: dict, count_type: str = "documents",
                       present_files: set[str] | None = None) -> int:
    """... (extender el docstring: count_type 'checks' → tally de _sum_marks;
    present_files se reenvía a _sum_marks.) """
    if cell.get("user_override") is not None:
        return cell["user_override"]
    if count_type == "checks":
        return _sum_marks(cell, present_files)
    per_file = cell.get("per_file") or {}
    per_file_overrides = cell.get("per_file_overrides") or {}
    if per_file or per_file_overrides:
        all_files = set(per_file) | set(per_file_overrides)
        return sum(per_file_overrides.get(f, per_file.get(f, 0)) for f in all_files)
    return cell.get("ocr_count") or cell.get("filename_count") or 0
```

Y el mirror JS en `frontend/src/lib/cellCount.js` — `_sumMarks` fiel a `_sum_marks` (incluida la semántica de set vacío explícito) + rama checks:

```javascript
// Mirror fiel de core/cell_count.py::_sum_marks. present_files: Set|Array|null.
// null → legacy (filtra por per_file si no está vacío); set/array (incl. vacío) → filtra por él.
export function _sumMarks(cell, presentFiles = null) {
  const marks = cell?.worker_marks ?? {};
  let allowed, filterOn;
  if (presentFiles != null) {
    allowed = new Set(presentFiles);
    filterOn = true;
  } else {
    const perFile = cell?.per_file ?? {};
    allowed = new Set(Object.keys(perFile));
    filterOn = allowed.size > 0;
  }
  let total = 0;
  for (const [filename, pageMarks] of Object.entries(marks)) {
    if (filterOn && !allowed.has(filename)) continue;
    for (const m of pageMarks ?? []) {
      if (m && typeof m.count === "number") total += m.count;
    }
  }
  return total;
}

export function computeCellCount(cell, countType = "documents", presentFiles = null) {
  if (cell?.user_override != null) return cell.user_override;
  if (countType === "checks") return _sumMarks(cell, presentFiles);
  return computeFilesCount(cell);
}
```

> **Atención (call-sites de `computeCellCount`):** la firma gana params con default, así que los llamadores actuales (1 arg) siguen compilando con `count_type="documents"`. Chunk 3 actualiza CategoryRow para pasar el countType real.

- [ ] **Step 4: Run** → PASS. `python -m pytest tests/unit/core/test_compute_cell_count_checks.py tests/test_cell_count_cross_language.py -v` y `cd frontend && npx vitest run src/lib/cellCount.test.js`.

- [ ] **Step 5: Commit**

```bash
git add core/cell_count.py frontend/src/lib/cellCount.js tests/test_cell_count_cross_language.py tests/fixtures/cell_count_cases.json tests/unit/core/test_compute_cell_count_checks.py
git commit -m "feat(3a): compute_cell_count checks branch (tally) + JS mirror + cross-lang parity"
```

### Task 2.2: `compute_settled` rama checks + `refresh_all_reliable` count_type

**Files:**
- Modify: `api/routes/sessions.py` (`compute_settled` ~113, `refresh_all_reliable` ~163, sus callers, `patch_worker_count`)
- Test: `tests/unit/api/test_compute_settled_checks.py` (create)

- [ ] **Step 1: Failing test**:

```python
# tests/unit/api/test_compute_settled_checks.py
from pathlib import Path
from api.routes.sessions import compute_settled


def test_checks_settled_when_terminado(tmp_path):
    cell = {"worker_status": "terminado", "worker_marks": {"m.pdf": [{"page": 1, "count": 5}]}}
    assert compute_settled(cell, tmp_path, count_type="checks") is True


def test_checks_not_settled_when_en_progreso(tmp_path):
    cell = {"worker_status": "en_progreso"}
    assert compute_settled(cell, tmp_path, count_type="checks") is False


def test_checks_not_settled_when_no_status(tmp_path):
    assert compute_settled({}, tmp_path, count_type="checks") is False
```

- [ ] **Step 2: Run** → FAIL (`compute_settled() got an unexpected keyword argument 'count_type'`).

- [ ] **Step 3: Implement** — `compute_settled` gana `count_type` y corta temprano para checks (antes de cualquier walk de páginas):

```python
def compute_settled(cell: dict, folder: Path, pages: dict[str, int] | None = None,
                    count_type: str | None = None) -> bool:
    """True iff la celda está 'lista' por procedencia.
    checks (maquinaria): lista sii worker_status == 'terminado' (verificación humana);
    no toca la carpeta. Resto: cada PDF presente tiene origin ∈ {R1, RN, Manual}.
    """
    if count_type == "checks":
        return cell.get("worker_status") == "terminado"
    if pages is None:
        pages = cell_page_counts(folder)
    # ... (resto sin cambios)
```

  `refresh_all_reliable` gana `count_type=None` y lo reenvía:

```python
def refresh_all_reliable(mgr, session_id, hospital, sigla, folder,
                         pages: dict[str, int] | None = None, count_type: str | None = None) -> None:
    state = mgr.get_session_state(session_id)
    cell = state["cells"][hospital][sigla]
    mgr.set_all_reliable(session_id, hospital, sigla,
                         compute_settled(cell, folder, pages=pages, count_type=count_type))
```

  Actualizar los callers de `refresh_all_reliable` para pasar `count_type=count_type_for(sigla)` (apply-ratio ~261, el de per-file override, los de scan). Y en `patch_worker_count`, **agregar** la llamada tras `apply_worker_count` (usando la `folder` ya resuelta en Task 1.3):

```python
    refresh_all_reliable(mgr, session_id, hospital, sigla, folder,
                         count_type=count_type_for(sigla))
```

> `count_type_for` ya está importado en sessions.py (lo usa `_is_capped_sigla`).

- [ ] **Step 4: Run** → PASS. `python -m pytest tests/unit/api/test_compute_settled_checks.py tests/integration -k "settled or reliable or ratio or worker" -v`.

- [ ] **Step 5: Commit**

```bash
git add api/routes/sessions.py tests/unit/api/test_compute_settled_checks.py
git commit -m "feat(3a): compute_settled checks branch + all_reliable refresh after worker PATCH"
```

### Task 2.3: el Excel escribe el tally de maquinaria por el path normal de celda

**Files:**
- Modify: `core/excel/writer.py` (`resolve_cell_value`), `api/routes/output.py` (`_build_cell_values`)
- Test: `tests/unit/core/test_resolve_cell_value_checks.py` (create) + extender el integration de maquinaria (Task 2.4)

- [ ] **Step 1: Failing test**:

```python
# tests/unit/core/test_resolve_cell_value_checks.py
from core.excel.writer import resolve_cell_value


def test_resolve_checks_returns_tally():
    cell = {"worker_marks": {"m.pdf": [{"page": 1, "count": 7}]}}
    assert resolve_cell_value(cell, count_type="checks", present_files={"m.pdf"}) == 7


def test_resolve_documents_unchanged():
    assert resolve_cell_value({"per_file": {"a.pdf": 4}}) == 4
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement** — `resolve_cell_value` gana params y los reenvía:

```python
def resolve_cell_value(cell: dict, count_type: str = "documents",
                       present_files: set[str] | None = None) -> int | None:
    if cell.get("excluded"):
        return None
    value = compute_cell_count(cell, count_type, present_files)
    if value == 0 and cell.get("count") is not None:
        return cell["count"]
    return value
```

  `_build_cell_values` (output.py ~96-107) enhebra count_type + present_files por celda:

```python
def _build_cell_values(state: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    month_root = Path(state.get("month_root", ""))
    cells = state.get("cells", {})
    for hosp in HOSPITALS:
        hosp_cells = cells.get(hosp, {})
        for sigla in SIGLAS:
            ct = count_type_for(sigla)
            present = None
            if ct == "checks":
                folder = _find_category_folder(month_root / hosp, sigla)
                present = set(cell_page_counts(folder)) if folder.exists() else None
            value = resolve_cell_value(hosp_cells.get(sigla, {}), count_type=ct, present_files=present)
            if value is None:
                continue
            out[f"{hosp}_{sigla}_count"] = value
    return out
```

> Importar `count_type_for` (de `core.scanners.patterns`) en output.py. `present` solo se resuelve para checks (evita walks innecesarios en las 16 siglas de documentos).

- [ ] **Step 4: Run** → PASS. `python -m pytest tests/unit/core/test_resolve_cell_value_checks.py -v`.

- [ ] **Step 5: Commit**

```bash
git add core/excel/writer.py api/routes/output.py tests/unit/core/test_resolve_cell_value_checks.py
git commit -m "feat(3a): Excel routes maquinaria check tally via resolve_cell_value(count_type)"
```

### Task 2.4: integración end-to-end de maquinaria

**Files:**
- Test: `tests/integration/test_maquinaria_checks.py` (create). **Reusar** `session_with_checks_cell` (conftest.py:73) — NO recrear el fixture maquinaria.

- [ ] **Step 1: Failing integration test** (fixtures reales, sin mock): usar `session_with_checks_cell` (HPV/maquinaria, `maq.pdf`=2pg); PATCH worker-count con marcas (status terminado); asserts:
  - la cuenta de la celda (vía el snapshot/`compute_cell_count` con count_type=checks) == tally;
  - `all_reliable` True tras terminado;
  - `POST .../output` escribe el tally en la celda de maquinaria de la grilla.

- [ ] **Step 2: Run** → FAIL hasta que el cableado de 2.1-2.3 esté completo (debería pasar ya; si no, arreglar el call-site que falte).

- [ ] **Step 3:** (sin código nuevo esperado; este test es la red de seguridad del cableado de Chunk 2.)

- [ ] **Step 4: Run** → PASS. `python -m pytest tests/integration/test_maquinaria_checks.py -v`.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_maquinaria_checks.py tests/integration/conftest.py
git commit -m "test(3a): maquinaria checks end-to-end (PATCH -> count/green/Excel)"
```

---

## Chunk 3: maquinaria frontend (mapa count_type + visor + render)

### Task 3.1: `SIGLA_COUNT_TYPE` map + completitud

**Files:**
- Modify: `frontend/src/lib/sigla-info.js`, `frontend/src/lib/sigla-info.test.js`

- [ ] **Step 1: Failing test** en `sigla-info.test.js`: todo sigla de `SIGLAS` tiene un `SIGLA_COUNT_TYPE` válido (`documents`/`documents_workers`/`checks`); maquinaria=checks, charla/chintegral/dif_pts=documents_workers.

- [ ] **Step 2: Run** → FAIL (`SIGLA_COUNT_TYPE is not exported`).

- [ ] **Step 3: Implement** en `sigla-info.js` (espejo de `core/scanners/patterns.py::COUNT_TYPE_BY_SIGLA`; comentar el origen):

```javascript
// Espejo de core/scanners/patterns.py::COUNT_TYPE_BY_SIGLA. Conjunto cerrado de
// 18 siglas; la grilla usa esto para no fetchear scan-info por fila. Completitud
// + valores validados en sigla-info.test.js.
export const SIGLA_COUNT_TYPE = {
  reunion: "documents", irl: "documents", odi: "documents",
  charla: "documents_workers", chintegral: "documents_workers", dif_pts: "documents_workers",
  // ... las 12 de documentos restantes ...
  maquinaria: "checks",
};
export const countTypeFor = (sigla) => SIGLA_COUNT_TYPE[sigla] ?? "documents";
```

> El implementer copia los 18 valores verbatim del backend (`COUNT_TYPE_BY_SIGLA`), no de memoria.

- [ ] **Step 4: Run** → PASS. `cd frontend && npx vitest run src/lib/sigla-info.test.js`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/sigla-info.js frontend/src/lib/sigla-info.test.js
git commit -m "feat(3a): SIGLA_COUNT_TYPE frontend map (mirror of COUNT_TYPE_BY_SIGLA)"
```

### Task 3.2: `cell-status` + grilla por count_type

**Files:**
- Modify: `frontend/src/lib/cell-status.js`, `frontend/src/components/CategoryRow.jsx`, `frontend/src/components/HospitalCard.jsx`
- Test: `frontend/src/lib/cell-status.test.js`

- [ ] **Step 1: Failing test**: `isCellReady(cell, "checks")` True sii `worker_status==="terminado"` (sin confirmed/override); `isCellReady(cell, "documents")` mantiene la lógica 1B/2.

```javascript
it("checks cell ready only when terminado", () => {
  expect(isCellReady({ worker_status: "terminado" }, "checks")).toBe(true);
  expect(isCellReady({ worker_status: "en_progreso" }, "checks")).toBe(false);
  expect(isCellReady({}, "checks")).toBe(false);
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement** — `isCellReady(cell, countType)` + `dotVariantFor(cell, {isScanning, countType})`:

```javascript
export function isCellReady(cell, countType = "documents") {
  if (!!cell?.confirmed || hasOverride(cell)) return true;
  if (countType === "checks") return cell?.worker_status === "terminado";
  return cell?.all_reliable ?? allFilesReliable(cell);
}

export function dotVariantFor(cell, { isScanning = false, countType = "documents" } = {}) {
  if (isScanning) return "state-scanning";
  if (cell?.errors?.length > 0) return "state-error";
  if (!cell) return "neutral";
  return isCellReady(cell, countType) ? "confidence-high" : "confidence-low";
}
```

  **Barrer TODOS los consumidores** (decisión consciente: pasar `countTypeFor(sigla)` en cada uno, para que las celdas checks no contribuyan un número de documentos equivocado a agregados/pendientes). La firma con default no rompe la compilación, así que el riesgo es **wrongness silenciosa**, no un crash:
  - `computeCellCount(cell)` → pasar `countTypeFor(sigla)`: `CategoryRow.jsx:69` (número de fila; sin presentFiles en la grilla — backend autoritativo, huérfanos raros), `MonthOverview.jsx:47`, `HospitalDetail.jsx:20` (totales agregados), `scanCost.js:40`.
  - `dotVariantFor(cell, {...})` → agregar `countType: countTypeFor(sigla)`: `CategoryRow.jsx:58`, `HospitalCard.jsx:54`.
  - `isCellReady(cell)` → pasar `countTypeFor(sigla)`: `CategoryBulkActions.jsx:14`, `session.js:158` (conteo/filtro de pendientes — sin esto, una maquinaria `terminado` se lee como pendiente).
  (Todos tienen la sigla en scope, verificado.)

- [ ] **Step 4: Run** → PASS (`cell-status.test.js` + build). Confirmar por grep que NINGÚN call-site de `computeCellCount`/`isCellReady`/`dotVariantFor` quedó sin `countType` (los 8 de arriba + los 2 de DetailPanel que se enrutan en 3.4).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/cell-status.js frontend/src/components/CategoryRow.jsx frontend/src/components/HospitalCard.jsx frontend/src/lib/cell-status.test.js
git commit -m "feat(3a): green dot + grid count honor count_type (checks ready on terminado)"
```

### Task 3.3: visor parametrizado por unidad + voz off en checks

**Files:**
- Modify: `frontend/src/components/WorkerCountViewer.jsx`

- [ ] **Step 1:** Derivar `countType = countTypeFor(sigla)` en el visor. Parametrizar los textos: `checks` → "chequeos"; `documents_workers` → "trabajadores" (actual). Desactivar la voz (`useSpeechNumber`, tecla M, indicador de mic) cuando `countType !== "documents_workers"`.

- [ ] **Step 2:** Vitest si hay test del visor; si no, smoke manual en Task de smoke. Como mínimo, un test de que el label de unidad deriva de countType (extraer la lógica de label a una función pura testeable si ayuda).

- [ ] **Step 3:** Implementar. Mantener la voz **idéntica** para charla/chintegral (no regresar Feature 1). **Gate de voz limpio (verificado):** `useSpeechNumber` ya recibe un param `enabled` (hoy `enabled: !micPaused`) y para el reconocedor cuando es false (`useSpeechNumber.js:21,27`). Por tanto el hook se sigue llamando SIEMPRE (sin Rules-of-Hooks) — gatear con `enabled: !micPaused && countType === "documents_workers"`. Ocultar además la tecla "M" (handler ~213) y el indicador de mic cuando `countType !== "documents_workers"`.

- [ ] **Step 4:** `cd frontend && npx vitest run` + `npm run build` limpio.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/WorkerCountViewer.jsx
git commit -m "feat(3a): counter viewer parametrized by unit (chequeos) + voice off outside workers"
```

### Task 3.4: DetailPanel — render gate por count_type + ocultar controles de documento en checks

**Files:**
- Modify: `frontend/src/components/DetailPanel.jsx`
- Test: vitest del gate (extraer a función pura si conviene) o smoke conducido.

- [ ] **Step 1:** Render del módulo de conteo: gate de `sigla === "charla" || sigla === "chintegral"` →
  `count_type === "checks" || sigla === "charla" || sigla === "chintegral"` (sin dif_pts). El `count_type` ya está disponible vía `scanInfo?.count_type` (DetailPanel:411) o `countTypeFor(sigla)`. Pasar `countType` al `WorkerCountModule` para sus textos.

- [ ] **Step 2:** Para celdas `checks`, ocultar/enrutar **todos** los bloques de conteo de documentos (la cuenta viene del tally; el `WorkerCountModule` de 3.3 es el número primario). Envolver cada uno en `count_type !== "checks"`:
  - **El número grande de documentos** (`DetailPanel.jsx:265-266`, `{total.toLocaleString()}` + "documentos", alimentado por `computeCellCount(cell)` en ~233) — **crítico**: sin esto, una celda checks muestra un número de documentos equivocado arriba. Ocultarlo (el `WorkerCountModule` muestra el tally) **o** pasar `countTypeFor(sigla)` a `computeCellCount` en la línea 233.
  - **La tabla "Conteo automático"** (`DetailPanel.jsx:366-401`).
  - El toggle `Archivo·Manual` (`~268-281`), el cluster `Aplicar R1 / ratio N` (`~283-344`), y `OverridePanel` (`~404-412`).
  - La lista de archivos (`FileList`) **queda visible** (informativa).
  > No hay un wrapper único — gatear cada bloque. Los hooks (`useState` ~190-191) están sobre el early-return (~221), así que leer `count_type` para el gate es Rules-of-Hooks-safe.

- [ ] **Step 3:** Implementar los condicionales de render. `WorkerCountModule` ya parametrizado en 3.3 (textos por countType); el botón "Contar chequeos" / "Continuar conteo" / "Revisar".

- [ ] **Step 4:** `npm run build` limpio + vitest verde. (El smoke conducido valida el render real.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/DetailPanel.jsx
git commit -m "feat(3a): DetailPanel routes counter by count_type; hides doc controls for checks"
```

---

## Cierre (tras todas las tareas)

- [ ] **Suite completa verde:** `ruff check .` (0) · `python -m pytest` (incl. integración lenta) · `cd frontend && npx vitest run` · `npm run build`.
- [ ] **Final code review** (subagent) de toda la implementación contra el spec.
- [ ] **Smoke conducido** (chrome-devtools, data-safe): respaldar `data/overseer.db` a `data/_smoke-backup-<ts>/`; sobre **ABRIL** (nunca MAYO): (a) contar chequeos en una `maquinaria` → número en la grilla + punto verde al terminar + el Excel generado lleva ese número; (b) repro F1 — recontar un `charla` y confirmar detalle + Excel == visor. Restaurar la DB.
- [ ] **Tag** `incremento-3a` sobre el último commit; **push** `po_overhaul` + tag al cierre de la ronda.
- [ ] **Memoria:** `project_incremento_3a_shipped` + actualizar `MEMORY.md` + `project_roadmap_next` (3A ✅, siguiente = 3B). Actualizar la sección "Project history" de `CLAUDE.md`.
