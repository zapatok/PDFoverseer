# Plan: ART_674_tess Sweep Integration

**Branch:** `cuda-gpu`
**Scope:** Integrate ART_674_tess into the eval sweep, run it, analyze results, decide on param update.
**Prerequisite:** `eval/fixtures/real/ART_674_tess.json` exists (committed 2026-03-27).

---

## Por qué este plan es un nuevo archivo

El plan anterior (`2026-03-27-art674-tess-fixture.md`) terminó en Task 4 con STOP: fixture válido,
delta=-7 dentro del criterio ±2. Este plan cubre la siguiente decisión: si el delta es param-fixable,
encontrar esos params vía sweep.

---

## Análisis previo (base para el plan)

### Timing — no hay problema de rendimiento

| Fixture | Reads | ms/run |
|---------|-------|--------|
| ART_674_tess | 2,719 | 39.4ms |
| CH_74 (mayor anterior) | 150 | 1.6ms |

Sweep completo con ART_674_tess incluido: **~1.7 min** (1,000 configs × 42 fixtures).
El riesgo de "sweep lento" del plan anterior era incorrecto en magnitud — sin problema real.

### Clasificación del delta=-7

```
Total incomplete: 60
  Merges (found > declared): 30 docs  → FIXABLE con params
  True gaps (found < declared): 23 docs  → estructural (OCR failures irrecuperables)
  found == declared pero incomplete: 7 docs

Merges por región: p1-1752: 13,  p1753-1933: 6,  p1934-2719: 11
True gaps por región: p1-1752: 1,  p1753-1933: 13,  p1934-2719: 9
```

**Conclusión clave:** El delta=-7 es principalmente causado por merges (30 docs), no por gaps estructurales.
Los merges ocurren en zonas legibles (p1-1752: 13, p1934-2719: 11) → params pueden ayudar.

**Floor estructural estimado:** ~13-15 docs no recuperables (true gaps en p1753-1933).
Objetivo realista del sweep: reducir delta de -7 a -2/-3 (los merges en zonas legibles).

### Por qué ART_674 (VLM) se queda en el sweep

ART_674 (VLM, 0 failed reads) siempre obtiene delta=0 → actúa como guardrail contra over-splitting.
Si un config reduce merges en ART_674_tess pero rompe ART_674, la penalización de regresión lo elimina.
Los dos fixtures son complementarios: ART_674_tess presiona el gap solver, ART_674 previene soluciones extremas.

### Señal de scoring esperada

Por cada config, ART_674_tess contribuirá:
- `real_doc_delta += |667 - 674|` = ~7 (varía entre configs)
- `real_comp_delta += |607 - 662|` = ~55 (varía menos, floor ~15-20 por structural gaps)
- Penalización en `composite_score`: ~-7×3 - 55 = ~-76 puntos vs -0 para ART_674

Esto discrimina: configs que reducen merges obtendrán +15 a +21 puntos en composite.
Suficiente para mover el ranking si el sweep tiene ~100 pts de spread entre configs.

---

## Constraints

- DO NOT tocar `core/` (hookify block: eval-before-core)
- DO NOT modificar `eval/sweep.py` (funciona bien, no hay razón para tocarlo)
- DO NOT modificar el scoring de `eval/sweep.py` para ART_674_tess (misma lógica que real fixtures)
- DO NOT actualizar `core/utils.py` sin ver resultados primero
- STOP después de Task 3 — presentar resultados antes de actualizar production params

---

## Task 1: Agregar ART_674_tess a ground_truth.json

**Objetivo:** Que el sweep reconozca el fixture y lo incluya en el scoring.

**GT a usar:** `doc=674, complete=662, inferred=35` — idéntico a ART_674.
Razón: el ground truth es la verdad del PDF, no del método OCR. El mismo PDF tiene los mismos 674 docs.

**Editar `eval/ground_truth.json` — agregar después de la entrada "ART_674":**

```json
"ART_674_tess": {
  "doc_count": 674,
  "complete_count": 662,
  "inferred_count": 35
},
```

**Verificación después de editar:**
```bash
python -c "
import json; from pathlib import Path
gt = json.loads(Path('eval/ground_truth.json').read_text())
print('ART_674:', gt['ART_674'])
print('ART_674_tess:', gt['ART_674_tess'])
"
```

**Verificar que el sweep lo carga:**
```bash
python -c "
import sys; sys.path.insert(0, '.')
from eval.sweep import load_fixtures, load_ground_truth
fixtures = load_fixtures()
gt = load_ground_truth()
tess_fx = [f for f in fixtures if f['name'] == 'ART_674_tess']
print(f'Fixtures loaded: {len(fixtures)}')
print(f'ART_674_tess in fixtures: {len(tess_fx)} (expected 1)')
print(f'ART_674_tess in GT: {\"ART_674_tess\" in gt}')
"
```

**Ruff:** No hay código nuevo — solo JSON. No se necesita ruff check.

---

## Task 2: Correr el sweep

**Comando:**
```powershell
python eval/sweep.py
```

**Output esperado:**
```
Loaded 42 fixtures, N ground truth entries
Scoring baseline (production params)...
  baseline composite=XXX doc_exact=XX passes=XX/42
Pass 1: Latin Hypercube Sample (500 configs)...
  Pass1: 500/500 done
Pass 2: Fine grid around top-20...
  Pass2: XXX/XXX done
Pass 3: Beam search from top-5...
  Pass3: XXX/XXX done
Results saved to eval/results/sweep_YYYYMMDD_HHMMSS.json
Top config: composite=XXX regressions=X
```

**Tiempo estimado:** ~1.7 min.

**Guardar el path del resultado** — lo necesitamos para Task 3.

---

## Task 3: Analizar resultados

**Objetivo:** Determinar si el sweep encontró params que mejoran ART_674_tess sin regressions.

**Script de análisis (correr inline, no crear archivo):**
```bash
python -c "
import json, sys
from pathlib import Path
sys.path.insert(0, '.')
from eval.params import PRODUCTION_PARAMS
from eval.inference import PageRead, run_pipeline

# Leer resultado más reciente del sweep
results_dir = Path('eval/results')
latest = sorted(results_dir.glob('sweep_*.json'))[-1]
data = json.loads(latest.read_text())

print(f'Sweep: {latest.name}')
print(f'Fixtures: {data[\"fixtures_count\"]}  Configs tested: {data[\"total_configs_tested\"]}')
print()

# Baseline
bl = data['baseline']
print(f'BASELINE: composite={bl[\"composite_score\"]}  doc_delta={bl[\"doc_count_delta\"]}  regressions={bl[\"regression_count\"]}')
tess_bl = bl.get('fixture_breakdown', {}).get('ART_674_tess', 'NOT IN SWEEP')
print(f'  ART_674_tess baseline: {tess_bl}')
print()

# Top configs
fx_tess = Path('eval/fixtures/real/ART_674_tess.json')
reads_tess = [PageRead(**r) for r in json.loads(fx_tess.read_text())['reads']]
GT_DOC = 674

print(f'{\"Rank\":<5} {\"Composite\":>10} {\"Regs\":>5} {\"ART674_tess_result\":<20} {\"Tess_doc_delta\":>15} {\"Params_changed\"}')
print('-' * 100)
for cfg_entry in data['top_configs'][:10]:
    rank = cfg_entry['rank']
    scores = cfg_entry['scores']
    params = cfg_entry['params']
    tess_result = cfg_entry['fixture_breakdown'].get('ART_674_tess', 'N/A')
    # Re-run on tess to get doc count
    docs = run_pipeline(reads_tess, params)
    tess_doc = len(docs)
    tess_delta = tess_doc - GT_DOC
    # Params changed from production
    changed = [f'{k}:{PRODUCTION_PARAMS[k]}->{v}' for k, v in params.items() if v != PRODUCTION_PARAMS.get(k)]
    changed_str = ', '.join(changed[:3]) + ('...' if len(changed) > 3 else '')
    print(f'{rank:<5} {scores[\"composite_score\"]:>10} {scores[\"regression_count\"]:>5} {tess_result:<20} {tess_delta:>+15}  {changed_str}')
"
```

**Criterios de decisión:**

| Escenario | Acción |
|-----------|--------|
| Top config: ART_674_tess delta mejora (≥+2 docs) Y regressions=0 | Proponer update de production params |
| Top config: mejora delta PERO tiene regressions>0 | Analizar qué fixtures regressionan y reportar tradeoff |
| Ningún config mejora delta en ART_674_tess | Confirmar que el delta es estructural; no cambiar params |
| Top config es idéntico a PRODUCTION_PARAMS | Sweep convergió — params actuales son óptimos |

**Params a vigilar (los que controlan merges):**
- `min_conf_for_new_doc`: si baja de 0.55 → más splits → menos merges en ART_674_tess
- `clash_boundary_pen`: si sube de 1.5 → gap solver más conservador → menos merges
- `min_boundary_gap`: si sube de 2 → más separación entre docs → menos merges

---

## Task 4: Decisión final (STOP — requiere autorización)

Basado en Task 3, presentar al usuario:

1. **¿Mejora?** Delta ART_674_tess antes vs. después del best config
2. **¿Regressions?** Qué fixtures empeoran (si los hay)
3. **¿Recomendación?** Actualizar params o dejar como está

Si se aprueba actualizar:
- Editar `core/utils.py` con los nuevos valores
- Actualizar `eval/params.py` PRODUCTION_PARAMS
- Bump `INFERENCE_ENGINE_VERSION` en `core/utils.py`
- Correr `pytest` para verificar suite completa

**NO tocar `core/` hasta recibir autorización explícita.**

---

## Archivos modificados

| Archivo | Acción | Cuándo |
|---------|--------|--------|
| `eval/ground_truth.json` | EDIT — agregar ART_674_tess | Task 1 |
| `eval/results/sweep_*.json` | CREATE (auto) | Task 2 |
| `core/utils.py` | EDIT (condicional) | Task 4, solo si autorizado |
| `eval/params.py` | EDIT (condicional) | Task 4, solo si autorizado |

---

## Commits

Después de Task 1:
```
feat(eval): add ART_674_tess to ground_truth.json (doc=674, same as VLM fixture)
```

Después de Task 4 (si aplica):
```
feat(core): update production params from sweep3 (ART_674_tess discrimination signal)
```

---

## Session Prompt (para retomar)

> "Continúa el plan en `docs/superpowers/plans/2026-03-27-art674-tess-sweep.md`.
> Task 1 es agregar `ART_674_tess` a `eval/ground_truth.json` con doc=674, complete=662, inferred=35.
> Task 2 es correr `python eval/sweep.py` (~1.7 min).
> Task 3 es analizar resultados con el script inline del plan.
> NO toques `core/` — STOP en Task 4 y espera autorización antes de cualquier cambio a production params."
