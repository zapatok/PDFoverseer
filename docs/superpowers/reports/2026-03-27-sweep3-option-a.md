# Sweep 3 — Opción A: Mejor config con 0 regressions

**Fecha:** 2026-03-27
**Branch:** `cuda-gpu`
**Sweep:** `eval/results/sweep_20260327_142905.json` + grids adicionales (~5,000 configs)

---

## Resultado

| Métrica | Baseline (production) | Opción A | Delta |
|---------|----------------------|----------|-------|
| ART_674_tess docs | 667 (-7) | **668 (-6)** | +1 doc |
| INSAP_20_degraded docs | 18 | **19** | +1 doc (bonus) |
| CHAR_25 | 25 ✓ | 25 ✓ | sin regresión |
| composite score | 142 | **146** | +4 |
| regressions | 0 | **0** | — |

## Params a cambiar (vs PRODUCTION_PARAMS en `eval/params.py`)

```python
# Opción A — 12 cambios, 0 regressions
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
# clash_boundary_pen = 1.5  (sin cambio — NO subir, ver análisis)
# anomaly_dropout    = 0.0  (sin cambio)
```

## Por qué NO subir clash_boundary_pen

El principal limitante de ART_674_tess son 30 merges en zonas con OCR fallido.
Subir `clash_boundary_pen` >= 1.75 los reduce pero **siempre** causa regresión en CHAR_25:

| cbpen | ART_674_tess | CHAR_25 | regressions |
|-------|-------------|---------|-------------|
| 1.50 | 668 (-6) | 25 ✓ | **0** |
| 1.75 | 668 (-6) | 26 ✗ | 1 |
| 2.50 | 671 (-3) | 26 ✗ | 1 |
| 3.00 | 670 (-4) | 26 ✗ | 1 |

**Causa raíz del problema CHAR_25:** páginas 12-13 ambas leen curr=1, total=1 (OCR misread de página 13, que debería ser "2 de 2"). Con cbpen alto, el gap solver las trata como evidencia de dos docs distintos → 26 docs en lugar de 25.

## Ceiling de inferencia con params actuales

El delta restante (-6) se desglosa:
- ~13-15 docs irrecuperables (true gaps en p1753-1933 con 506 OCR failures)
- ~15-17 merges potencialmente recuperables si se resuelve CHAR_25

El espacio de params explorado (DS weights, phase thresholds, gap solver, cbpen) está mayormente agotado sin un nuevo param que segmente el problema CHAR_25 / ART_674_tess.

## Próximos pasos sugeridos

Ver plan `2026-03-27-new-params-exploration.md` (pendiente de crear).

---

## Aplicar cuando se autorice

```bash
# 1. Editar eval/params.py — PRODUCTION_PARAMS (12 valores arriba)
# 2. Editar core/utils.py — mismos valores + bump INFERENCE_ENGINE_VERSION
# 3. pytest
```
