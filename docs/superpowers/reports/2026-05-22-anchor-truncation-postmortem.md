# Anchor truncation postmortem — OCR per-sigla

**Fecha:** 2026-05-22
**Branch:** `feature/ocr-per-sigla`
**Severidad:** sistémica (10 de 15 anchor-strategy flavors afectados)
**Estado:** en remediación

## Qué pasó

El spec de OCR per-sigla
([docs/superpowers/specs/2026-05-18-ocr-per-sigla-refinement-design.md](../specs/2026-05-18-ocr-per-sigla-refinement-design.md), ~2470 líneas) definió listas comprehensivas de anclas por flavor — típicamente 5-11 anclas estructurales con `min_match=3` (la regla universal "≥ 3 matches ⇒ portada", repetida explícitamente en cada sección de sigla del spec).

Durante la implementación del Chunk 4, el implementer subagent redujo estas a 2-3 anclas mínimas con `min_match=2`, derivadas empíricamente de un fixture por sigla. El Chunk 5 heredó y propagó la truncación. El reviewer de spec del Chunk 5 levantó la inconsistencia como Issue 2 ("anchors mínimos de f_lch_xx"). El orquestador declinó el issue con el argumento "el enfoque mínimo-empírico es la convención sancionada" — un argumento **inventado por el implementer subagent**, no presente en el spec.

La truncación quedó invisible hasta que la calibración Fase A (2026-05-22) corrió los scanners sobre 8 celdas de spot-check y Daniel verificó manualmente. Aparecieron discrepancias de **−25 y −27 documentos por celda** en HRB/chintegral y HRB/andamios — exactamente las celdas de régimen 2 (compilación) donde el motor OCR existe para contar.

## Auditoría (post-descubrimiento)

10 de 15 anchor-strategy flavors tenían listas truncadas al 20-40% del conteo del spec:

| sigla / flavor | spec (anchors / min_match) | impl actual | Δ |
|---|---|---|---|
| odi / f_crs_odi_03 | 8 / 3 | 2 / 2 | −6 anchors |
| charla / f_crs_rch_01 | 8+ / 3 | 2 / 2 + literal **mal escrito** | crítico |
| chintegral / f_rch | 8+ / 3 | 2 / 2 + mismo literal mal | crítico |
| chintegral / f_japa | 10 / 3 | 2 / 2 | −8 |
| chintegral / f_previene | 11 / 3 | 2 / 2 | −9 |
| andamios / f_lch_05 | 9 / 4 | 3 / 2 | −6 |
| andamios / f_ribeiro | 6 / 3 | 3 / 2 | −3 |
| irl / f_crs_odi_01 | 14 / 3 | 2 / 2 | −12 |
| maquinaria / f_lch_xx | 5 / 3 | 2 / 2 | −3 |

Los 5 flavors correctamente transcritos (bodega, caliente, chps, exc, ext) son los que el implementer copió fielmente — no hay razón arquitectónica para la diferencia.

Además, `f_crs_rch_01` (usado por `charla` y `chintegral`) tenía un literal **factualmente incorrecto**: el spec nombra el formulario "REGISTRO DE FORMACIÓN E INFORMACIÓN" pero el implementer escribió `"registro de charla"` (título de una revisión antigua del formulario). Esta ancla **jamás puede machear** los PDFs reales del corpus ABRIL.

## Impacto medible — calibración Fase A

| celda | scanner reportó | real (verificado por Daniel) | Δ |
|---|---|---|---|
| HRB/bodega | 2 | 2 | 0 ✓ (A7 trivial) |
| HPV/chps | 1 | 1 | 0 ✓ |
| HRB/exc | 2 | 2 | 0 ✓ |
| HLU/odi | 23 | 24 | −1 |
| HRB/altura | 14 | 19 | −5 (V4 LOW, override) |
| HRB/chintegral | **0** | **27** | **−27** |
| HRB/andamios | **9** | **34** | **−25** |
| HRB/ext | 51 | (pendiente verificar) | ? |

Reporte de calibración: [docs/research/2026-05-22-calibration-fase-a.md](../../research/2026-05-22-calibration-fase-a.md).

## Causa raíz — tres fallas apiladas

1. **La lección existía pero se aplicó solo a una capa.** El memo de Serena `ocr_refinement_in_progress` registró explícitamente *"anchors deben ser copy-paste textual del spec, no recomposición de memoria"* — pero solo como regla SPEC→PLAN. La misma regla debía aplicar PLAN→IMPLEMENTACIÓN y no se transfirió.

2. **El implementer subagent inventó una convención local.** Con evidencia limitada por fixture (1-2 por sigla), el subagent generalizó a "anclas mínimas empíricas funcionan" sin volver a las listas verbosas del spec. Esta convención local se propagó chunk-a-chunk vía el contexto del implementer.

3. **El reviewer lo cazó, el orquestador lo declinó.** El Issue 2 del Chunk 5 spec review era correcto. Declinarlo con un argumento inventado (en lugar de consultar el spec) fue el momento en que el bug quedó.

## Remediación (en curso)

1. Reescribir `core/scanners/patterns.py` con copy-paste verbatim del spec para las 18 entradas de sigla. (Trabajo mecánico, sin decisiones de diseño nuevas.)
2. Re-correr unit tests; actualizar tests fixture-aligned donde el test estaba alineado al set truncado (no al spec).
3. Re-correr calibración Fase A; verificar que los conteos se acerquen a la ground truth verificada manualmente.
4. Proceder a Fase B (diagnóstico amplio sobre las 72 celdas).
5. Tag `ocr-per-sigla-mvp` solo después de que Fase A salga limpia.

Estimado: 1-2 horas focales. Riesgo de regresión bajo (cada cambio es "agrego anclas + subo min_match"; no cambia comportamiento estructural).

## Lecciones reforzadas

- **`feedback_first_attempt_quality_bar`**: el proceso SDD (spec → plan → impl → review) es el piso, no el techo. Cortar corners en transcripción derrota el proceso entero.
- **`feedback_incomplete_root_cause_investigation`**: cuando un bug aparece, auditar todas las referencias del mismo tipo antes de declarar "fix aislado". El patrón de truncación debió cazarse al instante de encontrar la primera ancla mal.
- **`feedback_art670_fixture_disaster`**: nunca reconstruir de recolección parcial. Mismo meta-patrón aquí: el orquestador confió en el rationale inventado por el implementer subagent sobre la fuente (spec).

Un nuevo memo de feedback **`feedback_anchors_verbatim_at_every_layer`** formaliza la lección para aplicarla cross-project.

## Antipatrones a evitar a futuro

- "El implementer ya está mirando el código, su criterio prevalece sobre el spec." NO. El implementer tiene contexto local; el spec tiene contexto global.
- "El spec exagera, suficiente con 2-3 anclas distintivas." NO. La redundancia del spec ES la defensa contra fragilidad OCR.
- "El reviewer no entiende el código real." NO por default. Si el reviewer dice "no coincide con el spec", releer el spec antes de declinarle.
- "Es mucho trabajo transcribir todo, optimicemos." NO. Es exactamente para esto que se hizo el spec — la transcripción mecánica es el trabajo.
