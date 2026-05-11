# PDFoverseer Overhaul — Design Spec

**Fecha:** 2026-05-11
**Rama:** `research/pixel-density`
**Estado:** Draft pendiente review
**Autor:** Daniel + Claude (Opus 4.7)

> Rediseño completo de PDFoverseer alrededor del flujo real: contar documentos por (hospital, categoría) para producir el Excel mensual de cumplimiento del programa de prevención. Reemplaza la UI single-PDF-session por un orchestrator filesystem-first con scanners especializados por tipo de documento.

---

## Tabla de contenidos

1. [Contexto y objetivos](#1-contexto-y-objetivos)
2. [Arquitectura general](#2-arquitectura-general)
3. [Scanner registry](#3-scanner-registry)
4. [Modelo de datos](#4-modelo-de-datos)
5. [Template Excel y outputs](#5-template-excel-y-outputs)
6. [API surface](#6-api-surface)
7. [Frontend](#7-frontend)
8. [Entrega por fases](#8-entrega-por-fases)
9. [Error handling](#9-error-handling)
10. [Estrategia de testing](#10-estrategia-de-testing)
11. [Plan de migración](#11-plan-de-migración)
12. [Riesgos y mitigaciones](#12-riesgos-y-mitigaciones)
13. [Decisiones diferidas a implementación](#13-decisiones-diferidas-a-implementación)

---

## 1. Contexto y objetivos

### 1.1 Problema

PDFoverseer es la etapa de conteo de un pipeline mensual de 3 proyectos hermanos (`informe mensual` → PDFoverseer → `estadistica mensual`) para reportes de seguridad ocupacional de 4 hospitales (CRS / Concesión Red Los Ríos-Los Lagos).

La app actual está orientada a **sesiones de PDF individuales**: el usuario sube un archivo, el motor de inferencia de 5 fases lo procesa, devuelve un conteo. Esto no calza con el flujo real:

- El usuario necesita producir **72 números por mes** (4 hospitales × 18 categorías) que llenan el archivo `RESUMEN_<MES>_<AÑO>.xlsx`
- En ABRIL 2026, ~90% de las celdas se resuelven con un simple `glob(*.pdf)` porque los archivos ya están individualizados por scripts upstream
- El ~10% restante son compilaciones implícitas (1 PDF que contiene N documentos internos) — y cada tipo de documento tiene características propias que pueden explotarse mejor que el motor genérico actual
- El conteo manual hoy "puede tomar días" (citando memoria `informe mensual/.serena/memories/task_completion.md`)

### 1.2 Objetivo

Reemplazar la app por un orchestrator filesystem-first que:

1. Tome una carpeta de mes (`A:\informe mensual\<MES>\`) como entrada
2. Enumere los 4 hospitales × 18 categorías automáticamente
3. Cuente cada celda usando un **scanner especializado por tipo de documento**
4. Permita corrección manual con cascada hasta el output
5. Genere `RESUMEN_<MES>_<AÑO>.xlsx` a partir de un template propio
6. Acumule datos cross-mes para reportes históricos
7. Reduzca el tiempo de Daniel de "días" a "minutos + revisión humana"

### 1.3 Non-goals (cosas que explícitamente NO hacemos)

- **NO reescribimos** el OCR base (Tesseract Tier 1+2+SR). Los scanners lo USAN, no lo reemplazan.
- **NO introducimos VLM ni modelos remotos** en el pipeline. El postmortem 2026-03-29 documentó por qué (sin-dato > dato-incorrecto, paradoja Claude 88.6% = 32 errores XVAL). VLM puede revivir solo como herramienta offline de auditoría, fuera del scope de este overhaul.
- **NO reemplazamos** el motor 5-fases. Queda como un scanner opcional ("legacy") invocable manualmente.
- **NO computamos** HH Capacitación ni % Cumplimiento. Esas son fórmulas Excel downstream en `estadistica mensual`.
- **NO tocamos** los scripts de `informe mensual` (Steps 0-2 ya automatizados). PDFoverseer solo lee desde su output.
- **NO migramos** los datos históricos de `data/sessions.db` (la sesión database actual). El overhaul empieza con DB nueva.

### 1.4 Constraints

| Constraint | Razón |
|---|---|
| Tesseract-only para OCR | Decisión `feedback_paddleocr_not_suitable.md` (2026-03) |
| Sin modelos AI inline | Postmortem VLM 2026-03-29 |
| Confianza explícita por celda | Lección VLM: el motor maneja "sin dato" mejor que "dato incorrecto" |
| Filesystem como source-of-truth | El upstream (`informe mensual`) ya impone naming canónico |
| Lectura directa, sin copia | Min friction; respeta el workflow real |
| Sin mocking de DB en tests | Regla del proyecto (`CLAUDE.md`) |
| Sin archivos titánicos | Directiva usuario 2026-05-11: capas, modular |
| Sin `print()` en library code | Hookify rule `no-print-in-libs` |
| Sin `shell=True` ni SQL f-strings | Hookify rules (blocking) |

### 1.5 Success criteria

**FASE 1 MVP exitoso si:**
- Usuario abre la app, pica una carpeta de mes, ve los 4 hospitales con sus 18 categorías y conteos triviales en < 30 segundos
- Genera el archivo Excel con valores correctos en las 54 celdas no-compiladas de ABRIL (HPV+HRB+HLU)
- Ningún test de regresión existente falla
- Sin OCR ejecutado en FASE 1 (todos los scanners son filename-glob)

**FASE 2 exitoso si:**
- Las celdas de compilación (HRB ODI, HLU ODI, HRB IRL en ABRIL) se cuentan correctamente con scanners OCR específicos
- El usuario puede revisar archivos con conteo dudoso usando el visor y corregir manualmente
- La corrección cascadea al Excel sin re-ejecutar nada
- Sesión por mes persiste entre cierres de app

**FASE 3 exitoso si:**
- Reporte cross-mes (FEBRERO+MARZO+ABRIL) se genera en < 10 segundos
- Rename de carpetas (`7.-ART` → `7.-ART 934`) y archivos (cuando aplique) es opt-in con preview obligatorio
- JSON export disponible
- Métricas, ETA, skip/add files implementados

---

## 2. Arquitectura general

### 2.1 Capas (5 capas, una responsabilidad cada una)

```
┌────────────────────────────────────────────────────────────────┐
│  FRONTEND (React + Vite, :5173)                                │
│  Drill-down nav: Mes → Hospital → Categoría (+ side panel)     │
│  3 vistas: MonthOverview, HospitalDetail, Settings/Output      │
└──────────────────────────────┬─────────────────────────────────┘
                               │ HTTP REST + WebSocket
┌──────────────────────────────▼─────────────────────────────────┐
│  API (FastAPI, :8000)                                          │
│  api/routes/*.py — uno por recurso, thin                       │
│  api/ws.py — broadcasts de progreso/ETA                        │
└──────────────────────────────┬─────────────────────────────────┘
                               │
┌──────────────────────────────▼─────────────────────────────────┐
│  ORCHESTRATOR (core/orchestrator.py)                           │
│  Enumera, dispatch a scanners, paralelismo, agrega resultados  │
└──────┬────────────────────────────────────────────┬────────────┘
       │                                            │
┌──────▼────────────────────────┐    ┌──────────────▼────────────┐
│  SCANNERS (core/scanners/)    │    │  STORAGE (core/db/)       │
│  Uno por sigla + utils        │    │  SQLite: sessions +       │
│  Self-contained, ≤250 LOC c/u │    │  historical_counts        │
└───────────────────────────────┘    └──────────────┬────────────┘
                                                    │
                                       ┌────────────▼────────────┐
                                       │ EXCEL WRITER            │
                                       │ core/excel/writer.py    │
                                       │ Template + datos →      │
                                       │ RESUMEN_<MES>.xlsx      │
                                       └─────────────────────────┘
```

### 2.2 Boundaries entre capas

| Capa | Conoce | NO conoce |
|---|---|---|
| Frontend | Modelo de UI, eventos API/WS | Implementación de scanners, schema DB |
| API | Schema DTOs, sesión service | Scanner internals, filesystem |
| Orchestrator | Scanners disponibles, schema sesión | Detalles OCR de cada scanner, UI |
| Scanners | OCR utils, su técnica propia | Otros scanners, DB, Excel |
| Storage | Schema SQLite | UI, scanners, filesystem PDFs |
| Excel writer | Template + estructura datos | Cómo se obtuvieron los datos |

### 2.3 Line-count budgets (codebase hygiene)

| Tipo de archivo | Max LOC |
|---|---|
| Scanner individual | 250 |
| Scanner shared util | 200 |
| Orchestrator | 400 |
| API route file (por recurso) | 300 |
| Storage layer total | 400 (repartido en 2-3 archivos) |
| Excel writer | 400 |
| Frontend component | 200 |
| Frontend hook | 150 |

Cuando un archivo se acerca al límite, **se refactoriza en submódulos antes** de pasarse. Excepciones documentadas en comments del propio archivo.

### 2.4 Reuse vs new vs retire

**Reusar (sin tocar)**:
- `core/ocr.py` — Tesseract Tier 1+2+SR, sigue siendo la base
- `core/utils.py` — constantes y helpers
- `frontend/src/lib/` — utils, formatters
- Hooks de calidad: `ruff check`, hookify rules

**Reusar (refactorizar)**:
- `core/inference.py` y `core/phases/` → empaquetado como `core/scanners/legacy_inference.py` con interfaz Scanner
- PDF viewer del frontend (`CorrectionPanel.jsx` partes) → componente nuevo `ReviewModal`

**Crear nuevo**:
- `core/scanners/` con su registry
- `core/orchestrator.py`
- `core/db/` (sessions, historical)
- `core/excel/` (template loader, writer)
- `api/routes/` (nueva organización por recurso)
- `frontend/src/views/` (MonthOverview, HospitalDetail, Settings)
- `frontend/src/components/` (CategoryRow, HospitalCard, ScanIndicator, etc.)

**Retirar (eventualmente, no en FASE 1)**:
- `frontend/src/components/Terminal.jsx` — el progreso pasa al side panel
- `frontend/src/components/IssueInbox.jsx` — el flujo de issues cambia
- `api/sessions.py` actual (single-PDF) — reemplazado por sesión-por-mes
- `data/sessions.db` actual — DB nueva, no migramos

---

## 3. Scanner registry

### 3.1 Interfaz

```python
# core/scanners/base.py

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

class ConfidenceLevel(Enum):
    HIGH = "high"      # filename count o múltiples métodos concuerdan
    MEDIUM = "medium"  # OCR scanner sin verificación cruzada
    LOW = "low"        # fallback, discrepancia detectada
    MANUAL = "manual"  # usuario corrigió el valor

@dataclass(frozen=True)
class ScanResult:
    count: int
    confidence: ConfidenceLevel
    method: str  # "filename_glob", "header_detect", "corner_count", "legacy_5phase", "manual"
    breakdown: dict[str, int] | None  # opcional: per-empresa, per-file
    flags: list[str]  # ["compilation_detected", "missing_pages", "unexpected_template", ...]
    errors: list[str]
    duration_ms: int
    files_scanned: int

class Scanner(Protocol):
    sigla: str  # "art", "irl", "odi", ...

    def count(
        self,
        folder: Path,
        *,
        override_method: str | None = None,
    ) -> ScanResult: ...
```

Nota: el dispatch es por sigla via registry (§3.2), no por `can_handle()`. Mantener la interfaz minimal — agregar capabilities solo cuando el orchestrator las necesite.

### 3.2 Registry pattern

```python
# core/scanners/__init__.py

from typing import Callable

_REGISTRY: dict[str, Scanner] = {}

def register(scanner: Scanner) -> None:
    _REGISTRY[scanner.sigla] = scanner

def get(sigla: str) -> Scanner:
    return _REGISTRY[sigla]

def all_siglas() -> list[str]:
    return list(_REGISTRY.keys())
```

Cada scanner se auto-registra al importarse (al final de su módulo). El orchestrator hace `from core.scanners import art_scanner, irl_scanner, ...` y la registry se llena.

### 3.3 Los 18 scanners — técnicas por tipo

Tabla autoritativa de qué técnica usa cada scanner. Las técnicas se discuten/refinan durante implementación; lo importante es que cada uno es **self-contained** con la mejor heurística para ese tipo de documento.

| # | Sigla | Técnica primaria | Heurística | Fallback |
|---|---|---|---|---|
| 1 | reunion | filename_glob | 1 PDF = 1 reunión | none |
| 2 | irl | header_detect | Buscar `F-CRS-IRL/XX` por página | filename_glob si page-count razonable |
| 3 | odi | header_detect | Buscar `F-CRS-ODI/03` por página | filename_glob |
| 4 | charla | filename_glob + roster_lines (FASE 2) | filename count + verificación de líneas en roster | corner_count |
| 5 | chintegral | filename_glob | 1 PDF = 1 charla (multi-página normal) | none |
| 6 | dif_pts | filename_glob | 1 PDF = 1 difusión | header_detect si page-count alto |
| 7 | art | corner_count + filename_glob | Página N/M en esquina cuando hay compilación; filename si individualizados | legacy_5phase |
| 8 | insgral | filename_glob | 1 PDF = 1 inspección | header_detect |
| 9 | bodega | filename_glob | mismo | none |
| 10 | maquinaria | filename_glob | mismo | none |
| 11 | ext | filename_glob | mismo | none |
| 12 | senal | filename_glob | mismo | none |
| 13 | exc | filename_glob | mismo | none |
| 14 | altura | filename_glob | mismo | header_detect (alto volumen, posible compilación) |
| 15 | caliente | filename_glob | mismo | none |
| 16 | herramientas_elec | filename_glob | mismo | none |
| 17 | andamios | filename_glob | mismo | none |
| 18 | chps | filename_glob | mismo | none |

**Decision rule per scanner** (uniforme):
1. Primero intentar la técnica primaria
2. Si la confianza < threshold (por scanner) → ejecutar fallback
3. Si fallback también baja confianza → `ConfidenceLevel.LOW`, `flags=["needs_review"]`

### 3.4 Shared utilities

```
core/scanners/utils/
├── filename_glob.py      # glob PDF + group by sigla del filename
├── header_detect.py      # OCR + busca códigos F-CRS-* en pages
├── corner_count.py       # OCR de esquina superior derecha "Página N de M"
├── page_count_heuristic.py  # flag compilación si pp >> esperado
└── empresa_breakdown.py  # roll up por subcarpeta empresa
```

Cada util ≤200 LOC. Los scanners individuales los componen.

### 3.5 Legacy 5-phase scanner

```python
# core/scanners/legacy_inference.py
class LegacyInferenceScanner:
    """Wrapper sobre core/phases/* — el motor 5-fases original.

    Disponible como override manual desde la UI cuando un scanner
    especializado falla. NO se ejecuta automáticamente.
    """
    sigla: str = "*"  # acepta cualquier sigla cuando se invoca manualmente

    def count(self, folder, *, override_method=None) -> ScanResult:
        # Wraps core/inference.py existing flow
        ...
```

### 3.6 Factory para scanners triviales

12-14 de los 18 scanners son `filename_glob` puro sin fallback (categorías 5, 8-13, 15-18 + tentativamente 1, 6, 9). Crear 12 archivos casi idénticos es boilerplate sin valor. Solución:

```python
# core/scanners/simple_factory.py
def make_simple_scanner(sigla: str, *, page_anomaly_threshold: int = 10) -> Scanner:
    """Build a filename_glob scanner with optional compilation-detected flag."""
    ...

# core/scanners/__init__.py
for sigla in ("reunion", "chintegral", "bodega", "maquinaria", "ext", "senal",
              "exc", "caliente", "herramientas_elec", "andamios", "chps",
              "insgral", "dif_pts"):
    register(make_simple_scanner(sigla))
```

Los scanners con técnica especializada (`art`, `odi`, `irl`, `charla`) tienen archivo propio en `core/scanners/<sigla>_scanner.py`.

### 3.7 Acceptance per custom scanner

Cada scanner con archivo propio debe:
1. Tener su archivo `core/scanners/<sigla>_scanner.py` (≤250 LOC)
2. Tener tests en `tests/scanners/test_<sigla>_scanner.py` con fixture real de ABRIL
3. Documentar su técnica + edge cases en docstring del módulo
4. Implementar el Scanner Protocol exactamente
5. Auto-registrarse al final del archivo

Para scanners simples (factory): un único test parametrizado en `tests/scanners/test_simple_factory.py` cubre todas las siglas triviales.

---

## 4. Modelo de datos

### 4.1 Storage backend

SQLite local en `data/overseer.db` (nueva DB, no extiende `sessions.db`).

**Concurrency model**: solo el **orchestrator** (proceso main) escribe a la DB. Los scanners corren en `multiprocessing.Pool` workers, devuelven `ScanResult` al orchestrator vía pool result, y el orchestrator persiste serialmente. Esto evita SQLite locks por contención de workers.

**Connection lifecycle**: una sola conexión persistente en el orchestrator + WAL mode habilitado para resiliencia ante crashes. Conexión cerrada en shutdown (FastAPI lifespan). Transacciones explícitas para writes multi-fila.

### 4.2 Schema

```sql
-- Sesión activa por mes (auto-saved)
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,    -- "2026-05" formato YYYY-MM
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    state_json TEXT NOT NULL,       -- ver SessionState schema abajo
    created_at TIMESTAMP NOT NULL,
    last_modified TIMESTAMP NOT NULL,
    status TEXT NOT NULL,           -- 'active' | 'finalized'
    CONSTRAINT status_valid CHECK (status IN ('active', 'finalized'))
);

CREATE INDEX idx_sessions_status ON sessions(status, last_modified);

-- Counts finalizados, fuente para reportes cross-mes
CREATE TABLE historical_counts (
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    hospital TEXT NOT NULL,         -- 'HPV', 'HRB', 'HLU', 'HLL'
    sigla TEXT NOT NULL,            -- 'art', 'irl', ...
    count INTEGER NOT NULL,
    confidence TEXT NOT NULL,
    method TEXT NOT NULL,
    finalized_at TIMESTAMP NOT NULL,
    PRIMARY KEY (year, month, hospital, sigla)
);

CREATE INDEX idx_historical_year ON historical_counts(year, month);
CREATE INDEX idx_historical_sigla ON historical_counts(sigla, year);
```

### 4.3 SessionState schema (state_json)

```python
@dataclass
class CellState:
    hospital: str         # 'HPV'
    sigla: str            # 'art'
    folder_path: str      # absolute path al folder
    last_result: ScanResult | None
    user_override: int | None       # corrección manual
    excluded: bool                  # usuario excluyó esta celda del cómputo
    custom_pdfs_added: list[str]    # paths a PDFs agregados manualmente
    custom_pdfs_excluded: list[str] # paths excluidos
    notes: str | None

@dataclass
class SessionState:
    month_folder: str                       # 'A:\\informe mensual\\ABRIL'
    cells: dict[tuple[str, str], CellState] # (hospital, sigla) → state
    settings_snapshot: dict                 # config en uso (scanners habilitados, etc.)
```

Serializado a JSON al guardar. Tamaño esperado por sesión: ~30-100 KB.

### 4.4 Lifecycle de sesión

```
[crear/abrir]              [escanear]               [finalizar]
SessionState.empty   →   cells populados   →   sessions.status='finalized'
                                                   + filas en historical_counts
                                                   + RESUMEN.xlsx escrito
```

**Idempotencia**: re-finalizar una sesión sobreescribe sus filas en `historical_counts` (UPSERT). El Excel también se re-genera. Daniel puede repetir el proceso si encuentra un error después.

### 4.5 Storage layer files

```
core/db/
├── connection.py        # singleton + context manager (≤100 LOC)
├── sessions_repo.py     # CRUD de sesiones (≤200 LOC)
├── historical_repo.py   # CRUD historical + queries cross-mes (≤200 LOC)
└── migrations.py        # init schema + futuros migrations (≤100 LOC)
```

---

## 5. Template Excel y outputs

### 5.1 Template propio

Ubicación: `data/templates/RESUMEN_template_v1.xlsx`

Estructura:
- **Hoja 1: "Cump. Programa Prevención"** — réplica del sample con celdas vacías que la app llena
- **Hoja 2: "Metadata"** — generación timestamp, scanners por celda, confianza, app version
- **Hoja 3: "Audit"** — per-empresa breakdown (rolled up de los scanners), útil para revisión

Cada celda a llenar tiene un **named range** en Excel:
```
HPV_reunion_count, HPV_irl_count, ..., HLL_chps_count
HPV_chargen_workers, HPV_chintegral_workers, ...  (workforce counts)
```

Beneficio: el writer no depende de posición de celda (G15, H22, etc.) → si el template cambia layout, no se rompe el writer. Solo importa que los named ranges existan.

### 5.2 Versionado de template

`RESUMEN_template_v1.xlsx`, `_v2.xlsx`, etc. El writer detecta versión por nombre de archivo. Breaking changes bump versión, app advierte si el usuario tiene un template viejo.

### 5.3 Writer

```python
# core/excel/writer.py
@dataclass(frozen=True)
class ExcelGenerationResult:
    output_path: Path
    cells_written: int
    warnings: list[str]    # ["named range XYZ not found", "value clipped", ...]
    duration_ms: int

def generate_resumen(
    session_state: SessionState,
    output_path: Path,
    template_path: Path = DEFAULT_TEMPLATE,
) -> ExcelGenerationResult:
    """Lee template, llena celdas usando named ranges, escribe a output_path."""
    ...
```

**Atomicity**: write-then-rename pattern. Escribe a `<output_path>.tmp` → fsync → rename atómico a `<output_path>`. Si target existe, primero `output_path → output_path.bak` antes del rename. Esto garantiza que `output_path` siempre es un Excel válido (nunca a medio-escribir).

Trabajo en **copy-and-modify**: nunca modificar el template directamente. `cp template → tmp → fill cells → save tmp → rename`.

### 5.4 Cross-month report (FASE 3)

Reporte separado: `RESUMEN_RANGE_<MES1>_<MES2>.xlsx` o similar.

Estructura tentativa:
- **Hoja 1: "Trend"** — tabla pivotada year+month como columnas, (hospital, sigla) como filas, counts como valores. Sparklines por fila.
- **Hoja 2: "Detail"** — datos crudos de `historical_counts` para el rango

Generado leyendo `historical_counts` con date range. No re-lee PDFs. Disponible solo para meses finalizados.

### 5.5 JSON export (FASE 3)

Mismo data que el Excel pero JSON estructurado:
```json
{
  "month": "2026-04",
  "generated_at": "2026-05-11T16:00:00",
  "scanners_used": {...},
  "cells": [
    {"hospital": "HPV", "sigla": "art", "count": 767, "confidence": "high", "method": "filename_glob"},
    ...
  ],
  "totals": {"HPV": 2184, "HRB": 406, "HLU": 67, "HLL": null}
}
```

Útil si futuras integraciones (Power BI, scripts custom) leen del JSON en vez del Excel.

---

## 6. API surface

### 6.1 Endpoints REST

Organizados por recurso, un archivo por recurso (`api/routes/<recurso>.py`).

```
GET    /api/months                                  list of available months (from informe mensual root)
GET    /api/months/{year}-{month}                   month metadata: 4 hospitals × 18 cats inventory
POST   /api/sessions                                create or open session for (year, month)
GET    /api/sessions/{session_id}                   get session state
DELETE /api/sessions/{session_id}                   discard session (active sessions only)
POST   /api/sessions/{session_id}/scan              trigger scan; body: {scope: "all"|"hospital:HPV"|"cell:HPV/art"}
POST   /api/sessions/{session_id}/scan/cancel       cancel running scan
PATCH  /api/sessions/{session_id}/cells/{hospital}/{sigla}
                                                    manual override / exclusion / notes
GET    /api/sessions/{session_id}/cells/{hospital}/{sigla}/files
                                                    list files in cell folder + per-file data
POST   /api/sessions/{session_id}/output            generate Excel; body: {target: "month_folder"|"custom_path"}
POST   /api/sessions/{session_id}/finalize          mark finalized + write historical_counts + generate output
GET    /api/reports/cross-month                     query historical_counts; params: from, to, hospitals[], siglas[]
POST   /api/reports/cross-month/export              generate cross-month Excel
GET    /api/settings                                user settings (template path, scanner toggles, rename policy)
PATCH  /api/settings                                update settings
GET    /api/pdfs                                    serve a PDF for viewer; param: path (absolute, validated against allowed roots)
GET    /api/health                                  app health + scanner registry status
```

**Validaciones críticas**:
- `/api/pdfs?path=...` debe validar path traversal. **Whitelist por default**: la `month_folder` de la sesión activa + los paths en `custom_pdfs_added`. Cualquier path fuera → 403. Implementación: `pathlib.Path.resolve()` + check `.is_relative_to(allowed_root)` contra cada root permitido.
- `PATCH /api/sessions/.../cells/...` con `user_override: int` validar `>= 0` y `<= MAX_REASONABLE_COUNT` (constante en `core/utils.py`, default 10000).
- Todos los `session_id` validados contra regex `^\d{4}-(0[1-9]|1[0-2])$` antes de usar.

### 6.2 WebSocket events

```
WS /ws/sessions/{session_id}

Event types:
  - scan.started        {scope, total_cells}
  - cell.scanning       {hospital, sigla, files_total}
  - cell.progress       {hospital, sigla, files_done, files_total}
  - cell.done           {hospital, sigla, result: ScanResult}
  - cell.error          {hospital, sigla, error}
  - scan.eta            {seconds_remaining, cells_remaining}
  - scan.complete       {cells_succeeded, cells_failed}
  - cell.corrected      {hospital, sigla, new_count, by: 'user'}
  - output.generating
  - output.complete     {path}
```

### 6.3 Backend infra reuse

- FastAPI sigue. Reusamos lifespan + WebSocket pattern.
- Cancellation: usar `asyncio.Event` para signalear cancel a scanners largos.
- Concurrency: orchestrator usa `multiprocessing.Pool` para paralelismo CPU-bound (Tesseract); async para I/O.

---

## 7. Frontend

### 7.1 Navigation model (drill-down)

```
┌─ Vista 1: MonthOverview ──────────────────────────────────────┐
│ Picker de mes (default: último encontrado en informe mensual) │
│ 4 cards de hospital con totales + barra de progreso            │
│ Click hospital → Vista 2                                        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─ Vista 2: HospitalDetail ─────────────────────────────────────┐
│ Header: "← Volver | HPV | [▶ Escanear todo]"                  │
│ Lista de 18 categorías con conteo, status, acciones por fila  │
│ Click categoría → expand side panel con detalle               │
│ Side panel: archivos, método, confianza, override, exclude    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─ Vista 3: Settings ────────────────────────────────────────────┐
│ Template path, scanner toggles, rename policy, API config     │
│ Modal accesible desde el ⚙ en cualquier vista                  │
└─────────────────────────────────────────────────────────────────┘
```

Mockups detallados en el companion (`navigation-flow.html`).

### 7.2 Componentes (inventory)

```
frontend/src/
├── views/
│   ├── MonthOverview.jsx        (≤200 LOC, container)
│   ├── HospitalDetail.jsx       (≤200 LOC, container)
│   └── SettingsModal.jsx        (≤200 LOC)
├── components/
│   ├── HospitalCard.jsx         card en MonthOverview
│   ├── CategoryRow.jsx          fila en HospitalDetail
│   ├── ScanIndicator.jsx        badge de status (✓⚠●✕○✎)
│   ├── ConfidenceBadge.jsx      pill HIGH/MEDIUM/LOW/MANUAL
│   ├── CellDetailPanel.jsx      side panel con detalle de celda
│   ├── ReviewModal.jsx          PDF viewer + correcciones (reuso parcial)
│   ├── ScanControls.jsx         Play/Pause/Skip/Resume
│   ├── ProgressFooter.jsx       barra + ETA en bottom
│   └── GenerateOutputButton.jsx
├── hooks/
│   ├── useSession.js            estado de sesión + WS connection
│   ├── useMonths.js             lista de meses disponibles
│   └── useScanProgress.js       suscripción a eventos WS
├── store/                       (existing Zustand, refactor liviano)
└── lib/
    ├── api.js                   client REST
    └── format.js                helpers
```

### 7.3 Estados de celda (badges)

| Icon | Estado | Significado |
|---|---|---|
| ○ gris | pending | No escaneada |
| ● azul | scanning | En progreso |
| ✓ verde | done_high | Cerrada, alta confianza |
| ⚠ amarillo | done_review | Cerrada pero flag (compilación detectada / fallback / etc.) |
| ✕ rojo | error | Scanner falló o filesystem error |
| ✎ violeta | manual | Usuario corrigió override |

### 7.4 Stack

- React 18 + Vite (ya en place)
- Zustand para state (ya en place; refactor a slices por feature)
- Tailwind + estilo del current design (paleta dark)
- react-zoom-pan-pinch para PDF viewer (ya en place)
- pdf.js para renderizar páginas en thumbnails (FASE 2)

### 7.5 Accesibilidad mínima

- Keyboard navigation entre cells (arrow keys)
- Tooltips con descripción completa (Categorías tienen siglas cortas)
- Status badges con `aria-label` describiendo el estado
- Color no es la única señal (icons + text)

---

## 8. Entrega por fases

### FASE 1 — MVP (~3 semanas)

**Scope**:
- Folder enumeration: dado `A:\informe mensual\<MES>\`, descubrir 4 hospitales × 18 categorías
- **Un único `simple_filename_scanner` parametrizable** (no 18 archivos casi idénticos) que sirve a las 12-14 categorías que solo necesitan glob. Los 4-6 que necesitan técnicas custom (ART, ODI, IRL, Charlas) se construyen en FASE 2 — en FASE 1 también usan `simple_filename_scanner` como baseline
- `page_count_heuristic.py` util (~50 LOC): flag `compilation_detected` cuando `total_pages_in_folder / num_pdfs > umbral_por_sigla`. Usado solo para badges, no para conteo
- Storage layer (sessions + historical, schema completo, sin queries cross-mes)
- API endpoints básicos: months, sessions, scan, output (sin cancel, sin overrides)
- Frontend: MonthOverview + HospitalDetail (sin Settings, sin side panel detallado, sin viewer)
- Excel writer: template propio + named ranges + generate básico
- Tests por scanner con fixtures ABRIL + write-guard que falla loud si un test escribe a `A:\informe mensual\`

**Acceptance**:
- Abrir `A:\informe mensual\ABRIL` → ver los 4 hospitales en < 2s
- Click HPV → 18 categorías con counts en < 5s (filename-glob es instant)
- Click Generar Resumen → archivo Excel correcto en `data/outputs/RESUMEN_ABRIL_2026.xlsx`
- HRB ODI y HLU ODI muestran badge ⚠ ("compilation_detected") porque page-count >> esperado (queda para FASE 2)
- 54 celdas (HPV+HRB+HLU - 3 compilaciones - HLL no normalizado) tienen valor correcto vs conteo manual
- 0 violaciones de ruff
- Todos los tests pasan

**Out of scope FASE 1**: OCR scanners, correcciones manuales, side panel viewer, settings, cross-month, rename, ETA, JSON export.

### FASE 2 — OCR para compilaciones + correcciones (~3 semanas)

**Scope**:
- Scanners OCR para los tipos con compilaciones: ODI, IRL, ART (con técnicas header_detect / corner_count)
- Shared utils: `header_detect.py`, `corner_count.py`, `page_count_heuristic.py`
- Side panel completo con detalle de celda + per-file breakdown
- ReviewModal con PDF viewer + corrección manual
- API: PATCH cells/.../override, cancel scan, files endpoint
- Frontend: ScanControls (Play/Pause/Cancel), ProgressFooter con progreso real
- Persistencia: sesión por mes con auto-save cada cambio
- Re-finalizar: idempotente, UPSERT en historical_counts

**Acceptance**:
- HRB ODI cuenta correctamente las ~17 ODIs en su PDF compilado de 34 páginas
- Daniel puede corregir un count manualmente y el Excel reflejado
- Cerrar la app y reabrirla retorna a la sesión exacta donde quedaste
- Cancelación de scan toma < 3s
- Tests E2E del flujo completo (abrir → scan → corregir → finalizar → generar)

**Out of scope FASE 2**: cross-month, rename, JSON, métricas dashboard, settings UI.

### FASE 3 — Cross-month + rename + polish (~2 semanas)

**Scope**:
- Cross-month report: query historical, generar Excel comparativo
- Folder rename automation: `7.-ART` → `7.-ART 934` (opt-in en Settings, preview obligatorio)
- File rename suggestions: si filename no matchea convención, sugerir corrección (no aplicar automático)
- JSON export
- ETA accurate (basado en historial de scanners)
- Settings UI completa
- Métricas dashboard mínimo (counts totales por mes, top scanners-fallaron, tiempo invertido)
- Skip/add files via UI (custom_pdfs_added, custom_pdfs_excluded)

**Acceptance**:
- Cross-month report FEBRERO + MARZO + ABRIL genera Excel en < 10s
- Rename con preview muestra "antes/después" para los 18 folders + opción cancelar
- JSON export tiene mismo data que Excel + scanners metadata
- Settings persisten entre sesiones
- App estable con corpus reales (HPV ART 767 archivos en < 30s)

### Cross-phase concerns (continuos)

- Documentation: cada fase actualiza el README + memorias relevantes
- Tests: cobertura crece per fase (FASE 1 ~60%, FASE 2 ~80%, FASE 3 ~85%)
- Performance budget: full month scan < 2 min para ABRIL HPV (la obra más grande)

---

## 9. Error handling

### 9.1 Principios

1. **Scanner failures NO matan el run**: el orchestrator captura excepciones por celda, marca esa celda como error, continúa con el resto.
2. **Sin-dato > dato-incorrecto**: si un scanner no puede determinar confiablemente, devuelve `ConfidenceLevel.LOW + flags` en vez de adivinar. El humano decide.
3. **Errores filesystem son fatales del scan, no del run**: si la carpeta de mes no existe, la app muestra error y bloquea acciones; no intenta "adivinar".
4. **DB writes en transacciones**: cada finalize es atómico — o se escribe todo (historical + sesión finalized + archivo Excel) o nada.

### 9.2 Casos específicos

| Caso | Comportamiento |
|---|---|
| Carpeta de mes no existe | Error al abrir sesión, mensaje claro al usuario |
| Carpeta de hospital falta (ej. HLL ABRIL) | Mostrar card "no normalizado", excluir de cálculos, no error |
| Carpeta de categoría falta | Asumir count = 0, badge "○ pending" |
| PDF corrupto | Scanner falla con error específico, celda en ✕, mensaje en panel |
| Permission denied | Error claro, mensaje sobre permisos requeridos |
| Excel template no encontrado | Bloquear Generar Resumen, mensaje con path esperado |
| Excel write falla (target en uso) | Write-then-rename garantiza el original intacto. Reintentar 1x, si falla, mostrar error y sugerir cerrar Excel. NO marcar la sesión como finalized si Excel falló |
| Finalize parcial (DB write OK, Excel falla) | Compensating action: rollback `historical_counts` rows + revertir `sessions.status` a 'active'. Único orden válido: Excel `.tmp` → DB transaction → rename Excel a final. Si rename falla, ya está en disco como `.tmp` → manual recovery posible |
| WS disconnect | Frontend muestra banner, reintenta cada 3s, no pierde estado (estado vive en DB) |
| Override negative o no numérico | API rechaza con 400 + mensaje validation |
| Sesión finalizada modificada | Pedir confirmación, re-finalizar UPSERT |

### 9.3 Logging

- Backend: `logging.getLogger(__name__)`, sin `print()` (hookify rule)
- Niveles: INFO para acciones del usuario, WARNING para fallbacks, ERROR para fallos
- Log file en `data/logs/overseer.log`, rotación diaria (max 30 días)
- Frontend: errors al panel + console.error con id de correlación

---

## 10. Estrategia de testing

### 10.1 Capas de tests

```
tests/
├── unit/
│   ├── scanners/
│   │   ├── test_art_scanner.py
│   │   ├── test_irl_scanner.py
│   │   ├── ...                       (18 archivos, uno por sigla)
│   │   └── utils/
│   │       ├── test_filename_glob.py
│   │       ├── test_header_detect.py
│   │       └── test_corner_count.py
│   ├── test_orchestrator.py
│   ├── test_excel_writer.py
│   └── db/
│       ├── test_sessions_repo.py
│       └── test_historical_repo.py
├── integration/
│   ├── test_abril_full_corpus.py     ABRIL HPV+HRB+HLU end-to-end
│   ├── test_session_persistence.py   abrir/cerrar/reabrir
│   ├── test_excel_generation.py      template → output con datos reales
│   └── test_cross_month_report.py
└── e2e/
    └── test_smoke.py                 abrir app, scan minimal, generate
```

### 10.2 Fixtures

- **Reuso del corpus real**: `A:\informe mensual\ABRIL\HPV\` etc. — los tests apuntan a estos folders en read-only mode
- **Write-guard contra el corpus**: `tests/conftest.py` define un autouse fixture que monkey-patches `Path.write_*`, `Path.unlink`, `shutil.copy*`, `os.rename` para FALLAR loud si el target está dentro de `A:\informe mensual\` o `A:\estadistica mensual\`. Garantiza que ningún test (intencional o accidental) corrompa el corpus de origen
- **No mocking de DB**: cada test crea DB temporal con `tmp_path` fixture (regla del proyecto)
- **No mocking de Tesseract**: ejecutamos OCR real en tests (más lento pero realista). Tests OCR pesados marcados con `@pytest.mark.slow` para CI fast/full split.
- **No fabricar fixtures**: los counts conocidos vienen de las celdas del RESUMEN sample. Cualquier número en un test viene de un PDF real (regla `feedback_art670_fixture_disaster`).

### 10.3 Coverage targets

| Capa | FASE 1 | FASE 2 | FASE 3 |
|---|---|---|---|
| Scanners | 100% scanner files (smoke) | 80% lines | 85% lines |
| Orchestrator | 70% | 85% | 90% |
| API | 60% | 80% | 85% |
| Excel writer | 80% | 90% | 90% |
| DB layer | 90% | 95% | 95% |
| Frontend | manual smoke | RTL básico | RTL + Playwright E2E |

### 10.4 Comandos

```bash
pytest                              # full suite
pytest -m "not slow"                # fast tier (skip OCR-heavy)
pytest tests/scanners/              # solo scanners
pytest --cov=core --cov-report=html # coverage
```

---

## 11. Plan de migración

### 11.1 Filesystem changes

Crear nuevas estructuras sin tocar las viejas inicialmente:

```
core/
├── scanners/         (nuevo)
├── orchestrator.py   (nuevo)
├── db/               (nuevo)
├── excel/            (nuevo)
├── ocr.py            (sin cambios, lo usan scanners)
├── inference.py      (sin cambios; será wrapped en scanners/legacy_inference.py al final de FASE 1)
└── phases/           (sin cambios inicialmente)

api/
├── routes/           (nuevo)
├── ws.py             (nuevo, simplificado del current)
├── state.py          (modificado: nuevo session_manager)
└── (viejos archivos eventualmente retirados)

frontend/src/
├── views/            (nuevo)
├── components/       (nuevo, algunos reusan código del existing)
└── (componentes viejos eventualmente borrados)

data/
├── overseer.db       (nuevo)
├── sessions.db       (existente, lo dejamos por compat)
├── templates/        (nuevo)
└── outputs/          (nuevo)
```

### 11.2 Coexistencia durante FASE 1

Durante FASE 1, la app vieja sigue funcional para no perder la capacidad de procesar PDFs individuales. Acceso por toggle en header: "Modo nuevo / Modo legacy".

Al final de FASE 2, retirar el modo legacy.

### 11.3 Datos históricos (sessions.db existente)

**Decisión**: NO migrar. La DB actual tiene formato single-PDF que no calza con el nuevo modelo mes-céntrico. Daniel re-cuenta los meses que necesite cross-mes report (ABRIL y posteriores).

Si en el futuro hay que rescatar datos viejos, hay un script ad-hoc fuera del scope de este overhaul.

### 11.4 Branch + commits

- Rama de trabajo: `research/pixel-density` (decisión usuario)
- Commits granulares, uno por feature/módulo cerrado
- Hooks de calidad: ruff check + format en cada commit (PostToolUse ya lo aplica)
- Cuando FASE 1 esté completa, merge to `master` opcional (decisión usuario al final)

---

## 12. Riesgos y mitigaciones

### 12.1 Riesgos técnicos

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Scanner accuracy variable por tipo | Alta | Medio | Per-scanner tests con fixtures reales; badge confianza explícito |
| Template Excel se desfasa | Media | Bajo | Named ranges (no posición); versionado |
| Filesystem write permissions | Media | Medio | Pedir permisos al setup; fallback a custom path |
| Pixel-density / legacy engine fail en ART | Baja | Bajo | filename_glob es la primaria; legacy es fallback |
| OCR Tesseract lento en HPV ART 767 PDFs | Alta | Medio | Paralelismo multiprocessing.Pool 6-10 workers (ya en project); progress feedback |
| DB corrupcion (SQLite locked) | Baja | Alto | WAL mode + close on shutdown; backup automático antes de finalize |
| Concurrencia sesión + scan en paralelo | Media | Medio | Lock por sesión; scan no permite ediciones simultáneas |

### 12.2 Riesgos de proceso

| Riesgo | Mitigación |
|---|---|
| Scope creep (FASE 1 absorbe features de FASE 2) | Acceptance criteria explícitos; not-in-scope listado per fase |
| Tentación de reintroducir VLM | Spec explícita: NO VLM (sección 1.3); requiere nuevo postmortem para revivir |
| Pixel-density research bloqueado por overhaul | Pixel density vive en `core/scanners/legacy_inference.py` y `eval/pixel_density/`, no se toca el research |
| Memorias y docs se desfasan | Cada fase actualiza memorias + MEMORY.md como parte del DoD |

### 12.3 Riesgos de UX

| Riesgo | Mitigación |
|---|---|
| Daniel pierde datos por error de rename | Rename opt-in + preview obligatorio + backup |
| Confusión multi-mes | Picker prominente, mes activo en header siempre visible |
| OCR scanner timeout sin feedback | Progress events cada 1s, cancelación accesible |
| Excel generado sobreescribe trabajo | Confirmación si target ya existe; backup .bak |

---

## 13. Decisiones diferidas a implementación

Cosas que NO se deciden en este spec — se resuelven al construir cada parte:

1. **PDF viewer**: pdf.js vs iframe vs pdf-lib. Elegir cuando se construya ReviewModal en FASE 2.
2. **Notificaciones de error**: toast vs modal vs inline. Decidir en frontend impl.
3. **Cómo se serializan los flags en JSON output**: array de strings vs objetos con metadata. Decidir cuando se diseñe JSON export FASE 3.
4. **Threshold de page-count para flag compilación**: 10pp? 15pp? Calibrar con corpus real.
5. **Tesseract PSM mode por scanner**: experimentación per scanner en FASE 2.
6. **Cross-month report layout exacto**: pivot vs long-format vs ambos. Decidir cuando se construya.
7. **Logging level default**: INFO vs WARNING. Decidir tras observar volumen real.
8. **Settings storage**: SQLite vs JSON file vs env vars. Probablemente JSON file en `data/config.json`.

---

## Apéndice A — Glosario

| Término | Significado |
|---|---|
| Celda | Una intersección (hospital, sigla) que tiene que tener un count |
| Sigla | Una de las 18 categorías canónicas (`art`, `irl`, `odi`, ...) |
| Obra / Hospital | HPV, HRB, HLU, HLL |
| Scanner | Módulo Python que cuenta documentos en una carpeta usando una técnica específica |
| Compilación | 1 PDF que contiene N documentos internos (no marcado como compilado explícitamente) |
| Resumen | El archivo Excel mensual final (`RESUMEN_<MES>_<AÑO>.xlsx`) |
| Finalize | Mover sesión de active → finalized + escribir historical + generar Excel |

## Apéndice B — Referencias

- `docs/research/2026-05-11-abril-corpus-audit.md` — corpus audit completo
- `docs/superpowers/reports/2026-03-29-vlm-integration-postmortem.md` — por qué NO VLM
- `A:\estadistica mensual\SUMARIO_PANORAMA_GENERAL.md` — workflow upstream/downstream
- `A:\estadistica mensual\guia_estadisticas_seguridad_excel.md` — Excel best practices
- `A:\informe mensual\.serena\memories\` — convenciones upstream
- Memorias auto-loaded: `project_pdfoverseer_purpose.md`, `reference_external_workflow.md`
