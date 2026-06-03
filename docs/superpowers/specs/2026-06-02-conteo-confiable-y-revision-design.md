# Spec — Conteo confiable, organización por carpeta y revisión por archivo

- **Fecha:** 2026-06-02
- **Base:** `po_overhaul` **consolidado** (= po_overhaul + PR #1 `feature/ocr-per-sigla` + `feature/worker-viewer-ux`, fusionados). Las anclas de código de este spec apuntan al árbol de `feature/ocr-per-sigla`, que es el grueso de esa base. **Pin de líneas exactas: al implementar, tras la consolidación.**
- **Predecesores:** OCR per-sigla (PR #1), worker-viewer-ux, Feature 1.
- **Solicitado por:** Daniel, 2026-06-02.

## Contexto y motivación

Hoy el conteo automático "R1" (pase 1, `filename_glob`) cuenta **archivos**, no
documentos, y los muestra como conteo de documentos con aire de certeza (punto
verde). Eso es deshonesto cuando un PDF contiene varios documentos: ej. HRB/exc
figura "1 R1" pero el PDF tiene 2 documentos adentro. El operador no tiene señal
de cuáles celdas son confiables y cuáles hay que revisar.

Esta tanda hace tres cosas:
- **Tema A** — un modelo de "listo" honesto + conteo por páginas para las siglas
  de estructura fija + la lista de categorías en orden de carpeta.
- **Tema B** — alinear el `FileList` (hoy los nombres largos desalinean tags).
- **Tema C** — el visor de archivo individual muestra/edita datos **del archivo**,
  no de la celda, y con números legibles (blanco).

## Decisiones transversales (cerradas en brainstorming)

- **D1 — Base consolidada.** Construir sobre `po_overhaul` consolidado. Secuencia:
  (1) smoke manual de PR #1 (Daniel), (2) merge `ocr-per-sigla` → po_overhaul,
  (3) merge `worker-viewer-ux` → po_overhaul, (4) implementar esta tanda. El spec
  y el plan se escriben antes; la consolidación ocurre antes de tocar código.
- **D2 — Conjunto de siglas de páginas fijas (1 página = 1 documento):**
  `FIXED_PAGE_SIGLAS = {bodega, ext, caliente, herramientas_elec, exc}`, todas con
  divisor 1. **Sólidas** (documentadas + confirmadas en calibración): `bodega`,
  `ext`. **Inferidas** (Fase B, menos evidencia — llevan matiz "verificar"):
  `caliente`, `herramientas_elec`, `exc`. Fuente: `docs/research/2026-05-11-abril-corpus-audit.md`,
  spec OCR per-sigla §9/§11/§13/§15/§16, calibración Fase A/B.
- **D3 — `odi`/`art` quedan FUERA** del conjunto de páginas fijas: odi es ~2.3
  págs/doc real (contaría de más); art es 4 nominal pero las multi-trabajador se
  van a 28+ págs. Se cuentan por OCR/manual como hoy.
- **D4 — "Verde/listo" se deriva del campo `confidence` existente** (no se inventa
  un campo nuevo de estado salvo `confirmed`). El frontend ya pinta verde con
  `confidence === "high"`.

---

## Tema A — Modelo de "listo" + conteo por páginas + organización

### A1. Regla de confianza en el pase 1 (backend)

**Ancla:** `core/scanners/simple_factory.py`, `SimpleFilenameScanner.count`
(líneas 31-56). Hoy: `confidence = LOW` si `compilation_suspect`, si no `HIGH`
(líneas 36-43). El conteo es `glob_result.count` (archivos) y `per_file = {fn: 1}`
(línea 55).

**Cambio.** `count` lee los page-counts de los archivos matched llamando
`_page_count` (de `page_count_heuristic.py`) **directamente sobre
`glob_result.matched_filenames`** (no reutiliza la lista folder-wide interna de
`flag_compilation_suspect`; ese costo es aparte, aunque del mismo orden — abrir
cada PDF una vez) y aplica:

1. **Sigla de páginas fijas** (`sigla in FIXED_PAGE_SIGLAS`):
   - `count = Σ page_count` de los archivos matched.
   - `per_file = {fn: page_count}` (cada archivo aporta sus páginas).
   - `method = "page_count_pure"` (token ya existente; label "Conteo de páginas").
   - `confidence = HIGH` (listo). Si la sigla es **inferida** (D2), añade flag
     `"fixed_pages_inferred"` para el matiz visual.
2. **Resto de siglas:**
   - `count = glob_result.count` (archivos), `per_file = {fn: 1}` (como hoy).
   - `confidence = HIGH` **solo si todos** los archivos matched son de 1 página
     (cada archivo = 1 doc, trivial, alineado con A7). Si no → `confidence = LOW`
     (ámbar: R1 sin verificar). **Esto reemplaza** la regla actual "HIGH salvo
     compilation_suspect".
3. **`folder_missing`** → `HIGH`, count 0 (como hoy).

El flag `compilation_suspect` se mantiene como **señal informativa** (chip), pero
ya no decide la confianza — un PDF multipágina de sigla variable es LOW por la
regla 2 aunque la heurística no lo marque (cierra el caso exc/2-docs).

**Constante.** `FIXED_PAGE_SIGLAS: dict[str, int]` en `core/utils.py` (convención
de constantes), mapeando sigla → páginas/doc (todas 1 por ahora), más un set
`FIXED_PAGE_SIGLAS_INFERRED` para el matiz. Documentar fuente y estado
(sólida/inferida) en comentario. Bump `SCANNER_PATTERNS_VERSION`.

**Origen del chip (FileList).** Para las celdas de páginas fijas el método pasa a
`page_count_pure`, que en `_origin_for` (`api/routes/sessions.py` ~408-425) hoy
mapea a origen **"OCR"**. Como no hubo OCR real, se añade un origen nuevo
**"Estructura"** (o `"págs"`): `_origin_for` devuelve `"Estructura"` cuando
`cell_method == "page_count_pure"`. Nuevo variant en `OriginChip.jsx`.

### A2. Estado `confirmed` (marcar listo a mano) — backend

- Nuevo campo por celda `confirmed: bool` (default `false`), persistido junto al
  resto del estado de celda (`api/state.py`). Una celda `confirmed` cuenta como
  **lista (verde)** aunque su `confidence` sea LOW, sin cambiar el número.
- Endpoint `PATCH /api/sessions/{id}/cells/{h}/{s}/confirm` con body `{confirmed:
  bool}` (toggle). Espeja el patrón de `worker-count` / override.
- Un override de celda o de archivo ya implica revisión manual → la celda se
  considera lista igual que hoy (no se toca esa cascada).
- **Persistencia entre escaneos:** `confirmed` se **preserva** cuando un escaneo
  posterior reescribe la celda (`apply_filename_result` / OCR usan `setdefault` o
  equivalente para no pisarlo). Solo el operador lo limpia con el toggle; un
  re-escaneo no des-confirma.

### A3. Lista de categorías en orden de carpeta (frontend)

**Ancla:** `frontend/src/views/HospitalDetail.jsx:23-101` (hoy separa `normalized`
vs `compilations` por `compilation_suspect` y monta dos `CategoryGroup`).

**Cambio.** Una sola lista con las **18 siglas en orden `SIGLAS`** (ya es 1-18 en
`core/domain.py`). Se elimina el split Normalizadas/Compilaciones y el segundo
`CategoryGroup`. El tooltip de cada fila puede mostrar el nombre de carpeta
(`CATEGORY_FOLDERS[sigla]`, ej. "9.-Inspeccion Bodega"). En `mode==="manual"` se
mantienen las 18 filas como hoy.

**Punto verde/ámbar** (`CategoryRow.jsx:11-19`, `dotVariantFor`; **y el equivalente
en `HospitalCard.jsx:11-16`** — actualizar ambos consistentemente): se redefine a
**listo vs pendiente**:
- verde (`confidence-high`) si la celda está lista: `confidence === "high"` **o**
  `confirmed` **o** override.
- ámbar (`confidence-low`) si pendiente.
- se mantienen `state-scanning` y `state-error`.
- **Decisión (revisión):** hoy una celda con override pinta `state-override` (color
  propio). Al colapsar override en "listo/verde" se pierde ese color en el punto —
  **es intencional**: el chip "Manual" de la fila (`CategoryRow.jsx:88`) ya marca
  las celdas con override, así que no se pierde información. Si prefieres conservar
  un punto distinto para override, es un ajuste menor (mantener `state-override`
  como una tercera variante "listo").

El chip "Compilación" (`CategoryRow.jsx:89-92`) deja de agrupar pero sigue
mostrándose inline si `compilation_suspect`, como dato extra.

### A4. Acciones masivas (frontend)

**Ancla:** `frontend/src/components/ScanControls.jsx` (hoy escanea las siglas
seleccionadas por checkbox) y el botón `showScanAll` del `CategoryGroup` de
Compilaciones (desaparece con A3).

**Cambio.** Encima de la lista, dos botones contiguos:
- **"Escanear pendientes"** → `scanOcr` sobre **todas las celdas ámbar** (no
  listas) del hospital. Deriva la lista de pendientes del estado (las que no
  cumplen A3-verde).
- **"Marcar seleccionadas como listas"** → `PATCH …/confirm {confirmed:true}` para
  cada sigla tildada con checkbox; actualización optimista del dot a verde.
- Se mantiene el escaneo de seleccionadas (header `ScanControls`) para escaneo
  dirigido; puede convivir o fusionarse con "Escanear pendientes" (decisión de
  layout en el plan, sin cambio de comportamiento).

### A5. Cascada de conteo y Excel — sin cambio de contrato

`compute_cell_count` / `cellCount.js` y el writer mantienen su cascada. **Ojo
(revisión):** la cascada real tiene un nivel intermedio `per_file_overrides ∪
per_file` **antes** de `filename_count`. Para páginas fijas el total sale de ese
nivel — `per_file = {fn: page_count}`, que A1 ya pobla en el `ScanResult` y
`apply_filename_result` persiste — **no** de `filename_count`. El número es el
mismo, pero el implementador DEBE poblar `per_file` por páginas (lo hace A1); no
basta con setear `filename_count`/`count`. `confirmed` no entra en la cascada de
número, solo en el estado visual de "listo".

---

## Tema B — FileList alineado

**Ancla:** `frontend/src/components/FileList.jsx:82-117` (consolidado: incluye el
chip `trivial` para `page_count === 1`, líneas ~114-116 en la versión
ocr-per-sigla). **Causa raíz:** el `<span>` del nombre usa `truncate flex-1` sin
`min-w-0`; en flexbox eso impide que se encoja, así que un nombre largo se expande
y empuja/recorta las columnas de la derecha.

**Cambio.** La fila pasa a grilla de columnas fijas:
```
[icono] [nombre............] [Npp] [⧉ comp?] [conteo] [chip]
  auto   minmax(0,1fr)+scroll-x  auto  auto      auto     auto
```
- Nombre: `min-w-0 overflow-x-auto whitespace-nowrap` → con nombre largo aparece
  **scroll horizontal solo en esa celda** para deslizarse y leerlo; el resto de
  columnas no se mueven.
- `Npp` y el ícono de compilación (`f.suspect`) salen de adentro del botón del
  nombre a **columnas fijas propias**, alineadas fila a fila (como imagen 4).
- Clic en icono/nombre abre el lightbox (`openLightbox`); conteo editable
  (`InlineEditCount`) y `OriginChip` mantienen su `stopPropagation`.
- `Npp` y el ícono de compilación, al salir del botón del nombre a columnas
  propias, **no** deben abrir el lightbox → quedan como elementos no-clickeables
  (o el clic de la fila se maneja a nivel `li`, con `stopPropagation` en los
  controles editables). Decidir el patrón exacto en el plan.
- Sin cambios de datos ni de API. Layout puro (grid + min-w-0 + overflow-x).

---

## Tema C — Visor de archivo individual por-archivo

**Ancla:** `frontend/src/components/PDFLightbox.jsx` — `CountSummary` (27-54) y el
panel lateral (146-150) que hoy reciben `cell` (datos de celda). Modo
`count_workers` (134-140) **no se toca**.

**Cambio.** El panel lateral del modo inspección pasa a **por-archivo**, usando
`files[lightbox.fileIndex]` (ya cargado en `PDFLightbox`, estado `files`):
- Número grande = **conteo del archivo** (`file.effective_count`), label
  "documentos en este archivo". Para páginas fijas = sus páginas.
- Chip de origen del archivo (`file.origin`: R1/OCR/manual/trivial/Estructura) +
  sus páginas (`file.page_count`).
- **Ajuste manual del archivo**: edita el override **del archivo** vía
  `savePerFileOverride(session_id, hospital, sigla, file.name, n)` (ya existe,
  usado por `FileList.jsx:110`), no el override de celda. Reemplaza el
  `OverridePanel` (que opera sobre celda) por un editor per-file.
- **Contraste:** todos los números con `text-po-text` explícito (hoy heredan un
  color oscuro y se ven negros). Aplica al número grande, valores y al input.
- Se quita del panel el resumen de celda (Por nombre / Por OCR / Método /
  confianza) — eso vive en el `DetailPanel` afuera. El encabezado mantiene el
  contexto (hospital · sigla · nombre · páginas).
- Tras editar, refrescar el row del `FileList` (mismo patrón optimista de FASE 4,
  `savePerFileOverride`); el `files` del lightbox y del FileList se mantienen
  coherentes (ambos derivan de `getCellFiles`).

---

## Casos borde

- **Celda de páginas fijas con un PDF de 1 página** → count 1 (Σ páginas = 1);
  consistente con R1 y con A7.
- **Sigla de páginas fijas con archivo ilegible** (`_page_count` = 0) → ese
  archivo aporta 0; no rompe el conteo (se suma 0). Considerar flag si Σ = 0.
- **`ext` con formularios fuera de alcance** (UEO-01, PSR-RG) → la regla cuenta
  páginas igual; el operador corrige con override (documentado en spec OCR §11).
- **Celda ya escaneada con OCR** → su `confidence`/método mandan; la regla de
  pase 1 no la pisa (el OCR es pase 2, posterior).
- **`confirmed` + luego OCR/override** → sigue lista; `confirmed` no se borra solo
  (el operador lo controla).
- **Nombre larguísimo en FileList** → scroll horizontal en la celda del nombre; el
  resto alineado.
- **Lightbox de un archivo que no abre** → el panel per-file muestra su conteo y
  permite override igual (no depende de renderizar el PDF).

## Pruebas

- **pytest** — `SimpleFilenameScanner.count`: (a) sigla de páginas fijas →
  count = Σ páginas, per_file por páginas, method page_count_pure, HIGH; (b) sigla
  normal todos-1-página → HIGH; (c) sigla normal con un multipágina → LOW; (d)
  inferida lleva flag `fixed_pages_inferred`; (e) folder_missing → HIGH, 0.
  Fixtures reales (sin mock de DB). Endpoint `confirm` (toggle persiste).
- **vitest** — `dotVariantFor` (listo vs pendiente con confidence/confirmed/
  override); `_origin_for`/OriginChip nuevo variant "Estructura".
- **Smoke en vivo (chrome-devtools)** desde el worktree de la tanda: lista 1-18 sin
  agrupar; exc/bodega muestran conteo por páginas y verde; un charla multipágina
  ámbar; "Escanear pendientes" toma solo ámbar; "Marcar seleccionadas" pone verde;
  FileList alineado con scroll de nombre; lightbox por-archivo con números blancos
  y override de archivo.

## Fuera de alcance (YAGNI)

- Calibrar divisores ≠ 1 (odi=2, art=4, etc.) — explícitamente excluidos (D3).
- Promover las 3 inferidas a "sólidas" (necesita medición de corpus — fase 2).
- Cambiar la cascada de conteo o el formato del Excel.
- Reordenar/persistir nada del histórico o del modo manual más allá de las 18 filas.

## Rama e integración

- **Consolidar primero** (D1): smoke PR #1 + 2 merges a `po_overhaul`, luego rama
  `feature/conteo-confiable` (worktree `.worktrees/conteo-confiable`) sobre la base
  consolidada.
- Commits atómicos por unidad. Orden sugerido: A1 backend (regla + constante) → A2
  confirmed (backend + endpoint) → A1 origen "Estructura" → A3 lista 1-18 + dot →
  A4 acciones masivas → B FileList → C lightbox per-file. Tag al cierre.
- **Cambio de números visible:** las celdas de páginas fijas con compilaciones
  cambian su conteo (ej. bodega 4pp: 1 → 4). Es el comportamiento deseado; avisar
  en el smoke.
