# Incremento 1B — Frontend honesto (procedencia + controles)

**Fecha:** 2026-06-15
**Rama:** `po_overhaul`
**Depende de:** Incremento 1A (`tag incremento-1a`) — `per_file_method`, `count_type`, merge incremental.
**Origen de decisiones:** `docs/backlog/2026-06-09-ideas-triage.md` (Decisiones 1, 3, 4) + mockup aprobado `docs/backlog/mockups/override-revert.png` (Variante C).

---

## 1. Contexto y objetivo

Incremento 1A puso la **fundación backend** del conteo (merge incremental, `count_type`
por sigla, procedencia `per_file_method` por archivo) sin cambiar el frontend a propósito:
el contrato `cell_done` quedó idéntico para que 1B se ocupara de la **UI honesta**.

Hoy el frontend tiene **dos deshonestidades** y **una fricción**:

1. **El punto verde miente.** `frontend/src/lib/cell-status.js` enciende verde con
   `cell.confidence === "high"`. El scanner marca `high` también cuando contó por **OCR**
   (motor incierto). Resultado: una celda contada por OCR puede leerse como "lista" sin
   verificación humana — exactamente lo que la Decisión 1 prohíbe.
2. **El badge "Confianza alta/baja"** del `DetailPanel` refuerza esa misma señal engañosa.
3. **El override de celda es un callejón sin salida.** Hoy, ajustar el total de la celda en
   "Ajuste manual" tapa el conteo por archivos sin forma visible de volver (la columna
   "Conteo por archivos" en muted no es una acción). El operador no sabe cómo deshacer.

**Objetivo de 1B:** que la señal de "listo" diga la verdad (procedencia, no `confidence`),
que el override celda↔archivos sea **reversible y legible**, y que el campo de ajuste
rechace entradas imposibles (negativos). Todo consumiendo lo que 1A ya dejó listo; **casi
puro frontend** (ver §7 para el único matiz).

---

## 2. Alcance

### Dentro (1B)
- **Pieza 1** — Punto verde honesto por procedencia (Decisión 1). Solo `cell-status.js` + tests.
- **Pieza 2** — Toggle `Por archivos · Manual` reversible (Decisión 3, Variante C) + hint inline
  ámbar. Rehace `OverridePanel` y la cabecera del `DetailPanel`; toca `FileList` para el hint.
- **Pieza 3** — Validación de entrada: bloquear negativos, 0 explícito válido (parte de Decisión 4).
- Quitar el badge "Confianza alta/baja" del `DetailPanel`.

### Fuera (diferido, con justificación)
- **Tope `conteo ≤ páginas`** (resto de Decisión 4) → **Incr 2**, junto con la persistencia de
  `per_file_pages`. Razón: el tope necesita páginas-por-archivo como dato persistido, que
  **RN (Incr 2) obliga de todas formas** (`páginas_del_archivo ÷ N`) y que será fundación del
  manifiesto de reorganización (Grupo J). Hacerlo a medias en 1B sería trabajo desechable.
  Decidido con Daniel 2026-06-15.
- **RN / tratamientos en bloque** (Incr 2).
- **`count_type` aplicado al conteo** (contador por teclado, maquinaria=chequeos → Incr 3).
  1A ya lo expone como dato; 1B **no** lo usa todavía (sin el tope, no hay consumidor en 1B).
- **Nota-con-estado** (Grupo N) — no es de 1B; sigue siendo la nota simple actual.
- Cualquier cambio de backend para el conteo o la procedencia (1A ya los dejó).

---

## 3. Decisiones de origen (verbatim del triage — autoridad)

> Copiadas literales de `docs/backlog/2026-06-09-ideas-triage.md` §"Bitácora de decisiones".
> Si esta capa entra en conflicto con el triage, **el triage manda** (lección
> `feedback_anchors_verbatim_at_every_layer`).

**Decisión 1 — qué enciende el punto verde (A1 + A2):**
> El verde ("listo") se enciende SOLO si: la celda está `confirmed`, **o** tiene override
> manual de celda, **o** *todos* los archivos son **R1 o Manual** (incluida la mezcla
> R1+Manual). Cualquier archivo OCR / Pendiente / Error → ámbar hasta confirmar. Se deja de
> confiar en `confidence === "high"` del scanner; la procedencia por archivo manda.

**Decisión 3 — modelo override celda ↔ archivos (C1 + C2) — Variante C, mockup aprobado:**
> **Toggle segmentado** bajo el número grande, dos modos de **una palabra**: `Archivo` ·
> `Manual`. Al lado, el conteo por archivos en muted (`archivos: 1.187`). Interacción:
> - Modo **Archivo** → el total = suma por archivos; el campo de "Ajuste manual" se
>   desactiva/aclara. Cambiar a este modo **limpia** el `user_override` (backend ya soporta
>   `value=None`).
> - Modo **Manual** → enfoca el campo de ajuste; el total = override de celda (anula archivos).
> **Modal de aviso DESCARTADO** → en su lugar, **hint inline ámbar persistente** cuando editas
> un archivo con override de celda activo.

**Decisión 4 — validación del número (A4) — parte aplicable a 1B:**
> Bloquear negativos siempre; 0 explícito válido. [El tope `conteo ≤ páginas` se difiere a
> Incr 2 — ver §2 Fuera.]

---

## 4. Pieza 1 — Punto verde honesto

### 4.1 La regla
Una celda enciende **verde** (`confidence-high` en el `Dot`) si y solo si:

```
ready(cell) =
     cell.confirmed === true
  OR hasOverride(cell)                       // user_override presente (0 incluido)
  OR allFilesReliable(cell)
```

donde un archivo es **confiable** (= R1 o Manual) y `allFilesReliable` es verdadero cuando
**ningún** archivo es OCR-sin-override / Pendiente / Error:

```
allFilesReliable(cell) =
     cell.confidence === "high"              // (a) garantiza que los filename_glob son 1-página
  AND NOT anyUnreliableOcrFile(cell)         // (b) ningún archivo OCR sin override por-archivo

anyUnreliableOcrFile(cell) =
  exists f in keys(per_file_method) such that
       per_file_method[f] in OCR_METHODS
   AND per_file_overrides[f] is absent       // un override por-archivo lo vuelve Manual (confiable)

OCR_METHODS = { "header_detect", "corner_count", "header_band_anchors", "v4" }
```

### 4.2 Por qué `confidence === "high"` sigue en juego (no se elimina, se subordina)
El scanner ya computa `confidence`:
- `simple_factory` (filename_glob): `HIGH` ⟺ todos los archivos son **1 página**
  (`no_multipage`) o la sigla es de página fija (`page_count_pure`). Es decir, `HIGH` **ya
  significa "todos R1"** para el camino sin OCR (`simple_factory.py:97`).
- `pagination_scanner` (V4) y el de anclas: `HIGH` cuando no hubo errores ni archivos de baja
  confianza.

Decisión 1 NO dice "ignora `confidence`": dice "deja de **confiar** en `confidence === high`
[como único criterio de listo]". El defecto concreto es que mete al **OCR** en `high`. Por eso
la regla mantiene la cláusula (a) `confidence === "high"` —que aporta gratis el "todos los
`filename_glob` son 1-página"— y le **suma** la cláusula (b) que excluye los archivos OCR sin
override. Sin la cláusula (a) tendríamos que persistir páginas-por-archivo para distinguir un
`filename_glob` de 1 página de uno multipágina; eso es justo lo que se difiere a Incr 2.

**Único cambio de comportamiento respecto de hoy:** una celda contada por OCR con
`confidence === high` **deja de** encender verde automáticamente (ahora exige `confirmed` u
override). Toda otra celda mantiene su color actual.

### 4.3 Casos cubiertos (tabla de verdad para los tests)

| Celda | `confidence` | `per_file_method` | overrides | `confirmed` | Verde |
|-------|--------------|-------------------|-----------|-------------|:-----:|
| Todos R1 (1-pág) | high | `filename_glob`×N | — | false | ✅ |
| Sigla página fija | high | `page_count_pure`×N | — | false | ✅ |
| Multipágina sin OCR | low | `filename_glob`×N | — | false | ⛔ ámbar |
| OCR limpio | high | `v4` / `header_band_anchors` | — | false | ⛔ ámbar (cambio) |
| OCR + confirmado | high | `v4` | — | **true** | ✅ |
| OCR + override de celda | high | `v4` | `user_override=N` | false | ✅ |
| Mezcla R1 + 1 OCR | high | `filename_glob`,`v4` | — | false | ⛔ ámbar |
| Mezcla R1 + OCR-overrideado por archivo | high | `filename_glob`,`v4` | `per_file_overrides[archivoOCR]` | false | ✅ |
| Sin escanear (sin `per_file_method`) | — | `{}` | — | false | neutral (gris, vía `dotVariantFor`) |
| Con error | cualquiera | — | — | — | rojo (precede, ya existe) |

> Nota sobre "Mezcla R1 + Manual" de la Decisión 1: un archivo Manual = tiene
> `per_file_overrides[f]`. Como (b) solo bloquea archivos **OCR sin override**, un archivo con
> override por-archivo nunca bloquea, y los R1 tampoco → la mezcla R1+Manual enciende verde, tal
> como pide la decisión.

### 4.4 Dónde vive
- `frontend/src/lib/cell-status.js`: reescribir `isCellReady`. `hasOverride` y `dotVariantFor`
  **no cambian de firma** (siguen recibiendo `cell`); `dotVariantFor` mantiene la precedencia
  scanning > error > neutral(sin cell) > ready/pendiente.
- Añadir constante `OCR_METHODS` y los helpers `allFilesReliable` / `anyUnreliableOcrFile`
  (exportados para test directo).
- Sin cambios en `CategoryRow.jsx` (ya llama `dotVariantFor(cell, { isScanning })`).

---

## 5. Pieza 2 — Toggle `Por archivos · Manual`

### 5.1 Modelo de estado (derivado, no nuevo estado persistido)
El "modo" no es un campo nuevo del backend; se **deriva** de `cell.user_override`:
- `hasOverride(cell)` → modo **Manual**.
- si no → modo **Por archivos**.

Cambiar de modo = una mutación que ya existe:
- **→ Manual:** enfocar el campo de ajuste; al teclear un número, `saveOverride(..., value)`.
- **→ Por archivos:** `saveOverride(..., value=null)` (el store + backend ya soportan `null`
  para limpiar el override — `OverridePanel.jsx:29`, store `saveOverride` línea 169).

### 5.2 Layout (mockup Variante C, `override-revert.png`)
En la cabecera del `DetailPanel`, bajo el número grande (`<p className="text-5xl …">`):

```
art · ART realizadas
1.000
documentos
┌─────────────┬──────────┐
│ Por archivos│  Manual  │   archivos: 1.187
└─────────────┴──────────┘
AJUSTE MANUAL
[ 1000 ]
[ Nota (opcional)            ]
```

- **Toggle segmentado** de dos opciones (`Por archivos` / `Manual`). Primitiva nueva ligera
  `SegmentedToggle` en `frontend/src/ui/` (sigue el patrón de las 8 primitivas; tokens `po-*`,
  Radix no es necesario — es un par de botones con `role="radiogroup"`/`aria-pressed`).
- A la derecha del toggle, `archivos: {N}` en `text-po-text-muted` (N = `computeCellCount` sobre
  la celda **ignorando** `user_override`; ver §5.4).
- El número grande (`computeCellCount(cell)`) ya refleja el modo: con override muestra el manual,
  sin override muestra la suma por archivos. **Sin cambio** en `cellCount.js`.

### 5.3 Comportamiento del campo "Ajuste manual" (`OverridePanel`)
- **Modo Por archivos:** input deshabilitado/atenuado (`disabled`, opacidad reducida). El
  placeholder sigue mostrando el conteo automático. La nota **permanece editable** (una nota no
  requiere override — es metadato de la celda).
- **Modo Manual:** input habilitado y enfocado al entrar al modo. Igual que hoy (debounce 400 ms,
  `SaveIndicator`).
- El toggle y el input comparten el mismo `saveOverride`; sin doble fuente de verdad.

### 5.4 `archivos: N` — el conteo por archivos sin el override
Necesitamos "cuánto daría la suma por archivos" aunque haya override activo. Hoy
`computeCellCount` corta temprano si `user_override != null`. Opciones:
- **Elegida:** un helper `computeFilesCount(cell)` en `cellCount.js` que corre la **misma lógica
  de suma por archivos** (`per_file` + `per_file_overrides`) **sin** la rama de `user_override`.
  `computeCellCount` se refactoriza para delegar en él (cuando no hay override, devuelve
  `computeFilesCount`). Mantiene la paridad cross-language ya existente con
  `api/state.py:compute_cell_count` (la rama de archivos es idéntica; solo se extrae).
- Garantía de paridad: el fixture `tests/fixtures/cell_count_cases.json` sigue cubriendo
  `computeCellCount`; se añade cobertura JS para `computeFilesCount`.

### 5.5 Hint inline ámbar (reemplaza el modal)
En `FileList.jsx`, cuando la celda tiene override activo (`hasOverride(cell)`), mostrar **sobre
la lista** (o como primera fila no-archivo) un aviso ámbar persistente:

> ⚠ La celda usa un total manual ({user_override}) que anula los archivos.
> **usar conteo por archivos**

- "usar conteo por archivos" es un botón-enlace → `saveOverride(..., value=null)` (= cambiar a
  modo Por archivos). Mismo efecto que el toggle; dos puertas a la misma acción.
- `FileList` hoy recibe `hospital`/`sigla` y trae los archivos por fetch. Para conocer el override
  necesita la celda: leerla del store (`useSessionStore`) por `hospital|sigla` (no se añade prop
  desde el padre para no acoplar; el store ya es la fuente de la celda).
- Estilo: usar los tokens ámbar existentes (los mismos del `Badge` tono `amber` / `po-suspect`),
  sin introducir color crudo.

### 5.6 Componentes tocados
| Archivo | Cambio |
|---------|--------|
| `frontend/src/ui/SegmentedToggle.jsx` | **Nuevo** — primitiva de toggle de 2 segmentos, accesible. |
| `frontend/src/components/DetailPanel.jsx` | Insertar el toggle + `archivos: N` bajo el número; quitar el badge de confianza (§6). |
| `frontend/src/components/OverridePanel.jsx` | `disabled` del input según modo; foco al entrar a Manual. |
| `frontend/src/components/FileList.jsx` | Hint inline ámbar cuando `hasOverride(cell)`; leer cell del store. |
| `frontend/src/lib/cellCount.js` | Extraer `computeFilesCount`; `computeCellCount` delega. |

---

## 6. Quitar el badge "Confianza alta/baja"

En `DetailPanel.jsx` (líneas 232–234) eliminar el `<Badge variant={confidenceVariant(cell)}>`
y la función `confidenceVariant`. Razón (decidida con Daniel 2026-06-15): con el punto verde por
procedencia, el badge mostraría "alta" en celdas ámbar por OCR → señal contradictoria. El estado
real ya lo comunican el punto verde + los chips por archivo (`OriginChip`). El badge "Manual"
(`state-override`) y "Compilación" (`state-suspect`) **se mantienen**.

`CONFIDENCE_LABEL` queda sin uso en `DetailPanel`; verificar si otros consumidores lo usan antes
de borrarlo del módulo (`grep`); si no, retirarlo (regla de dead-code del proyecto).

---

## 7. Pieza 3 — Validación de entrada (negativos + 0)

En el camino de guardado del override (`OverridePanel` → `saveOverride`):
- **Negativos:** rechazar `value < 0`. El `<input type="number">` con `min={0}` no basta
  (se puede teclear/pegar `-5`); validar en `onChangeValue` antes de `flushSave`: si
  `parseInt < 0`, no guardar y dar feedback visual (borde error + no enviar).
- **0 explícito:** válido — ya lo es (`hasOverride` trata 0 como override). No regresar.
- **Vacío:** `null` (limpia override) — comportamiento actual, se conserva.
- El **tope `≤ páginas` NO se implementa aquí** (§2 Fuera). El campo no conoce el total de
  páginas de la celda en 1B.

Sin cambios de backend: `saveOverride` ya acepta `int | null`; la validación es de UI (evita
mandar un negativo). El backend mantiene su propia robustez existente.

---

## 8. Datos disponibles (confirma "sin backend nuevo")

La celda que el frontend ya recibe (vía `cell_done` / estado persistido) carga: `confidence`,
`confirmed`, `per_file`, `per_file_overrides`, `per_file_method` (1A), `user_override`,
`override_note`, `ocr_count`, `filename_count`, `method`, `flags`, `errors`, `near_matches`,
`worker_*`. Las tres piezas de 1B se construyen con estos campos. **No** se necesita
`per_file_pages` (eso es Incr 2) porque el tope ≤páginas queda fuera.

---

## 9. Estrategia de tests

- **`cell-status.test.js`** (vitest): reescribir/ampliar para la tabla de verdad de §4.3. Casos
  clave: OCR-limpio ahora ámbar; OCR+confirmado verde; OCR+override de celda verde; mezcla
  R1+OCR ámbar; mezcla R1+OCR-overrideado-por-archivo verde; multipágina ámbar; sin-datos
  neutral. Tests directos de `allFilesReliable` / `anyUnreliableOcrFile`.
- **`cellCount`**: test JS para `computeFilesCount` (ignora `user_override`) + re-verificar que
  `computeCellCount` sigue pasando el fixture `cell_count_cases.json` (paridad con Python).
- **Componentes** (si hay infraestructura de render-test; si no, smoke conducido): toggle cambia
  de modo y limpia/escribe override; input deshabilitado en modo Por archivos; hint inline
  aparece solo con override y "usar conteo por archivos" lo limpia; negativo rechazado.
- **Smoke conducido por chrome-devtools** (no checklist a Daniel) sobre una celda **sandbox**
  (no datos reales de un mes en vivo): verificar el punto verde de una celda OCR vira a ámbar,
  el toggle ida/vuelta, el hint, y el rechazo de negativo. Capturas a `data/_smoke/` (gitignored).
- `ruff check .` no aplica (frontend); `npm run lint` / `vitest` / `npm run build` verdes antes
  de commit.

---

## 10. Riesgos y mitigaciones

- **Regresión del punto verde en celdas reales de MAYO.** Mitigación: la regla solo *quita*
  verde a celdas OCR (las vuelve ámbar = más conservador, nunca afirma de más); ninguna celda
  R1/manual pierde su verde. La tabla §4.3 fija el contrato; el smoke se hace en sandbox.
- **`FileList` leyendo la celda del store** podría desincronizarse del fetch de archivos.
  Mitigación: el override vive en la celda del store (no en el fetch de file-list), así que el
  hint reacciona correcto al toggle; el fetch de archivos solo provee filas, no el override.
- **Primitiva `SegmentedToggle` nueva.** Riesgo bajo; se ciñe al patrón de `ui/` + tokens `po-*`
  + a11y (`role`, `aria`), revisada en el plan.

---

## 11. Criterios de aceptación

1. Una celda contada por OCR (`confidence high`, sin confirmar, sin override) muestra punto
   **ámbar**; al confirmarla o ponerle override de celda → **verde**.
2. Una celda todo-R1 (1-página) o de página fija sigue **verde**; una multipágina sin OCR sigue
   **ámbar**; una sin escanear sigue **neutral**; una con error sigue **roja**.
3. El `DetailPanel` ya **no** muestra el badge "Confianza alta/baja".
4. Bajo el número grande hay un toggle `Por archivos · Manual` con `archivos: N` al lado; en
   modo Por archivos el campo de ajuste está deshabilitado y el total = suma por archivos; en
   modo Manual el campo se enfoca y el total = override; el cambio ida/vuelta limpia/escribe el
   override correctamente.
5. Editar un archivo con override de celda activo muestra el hint ámbar; "usar conteo por
   archivos" limpia el override y vuelve a modo Por archivos.
6. El campo de ajuste rechaza negativos; 0 es válido; vacío limpia el override.
7. `vitest` y `npm run build` verdes; sin tokens de color crudos nuevos; smoke conducido OK.

---

## 12. Fuera de alcance — recordatorio explícito

- Tope `conteo ≤ páginas` → **Incr 2** con `per_file_pages` persistido (lo obliga RN; fundación
  de Grupo J / manifiesto).
- RN / "Aplicar R1" / tratamientos en bloque → Incr 2.
- Contador por teclado, maquinaria=chequeos, `count_type` aplicado al conteo, bug F1 → Incr 3.
- Nota-con-estado (Grupo N), filtro por chip, color docs≠páginas, perf del visor → Track B UX.
- Reorganización / manifiesto (Grupo J), multiplayer (Grupo L), autoría de flavors (Incr 4).
