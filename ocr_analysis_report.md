# Baseline OCR Analysis — [logsmaster.txt](file:///a:/PROJECTS/PDFoverseer/logsmaster.txt)
> **Referencia:** [a:\PROJECTS\PDFoverseer\logsmaster.txt](file:///a:/PROJECTS/PDFoverseer/logsmaster.txt) — Run en `master` con EasyOCR GPU activo, 2026-03-18.  
> Este archivo es el **benchmark oficial** contra el que se compararán todas las ramas futuras.

---

## Resumen por Archivo

| Archivo | Páginas | Docs | Completos | Incompletos | Inferidas | ms/pág | OCR fail |
|---|---|---|---|---|---|---|---|
| ART_HLL_674docsapp.pdf | 2719 | 676 | 612 (91%) | 64 | 759 | 173 | 664 (24%) |
| CH_9docs.pdf | 17 | 9 | 8 (89%) | 1 | 0 | 59 | 0 |
| CH_39docs.pdf | 78 | 39 | 39 (100%) | 0 | 6 | 78 | 1 |
| CH_51docs.pdf | 102 | 51 | 43 (84%) | 8 | 1 | 67 | 1 |
| CH_74docs.pdf | 150 | 76 | 60 (79%) | 16 | 2 | 73 | 2 |
| HLL_363docs.pdf | 538 | 372 | 214 (58%) | 158 | 30 | 75 | 30 |
| INS_31.pdf.pdf | 31 | 31 | 31 (100%) | 0 | 4 | 121 | 2 |

---

## Hallazgos Profundos

### 1. Tasa OCR Global y Eficiencia del Pipeline
- **OCR total procesado:** 3635 páginas en 539.9s → **148ms/pág promedio total** incluyendo inferencia, D-S y I/O.
- **SR (Super Resolución Tier 2)** se activó en 4 de 7 archivos. ART consume el 85% de ese cómputo (1248 de ~1291 SR total). En los CH* y HLL, SR es residual.
- **EasyOCR GPU** solo rescató 7 páginas en total (6 ART + 1 HLL). Aporte marginal en volumen, pero each rescued page mejora los anclajes del motor de inferencia exponencialmente.

### 2. Degradación de Completitud por Volumen (Ley de Escala)
Existe una relación inversa clara entre tamaño del documento y tasa de completitud:

| Archivo | Páginas | % Completos |
|---|---|---|
| CH_9 | 17 | 89% |
| CH_39 | 78 | 100% |
| CH_51 | 102 | 84% |
| CH_74 | 150 | 79% |
| HLL_363 | 538 | 58% |
| ART_674 | 2719 | 91%* |

*ART recupera bien gracias al `undercount_recovery` (12 docs fusionados) y al periodo muy estable (4 pags/ciclo, 79% conf). El caso atípico vs. la tendencia es una señal de que la regularidad interna del PDF compensa el volumen.

**HLL_363 es el caso más crítico (58%)** — no por falla de OCR (solo 30/538 fallan, 5.6%) sino por fallas de inferencia: **153 documentos con undercount** (páginas de 1 sola hoja que el motor lee como "nuevos docs" en vez de continuar el anterior). El problema real de HLL no es OCR, es segmentación de documentos.

### 3. Distribución de Tamaño de Documentos: La "Firma" de Cada PDF
El campo `dist` del log revela la estructura interna real:
- **ART:** `1p×4 4p×682 5p×1 12p×1` → 682 microdocumentos de 4 páginas exactas. Estructura ultra-regular.
- **HLL:** `1p×63 2p×307 3p×1 4p×1` → **63 documentos de 1 sola página** detectados. Aquí está el problema: hay documentos reales multi-página que se están partiendo en fragmentos de 1 página.
- **CH_74:** `1p×2 2p×58 3p×16` → 16 docs de 3 páginas y 2 docs de 1 página que deberían ser "2 de 2" truncados.
- **CH_51:** `1p×1 2p×43 3p×7` → 7 docs de 3 páginas que son documentos de 2 páginas con undercount.

### 4. Calidad de Inferencia D-S: Distribución de Confianzas
De los `759` inferidos en ART: `low:1 mid:125 hi:633` → **83% de las inferencias son alta confianza (≥60%)**. Solo 1 es baja confianza (p.11, 49%). El motor toma decisiones seguras la mayoría del tiempo.

Para HLL: `INF:30 x̄=79% 16✓14~0✗` → **16 de 30 inferidas son correctas (alta conf), 14 son inciertas (media)**. El motor no "sabe" que está fallando en la segmentación — está haciendo lo mejor posible con los datos OCR disponibles.

### 5. Detección de Período: El Cerebro Oculto
- **ART:** Período 4, conf 79% — muy preciso, explica el buen resultado.
- **HLL:** Período 2, conf **43%** — umbral de incertidumbre. El motor detecta que algo es "de 2 páginas" pero no está seguro. Exactamente donde ocurren los errores.
- **INS_31:** Período 1, conf 70% — cada charla = 1 página, correcto pero baja confianza por el documento de fin atípico.
- **CH_39:** Período 2, conf **96%** — datos limpios, motor perfecto (39/39 completos).

### 6. Fenómenos Anómalos en el Log
- **ART, páginas 1-16:** Todas con conf 48-53%. Son las **páginas de portada/carátula del PDF compuesto**, sin numeración interna tipo "Página X de N". El motor las infiere como "1/4" de la secuencia circundante — correcto desde el punto de vista lógico.
- **ART, página 1063:** Inferida como **"5/12"** — exactamente el umbral entre un doc de 4 páginas y un doc de 12 páginas. El motor detectó un período localmente distinto en esa zona del documento, probablemente un archivo con documentos de mayor longitud intercalados.
- **ART, páginas 1809-1812:** `1/1i → 1/1 → 1/1 → 1/4i` — el motor converge a un documento de 1 página embebido entre documentos de 4 páginas. Evidencia de un "charla especial" de 1 sola página en medio del batch.

### 7. Oportunidades Claras Para el Motor de Inferencia
Basado en el análisis, los quick wins para la rama `feature/inference-engine`:

1. **HLL_363 undercount:** 153 docs con undercount. Si el motor detectara mejor cuándo una "página 1 de 1" es en realidad una continuación truncada de un doc anterior, completitud subiría de 58% a potencialmente >80%.
2. **CH_74 undercount:** 16 docs de 3 páginas con declared_total=2. La heurística actual de undercount_recovery no los está reconstruyendo correctamente.
3. **Período con baja confianza (43% HLL):** El autocorrelador puede mejorarse con un paso de búsqueda local antes del global para detectar períodos mixtos (documentos de 1 y 2 páginas entrelazados).

---

## Números que Deben Mejorar en `feature/inference-engine`
| Métrica | Baseline Master | Objetivo |
|---|---|---|
| HLL completos | 214 / 372 (58%) | >280 / 372 (>75%) |
| CH_74 completos | 60 / 76 (79%) | >70 / 76 (>92%) |
| CH_51 completos | 43 / 51 (84%) | >48 / 51 (>94%) |
| ART completos | 612 / 676 (91%) | mantener ≥91% |
