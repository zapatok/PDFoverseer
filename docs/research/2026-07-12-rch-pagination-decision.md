# RCH pagination benchmark + per-sigla migration verdict — Task 7

**Fecha:** 2026-07-12 · **Script:** `eval/pagination_count/benchmark.py`
(`run_rch_benchmark` / `main_rch`) · **Raw dump:**
`eval/pagination_count/results/rch_benchmark.json` (gitignored) · **Spec:**
`docs/superpowers/specs/2026-07-12-track-d-ocr-speed-design.md` §3 · **Fase 0:**
`docs/research/2026-07-12-rch-corner-survey.md`

## Método

Cada uno de los 7 samples reales de charla (`data/samples/`) se ventaneó a
`max_pages=60` (CH_39/CH_51/CH_74 exceden 60pp y quedan capados; los otros 4
caben enteros) y se corrió:

- **(a) `AnchorsScanner` de producción** (`_build_scanner_for_sigla("charla")`)
  — el baseline de hoy para charla.
- **(b) `count_documents_by_pagination` de producción** (paginación llana,
  sin de-dup) — `core/scanners/utils/pagination_count.py`.
- **(c) Los 3 enfoques del Task 6** (`eval/pagination_count/engine.py`),
  alimentados por la MISMA lectura de esquina (`current`) +
  `top_left_half` que ya usa `rch_survey.survey_pdf` (para no duplicar OCR):
  `count_by_arithmetic_dedup`, `count_by_region_discriminator`,
  `count_by_hybrid_fallback` (con `anchors_fallback_count` = el conteo real
  de (a) para ese mismo archivo).

Para los samples homogéneos (período exacto), `windowed_gt` = ventana //
período (exacto). Para los que caben enteros sin capar, `windowed_gt` = GT
completo. `CH_74` (150pp, no homogéneo, capado a 60) no tiene `windowed_gt` —
esa fila es informativa, no se compara contra un delta numérico.

## Resultado — tabla completa

| sample | ventana/total | GT ventana | anclas | anclas(s) | paginación | pag(s) | aritmético | discriminador | híbrido | patrón repetido? |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| CHAR_17 | 17/17 | 17 | **17** | 3.49 | **17** | 0.83 | 9 ✗ | 3 | **17** | sí (benigno — ver nota) |
| CHAR_25 | 53/53 | 25 | 22 | 19.64 | **25** | 3.29 | — | 10 | **25** | no |
| CH_9 | 17/17 | 9 | **9** | 4.86 | **9** | 0.86 | — | 4 | **9** | sí (benigno — ver nota) |
| CH_39 | 60/78 | 30 | **30** | 15.18 | **30** | 2.80 | — | 15 | **30** | no |
| CH_51 | 60/102 | 30 | **30** | 15.77 | **30** | 2.91 | — | 17 | **30** | no |
| CH_74 | 60/150 | — (informativo) | 30 | 16.12 | 31 | 2.88 | — | 18 | 31 | no |
| CH_BSM_18 | 36/36 | 18 | **18** | 10.76 | **18** | 1.76 | — | 10 | **18** | no |

(`—` = enfoque no disparó, retorna `None`; **negrita** = empata el GT de
ventana.)

## Enfoque por enfoque

### Aritmético (candidato 1) — RECHAZADO por evidencia directa

Su única condición de disparo ("TODAS las páginas leen 1 de M") no se
cumplió en 6/7 samples (correcto — no aplica, retorna `None`, sin dañar
nada). Pero SÍ se cumplió en **CHAR_17** — y ahí dio **9**, la mitad del GT
real (**17**). CHAR_17 es un archivo de 17 documentos de 1 página cada uno
donde la plantilla imprime "Página 1 de 2" en TODAS las páginas por defecto
(no hay una página 2 real). El enfoque aritmético asume ciegamente que ese
patrón significa "agrupar de a 2" — y se equivoca por completo. **Un solo
sample real basta para descartarlo**: no hay forma segura de distinguir,
solo con el conteo de "1 de M" uniforme, entre "de verdad son documentos de
M páginas" y "la plantilla imprime M por defecto en docs de 1 página".

### Discriminador de región (candidato 2, corregido a `top_left_half`) — RECHAZADO por sub-cobertura

Confirma solo 3-18 de los 9-30 documentos reales por muestra (12-56% de
cobertura) — consistente con la tasa de acierto 52-64% medida en Fase 0 (y
peor aún en muestras no-homogéneas donde el conteo de portadas reales es
menos cierto). Undercount-safe (nunca infla), pero deja pasar demasiadas
portadas reales sin confirmar como para ser el mecanismo principal.

### Híbrido detect-and-fallback (candidato 3) — GANADOR

Empata EXACTAMENTE el conteo de anclas en los 6 samples con GT de ventana
conocido, y en CH_74 (sin GT) queda a 1 documento de anclas (31 vs 30, sin
forma de saber cuál es más correcto en esa ventana parcial no-homogénea).
**Cero retrocesos frente a anclas en ningún fixture.**

En 2 de los 7 samples (CHAR_17, CH_9) el detector de patrón SÍ se activó —
pero por un motivo benigno, no el bug original: CHAR_17 tiene TODAS sus
páginas leyendo "1 de 2" (ver aritmético arriba) y CH_9 tiene un par
adyacente ambiguo en páginas 6-7 (ver `docs/research/2026-07-12-rch-corner-survey.md`,
Resultado 1). El detector (`detect_repeated_pattern`: dos páginas
ADYACENTES con `curr==1` y el mismo total) es intencionalmente conservador —
prefiere activarse de más (pagando el costo de OCR de anclas en un archivo
que en realidad estaba bien) a arriesgarse a NO activarse en un bug real.
En AMBOS casos donde se activó, el fallback a anclas dio el conteo
CORRECTO (17 y 9) — la propiedad de seguridad se sostiene incluso cuando el
disparo es "de más".

## Velocidad — número honesto, no el optimista

Sumando las 7 muestras: **anclas = 85.82 s** en total.

- **Si el híbrido NUNCA cae a anclas** (escenario optimista: paginación pura
  en las 7): 15.33 s → **5.6x**.
- **Número realista** (contando el costo real de los 2 disparos observados —
  CHAR_17 y CH_9 pagan paginación + anclas completas, las otras 5 pagan solo
  paginación): 0.83+3.49 + 3.29 + 0.86+4.86 + 2.80 + 2.91 + 2.88 + 1.76 =
  **23.68 s** → **3.6x**.

Ambos números superan cómodamente el gate `≥2x` del spec (regla única, sin
zona gris). El número realista (3.6x) es el que se reporta como resultado —
no el optimista — porque refleja el comportamiento medido del detector, no
un escenario hipotético sin disparos.

## Veredicto por sigla (spec §3, las tres gates por separado)

### charla — MIGRA

- **(a) Exactitud:** empata o gana a anclas en los 6 fixtures con GT de
  ventana conocido (0 retrocesos); CH_74 (sin GT) queda ±1, sin evidencia de
  regresión. **PASA.**
- **(b) Confianza honesta:** el mecanismo portado (Task 8) preserva los
  triggers LOW existentes de `PaginationScanner` (heavy-recovery,
  failed-reads, F7) y usa el `count==0` de anclas como low_trust cuando cae
  al fallback (F8 ya existente, reusado tal cual). **PASA por diseño** (Task
  8 lo verifica con TDD).
- **(c) Velocidad ≥2x medida:** 3.6x realista (5.6x optimista). **PASA.**

**Gana el enfoque 3 (híbrido detect-and-fallback)**, no el 1 ni el 2 — ambos
quedan documentados como candidatos descartados por evidencia directa
(aritmético falla en CHAR_17; discriminador sub-cubre en todos).

### chintegral — NO migra (decisión registrada, no fracaso)

Sus flavors `f_japa`/`f_previene` (no-RCH) no tienen NINGÚN fixture
disponible en este round — ni en `data/samples/`, ni producible sin tocar
el corpus real (fuera de alcance esta ronda). El único sample RCH-control
existente para chintegral (`eval/pagination_count/samples.py`) apunta al
corpus real, inutilizable aquí. Per spec §3: "Evidencia solo-RCH NO basta
para declararla migrable" — y aquí ni siquiera hay evidencia RCH nueva de
chintegral específicamente (los 7 samples benchmarkeados arriba son todos
de charla). **chintegral se queda en `scan_strategy: "anchors"` sin
cambios.**

### dif_pts — NO migra (decisión registrada, no fracaso)

Fase 0 confirmó: cero samples con nombre dif_pts en `data/samples/`, y su
propia ground truth existente documenta que sus flavors reales
(`f_rch`, `f_aguasan`) son formularios de 1 página (A7-lock, sin OCR) que
NUNCA activarían el motor de paginación en absoluto, y su único flavor
multi-página (`f_ch_crs_01`) no es un escenario de paginación repetida
(portada + página "sombra" de contenido distinto, no "1 de N" repetido). No
hay GT nueva ni antigua que ejercite el bug para dif_pts. Per spec §3: "sin
GT nueva adecuada, dif_pts NO se migra — un gate sin evidencia no se
declara pasado." **dif_pts se queda en `scan_strategy: "anchors"` sin
cambios.**

## Siguiente paso

Task 8 (condicional, solo siglas con gate PASADO): portar
`detect_repeated_pattern` + el mecanismo de fallback a
`core/scanners/utils/pagination_count.py` / `core/scanners/pagination_scanner.py`
con TDD, flip **solo de `charla`** en `patterns.py` (`scan_strategy:
"pagination"`, flavors de anclas RETENIDOS, nuevo flag `rch_fallback: True`
para que el fallback opt-in NO afecte a ninguna otra sigla ya migrada), bump
manual de `SCANNER_PATTERNS_VERSION`.
