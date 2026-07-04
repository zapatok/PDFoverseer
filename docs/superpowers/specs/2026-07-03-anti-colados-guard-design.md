# Guard anti-colados — design spec

**Fecha:** 2026-07-03
**Estado:** aprobado por Daniel (diseño de 2 vertientes, 2026-07-03)
**Alcance:** detección de documentos mal archivados ("colados") + sugerencia de
corrección vía las ops de reorganización Incr-J existentes. **Ningún conteo
cambia por detección.**

---

## 1. Problema

Según Daniel (2026-07-03), **el 2-3% del corpus mensual llega colado**, peor en
HRB. Dos formas, aproximadamente mitad y mitad:

- **(a) Archivo completo** en la carpeta de categoría equivocada.
- **(b) Documento interior**: páginas de otra categoría escaneadas dentro de una
  compilación legítima de varias páginas.

Comportamiento actual por tipo de celda:

| Tipo de celda | Forma (a): archivo ajeno en la carpeta | Forma (b): páginas ajenas dentro de un PDF |
|---|---|---|
| pase-1 por token (~90%) | **desaparece**: no matchea el token del host (no cuenta ahí) y su celda verdadera no lo ve (enumera otra carpeta) → subconteo silencioso en la celda verdadera | cuenta 1 por archivo — el colado interior queda absorbido |
| pase-2 `pagination` (12 siglas) | **cuenta completo** en la celda equivocada: el scanner OCR itera TODO PDF de la carpeta (`enumerate_cell_pdfs` = `rglob`, sin filtro por nombre) y cuenta por "Página N de M" sin mirar QUÉ documento es | **cuenta como documentos del host** — el caso que el audit 2026-07-02 dejó como pregunta abierta (caveat de los shadow fixtures de andamios/herramientas_elec) |
| pase-2 `anchors` (6 siglas) | protegida por anti_anchors (contenido) | ídem |
| `count_scope: "folder"` (chps) | cuenta (la carpeta ES el clasificador) | absorbido |

**Decisión de producto (Daniel, 2026-07-03):** al detectar → **contar igual +
marcar + sugerir la op de reorg pre-llenada**. Nunca excluir automáticamente:
el número lo cambia el operador (aceptando la op, cuyo delta ya hace la
corrección vía la maquinaria Incr-J, y cuyo manifiesto le indica a paso-1 la
corrección física — el consumidor en paso-1 está operativo desde 2026-07-03).

## 2. Principios de diseño

1. **Solo evidencia positiva ajena.** Un sospechoso requiere que la evidencia
   matchee positivamente el identificador de OTRA sigla **y no** el del host.
   Evidencia ausente, ilegible, desconocida o ambigua (matchea host y ajeno)
   → **silencio**. Corolario: el guard degrada hacia el silencio (= estado
   actual), nunca hacia falsas alarmas. Un cambio futuro de template produce
   códigos "desconocidos" → silencio, no ruido.
2. **La detección no toca conteos.** Invariante verificable: el OUTPUT GUARD
   (dump de counts vs baseline) da diff vacío con el guard activo.
3. **Opt-in por datos** (vertiente 2): solo las siglas con `expected_codes`
   poblado se verifican por código. Sin datos → sin guard → sin falsos.
4. **Una sola superficie**: ambas vertientes alimentan la misma lista de
   sospechosos en el estado de la celda, el mismo panel UI y el mismo botón
   de op de reorg (endpoints Incr-J existentes, sin lógica de op nueva).
5. **Confianza derivada, no horneada**: el ámbar por sospechoso se deriva de
   la lista viva de sospechosos (patrón `refresh_all_reliable` /
   `reorg_doc_delta`), de modo que descartar o crear la op restaura el estado
   sin re-scan.

## 3. Vertiente 1 — guard por filename (pase 1, las 20 siglas, costo cero)

**Señal:** el nombre del archivo. `2026-05-04_odi_jhon.pdf` en la carpeta de
ART se delata solo.

**Regla:** para cada PDF de la carpeta de la celda `(hospital, sigla_host)`:
- La pregunta de esta vertiente es **"¿qué sigla sugiere este NOMBRE?"** — que
  NO es la pregunta de `_matches` ("¿este archivo pertenece al conteo de la
  sigla X?"). `_matches` tiene el escape `count_scope == "folder"` (chps):
  devuelve True para *cualquier* PDF — usarlo aquí haría que todo archivo del
  corpus "sugiera" chps (tormenta de falsos) y que chps jamás pudiera marcar
  (todo matchearía al host). Por eso `filename_glob.py` expone un helper
  nuevo, **`siglas_suggested_by_filename(basename) -> set[str]`**, que evalúa
  SOLO los patrones de token compilados + `_SIGLA_TOKEN_ALIASES` (`cphs`, la
  frase `revision_documentacion`, etc.) de las 20 siglas, **ignorando
  `count_scope`**. Reutiliza `_SIGLA_PATTERNS` internamente — el matching de
  tokens sigue teniendo una sola fuente (estilo F5), solo que sin el escape
  de carpeta, y devuelve el SET completo (necesario para la regla "2+").
- Con `S = siglas_suggested_by_filename(basename)`:
  - `sigla_host ∈ S` (con o sin ajenas) → silencio.
  - `S = ∅` (ej. `crs.pdf`, `titan.pdf`) → silencio.
  - `S = {s'}` con s' ajena → sospechoso, `suggested_sigla = s'`.
  - `|S| ≥ 2` (todas ajenas) → sospechoso con `suggested_sigla = null` (el
    operador elige el destino en el formulario de la op).
- Sugerencia: `move_file` con `dest = {mismo hospital, suggested_sigla}`;
  `doc_count`/`worker_count` por los defaults Incr-J existentes
  (`resolve_op_defaults`).

**Dónde corre:** dentro del scan de pase-1 (el pase de ~4 s), como parte del
resultado por celda — el cómputo es una función pura
`find_foreign_filename_suspects(files, sigla_host)` en el módulo nuevo
`core/scanners/utils/colado_guard.py`.

**Cobertura extra:** los PDFs de 1 página (que A7 jamás OCRea) SÍ quedan
cubiertos por esta vertiente cuando su nombre los delata.

## 4. Vertiente 2 — guard por código de formulario (pase 2, siglas `pagination` opt-in)

**Señal:** la esquina superior derecha que el motor ya OCRea para la
paginación trae impreso el código de control del formulario
(`F-CRS-ART-01`…). `extract_code` ya lo captura en
`PaginationCountResult.codes`; hoy se descarta (salvo `cover_code` en
irl/espacios). **No hay OCR nuevo.**

### 4.1 Datos: `expected_codes` por sigla (`patterns.py`)

Campo opcional `expected_codes: list[str]` en la entrada de la sigla. Cada
entrada es un código exacto o un prefijo terminado en `*`. Datos del survey
rápido 2026-07-03 (muestras MAYO, a confirmar por el survey profundo — §7):

| sigla | expected_codes (provisional) | evidencia |
|---|---|---|
| art | `F-CRS-ART-01` | 4/4 y 2/6 legibles (+ruido `ARTO1`, `FECHA-31`) |
| irl | `F-CRS-ODI-01` | 6/6 en 2 muestras (ya es su `cover_code`) |
| odi | `F-CRS-ODI-03` | 2/2 en 2 muestras |
| exc | `F-CRS-LCH-31` | 6/6 en 2 muestras (+variante OCR `F-CRG-`) |
| altura | `F-PETS-CRS-01-01` | 5/6 y 6/6 |
| espacios | `F-PETS-CRS-08*` (familia: 00/01/04 legítimos en un mismo paquete) | muestra HLL |
| ext | **sin código** en la esquina (pagination 6/6, códigos 0) → **fuera** | confirmado |
| insgral, bodega, caliente, herramientas_elec, andamios | sin datos (muestras de 1 página) → survey profundo decide | pendiente |

**Lecciones fijadas por el survey rápido (verbatim, no re-derivar):**
- El prefijo de familia NO basta: irl=`F-CRS-ODI-01` vs odi=`F-CRS-ODI-03`
  (misma familia, siglas distintas). Matching por código completo
  normalizado; `*` solo donde la familia entera es de una sigla (espacios).
- NO endurecer el regex `_CODE`: espacios pierde a veces el primer guion
  (`FPETS-CRS-08-00`); el filtro de ruido es la regla de decisión (un código
  que no matchea el set de NINGUNA sigla se ignora — `FECHA-31` muere solo).

### 4.2 Normalización de comparación

Ambos lados (código leído y `expected_codes`) se normalizan igual:
mayúsculas → quitar todo no-alfanumérico → plegar confusiones OCR con el mapa
`_DIGIT` existente (O→0, I/l/|→1, Z→2, S→5, B→8). La igualdad se preserva
(mismo pliegue en ambos lados). **Test de registro obligatorio:** distinción
par-a-par de todos los `expected_codes` normalizados entre siglas distintas
(guard de colisión — si dos siglas colisionan post-pliegue, el test bloquea la
entrada de datos). Semántica con comodín: literal-vs-literal = igualdad
normalizada; **prefijo`*`-vs-literal = colisión si el literal empieza con el
prefijo normalizado; prefijo-vs-prefijo = colisión si uno contiene al otro**
(una comparación de igualdad simple no detectaría el solape — hoy solo
espacios usa `*`, pero el survey §7 puede agregar más).

### 4.3 Segmentación por documento (motor, `pagination_count.py`)

Función pura nueva: segmentar las `PageRead` en los **documentos contados** —
un segmento por inicio contado (la MISMA regla de `count_starts`, incluido el
filtro `cover_code`, para que los segmentos coincidan 1:1 con lo que se
contó). Páginas antes del primer inicio contado se adjuntan al primer
segmento; si no hubo inicios (fallback conteo=1), un único segmento cubre el
archivo. Nuevo dataclass `DocSegment {page_start, page_end (1-based,
inclusivo), codes}` con solo códigos de lecturas `direct` (las recuperadas no
tienen esquina leída); `PaginationCountResult` gana `documents:
list[DocSegment]`.

### 4.4 Regla de decisión por segmento

Con `own` = set normalizado del host, `foreign(s')` = sets del resto:
- Página con ≥1 lectura que matchea `foreign(s')` y ninguna que matchee
  `own` → página ajena (atribuida a s').
- **Corridas máximas consecutivas de páginas ajenas** dentro del segmento →
  un sospechoso `{page_range, código dominante, suggested_sigla}`. Una página
  sin evidencia (sin lectura de código) interrumpe la corrida: dos corridas
  separadas → dos sospechosos/`extract_pages` (aceptado: fricción menor, pero
  nunca un rango que abarque páginas sin evidencia).
- Sugerencia `move_file` (archivo completo) **solo si** las corridas ajenas
  cubren TODAS las páginas del PDF **y todas sugieren la MISMA sigla** (una
  op `move_file` tiene un único destino). En cualquier otro caso →
  `extract_pages` por corrida, aunque en conjunto cubran el archivo.
- Host sin `expected_codes` → vertiente 2 apagada para esa celda.
- Código que matchea host y ajeno a la vez → own (silencio; el test §4.2 lo
  hace imposible en la práctica).

### 4.5 Confianza

Cada sospechoso lleva `counted: bool` — **derivado de los datos, no de una
taxonomía de celdas** (la taxonomía miente: un archivo ajeno en irl/espacios
cae al fallback conteo=1 del scanner aunque `cover_code` no matchee; en una
celda anchors multipágina aporta 0 por F8; con A7 un ajeno de 1 página aporta
1):

- **Sospechoso `kind="code"`** → `counted = true` por construcción (los
  segmentos son exactamente los documentos contados).
- **Sospechoso `kind="filename"`** → `counted = (contribución actual del
  archivo al conteo del host) > 0`, leída de los MISMOS datos per-file que
  usa `compute_cell_count` (`per_file_overrides[f] | per_file[f] | ausente→0
  en celdas por token; en celdas OCR/`count_scope:"folder"` el archivo tiene
  entrada per-file tras el scan). Sin taxonomía paralela que mantener.

**Efecto de un sospechoso abierto con `counted=true`:** la celda deja de ser
confiable **plegándose a la derivación existente de `all_reliable`**
(backend: la recomputación estilo `refresh_all_reliable` considera "hay
sospechosos abiertos contados" → `all_reliable=false`). Se elige este punto
de integración y NO uno nuevo porque: (1) el frontend ya consume
`all_reliable` para el punto verde — **cero cable nuevo, cero riesgo de
divergencia front/back** (la clase de bug F15/toast-asymmetry); (2) la
precedencia existente se conserva tal cual: `por_resolver` > `confirmed |
override` (verde ganado por humano NO es anulado por un sospechoso — el
panel sigue mostrándolo, la información no se pierde) > `all_reliable`.
Sospechoso con `counted=false` (vertiente 1 en celda por token: el archivo no
sumó) **no** toca `all_reliable` — el conteo del host es correcto; el panel
es la superficie. Derivación viva en ambos casos (§2.5), nunca horneada en
`per_file`: descartar o crear la op restaura el verde sin re-scan.

## 5. Ciclo de vida de los sospechosos

- Estado de celda gana `colado_suspects: list[Suspect]`;
  `Suspect = {id, kind: "filename"|"code", file, page_range: [a,b] | null,
  evidence: str, suggested_sigla: str | null, counted: bool}`.
  `id = "cs_" + sha1(kind|file|page_range|suggested_sigla)[:10]` —
  determinístico sobre la evidencia; sirve solo para direccionar el descarte.
- **Refresh por kind, quirúrgico** (el precedente near_matches hace wipe
  total en pase-1 + evict-por-archivo en OCR, pero tiene un solo kind; aquí
  hay dos con dueños distintos):
  - el scan de **pase-1** reemplaza SOLO las entradas `kind=="filename"` de
    la celda;
  - el OCR (de celda o de archivo suelto) reemplaza SOLO las entradas
    `kind=="code"` **de los PDFs efectivamente escaneados**.
- **Precedencia entre vertientes sobre el mismo archivo:** si existe un
  sospechoso `filename` (archivo completo) para F, los sospechosos `code` de
  F se suprimen — la sugerencia de archivo completo subsume los rangos; los
  `code` solo aparecen en archivos cuyo nombre no delató nada.
- **Descartar** (el operador dice "es legítimo") elimina el sospechoso hasta
  el próximo scan que refresque su kind en esa celda (sin supresiones
  permanentes ocultas — consistente con near_matches; el microcopy del panel
  lo advierte).
- **Dedupe contra ops de reorg existentes** (evita re-sugerir mientras la
  corrección física espera a paso-1), con regla explícita para rangos nulos
  (`move_file` no lleva `page_range`; los sospechosos de archivo completo
  tampoco):

  | sospechoso \ op existente sobre el mismo `source.file` | `move_file` (sin rango) | `extract_pages [c,d]` | `rotate` / `split_in_place` |
  |---|---|---|---|
  | `filename` (rango null) | **suprimir** | mantener (la op parcial no resuelve el archivo) | mantener |
  | `code [a,b]` | **suprimir** (el archivo entero ya se va) | suprimir ⟺ `[a,b]` solapa `[c,d]` | mantener |

- **Crear la op** desde el panel usa el `POST /reorg/ops` existente
  (pre-llenado); el sospechoso desaparece de la lista abierta por el dedupe
  de arriba (queda la op en el panel REORGANIZACIÓN como superficie de
  seguimiento; si la op se borra, el sospechoso reaparece solo — dedupe
  derivado, no estado).

## 6. API + UI

- **Payload:** `colado_suspects` viaja en el estado de la celda (snapshot
  `cell_updated` incluido).
- **Endpoint nuevo (descarte):** `POST
  /api/sessions/{sid}/cells/{hospital}/{sigla}/colado-suspects/{suspect_id}/dismiss`
  con body `{participant_id}` — método de escritura del manager con lock M3
  (primera sentencia `CellLockedError` si la celda la tiene otro → 409 con
  `lock_holder`, patrón de los 6 write-methods) + auto-claim del agente si
  aplica + broadcast `cell_updated` + recomputación de `all_reliable`.
  `suspect_id` inexistente → 404 (idempotencia amable: descartar dos veces no
  es error de datos, es 404 del segundo). La creación de op NO agrega backend
  nuevo (endpoint Incr-J existente).
- **UI (DetailPanel):** sección **"POSIBLES COLADOS"** en tono suspect
  (patrón OrphanMarksPanel): por fila → chip de tipo (`Archivo` | `Páginas`),
  nombre del archivo, rango de páginas (si aplica), evidencia (token o
  código leído), sigla sugerida (label de `sigla-labels.js`), botones
  **"Crear op de reorg"** y **"Descartar"**. Tokens `po-*`, primitivas
  compartidas (`Badge`, etc.), español neutro.
- La celda con sospechoso contado se ve ámbar por el camino LOW existente —
  sin código nuevo de gating.

## 7. Compuerta 1 de implementación: survey profundo de códigos

Antes de poblar `expected_codes`:
- Herramienta committeada `tools/survey_form_codes.py` (solo lectura,
  reutilizable para mantenimiento A13): ABRIL + MAYO × 4 hospitales, **solo
  PDFs multipágina** (los de 1 página nunca ven la vertiente 2), cap por
  sigla (~8 PDFs × 8 páginas), **HRB reforzado** (ahí está el problema).
- Salida: tabla código×frecuencia por sigla → propuesta de `expected_codes`.
- **Criterio de aborto de la vertiente 2:** si <4 siglas quedan viables o hay
  contradicciones entre hospitales sin resolver, se informa a Daniel con el
  mapa y se decide (la vertiente 1 se embarca igual — no depende de códigos).
- El mapa final se presenta a Daniel antes de fijar los datos.

**Faseo del plan (obligatorio):** la vertiente 1 no tiene prerequisitos y se
implementa/embarca primero, completa (detección + estado + panel + descarte +
op pre-llenada); la vertiente 2 va después, detrás de esta compuerta — el
patrón de fases de los milestones previos (Incrementos, M1→M3b). Así la mitad
barata y sin riesgo del feature no queda bloqueada por la mitad
dependiente-de-datos.

## 8. Testing

- **Puras:** segmentación (con `cover_code`, preámbulo, fallback sin
  inicios); normalización/pliegue; regla de decisión (own/foreign/mixto/
  desconocido/ruido `FECHA-31`/multi-ajena → `suggested_sigla null`);
  corridas máximas (incl. interrupción por página sin evidencia → 2
  sospechosos); move_file solo con sigla única + cobertura total (multi-sigla
  cubriendo el archivo → extract_pages); la tabla de dedupe §5 completa
  (rangos nulos en ambas direcciones, rotate/split nunca suprimen);
  precedencia filename-sobre-code en el mismo archivo.
- **Vertiente 1:** unit de `siglas_suggested_by_filename` con nombres reales
  y aliases (`cphs`, frase `revision_documentacion`) en ambas direcciones
  (host presente en el set suprime), y el caso chps explícito: `crs.pdf`/
  `titan.pdf` sugieren ∅ (jamás "todo PDF sugiere chps"), y un `odi_x.pdf` en
  la carpeta chps sí marca con `counted=true`.
- **`counted` data-driven:** ajeno en celda por token → false; ajeno en celda
  OCR (fallback=1) → true; ajeno 1-página (A7) en celda OCR → true; ajeno
  multipágina 0-covers en celda anchors → false.
- **Registro:** distinción par-a-par de `expected_codes` normalizados (§4.2)
  + gate de completitud existente intacto.
- **Integración:** fixture sintético de colado (páginas con código art
  dentro de una compilación odi — PDFs sintéticos estilo
  `eval/pagination_count`, jamás datos personales); scan → sospechosos en
  estado → descarte (M3 lock + 409) → dedupe con op creada.
- **Frontend:** vitest del panel (render, acciones, estados) + store.
- **OUTPUT GUARD:** grid completo de counts byte-idéntico con el guard
  activo (invariante §2.2); rescan-diff vacío.
- Shadow fixtures de andamios/herramientas_elec: si el survey les da
  `expected_codes`, el caveat del README se resuelve con tests reales del
  guard; si no, el caveat queda documentado tal cual.

## 9. Fuera de alcance / límites (documentar en core/CLAUDE.md)

- **PDF de 1 página con nombre inocente y contenido ajeno**: invisible (A7 no
  lo OCRea y el nombre no lo delata). Tocarlo multiplicaría el tiempo de scan
  de los meses divididos; se acepta.
- **Siglas sin código legible** (ext confirmado; otras según survey): sin
  vertiente 2; vertiente 1 sigue activa.
- **Siglas `anchors`**: sin vertiente 2 (anti_anchors ya cubre contenido);
  vertiente 1 activa.
- **Colados entre hospitales** (archivo de HPV en carpeta de HRB): el nombre
  no trae hospital — indetectable, fuera de alcance.
- **Nunca** exclusión automática del conteo.

## 10. Versionado y convenciones

- `SCANNER_PATTERNS_VERSION` v6 → **`v7-colado-guard`** (`core/utils.py`).
- Módulo nuevo `core/scanners/utils/colado_guard.py` (una responsabilidad:
  detección; sin I/O de PDF — funciones puras sobre nombres/segmentos).
- Sin cambios en el contrato del manifiesto paso-1 (`manifest_version: 1`).
- Commits `feat(guard): …`; ruff 0; sin mocks de DB; español neutro en UI.

## 11. Registro de decisiones (Daniel, 2026-07-03)

1. Respuesta a la detección: **contar + marcar + sugerir reorg** (opción
   recomendada; excluir automáticamente rechazado por filosofía).
2. Frecuencia real estimada: **2-3% del corpus**, peor en HRB → GO.
3. Formas: **mitad archivo completo / mitad documento interior** → ambas
   vertientes son necesarias.
4. Desde JUNIO el corpus queda como la primera pasada de paso-1 (sin fusión
   post-conteo) — contexto que motivó la vertiente 1.
