# Plan: New Params Exploration — failure_zone_cbpen_scale

**Branch:** `cuda-gpu`
**Fecha:** 2026-03-27
**Continúa:** `2026-03-27-art674-tess-sweep.md` (Tasks 1–4 completados)

---

## Contexto acumulado

### Historial de sweeps

| Sweep | Fecha | Fixtures | Best config (0-reg) | ART_674_tess |
|-------|-------|----------|---------------------|--------------|
| Sweep1 | 2026-03-24 | 41 | composite=138 | N/A |
| Sweep2 | 2026-03-26 | 41+INS_31 | composite=142 | N/A |
| Sweep3 | 2026-03-27 | 42+ART_674_tess | composite=146 (**Opción A**) | 668 (-6) |

### Opción A (sweep3, 0 regressions) — PENDIENTE de aplicar

```python
fwd_conf            = 0.97   # era 0.99
new_doc_hom_mul     = 0.25   # era 0.30
ds_period_weight    = 0.12   # era 0.10
ds_neighbor_weight  = 0.08   # era 0.10
ds_prior_weight     = 0.09   # era 0.07
ds_boost_max        = 0.20   # era 0.18
ph5b_conf_min       = 0.65   # era 0.50
clash_w_local       = 1.00   # era 0.75
clash_w_period      = 1.50   # era 2.50
phase4_conf         = 0.10   # era 0.15
hom_threshold       = 0.83   # era 0.85
min_boundary_gap    = 1      # era 2
```

Ver informe completo: `docs/superpowers/reports/2026-03-27-sweep3-option-a.md`

### Ceiling de sweep3 — conflicto estructural

El param `clash_boundary_pen` (cbpen) tiene un conflicto irresolvable con los params actuales:

| cbpen | ART_674_tess | CHAR_25 | regressions |
|-------|-------------|---------|-------------|
| 1.50 | 668 (-6) | 25 ✓ | **0** |
| 1.75 | 668 (-6) | 26 ✗ | 1 |
| 2.50 | 671 (-3) | 26 ✗ | 1 |
| 3.00 | 670 (-4) | 26 ✗ | 1 |

**Causa raíz CHAR_25:** páginas 12-13 leen curr=1, total=1. cbpen alto → gap solver trata la zona como 2 docs → regresión.

**Causa raíz ART_674_tess merges:** zona p1753-1933 (~180 pp, 60%+ OCR failures). cbpen=1.5 → gap solver merge docs a través de la zona → -6 docs.

**La solución global cbpen no puede satisfacer ambos a la vez.**

---

## Nueva idea: failure_zone_cbpen_scale

Separar el comportamiento de cbpen según el tamaño del gap:

```
effective_cbpen = clash_boundary_pen * failure_zone_cbpen_scale
                  SOLO cuando gap_len >= failure_zone_min_len
```

### Motivación

- ART_674_tess: zona de 20–180 páginas consecutivas fallidas → `gap_len >= 20` → scale se aplica → effective_cbpen alto → más boundaries → menos merges
- CHAR_25: gaps cortos (si los hay) de 1–3 páginas → `gap_len < 20` → scale NO se aplica → cbpen=1.5 global → sin regresión

### Parámetros nuevos

| Param | Default | Space | Efecto |
|-------|---------|-------|--------|
| `failure_zone_cbpen_scale` | 1.0 | [1.0, 1.5, 2.0, 3.0] | Multiplica cbpen para gaps grandes |
| `failure_zone_min_len` | 20 | [5, 10, 20, 50] | Mínimo gap_len para activar el scale |

---

## Fixtures nuevos

Los fixtures sintéticos existentes no discriminan bien este par de parámetros.
Faltan dos casos clave:

### syn_misread_singleton (NUEVO)

**Propósito:** Fixture de regresión. Simula el patrón CHAR_25: gaps cortos (≤3) alrededor de doc boundaries con lecturas ambiguas. Verifica que `failure_zone_cbpen_scale` NO se aplica a gaps cortos (protegido por `failure_zone_min_len`).

- doc_count: 10, complete_count: 8
- Estructura: mezcla de docs de 1 y 2 páginas con gaps de 1–3 failures entre ellos

### syn_failure_zone (NUEVO)

**Propósito:** Fixture discriminante. Zona concentrada de 20+ failures consecutivas con anchors legibles en los extremos. Verifica que `failure_zone_cbpen_scale=2.0, min_len=10` mejora la detección de boundaries en la zona (menos merges).

- doc_count: 20, complete_count: 10
- Estructura: docs limpios + zona de 24 failures con 2 anchors internos + docs limpios

---

## Constraints

- **NO tocar `core/`** — solo `eval/`
- **NO modificar `eval/sweep.py`** — funciona bien
- **NO actualizar `core/utils.py` o production params** hasta ver resultados
- STOP en Task 8 — presentar resultados antes de cualquier cambio al pipeline

---

## Task 1: Crear fixtures nuevos

**Archivos:** `eval/fixtures/synthetic/syn_misread_singleton.json` y `syn_failure_zone.json`

**Verificación:**
```bash
python -c "
import json; from pathlib import Path
from eval.inference import PageRead, run_pipeline
from eval.params import PRODUCTION_PARAMS

for name in ['syn_misread_singleton', 'syn_failure_zone']:
    fx = json.loads(Path(f'eval/fixtures/synthetic/{name}.json').read_text())
    reads = [PageRead(**r) for r in fx['reads']]
    docs = run_pipeline(reads, PRODUCTION_PARAMS)
    print(f'{name}: {len(docs)} docs (GT: {fx[\"name\"]})')
"
```

---

## Task 2: Actualizar ground_truth.json

Agregar entradas para los dos fixtures nuevos.

---

## Task 3: Implementar failure_zone_cbpen_scale en eval/inference.py

**Cambios en `_infer()` (eval/inference.py):**

Después de la línea `clash_boundary_pen = params.get("clash_boundary_pen", 5.0)`:

```python
failure_zone_cbpen_scale = params.get("failure_zone_cbpen_scale", 1.0)
failure_zone_min_len = int(params.get("failure_zone_min_len", 20))
```

Dentro del loop `for gap_start, gap_end in gaps:`, antes de "Score hypotheses":

```python
# Effective cbpen: scale up for large failure zones
gap_len = gap_end - gap_start
if gap_len >= failure_zone_min_len and failure_zone_cbpen_scale > 1.0:
    effective_cbpen = clash_boundary_pen * failure_zone_cbpen_scale
else:
    effective_cbpen = clash_boundary_pen
```

Reemplazar las 2 apariciones de `clash_boundary_pen` en "Boundary divergence penalty" con `effective_cbpen`.

**Ruff:** correr `ruff check .` antes de commit.

---

## Task 4: Actualizar eval/params.py

```python
# En PARAM_SPACE:
"failure_zone_cbpen_scale": [1.0, 1.5, 2.0, 3.0],
"failure_zone_min_len":     [5, 10, 20, 50],

# En PRODUCTION_PARAMS:
"failure_zone_cbpen_scale": 1.0,
"failure_zone_min_len":     20,
```

---

## Task 5: Verificar que el sweep carga los nuevos params

```bash
python -c "
import sys; sys.path.insert(0, '.')
from eval.params import PRODUCTION_PARAMS, PARAM_SPACE
print('failure_zone_cbpen_scale in PARAM_SPACE:', 'failure_zone_cbpen_scale' in PARAM_SPACE)
print('failure_zone_min_len in PRODUCTION_PARAMS:', 'failure_zone_min_len' in PRODUCTION_PARAMS)
from eval.sweep import load_fixtures, load_ground_truth
fixtures = load_fixtures()
gt = load_ground_truth()
print('Fixtures:', len(fixtures))
print('syn_misread_singleton in GT:', 'syn_misread_singleton' in gt)
print('syn_failure_zone in GT:', 'syn_failure_zone' in gt)
"
```

---

## Task 6: Correr sweep (STOP — presentar resultados)

```bash
python eval/sweep.py
```

Tiempo estimado: ~2.5 min (más fixtures + más params en espacio).

---

## Task 7: Analizar resultados (STOP — requiere decisión)

Criterios:
| Escenario | Acción |
|-----------|--------|
| failure_zone_cbpen_scale mejora ART_674_tess ≥+2, 0 regressions | Proponer update production params |
| Mejora ART_674_tess pero regresiona syn_misread_singleton | failure_zone_min_len muy bajo — ajustar |
| Sin mejora en ART_674_tess | Ceiling real — documentar |

---

## Task 8: Decisión final (STOP — requiere autorización)

NO modificar `core/utils.py`, `eval/params.py` PRODUCTION_PARAMS, ni hacer commit a `core/` hasta autorización explícita.

---

## Archivos modificados

| Archivo | Acción | Cuándo |
|---------|--------|--------|
| `eval/fixtures/synthetic/syn_misread_singleton.json` | CREATE | Task 1 |
| `eval/fixtures/synthetic/syn_failure_zone.json` | CREATE | Task 1 |
| `eval/ground_truth.json` | EDIT | Task 2 |
| `eval/inference.py` | EDIT | Task 3 |
| `eval/params.py` | EDIT | Task 4 |
| `core/utils.py` | EDIT (condicional) | Task 8, solo si autorizado |

---

## Session Prompt (para retomar)

> "Continúa el plan en `docs/superpowers/plans/2026-03-27-new-params-exploration.md`.
> Task 1: crear `syn_misread_singleton.json` y `syn_failure_zone.json` en `eval/fixtures/synthetic/`.
> Task 2: actualizar `eval/ground_truth.json`.
> Task 3: implementar `failure_zone_cbpen_scale` y `failure_zone_min_len` en `eval/inference.py`.
> Task 4: actualizar `eval/params.py`.
> Task 5: verificar carga.
> Task 6: correr sweep.
> NO tocar `core/`."
