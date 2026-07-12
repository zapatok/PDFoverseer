# RCH corner survey — Fase 0 (Track D / D2)

**Fecha:** 2026-07-12 · **Script:** `eval/pagination_count/rch_survey.py` ·
**Raw dump:** `eval/pagination_count/results/rch_survey.json` (gitignored,
810 page×region rows) · **Spec:** `docs/superpowers/specs/2026-07-12-track-d-ocr-speed-design.md` §3

**Regla de esta fase: ningún diseño de-dup se fija antes de esto.** Este
documento mide, no asume.

## Método

Para los 7 samples de charla nombrados en el plan (Task 5 Step 2) —
`CHAR_17.PDF`, `CHAR_25.pdf`, `CH_9.pdf`, `CH_39.pdf`, `CH_51docs.pdf`,
`CH_74docs.pdf`, `CH_BSM_18.pdf`, todos bajo `data/samples/` — se OCR'd cada
página (capada a 50pp/sample; los 3 samples de >50 páginas — CHAR_25 53pp,
CH_39 78pp, CH_51 102pp, CH_74 150pp — quedaron parcialmente cubiertos, ver
nota de cobertura abajo) en tres regiones candidatas:

- **`current`** — la esquina de producción, `_CORNER_PORTRAIT` de
  `pagination_count.py` (`(0.50, 0.0, 1.0, 0.15)`).
- **`amplified`** — la región candidata que proponía el spec §3
  (`(0.35, 0.0, 1.0, 0.20)`).
- **`top_left_half`** — el lado opuesto de la página (`(0.0, 0.0, 0.5,
  0.20)`) — NO incluye la esquina de paginación en absoluto.

Por cada (página, región) se registró: texto crudo, `parse_pagination`,
`extract_code`, y qué `CRS_RCH_ANCHORS` (el discriminador cover-only que ya
usa el motor de anclas) aparecen normalizados en el texto.

**No hay samples de chintegral ni dif_pts en `data/samples/`** — ningún
archivo del directorio lleva esos nombres, y el corpus real
(`A:\informe mensual`) está fuera de alcance para esta ronda ("Samples
only", regla de Daniel 2026-07-11). Ver conclusión dif_pts/chintegral abajo.

**Etiquetado cover/continuación por paridad de página:** para los samples
cuyo total de páginas del ARCHIVO COMPLETO es múltiplo exacto del `doc_count`
GT (`eval/fixtures/ground_truth.json`) — homogéneos N páginas/doc — la
paridad de índice de página (`i % N == 0` ⇒ portada esperada) es una etiqueta
de rol confiable sin necesidad de leer contenido. Tres de los 7 samples son
homogéneos: **CH_39** (78pp/39docs=2), **CH_51** (102pp/51docs=2),
**CH_BSM_18** (36pp/18docs=2). Los otros 4 no lo son (CHAR_17: 17pp/17docs=1,
trivial 1pp/doc; CHAR_25: 53pp/25docs no exacto — longitudes mixtas; CH_9:
17pp/9docs no exacto; CH_74: 150pp/74docs no exacto).

## Resultado 1 — la sobrecuenta "~2x" pineada NO se reproduce en estos samples

Tabla por sample (columna `curr==1` = páginas leídas con `curr==1` en la
región `current`, sobre las páginas efectivamente surveyeadas):

| sample | páginas (survey/total) | gt_docs | período homogéneo | curr==1 | dominant_total | códigos vistos |
|---|---:|---:|---:|---:|---:|---|
| CHAR_17 | 17/17 | 17 | — (1pp/doc) | 17 | 2 | F-CRS-RCH-01 |
| CHAR_25 | 50/53 | 25 | — | 24 | 2 | F-CAS-0D1-03, F-CH-CRS-01, F-CRS-ODI-03, F-CRS-RCH-01, F-CRS-ROY |
| CH_9 | 17/17 | 9 | — | 9 | 2 | F-CH-CRS-01, F-CRS-RCH-01 |
| CH_39 | 50/78 | 39 | 2 | 24 | 2 | F-CH-CRS-01, F-CRS-RCH-01, F-CRS-RCH-O1 |
| CH_51 | 50/102 | 51 | 2 | 25 | 2 | F-CH-CRS-01, F-CRS-RCH-01 |
| CH_74 | 50/150 | 74 | — | 23 | 2 | F-CH-CRS(-01), F-CRS-RCH(-01/-014) |
| CH_BSM_18 | 36/36 | 18 | 2 | 18 | 2 | F-CH-CRS-01, F-CRS-RCH-0/-01/-81/-Q1 |

**Verificación directa de la firma del bug** (dos páginas ADYACENTES que
ambas leen `curr==1` con el MISMO total — la firma literal de "la
continuación también dice Página 1 de N"), corrida sobre las 270 filas
capturadas:

- **CH_39, CH_51, CH_BSM_18** (los 3 homogéneos, 136 páginas / 68 documentos
  cubiertos): **CERO** ocurrencias. La secuencia `curr` alterna
  perfectamente `1,2,1,2,…` — ejemplo real (CH_39, páginas 0-5):
  `curr=[1,2,1,2,1,2]`, `total=[2,2,2,2,2,2]`. Un solo miss real por falla de
  OCR (CH_39 página 14: `curr=None,total=None` — no es el bug, es una lectura
  fallida aislada que el `recover_sequence` de producción ya cubre).
- **CH_9**: un candidato ambiguo en páginas 6-7 (ambas `curr=1,total=2`). No
  se puede determinar sin inspección visual si la página 7 es una
  continuación mal etiquetada (el bug) o el inicio legítimo de un documento
  de 1 página seguido de otro documento — el conteo total (`count_starts`)
  da 9, exactamente el GT, en ambas interpretaciones.
- **CHAR_17, CHAR_25, CH_74**: cero ocurrencias adyacentes del patrón.

**Esto diverge del hecho pineado del spec** ("las páginas de continuación
… también leen 'Página 1 de 2' … template bug verificado con sample de
Daniel"). Sobre estos 7 samples reales, el conteo simple `count_starts`
(sin ningún de-dup) ya reproduce el GT casi exactamente:

- CH_39/CH_51/CH_BSM_18 (homogéneos): `curr==1` en la ventana coincide con
  el conteo esperado de portadas EXACTO salvo 1 miss aislado por OCR.
- CHAR_17, CH_9, CH_BSM_18: `overcount_ratio` ≈ 1.00x (ver tabla) — no hay
  sobrecuenta sistemática ~2x en NINGÚN sample.

**Interpretación, no descarte del hecho pineado:** el sample citado por
Daniel que motivó "KEEP anchors" pudo ser un archivo/plantilla/revisión no
representado en estos 7 (o un caso puntual de mala digitación de esa
página específica, no un defecto sistemático del template). Fase 6/7 no
descartan la posibilidad — el mecanismo de fallback (abajo) está diseñado
para blindarse contra ella de todas formas, precisamente PORQUE una
ocurrencia real, aunque rara, sigue siendo posible.

## Resultado 2 — la región `amplified` del spec NO funciona; `top_left_half` funciona parcialmente

Para los 3 samples homogéneos, tasa de acierto (≥2 `CRS_RCH_ANCHORS`
normalizadas en el texto) sobre páginas-portada etiquetadas vs.
páginas-continuación etiquetadas:

| sample | región | acierto en portada (≥2 anclas) | falso positivo en continuación (≥2 anclas) |
|---|---|---:|---:|
| CH_39 | `current` | 0% (0/25) | 0% (0/25) |
| CH_39 | `amplified` | 0% (0/25) | 0% (0/25) |
| CH_39 | `top_left_half` | **52%** (13/25) | 0% (0/25) |
| CH_51 | `current` | 0% (0/25) | 0% (0/25) |
| CH_51 | `amplified` | 0% (0/25) | 0% (0/25) |
| CH_51 | `top_left_half` | **64%** (16/25) | 0% (0/25) |
| CH_BSM_18 | `current` | 0% (0/18) | 0% (0/18) |
| CH_BSM_18 | `amplified` | 0% (0/18) | 0% (0/18) |
| CH_BSM_18 | `top_left_half` | **56%** (10/18) | 0% (0/18) |

**La región `amplified` propuesta en el spec §3 (`x0=0.35, y1=0.20`) lee
CERO anclas cover-only en las 3 muestras homogéneas — 0% de acierto, no
1 anecdótico.** Los campos cover-only del formulario RCH ("nombre de la
charla", "obra", "relator", …) NO están en el lado derecho de la página
donde vive la paginación — están del lado IZQUIERDO. `top_left_half`
(que sí cubre ese lado) acierta 52-64% en páginas-portada reales — parcial,
no confiable como confirmador único, pero con **0% de falso positivo en
continuaciones en las 3 muestras** (68 páginas-continuación revisadas, cero
falsas alarmas).

**Esto también diverge de la premisa del spec** ("una región ampliada …
busca ≥2 anclas cover-only para confirmar portada" — la región propuesta,
literalmente, no lee ninguna). Cualquier discriminador de región viable
tendría que usar `top_left_half`, no `amplified` — y aun así, a 52-64% de
acierto, dejaría 36-48% de portadas reales sin confirmar (irían a LOW
confidence bajo el diseño undercount-safe, no se perderían del conteo,
pero perderían el "verde honesto" innecesariamente).

## Resultado 3 — dif_pts / chintegral: sin evidencia en este round

- **chintegral**: cero samples con nombre chintegral en `data/samples/`.
  Sus flavors `f_japa`/`f_previene` (no-RCH) no tienen ningún sample
  disponible en este round tampoco — el único sample RCH-control existente
  para chintegral (`eval/pagination_count/samples.py`) apunta al corpus real
  (`A:\informe mensual`), fuera de alcance. **No se produce evidencia nueva
  para chintegral en esta Fase 0.**
- **dif_pts**: cero samples con nombre dif_pts en `data/samples/`. Su propia
  ground truth existente (`tests/fixtures/scanners/dif_pts/*/ground_truth.json`)
  documenta que sus flavors `f_rch` y `f_aguasan` son, en la práctica,
  formularios de **1 página standalone** ("A7 lock fires, no OCR needed") —
  ni siquiera activan el motor de paginación — y su único flavor multi-página
  (`f_ch_crs_01`, portada + página "sombra" de test de comprensión) NO es un
  escenario de paginación repetida (contenido distinto entre páginas, no
  "1 de N" repetido). **No hay GT nueva ni antigua que ejercite el bug RCH
  para dif_pts en este round.** Per spec §3 gate: sin GT nueva adecuada,
  dif_pts NO se migra — esto se confirma en la Fase 0, no se difiere.

## Cobertura — nota honesta

El cap de 50pp/sample (spec: "cap survey/benchmark page counts sensibly")
dejó CHAR_25 (53pp), CH_39 (78pp), CH_51 (102pp) y CH_74 (150pp)
parcialmente cubiertos en ESTA encuesta exploratoria. La tabla de acierto
por región (Resultado 2) solo usa las 3 muestras homogéneas cubiertas en su
ventana de 50pp (que sigue siendo representativa por paridad de página). El
benchmark de Task 7 vuelve a leer estos mismos samples SIN cap (o con un
cap más generoso donde aplica) para comparar contra el GT completo del
archivo — ver `docs/research/2026-07-12-rch-pagination-decision.md`.

## Conclusiones que fijan el diseño de Task 6

1. **¿El patrón "1 de M repetido" es uniforme?** No — es prácticamente
   AUSENTE en los 7 samples reales medidos (0 ocurrencias confirmadas en 136
   páginas homogéneas, 1 caso ambiguo en CH_9 que no cambia el conteo). El
   enfoque 1 (de-dup aritmético incondicional) NO tiene base empírica de
   necesidad en este corpus — pero tampoco hace daño si se implementa con
   guarda estricta (solo dispara si TODAS las páginas leen "1 de M", spec
   §3), porque esa condición simplemente no se cumple en ninguno de estos
   7 archivos sanos.
2. **¿Qué región mínima lee ≥2 anclas cover-only, con qué tasa?**
   `top_left_half`, al 52-64% en portadas reales, 0% de falsos positivos en
   continuaciones. La región `amplified` del spec (0%) queda descartada por
   los datos — un enfoque 2 fiel al spec original no es viable; una versión
   corregida (región `top_left_half`) es parcialmente viable pero deja
   36-48% de portadas sin confirmar.
3. **¿Hay samples/GT utilizables de dif_pts?** No — ni de chintegral. Ambos
   quedan sin evidencia nueva en esta Fase 0 (ver Resultado 3).
4. **Implicación de diseño:** dado que (a) el bug no se reproduce en el
   corpus de samples disponible, (b) el discriminador de región más
   prometedor solo cubre ~60% de los casos y (c) el motor de paginación ya
   cuenta correctamente en la inmensa mayoría de las páginas medidas, el
   enfoque más defendible NO es "confirmar cada portada con OCR extra" sino
   **detectar la firma exacta del bug (dos páginas adyacentes `curr==1`
   mismo total) y, solo si aparece, caer TODO el archivo al motor de anclas
   ya probado** (enfoque 3, híbrido detect-and-fallback) — cero riesgo de
   conteo cuando el bug SÍ aparece (reusa el motor que ya se sabe correcto),
   velocidad plena de paginación cuando no aparece (el caso medido en el
   100% de los samples reales disponibles). Los 3 enfoques se implementan
   igual en Task 6 para comparación por datos (spec: "decisión por datos"),
   pero esta es la hipótesis que Fase 0 deja mejor sustentada.

Ver Task 6 (`eval/pagination_count/engine.py` + fixtures sintéticas) y
Task 7 (`docs/research/2026-07-12-rch-pagination-decision.md`) para la
comparación cuantitativa y el veredicto por sigla.
