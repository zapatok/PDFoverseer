# Plan: Reorganización de eval/ por etapas de investigación

**Fecha:** 2026-03-28
**Objetivo:** Separar `eval/` en carpetas por etapa de investigación, extraer código compartido, centralizar tests.

---

## Principios de diseño

1. **Sin duplicación de código** — funciones compartidas van en `eval/shared/`
2. **Tests centralizados** en `eval/tests/` (solo 5 archivos, no justifica dispersar)
3. **Fixtures, ground_truth, extractors** quedan en `eval/` raíz (usados por todos)
4. **Cada etapa** tiene su código, params, resultados, y un POSTMORTEM.md
5. **Renombrar prefijos redundantes** (ej: `ocr_preprocess.py` → `preprocess.py` dentro de `ocr_preprocessing/`)
6. **Documentación** se mueve a cada etapa bajo `docs/`
7. **Imports** usan paths completos (`from eval.shared.loaders import ...`)

---

## Etapas identificadas

| # | Etapa | Descripción |
|---|-------|-------------|
| 1 | **inference_tuning** | Sweep de parámetros del motor de inferencia (sweep1→sweep4) |
| 2 | **graph_inference** | Motor experimental HMM+Viterbi + híbrido + comparación |
| 3 | **ocr_preprocessing** | Preprocesamiento de imagen antes de Tesseract |
| 4 | **ocr_engines** | Evaluación de motores OCR alternativos (EasyOCR, PaddleOCR) |

---

## Código compartido identificado

Funciones duplicadas entre archivos que se extraen a `eval/shared/`:

| Función | Origen actual | Usado por |
|---------|---------------|-----------|
| `load_fixtures()` | sweep.py, graph_sweep.py, compare_engines.py (3 copias) | inference_tuning, graph_inference |
| `load_ground_truth()` | sweep.py, graph_sweep.py, compare_engines.py (3 copias) | inference_tuning, graph_inference |
| `PageRead` (dataclass) | inference.py, graph_inference.py (2 definiciones idénticas) | todas las etapas |
| `Document` (dataclass) | inference.py, graph_inference.py (2 definiciones idénticas) | inference_tuning, graph_inference |

**Plan:** Crear `eval/shared/types.py` (PageRead, Document) y `eval/shared/loaders.py` (load_fixtures, load_ground_truth). Los engines y sweeps importan de ahí.

> **Nota sobre score_config():** Aunque sweep.py y graph_sweep.py tienen funciones de scoring similares, NO son idénticas — cada una usa métricas diferentes adaptadas a su motor. Se quedan en sus respectivos sweeps.

---

## Estructura propuesta

```
eval/
├── __init__.py
├── README.md                            # reescribir con nueva estructura
├── ground_truth.json                    # compartido (raíz)
├── extract_fixtures.py                  # compartido (one-time, extrae fixtures de todos los PDFs)
├── extract_art674_tess.py               # compartido (one-time, extrae fixture Tesseract para ART_674)
│
├── fixtures/                            # compartido — sin cambios
│   ├── real/
│   ├── synthetic/
│   ├── degraded/
│   └── archived/
│
├── shared/                              # ── NUEVO: código compartido ──
│   ├── __init__.py
│   ├── types.py                         # PageRead, Document (extraídos de inference.py)
│   └── loaders.py                       # load_fixtures(), load_ground_truth()
│
├── tests/                               # ── CENTRALIZADO (sin cambios de ubicación) ──
│   ├── __init__.py
│   ├── test_inference.py                # actualizar imports
│   ├── test_sweep_scoring.py            # actualizar imports
│   ├── test_graph_inference.py          # actualizar imports
│   ├── test_ocr_preprocess.py           # → test_preprocess.py (renombrar)
│   └── test_benchmark.py               # actualizar imports
│
├── inference_tuning/                    # ── ETAPA 1 ──
│   ├── __init__.py
│   ├── inference.py                     # ← eval/inference.py (quitar PageRead/Document, importar de shared)
│   ├── params.py                        # ← eval/params.py
│   ├── sweep.py                         # ← eval/sweep.py (quitar load_fixtures/gt, importar de shared)
│   ├── report.py                        # ← eval/report.py
│   ├── baseline_art674.py               # ← eval/baseline_art674.py
│   ├── baseline_art674_tess.py          # ← eval/baseline_art674_tess.py
│   ├── results/                         # ← eval/results/sweep_*.json
│   ├── docs/                            # ← docs/superpowers/ (relacionados a inference)
│   └── POSTMORTEM.md
│
├── graph_inference/                     # ── ETAPA 2 ──
│   ├── __init__.py
│   ├── engine.py                        # ← eval/graph_inference.py (renombrar, quitar PageRead/Document)
│   ├── params.py                        # ← eval/graph_params.py (renombrar sin prefijo)
│   ├── sweep.py                         # ← eval/graph_sweep.py (quitar load_fixtures/gt)
│   ├── hybrid.py                        # ← eval/hybrid_inference.py (renombrar)
│   ├── compare.py                       # ← eval/compare_engines.py (renombrar)
│   ├── results/                         # ← eval/results/graph_sweep_*.json
│   ├── docs/
│   └── POSTMORTEM.md
│
├── ocr_preprocessing/                   # ── ETAPA 3 ──
│   ├── __init__.py
│   ├── preprocess.py                    # ← eval/ocr_preprocess.py (sin prefijo ocr_)
│   ├── params.py                        # ← eval/ocr_params.py (sin prefijo ocr_)
│   ├── sweep.py                         # ← eval/ocr_sweep.py (sin prefijo ocr_)
│   ├── report.py                        # ← eval/ocr_report.py (sin prefijo ocr_)
│   ├── results/                         # ← eval/results/ocr_*.json
│   ├── docs/
│   └── POSTMORTEM.md
│
├── ocr_engines/                         # ── ETAPA 4 (sin results/: output va a data/) ──
│   ├── __init__.py
│   ├── benchmark.py                     # ← eval/ocr_benchmark.py (sin prefijo ocr_)
│   ├── docs/
│   └── POSTMORTEM.md
│
└── results/                             # vacío + .gitkeep (resultados migran a cada etapa)
    └── .gitkeep
```

---

## Movimiento de archivos

### Código

| Origen | Destino | Renombrado | Notas |
|--------|---------|------------|-------|
| eval/inference.py | eval/inference_tuning/inference.py | — | Quitar PageRead/Document → importar de shared |
| eval/params.py | eval/inference_tuning/params.py | — | |
| eval/sweep.py | eval/inference_tuning/sweep.py | — | Quitar load_fixtures/load_gt → importar de shared |
| eval/report.py | eval/inference_tuning/report.py | — | |
| eval/baseline_art674.py | eval/inference_tuning/baseline_art674.py | — | |
| eval/baseline_art674_tess.py | eval/inference_tuning/baseline_art674_tess.py | — | |
| eval/graph_inference.py | eval/graph_inference/engine.py | ✓ | Quitar PageRead/Document |
| eval/graph_params.py | eval/graph_inference/params.py | ✓ | |
| eval/graph_sweep.py | eval/graph_inference/sweep.py | ✓ | Quitar load_fixtures/load_gt |
| eval/hybrid_inference.py | eval/graph_inference/hybrid.py | ✓ | |
| eval/compare_engines.py | eval/graph_inference/compare.py | ✓ | |
| eval/ocr_preprocess.py | eval/ocr_preprocessing/preprocess.py | ✓ | |
| eval/ocr_params.py | eval/ocr_preprocessing/params.py | ✓ | |
| eval/ocr_sweep.py | eval/ocr_preprocessing/sweep.py | ✓ | |
| eval/ocr_report.py | eval/ocr_preprocessing/report.py | ✓ | |
| eval/ocr_benchmark.py | eval/ocr_engines/benchmark.py | ✓ | |

### Tests (renombrar en su lugar)

| Origen | Destino | Notas |
|--------|---------|-------|
| eval/tests/test_ocr_preprocess.py | eval/tests/test_preprocess.py | Renombrar sin prefijo redundante |
| eval/tests/test_benchmark.py | — | Solo actualizar imports |
| eval/tests/test_inference.py | — | Solo actualizar imports |
| eval/tests/test_sweep_scoring.py | — | Solo actualizar imports |
| eval/tests/test_graph_inference.py | — | Solo actualizar imports |

---

## Nuevo: eval/shared/

### eval/shared/types.py

Extraer de `eval/inference.py`:

```python
"""Shared data types for all eval engines."""
from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class PageRead:
    pdf_page:   int
    curr:       int | None
    total:      int | None
    method:     str
    confidence: float
    # Internal flag set during inference (not in fixture JSON — has default):
    _ph1_orphan_candidate: bool = field(default=False, repr=False, compare=False)

@dataclass
class Document:
    index:          int
    start_pdf_page: int
    declared_total: int
    pages:          list[int] = field(default_factory=list)
    inferred_pages: list[int] = field(default_factory=list)
    sequence_ok:    bool      = True

    @property
    def found_total(self) -> int:
        return len(self.pages) + len(self.inferred_pages)

    @property
    def is_complete(self) -> bool:
        return self.sequence_ok and self.found_total == self.declared_total
```

### eval/shared/loaders.py

Extraer de `eval/sweep.py`:

```python
"""Shared fixture/ground-truth loaders for all eval sweeps."""
from __future__ import annotations
import json
from pathlib import Path
from .types import PageRead  # relative import: intra-package, no sys.path needed

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
GROUND_TRUTH_PATH = Path(__file__).parent.parent / "ground_truth.json"

def load_fixtures() -> list[dict]:
    fixtures = []
    for path in sorted(FIXTURES_DIR.rglob("*.json")):
        if "archived" in path.parts:
            continue
        data = json.loads(path.read_text())
        data["reads"] = [PageRead(**r) for r in data["reads"]]
        fixtures.append(data)
    return fixtures

def load_ground_truth() -> dict[str, dict]:
    return json.loads(GROUND_TRUTH_PATH.read_text())
```

> **Nota:** `loaders.py` usa import relativo (`from .types`) para no depender de `sys.path`. Los paths a fixtures usan `Path(__file__).parent.parent` (relativo al módulo), no paths hardcodeados.

---

## Cambios de imports por archivo

### Principio general

- Todos los `sys.path.insert` apuntan al **repo root** (`Path(__file__).parent.parent.parent` para archivos en subcarpetas de eval/)
- Imports internos usan paths completos: `from eval.shared.types import PageRead`
- Paths a fixtures/results usan `Path(__file__)` relativo, nunca hardcodeados

### inference_tuning/

| Archivo | Cambios |
|---------|---------|
| **inference.py** | Quitar definición de `PageRead`, `Document` → `from eval.shared.types import PageRead, Document`; `sys.path`: `parent.parent.parent` |
| **params.py** | Sin cambios internos (no importa de eval/) |
| **sweep.py** | `from eval.inference` → `from eval.inference_tuning.inference`; `from eval.params` → `from eval.inference_tuning.params`; quitar `load_fixtures`/`load_ground_truth` → `from eval.shared.loaders import ...`; FIXTURES_DIR/GT_PATH eliminados; RESULTS_DIR → `Path(__file__).parent / "results"` |
| **report.py** | `from eval.params` → `from eval.inference_tuning.params` (**ojo: late import en línea ~57 dentro de función**, no solo module-level); RESULTS_DIR → `Path(__file__).parent / "results"` |
| **baseline_art674.py** | `from eval.inference` → `from eval.inference_tuning.inference`; `from eval.params` → `from eval.inference_tuning.params`; fixture path → `Path(__file__).parent.parent / "fixtures/real/ART_674.json"` |
| **baseline_art674_tess.py** | Ídem baseline_art674.py con ART_674_tess.json |

### graph_inference/

| Archivo | Cambios |
|---------|---------|
| **engine.py** | Quitar `PageRead`, `Document` → `from eval.shared.types import ...`; sin otros cambios |
| **params.py** | Sin cambios (era graph_params.py, self-contained) |
| **sweep.py** | `from eval.graph_inference` → `from eval.graph_inference.engine`; `from eval.graph_params` → `from eval.graph_inference.params`; quitar load_fixtures/gt → `from eval.shared.loaders`; RESULTS_DIR → `Path(__file__).parent / "results"` |
| **hybrid.py** | `from eval.graph_inference` → `from eval.graph_inference.engine` (solo `extract_documents`, `viterbi_decode`); `from eval.inference` → `from eval.inference_tuning.inference` (solo `_detect_period`, `_infer`); `Document, PageRead` → `from eval.shared.types import Document, PageRead` (no re-exportar transitivamente) |
| **compare.py** | `from eval.graph_inference` → `from eval.graph_inference.engine`; `from eval.hybrid_inference` → `from eval.graph_inference.hybrid`; `from eval.inference` → `from eval.inference_tuning.inference`; `PageRead` → `from eval.shared.types import PageRead`; quitar load_fixtures/gt → `from eval.shared.loaders` |

### ocr_preprocessing/

| Archivo | Cambios |
|---------|---------|
| **preprocess.py** | `sys.path`: `parent.parent.parent`; `from core.image import _deskew` se mantiene |
| **params.py** | Sin cambios (self-contained) |
| **sweep.py** | `from eval.ocr_params` → `from eval.ocr_preprocessing.params`; `from eval.ocr_preprocess` → `from eval.ocr_preprocessing.preprocess`; `from core.utils import _parse` se mantiene; `_ROOT` → `Path(__file__).parent.parent.parent` (un `.parent` extra por subcarpeta); `DATA_DIR` = `_ROOT / "data" / "ocr_all"` (sin cambio lógico); `INDEX_CSV` = `DATA_DIR / "all_index.csv"` (sin cambio); RESULTS_DIR → `Path(__file__).parent / "results"` |
| **report.py** | `from eval.ocr_params` → `from eval.ocr_preprocessing.params`; RESULTS_DIR → `Path(__file__).parent / "results"` |

### ocr_engines/

| Archivo | Cambios |
|---------|---------|
| **benchmark.py** | `sys.path`: `parent.parent.parent`; `from core.*` se mantiene; `FIXTURE_PATH` → `Path(__file__).parent.parent / "fixtures/real/ART_674.json"`; `PDF_PATH` → `Path(__file__).parent.parent.parent / "data/samples/ART_670.pdf"` (CWD-relativo → `__file__`-relativo); `OUTPUT_PATH` → `Path(__file__).parent.parent.parent / "data/benchmark_results.json"`; corregir `from typing import Optional` → usar `X \| None` (hookify: no-legacy-typing). **Nota:** `load_fixture()` (singular, con path arg) NO es duplicado de `load_fixtures()` — se queda en benchmark.py |

### tests/ (actualizar imports, no mover)

| Archivo | Cambios |
|---------|---------|
| **test_inference.py** | `from eval.inference` → `from eval.inference_tuning.inference`; `from eval.params` → `from eval.inference_tuning.params`; `PageRead` → `from eval.shared.types import PageRead` |
| **test_sweep_scoring.py** | `from eval.inference` → `from eval.inference_tuning.inference`; `from eval.params` → `from eval.inference_tuning.params`; `from eval.sweep` → `from eval.inference_tuning.sweep` |
| **test_graph_inference.py** | `from eval.graph_inference` → `from eval.graph_inference.engine`; `PageRead` → `from eval.shared.types import PageRead` |
| **test_preprocess.py** | `from eval.ocr_params` → `from eval.ocr_preprocessing.params`; `from eval.ocr_preprocess` → `from eval.ocr_preprocessing.preprocess` |
| **test_benchmark.py** | `from eval.ocr_benchmark` → `from eval.ocr_engines.benchmark` |

---

## Movimiento de documentación

### Etapa 1: inference_tuning/docs/

| Destino | Origen |
|---------|--------|
| specs/eval-harness-design.md | docs/superpowers/specs/2026-03-15-eval-harness-design.md |
| specs/inference-tuning-design.md | docs/superpowers/specs/2026-03-16-inference-tuning-design.md |
| specs/inference-phase-c.md | docs/superpowers/specs/2026-03-18-inference-phase-c.md |
| specs/inference-tuning-v2.md | docs/superpowers/specs/2026-03-18-inference-tuning-v2.md |
| plans/eval-harness.md | docs/superpowers/plans/2026-03-15-eval-harness.md |
| plans/inference-tuning.md | docs/superpowers/plans/2026-03-16-inference-tuning.md |
| plans/inference-phase-c.md | docs/superpowers/plans/2026-03-18-inference-phase-c.md |
| plans/inference-tuning-v2.md | docs/superpowers/plans/2026-03-18-inference-tuning-v2.md |
| plans/soft-alignment.md | docs/superpowers/plans/2026-03-21-inference-soft-alignment-plan.md |
| plans/new-params-exploration.md | docs/superpowers/plans/2026-03-27-new-params-exploration.md |
| plans/art674-tess-fixture.md | docs/superpowers/plans/2026-03-27-art674-tess-fixture.md |
| plans/art674-tess-sweep.md | docs/superpowers/plans/2026-03-27-art674-tess-sweep.md |
| reports/sweep3-option-a.md | docs/superpowers/reports/2026-03-27-sweep3-option-a.md |
| reports/6ph-t2-final-analysis.md | docs/superpowers/reports/6ph-t2-final-analysis.md |
| reports/regex-guard-sweep.md | docs/superpowers/reports/2026-03-26-regex-guard-sweep.md |

### Etapa 2: graph_inference/docs/

| Destino | Origen |
|---------|--------|
| specs/graph-inference-design.md | docs/superpowers/specs/2026-03-23-graph-inference-design.md |
| plans/graph-inference.md | docs/superpowers/plans/2026-03-23-graph-inference.md |

### Etapa 3: ocr_preprocessing/docs/

| Destino | Origen |
|---------|--------|
| specs/preprocess-sweep.md | docs/superpowers/specs/2026-03-24-ocr-preprocess-sweep.md |
| specs/preprocess-v2-design.md | docs/superpowers/specs/2026-03-27-ocr-preprocess-v2-design.md |
| specs/dpi300-tesseract-postmortem.md | docs/superpowers/specs/2026-03-25-dpi300-tesseract-postmortem.md |
| specs/confidence-gating-design.md | docs/superpowers/specs/2026-03-25-ocr-confidence-gating-design.md |
| plans/preprocess-sweep.md | docs/superpowers/plans/2026-03-24-ocr-preprocess-sweep.md |
| plans/preprocess-sweep-v1b.md | docs/superpowers/plans/2026-03-25-preprocess-sweep.md |
| plans/preprocess-v2.md | docs/superpowers/plans/2026-03-27-ocr-preprocess-v2.md |
| plans/tier1b-dpi300.md | docs/superpowers/plans/2026-03-25-tier1b-dpi300.md |
| plans/confidence-gating.md | docs/superpowers/plans/2026-03-25-ocr-confidence-gating.md |
| reports/preprocess-v2-investigation.md | docs/superpowers/reports/2026-03-28-ocr-preprocess-v2-investigation.md |

### Etapa 4: ocr_engines/docs/

| Destino | Origen |
|---------|--------|
| specs/benchmark-design.md | docs/superpowers/specs/2026-03-23-ocr-benchmark-design.md |
| plans/benchmark-art670.md | docs/superpowers/plans/2026-03-25-ocr-benchmark-art670.md |
| reports/easyocr-paddle-postmortem.md | docs/superpowers/reports/2026-03-25-easyocr-paddle-postmortem.md |

### Documentación que NO se mueve (no es eval)

Quedan en `docs/superpowers/`:
- crop-selector, pixel-density, core-modularization, server-modularization, deskew
- frontend-cleanup, tray-and-metrics, ui-audit, ui-implementation
- vlm-ocr-prototype, vlm-resolver, art670-vlm-rescan, art674-vlm-rescan
- ocr-failure-capture, ocr-matcher, word-anchor-fallback, project-hygiene
- session-review, system-audit
- **eval-reorganization plan** (este documento)

---

## Movimiento de resultados

| Destino | Pattern de archivos |
|---------|---------------------|
| inference_tuning/results/ | eval/results/sweep_*.json |
| graph_inference/results/ | eval/results/graph_sweep_*.json |
| ocr_preprocessing/results/ | eval/results/ocr_*.json, ocr_preprocess_v2_*.json, ocr_tier1_*.json, ocr_mini_*.json |

---

## Postmortems a crear

### 1. inference_tuning/POSTMORTEM.md

- Historia sweep1→sweep2→sweep3→sweep4, evolución de parámetros
- soft-alignment, phase C, D-S post-validation
- Resultados: composite score por sweep (111→122)
- s2t-helena → s2t4-helena → s2t5-vlm: versiones del motor
- Lecciones: eval-first workflow, fixture groups
- Regex guard sweep: por qué `tot<=10` es óptimo
- Fuentes: manual_test_logs/, sweep results, memory files

### 2. graph_inference/POSTMORTEM.md

- Motivación: HMM+Viterbi como alternativa global al motor de fases
- Qué se implementó: engine (puro), hybrid (fases 0-6 + Viterbi), compare
- Resultados: motor de fases con D-S supera al grafo en fixtures reales
- Por qué no se adoptó, valor residual del decoder Viterbi
- Fuentes: graph sweep results, compare output

### 3. ocr_preprocessing/POSTMORTEM.md

**Consolidación completa de preprocesamiento de imagen:**
- Pipeline de producción actual (blue inpaint, grayscale, unsharp, skip_binarization)
- v1 sweep (1024 configs): qué se probó, qué ganó
- v2 sweep (CLAHE, red channel, dilation): +98 rescued pero reverted
- DPI 300 experiment
- Otsu post-procesamiento
- Confidence gating
- Eval-production gap: lección central
- Ideas futuras: adaptive CLAHE, CLAHE en Tier 2 only, bilateral filter
- Fuentes: reportes existentes, manual test logs, sweep results

### 4. ocr_engines/POSTMORTEM.md

- EasyOCR: 0.07% hit rate, eliminado
- PaddleOCR: 0% accuracy
- Por qué Tesseract gana: domain-specific preprocessing + PSM 6 + OEM 1
- Impacto en arquitectura: producer-consumer → solo producers
- Fuentes: easyocr-paddle-postmortem.md, benchmark results

---

## Pasos de ejecución (orden estricto)

### Paso 0: Backup

```bash
# Stage eval/ + docs for snapshot (no git add -A para evitar data/sessions.db u otros)
git add eval/ docs/ CLAUDE.md && git commit -m "chore: snapshot before eval/ reorganization"
```

> **Nota:** `eval/__init__.py` existente se mantiene sin cambios (vacío o con contenido mínimo).

### Paso 1: Crear eval/shared/ y tipos compartidos

1. Crear `eval/shared/__init__.py`, `types.py`, `loaders.py`
2. Extraer `PageRead`, `Document` de inference.py → types.py
3. Extraer `load_fixtures()`, `load_ground_truth()` de sweep.py → loaders.py
4. Los loaders usan `Path(__file__).parent.parent` para fixtures/ground_truth

### Paso 2: Resolver conflicto archivo↔directorio (Windows NTFS)

> **⚠ Windows:** No pueden coexistir `eval/graph_inference.py` (archivo) y `eval/graph_inference/` (directorio) en NTFS.
> Hay que renombrar el archivo ANTES de crear el directorio.

```bash
# Renombrar el archivo conflictivo primero
git mv eval/graph_inference.py eval/_graph_inference_tmp.py
```

### Paso 3: Crear estructura de carpetas

Crear directorios con `__init__.py` vacío (imports usan paths explícitos, no re-exports):
- `eval/inference_tuning/`, `eval/graph_inference/`, `eval/ocr_preprocessing/`, `eval/ocr_engines/`
- Subdirectorios `results/`, `docs/`, `docs/specs/`, `docs/plans/`, `docs/reports/` en cada uno
- **Excepción:** `eval/ocr_engines/` NO lleva `results/` (su output va a `data/benchmark_results.json`)

### Paso 4: Mover y renombrar código (git mv)

Usar `git mv` para preservar historial. Combinar movimiento + renombrado en un solo paso por archivo.

**inference_tuning/**
```bash
git mv eval/inference.py eval/inference_tuning/inference.py
git mv eval/params.py eval/inference_tuning/params.py
git mv eval/sweep.py eval/inference_tuning/sweep.py
git mv eval/report.py eval/inference_tuning/report.py
git mv eval/baseline_art674.py eval/inference_tuning/baseline_art674.py
git mv eval/baseline_art674_tess.py eval/inference_tuning/baseline_art674_tess.py
```

**graph_inference/** (archivo conflictivo ya renombrado en Paso 2)
```bash
git mv eval/_graph_inference_tmp.py eval/graph_inference/engine.py
git mv eval/graph_params.py eval/graph_inference/params.py
git mv eval/graph_sweep.py eval/graph_inference/sweep.py
git mv eval/hybrid_inference.py eval/graph_inference/hybrid.py
git mv eval/compare_engines.py eval/graph_inference/compare.py
```

**ocr_preprocessing/**
```bash
git mv eval/ocr_preprocess.py eval/ocr_preprocessing/preprocess.py
git mv eval/ocr_params.py eval/ocr_preprocessing/params.py
git mv eval/ocr_sweep.py eval/ocr_preprocessing/sweep.py
git mv eval/ocr_report.py eval/ocr_preprocessing/report.py
```

**ocr_engines/**
```bash
git mv eval/ocr_benchmark.py eval/ocr_engines/benchmark.py
```

### Paso 4b: Commit intermedio (checkpoint de rollback)

```bash
# git mv ya staged los movimientos; solo agregar __init__.py y shared/ nuevos
git add eval/ && git commit -m "refactor(eval): move files to stage folders (imports not yet updated)"
```

> Este commit intermedio permite rollback más barato si los cambios de imports del Paso 5 fallan parcialmente.

### Paso 5: Actualizar imports en todos los archivos movidos

Seguir la tabla de "Cambios de imports por archivo" de arriba.
Incluye:
- Imports de eval.* → nueva ruta
- sys.path.insert profundidad
- Paths a fixtures/results relativos a __file__
- PageRead/Document → from eval.shared.types
- load_fixtures/load_ground_truth → from eval.shared.loaders

### Paso 6: Actualizar imports en tests

Renombrar `test_ocr_preprocess.py` → `test_preprocess.py`.
Actualizar todos los imports en eval/tests/ según tabla.

### Paso 7: Mover resultados (git mv)

Repartir eval/results/*.json a cada etapa/results/.

### Paso 8: Mover documentación

Copiar docs a cada etapa (git mv). Eliminar prefijos de fecha en destino.

### Paso 9: Verificar

```bash
# Ejecutar desde la raíz del repo (a:/PROJECTS/PDFoverseer)

# Cada módulo importable (PYTHONPATH=. para que eval sea importable como paquete)
PYTHONPATH=. python -c "from eval.shared.types import PageRead, Document"
PYTHONPATH=. python -c "from eval.shared.loaders import load_fixtures, load_ground_truth"
PYTHONPATH=. python -c "from eval.inference_tuning.inference import run_pipeline"
PYTHONPATH=. python -c "from eval.graph_inference.engine import run_pipeline"
PYTHONPATH=. python -c "from eval.ocr_preprocessing.preprocess import preprocess"
PYTHONPATH=. python -c "from eval.ocr_engines.benchmark import _parse_lenient"

# Tests pasan
pytest eval/tests/ -v

# Ruff limpio
ruff check eval/
```

### Paso 10: Escribir postmortems

Un POSTMORTEM.md por etapa según sección de arriba.

### Paso 11: Actualizar README.md, CLAUDE.md

- Reescribir `eval/README.md` con nueva estructura
- Actualizar sección `Project Structure` y references en CLAUDE.md

### Paso 12: Limpiar

- Eliminar archivos .py originales de eval/ raíz (ya movidos con git mv)
- Eliminar eval/results/ originales (ya migrados)
- Verificar que no queden archivos huérfanos

### Paso 13: Actualizar memoria

Actualizar memory files que referencien paths de eval/.

### Paso 14: Commit final

```
refactor(eval): reorganize by investigation stage + shared types/loaders
```

---

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| Imports rotos | Paso 9 verifica cada módulo + pytest |
| Paths a fixtures/results rotos | loaders.py centraliza; grep exhaustivo de paths hardcodeados |
| Cross-stage dependency (hybrid → inference_tuning) | Aceptable: import explícito documentado |
| PageRead/Document divergen entre engines | shared/types.py es la fuente única de verdad |
| `__init__.py` vacío rompe imports por nombre de paquete | Todos los `__init__.py` de etapas son **vacíos** — los imports usan paths explícitos (`from eval.graph_inference.engine import ...`), nunca `from eval.graph_inference import ...` |
| `ocr_engines/` sin `results/` | Correcto: `ocr_benchmark.py` escribe a `data/benchmark_results.json` (fuera de eval/), no a `eval/results/`. No necesita `results/` propio |
| CLAUDE.md desactualizado | Paso 11 lo actualiza |
| Memory stale | Paso 13 actualiza references |

---

## Dependencias cross-stage (documentadas, aceptables)

```
graph_inference/hybrid.py  ──imports──→  inference_tuning/inference.py
graph_inference/compare.py ──imports──→  inference_tuning/inference.py
graph_inference/compare.py ──imports──→  graph_inference/hybrid.py
```

Esto es correcto: el motor híbrido combina ambos engines, y compare necesita ejecutar los tres.
