# Spec — Mejoras al visor de conteo de trabajadores

- **Fecha:** 2026-06-02
- **Rama:** `feature/worker-viewer-ux` (desde `po_overhaul`; worktree `.worktrees/worker-viewer-ux`)
- **Predecesor:** Feature 1 — Conteo asistido de trabajadores firmantes (`conteo-trabajadores-mvp`)
- **Solicitado por:** Daniel, 2026-06-02 (smoke manual del visor)

## Contexto

El visor `WorkerCountViewer` permite contar a mano los trabajadores que firman
las listas de asistencia de las celdas `charla` / `chintegral`. Durante el uso
real surgieron cuatro puntos a mejorar. Tres son de usabilidad del visor; uno es
un bug en la derivación del total parcial fuera del visor.

Esta es una slice de UI acotada sobre Feature 1. No toca el backend salvo que el
bug ① lo requiera (no lo requiere: el fix es de paridad con el backend, que ya es
correcto).

## Estado actual (anclas de código, `po_overhaul`)

- **`frontend/src/components/WorkerCountViewer.jsx`**
  - Layout `[panel PDF | WorkerHud]` (líneas 199-232). No hay columna de miniaturas.
  - Render de una sola página con **escala fija** `scale={1.8}` (línea 212), centrada
    en un contenedor `overflow-auto bg-black`.
  - Handler de teclado en líneas 183-196: `PageDown`=`fixAndAdvance`, `PageUp`=`retreat`,
    `Delete`=`deleteMark`, `E`=`editMark`, `M`=toggle mic, dígitos→buffer, `Backspace`.
    **No se muestra en ninguna parte.**
  - El doc pdf.js actual ya está disponible como `doc` (hook `usePdfDocument`),
    `page` (acotada), `pageCount`, `marks`, `currentFile.name`.
- **`frontend/src/components/WorkerHud.jsx`** — panel lateral derecho (`w-72`), métricas,
  total, lista de marcas, chips (mic/save/terminado), botón terminar.
- **`frontend/src/components/DetailPanel.jsx`** — `WorkerCountModule` (líneas 22-53):
  muestra `total` cuando `started` (`en_progreso` o `terminado`), pero lo deriva con
  `computeWorkerCount(cell.worker_marks, Object.keys(cell.per_file || {}))` (línea 25).
- **`frontend/src/lib/worker-count.js`** — `computeWorkerCount(marks, fileNames)`:
  filtra con `if (fileNames && !present.has(filename)) continue;` (línea 15).
- **`api/state.py`** — `compute_worker_count(cell)` (líneas 39-61), fuente de verdad
  (alimenta Excel y `worker_warnings`): filtra con `if per_file and filename not in per_file`.

## Cambios

### ① Bugfix — el total parcial figura 0 fuera del visor

**Síntoma (reportado por Daniel):** contó páginas en `chintegral` y las fijó con
`Av Pág`; cerró el visor a medio conteo; el DETALLE mostraba `0 trabajadores ·
En progreso` incluso tras refrescar la página, pero al reabrir el visor las marcas
seguían ahí.

**Causa raíz:** el visor deriva el total contra la lista real de archivos
(`getCellFiles()[].name`), pero el `DetailPanel` la deriva contra
`Object.keys(cell.per_file)`. En una celda sin escaneo per-file, `per_file` es
`{}` → `Object.keys` da `[]`. En JS **`[]` es truthy**, así que el guard
`if (fileNames && !present.has(...))` se ejecuta y **descarta todas las marcas** → 0.
El backend (`compute_worker_count`) no tiene el bug porque un dict vacío es falsy
en Python (`if per_file and ...` → no filtra), y está documentado: *"Si per_file
está vacío (celda sin escanear), no se filtra."*

**Fix:** en `computeWorkerCount` (y por simetría `fileSubtotal` no aplica, solo
`computeWorkerCount`), no filtrar cuando `fileNames` esté vacío. Espejo exacto del
backend:

```js
const filter = Array.isArray(fileNames) && fileNames.length > 0;
const present = new Set(fileNames || []);
for (const [filename, pageMarks] of Object.entries(marks || {})) {
  if (filter && !present.has(filename)) continue;
  ...
}
```

Vive en el lib compartido, así que corrige el DETALLE **y** mantiene correcto el
visor. Con `per_file` no vacío sigue filtrando las marcas huérfanas (archivo
renombrado/eliminado), igual que el backend.

**Test:** vitest — (a) marcas + `fileNames` vacío/`null` → suma todo; (b) marcas +
`fileNames` con nombres → descarta las que no estén; (c) caso del bug: `per_file`
`{}` ⇒ `Object.keys` `[]` ⇒ suma todo.

### ② Ajuste a ventana + zoom manual por página

- **Inicio / default:** la página se renderiza **completa, ajustada a la ventana**
  (contain). Escala de ajuste = `min(panelW / pageW, panelH / pageH)` con el
  viewport de pdf.js a escala 1. Se recalcula con `ResizeObserver` sobre el panel.
- **Zoom manual:** `zoomFactor` (default `1.0`). **Escala efectiva = escalaAjuste ×
  zoomFactor.** El `zoomFactor` se **resetea a 1.0 cada vez que cambia la página o
  el archivo** (cada página nueva arranca ajustada — decisión de Daniel 2026-06-02).
  El zoom solo afecta la página actual.
- **Controles:**
  - Teclado: `+` acercar, `−` alejar (no chocan con los dígitos 0-9 del conteo;
    se añaden al handler de líneas 183-196).
  - Overlay flotante discreto en una esquina del panel PDF: `[ − ] [ ⤢ Ajustar ] [ + ]`.
    `⤢ Ajustar` resetea `zoomFactor` a 1.0 (vuelve al encuadre completo).
- **Implementación:** un hook/función pura para la escala de ajuste
  (`computeFitScale(viewport, panelRect)`) testeable, más el `zoomFactor` como
  estado local del visor. `PdfPage` ya acepta `scale`; se le pasa la escala efectiva.
  `computeFitScale` devuelve `1.0` si `pageW` o `pageH` es 0 (viewport degenerado de
  una página malformada) para evitar la división por cero.
- **Scroll:** cuando el zoom supera el panel, el contenedor ya es `overflow-auto`.

### ③ Columna de miniaturas (solo el PDF actual)

- Nuevo componente `frontend/src/components/WorkerThumbnails.jsx`: tira **vertical** a
  la izquierda del panel PDF; una miniatura por página del **archivo abierto**
  (`doc` actual, `pageCount` páginas).
- **Render perezoso:** `IntersectionObserver` — cada miniatura se rasteriza a un canvas
  pequeño solo al entrar en viewport; se cachea para no re-renderizar al navegar. Reusa
  el `doc` ya cargado (sin fetch extra). **Invalidación del cache:** keyed por página del
  `doc` actual (p. ej. `WeakMap` sobre el objeto `doc` → mapa de canvas por número de
  página). Al cambiar de archivo, `doc` es otro objeto → el cache se invalida solo, sin
  limpieza manual.
- **Estado visual:** resalta la página actual (anillo); las páginas con marca muestran
  un badge pequeño con el `count`. Clic en una miniatura → `setPageInFile(n)`.
- **Layout:** el visor pasa a `[WorkerThumbnails | panel PDF | WorkerHud]`.
- **Alcance:** solo el archivo actual (evita rasterizar cientos de páginas en celdas
  como ART; la navegación entre archivos sigue con `Av Pág`/`Re Pág`).

### ④ Leyenda de atajos (persistente y compacta, en el HUD)

- Nuevo módulo `frontend/src/lib/worker-shortcuts.js`: **fuente única** de la lista de
  atajos como array `[{ keys, action }]` (para que leyenda y handler no se desincronicen).
- `WorkerHud.jsx`: sección compacta al pie, **siempre visible** (sin toggle), con chips:
  `0-9` ingresar · `Av Pág` fijar y avanzar · `Re Pág` retroceder · `Supr` borrar ·
  `E` editar página · `+ / −` zoom · `M` voz on/off · `Retroceso` corregir dígito.
- Las teclas se muestran con el primitive `Badge` en tono **`neutral`** (no un color de
  estado como iris/jade/amber) y tipografía monoespaciada (`@fontsource/jetbrains-mono`,
  ya dependencia) para que lean como teclas; el texto de la acción en español neutro,
  coherente con "Re Pág / Av Pág" ya usado en el panel de error.

## Casos borde

- **PDF roto:** se mantiene el comportamiento actual (spec Feature 1 §10) — el error se
  muestra en el panel, el HUD y el teclado siguen vivos. Las miniaturas no se renderizan
  para un doc que no abre; la leyenda y el zoom no aplican hasta cargar otro archivo.
- **Cambio de archivo:** `zoomFactor` se resetea; `fileIdx`/`page` ya van acotados.
- **Celda sin PDFs:** mensaje existente ("Esta celda no tiene PDFs que contar").
- **Marcas de archivos ausentes:** el fix ① conserva el filtrado cuando hay lista real
  (no las cuenta), igual que el backend.

## Pruebas

- **vitest:** fix de `computeWorkerCount` (3 casos arriba); forma/contenido de
  `worker-shortcuts` (todas las teclas del handler están en la lista); `computeFitScale`
  (math de contain).
- **Smoke en vivo (chrome-devtools, Chrome debug):** desde el worktree
  `.worktrees/worker-viewer-ux` (backend :8000 + Vite :5173). En `chintegral`: contar
  2-3 páginas, verificar miniaturas + badges + página resaltada, ajuste a ventana,
  zoom `+/−` y reset al cambiar de página, leyenda visible; cerrar el visor → el DETALLE
  muestra el parcial (bug ① resuelto).

## Fuera de alcance (YAGNI)

- Persistir el `zoomFactor` entre páginas (se resetea por diseño).
- Miniaturas de toda la celda (solo el archivo actual).
- Leyenda plegable o con estado persistido.
- Cambios de backend (el bug ① es puramente de paridad en el lib JS).

## Rama e integración

- `feature/worker-viewer-ux` desde `po_overhaul`, worktree `.worktrees/worker-viewer-ux`.
- Independiente del PR #1 (OCR per-sigla). El código de conteo (`worker-count.js`,
  `WorkerCountViewer`, `WorkerHud`) es idéntico en ambas ramas; `DetailPanel.jsx` recibe
  cambios en secciones distintas en cada rama (OCR añade su UI; aquí solo el módulo de
  trabajadores), así que un eventual merge de ambas es de conflicto menor y localizado.
- **Commits atómicos**, un commit por item. Orden sugerido: ① bug → ② ajuste/zoom →
  ③ miniaturas → ④ leyenda. Tag al cierre: `worker-viewer-ux-mvp` (local, awaiting push).
