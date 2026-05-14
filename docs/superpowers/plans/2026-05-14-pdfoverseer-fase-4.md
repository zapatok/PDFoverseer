# PDFoverseer FASE 4 — Slice UX Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cerrar 3 pendientes UX del roadmap post-FASE 3 (HLL manual-entry, docs por archivo en FileList, multi-mes histórico) sobre la base de diseño FASE 3 sin romper el contrato de FASE 2.

**Architecture:** 4 capas. (1) Backend per-file: extiende `ScanResult.per_file: dict[str, int] | None` propagado por scanners; persiste en cell state nested (`state["cells"][hospital][sigla]`); nuevo endpoint `PATCH /files/{f}/override`; nuevo endpoint `GET /history?n=12` que delega en `historical_repo.query_range`. (2) Frontend cross-language helper: `frontend/src/lib/cellCount.js` espeja `compute_cell_count` de Python con fixtures JSON cross-language. (3) Frontend nuevos componentes: `Sparkline` (~50 LoC SVG), `OriginChip` (3 variantes sobre Badge), `InlineEditCount` extraído a primitive propio, FileList row extendido. (4) Frontend flows: HospitalCard CTA "Llenar manualmente" + extensión Zustand store con `hospitalMode` + `focusSigla` (NO react-router), SparkGrid + toggle Histórico en MonthOverview con `useHistoryStore` (cache módulo-level).

**Tech Stack:** Python 3.10+ (FastAPI, PyMuPDF, pytest), React 18 + Vite, Zustand, Tailwind 3 con `po-*` tokens (FASE 3), `@radix-ui/react-{dialog,tooltip}`, `lucide-react`, `sonner`. **Cero deps nuevas** (todo se construye sobre la base FASE 3 — no react-router, no vitest).

**Spec:** [`docs/superpowers/specs/2026-05-14-fase-4-design.md`](../specs/2026-05-14-fase-4-design.md) (aprobado en 3 iteraciones, último commit `5e97e17`).

**Predecesor:** Tag `fase-3-polish` (commit `911084f`) en rama `po_overhaul`. **No** se crea worktree nuevo — continuamos en `po_overhaul`.

---

## Conventions for this plan

### TDD adaptation por capa

| Capa | Tool | Disciplina |
|------|------|------------|
| Backend Python | `pytest` | Estricta TDD: test rojo → impl → test verde → commit. Fixtures reales (memoria `feedback_no_db_mocking`). |
| Frontend `.jsx`/`.js` | `npm run build` | Sin test runner UI (FASE 3 §8 + FASE 4 §9.1 lo confirman). Cada cambio: (a) editar, (b) `cd frontend && npm run build` verde, (c) smoke visual cuando hay UI nueva, (d) commit. |
| Cross-language `cellCount` | `pytest` con fixtures JSON | Fixtures `tests/fixtures/cell_count_cases.json` validados desde Python; paridad JS verificada en smoke manual. |
| E2E smoke | chrome-devtools MCP | Claude maneja al final del plan. Memoria `feedback_browser_testing_via_devtools`. |

### File path conventions

- Paths relativos a repo root `a:\PROJECTS\PDFoverseer\`.
- Forward slashes en comandos.
- Frontend: `.jsx` para componentes (`frontend/src/components/`), `.js` para utils (`frontend/src/lib/`), Zustand store en `frontend/src/store/session.js`. **No TypeScript**, no `utils/` dir.
- Tests Python: `tests/test_<feature>.py`.
- **Plataforma:** Windows + PowerShell por default. Para comandos POSIX (`cp`, `pkill`, `&`, `sleep`) usar `Bash` tool explícitamente o equivalente PowerShell.

### Commit message format

`<type>(<scope>): <message>` por CLAUDE.md. Tipos en este plan:

- `feat(scanners)` / `feat(api)` / `feat(ui)` — funcionalidad nueva
- `refactor(<file>)` — cambios sin alterar comportamiento externo (extracción, renames)
- `test(<feature>)` — solo tests
- `docs(plan)` / `docs(claude-md)` — documentación
- `chore(verify)` — pre-flight checks

Trailer obligatorio en cada commit:
```
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

### Scope guardrails

- **Method literals:** registry congelado en spec §6.3 — solo `filename_glob`, `header_detect`, `corner_count`, `page_count_pure`, `manual`. Verificable en `frontend/src/lib/method-labels.js`.
- **Schema:** `historical_counts` no se migra. Columnas `year INTEGER, month INTEGER` (separadas), PK `(year, month, hospital, sigla)`.
- **Funciones existentes (NO inventar):**
  - `historical_repo.query_range(conn, *, from_year, from_month, to_year, to_month)` — ya existe.
  - `historical_repo.upsert_count(...)` — ya existe.
  - `SessionManager._load_and_migrate(session_id) → (state, last_modified)` — método "privado" (underscore) pero estable; no hay `get_state` público.
  - `update_session_state(conn, session_id, state_json=...)` — función módulo-level en `api/state.py`. Es como persistes después de mutar.
  - `get_manager()` — placeholder DI en `api/routes/sessions.py:77`, overridden en main.py. Importar como `from api.routes.sessions import get_manager` o definir localmente.
- **Cell shape:** `state["cells"][hospital][sigla]` (nested, NO flat key `f"{h}|{s}"`). Verificable en `apply_filename_result:101`, `apply_ocr_result:130`, `apply_user_override:162`.
- **Override endpoint:** `PATCH /sessions/{id}/cells/{h}/{s}/override` (sessions.py:252). Llama `mgr.apply_user_override(sid, h, s, value=..., note=...)` — kwargs only.
- **Navegación frontend:** Zustand store, NO react-router. Estado `view: "month"|"hospital"`, acciones `setView(view)`, `selectHospital(code)`.
- **InlineEditCount:** hoy vive como función nested DENTRO de `frontend/src/components/CategoryRow.jsx:25`. La Task 2.5 lo extrae a `frontend/src/components/InlineEditCount.jsx` como pre-requisito para Task 15.
- **Tailwind tokens:** los tonos disponibles para "warn"/"alarma" son la familia `po-suspect`/`po-suspect-bg`/`po-suspect-border` (amber-11/a3/a7). **NO existe `po-warning`** — no usar.
- **CTA copy:** "Llenar manualmente →" (con flecha). Single string en `frontend/src/lib/constants.js`.
- **Po-* tokens:** todo el JSX usa `po-*`, nunca raw `bg-slate-*`. Audit por grep al cierre.

---

## Pre-flight (Chunk 0)

**Propósito:** descartar bugs latentes y reconfirmar invariantes que el plan asume. **Bloqueante** — si algo falla, fix antes de Chunk 1.

### Task 0: Verify `historical_counts` populates today

**Files:** ninguno (solo lectura + Excel temporal)

Riesgo §8.4: bug latente FASE 2 donde `historical_counts` no se popula al generar Excel. Si está, el toggle Histórico de FASE 4 muestra grid vacío.

- [ ] **Step 1: Backup current DB**

PowerShell:
```powershell
Copy-Item data/overseer.db data/overseer.db.preflight-backup -Force
```

O Bash:
```bash
cp data/overseer.db data/overseer.db.preflight-backup
```

- [ ] **Step 2: Inspect current rows**

```bash
sqlite3 data/overseer.db "SELECT COUNT(*), GROUP_CONCAT(DISTINCT method) FROM historical_counts;"
sqlite3 data/overseer.db "SELECT year, month, hospital, sigla, count, method FROM historical_counts ORDER BY year DESC, month DESC LIMIT 10;"
```

Anotar el COUNT actual como baseline.

- [ ] **Step 3: Run end-to-end smoke for ABRIL (manual via UI is OK; or via API)**

Si tienes el server corriendo y prefieres UI: abrir frontend, sesión sobre `A:/informe mensual/04 Abril/`, generar Excel.

Si vía API:

```bash
# Inicia server en otra terminal: python server.py
curl -s -X POST http://localhost:8000/sessions -H "Content-Type: application/json" -d '{"month_root":"A:/informe mensual/04 Abril/"}'
# Anotar session_id de la respuesta
SID="<paste>"
curl -s -X POST "http://localhost:8000/sessions/$SID/output"
```

Expected: 200 OK, archivo `RESUMEN_2026-04.xlsx` creado.

- [ ] **Step 4: Re-inspect historical_counts**

```bash
sqlite3 data/overseer.db "SELECT COUNT(*) FROM historical_counts WHERE year=2026 AND month=4;"
sqlite3 data/overseer.db "SELECT DISTINCT method FROM historical_counts WHERE year=2026 AND month=4;"
```

Expected: COUNT >= 1, methods ⊆ `{filename_glob, header_detect, corner_count, page_count_pure, manual}`. **Nota:** el número exacto (≤54) depende de qué celdas se persisten — siglas con count=0 pueden o no escribirse según `core/excel/writer.py`. Lo importante es que **algunos** rows se escriben con methods válidos.

- [ ] **Step 5: Verify methods registry**

Si en Step 4 aparece algún method que NO está en el registry, surface al usuario antes de avanzar — significa que FASE 2 está usando literales fuera del contrato congelado.

- [ ] **Step 6: Restore DB if you don't want to keep test data**

```powershell
Copy-Item data/overseer.db.preflight-backup data/overseer.db -Force
```

(Opcional. Sin commit.)

### Task 1: Verify `core/excel/writer.py` tolerates missing hospital

**Files:**
- Test: `tests/test_writer_missing_hospital.py` (nuevo si no existe)

Spec §5.2 + AC1: Excel generable aunque HLL no tenga datos.

- [ ] **Step 1: Check if test already exists**

```bash
grep -r "missing_hospital\|test_.*HLL.*missing\|hospital.*sin datos" tests/test_writer*.py 2>/dev/null
```

Si existe — marca esta tarea como done y avanza.

- [ ] **Step 2: Inspect writer signature first**

```bash
grep -n "^def generate_resumen\|def write_resumen\|^def write\b" core/excel/writer.py
```

Adjustar el test al nombre real (puede ser `generate_resumen`, `write_resumen` u otro).

- [ ] **Step 3: Write the failing test**

Crear `tests/test_writer_missing_hospital.py` (ajustar import al nombre real):

```python
"""Verify writer tolerates a hospital with no cells in session state.

Pre-flight FASE 4: HLL manual-entry permite que un hospital quede sin
datos; el Excel debe seguir generándose (HLL columns en 0 / vacío) sin
error.
"""
from pathlib import Path

import pytest
from openpyxl import load_workbook

# Ajustar al nombre real localizado en Step 2
from core.excel.writer import generate_resumen


def test_generate_resumen_with_missing_hll(tmp_path):
    """3 hospitales con cells, HLL omitido. Writer no debe crashear."""
    cells_state = {
        "HPV": {f"sigla_{i}": {
            "filename_count": 5,
            "ocr_count": None,
            "user_override": None,
            "excluded": False,
        } for i in range(1, 19)},
        "HRB": {f"sigla_{i}": {
            "filename_count": 5,
            "ocr_count": None,
            "user_override": None,
            "excluded": False,
        } for i in range(1, 19)},
        "HLU": {f"sigla_{i}": {
            "filename_count": 5,
            "ocr_count": None,
            "user_override": None,
            "excluded": False,
        } for i in range(1, 19)},
        # HLL deliberately omitted
    }

    template = Path("data/templates/RESUMEN_template_v1.xlsx")
    output = tmp_path / "RESUMEN_test.xlsx"

    generate_resumen(
        cells_state,
        template_path=template,
        output_path=output,
        year=2026,
        month=4,
    )

    assert output.exists(), "Excel was not created"
    wb = load_workbook(output)
    wb.close()
```

(Si `generate_resumen` espera otro shape — ej. lista de cells aplanada — ajustar la fixture y los kwargs.)

- [ ] **Step 4: Run test, observe outcome**

```bash
pytest tests/test_writer_missing_hospital.py -v
```

- [ ] **Step 5a: If PASS — commit as regression guard**

```bash
git add tests/test_writer_missing_hospital.py
git commit -m "$(cat <<'EOF'
test(writer): regression guard for missing-hospital cells (FASE 4 pre-flight)

Verifica que el writer tolera session state donde un hospital (típicamente
HLL) no tiene cells. Pre-flight para FASE 4 HLL manual-entry.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5b: If FAIL — minimal fix to writer.py**

Inspeccionar la traza. Fix probable: usar `.get(hospital, {})` o iterar solo los hospitales presentes con default 0. Aplicar fix mínimo, re-correr el test:

```bash
pytest tests/test_writer_missing_hospital.py -v
```

Commit con ambos archivos:

```bash
git add tests/test_writer_missing_hospital.py core/excel/writer.py
git commit -m "$(cat <<'EOF'
fix(writer): tolerate cells missing for a hospital

Default a count=0 cuando un (hospital, sigla) no tiene entry en session
state. Pre-flight para FASE 4 HLL manual-entry.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 2: Verify FASE 3 invariants (saveOverride + signatures)

**Files:** ninguno (verification only)

- [ ] **Step 1: Verify saveOverride signature**

```bash
grep -A 3 "saveOverride: async" frontend/src/store/session.js
```

Expected:
```js
saveOverride: async (sessionId, hospital, sigla, value, note) => {
  const key = `${hospital}|${sigla}`;
  ...
}
```

5 args (sessionId, hospital, sigla, value, note). Si la signature difiere, los snippets de Task 15 + Task 16 deben adaptarse.

- [ ] **Step 2: Verify pendingSaves AbortController pattern intact**

```bash
grep -n "pendingSaves\|AbortController\|controller.abort" frontend/src/store/session.js
```

Expected: ≥1 match cada uno. Si no hay AbortController-safe, surface — Task 15 lo asume.

- [ ] **Step 3: Verify historical_repo.query_range signature**

```bash
grep -A 8 "^def query_range" core/db/historical_repo.py
```

Expected: kwargs `from_year, from_month, to_year, to_month`. Si difiere, ajustar Task 11.

- [ ] **Step 4: Verify historical_repo.upsert_count exists**

```bash
grep "^def upsert_count" core/db/historical_repo.py
```

Expected: 1 match.

- [ ] **Step 5: Verify SessionManager API**

```bash
grep -n "def get_session_state\|def _load_and_migrate\|def apply_\|def open_session" api/state.py
```

Expected: `_load_and_migrate(session_id)`, `apply_filename_result`, `apply_ocr_result`, `apply_user_override`, `apply_cell_result`, `open_session`. NO `get_state`/`set_state` públicos. Persistencia vía `update_session_state(conn, sid, state_json=...)` (módulo-level).

- [ ] **Step 6: Verify get_manager DI**

```bash
grep -n "def get_manager" api/routes/sessions.py api/main.py
```

Expected: placeholder en sessions.py, override en main.py. Importable desde `api.routes.sessions`.

- [ ] **Step 7: Verify Tailwind po-suspect tokens**

```bash
grep "po-suspect\|po-warning" frontend/tailwind.config.js
```

Expected: `po-suspect`, `po-suspect-bg`, `po-suspect-border` (amber). **CERO** matches para `po-warning` — confirmar que no existe.

- [ ] **Step 8: No commit (verification). If todo OK, avanzar a Pre-flight Task 2.5.**

### Task 2.5: Extract `InlineEditCount` to its own component (refactor)

**Files:**
- Create: `frontend/src/components/InlineEditCount.jsx`
- Modify: `frontend/src/components/CategoryRow.jsx` (importar el extraído)

Pre-requisito para Task 15 (FileList per-file edit). Hoy `InlineEditCount` vive como función local dentro de `CategoryRow.jsx:25`. Lo extraemos sin cambiar comportamiento (refactor puro, no behavior delta).

- [ ] **Step 1: Read the existing inline component**

```bash
sed -n '20,75p' frontend/src/components/CategoryRow.jsx
```

Localizar el `function InlineEditCount({ value, onCommit })` interno y todo su body (probablemente ~40 líneas hasta el fin del componente).

- [ ] **Step 2: Create the extracted file**

`frontend/src/components/InlineEditCount.jsx` — copiar VERBATIM el body de la función nested actual, agregar `export default` y los imports necesarios (`useState`, `useRef`, `useEffect` según lo que use).

```jsx
// Extracted from CategoryRow.jsx (FASE 4 Task 2.5). Refactor puro: no
// behavior change. Reusado en FileList row para per-file overrides.

import { useState, useRef, useEffect } from "react";

export default function InlineEditCount({ value, onCommit, ...rest }) {
  // ... pegar exactamente el body actual ...
}
```

(Inspeccionar qué hooks/props se usan internamente y replicar 1:1.)

- [ ] **Step 3: Modify CategoryRow.jsx to import the extracted component**

Borrar la `function InlineEditCount(...)` local. Agregar arriba:

```jsx
import InlineEditCount from "./InlineEditCount";
```

- [ ] **Step 4: Verify build is green**

```bash
cd frontend && npm run build
```

Expected: green.

- [ ] **Step 5: Visual smoke (manual)**

```bash
cd frontend && npm run dev
# Browser: abrir un mes, ir a un HospitalDetail, click en un count number,
# editar inline, Enter. Verificar que el comportamiento sea idéntico al
# pre-refactor (mismo focus, blur, key handling).
```

- [ ] **Step 6: Commit**

```bash
cd a:/PROJECTS/PDFoverseer
git add frontend/src/components/InlineEditCount.jsx frontend/src/components/CategoryRow.jsx
git commit -m "$(cat <<'EOF'
refactor(category-row): extract InlineEditCount to its own component

Pre-requisito FASE 4 Task 15 — el component se va a reusar en FileList
para per-file overrides. Sin behavior change: API (value, onCommit) y
markup idénticos. Smoke verde.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Chunk 1: Backend per-file plumbing

### Task 3: Extend `ScanResult` with `per_file` field

**Files:**
- Modify: `core/scanners/base.py:17-26`
- Test: `tests/test_scan_result_per_file.py` (nuevo)

Spec §5.2: aditivo, default `None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scan_result_per_file.py
"""ScanResult.per_file field — FASE 4."""
import json
from dataclasses import asdict

from core.scanners.base import ConfidenceLevel, ScanResult


def test_scan_result_default_per_file_is_none():
    result = ScanResult(
        count=5,
        confidence=ConfidenceLevel.HIGH,
        method="filename_glob",
        breakdown=None,
        flags=[],
        errors=[],
        duration_ms=10,
        files_scanned=5,
    )
    assert result.per_file is None


def test_scan_result_with_per_file_serializes_via_asdict():
    result = ScanResult(
        count=24,
        confidence=ConfidenceLevel.HIGH,
        method="header_detect",
        breakdown=None,
        flags=[],
        errors=[],
        duration_ms=8345,
        files_scanned=2,
        per_file={"a.pdf": 20, "b.pdf": 4},
    )
    d = asdict(result)
    assert d["per_file"] == {"a.pdf": 20, "b.pdf": 4}
    assert json.dumps(d["per_file"])
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/test_scan_result_per_file.py -v
```

Expected: FAIL — `unexpected keyword argument 'per_file'` y/o `AttributeError`.

- [ ] **Step 3: Add per_file field**

Modificar `core/scanners/base.py` (clase `ScanResult` líneas 17-26):

```python
@dataclass(frozen=True)
class ScanResult:
    count: int
    confidence: ConfidenceLevel
    method: str
    breakdown: dict[str, int] | None
    flags: list[str]
    errors: list[str]
    duration_ms: int
    files_scanned: int
    per_file: dict[str, int] | None = None
```

(Solo el último field es nuevo. Default `None` preserva todos los call sites existentes.)

- [ ] **Step 4: Verify pass**

```bash
pytest tests/test_scan_result_per_file.py -v
pytest tests/ -q
```

Expected: 2 PASS + zero regressions.

- [ ] **Step 5: Commit**

```bash
git add core/scanners/base.py tests/test_scan_result_per_file.py
git commit -m "$(cat <<'EOF'
feat(scanners): add ScanResult.per_file field for per-file doc count

Aditive field defaulting to None. Subsequent tasks populate it from each
scanner. Spec §5.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 3.5: Extend `GlobCountResult` with `matched_filenames`

**Files:**
- Modify: `core/scanners/utils/filename_glob.py` (`GlobCountResult` dataclass + `count_pdfs_by_sigla` return)
- Test: `tests/test_glob_count_matched_filenames.py` (nuevo)

Para que `simple_factory` pueda derivar `per_file` correctamente sin recomputar el matching, exponemos los filenames en `GlobCountResult`. Spec §5.2 risk: si re-glob en simple_factory, el filtering por sigla se duplica y puede divergir.

- [ ] **Step 1: Write failing test**

```python
# tests/test_glob_count_matched_filenames.py
"""GlobCountResult.matched_filenames exposes the matching files."""
from pathlib import Path

import pytest

from core.scanners.utils.filename_glob import count_pdfs_by_sigla


def test_matched_filenames_contains_only_sigla_matches(tmp_path: Path):
    # 2 ART files + 1 IRL file
    (tmp_path / "2026-04-01_art_demo_empresa.pdf").write_bytes(b"%PDF\n%%EOF")
    (tmp_path / "2026-04-02_art_otro_empresa.pdf").write_bytes(b"%PDF\n%%EOF")
    (tmp_path / "2026-04-03_irl_x_empresa.pdf").write_bytes(b"%PDF\n%%EOF")

    result = count_pdfs_by_sigla(tmp_path, sigla="art")

    assert result.count == 2
    assert sorted(result.matched_filenames) == [
        "2026-04-01_art_demo_empresa.pdf",
        "2026-04-02_art_otro_empresa.pdf",
    ]


def test_matched_filenames_empty_when_no_match(tmp_path: Path):
    (tmp_path / "2026-04-03_irl_x_empresa.pdf").write_bytes(b"%PDF\n%%EOF")
    result = count_pdfs_by_sigla(tmp_path, sigla="art")
    assert result.matched_filenames == []


def test_matched_filenames_empty_when_folder_missing(tmp_path: Path):
    missing = tmp_path / "no_such_folder"
    result = count_pdfs_by_sigla(missing, sigla="art")
    assert result.matched_filenames == []
    assert "folder_missing" in result.flags
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/test_glob_count_matched_filenames.py -v
```

Expected: FAIL — `AttributeError: 'GlobCountResult' object has no attribute 'matched_filenames'`.

- [ ] **Step 3: Extend GlobCountResult + count_pdfs_by_sigla**

En `core/scanners/utils/filename_glob.py`:

```python
@dataclass(frozen=True)
class GlobCountResult:
    count: int
    method: str
    files_scanned: int
    flags: list[str] = field(default_factory=list)
    matched_filenames: list[str] = field(default_factory=list)  # ◀ NUEVO
```

En `count_pdfs_by_sigla`:

```python
# folder_missing branch
if not folder.exists():
    return GlobCountResult(
        count=0,
        method="filename_glob",
        files_scanned=0,
        flags=["folder_missing"],
        matched_filenames=[],  # ◀ NUEVO
    )
# happy path
pdfs = list(folder.rglob("*.pdf"))
matched = [p for p in pdfs if extract_sigla(p.name) == sigla]
# ... existing flag logic ...
return GlobCountResult(
    count=len(matched),
    method="filename_glob",
    files_scanned=len(pdfs),
    flags=flags,
    matched_filenames=[p.name for p in matched],  # ◀ NUEVO
)
```

- [ ] **Step 4: Verify pass**

```bash
pytest tests/test_glob_count_matched_filenames.py -v
pytest tests/ -q
```

- [ ] **Step 5: Commit**

```bash
git add core/scanners/utils/filename_glob.py tests/test_glob_count_matched_filenames.py
git commit -m "$(cat <<'EOF'
feat(filename-glob): GlobCountResult exposes matched_filenames

Aditive field para que simple_factory pueda derivar ScanResult.per_file
sin re-implementar el matching por sigla. Default empty list.
Spec §5.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 4: Populate `per_file` in `simple_factory` (régimen 1)

**Files:**
- Modify: `core/scanners/simple_factory.py:24-54` (`SimpleFilenameScanner.count`)
- Test: `tests/test_simple_factory_per_file.py` (nuevo)

Régimen 1: 1 PDF matchado = 1 doc. `per_file = {filename: 1 for filename in matched_filenames}`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_simple_factory_per_file.py
"""SimpleFilenameScanner devuelve per_file = {matched_filename: 1}."""
from pathlib import Path

from core.scanners.simple_factory import SimpleFilenameScanner


def test_simple_factory_per_file_only_matching_files(tmp_path: Path):
    (tmp_path / "2026-04-01_art_a_empresa.pdf").write_bytes(b"%PDF\n%%EOF")
    (tmp_path / "2026-04-02_art_b_empresa.pdf").write_bytes(b"%PDF\n%%EOF")
    (tmp_path / "2026-04-03_irl_x_empresa.pdf").write_bytes(b"%PDF\n%%EOF")
    (tmp_path / "ignore.txt").write_text("not a pdf")

    scanner = SimpleFilenameScanner(sigla="art")
    result = scanner.count(tmp_path)

    assert result.per_file == {
        "2026-04-01_art_a_empresa.pdf": 1,
        "2026-04-02_art_b_empresa.pdf": 1,
    }
    # Sanity: count and per_file en sync
    assert result.count == sum(result.per_file.values())


def test_simple_factory_per_file_empty_when_no_match(tmp_path: Path):
    """Folder con PDFs pero ninguno matchea sigla → per_file = {}."""
    (tmp_path / "irl_only.pdf").write_bytes(b"%PDF\n%%EOF")
    scanner = SimpleFilenameScanner(sigla="art")
    result = scanner.count(tmp_path)
    assert result.per_file == {}


def test_simple_factory_per_file_empty_when_folder_missing(tmp_path: Path):
    scanner = SimpleFilenameScanner(sigla="art")
    result = scanner.count(tmp_path / "no_such_folder")
    assert result.per_file == {}
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/test_simple_factory_per_file.py -v
```

Expected: FAIL — `result.per_file is None`.

- [ ] **Step 3: Modify SimpleFilenameScanner.count**

En `core/scanners/simple_factory.py:24-54`, agregar al return:

```python
return ScanResult(
    count=glob_result.count,
    confidence=confidence,
    method="filename_glob",
    breakdown=breakdown if breakdown else None,
    flags=flags,
    errors=[],
    duration_ms=duration_ms,
    files_scanned=glob_result.files_scanned,
    per_file={fn: 1 for fn in glob_result.matched_filenames},  # ◀ NUEVO
)
```

(Necesita `glob_result.matched_filenames` de Task 3.5.)

- [ ] **Step 4: Verify pass**

```bash
pytest tests/test_simple_factory_per_file.py -v
pytest tests/ -q
```

- [ ] **Step 5: Commit**

```bash
git add core/scanners/simple_factory.py tests/test_simple_factory_per_file.py
git commit -m "$(cat <<'EOF'
feat(scanners): simple_factory populates per_file (1 doc per matched PDF)

per_file = {filename: 1 for filename in matched_filenames}. Sólo los
PDFs que matchean la sigla — coincide con count. Spec §5.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 5: Populate `per_file` in `art_scanner` (compilation OCR)

**Files:**
- Modify: `core/scanners/art_scanner.py:38-76` (`count_ocr`) + `_fallback_from_base`
- Test: `tests/test_art_scanner_per_file.py` (nuevo)

ART scanner solo corre OCR cuando `len(pdfs) == 1 and flag_compilation_suspect(...)`. En ese caso `per_file = {pdfs[0].name: ocr.count}`. En path filename_glob hereda de simple_factory. En _fallback path preserva `base.per_file`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_art_scanner_per_file.py
"""ART scanner: per_file populated from compilation OCR result."""
from pathlib import Path
from unittest.mock import patch

import pytest

from core.scanners.art_scanner import ArtScanner
from core.scanners.cancellation import CancellationToken


def test_art_per_file_filename_glob_path_multi_pdf(tmp_path: Path):
    """≥2 PDFs → no compilation, filename_glob path. per_file de simple_factory."""
    (tmp_path / "2026-04-01_art_a_empresa.pdf").write_bytes(b"%PDF\n%%EOF")
    (tmp_path / "2026-04-02_art_b_empresa.pdf").write_bytes(b"%PDF\n%%EOF")
    scanner = ArtScanner(sigla="art")
    result = scanner.count_ocr(tmp_path, cancel=CancellationToken.NEVER)
    # Heredado de simple_factory (Task 4)
    assert result.per_file == {
        "2026-04-01_art_a_empresa.pdf": 1,
        "2026-04-02_art_b_empresa.pdf": 1,
    }


def test_art_per_file_compilation_ocr_path(tmp_path: Path):
    """1 PDF + flag_compilation_suspect → OCR; per_file = {filename: ocr.count}."""
    pdf = tmp_path / "2026-04-15_art_compilacion_empresa.pdf"
    pdf.write_bytes(b"%PDF\n%%EOF")

    with patch(
        "core.scanners.art_scanner.flag_compilation_suspect",
        return_value=True,
    ), patch("core.scanners.art_scanner.count_paginations") as mock_ocr:
        mock_ocr.return_value.count = 24
        scanner = ArtScanner(sigla="art")
        result = scanner.count_ocr(tmp_path, cancel=CancellationToken.NEVER)

    assert result.method == "corner_count"
    assert result.count == 24
    assert result.per_file == {"2026-04-15_art_compilacion_empresa.pdf": 24}


def test_art_per_file_fallback_preserves_base(tmp_path: Path):
    """OCR fail path → fallback retorna per_file de la base (filename_glob)."""
    pdf = tmp_path / "2026-04-15_art_compilacion_empresa.pdf"
    pdf.write_bytes(b"%PDF\n%%EOF")

    with patch(
        "core.scanners.art_scanner.flag_compilation_suspect",
        return_value=True,
    ), patch(
        "core.scanners.art_scanner.count_paginations",
        side_effect=RuntimeError("OCR exploded"),
    ):
        scanner = ArtScanner(sigla="art")
        result = scanner.count_ocr(tmp_path, cancel=CancellationToken.NEVER)

    # Base sería simple_factory(folder) → per_file={pdf.name: 1}
    assert result.per_file == {"2026-04-15_art_compilacion_empresa.pdf": 1}
```

(Si `ArtScanner()` no acepta `sigla` arg, ajustar al constructor real — confirmar con `grep "class ArtScanner" core/scanners/art_scanner.py`. Si `count_paginations` está importado desde otro módulo, ajustar el patch path.)

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/test_art_scanner_per_file.py -v
```

- [ ] **Step 3: Modify art_scanner**

En `count_ocr` (líneas 67-76 aprox.) — el ScanResult del path OCR:

```python
return ScanResult(
    count=ocr.count,
    confidence=ConfidenceLevel.HIGH,
    method="corner_count",
    breakdown=None,
    flags=list(base.flags),
    errors=[],
    duration_ms=duration_ms,
    files_scanned=1,
    per_file={pdfs[0].name: ocr.count},  # ◀ NUEVO
)
```

En `_fallback_from_base` (líneas 84-94):

```python
def _fallback_from_base(self, base: ScanResult, *, error: str) -> ScanResult:
    return ScanResult(
        count=base.count,
        confidence=base.confidence,
        method=base.method,
        breakdown=base.breakdown,
        flags=[*base.flags, "ocr_failed"],
        errors=[*base.errors, error],
        duration_ms=base.duration_ms,
        files_scanned=base.files_scanned,
        per_file=base.per_file,  # ◀ NUEVO
    )
```

- [ ] **Step 4: Verify pass**

```bash
pytest tests/test_art_scanner_per_file.py -v
pytest tests/ -q
```

- [ ] **Step 5: Commit**

```bash
git add core/scanners/art_scanner.py tests/test_art_scanner_per_file.py
git commit -m "$(cat <<'EOF'
feat(scanners): art_scanner populates per_file in compilation path

Compilation path (1 PDF + suspect flag): per_file={pdfs[0].name: ocr.count}.
Filename_glob path hereda de simple_factory. Fallback preserva per_file
de base. Spec §5.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 6: Populate `per_file` in `charla_scanner`

**Files:**
- Modify: `core/scanners/charla_scanner.py:36-89`
- Test: `tests/test_charla_scanner_per_file.py` (nuevo)

Estructura idéntica a ART (single-PDF compilation, line 39 en count_ocr). Función OCR es `count_paginations` o `count_charla` — verificar con grep.

- [ ] **Step 1: Inspect**

```bash
grep -n "count_paginations\|count_charla\|count_form_codes" core/scanners/charla_scanner.py
```

- [ ] **Step 2: Write failing tests** (analógo Task 5; reusar el patrón con `sigla="charla"`)

- [ ] **Step 3: Modify charla_scanner.count_ocr + _fallback_from_base** (idéntico Task 5)

- [ ] **Step 4: Verify pass + Commit**

```bash
pytest tests/test_charla_scanner_per_file.py -v
pytest tests/ -q

git add core/scanners/charla_scanner.py tests/test_charla_scanner_per_file.py
git commit -m "$(cat <<'EOF'
feat(scanners): charla_scanner populates per_file in compilation path

Idem ART. per_file={pdfs[0].name: ocr.count} en path OCR. Spec §5.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 7: Populate `per_file` in `_header_detect_base`

**Files:**
- Modify: `core/scanners/_header_detect_base.py:41-79` (`HeaderDetectScanner.count_ocr`) + `_fallback_from_base`
- Test: `tests/test_header_detect_per_file.py` (nuevo)

Verificado: HeaderDetectScanner es single-PDF compilation (líneas 50-52: `is_compilation = len(pdfs) == 1 and flag_compilation_suspect(...)`). Función OCR: `count_form_codes(pdfs[0], sigla_code=self.sigla_code)`. Misma estructura que ART/charla.

- [ ] **Step 1: Inspect constructor + sigla_code attribute**

```bash
grep -n "class HeaderDetectScanner\|self.sigla_code\|sigla_code:" core/scanners/_header_detect_base.py
```

- [ ] **Step 2: Write failing test** (idem Task 5/6, mockeando `count_form_codes` con `pdfs[0].name` y un count específico)

- [ ] **Step 3: Modify count_ocr (línea 71-79 return) + _fallback_from_base** — agregar `per_file={pdfs[0].name: ocr.count}` al ScanResult OCR + `per_file=base.per_file` al fallback.

- [ ] **Step 4: Verify pass + commit**

```bash
pytest tests/test_header_detect_per_file.py -v
pytest tests/ -q

git add core/scanners/_header_detect_base.py tests/test_header_detect_per_file.py
git commit -m "$(cat <<'EOF'
feat(scanners): _header_detect_base populates per_file

Per-file attribution para todos los scanners derivados (irl, odi, dif_pts,
chintegral). Single-PDF compilation: per_file={pdfs[0].name: ocr.count}.
Fallback preserva base. Spec §5.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 8: `compute_cell_count` pure function

**Files:**
- Modify: `api/state.py` (agregar función módulo-level)
- Test: `tests/test_compute_cell_count.py` (nuevo)

Función pura espejo del JS de Task 12. Ver spec §6.2.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_compute_cell_count.py
"""Pure function compute_cell_count(cell) — FASE 4 §6.2 precedence."""
from api.state import compute_cell_count


def test_user_override_wins():
    cell = {
        "user_override": 99,
        "per_file": {"a.pdf": 5},
        "per_file_overrides": {"a.pdf": 3},
        "ocr_count": 10,
        "filename_count": 2,
    }
    assert compute_cell_count(cell) == 99


def test_per_file_overrides_compose_with_per_file():
    cell = {
        "user_override": None,
        "per_file": {"a.pdf": 5, "b.pdf": 3},
        "per_file_overrides": {"a.pdf": 7},
        "ocr_count": 99,
    }
    assert compute_cell_count(cell) == 10  # 7 (override) + 3 (per_file)


def test_per_file_only_no_overrides():
    cell = {
        "user_override": None,
        "per_file": {"a.pdf": 24, "b.pdf": 1},
        "per_file_overrides": {},
        "ocr_count": 99,
    }
    assert compute_cell_count(cell) == 25


def test_per_file_overrides_can_add_files_not_in_per_file():
    cell = {
        "user_override": None,
        "per_file": {"a.pdf": 5},
        "per_file_overrides": {"b.pdf": 3},
    }
    assert compute_cell_count(cell) == 8


def test_falls_back_to_ocr_count():
    cell = {
        "user_override": None,
        "per_file": None,
        "per_file_overrides": None,
        "ocr_count": 24,
        "filename_count": 5,
    }
    assert compute_cell_count(cell) == 24


def test_falls_back_to_filename_count_when_no_ocr():
    cell = {
        "user_override": None,
        "per_file": None,
        "per_file_overrides": None,
        "ocr_count": None,
        "filename_count": 5,
    }
    assert compute_cell_count(cell) == 5


def test_returns_zero_when_nothing():
    cell = {"user_override": None, "ocr_count": None, "filename_count": None}
    assert compute_cell_count(cell) == 0
```

- [ ] **Step 2: Run, verify failure**

Expected: FAIL — `cannot import name 'compute_cell_count'`.

- [ ] **Step 3: Add to api/state.py**

Insertar como función módulo-level (no método) ANTES de la clase `SessionManager`:

```python
def compute_cell_count(cell: dict) -> int:
    """Cell count derivation per FASE 4 §6.2 precedence.

    1. user_override (FASE 2 escape hatch) wins absolutely.
    2. per_file_overrides ∪ per_file → suma derivada.
    3. Fallback: ocr_count or filename_count or 0.
    """
    if cell.get("user_override") is not None:
        return cell["user_override"]

    per_file = cell.get("per_file") or {}
    per_file_overrides = cell.get("per_file_overrides") or {}
    if per_file or per_file_overrides:
        all_files = set(per_file) | set(per_file_overrides)
        return sum(
            per_file_overrides.get(f, per_file.get(f, 0))
            for f in all_files
        )

    return cell.get("ocr_count") or cell.get("filename_count") or 0
```

- [ ] **Step 4: Verify pass**

```bash
pytest tests/test_compute_cell_count.py -v
```

- [ ] **Step 5: Commit**

```bash
git add api/state.py tests/test_compute_cell_count.py
git commit -m "$(cat <<'EOF'
feat(api): compute_cell_count pure function with FASE 4 precedence

Jerarquía: user_override > per_file (∪ per_file_overrides) > ocr_count >
filename_count > 0. Función pura módulo-level. Espejo en JS en Task 12.
Spec §6.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 8.5: `apply_filename_result` and `apply_ocr_result` persist `per_file`

**Files:**
- Modify: `api/state.py` (`apply_filename_result:93-114`, `apply_ocr_result:116-142`)
- Test: `tests/test_apply_persists_per_file.py` (nuevo)

Spec §5.2. TDD: test failing first.

- [ ] **Step 1: Write failing test**

```python
# tests/test_apply_persists_per_file.py
"""apply_filename_result and apply_ocr_result persist per_file from ScanResult."""
import pytest

from api.state import SessionManager, update_session_state
from core.scanners.base import ConfidenceLevel, ScanResult


@pytest.fixture
def mgr_session(tmp_path):
    from api.db import get_db_connection  # ajustar al patrón real (Task 2 lo verificó)
    from core.db.migrations import init_schema
    import sqlite3
    conn = sqlite3.connect(tmp_path / "t.db")
    init_schema(conn)
    mgr = SessionManager(conn)
    sid = mgr.open_session(month_root=str(tmp_path), year=2026, month=4)
    yield mgr, sid
    conn.close()


def test_apply_filename_result_persists_per_file(mgr_session):
    mgr, sid = mgr_session
    result = ScanResult(
        count=2,
        confidence=ConfidenceLevel.HIGH,
        method="filename_glob",
        breakdown=None,
        flags=[],
        errors=[],
        duration_ms=10,
        files_scanned=2,
        per_file={"a.pdf": 1, "b.pdf": 1},
    )
    mgr.apply_filename_result(sid, "HRB", "art", result)

    state, _ = mgr._load_and_migrate(sid)
    cell = state["cells"]["HRB"]["art"]
    assert cell["per_file"] == {"a.pdf": 1, "b.pdf": 1}
    assert cell["per_file_overrides"] == {}  # default initialized
    assert cell["manual_entry"] is False  # default initialized


def test_apply_ocr_result_persists_per_file(mgr_session):
    mgr, sid = mgr_session
    # First seed a filename result so the cell exists
    base = ScanResult(
        count=1, confidence=ConfidenceLevel.HIGH, method="filename_glob",
        breakdown=None, flags=[], errors=[], duration_ms=5, files_scanned=1,
        per_file={"compilacion.pdf": 1},
    )
    mgr.apply_filename_result(sid, "HRB", "odi", base)
    # Now apply OCR result with refined per_file
    ocr_result = ScanResult(
        count=24, confidence=ConfidenceLevel.HIGH, method="header_detect",
        breakdown=None, flags=[], errors=[], duration_ms=8000, files_scanned=1,
        per_file={"compilacion.pdf": 24},
    )
    mgr.apply_ocr_result(sid, "HRB", "odi", ocr_result)

    state, _ = mgr._load_and_migrate(sid)
    cell = state["cells"]["HRB"]["odi"]
    assert cell["per_file"] == {"compilacion.pdf": 24}
```

(Si `mgr.open_session(...)` tiene otra signature, ajustar — verificar con `grep "def open_session" api/state.py`. El import de `get_db_connection` puede no aplicar — usar `sqlite3.connect` + `init_schema` directo es más portátil.)

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/test_apply_persists_per_file.py -v
```

Expected: FAIL — `cell["per_file"]` no existe (apply_filename_result no lo persiste todavía).

- [ ] **Step 3: Modify apply_filename_result + apply_ocr_result**

En `api/state.py:93-114` (`apply_filename_result`), agregar después de los `setdefault` existentes:

```python
cell["per_file"] = result.per_file
cell.setdefault("per_file_overrides", {})
cell.setdefault("manual_entry", False)
```

Idem en `apply_ocr_result:116-142`.

(`apply_cell_result:169-177` es wrapper sobre apply_filename_result — sin cambio.)

- [ ] **Step 4: Verify pass**

```bash
pytest tests/test_apply_persists_per_file.py -v
pytest tests/ -q
```

- [ ] **Step 5: Commit**

```bash
git add api/state.py tests/test_apply_persists_per_file.py
git commit -m "$(cat <<'EOF'
feat(state): apply_filename_result and apply_ocr_result persist per_file

ScanResult.per_file (Task 3) ahora se escribe al cell state nested
(state["cells"][hospital][sigla]). setdefault para per_file_overrides y
manual_entry asegura backward-compat con cells de sesiones FASE 1/2/3.
apply_cell_result es wrapper deprecated; delega en apply_filename_result.
Spec §5.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 9: `apply_per_file_override` method + PATCH endpoint

**Files:**
- Modify: `api/state.py` (nuevo método en SessionManager)
- Modify: `api/routes/sessions.py` (nuevo endpoint)
- Test: `tests/test_apply_per_file_override.py` (nuevo)
- Test: `tests/test_per_file_override_endpoint.py` (nuevo)

Spec §5.2 + §7.2. Persistir override + endpoint REST.

- [ ] **Step 1: Write failing test for the SessionManager method**

```python
# tests/test_apply_per_file_override.py
"""SessionManager.apply_per_file_override persiste override y refleja count."""
import sqlite3

import pytest

from api.state import SessionManager, compute_cell_count
from core.db.migrations import init_schema


@pytest.fixture
def mgr_with_seeded_cell(tmp_path):
    conn = sqlite3.connect(tmp_path / "t.db")
    init_schema(conn)
    mgr = SessionManager(conn)
    sid = mgr.open_session(month_root=str(tmp_path), year=2026, month=4)
    # Seed cell con per_file via apply_filename_result
    from core.scanners.base import ConfidenceLevel, ScanResult
    base = ScanResult(
        count=2, confidence=ConfidenceLevel.HIGH, method="filename_glob",
        breakdown=None, flags=[], errors=[], duration_ms=5, files_scanned=2,
        per_file={"a.pdf": 5, "b.pdf": 3},
    )
    # Hack: apply_filename_result espera count match files matched, no problema en test
    mgr.apply_filename_result(sid, "HRB", "odi", base)
    yield mgr, sid
    conn.close()


def test_apply_per_file_override_persists(mgr_with_seeded_cell):
    mgr, sid = mgr_with_seeded_cell
    mgr.apply_per_file_override(sid, "HRB", "odi", "a.pdf", 10)

    state, _ = mgr._load_and_migrate(sid)
    cell = state["cells"]["HRB"]["odi"]
    assert cell["per_file_overrides"]["a.pdf"] == 10
    # Cell-count: 10 (override) + 3 (b.pdf) = 13
    assert compute_cell_count(cell) == 13


def test_apply_per_file_override_zero_is_valid(mgr_with_seeded_cell):
    mgr, sid = mgr_with_seeded_cell
    mgr.apply_per_file_override(sid, "HRB", "odi", "a.pdf", 0)
    state, _ = mgr._load_and_migrate(sid)
    cell = state["cells"]["HRB"]["odi"]
    assert cell["per_file_overrides"]["a.pdf"] == 0
    assert compute_cell_count(cell) == 0 + 3


def test_apply_per_file_override_unknown_cell_raises(mgr_with_seeded_cell):
    mgr, sid = mgr_with_seeded_cell
    with pytest.raises((KeyError, ValueError)):
        mgr.apply_per_file_override(sid, "HXX", "yyy", "any.pdf", 5)
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/test_apply_per_file_override.py -v
```

Expected: FAIL — `apply_per_file_override` no existe.

- [ ] **Step 3: Add method to SessionManager**

En `api/state.py`, dentro de `class SessionManager`:

```python
def apply_per_file_override(
    self,
    session_id: str,
    hospital: str,
    sigla: str,
    filename: str,
    count: int,
) -> None:
    """Persist per-file count override. Spec §5.2.

    Raises:
        KeyError: if (hospital, sigla) cell is not in session state.
    """
    state, _ = self._load_and_migrate(session_id)
    cells = state.setdefault("cells", {})
    if hospital not in cells or sigla not in cells.get(hospital, {}):
        raise KeyError(f"Cell ({hospital}, {sigla}) not in session {session_id}")
    cell = cells[hospital][sigla]
    cell.setdefault("per_file_overrides", {})
    cell["per_file_overrides"][filename] = count
    update_session_state(self._conn, session_id, state_json=json.dumps(state))
```

- [ ] **Step 4: Verify pass**

```bash
pytest tests/test_apply_per_file_override.py -v
pytest tests/ -q
```

- [ ] **Step 5: Commit method**

```bash
git add api/state.py tests/test_apply_per_file_override.py
git commit -m "$(cat <<'EOF'
feat(state): apply_per_file_override SessionManager method

Persiste cell.per_file_overrides[filename] = count en state nested.
KeyError si la cell no existe. Override = 0 válido (descartar archivo).
Spec §5.2 + §7.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 6: Write failing test for endpoint**

```python
# tests/test_per_file_override_endpoint.py
"""PATCH /sessions/{id}/cells/{h}/{s}/files/{f}/override endpoint."""
from fastapi.testclient import TestClient
import pytest

from api.main import app


@pytest.fixture
def client_with_seeded(tmp_path, monkeypatch):
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "test.db"))
    client = TestClient(app)
    r = client.post("/sessions", json={"month_root": str(tmp_path)})
    sid = r.json()["session_id"]
    # Seed via SessionManager + apply_filename_result
    from api.routes.sessions import get_manager
    mgr = get_manager()
    from core.scanners.base import ConfidenceLevel, ScanResult
    mgr.apply_filename_result(sid, "HRB", "odi", ScanResult(
        count=1, confidence=ConfidenceLevel.HIGH, method="filename_glob",
        breakdown=None, flags=[], errors=[], duration_ms=5, files_scanned=1,
        per_file={"a.pdf": 5},
    ))
    yield client, sid


def test_patch_per_file_override_writes_value(client_with_seeded):
    client, sid = client_with_seeded
    r = client.patch(
        f"/sessions/{sid}/cells/HRB/odi/files/a.pdf/override",
        json={"count": 10},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["filename"] == "a.pdf"
    assert body["count"] == 10
    assert body["new_cell_count"] == 10


def test_patch_per_file_override_404_unknown_cell(client_with_seeded):
    client, sid = client_with_seeded
    r = client.patch(
        f"/sessions/{sid}/cells/HXX/yyy/files/whatever.pdf/override",
        json={"count": 5},
    )
    assert r.status_code == 404
```

(Si `OVERSEER_DB_PATH` no es la env var de configuración, ajustar — verificar con `grep "DB_PATH\|overseer.db" api/`.)

- [ ] **Step 7: Run, verify failure**

```bash
pytest tests/test_per_file_override_endpoint.py -v
```

- [ ] **Step 8: Add the endpoint**

En `api/routes/sessions.py`, junto a los otros override endpoints (`PATCH override` está en línea 252):

```python
from pydantic import BaseModel  # ya importado probablemente


class PerFileOverrideRequest(BaseModel):
    count: int


@router.patch(
    "/sessions/{session_id}/cells/{hospital}/{sigla}/files/{filename:path}/override"
)
def patch_per_file_override(
    session_id: str,
    hospital: str,
    sigla: str,
    filename: str,
    body: PerFileOverrideRequest,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Persist per-file count override. Spec §5.2 + §7.2."""
    try:
        mgr.apply_per_file_override(
            session_id, hospital, sigla, filename, body.count
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    state, _ = mgr._load_and_migrate(session_id)
    cell = state["cells"][hospital][sigla]
    return {
        "filename": filename,
        "count": body.count,
        "new_cell_count": compute_cell_count(cell),
    }
```

(`{filename:path}` permite filenames con caracteres especiales. Ajustar si la convención del proyecto es distinta.)

Importar `compute_cell_count`:

```python
from api.state import compute_cell_count, get_manager  # si no lo está
```

- [ ] **Step 9: Verify pass**

```bash
pytest tests/test_per_file_override_endpoint.py -v
pytest tests/ -q
```

- [ ] **Step 10: Commit endpoint**

```bash
git add api/routes/sessions.py tests/test_per_file_override_endpoint.py
git commit -m "$(cat <<'EOF'
feat(api): PATCH /files/{filename}/override endpoint

Persiste per-file count override y devuelve new_cell_count derivado de
compute_cell_count. 404 si la cell no existe en la sesión. Spec §5.2 + §7.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 10: Extend `/files` endpoint to expose per_file + overrides + origin

**Files:**
- Modify: `api/routes/sessions.py:281-317` (`get_cell_files`)
- Test: `tests/test_cell_files_endpoint.py` (nuevo)

Spec §5.2.

- [ ] **Step 1: Write failing test**

```python
# tests/test_cell_files_endpoint.py
"""GET /sessions/{id}/cells/{h}/{s}/files returns per_file + overrides + origin."""
from fastapi.testclient import TestClient
import pytest

from api.main import app


@pytest.fixture
def client_with_pdfs(tmp_path, monkeypatch):
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "test.db"))
    folder = tmp_path / "HRB" / "3.-ODI Visitas"
    folder.mkdir(parents=True)
    (folder / "a.pdf").write_bytes(b"%PDF\n%%EOF")
    (folder / "b.pdf").write_bytes(b"%PDF\n%%EOF")
    client = TestClient(app)
    r = client.post("/sessions", json={"month_root": str(tmp_path)})
    sid = r.json()["session_id"]
    # Seed cell via SessionManager
    from api.routes.sessions import get_manager
    from core.scanners.base import ConfidenceLevel, ScanResult
    mgr = get_manager()
    mgr.apply_ocr_result(sid, "HRB", "odi", ScanResult(
        count=8, confidence=ConfidenceLevel.HIGH, method="header_detect",
        breakdown=None, flags=[], errors=[], duration_ms=8000, files_scanned=1,
        per_file={"a.pdf": 5, "b.pdf": 3},
    ))
    mgr.apply_per_file_override(sid, "HRB", "odi", "a.pdf", 7)
    yield client, sid


def test_get_cell_files_includes_per_file_and_origin(client_with_pdfs):
    client, sid = client_with_pdfs
    r = client.get(f"/sessions/{sid}/cells/HRB/odi/files")
    assert r.status_code == 200
    files = r.json()
    by_name = {f["name"]: f for f in files}

    # a.pdf has per_file=5 and override=7 → effective=7, origin=manual
    assert by_name["a.pdf"]["per_file_count"] == 5
    assert by_name["a.pdf"]["override_count"] == 7
    assert by_name["a.pdf"]["effective_count"] == 7
    assert by_name["a.pdf"]["origin"] == "manual"

    # b.pdf has per_file=3, no override → effective=3, origin=OCR
    assert by_name["b.pdf"]["per_file_count"] == 3
    assert by_name["b.pdf"]["override_count"] is None
    assert by_name["b.pdf"]["effective_count"] == 3
    assert by_name["b.pdf"]["origin"] == "OCR"
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/test_cell_files_endpoint.py -v
```

Expected: FAIL — campos nuevos no existen en respuesta.

- [ ] **Step 3: Modify the endpoint**

En `api/routes/sessions.py:281-317` (función `get_cell_files`), agregar lookup del cell antes del loop:

```python
state, _ = mgr._load_and_migrate(session_id)
cell = state.get("cells", {}).get(hospital, {}).get(sigla, {})
per_file = cell.get("per_file") or {}
per_file_overrides = cell.get("per_file_overrides") or {}
cell_method = cell.get("method") or "filename_glob"

def _origin_for(filename: str, override: int | None) -> str:
    """OriginChip variant: manual if override, OCR if scanner ran, else R1."""
    if override is not None:
        return "manual"
    if cell_method in ("header_detect", "corner_count", "page_count_pure"):
        return "OCR"
    return "R1"
```

Y modificar el `out.append({...})`:

```python
override = per_file_overrides.get(pdf.name)
inferred = per_file.get(pdf.name)
out.append({
    "name": pdf.name,
    "subfolder": subfolder,
    "page_count": page_count,
    "suspect": page_count >= 10,
    "per_file_count": inferred,
    "override_count": override,
    "effective_count": override if override is not None else (inferred if inferred is not None else 1),
    "origin": _origin_for(pdf.name, override),
})
```

(`mgr` ya está disponible si la firma de `get_cell_files` ya lo recibe via Depends. Si no, agregar `mgr: SessionManager = Depends(get_manager)`.)

- [ ] **Step 4: Verify pass**

```bash
pytest tests/test_cell_files_endpoint.py -v
pytest tests/ -q
```

- [ ] **Step 5: Commit**

```bash
git add api/routes/sessions.py tests/test_cell_files_endpoint.py
git commit -m "$(cat <<'EOF'
feat(api): /files endpoint returns per_file + overrides + origin chip variant

Cada file row incluye per_file_count (del scanner), override_count (manual),
effective_count (final por archivo), y origin ('OCR'|'R1'|'manual') que el
frontend mapea a OriginChip. Spec §5.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Chunk 2: History endpoint + cellCount JS

### Task 11: GET `/sessions/{id}/history?n=12` endpoint

**Files:**
- Create: `api/routes/history.py`
- Modify: `api/main.py` (registrar router)
- Test: `tests/test_history_endpoint.py` (nuevo)

Spec §5.2 + §6.4. DI vía `get_manager` para acceder a `mgr._conn`.

- [ ] **Step 1: Write failing test**

```python
# tests/test_history_endpoint.py
"""GET /sessions/{id}/history?n=12 endpoint."""
from fastapi.testclient import TestClient
import pytest

from api.main import app
from core.db.historical_repo import upsert_count


@pytest.fixture
def client_with_history(tmp_path, monkeypatch):
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "test.db"))
    client = TestClient(app)
    r = client.post("/sessions", json={"month_root": str(tmp_path)})
    sid = r.json()["session_id"]

    # Seed via mgr._conn
    from api.routes.sessions import get_manager
    mgr = get_manager()
    for offset in range(12):
        # 2025-06 → 2026-05
        total = 2025 * 12 + 6 + offset - 1
        year, month = divmod(total, 12)
        month += 1
        upsert_count(
            mgr._conn,
            year=year,
            month=month,
            hospital="HPV",
            sigla="reunion",
            count=10 + offset,
            confidence="high",
            method="filename_glob",
        )
    mgr._conn.commit()
    yield client, sid


def test_history_endpoint_returns_n_months(client_with_history):
    client, sid = client_with_history
    r = client.get(f"/sessions/{sid}/history?n=12")
    assert r.status_code == 200
    data = r.json()
    assert "HPV|reunion" in data
    series = data["HPV|reunion"]
    assert len(series) == 12
    assert series[0]["year"] == 2025
    assert series[0]["month"] == 6
    assert series[-1]["year"] == 2026
    assert series[-1]["month"] == 5
    assert series[-1]["count"] == 21


def test_history_endpoint_default_n_is_12(client_with_history):
    client, sid = client_with_history
    r1 = client.get(f"/sessions/{sid}/history")
    r2 = client.get(f"/sessions/{sid}/history?n=12")
    assert r1.json() == r2.json()


def test_history_endpoint_n_can_be_smaller(client_with_history):
    client, sid = client_with_history
    r = client.get(f"/sessions/{sid}/history?n=3")
    series = r.json()["HPV|reunion"]
    assert len(series) == 3
```

- [ ] **Step 2: Run, verify failure**

Expected: FAIL — endpoint no existe (404).

- [ ] **Step 3: Create api/routes/history.py**

```python
"""History endpoint for FASE 4 multi-month view. Spec §5.2 + §6.4."""
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, Query

from api.routes.sessions import get_manager
from api.state import SessionManager
from core.db.historical_repo import query_range


router = APIRouter()


@router.get("/sessions/{session_id}/history")
def get_history(
    session_id: str,
    n: int = Query(default=12, ge=1, le=48),
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Returns N months of historical_counts grouped by (hospital, sigla).

    Response shape:
        {"<hospital>|<sigla>": [{"year": int, "month": int, "count": int,
        "confidence": str, "method": str}, ...], ...}
    """
    # Window of N months ending in current (year, month). Use 0-indexed
    # months internally (jan=0, dec=11) so divmod is clean.
    today = datetime.utcnow()
    to_year, to_month = today.year, today.month
    to_idx = to_year * 12 + (to_month - 1)       # 0-indexed: jan 2026 → 24312
    from_idx = to_idx - (n - 1)                  # n=12 → 11 months back
    from_year, from_month_zero = divmod(from_idx, 12)
    from_month = from_month_zero + 1             # back to 1-indexed
    assert 1 <= from_month <= 12 and 1 <= to_month <= 12, "month out of range"

    rows = query_range(
        mgr._conn,
        from_year=from_year,
        from_month=from_month,
        to_year=to_year,
        to_month=to_month,
    )

    grouped: dict[str, list] = defaultdict(list)
    for row in rows:
        # Adjust to dict-or-Row access depending on query_range return type
        get = (lambda k: row[k]) if hasattr(row, "__getitem__") else (lambda k: getattr(row, k))
        key = f"{get('hospital')}|{get('sigla')}"
        grouped[key].append({
            "year": get("year"),
            "month": get("month"),
            "count": get("count"),
            "confidence": get("confidence"),
            "method": get("method"),
        })
    return dict(grouped)
```

(Si `query_range` retorna sqlite3.Row, el access `row["count"]` funciona; si retorna dataclass, `getattr` funciona. La línea `get = ...` es defensiva — verificar el tipo real con `grep "return\|yield" core/db/historical_repo.py | head -5` y simplificar.)

- [ ] **Step 4: Register router en api/main.py**

```bash
grep -n "include_router" api/main.py
```

Agregar junto a los otros:

```python
from api.routes import history

app.include_router(history.router)
```

- [ ] **Step 5: Verify pass**

```bash
pytest tests/test_history_endpoint.py -v
pytest tests/ -q
```

- [ ] **Step 6: Commit**

```bash
git add api/routes/history.py api/main.py tests/test_history_endpoint.py
git commit -m "$(cat <<'EOF'
feat(api): GET /sessions/{id}/history?n=12 endpoint

Devuelve N meses de historical_counts agrupado por (hospital, sigla).
Delega en historical_repo.query_range — sin SQL nuevo. N default 12,
clamped [1, 48]. DI via get_manager (compartido con sessions router).
Spec §5.2 + §6.4.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 12: Frontend `cellCount.js` mirror + cross-language fixtures

**Files:**
- Create: `frontend/src/lib/cellCount.js`
- Create: `tests/fixtures/cell_count_cases.json`
- Create: `tests/test_cell_count_cross_language.py`

Spec §5.1 + §8.4.

- [ ] **Step 1: Create the shared fixture**

`tests/fixtures/cell_count_cases.json`:

```json
[
  {
    "name": "user_override_wins",
    "cell": {
      "user_override": 99,
      "per_file": {"a.pdf": 5},
      "per_file_overrides": {"a.pdf": 3},
      "ocr_count": 10,
      "filename_count": 2
    },
    "expected": 99
  },
  {
    "name": "per_file_overrides_compose",
    "cell": {
      "user_override": null,
      "per_file": {"a.pdf": 5, "b.pdf": 3},
      "per_file_overrides": {"a.pdf": 7},
      "ocr_count": 99
    },
    "expected": 10
  },
  {
    "name": "per_file_only",
    "cell": {
      "user_override": null,
      "per_file": {"a.pdf": 24, "b.pdf": 1},
      "per_file_overrides": {},
      "ocr_count": 99
    },
    "expected": 25
  },
  {
    "name": "override_adds_unknown_file",
    "cell": {
      "user_override": null,
      "per_file": {"a.pdf": 5},
      "per_file_overrides": {"b.pdf": 3}
    },
    "expected": 8
  },
  {
    "name": "fallback_ocr_count",
    "cell": {
      "user_override": null,
      "per_file": null,
      "per_file_overrides": null,
      "ocr_count": 24,
      "filename_count": 5
    },
    "expected": 24
  },
  {
    "name": "fallback_filename_count",
    "cell": {
      "user_override": null,
      "per_file": null,
      "per_file_overrides": null,
      "ocr_count": null,
      "filename_count": 5
    },
    "expected": 5
  },
  {
    "name": "all_null_returns_zero",
    "cell": {
      "user_override": null,
      "ocr_count": null,
      "filename_count": null
    },
    "expected": 0
  }
]
```

- [ ] **Step 2: Create the cross-language test**

```python
# tests/test_cell_count_cross_language.py
"""Validate compute_cell_count Python against shared fixtures.
Frontend (cellCount.js) is asserted against the same fixtures during smoke."""
import json
from pathlib import Path

import pytest

from api.state import compute_cell_count


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "cell_count_cases.json"


@pytest.mark.parametrize("case", json.loads(FIXTURE_PATH.read_text(encoding="utf-8")))
def test_compute_cell_count_against_shared_fixture(case):
    assert compute_cell_count(case["cell"]) == case["expected"], (
        f"case={case['name']}"
    )
```

- [ ] **Step 3: Run, verify pass**

```bash
pytest tests/test_cell_count_cross_language.py -v
```

Expected: 7 PASS (Task 8 ya tiene compute_cell_count).

- [ ] **Step 4: Create the JS mirror**

`frontend/src/lib/cellCount.js`:

```js
// Mirror of api/state.py:compute_cell_count. Mantener en sync — ambas funciones
// deben producir el mismo número para el mismo cell. Cross-language parity
// validada por tests/fixtures/cell_count_cases.json (Python tests + smoke).
// Spec FASE 4 §6.2.

export function computeCellCount(cell) {
  if (cell?.user_override != null) return cell.user_override;

  const perFile = cell?.per_file ?? {};
  const perFileOverrides = cell?.per_file_overrides ?? {};
  const hasPerFile = perFile && Object.keys(perFile).length > 0;
  const hasOverrides = perFileOverrides && Object.keys(perFileOverrides).length > 0;

  if (hasPerFile || hasOverrides) {
    const allFiles = new Set([
      ...Object.keys(perFile ?? {}),
      ...Object.keys(perFileOverrides ?? {}),
    ]);
    let sum = 0;
    for (const f of allFiles) {
      const val = perFileOverrides?.[f] ?? perFile?.[f] ?? 0;
      sum += val;
    }
    return sum;
  }

  return cell?.ocr_count ?? cell?.filename_count ?? 0;
}
```

- [ ] **Step 5: Verify build**

```bash
cd frontend && npm run build
```

Expected: green.

- [ ] **Step 6: Commit**

```bash
cd a:/PROJECTS/PDFoverseer
git add tests/fixtures/cell_count_cases.json tests/test_cell_count_cross_language.py frontend/src/lib/cellCount.js
git commit -m "$(cat <<'EOF'
feat(lib): cellCount.js mirror + cross-language fixtures

Shared fixture set en tests/fixtures/cell_count_cases.json validado por
pytest contra api/state.py.compute_cell_count. La función JS computeCellCount
en frontend/src/lib/cellCount.js espeja la lógica 1:1 — paridad verificada
en smoke manual al final del plan. Spec §5.1 + §8.4.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Chunk 3: Frontend new components

### Task 13: `Sparkline` component

**Files:**
- Create: `frontend/src/components/Sparkline.jsx`

Spec §5.1: ~50 LoC SVG, props `data: number[]`, `tone?: "neutral"|"warn"|"muted"`. Tonto. Usa tokens `po-suspect` para warn (amber), no `po-warning` (no existe).

- [ ] **Step 1: Create the component**

`frontend/src/components/Sparkline.jsx`:

```jsx
const TONE_STROKE = {
  neutral: "stroke-po-accent",
  warn:    "stroke-po-suspect",   // amber, NO po-warning (no existe)
  muted:   "stroke-po-text-subtle",
};

const TONE_FILL = {
  neutral: "fill-po-accent",
  warn:    "fill-po-suspect",
  muted:   "fill-po-text-subtle",
};

const W = 80;
const H = 28;
const PAD_Y = 4;

/**
 * Sparkline tonto. SparkGrid (Task 17) computa el tone (anomaly detection)
 * y se lo pasa como prop.
 *
 * - data.length === 0 → dashed line (sin datos)
 * - data.length === 1 → solo el punto
 * - data.length >= 2  → polyline + último punto resaltado
 */
export default function Sparkline({ data, tone = "neutral" }) {
  if (!data || data.length === 0) {
    return (
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-label="Sin datos">
        <line
          x1={0} y1={H / 2} x2={W} y2={H / 2}
          className="stroke-po-text-subtle"
          strokeWidth={1}
          strokeDasharray="2,2"
        />
      </svg>
    );
  }

  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = Math.max(max - min, 1);
  const stepX = data.length > 1 ? W / (data.length - 1) : 0;
  const yFor = (v) => PAD_Y + (1 - (v - min) / range) * (H - 2 * PAD_Y);
  const xFor = (i) => i * stepX;

  if (data.length === 1) {
    return (
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
        <circle cx={W / 2} cy={H / 2} r={2.5} className={TONE_FILL[tone]} />
      </svg>
    );
  }

  const points = data.map((v, i) => `${xFor(i)},${yFor(v)}`).join(" ");
  const lastIdx = data.length - 1;

  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
      <polyline
        fill="none"
        strokeWidth={1.5}
        className={TONE_STROKE[tone]}
        points={points}
      />
      <circle
        cx={xFor(lastIdx)}
        cy={yFor(data[lastIdx])}
        r={2}
        className={TONE_FILL[tone]}
      />
    </svg>
  );
}
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build
```

- [ ] **Step 3: Commit**

```bash
cd a:/PROJECTS/PDFoverseer
git add frontend/src/components/Sparkline.jsx
git commit -m "$(cat <<'EOF'
feat(ui): Sparkline component (SVG inline, dumb)

~60 LoC SVG. Props: data: number[], tone: 'neutral'|'warn'|'muted'.
No calcula anomalías — SparkGrid (Task 17) le pasa el tone calculado.
Tres modos: empty (dashed line), single point (circle), polyline + último
punto. Tone "warn" usa po-suspect (amber). Spec §5.1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 14: `OriginChip` component

**Files:**
- Create: `frontend/src/components/OriginChip.jsx`

Spec §5.1 + memoria `feedback_chip_consistency`. Reusa `Badge` primitive de FASE 3.

- [ ] **Step 1: Inspect Badge primitive**

```bash
cat frontend/src/ui/Badge.jsx
```

Identificar: variantes/tonos disponibles, props (size, etc).

- [ ] **Step 2: Create OriginChip**

`frontend/src/components/OriginChip.jsx`:

```jsx
// OriginChip: 3 variantes uniformes (forma idéntica, color por significado).
// Reusa Badge primitive — no es primitive top-level porque solo lo consume
// FileList. Spec §5.1 + memoria feedback_chip_consistency.

import Badge from "../ui/Badge";

// Map origin → Badge tone. Si los tonos en Badge son nombres distintos
// (ej. "info"/"success"/"warning"), ajustar este map en lugar del Badge.
const ORIGIN_TONE = {
  OCR:    "iris",   // azul/iris — dato medido por motor
  R1:     "jade",   // verde — default régimen 1
  manual: "amber",  // ámbar — override del usuario (= po-suspect family)
};

export default function OriginChip({ origin }) {
  const tone = ORIGIN_TONE[origin] ?? "muted";
  return (
    <Badge tone={tone}>
      {origin}
    </Badge>
  );
}
```

(Si Badge no acepta `tone="iris"`/`"jade"`/`"amber"`, agregar las variantes en Badge.jsx siguiendo el patrón de FASE 3 — ver el código de Task 7 del FASE 3 plan para referencia.)

- [ ] **Step 3: Verify build**

```bash
cd frontend && npm run build
```

- [ ] **Step 4: Commit**

```bash
cd a:/PROJECTS/PDFoverseer
git add frontend/src/components/OriginChip.jsx
git commit -m "$(cat <<'EOF'
feat(ui): OriginChip — 3 variantes uniformes sobre Badge

Mapea origin string ('OCR'|'R1'|'manual') a Badge tone (iris|jade|amber).
Misma forma para los 3 (memoria feedback_chip_consistency). Vive en
components/, no en ui/, porque solo lo consume FileList. Spec §5.1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 15: Extend `FileList` row with per_file UI + InlineEditCount

**Files:**
- Modify: `frontend/src/components/FileList.jsx`
- Modify: `frontend/src/store/session.js` (nueva action `savePerFileOverride`)
- Modify: `frontend/src/lib/api.js` (nueva función `patchPerFileOverride`)

Spec §5.1 + §7.2.

- [ ] **Step 1: Add patchPerFileOverride to api.js**

```bash
grep -A 12 "patchOverride" frontend/src/lib/api.js
```

Agregar siguiendo el patrón de `patchOverride` (que recibe `opts = { signal }` como último arg):

```js
patchPerFileOverride: async (sessionId, hospital, sigla, filename, count, opts = {}) => {
  const r = await fetch(
    `/api/sessions/${sessionId}/cells/${hospital}/${sigla}/files/${encodeURIComponent(filename)}/override`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ count }),
      signal: opts.signal,
    }
  );
  if (!r.ok) throw new Error(await r.text());
  return r.json();
},
```

- [ ] **Step 2: Add savePerFileOverride to store/session.js**

**Patrón crítico:** el store actual tiene **dos mapas separados** (verificable en `frontend/src/store/session.js:21-23`):
- `_pendingSave: Map` con `{controller: AbortController}` values (interno, abort-coordination).
- `pendingSaves: {}` plain object con status strings (`'saving'|'saved'|'error'`, lectura pública por componentes).

Las cells viven en `state.session.cells[hospital][sigla]` (NESTED bajo session). El patrón canónico es `saveOverride` (líneas 78-156) — espejarlo verbatim, solo cambiando key, endpoint, y lógica de update del cell.

```js
savePerFileOverride: async (sessionId, hospital, sigla, filename, count) => {
  const key = `${hospital}|${sigla}|${filename}`;
  const controller = new AbortController();

  // Atomic prev-read + write para evitar stale-read race.
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
    const result = await api.patchPerFileOverride(
      sessionId, hospital, sigla, filename, count,
      { signal: controller.signal },
    );
    if (controller.signal.aborted) return;

    set((prev) => {
      if (!prev.session) return {};
      const cells = { ...prev.session.cells };
      const hosp = { ...cells[hospital] };
      hosp[sigla] = {
        ...hosp[sigla],
        per_file_overrides: {
          ...(hosp[sigla]?.per_file_overrides ?? {}),
          [filename]: count,
        },
        count: result.new_cell_count,  // derivado del backend
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

    // Auto-flush 'saved' después de 2s (idem saveOverride).
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

(También: `api.patchPerFileOverride` debe aceptar `opts = { signal }` como 6º arg, idem el patrón de `api.patchOverride`. Ver Step 1 — la firma ya está pensada así.)

- [ ] **Step 3: Modify FileList.jsx row**

Reemplazar el button del map (líneas ~80-94) por:

```jsx
import InlineEditCount from "./InlineEditCount";
import OriginChip from "./OriginChip";
import { useSessionStore } from "../store/session";

// ... dentro del componente, antes del return ...
const session = useSessionStore((s) => s.session);
const savePerFileOverride = useSessionStore((s) => s.savePerFileOverride);

// ... dentro del map ...
{filtered.map((f, i) => (
  <li key={`${f.name}-${i}`} className="px-3 py-2 hover:bg-po-panel-hover transition">
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={() => openLightbox(hospital, sigla, files.indexOf(f))}
        className="flex items-center gap-2 flex-1 text-left"
      >
        <FileText size={14} strokeWidth={1.75} className="text-po-text-muted shrink-0" />
        <span className="font-mono text-xs text-po-text truncate flex-1">{f.name}</span>
        <span className="text-xs tabular-nums text-po-text-muted shrink-0">{f.page_count}pp</span>
        {f.suspect && (
          <Tooltip content="Probable compilación">
            <span><FileStack size={14} strokeWidth={1.75} className="text-po-suspect shrink-0" /></span>
          </Tooltip>
        )}
      </button>
      <div className="flex items-center gap-1.5 shrink-0" onClick={(e) => e.stopPropagation()}>
        <InlineEditCount
          value={f.effective_count ?? 1}
          onCommit={(newCount) =>
            savePerFileOverride(session.session_id, hospital, sigla, f.name, newCount)
          }
        />
        <OriginChip origin={f.origin ?? "R1"} />
      </div>
    </div>
  </li>
))}
```

- [ ] **Step 4: Verify build**

```bash
cd frontend && npm run build
```

- [ ] **Step 5: Visual smoke**

```bash
cd frontend && npm run dev
# Browser :5173 → mes ABRIL → HRB > odi > FileList
# Verificar cada row muestra Npp + Ndocs editable + OriginChip
# Click N docs → InlineEditCount inline → tipear nuevo valor → Enter
# Verificar: chip cambia a "manual" tras success, cell-total recalcula
```

- [ ] **Step 6: Commit**

```bash
cd a:/PROJECTS/PDFoverseer
git add frontend/src/components/FileList.jsx frontend/src/store/session.js frontend/src/lib/api.js
git commit -m "$(cat <<'EOF'
feat(file-list): per-file docs count + override + OriginChip

Cada row pasa de [icono][name][Npp] a [icono][name][Npp][Ndocs editable]
[OriginChip]. Click en Ndocs abre InlineEditCount (extraído en Task 2.5);
Enter guarda vía savePerFileOverride (AbortController-safe key=${h}|${s}|${file});
chip cambia a "manual" en success. Cell-total derivado del backend
(compute_cell_count). Spec §5.1 + §7.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Chunk 4: HLL flow + Multi-mes + smoke + close

### Task 16: HLL manual-entry flow (HospitalCard CTA + HospitalDetail manual mode)

**Files:**
- Modify: `frontend/src/lib/constants.js` (CTA copy)
- Modify: `frontend/src/store/session.js` (nuevo state `hospitalMode` + `focusSigla`; extend `saveOverride` con flag manual)
- Modify: `frontend/src/lib/api.js` (extend `patchOverride` para enviar `manual` flag)
- Modify: `api/routes/sessions.py:252` (extend PATCH /override request body)
- Modify: `api/state.py` (extend `apply_user_override` para aceptar `manual` flag)
- Modify: `frontend/src/components/HospitalCard.jsx`
- Modify: `frontend/src/views/HospitalDetail.jsx`
- Modify: `frontend/src/components/CategoryRow.jsx`
- Test: `tests/test_user_override_manual_flag.py` (nuevo)

Spec §5.1 + §7.1 + AC1.

**Importante:** navegación es vía Zustand store (`setView('hospital')` + `selectHospital(code)`), NO react-router. El `mode=manual&focus=reunion` no es una URL — es state interno del store.

- [ ] **Step 1: Add CTA copy constant**

`frontend/src/lib/constants.js`:

```js
// CTA copy en un solo lugar para mantener consistencia (spec §5.1).
export const CTA_LLENAR_MANUAL = "Llenar manualmente →";
```

- [ ] **Step 2: Backend — extend apply_user_override with manual flag (TDD)**

Test:

```python
# tests/test_user_override_manual_flag.py
"""apply_user_override accepts manual flag and persists cell.manual_entry."""
import sqlite3

import pytest

from api.state import SessionManager
from core.db.migrations import init_schema


@pytest.fixture
def mgr_session(tmp_path):
    conn = sqlite3.connect(tmp_path / "t.db")
    init_schema(conn)
    mgr = SessionManager(conn)
    sid = mgr.open_session(month_root=str(tmp_path), year=2026, month=4)
    yield mgr, sid
    conn.close()


def test_manual_flag_sets_manual_entry_true(mgr_session):
    mgr, sid = mgr_session
    mgr.apply_user_override(sid, "HLL", "reunion", value=12, note=None, manual=True)
    state, _ = mgr._load_and_migrate(sid)
    cell = state["cells"]["HLL"]["reunion"]
    assert cell["user_override"] == 12
    assert cell["manual_entry"] is True


def test_default_manual_flag_false_preserves_legacy_behavior(mgr_session):
    mgr, sid = mgr_session
    mgr.apply_user_override(sid, "HRB", "art", value=5, note="ajuste")
    state, _ = mgr._load_and_migrate(sid)
    cell = state["cells"]["HRB"]["art"]
    assert cell["user_override"] == 5
    # manual_entry should default to False (or not set if pre-existing)
    assert cell.get("manual_entry") is False
```

Run, verify failure (`unexpected keyword argument 'manual'`).

Modify `api/state.py:144-167` (`apply_user_override`) — agregar param keyword-only:

```python
def apply_user_override(
    self,
    session_id: str,
    hospital: str,
    sigla: str,
    *,
    value: int | None,
    note: str | None,
    manual: bool = False,  # ◀ NUEVO
) -> None:
    state, _ = self._load_and_migrate(session_id)
    cell = state.setdefault("cells", {}).setdefault(hospital, {}).setdefault(sigla, {})
    cell["user_override"] = value
    cell["override_note"] = note if value is not None else None
    cell.setdefault("filename_count", None)
    cell.setdefault("ocr_count", None)
    cell.setdefault("excluded", False)
    cell.setdefault("manual_entry", False)  # ◀ NUEVO (default initialization)
    if manual:
        cell["manual_entry"] = True
    update_session_state(self._conn, session_id, state_json=json.dumps(state))
```

Run tests:

```bash
pytest tests/test_user_override_manual_flag.py -v
pytest tests/ -q
```

- [ ] **Step 3: Backend — extend PATCH /override endpoint**

En `api/routes/sessions.py:252` (`patch_override`), inspeccionar el request model:

```bash
sed -n '245,275p' api/routes/sessions.py
```

Agregar `manual: bool = False` al request body model:

```python
class OverrideRequest(BaseModel):
    value: int | None
    note: str | None = None
    manual: bool = False  # ◀ NUEVO
```

Y en el handler, pasar el flag:

```python
mgr.apply_user_override(
    session_id, hospital, sigla,
    value=body.value, note=body.note, manual=body.manual,
)
```

Test rápido (extender suite existente o agregar test endpoint si no hay):

```python
def test_override_endpoint_accepts_manual_flag(client, sid):
    r = client.patch(
        f"/sessions/{sid}/cells/HLL/reunion/override",
        json={"value": 12, "manual": True},
    )
    assert r.status_code == 200
    # Verificar via mgr que cell.manual_entry == True
```

Commit backend changes:

```bash
git add api/state.py api/routes/sessions.py tests/test_user_override_manual_flag.py
git commit -m "$(cat <<'EOF'
feat(state): apply_user_override accepts manual flag

Kwarg manual: bool = False agrega cell.manual_entry = True cuando es el
HLL manual flow. PATCH /override request body acepta el flag opcional.
Default False preserva el comportamiento FASE 2. Spec §7.1 + AC1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: Frontend — extend api.js patchOverride**

```bash
grep -A 10 "patchOverride" frontend/src/lib/api.js
```

Agregar el `manual` opcional al body:

```js
patchOverride: async (sessionId, hospital, sigla, value, note, opts = {}) => {
  const body = { value, note };
  if (opts.manual) body.manual = true;
  const r = await fetch(
    `/api/sessions/${sessionId}/cells/${hospital}/${sigla}/override`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: opts.signal,
    }
  );
  if (!r.ok) throw new Error(await r.text());
  return r.json();
},
```

- [ ] **Step 5: Frontend — extend store with hospitalMode + focusSigla + saveOverride opts**

En `frontend/src/store/session.js`, agregar campos de state cerca de los existentes (líneas 5-23):

```js
// State (agregar junto a view/hospital):
hospitalMode: "scanned",  // ◀ NUEVO: "scanned" | "manual"
focusSigla: null,         // ◀ NUEVO: string | null
```

Modificar `selectHospital` (línea 51) para aceptar opts:

```js
selectHospital: (hospital, opts = {}) => set({
  view: "hospital",
  hospital,
  hospitalMode: opts.mode ?? "scanned",
  focusSigla: opts.focus ?? null,
}),
```

Modificar `setView` (línea 25) para resetear modo al salir de hospital:

```js
setView: (view) => set({
  view,
  ...(view !== "hospital" && { hospitalMode: "scanned", focusSigla: null }),
}),
```

Extender `saveOverride` (líneas 78-156) para aceptar `opts.manual`. **Cambio mínimo:** agregar 6º arg `opts = {}` y pasar `manual: opts.manual` al `api.patchOverride`. El resto del cuerpo (functional set, dual-map pendingSaves) **queda idéntico**:

```js
// Cambia ÚNICAMENTE la signature y la llamada a api.patchOverride.
// Resto del cuerpo (functional set + dual-map pattern) sin tocar.
saveOverride: async (sessionId, hospital, sigla, value, note, opts = {}) => {
  const key = `${hospital}|${sigla}`;
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
    const result = await api.patchOverride(
      sessionId, hospital, sigla, value, note,
      { signal: controller.signal, manual: opts.manual },  // ◀ ÚNICO cambio: agrega manual
    );
    // ... resto del cuerpo (atomic cell update, auto-flush 'saved', catch error)
    //     IDÉNTICO al actual — verbatim líneas 106-155 ...
  } catch (error) {
    // ... idem ...
  }
},
```

(Cuando el agente implemente esto, debe copiar el cuerpo actual líneas 87-155 verbatim, cambiando SOLO la línea de `api.patchOverride` para incluir `manual: opts.manual`.)

- [ ] **Step 6: Modify HospitalCard.jsx — CTA en empty state**

```bash
grep -n "empty\|sin carpeta\|disabled\|opaco" frontend/src/components/HospitalCard.jsx
```

Reemplazar el placeholder estático por:

```jsx
import { CTA_LLENAR_MANUAL } from "../lib/constants";
import { useSessionStore } from "../store/session";

// ... dentro del componente ...
const selectHospital = useSessionStore((s) => s.selectHospital);

// En el branch state === "empty":
<button
  type="button"
  onClick={() => selectHospital(hospital.code, { mode: "manual", focus: "reunion" })}
  className="inline-flex items-center gap-1 text-xs text-po-accent hover:text-po-accent-hover px-2 py-1 rounded hover:bg-po-panel-hover transition"
>
  {CTA_LLENAR_MANUAL}
</button>
```

- [ ] **Step 7: Modify HospitalDetail.jsx — leer hospitalMode + focusSigla del store**

```bash
grep -n "useSessionStore\|cells\|sigla" frontend/src/views/HospitalDetail.jsx | head
```

```jsx
const hospitalMode = useSessionStore((s) => s.hospitalMode);
const focusSigla = useSessionStore((s) => s.focusSigla);

// Header text:
const headerCount = hospitalMode === "manual"
  ? `${ingresadas} / 18 ingresadas`
  : `${procesadas} / 18 procesadas`;

// Render: pasar mode + autoFocus + onCommitNext a CategoryRow
<CategoryRow
  cell={cell}
  mode={hospitalMode}
  autoFocus={cell.sigla === focusSigla}
  onCommitNext={() => focusNextSigla(cell.sigla)}  // helper local
/>
```

`focusNextSigla` es un helper que busca la siguiente sigla en `SIGLAS` y dispatch `setState({ focusSigla: nextSigla })`. Implementación corta dentro del componente o en `lib/`.

- [ ] **Step 8: Modify CategoryRow.jsx — soportar mode + focusSigla + Enter para next**

```jsx
export default function CategoryRow({ cell, mode = "scanned", autoFocus = false, onCommitNext, ... }) {
  const showMethodChip = mode === "scanned" && cell.count != null;
  const placeholder = mode === "manual" ? "—" : null;

  const onCommitCount = (v) => {
    saveOverride(
      session.session_id, cell.hospital, cell.sigla, v, cell?.override_note ?? null,
      { manual: mode === "manual" },  // ◀ NUEVO: pasa el flag
    );
    if (mode === "manual" && onCommitNext) onCommitNext();
  };

  return (
    <div ...>
      {/* ... */}
      <InlineEditCount
        value={cell.count ?? 0}
        placeholder={placeholder}
        autoFocus={autoFocus}
        onCommit={onCommitCount}
      />
      {showMethodChip && <MethodChip method={cell.method} />}
      {/* ... */}
    </div>
  );
}
```

(Si `InlineEditCount` no soporta `placeholder` o `autoFocus` props todavía, agregarlos en Task 2.5's extracted file.)

- [ ] **Step 9: Verify build + visual smoke**

```bash
cd frontend && npm run build
cd frontend && npm run dev
# Browser → MonthOverview → HLL card → click "Llenar manualmente →"
# Verificar: navegación a HospitalDetail con hospitalMode="manual"
# Header dice "0/18 ingresadas"
# Primer InlineEditCount (sigla "reunion") tiene focus
# Tipear "12" + Enter → toast confirma + focus pasa al siguiente input
# F5 → state se preserva (cell-level via BD; hospitalMode se resetea, OK)
# Generar Excel desde la app → archivo creado, HLL columns con valores
```

- [ ] **Step 10: Commit frontend changes**

```bash
cd a:/PROJECTS/PDFoverseer
git add frontend/src/lib/constants.js \
        frontend/src/lib/api.js \
        frontend/src/store/session.js \
        frontend/src/components/HospitalCard.jsx \
        frontend/src/views/HospitalDetail.jsx \
        frontend/src/components/CategoryRow.jsx \
        frontend/src/components/InlineEditCount.jsx
git commit -m "$(cat <<'EOF'
feat(hll-flow): manual-entry CTA + HospitalDetail manual mode

HospitalCard en state=empty muestra "Llenar manualmente →" → invoca
selectHospital(code, {mode: "manual", focus: "reunion"}) sobre Zustand
store (no react-router). HospitalDetail lee hospitalMode + focusSigla y
renderea CategoryRow modo manual: header "N/18 ingresadas", placeholder "—",
focus en primer input, Enter avanza. Frontend store extendido con
hospitalMode + focusSigla + saveOverride opts.manual flag, plumbed end-to-end
hasta apply_user_override que persiste cell.manual_entry = true.
historical_counts queda con method="manual" (literal FASE 2 reusado).
Spec §5.1 + §7.1 + AC1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 17: SparkGrid + toggle "Histórico" en MonthOverview + useHistoryStore

**Files:**
- Create: `frontend/src/components/SparkGrid.jsx`
- Create: `frontend/src/lib/useHistoryStore.js`
- Modify: `frontend/src/views/MonthOverview.jsx`
- Modify: `frontend/src/lib/api.js` (agregar `getHistory`)
- Modify: `frontend/src/store/session.js` (agregar `historyView` toggle state)

Spec §5.1 + §7.3 + AC3.

**Importante:** sin URL state porque no hay router. El toggle vive en Zustand store.

- [ ] **Step 1: Add getHistory to api.js**

```js
getHistory: async (sessionId, n = 12) => {
  const r = await fetch(`/api/sessions/${sessionId}/history?n=${n}`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
},
```

- [ ] **Step 2: Add toggle state to store/session.js**

```js
// state:
historyView: false,  // ◀ NUEVO: false = mes actual, true = histórico

// actions:
toggleHistoryView: () => set((s) => ({ historyView: !s.historyView })),
setHistoryView: (v) => set({ historyView: !!v }),
```

- [ ] **Step 3: Create useHistoryStore with module-level cache**

`frontend/src/lib/useHistoryStore.js`:

```js
// Module-level cache singleton — sobrevive entre mounts. Cache por session_id.
// Spec §5.1: "objeto singleton fuera del componente, similar al patrón de
// frontend/src/lib/api.js".

import { useEffect, useState } from "react";
import { api } from "./api";

const _cache = new Map();   // session_id → {data}
const _listeners = new Set();

export function invalidateHistory(sessionId) {
  if (sessionId) _cache.delete(sessionId);
  _listeners.forEach((l) => l());
}

export function useHistory(sessionId, n = 12) {
  const [data, setData] = useState(_cache.get(sessionId)?.data ?? null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!sessionId) {
      setData(null);
      return;
    }
    const cached = _cache.get(sessionId);
    if (cached) {
      setData(cached.data);
      return;
    }
    let cancelled = false;
    api.getHistory(sessionId, n)
      .then((d) => {
        if (cancelled) return;
        _cache.set(sessionId, { data: d });
        setData(d);
      })
      .catch((err) => !cancelled && setError(err));
    return () => { cancelled = true; };
  }, [sessionId, n]);

  // Re-render when invalidate is called from elsewhere
  useEffect(() => {
    const listener = () => {
      const cached = _cache.get(sessionId);
      setData(cached ? cached.data : null);
    };
    _listeners.add(listener);
    return () => _listeners.delete(listener);
  }, [sessionId]);

  return { data, error };
}
```

- [ ] **Step 4: Create SparkGrid component**

`frontend/src/components/SparkGrid.jsx`:

```jsx
import Sparkline from "./Sparkline";
import Tooltip from "../ui/Tooltip";
import { SIGLAS } from "../lib/sigla-labels";  // verificar nombre exacto

const HOSPITALS = ["HPV", "HRB", "HLU", "HLL"];

function anomalyTone(series) {
  // Caída >30% vs promedio últimos 6 meses, solo si baseline efectivo >=6.
  if (!series || series.length < 7) return "neutral";  // last + 6 baseline
  const last = series[series.length - 1].count;
  const baseline = series.slice(-7, -1);  // 6 meses previos al último
  const valid = baseline.filter((p) => p && p.count > 0);
  if (valid.length < 6) return "neutral";
  const mean = valid.reduce((a, b) => a + b.count, 0) / valid.length;
  if (mean === 0) return "neutral";
  if (last / mean < 0.7) return "warn";
  return "neutral";
}

function tooltipContent(series) {
  if (!series || series.length === 0) return "Sin datos";
  return series
    .map((p) => `${String(p.month).padStart(2, "0")}/${p.year}: ${p.count}`)
    .join("\n");
}

export default function SparkGrid({ history }) {
  return (
    <div className="rounded-xl bg-po-panel border border-po-border overflow-hidden">
      <div className="grid grid-cols-[200px_repeat(4,1fr)] bg-po-panel-hover text-xs font-mono text-po-text-subtle uppercase tracking-wide">
        <div className="px-3 py-2">Sigla</div>
        {HOSPITALS.map((h) => (
          <div key={h} className="px-3 py-2 text-center">{h}</div>
        ))}
      </div>
      {SIGLAS.map((sigla) => {
        // Adaptar al shape real de SIGLAS (puede ser {code, label, ...} o array de strings)
        const code = sigla.code ?? sigla;
        const label = sigla.numbered_label ?? sigla.label ?? code;
        return (
          <div
            key={code}
            className="grid grid-cols-[200px_repeat(4,1fr)] border-t border-po-border"
          >
            <div className="px-3 py-2 text-sm text-po-text font-mono">{label}</div>
            {HOSPITALS.map((h) => {
              const series = history?.[`${h}|${code}`] ?? [];
              const tone = anomalyTone(series);
              const last = series[series.length - 1]?.count ?? "—";
              return (
                <Tooltip key={h} content={tooltipContent(series)}>
                  <div className="px-3 py-2 flex items-center justify-between gap-2 cursor-pointer hover:bg-po-panel-hover">
                    <Sparkline data={series.map((p) => p.count)} tone={tone} />
                    <span className={`text-sm tabular-nums ${tone === "warn" ? "text-po-suspect font-semibold" : "text-po-text"}`}>
                      {last}{tone === "warn" && " ↓"}
                    </span>
                  </div>
                </Tooltip>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}
```

(Verificar nombre exacto de SIGLAS y su shape antes de escribir — `grep "export.*SIGLAS\|export const SIGLAS" frontend/src/lib/sigla-labels.js`.)

- [ ] **Step 5: Modify MonthOverview.jsx — add toggle + conditional render**

```bash
grep -n "HospitalCardGrid\|return\|MonthOverview" frontend/src/views/MonthOverview.jsx
```

```jsx
import SparkGrid from "../components/SparkGrid";
import { useHistory } from "../lib/useHistoryStore";

// ... dentro del componente ...
const historyView = useSessionStore((s) => s.historyView);
const setHistoryView = useSessionStore((s) => s.setHistoryView);
const sessionId = useSessionStore((s) => s.session?.session_id);
const { data: history } = useHistory(historyView ? sessionId : null);

const Toggle = (
  <div className="flex bg-po-panel rounded-md p-0.5 text-xs">
    <button
      onClick={() => setHistoryView(false)}
      className={`px-3 py-1 rounded ${!historyView ? "bg-po-panel-hover text-po-text font-semibold" : "text-po-text-muted"}`}
    >
      Mes actual
    </button>
    <button
      onClick={() => setHistoryView(true)}
      className={`px-3 py-1 rounded ${historyView ? "bg-po-panel-hover text-po-text font-semibold" : "text-po-text-muted"}`}
    >
      Histórico
    </button>
  </div>
);

// In the JSX, after existing header:
<div className="flex items-center justify-between mb-4">
  <h2>...</h2>
  {Toggle}
</div>

{historyView
  ? <SparkGrid history={history} />
  : <HospitalCardGrid />  // existing component or markup
}
```

- [ ] **Step 6: Hook invalidation on Excel generation**

Localizar el handler post-Excel exitoso (probablemente en store/session.js o en ScanControls):

```bash
grep -rn "generate.*output\|toast.success.*Excel\|RESUMEN" frontend/src/
```

Agregar:

```js
import { invalidateHistory } from "./useHistoryStore";  // si está en store/session.js

// Después de POST /output exitoso:
invalidateHistory(get().session.session_id);
```

- [ ] **Step 7: Verify build + visual smoke**

```bash
cd frontend && npm run build
cd frontend && npm run dev
# Browser → MonthOverview → click "Histórico" toggle
# Verificar: vista cambia a SparkGrid
# Si BD tiene historical_counts (después de Pre-flight Task 0), las series aparecen
# Hover en celda → Tooltip con valores mes-a-mes
# Click "Mes actual" → vuelve a HospitalCardGrid
```

- [ ] **Step 8: Commit**

```bash
cd a:/PROJECTS/PDFoverseer
git add frontend/src/components/SparkGrid.jsx \
        frontend/src/lib/useHistoryStore.js \
        frontend/src/views/MonthOverview.jsx \
        frontend/src/lib/api.js \
        frontend/src/store/session.js
git commit -m "$(cat <<'EOF'
feat(multi-mes): SparkGrid + toggle Histórico + useHistoryStore

Toggle [Mes actual] [Histórico] en MonthOverview con state Zustand
(historyView). SparkGrid 18 siglas × 4 hospitales con sparklines de 12
meses; anomalías (caída >30% vs promedio 6m, baseline efectivo >=6) en
tone="warn" (po-suspect, no po-warning) con flecha ↓; Tooltip con valores
mes-a-mes. useHistoryStore con cache módulo-level singleton (no Zustand,
no React Query); invalida post-Excel. Sin URL state (no react-router).
Spec §5.1 + §7.3 + AC3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 18: E2E smoke via chrome-devtools MCP + bug fixes

**Files:** N/A (smoke conducting)

Spec §9.1 + §10. Claude maneja la verificación visual end-to-end. Memoria `feedback_browser_testing_via_devtools`.

- [ ] **Step 1: Start backend + frontend**

PowerShell o Bash, dos terminales separadas:

```bash
# Terminal 1 — backend
source .venv-cuda/Scripts/activate  # o .\.venv-cuda\Scripts\activate
python server.py

# Terminal 2 — frontend
cd frontend && npm run dev
```

(O usa el procedimiento "reinicia_todo" guardado en memoria.)

- [ ] **Step 2: Open browser via chrome-devtools MCP**

Navegar a `http://localhost:5173`. Verificar página carga.

- [ ] **Step 3: Smoke AC1 — HLL manual flow**

- [ ] Crear sesión sobre `A:/informe mensual/04 Abril/`.
- [ ] HospitalCard de HLL muestra "Llenar manualmente →" (no estado opaco no-clickeable).
- [ ] Click → navegación interna a HospitalDetail HLL con `hospitalMode="manual"`.
- [ ] Header dice "0/18 ingresadas".
- [ ] Tipear N en primer input + Enter → toast Sonner confirma, focus pasa al siguiente input.
- [ ] Refresh con F5 → valores ingresados persisten (vienen de BD).
- [ ] Generar Excel → archivo `RESUMEN_2026-04.xlsx` creado.
- [ ] Inspect xlsx: HLL columns muestran los valores ingresados; siglas no-ingresadas en 0.
- [ ] `sqlite3 data/overseer.db "SELECT * FROM historical_counts WHERE hospital='HLL' AND year=2026 AND month=4"` → method='manual'.
- [ ] Capturar screenshots → `docs/research/fase4-smoke-hll-*.png`.

- [ ] **Step 4: Smoke AC2 — Per-file**

- [ ] Entrar a HRB > odi > FileList. Cada row muestra `Npp + Ndocs + chip OCR/R1/manual`.
- [ ] Click en `N docs` → InlineEditCount inline aparece.
- [ ] Tipear nuevo valor + Enter → chip cambia a "manual" (ámbar), cell-total recalcula.
- [ ] Toast Sonner confirma.
- [ ] F5 → override persiste (BD).
- [ ] Capturar screenshots → `docs/research/fase4-smoke-perfile-*.png`.

- [ ] **Step 5: Smoke AC3 — Multi-mes**

- [ ] Pre-condición: BD con ≥6 meses de historical_counts. Si no hay, generar Excel para ABRIL varias veces (cada generación UPSERTea, pero un solo mes no produce sparkline interesante — para smoke completo, idealmente fabricar entries para varios meses con un script ad-hoc usando `historical_repo.upsert_count`).
- [ ] Click toggle "Histórico" en header MonthOverview.
- [ ] SparkGrid renderea 18 siglas × 4 hospitales.
- [ ] Si hay caída fabricada: sparkline tone="warn" + flecha ↓ visible.
- [ ] Hover en celda → Tooltip con (mes, valor) por mes.
- [ ] Click "Mes actual" → vuelve a HospitalCardGrid.
- [ ] Capturar screenshots → `docs/research/fase4-smoke-multimes-*.png`.

- [ ] **Step 6: Smoke AC4 — Cross-cutting**

- [ ] `ruff check .` → 0 violations.
- [ ] `pytest -q` → todos verde.
- [ ] `cd frontend && npm run build` → green; observar bundle delta vs FASE 3.
- [ ] Verificar que features FASE 3 no regresaron: cell-level override (FASE 2), inline edit, save indicator, lightbox, ScanControls.

- [ ] **Step 7: Para cada bug found, write failing test (backend) o repro doc (frontend), fix, commit aparte**

Cada bug = un commit `fix(<scope>): <bug>`.

- [ ] **Step 8: Commit smoke screenshots**

```bash
git add docs/research/fase4-smoke-*.png
git commit -m "$(cat <<'EOF'
docs(research): FASE 4 smoke screenshots

Capturas de los 3 ACs (HLL flow, per-file, multi-mes) y cross-cutting,
manejado vía chrome-devtools MCP. Memoria
feedback_browser_testing_via_devtools.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 19: Update CLAUDE.md + tag fase-4-mvp

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Inspect current FASE sections in CLAUDE.md**

```bash
grep -n "## FASE\|### FASE\|fase-3\|fase-4" CLAUDE.md
```

- [ ] **Step 2: Edit FASE 3 section to predecessor format**

Demote la sección FASE 3 a subsección dentro de FASE 4:

- Cambiar `## FASE 3 polish — ...` → `### FASE 3 polish — predecessor, ...`
- Demote también las subsecciones internas para mantener nesting consistente:
  - `### Design tokens` → `#### Design tokens`
  - `### Next (FASE 4)` → `#### Next (ya cubierto en FASE 4)` (o eliminar si redundante)
  - Cualquier otro `### ` dentro de la sección FASE 3 → `#### `

Sigue el patrón exacto que FASE 3 hizo con FASE 2 (verificable en el CLAUDE.md actual antes de la edit).

- [ ] **Step 3: Add FASE 4 section above FASE 3 predecessor**

```markdown
## FASE 4 polish — `po_overhaul` branch (shipped 2026-05-XX)

Slice UX cerrando 3 pendientes del roadmap post-FASE 3:

1. **HLL manual-entry**: HospitalCard CTA "Llenar manualmente →" cuando state=empty, HospitalDetail mode=manual (Zustand-based, no router), focus auto-shift en Enter, audit trail con method="manual" (literal FASE 2 reusado).
2. **Docs por archivo en FileList**: ScanResult.per_file propagado por scanners; FileList row con Npp + Ndocs editable + OriginChip (OCR/R1/manual); cell-count derivado de compute_cell_count espejado en JS (frontend/src/lib/cellCount.js).
3. **Multi-mes tendencia**: Toggle [Mes actual]/[Histórico] en MonthOverview (state Zustand, sin URL); SparkGrid 18×4 con sparklines de 12 meses sobre historical_counts via query_range; anomalías >30% en ámbar (po-suspect, baseline ≥6); useHistoryStore con cache módulo-level.

- **Spec:** `docs/superpowers/specs/2026-05-14-fase-4-design.md`
- **Plan:** `docs/superpowers/plans/2026-05-14-pdfoverseer-fase-4.md`
- **Tag:** `fase-4-mvp` (local, awaiting push approval)
- **Bundle delta:** [completar tras smoke]
- **New deps:** ninguna (todo construido sobre la base FASE 3)

### Next (FASE 5)
- Per-sigla OCR engine refinement contra el corpus real
- Page-level cancellation (target <3s)
- Drill-in del histórico (vista detalle de serie completa con números mes-a-mes)
- Auto-retry on OCR failure
```

- [ ] **Step 4: Verify ruff + tests still green**

```bash
ruff check .
pytest -q
```

- [ ] **Step 5: Commit CLAUDE.md**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(claude-md): FASE 4 section + demote FASE 3 to predecessor

Sigue el patrón FASE 3 hizo con FASE 2: la fase actual al tope, la
predecesora demotada a sub-sección. Incluye spec/plan links, tag, bundle
delta, deps, y next-steps roadmap.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 6: Tag locally**

```bash
git tag fase-4-mvp
git log --oneline -1
```

Expected: tag aplicado al último commit.

- [ ] **Step 7: Surface to user — push approval**

Imprimir resumen al usuario:

> FASE 4 implementada y testeada. Commits: [N] sobre `po_overhaul`.
> Tag local: `fase-4-mvp`. Bundle delta: +X kB gzipped (vs FASE 3 baseline).
> ¿Push a origin?

**No push automático** — esperar aprobación explícita (regla FASE 3 mantenida).

---

## Done

Plan completo cubre §10 ACs del spec. Total: 22 tareas (3 pre-flight + 1 refactor + 16 implementation + 1 smoke + 1 docs).

Ejecutar con `superpowers:subagent-driven-development` — un subagent fresco por tarea, con review entre cada uno.
