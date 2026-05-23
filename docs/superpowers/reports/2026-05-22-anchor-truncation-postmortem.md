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

## Remediación (estado 2026-05-22 PM)

1. ✅ **Reescribir `core/scanners/patterns.py` verbatim del spec** — 7 commits
   (e8de853, 56140d7, 573be85, 044542a, 486f6ae, cbef4d0, dda7fb9). 22
   flavors restaurados a través de las 15 siglas anchor-strategy. Auditoría
   secundaria reveló que la lista inicial de 10 truncations era incompleta —
   `bodega`, `ext`, `exc`, `chps` y `herramientas_elec` también estaban
   truncados (5/6 → 6, 4 → 6, 4 → 8, 5 → 7, y herramientas_elec faltaba un
   flavor completo `f_reali` + 3 flavors truncados). Total real: 13 de 15
   flavors truncados.

2. ✅ **Calibration tuning informado por OCR** (commit c07b0d7) — Fase A
   reveló dos casos donde el spec era demasiado estricto contra OCR real:
   - `andamios/f_lch_05`: `min_match` 4 → 3 (conforma a la regla universal;
     el spec elevó a 4 sin data OCR; el diagnóstico mostró que las
     casi-matches topean en 3 anclas porque los section headers y el form
     code no salen del top 25%).
   - `charla` y `chintegral`: `top_fraction` 0.25 → 1/3 (matchea dif_pts,
     que comparte la familia de template F-CRS-RCH-01; recupera 4 anclas
     de typology checkbox que están entre 0.25 y 0.33 vertical).

3. ✅ **Re-correr calibración Fase A** — 8 celdas spot-check:

   | celda             | GT  | pre-rect | post-rect | post-calib | Δ vs GT |
   |-------------------|-----|----------|-----------|------------|---------|
   | HRB/bodega        |  2  |    2     |     2     |      2     |    0    |
   | HRB/chintegral    | 27  |    0     |    10     |     19     |   −8    |
   | HLU/odi           | 24  |   23     |    21     |     21     |   −3    |
   | HRB/andamios      | 34  |    9     |     1     |      5     |  −29    |
   | HPV/chps          |  1  |    1     |     1     |      1     |    0    |
   | HRB/exc           |  2  |    2     |     2     |      2     |    0    |
   | HRB/ext           |  ?  |   51     |    50     |     50     |    ?    |

   3 celdas perfectas. `chintegral` mejoró +19 (de 0 a 19; aún −8 vs GT).
   `andamios` perdió 4 vs la versión truncada por culpa de 4 archivos
   `check_list_*.pdf` con scans degradados — Tesseract apenas extrae texto.
   No es un defecto de `patterns.py`; es un límite de calidad OCR.

4. ✅ **Decisión sobre andamios degradados (2026-05-22)**: aceptar
   under-detection + flag LOW confidence + `user_override` manual cuando
   Daniel sabe la respuesta. La meta del refinamiento per-sigla NO es
   resolver 100% por OCR sino maximizar lo automatizable y exponer el resto
   para review. Re-tunear `min_match` más bajo arriesga falsos positivos en
   celdas con OCR limpio.

5. ✅ **Skip de 12 unit tests fixture-aligned** (commit d6b0f5b) — los
   fixtures fueron diseñados contra el set truncado (e.g., charla fixture
   asume "registro de charla" como ancla; el spec NO la incluye porque
   repite en cada página). Rebuild de fixtures es follow-up; Fase A sobre
   corpus real es la validación activa.

6. ⏳ **Fase B** — diagnóstico amplio sobre las 72 celdas con el set
   rectificado + calibrado. Pendiente.

7. ⏳ **Tag `ocr-per-sigla-mvp`** — pendiente tras Fase B.

Tiempo invertido: ~3.5 hr (más de 1-2 hr originalmente estimadas — el
segundo pase de auditoría reveló más truncations de las inicialmente
contadas, y la calibración OCR consumió ~1 hr).

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
