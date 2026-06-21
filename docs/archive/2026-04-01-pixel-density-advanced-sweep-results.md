# Pixel Density Advanced Sweep — Resultados

**Fecha:** 2026-04-01
**Branch:** `research/pixel-density`
**Dataset principal:** ART_674.pdf (2719 pages, 674 documentos)
**Validacion cruzada:** 21 PDFs del corpus general + 5 PDFs familia ART

---

## Objetivo

Mejorar la deteccion de portadas por pixel density mas alla del baseline actual (F1=0.922), explorando 4 lineas de investigacion:

1. **Chi-cuadrado** como distancia alternativa a L2
2. **PELT** (change-point detection) como paradigma alternativo al bilateral
3. **Multi-descriptor** combinando features complementarios
4. **Fusion de senales** combinando los mejores detectores

Ademas, medir cuantas de las 27 paginas "TESS-ONLY" (portadas que solo Tesseract detecta, no el bilateral baseline) podemos recuperar.

**Restriccion critica (establecida en specs):** cualquier mejora debe **generalizar** a multiples PDFs, no solo optimizar para ART_674.

---

## Baseline de referencia (PD_BASELINE / V1)

Dos configuraciones establecidas via sweep de 54 combinaciones:

| Config | Matches | Error | P | R | F1 | FP | TESS |
|--------|---------|-------|------|------|-------|-----|------|
| **V1-count** (CLAHE/min/pct_75.2) | 675 | +1 | 0.921 | 0.923 | **0.922** | 49 | 0/27 |
| **V1-quality** (CLAHE/min/kmeans) | 626 | -48 | 0.966 | 0.898 | **0.931** | 21 | 0/27 |

---

## Fase 1: Distancia Chi-cuadrado

**Idea:** Chi-cuadrado (`(h1-h2)^2 / (h1+h2)`) es una metrica pensada para comparar distribuciones (histogramas). Deberia ser mejor que L2 para capturar diferencias en la forma de los histogramas de intensidad.

**Combinaciones probadas:** 84 (3 bins x 2 modos x 2 score_fns x 7 thresholds)
**Tiempo:** ~6 min (con cache de paginas)

### Top 5

| Config | F1 | TP | FP | FN | TESS |
|--------|-----|-----|-----|-----|------|
| 32bins / global / min / pct_78 | 0.885 | 563 | 35 | 111 | 0 |
| 16bins / tile_4x4 / min / pct_80 | 0.885 | 539 | 5 | 135 | 0 |
| 32bins / tile_4x4 / min / kmeans | 0.885 | 539 | 5 | 135 | 0 |
| 32bins / tile_4x4 / min / pct_80 | 0.885 | 539 | 5 | 135 | 0 |
| 16bins / tile_4x4 / min / kmeans | 0.884 | 538 | 5 | 136 | 0 |

### Veredicto: FAIL

- F1=0.885, **por debajo del baseline** (0.922)
- 0 paginas TESS-ONLY recuperadas
- Chi-cuadrado como distancia standalone no mejora L2 para dark_ratio. Amplifica ruido en bins con pocos pixels.
- **Valor residual:** los scores per-page se guardaron para probar fusion en Fase 4.

---

## Fase 2: Segmentacion PELT

**Idea:** En lugar de comparar pares de paginas vecinas (bilateral), tratar la secuencia de paginas como una senal y usar PELT (Pruned Exact Linear Time) para detectar puntos de cambio globales. Cada segmento = un documento.

**Combinaciones probadas:** 3/6 completadas (cancelado despues de 45+ min)

### Resultados

| Features | Modelo | Segmentos | F1 | Tiempo |
|----------|--------|-----------|-----|--------|
| grid_8x8 (64d) | L2 | 440 | 0.237 | 4.7 min |
| grid_8x8 (64d) | RBF | 544 | 0.228 | 24 min |
| histogram_32 (32d) | L2 | 22 | 0.023 | 5.2 min |

### Veredicto: DEAD END

- F1 < 0.25 en todos los casos — ni cerca de ser competitivo
- PELT no puede segmentar 674 documentos en 2719 paginas. Incluso con calibracion de penalidad, no encuentra el numero correcto de segmentos
- **Problema fundamental:** las transiciones entre documentos en PDFs de charlas CRS no son "cambios abruptos" en la senal de features — muchos documentos se ven visualmente similares
- Computacionalmente prohibitivo: modelo RBF tarda 24 min por combo en 2719 paginas (O(n^2 * d))
- **Conclusion:** segmentacion global no es viable para este problema. El enfoque bilateral (comparar vecinos) es el paradigma correcto

---

## Fase 3: Multi-descriptor bilateral

**Idea:** En lugar de usar solo dark_ratio (densidad de tinta), combinar multiples features que capturen aspectos diferentes de cada pagina:

| Feature | Dims | Que captura |
|---------|------|-------------|
| `dark_ratio_grid` | 64 | Densidad de tinta por region (8x8 grid) |
| `edge_density_grid` | 16 | Estructura de layout — bordes, lineas (4x4 grid) |
| `lbp_histogram` | 10 | Textura local (Local Binary Pattern) |
| `histogram` | 32 | Distribucion global de intensidad |
| `histogram_tile` | 256 | Distribucion de intensidad por region (4x4 tiles x 16 bins) |
| `cc_stats` | 2 | Componentes conectados (num. objetos + tamano medio) |
| `projection_stats` | 6 | Perfiles de proyeccion horizontal/vertical |

**Tiempo:** Stage A 8 min, Stage B 19 min

### Stage A: Features individuales (14 combos)

Cada feature solo, con bilateral L2 y dos thresholds (kmeans + pct_75.2):

| Feature | Threshold | F1 | TP | FP | FN | TESS |
|---------|-----------|-----|-----|-----|-----|------|
| **edge_density_grid** | pct_75.2 | **0.928** | 626 | 49 | 48 | **27** |
| histogram_tile | kmeans | 0.884 | 538 | 5 | 136 | 0 |
| histogram | kmeans | 0.881 | 544 | 17 | 130 | 0 |
| dark_ratio_grid | pct_75.2 | 0.844 | 569 | 106 | 105 | 0 |
| lbp_histogram | pct_75.2 | 0.225 | 152 | 523 | 522 | 0 |
| projection_stats | pct_75.2 | 0.098 | 66 | 609 | 608 | 0 |
| cc_stats | pct_75.2 | 0.074 | 50 | 626 | 624 | 1 |

**Hallazgo clave:** `edge_density_grid` solo, con percentil 75.2, ya supera el baseline (0.928 vs 0.922). Ademas recupera las 27 paginas TESS-ONLY. La densidad de bordes captura cambios de layout que dark_ratio no ve.

**Features inservibles:** LBP, projection_stats, cc_stats producen F1 < 0.25 solos. No discriminan portadas.

### Stage B: Combinaciones con normalizacion

Se combinan pares y trios de features, aplicando normalizacion (z-score, robust-z, min-max) para que escalas distintas sean comparables, y luego L2 bilateral.

| Features | Norm | Score | Thresh | F1 | TP | FP | FN | TESS |
|----------|------|-------|--------|-----|-----|-----|-----|------|
| **dark_ratio + edge_density** | **robust_z** | **min** | **kmeans** | **0.957** | **648** | **33** | **26** | **26** |
| dark_ratio + edge_density | robust_z | min | pct_75.2 | 0.956 | 645 | 30 | 29 | 26 |
| dark_ratio + lbp_histogram | robust_z | min | pct_75.2 | 0.952 | 642 | 33 | 32 | 24 |
| dark_ratio + histogram | robust_z | min | pct_75.2 | 0.946 | 638 | 37 | 36 | 18 |
| dark_ratio + projection_stats | robust_z | min | pct_75.2 | 0.946 | 638 | 37 | 36 | 23 |

### Veredicto: BREAKTHROUGH en ART_674

- **F1=0.957** (+3.5pp sobre baseline) en ART_674
- 26/27 TESS-ONLY recuperadas
- `robust_z` (basada en mediana/MAD) funciona mejor que z-score (media/std)
- Agregar mas de 2 features no mejora; dark_ratio + edge_density es suficiente

**PERO:** estos resultados son exclusivamente sobre ART_674. Ver seccion de validacion cruzada abajo.

---

## Fase 4: Fusion de senales

**Idea:** Combinar los scores per-page de los mejores detectores (baseline L2, chi-cuadrado, multi-descriptor) mediante pesos, votacion, o operaciones de conjuntos.

**Fuentes:** bilateral_l2 (V1), chi2 (Phase 1), multidesc (Phase 3)
**Combos probados:** 66 pesos + voting + set ops
**Tiempo:** < 1 min

### Top resultados

| Estrategia | Pesos | F1 | TP | FP | FN | TESS |
|-----------|-------|-----|-----|-----|-----|------|
| **Score fusion** | L2=0.1, chi2=0.0, **md=0.9** | **0.959** | 643 | 24 | 31 | 26 |
| Score fusion | L2=0.2, chi2=0.0, md=0.8 | 0.957 | 637 | 20 | 37 | 22 |
| Score fusion | L2=0.3, chi2=0.0, md=0.7 | 0.957 | 632 | 15 | 42 | 20 |
| Multidesc solo | md=1.0 | 0.957 | 648 | 33 | 26 | 26 |
| **Union** | todos | 0.951 | **666** | 60 | **8** | 26 |

### Veredicto: MARGINAL

- Mejor fusion: F1=0.959, apenas +0.2pp sobre Phase 3 standalone (0.957)
- Chi-cuadrado recibe peso 0.0 en todas las configs ganadoras — **no aporta nada** a la fusion
- Un poco de L2 baseline (10-20%) ayuda a reducir FP sin sacrificar mucho recall
- **Union** interesante: solo 8 FN (casi no pierde portadas) pero 60 FP

---

## Validacion cruzada: V2 NO GENERALIZA

Tras el exito en ART_674, se corrio la config V2 (dark_ratio + edge_density, robust-z, min, kmeans) sobre el corpus completo. Los resultados son decepcionantes.

### Corpus general (21 PDFs)

| PDF | Pages | Target | V1-count | V1c err | V1-qual | V1q err | V2 | V2 err |
|-----|-------|--------|----------|---------|---------|---------|-----|--------|
| ALUM_1 | 2 | 1 | 2 | +1 | 2 | +1 | 2 | +1 |
| ALUM_19 | 36 | 19 | 10 | -9 | 20 | +1 | **19** | **+0** |
| ART_674 | 2719 | 674 | **675** | **+1** | 626 | -48 | 681 | +7 |
| CASTRO_15 | 15 | 15 | 6 | -9 | 6 | -9 | 4 | -11 |
| CASTRO_5 | 5 | 5 | 2 | -3 | 3 | -2 | 2 | -3 |
| CHAR_25 | 53 | 25 | 13 | -12 | 29 | +4 | 30 | +5 |
| CH_39 | 78 | 39 | 21 | -18 | 43 | +4 | 44 | +5 |
| CH_51 | 102 | 51 | 27 | -24 | 55 | +4 | 76 | **+25** |
| CH_74 | 150 | 74 | 38 | -36 | 63 | -11 | 53 | -21 |
| CH_9 | 17 | 9 | 4 | -5 | 4 | -5 | 5 | -4 |
| CH_BSM_18 | 36 | 18 | 11 | -7 | 21 | +3 | 15 | -3 |
| CRS_9 | 19 | 9 | 5 | -4 | 16 | +7 | **9** | **+0** |
| HLL_363 | 538 | 363 | 135 | -228 | 348 | -15 | 30 | **-333** |
| INSAP_20 | 31 | 20 | 8 | -12 | 23 | +3 | 18 | -2 |
| INS_31 | 31 | 31 | 9 | -22 | 3 | -28 | 3 | -28 |
| JOGA_19 | 38 | 19 | 10 | -9 | 14 | -5 | 21 | +2 |
| QUEVEDO_1 | 2 | 1 | 2 | +1 | 2 | +1 | 2 | +1 |
| QUEVEDO_13 | 26 | 13 | 8 | -5 | 8 | -5 | 17 | +4 |
| QUEVEDO_2 | 4 | 2 | 1 | -1 | 1 | -1 | 3 | +1 |
| RACO_25 | 43 | 25 | 13 | -12 | 21 | -4 | 17 | -8 |
| SAEZ_14 | 24 | 14 | 6 | -8 | 13 | -1 | 8 | -6 |

### Familia ART (5 PDFs adicionales, ~4 pags/doc)

| PDF | Pages | Target | V1-count | V1c err | V1-qual | V1q err | V2 | V2 err |
|-----|-------|--------|----------|---------|---------|---------|-----|--------|
| ART_CH_13 | 52 | 13 | **13** | **+0** | 26 | +13 | 24 | +11 |
| ART_CON_13 | 52 | 13 | **13** | **+0** | 26 | +13 | 15 | +2 |
| ART_EX_13 | 52 | 13 | **13** | **+0** | 26 | +13 | 16 | +3 |
| ART_GR_8 | 32 | 8 | 9 | +1 | 16 | +8 | 16 | +8 |
| ART_ROC_10 | 40 | 10 | **10** | **+0** | 20 | +10 | 19 | +9 |

### Metricas agregadas

| Metrica | V1-count | V1-quality | V2 |
|---------|----------|------------|------|
| MAE (21 PDFs generales) | 20.3 | 7.7 | **22.4** |
| Exactos (21 PDFs) | 0 | 0 | 2 |
| Dentro de +/-2 (21 PDFs) | 4 | 6 | 7 |
| MAE (5 ARTs chicos) | 0.2 | 11.4 | 6.6 |
| Exactos (5 ARTs chicos) | 4 | 0 | 0 |

### Diagnostico del fallo

**V2 esta sobreajustada a ART_674.** Las causas son:

1. **KMeans k=2 no escala a PDFs chicos.** En ART_674, la proporcion de portadas es 674/2719 = 25%. KMeans separa bien porque hay masa estadistica suficiente. En PDFs de 50 paginas, KMeans pone el corte demasiado bajo y clasifica ~50% como portadas.

2. **Robust-z con pocas muestras es inestable.** La mediana y MAD de 50 vectores de 80 dimensiones no son estadisticas confiables. Valores extremos en unas pocas paginas distorsionan la normalizacion.

3. **Edge_density domina la combinacion.** Al combinar 64 dims de dark_ratio + 16 dims de edge_density con normalizacion, edge_density tiene menos peso relativo. Pero edge_density es el feature que mas discrimina — la combinacion diluye su contribucion en PDFs donde dark_ratio no aporta.

4. **HLL_363 tiene estructura visual distinta.** Los documentos de HLL son mas homogeneos visualmente que los de ART — las transiciones entre documentos son mas sutiles, requiriendo un detector calibrado diferente.

**Contraste con V1-count (pct_75.2):** V1-count usa un threshold estadistico simple (percentil fijo) que no depende de la distribucion. Es robusto porque no intenta ser inteligente — simplemente toma el top 25% de scores. Esto funciona porque en la mayoria de PDFs CRS, ~25% de las paginas son portadas.

---

## Resumen ejecutivo

```
En ART_674 (dataset de optimizacion):
  Baseline V1-count     ████████████████████░░  F1=0.922  error=+1
  Phase 1 (Chi-sq)      ████████████████░░░░░░  F1=0.885  FAIL
  Phase 2 (PELT)        ████░░░░░░░░░░░░░░░░░░  F1=0.237  DEAD END
  Phase 3 (Multidesc)   ███████████████████░░░  F1=0.957  BEST en ART_674
  Phase 4 (Fusion)      ████████████████████░░  F1=0.959  MARGINAL

En validacion cruzada (26 PDFs):
  V1-count (pct_75.2)   Generaliza bien, MAE=20.3 (alto pero estable)
  V1-quality (kmeans)   Moderado, MAE=7.7
  V2 (multidesc)        NO GENERALIZA, MAE=22.4 — RECHAZADO como reemplazo de V1
```

**Conclusion:** V2 logra F1=0.957 en ART_674 pero no puede reemplazar a V1 porque falla en validacion cruzada. V1-count sigue siendo la referencia de produccion. Sin embargo, hay componentes rescatables de esta investigacion (ver seccion siguiente).

---

## Que funciono y por que

1. **Edge density como feature.** `edge_density_grid` solo, con percentil 75.2, dio F1=0.928 en ART_674 y recupero 27/27 TESS-ONLY. Mide estructura de layout (bordes, lineas) que dark_ratio no captura. Es el descubrimiento mas valioso de toda la investigacion.

2. **Robust-z normalization para combinar features.** Cuando se necesitan features de distinta escala en un mismo vector, robust-z (mediana + MAD) funciona mejor que z-score o min-max — resistente a outliers.

3. **El paradigma bilateral es correcto.** PELT confirmo que comparar vecinos es el enfoque adecuado. Segmentacion global no funciona para documentos CRS.

## Que NO funciono

1. **Chi-cuadrado** como distancia standalone no mejora L2. Peso=0 en todas las fusiones ganadoras.

2. **PELT** es un callejon sin salida. Costo O(n^2*d), resultados terribles (F1<0.25).

3. **Agregar mas de 2 features** no mejora en ART_674 y agrava el sobreajuste.

4. **KMeans k=2 como threshold para multi-descriptor** — sobreajusta a la distribucion especifica de ART_674. En PDFs chicos, clasifica ~50% como portadas.

5. **Optimizar exclusivamente para ART_674** — el PDF mas grande y complejo del corpus no es representativo de los demas.

---

## Componentes rescatables

A pesar de que V2 no generaliza como reemplazo completo, tres lineas merecen investigacion adicional:

### 1. Edge density con threshold de V1

`edge_density_grid` solo dio F1=0.928 en ART_674 con percentil 75.2 — el mismo threshold estable de V1. Si este feature, con el threshold que ya generaliza (percentil 75.2), tambien funciona en otros PDFs, seria una mejora directa sin cambiar el paradigma de thresholding.

**Hipotesis:** el valor esta en el feature, no en el threshold. V2 fallo por el threshold (kmeans), no por el feature (edge_density).

### 2. Score fusion ligera con V1 como base

En Phase 4, mezclar un poco de L2 baseline con multidesc redujo FP. La idea inversa — usar V1 como base (que ya generaliza) y agregar un pequeno boost de edge_density — podria mejorar precision/recall sin romper la generalizacion.

**Hipotesis:** V1_score * 0.8 + edge_score * 0.2, con el mismo percentil 75.2, conserva la estabilidad de V1 pero gana la senal complementaria de edge.

### 3. Normalizacion robust-z como herramienta

La tecnica de robust-z esta validada para combinar features de distinta escala. Si se usa con un threshold estable (percentil, no kmeans), la normalizacion no deberia causar sobreajuste porque solo afecta la escala relativa, no el criterio de decision.

---

## Investigacion de rescate (Rescue Sweep)

Tras el fracaso de V2 en validacion cruzada, se investigaron 3 lineas para rescatar componentes utiles. Se ejecuto cada linea sobre 27 PDFs (22 generales + 5 familia ART) con el **mismo threshold de V1 (percentil 75.2)** para aislar el efecto del feature vs el threshold.

### Resultados: Corpus general (22 PDFs)

| Metrica | V1 | Rescue A | Rescue B | Rescue C |
|---------|-----|----------|----------|----------|
| MAE | 20.0 | 20.0 | 20.0 | 20.1 |
| Exactos | 0 | 0 | 0 | 0 |
| Dentro +/-2 | 4 | 4 | 4 | 4 |

**Hallazgo:** con percentil 75.2, TODAS las lineas empatan con V1. El threshold domina; el feature subyacente casi no afecta el conteo. La estabilidad de V1 viene del threshold, no del feature.

### Resultados: Familia ART (5 PDFs)

| Metrica | V1 | Rescue A | Rescue B | Rescue C |
|---------|-----|----------|----------|----------|
| MAE | 0.2 | **0.0** | **0.0** | **0.0** |
| Exactos | 4/5 | **5/5** | **5/5** | **5/5** |

**Hallazgo:** las tres lineas corrigen ART_GR_8 (error +1 en V1) a exacto. Edge density captura mejor los limites de documentos tipo ART.

### Resultados: ART_674 page-level (unico PDF con GT por pagina)

| Config | F1 | P | R | TP | FP | FN | TESS-ONLY |
|--------|-----|------|------|-----|-----|-----|-----------|
| V1 | 0.922 | 0.921 | 0.923 | 622 | 53 | 52 | 7 |
| **Rescue A** (edge solo) | **0.928** | 0.927 | 0.929 | 626 | 49 | 48 | **27** |
| Rescue B (fusion 0.1) | 0.940 | 0.939 | 0.941 | 634 | 41 | 40 | 14 |
| **Rescue C** (multi+pct) | **0.956** | 0.956 | 0.957 | 645 | 30 | 29 | **26** |

### Conteo de documentos: V1 vs Rescue C (PDF por PDF)

Esta es la metrica que mas importa al usuario final — cuantos documentos detecta cada config.

| PDF | Target | V1 | V1 err | RC | RC err | Mejor |
|-----|--------|-----|--------|-----|--------|-------|
| ALUM_1 | 1 | 2 | +1 | 2 | +1 | -- |
| ALUM_19 | 19 | 10 | -9 | 9 | -10 | V1 |
| ART_674 | 674 | 675 | +1 | 675 | +1 | -- |
| ART_CH_13 | 13 | **13** | **+0** | **13** | **+0** | -- |
| ART_CON_13 | 13 | **13** | **+0** | **13** | **+0** | -- |
| ART_EX_13 | 13 | **13** | **+0** | **13** | **+0** | -- |
| ART_GR_8 | 8 | 9 | +1 | **8** | **+0** | RC |
| ART_ROC_10 | 10 | **10** | **+0** | **10** | **+0** | -- |
| CASTRO_15 | 15 | 6 | -9 | 4 | -11 | V1 |
| CASTRO_5 | 5 | 2 | -3 | 2 | -3 | -- |
| CHAR_17 | 17 | 5 | -12 | 5 | -12 | -- |
| CHAR_25 | 25 | 13 | -12 | 13 | -12 | -- |
| CH_39 | 39 | 21 | -18 | 20 | -19 | V1 |
| CH_51 | 51 | 28 | -23 | 27 | -24 | V1 |
| CH_74 | 74 | 38 | -36 | 38 | -36 | -- |
| CH_9 | 9 | 4 | -5 | 5 | -4 | RC |
| CH_BSM_18 | 18 | 11 | -7 | 10 | -8 | V1 |
| CRS_9 | 9 | 5 | -4 | 5 | -4 | -- |
| HLL_363 | 363 | 135 | -228 | 135 | -228 | -- |
| INSAP_20 | 20 | 8 | -12 | 8 | -12 | -- |
| INS_31 | 31 | 9 | -22 | 10 | -21 | RC |
| JOGA_19 | 19 | 10 | -9 | 10 | -9 | -- |
| QUEVEDO_1 | 1 | 2 | +1 | 2 | +1 | -- |
| QUEVEDO_13 | 13 | 7 | -6 | 8 | -5 | RC |
| QUEVEDO_2 | 2 | 1 | -1 | 3 | +1 | -- |
| RACO_25 | 25 | 13 | -12 | 12 | -13 | V1 |
| SAEZ_14 | 14 | 6 | -8 | 6 | -8 | -- |
| | | **MAE** | **16.3** | **MAE** | **16.4** | |
| | | **Exactos** | **4** | **Exactos** | **5** | |

**Score: V1 gana 6, RC gana 4, empate 17.**

En conteo puro, V1 y RC son practicamente identicos (MAE 16.3 vs 16.4). La diferencia real esta en la calidad page-level: RC detecta las portadas *correctas* con mucha mas precision (F1=0.956 vs 0.922 en ART_674), aunque el numero total de detecciones sea similar.

Dicho de otra forma: RC y V1 detectan ~la misma cantidad de portadas, pero RC acierta mas en *cuales* son portadas reales y cuales no.

### Veredicto por linea

**Rescue A (edge_density standalone, pct_75.2): VIABLE**
- Misma MAE que V1 en corpus general (no regresion)
- 5/5 exactos en familia ART (+1 sobre V1)
- F1=0.928 en ART_674 (+0.6pp), 27/27 TESS-ONLY
- La mas simple de implementar (un solo feature, sin normalizacion)

**Rescue B (fusion V1 + edge, pct_75.2): VIABLE pero sin ventaja clara**
- Misma MAE que V1 en corpus general
- 5/5 en familia ART
- F1=0.940 en ART_674 — intermedia entre A y C
- El peso optimo es 0.1 (solo 10% de edge) — V1 domina la fusion
- Complejidad adicional sin ganancia suficiente sobre A o C

**Rescue C (dark_ratio + edge_density, robust-z, pct_75.2): GANADORA**
- MAE=20.1 en corpus general (practicamente igual a V1)
- 5/5 en familia ART
- **F1=0.956** en ART_674 — **el mismo resultado que V2 pero sin sobreajuste**
- 26/27 TESS-ONLY recuperadas
- Confirma la hipotesis: V2 fallo por KMeans, no por los features ni la normalizacion

### Conclusion del rescate

**El percentil 75.2 es la clave de la generalizacion.** V2 fallo porque KMeans k=2 sobreajusta a la distribucion de cada PDF. El percentil fijo toma siempre el top ~25% de scores, independientemente de la forma de la distribucion.

Rescue C hereda lo mejor de ambos mundos:
- De V1: el threshold estable (percentil 75.2) que generaliza
- De V2: los features complementarios (dark_ratio + edge_density) y la normalizacion robust-z que mejoran la calidad page-level

**Config ganadora (PD_V2_RESCUE):**
```
features: dark_ratio_grid (8x8, 64d) + edge_density_grid (4x4, 16d)
normalization: robust-z (median + MAD * 1.4826)
distance: L2
bilateral score: min
threshold: percentile 75.2
```

---

## Resumen ejecutivo final

```
Baseline V1 (CLAHE/min/pct_75.2)     ████████████████████░░  F1=0.922
Phase 1 (Chi-sq)                      ████████████████░░░░░░  F1=0.885  FAIL
Phase 2 (PELT)                        ████░░░░░░░░░░░░░░░░░░  F1=0.237  DEAD END
Phase 3 (Multidesc, kmeans)           ███████████████████░░░  F1=0.957  SOBREAJUSTE
Phase 4 (Fusion, kmeans)              ████████████████████░░  F1=0.959  SOBREAJUSTE
Rescue A (edge solo, pct)             ████████████████████░░  F1=0.928  VIABLE
Rescue B (fusion, pct)                █████████████████████░  F1=0.940  VIABLE
Rescue C (multidesc, pct)             ███████████████████░░░  F1=0.956  GANADORA
```

**Arco completo:** Optimizacion agresiva para ART_674 (F1=0.959) --> fracaso en cross-validation --> diagnostico (KMeans es el problema) --> rescate exitoso (F1=0.956 con percentil que generaliza).

| | V1 baseline | Rescue C (final) | Cambio |
|--|-------------|-------------------|--------|
| MAE general (22 PDFs) | 20.0 | 20.1 | +0.1 (neutro) |
| MAE ART (5 PDFs) | 0.2 | **0.0** | **-0.2** |
| F1 ART_674 | 0.922 | **0.956** | **+3.4pp** |
| TESS-ONLY | 7/27 | **26/27** | **+19** |
| FP ART_674 | 53 | **30** | **-23** |
| FN ART_674 | 52 | **29** | **-23** |

---

## Archivos de datos

| Archivo | Contenido |
|---------|-----------|
| `data/pixel_density/sweep_chi2.json` | Phase 1: 84 resultados + scores del best config |
| `data/pixel_density/sweep_multidesc.json` | Phase 3: Stage A (14) + Stage B (~60) + scores del best config |
| `data/pixel_density/sweep_combine.json` | Phase 4: ~75 resultados de fusion |
| `data/pixel_density/tess_only_pages.json` | Cache de 27 paginas TESS-ONLY |
| `data/pixel_density/sweep_rescue.json` | Rescue sweep: V1 + A + B + C over 27 PDFs |
| `data/pixel_density/cache/*.npz` | Cached rendered page arrays (gitignored) |
