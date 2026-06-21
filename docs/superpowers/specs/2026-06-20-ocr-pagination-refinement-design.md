# Refinamiento OCR — conteo por paginación (motor unificado, migración gradual)

**Fecha:** 2026-06-20
**Estado:** diseño (post-brainstorm, fundamentado en benchmark sobre corpus real MAYO)
**Rama:** `po_overhaul`
**Relacionado:**
- Spec OCR per-sigla: `docs/superpowers/specs/2026-05-18-ocr-per-sigla-refinement-design.md`
- Postmortem VLM: `docs/superpowers/reports/2026-03-29-vlm-integration-postmortem.md`
- Pixel-density (estructura sin OCR): `eval/pixel_density/README.md`

---

## 1. Propósito

Mejorar la confiabilidad del **pase 2** (conteo de documentos dentro de compilaciones)
del ~10% de celdas que el filename-glob no resuelve. Hoy 15 de 18 siglas usan
**anclas de texto** (frágiles, acopladas a plantilla, alto mantenimiento — ver el
postmortem de *anchor-truncation* 2026-05-22) y solo 2 (insgral, altura) cuentan por
**paginación "Página N de M"** vía el pesado motor V4.

El brainstorm + un benchmark sobre el corpus real (MAYO, escaneos a 130 dpi, fusionados)
demostró que **la paginación impresa es la señal de límite de documento más robusta a la
compresión**, legible por el Tesseract de producción, y aplicable a muchas más siglas que
las 2 actuales. Este spec define un **motor de conteo por paginación unificado** (corner
OCR consciente de orientación + recuperación liviana de huecos + enrutamiento por código
de formulario + confianza honesta) y una **migración gradual y reversible** de las siglas
paginables desde anclas hacia ese motor.

**Objetivo medible:** para cada sigla migrada, el conteo automático debe **igualar o superar**
al método actual contra verdad-terreno re-etiquetada, con una señal de confianza honesta
que mande las celdas dudosas al **contador manual por teclado** ya existente.

---

## 2. No-objetivos (YAGNI)

- **No** reescribir el motor de inferencia V4 (`core/pipeline.py` / `core/inference.py`).
  Se reutiliza su idea de recuperación, en versión liviana, fuera del solver.
- **No** integrar VLM al pipeline. El postmortem 2026-03-29 es definitivo: el motor maneja
  "sin dato" mejor que "dato equivocado", el umbral de break-even (~97%) no se alcanza, y el
  VLM local (Ollama) es lento e insuficiente. VLM queda, a lo más, como **auditoría offline**
  (cola de revisión), nunca alimentando el conteo. (D9)
- **No** perseguir automación total de las familias inherentemente difíciles
  (RCH = charla/chintegral/dif_pts por el bug "1 de 2"; senal por corner ilegible). Para
  esas, el contrato es **primer-tiro + confirmación manual**, no precisión ciega.
- **No** tocar el `count_type` (documents / documents_workers / checks) ni el conteo de
  trabajadores/chequeos. El motor cuenta **documentos**; trabajadores/chequeos siguen su
  camino actual (teclado).
- **No** cambiar el contrato de `ScanResult` ni la interfaz `count_ocr(...)`. El motor nuevo
  es una pieza intercambiable detrás de la misma interfaz (mismo `per_file`, `confidence`,
  `flags`, callback `on_pdf`).
- **No** rediseñar UX. La confianza honesta se engancha al sistema ya shipeado
  (`all_reliable` / punto verde por procedencia / chip de método / contador por teclado).

---

## 3. Contexto: el motor hoy y por qué cuesta

Conteo en dos pases, despachado por `core/scanners/patterns.py` (un `scan_strategy` por sigla):

- **Pase 1 — filename glob** (`SimpleFilenameScanner`): ~90% de celdas. 1 PDF = 1 documento.
- **Pase 2 — OCR**, triada de scanners por `scan_strategy`:
  - `anchors` (15 siglas) → `AnchorsScanner` → `count_covers_by_anchors`: OCR de la banda
    superior, cuenta una página como **portada** si matchea ≥ `min_match` anclas de un *flavor*.
  - `pagination` (2 siglas: insgral, altura) → `PaginationScanner` → `count_documents_v4`:
    el motor V4 completo (autocorrelación + Dempster-Shafer).
  - `none` (1: reunion) → solo filename.

**Por qué cuesta pasar del 90%:** heterogeneidad (4 hospitales × 18 siglas × muchas
plantillas de contratista × escaneo de teléfono con manuscrito y timbres). La estrategia de
anclas está **acoplada a la plantilla por diseño**: cada formato nuevo es un flavor nuevo, el
ruido OCR tumba anclas, y el mantenimiento es perpetuo. Las anclas keyean en texto chico
junto a manuscrito/timbres — justo lo que la compresión a 130 dpi degrada.

---

## 4. Evidencia del benchmark (corpus real MAYO)

Medido con el Tesseract de producción (`--psm 6 --oem 1`, spa+eng) sobre archivos reales,
verdad-terreno = tus conteos de MAYO (`override`/`filename_glob`) re-etiquetados donde la base
miente. Detalle de scripts de diligencia en `eval/pagination_count/` (ver §10).

| Familia (archivo) | Resultado paginación-primero | Lectura |
|---|---|---|
| odi (HRB, 42p) | **21/21** | exacto |
| altura (HLU, 41p) | **20/20** | exacto |
| ext (HLL, 38p) | **38/38** | exacto |
| bodega (HLL, 2p) | **2/2** | exacto |
| insgral (HLL 6p / HLU 48p) | agrupa 6p→1 doc; cuenta 48 sueltos | exacto, maneja heterogeneidad |
| caliente (HLL, 60p) | 57/60 | 3 corners ilegibles → recuperables |
| **art** (HLL fusionado degradado, 120p) | crudo **22** → recuperado **31** (GT≈30) | requiere recuperación; la liviana basta |
| **irl** (HLU, 1 paquete de 54p) | ingenuo **17** → código-consciente **1** | contar solo portadas `F-CRS-ODI-01` |
| charla/chintegral/dif_pts (RCH) | sobre-cuenta multipágina (bug "1 de 2"); exacto en 1p | se queda en anclas |
| senal (HLL, 24p, landscape) | 0/24 (corner ilegible) | se queda en anclas (texto del cuerpo) |

**Hallazgos clave:**
1. La paginación impresa es legible y precisa donde existe (Tier A).
2. En escaneos degradados (ART fusionado) el corner falla ~45%, pero **recuperación por
   secuencia** (total dominante = 4, completar el ciclo desde vecinos) recupera `123412341234…`
   limpio → 31 ≈ 30. **No hace falta el solver pesado** para contar límites. (D3)
3. El **código de formulario** del corner (`F-CRS-ART-01`, `F-CRS-ODI-01`, `F-LCH-CRS-36`…)
   también es legible → enrutamiento + identidad de plantilla. (D4)
4. **Bug RCH confirmado** empíricamente: continuaciones de 2 páginas leen "1 de 2" → la
   paginación sobre-cuenta. RCH se queda en anclas. (D6)
5. **IRL** = paquete de inducción (1 formulario IRL largo "N de 31" + anexos). El conteo
   correcto = portadas IRL (`F-CRS-ODI-01`), no todas las páginas-1. (D5)
6. **Calidad de datos:** la verdad-terreno de las familias difíciles **no es confiable**
   (chintegral HLL: base dice 2, real ~20–35). Refuerza el modelo primer-tiro + confirmación
   manual. (D8)

---

## 5. El fit por categoría (verbatim — autoridad para las capas siguientes)

> Regla de migración (D7): una sigla migra a `pagination` **solo si** el benchmark del eval
> muestra que iguala/supera al método actual contra GT re-etiquetada. Las marcadas
> "(verificar)" son candidatas cuya migración decide el eval. Reversible: si una sigla
> regresa, vuelve a `anchors` cambiando un campo en `patterns.py`.

| sigla | count_type | hoy | propuesto | señal de límite |
|---|---|---|---|---|
| reunion | documents | none | none | nombre de archivo |
| irl | documents | anchors | **pagination + `cover_code=F-CRS-ODI-01`** | portada IRL |
| odi | documents | anchors | **pagination** | "Página 1 de 2" |
| charla | documents_workers | anchors | **anchors (sin cambio)** | portada RCH |
| chintegral | documents_workers | anchors | **anchors (sin cambio)** | portada RCH |
| dif_pts | documents_workers | anchors | **anchors (sin cambio)** | portada RCH |
| art | documents | anchors | **pagination + recuperación** | "Página 1 de 4" |
| insgral | documents | pagination (V4) | **pagination (motor liviano)** | "Página N de M" |
| bodega | documents | anchors | **pagination** | "Página 1 de 1" |
| maquinaria | checks | anchors | **anchors (sin cambio — es checks)** | — |
| ext | documents | anchors | **pagination** | "Página 1 de 1" |
| senal | documents | anchors | **anchors (corner landscape ilegible)** | texto del cuerpo |
| exc | documents | anchors | **pagination (verificar)** | LCH "Página N de M" |
| altura | documents | pagination (V4) | **pagination (motor liviano)** | "Página N de M" |
| caliente | documents | anchors | **pagination** | "Página 1 de 1" |
| herramientas_elec | documents | anchors | **pagination (verificar)** | LCH "Página N de M" |
| andamios | documents | anchors | **pagination (verificar)** | LCH "Página N de M" |
| chps | documents | anchors | **anchors (acta de reunión)** | portada acta |

**Resumen:** ~8–11 siglas a paginación (alta confianza), 5 se quedan en anclas (RCH×3, senal,
chps), 1 checks (maquinaria), 1 none (reunion).

---

## 6. El motor de conteo por paginación

Nuevo util `core/scanners/utils/pagination_count.py`, prototipado y validado primero en
`eval/pagination_count/engine.py` (§10). Función pública:

```python
def count_documents_by_pagination(
    pdf_path: Path,
    *,
    cancel: CancellationToken,
    cover_code: str | None = None,       # IRL: contar solo portadas con este código
    on_page: Callable[[int, int], None] | None = None,
) -> PaginationCountResult
```

`PaginationCountResult` (frozen): `count`, `pages_total`, `direct_reads`, `recovered_reads`,
`failed_reads`, `dominant_total`, `codes: dict[str,int]`.

**Pipeline por PDF:**

1. **Render del corner, consciente de orientación** (D2). Por página: detectar `w>h`
   (landscape) y ajustar el recorte top-right; render a ~3× (≈216 dpi) en gris. El corner
   top-right contiene paginación + código en ambas orientaciones.
2. **OCR + parseo.** Tesseract `--psm 6 --oem 1` spa+eng; normalización de dígitos
   (`O→0, l/I/|→1, S→5, …`); dos regex:
   - completa: `p[aá]gina\s*(\d+)\s*de\s*(\d+)` → (curr, total).
   - solo-curr (fallback): `p[aá]gina\.?\s*(\d+)` → (curr, None) — para formularios que
     imprimen "Página 1" sin total.
   - código: `F[-\s]?[A-Z]{2,4}[-\s][A-Z0-9\-]{2,12}`.
   - **Precedencia:** se prueba la regex completa primero; la solo-curr aplica **solo** si la
     completa no matchea (evita un doble match en "Página 12 de 20").
3. **Recuperación de huecos por secuencia** (D3). `dominant_total` = total más frecuente.
   Para páginas sin lectura: inferir `curr` continuando el ciclo desde el vecino izquierdo
   (`prev % dom + 1`) o derecho. Marca esas lecturas como `recovered` (menor confianza).
   **Sin** autocorrelación ni Dempster-Shafer (eso es V4); esto es completar una secuencia
   aritmética. No alimenta ningún solver → sin el daño cascada del postmortem. **Semántica de
   lecturas:** una página sin lectura pero rodeada de lecturas válidas con total consistente →
   `recovered`; una sin contexto de secuencia utilizable (sin total dominante, u huérfana en un
   extremo sin vecino válido) → `failed`.
4. **Conteo de límites.** Un documento empieza en cada página con `curr == 1`. Si
   `cover_code` está seteado (IRL): contar solo las `curr==1` cuyo código de página matchea
   `cover_code` (ignora portadas-1 de anexos). (D5)
5. **A7** (heredado): un PDF de 1 página = 1 documento sin OCR.
6. **Confianza honesta** (D8): `HIGH` si `recovered_reads / pages_total` es baja (la mayoría
   leídas directo) y `failed_reads == 0`; si no, `LOW` → la celda se marca para revisión
   manual. Umbral exacto se fija en el eval.

**Guardas de degeneración** (heredadas de la lógica V4): conteo 0 en un multipágina nunca es
correcto → fallback a 1 + LOW; un PDF ilegible → 1 + LOW + flag.

---

## 7. Integración (triada de scanners, sin romper contratos)

- **`patterns.py`**: extender `SiglaPattern` con campos opcionales para `scan_strategy="pagination"`:
  `cover_code: NotRequired[str]` (IRL). Migrar las siglas Tier A a `scan_strategy="pagination"`.
  Bump de `SCANNER_PATTERNS_VERSION`. Para IRL los **tres cambios van juntos**: extender el
  typedef, setear `cover_code="F-CRS-ODI-01"` en la entrada `irl`, y bump de versión (si no, el
  campo se ignora en runtime hasta que la entrada lo use).
- **`PaginationScanner`**: hoy llama `count_documents_v4`. Pasa a llamar
  `count_documents_by_pagination(...)` (motor liviano) como **primario**, leyendo `cover_code`
  del pattern. Mantiene **idéntica** la interfaz `count_ocr(folder, *, cancel, on_pdf, only,
  skip, on_page)`, el manejo A7/A8, el `per_file`, los `flags`, y el callback `on_pdf` (method
  pasa a `"pagination"`). Además **enhebra `on_page`** desde `count_ocr` hacia el motor: a
  diferencia de V4 (sin hook por página), el motor nuevo lo dispara por página → la barra del
  visor por fin muestra progreso en vivo para insgral/altura. (D1)
- **V4 como fallback opcional** (D10): si el motor liviano devuelve `LOW` (mucha
  recuperación), el scanner *puede* reintentar con `count_documents_v4` y quedarse con el de
  mayor confianza. Decisión de activarlo: gated por el eval (si V4 no mejora, no se invoca —
  evita el costo). Por defecto **off** hasta que el eval lo justifique.
- **Frontend**: nuevo valor de `method` `"pagination"` en el chip de procedencia (paralelo a
  `header_band_anchors`/`v4`). La confianza `LOW` ya enciende ámbar + ruta al teclado por el
  sistema honesto existente. Sin lógica de gating nueva.

---

## 8. El rol: primer-tiro honesto + confirmación manual

El motor produce un **conteo + confianza por celda**, no una autoridad ciega. Se engancha al
sistema ya shipeado:
- Confianza `HIGH` (mayoría directo) → la celda puede quedar verde por procedencia.
- Confianza `LOW` (mucha recuperación / familia RCH / GT dudosa) → ámbar + el operador
  confirma con el **contador por teclado** (Feature 1/2, ya existe) o ajuste manual.

Esto es coherente con `conteo-confiable` (modelo honesto ya shipeado) y con la recomendación
del postmortem VLM ("cola de revisión humana, sin VLM en el pipeline").

---

## 9. VLM: fuera del pipeline

Reafirmado por el postmortem 2026-03-29 (local Ollama probado por Daniel, no fue éxito):
el conteo **nunca** se alimenta de lecturas VLM. Si en el futuro se quiere, sería un
**oráculo de auditoría offline** (yo/Claude API mirando una muestra para generar una cola de
revisión priorizada), nunca en línea. No es parte de este spec.

---

## 10. Plan de eval (eval-first, obligatorio)

Nuevo stage `eval/pagination_count/` (committeado, no throwaway):
- `engine.py` — copia prototipo del motor (igual patrón que `inference_tuning/inference.py`),
  para iterar sin tocar core.
- `samples.py` — manifiesto de **muestras livianas**: `(hospital, sigla, archivo, rango_de_páginas)`
  con **GT etiquetada a mano por mí** (especialmente donde la base miente: chintegral, insgral
  multipágina, altura). Rebanadas de ~30–60 páginas, nunca los monstruos enteros (restricción
  de Daniel: "el cuerpo completo es demasiado").
- `benchmark.py` — corre, por muestra: **scanner actual** (anclas/V4) vs **motor nuevo** vs GT.
- `report.py` — exactitud por familia + tasa de recuperación + falsos límites (tabla Markdown a stdout).
- Métrica de aceptación por sigla (gate de migración, D7): error absoluto del motor nuevo ≤
  error del método actual, en todas las muestras de esa sigla.

Verdad-terreno: re-etiquetar a mano las muestras (yo cuento las rebanadas mirando todas las
señales — layout, campos, código — no solo la paginación, para no ser circular).

Tras validar en eval → portar `engine.py` a `core/scanners/utils/pagination_count.py` y migrar
siglas. La paridad eval↔core se cuida (mismo motor, copia controlada).

---

## 11. Despliegue gradual y reversible

1. Eval valida el motor + decide qué siglas migran (Tier A confirmadas + las "(verificar)").
2. Portar motor a core; migrar siglas **una por una** en `patterns.py`, cada una detrás de su
   gate de eval. Bump `SCANNER_PATTERNS_VERSION`.
3. Smoke en vivo (Brave debug, copia de DB en puerto aparte, nunca la `overseer.db` real)
   sobre un mes real, comparando conteos pre/post por celda.
4. Si una sigla empeora en vivo → revertir esa sigla a `anchors` (un campo). El resto queda.

Seguridad de datos: el corpus (`INFORME_MENSUAL_ROOT`) es **solo lectura**; el smoke usa una
copia de `overseer.db`; nada destructivo.

---

## 12. Riesgos

| Riesgo | Mitigación |
|---|---|
| Paginación ausente/ilegible en una sigla "(verificar)" (como senal) | El gate de eval la deja en anclas; no migra |
| Recuperación inventa límites (falsos `curr==1` por OCR ruidoso) | Recuperación solo rellena huecos entre lecturas válidas; guarda de total dominante; confianza LOW si mucha recuperación |
| Regresión en insgral/altura al cambiar V4→liviano | Gate de no-regresión en eval con GT re-etiquetada; V4 como fallback opcional (D10) |
| Plantilla nueva sin paginación entra al corpus | Confianza LOW + ruta a teclado; A7 y guardas de degeneración protegen el conteo |
| Orientación landscape mal recortada | Detección `w>h` + recorte por orientación, validado en eval (senal es el caso de prueba) |
| Costo OCR del corner por página | Solo se OCRea un recorte chico del corner, no la página entera; más barato que las anclas (banda superior completa) y que V4 (página completa) |

---

## 13. Registro de decisiones

- **D1** — El motor nuevo es intercambiable detrás de la interfaz `count_ocr`/`ScanResult`
  existente. Sin cambios de contrato → sin cambios obligados de frontend.
- **D2** — Corner OCR consciente de orientación (portrait/landscape), acepta "N de M" y
  "Página N" sin total.
- **D3** — Recuperación de huecos por **completar la secuencia** (liviana), no por el solver
  Dempster-Shafer. Validado: ART 22→31 (GT≈30).
- **D4** — Extraer el **código de formulario** del corner para enrutar e identificar plantilla.
- **D5** — **IRL** se cuenta por portadas `F-CRS-ODI-01` (`cover_code`), ignorando portadas-1
  de anexos.
- **D6** — **RCH** (charla/chintegral/dif_pts) **no** migra: bug "1 de 2" confirmado. Sigue
  en anclas.
- **D7** — Migración **gated por eval, sigla por sigla, reversible**. Migra solo si iguala/supera
  al método actual contra GT.
- **D8** — Confianza honesta por fracción de lecturas recuperadas; `LOW` → revisión por teclado.
  La GT de familias difíciles no es confiable (chintegral=2 falso) → no perseguir precisión ciega.
- **D9** — VLM **fuera del pipeline** (postmortem). A lo más auditoría offline futura.
- **D10** — V4 queda como **fallback opcional** para celdas `LOW`; activación gated por eval
  (off por defecto si no mejora).
- **D11** — `senal` y `chps` se quedan en anclas (corner ilegible / acta); `maquinaria` es
  `checks` (aparte); `reunion` es `none`.
