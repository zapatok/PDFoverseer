# Postmortem: Integración VLM en el Pipeline OCR

**Fecha:** 2026-03-29
**Duración del esfuerzo:** 2026-03-24 a 2026-03-29 (6 días)
**Resultado:** VLM descartado del pipeline de producción. Revertido a baseline `s2t4-helena`.
**Archivos relacionados:**
- Spec: `docs/superpowers/specs/2026-03-25-vlm-resolver-design.md`
- Plan original: `docs/superpowers/plans/2026-03-25-vlm-resolver.md`
- Plan safe: `docs/superpowers/plans/2026-03-29-vlm-safe-integration.md`
- Investigación alternativas: `docs/research/2026-03-29-vlm-alternative-approaches.md`
- Benchmark VLM: `vlm/results/sweep1-results.md`
- Test logs: `manual_test_logs/log_s2t6-tier3.txt` ... `log_s2t10-safe-vlm.txt`

---

## 1. Objetivo Original

> "Lograr que entre Tesseract y VLM se lean correctamente la mayor cantidad de imágenes, haciendo que la inferencia tenga más datos para lograr su cometido."

El pipeline OCR tiene ~588 páginas fallidas en ART_670 (21.6% de 2719). El motor de inferencia las llena todas, pero con confianza variable. La idea: usar un modelo de visión (VLM) como tercer tier OCR para que la inferencia tenga datos reales en vez de estimaciones.

---

## 2. Benchmark VLM Aislado (Prometedor)

Antes de integrar al pipeline, se hizo un benchmark exhaustivo sobre 697 imágenes de páginas fallidas de ART_670:

| Modelo | Exact Match | Parse Rate | Latencia | Costo |
|--------|-------------|------------|----------|-------|
| Gemma 3 4B (Ollama) | **79.5%** | 81.6% | 2.5s | $0 (local) |
| Claude Haiku 4.5 | **88.6%** | 96.3% | 1.3s | ~$0.07/scan |
| Tesseract Tier 1+2 | 0% (fallidas) | — | — | — |

Estos números sugerían que VLM podía recuperar ~80% de las páginas que Tesseract no podía leer. La realidad fue otra.

---

## 3. Los 6 Experimentos (Todos Fallidos)

### Resumen de resultados en ART_670

| Version | Modelo | Arquitectura | DOC | COM | XVAL bad | Tiempo | Delta vs baseline |
|---------|--------|-------------|-----|-----|----------|--------|-------------------|
| **baseline** | ninguno | Tess-SR puro | **668** | **606** | **7** | 472s | — |
| s2t5 (v7clahe) | Gemma 3 | Post-inference corrector | 644 | 583 | 3 | — | **-24 DOC** |
| s2t5 (v6tess) | Gemma 3 | Post-inference corrector | 662 | 600 | 4 | — | **-6 DOC** |
| s2t6 | Gemma 3 | Tier 3 pre-inference | 660 | 592 | 8 | 1074s | **-8 DOC** |
| s2t7 | Gemma 3 | Tier 3 soft (0.45 conf) | 663 | 598 | 15 | 1716s | **-5 DOC** |
| s2t8 | Qwen 2.5VL 7B | Tier 3 soft | 664 | 601 | 18 | 5637s | **-4 DOC** |
| s2t9 | Claude Haiku | Tier 3 soft | 665 | 599 | 32 | 611s | **-3 DOC, +25 XVAL** |
| s2t10 | Qwen + period gate + rollback | Safe integration v3 | 667 | 606 | 6 | 7311s | **-1 DOC** |

Ningún experimento igualó al baseline. El mejor (s2t10) perdió 1 documento y tardó 15x más.

### Detalle por experimento

**s2t5 — Post-inference corrector (2026-03-25)**
- Arquitectura: OCR → Inferencia → VLM corrige → Re-inferencia
- Primer intento. VLM hacía lecturas incorrectas que pasaban el gate de aceptación (`_should_accept()`), corrompiendo la segunda pasada de inferencia.
- CLAHE preprocessing empeoró todo (-24 DOC). Sin CLAHE: -6 DOC.

**s2t6 — Tier 3 pre-inferencia con Gemma (2026-03-26)**
- Arquitectura: OCR → VLM Tier 3 → Inferencia (un solo paso)
- VLM como fuente OCR antes de inferencia. Gap-edge targeting (solo bordes de gaps).
- VLM reads inyectados como `method="vlm_ollama"` con confianza 0.85.
- Resultado: -8 DOC. Las lecturas VLM incorrectas se convertían en anclas que corrompían el gap solver.

**s2t7 — Tier 3 soft con Gemma (2026-03-26)**
- Mismo que s2t6 pero VLM reads como `method="inferred"` con confianza 0.45 (más suave).
- 82 errores de conexión con Ollama (modelo se descargó de VRAM entre queries).
- Fix: `keep_alive: -1` en requests para mantener modelo cargado.
- Resultado: -5 DOC, 15 XVAL bad.

**s2t8 — Qwen 2.5VL 7B (2026-03-27)**
- Modelo más grande (7B vs 4B). Mejor parse rate (93% vs 81%).
- Cold start de ~89s causó timeouts iniciales. Fix: timeout=120s.
- Resultado: -4 DOC, 18 XVAL bad. Mejor que Gemma pero no suficiente.
- Tiempo: 5637s (94 min) — inviable para uso práctico.

**s2t9 — Claude Haiku API (2026-03-28)**
- El modelo más preciso (88.6% exact match) y más rápido (1.3s/query).
- **Paradoja Claude:** Más accuracy = más daño. Las lecturas incorrectas de Claude parsean limpiamente y pasan todos los guards, convirtiéndose en anclas de alta confianza para el gap solver.
- Resultado: -3 DOC, **32 XVAL bad** (el peor XVAL de todos los experimentos).
- Los errores de Claude: lee totales incorrectos (6, 7, 8 en vez de 4) que cascadean.

**s2t10 — Safe integration: period gate + rollback + confirmación (2026-03-29)**
- Tres capas de seguridad:
  1. **Period gate:** Rechaza reads VLM donde `total != expected_total` cuando period conf >= 0.65
  2. **Two-pass rollback:** Corre inferencia con y sin VLM, mantiene el que tenga más docs
  3. **Confirmation mode:** Post-inferencia, solo sube confianza si VLM concuerda
- Period gate redujo XVAL bad de 18 a 6.
- **Bug en rollback:** No disparó cuando debía (667 < 668). Comparaba `sum(curr==1)` en reads crudos en vez de `_build_documents()`, contando boundaries OCR que son idénticas en ambos passes.
- Confirmation mode: 32 queries extra, 0 mejora estructural (`_build_documents` ignora confidence).
- Tiempo: 7311s (2h) — completamente inviable.

---

## 4. Root Cause: Por Qué VLM Siempre Empeora

### El hallazgo fundamental

> **El motor de inferencia maneja "sin datos" MEJOR que "datos equivocados".**

Cuando hay un gap de páginas fallidas, el gap solver llena la secuencia con propagación bidireccional desde los vecinos confirmados. Esto funciona porque:
- Los vecinos OCR son de alta confianza (1.0)
- La propagación es determinística y consistente
- El gap solver asigna confianzas calibradas (0.85-1.0)

Cuando VLM inyecta un dato incorrecto en un borde de gap:
- El dato se convierte en un **ancla** que divide el gap en dos sub-gaps
- Cada sub-gap hereda la lectura VLM como vecino, pero el total/curr puede ser inconsistente
- El gap solver genera hipótesis con penalty de clash
- Phase 3 (cross-validation) detecta la inconsistencia y baja confianza a 0.40, pero **no elimina el dato**
- El dato incorrecto persiste y `_build_documents()` lo usa para definir fronteras de documentos

### Ejemplo concreto (trazado por fases)

Gap original: `[4/4d, ?, ?, ?, ?, 1/4d]` — 4 páginas fallidas entre dos lecturas OCR.
- Inferencia sin VLM: `[4/4d, 1/4@0.88, 2/4@1.0, 3/4@1.0, 4/4@1.0, 1/4d]` — secuencia perfecta.

Con VLM incorrecto en posición 2: `[4/4d, ?, 3/4v, ?, ?, 1/4d]` (VLM dice 3/4, verdad es 2/4):
- Sub-gap 1: `[4/4d, ?]` → solver: `1/4@0.88`
- Sub-gap 2: `[3/4v, ?, ?, 1/4d]` → clash: 3/4→4/4→1/4→... no cuadra con 1/4d al final
- Phase 3: capa confianza de 3/4v a 0.40 (inconsistente con vecino izquierdo)
- Resultado: boundary desplazada, -1 documento

### La taxonomía de errores VLM

| Tipo | Ejemplo | Daño | Detectable? |
|------|---------|------|-------------|
| **Curr incorrecto, total correcto** | Lee 3/4, verdad 1/4 | **MÁXIMO** — desplaza boundaries | No (period gate solo filtra totales) |
| **Total incorrecto** | Lee 2/6, verdad 2/4 | Moderado — crea docs fantasma | Sí (period gate lo rechaza) |
| **Ambos incorrectos** | Lee 4/7, verdad 1/4 | Alto — combina ambos efectos | Parcial (total filtrado, curr no) |

El period gate (s2t10) solo atrapa errores de tipo B. Los errores tipo A son el residual irreducible.

### El umbral de accuracy para break-even

Se estima en **~97%** (menos de 4 lecturas incorrectas de 138 candidates). Ningún modelo VLM disponible alcanza esto en crops degradados de ART_670. Claude Haiku logra 88.6% — lejos del umbral.

---

## 5. Por Qué el 79-89% de Accuracy NO Ayuda

### La paradoja del "74%"

En benchmark aislado, VLM lee correctamente ~80% de las imágenes. Intuitivamente, 80% correcto debería mejorar resultados. No es así porque:

1. **Las lecturas correctas son redundantes.** El 80% que VLM lee bien son páginas que la inferencia YA maneja correctamente. Las ~450 páginas aisladas (single-failure entre dos éxitos) son triviales para el gap solver — VLM las saltea (`SKIP_ISOLATED=True`), y si no las saltea, confirma lo que la inferencia ya sabe.

2. **Las lecturas incorrectas son catastróficas.** El 20% que VLM lee mal son las páginas más difíciles del PDF — exactamente las que están en las zonas de mayor degradación (pp1700-2000). VLM y Tesseract fallan en las mismas imágenes. La diferencia: Tesseract devuelve "no sé" (gap), VLM devuelve "creo que es 3/4" (dato incorrecto).

3. **El daño es no-lineal.** Una lectura incorrecta en un borde de gap corrompe hasta N páginas adyacentes (donde N = longitud del gap). 1 error puede causar 1-4 errores XVAL cascadeados.

### Números concretos

De las 588 páginas fallidas en ART_670:
- **525 son llenadas por inferencia** con confianza > 0.50
- **Solo 15 páginas** tienen confianza < 0.50 (contradicciones reales)
- Si VLM leyera esas 15 correctamente: +3-5 COM (0.5% mejora)
- Pero esas 15 son las más degradadas del PDF — probabilidad de lectura correcta: baja

---

## 6. Análisis de Rendimiento

| Configuración | Queries | Latencia/query | Overhead total | Factor |
|---------------|---------|----------------|----------------|--------|
| Baseline (sin VLM) | 0 | — | 0s | 1x |
| Gemma 3 4B (Ollama) | 138 | 2.5s | ~6 min | 1.7x |
| Qwen 2.5VL 7B (Ollama) | 138 | 33.4s | ~77 min | 10x |
| Qwen + confirm | 201 | 33.4s | ~112 min | 15x |
| Claude Haiku API | 138 | 1.3s | ~3 min | 1.3x |
| Claude parallel (20x) | 138 | — | ~10s | ~1x |

Claude API con paralelismo es la única opción viable en rendimiento. Pero el problema no es velocidad — es que VLM no mejora resultados.

---

## 7. Arquitecturas Intentadas

### A. Post-inference corrector (s2t5)
```
OCR → Inferencia Pass 1 → VLM corrige → Inferencia Pass 2
```
**Falló porque:** VLM corregía páginas que la inferencia ya tenía bien. La re-inferencia amplificaba errores VLM.

### B. Pre-inference Tier 3 (s2t6-s2t9)
```
OCR → VLM Tier 3 (gap edges) → Inferencia (single pass)
```
**Falló porque:** Lecturas VLM incorrectas se convierten en anclas para el gap solver. Peor que no tener dato.

### C. Safe integration: gate + rollback + confirm (s2t10)
```
OCR → Period detection → Baseline inference (deepcopy) → VLM Tier 3 + gate →
VLM inference → Compare → Rollback si peor → Confirm
```
**Casi funcionó** (667 vs 668, 6 XVAL vs 7) pero:
- Rollback tenía bug (no detectó -1 DOC)
- Confirm mode no cambia estructura (DOC/COM iguales)
- Tardó 2 horas

---

## 8. Alternativas Investigadas y Descartadas

Se investigaron 7 enfoques alternativos (ver `docs/research/2026-03-29-vlm-alternative-approaches.md`):

| Enfoque | Viabilidad | Razón de descarte |
|---------|-----------|-------------------|
| VLM como tie-breaker | MEDIA-ALTA | Solo ~5-15 queries, mejora marginal (+1-2 docs) |
| VLM como validador post-pipeline | ALTA | No cambia resultados, solo genera cola de revisión |
| VLM detección de layout | MEDIA | Requiere fine-tuning, beneficio incierto |
| VLM en contradicciones (conf=0) | ALTA | Solo 15 páginas, mejora ~0.5% completeness |
| VLM pre-filtro binario | BAJA-MEDIA | Mismo problema: error en clasificación peor que no clasificar |
| Cola de revisión humana | ALTA | No requiere VLM en pipeline, solo UX |
| Consenso Tesseract+VLM | BAJA | Tesseract ya falló en esas páginas |

**Conclusión del análisis:** Incluso el mejor escenario (contradicciones-only, 15 queries, ~20s) produce una mejora de +3-5 COM sobre 606 (0.5-0.8%). No justifica la complejidad.

---

## 9. Lo Que Sí Funcionó (Para Guardar)

1. **El módulo `vlm/` standalone es sólido.** Benchmark, sweep, parser, preprocess — todo funciona bien para análisis offline.
2. **Gap-edge targeting** (`_find_candidates` con `SKIP_ISOLATED`) es el approach correcto para minimizar queries.
3. **Period gate** es efectivo: redujo XVAL bad de 18→6 eliminando lecturas con total incorrecto.
4. **Claude Haiku 4.5** es superior a cualquier modelo local para esta tarea (88.6% vs 79.5%, 1.3s vs 2.5-33s).
5. **`keep_alive: -1`** en Ollama es necesario para evitar descarga de modelo entre queries.
6. **La infraestructura de providers** (`OllamaProvider`, `ClaudeProvider`) es reutilizable si se necesita VLM en otro contexto.

---

## 10. Lecciones Aprendidas

### Sobre integración de modelos de IA en pipelines determinísticos

1. **Un modelo con 80% accuracy NO es 80% útil.** En un sistema de propagación de restricciones, el 20% de error puede causar daño desproporcionado. La utilidad real depende de DÓNDE caen los errores, no de cuántos son.

2. **"Sin dato" puede ser mejor que "dato incorrecto".** Los sistemas de inferencia están diseñados para manejar incertidumbre. Inyectar certeza falsa rompe sus invariantes.

3. **El accuracy de benchmark no predice el accuracy de producción.** El benchmark VLM se hizo sobre 697 imágenes aleatorias. En producción, VLM solo se consulta sobre las 138 peores imágenes — exactamente las que tienen mayor tasa de error.

4. **Más accuracy = más daño (paradoja Claude).** Claude Haiku tiene el mejor accuracy (88.6%) pero causó el mayor daño XVAL (32 errores). Sus lecturas incorrectas parsean limpiamente y pasan todos los guards, haciéndolas indistinguibles de lecturas correctas.

5. **El rollback no es suficiente.** Comparar métricas agregadas (count de documentos) puede ocultar daño localizado. El rollback de s2t10 no detectó la pérdida de 1 documento porque contaba reads crudos, no output de `_build_documents()`.

### Sobre el proceso de experimentación

6. **Siempre commitear antes de testear.** El fixture ART_670 fue destruido accidentalmente por un agente Sonnet durante una sesión de VLM. Lección cara.

7. **Version bump obligatorio.** Omitir el bump de `INFERENCE_ENGINE_VERSION` causó confusión al comparar logs de diferentes experimentos.

8. **Cold starts de modelos locales son asesinos.** Qwen 2.5VL tarda ~89s en cold start. Sin `keep_alive: -1`, Ollama descargaba el modelo entre queries, causando 82 errores en s2t7.

9. **El overhead de tiempo invalida la iteración.** Con Qwen a 33s/query, cada experimento tardaba 2 horas. Con 6 experimentos, se gastaron ~12 horas de GPU solo en scans que no mejoraron nada.

---

## 11. Estado Final

**Código producción:** Revertido a `s2t4-helena` (commit `bcaef90`). Cero código VLM en `core/`, `api/`.

**Código preservado:**
- `vlm/` module (benchmark, sweep, parser, preprocess) — intacto para investigación
- Tests: `tests/test_vlm_benchmark.py`, `test_vlm_client.py`, etc. — para el módulo standalone
- Docs: specs, plans, research — esta documentación

**Eliminado:**
- `core/vlm_resolver.py` — query_failed_pages, confirm_inferred_pages
- `core/vlm_provider.py` — OllamaProvider, ClaudeProvider
- Tests de integración pipeline-VLM
- Constantes VLM de `core/utils.py`
- Detección VLM de `api/worker.py`

**Validación post-revert:** ruff 0 violations, 108 tests passed, 55 eval tests passed, `[AI:]` log tags restaurados.

---

## 12. Recomendación

VLM no es viable como componente del pipeline OCR de PDFoverseer para el caso de uso actual. El motor de inferencia `s2t4-helena` es suficientemente robusto: llena el 100% de las páginas fallidas con 0 residuos, y los 7 errores XVAL del baseline son en imágenes genuinamente ilegibles donde ningún modelo (Tesseract, Gemma, Qwen, Claude) lee correctamente.

Si en el futuro se necesita VLM, el único path viable es como **herramienta de auditoría offline** — generar una cola de revisión humana priorizada, sin modificar el pipeline.
