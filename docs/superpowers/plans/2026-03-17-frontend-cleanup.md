# Plan: Frontend Cleanup + Modularización UI/UX

**Fecha:** 2026-03-17
**Rama activa:** `feature/inference-engine`
**Archivo principal:** `frontend/src/App.jsx` (999 líneas)
**Contexto:** Auditoría UI/UX realizada por Sonnet + Opus. El estilo visual y la funcionalidad están bien encaminados. Este plan recoge los bugs reales y mejoras pendientes.

---

## Tier 1 — Fixes rápidos (1-2 líneas, impacto inmediato)

| # | Fix | Archivo | Línea | Cambio |
|---|-----|---------|-------|--------|
| 1.1 | Auto-scroll roto en modo AI | App.jsx | 132 | Deps: `[logs]` → `[logs, aiLogs, aiLogMode]` |
| 1.2 | `alert()` nativo → `confirmModal` | App.jsx | 349 | Reemplazar `alert(...)` por `setConfirmModal({...})` |
| 1.3 | Cap de `aiLogs` (memory leak) | App.jsx | 92 | `[...prev, payload]` → `[...prev.slice(-199), payload]` |
| 1.4 | Borrar `App.css` (dead code) | App.css | — | Eliminar archivo (no se importa en ningún lado) |
| 1.5 | Limpiar `index.css` | index.css | — | Conservar solo reglas `::-webkit-scrollbar` (líneas 38-66) |

---

## Tier 2 — Fixes medios (15-30 min)

| # | Fix | Archivo | Línea | Cambio |
|---|-----|---------|-------|--------|
| 2.1 | Iconos terminal casi invisibles | App.jsx | 758-766 | `text-[#842029]` → `text-gray-600 hover:text-gray-300` |
| 2.2 | Progress bar pulsa durante pausa | App.jsx | 677 | Condición: `status === 'running' && !globalProg.paused` |
| 2.3 | Sin detección de WS caído | App.jsx | 76-129 | Añadir `onclose`/`onerror` con indicador visual |
| 2.4 | `fileProg` no se limpia en start | App.jsx | 284 | Añadir `setFileProg({ done: 0, total: 0, filename: '' })` |
| 2.5 | Filtro por nombre, no por path | App.jsx | 606, 725 | `selectedPdfFilter` usa `p.path` en vez de `p.name` |
| 2.6 | Errores de API silenciosos | App.jsx | varios | Toast/flash en header cuando un fetch falla (todos los `catch`) |

---

## Tier 3 — Modularización del monolito

App.jsx tiene 999 líneas con 5 zonas claramente separables. Los cortes son limpios — ningún componente comparte lógica interna con otro.

### Estructura propuesta

```
frontend/src/
├── App.jsx                    (~120 líneas) ← shell + layout + state orchestration
├── lib/
│   └── constants.js           (~15 líneas)  ← API_BASE, SPINNER, formatTime
├── hooks/
│   ├── useWebSocket.js        (~60 líneas)  ← conexión WS + dispatch por type
│   └── useApi.js              (~200 líneas) ← todos los handlers de fetch
└── components/
    ├── HeaderBar.jsx           (~50 líneas)  ← barra superior con botones + controls pill
    ├── Sidebar.jsx             (~80 líneas)  ← lista de PDFs + progress fills + confidence dots
    ├── ProgressBar.jsx         (~40 líneas)  ← barra de progreso global + file + ETA
    ├── IssueInbox.jsx          (~70 líneas)  ← grid de issues + métricas individuales
    ├── Terminal.jsx            (~100 líneas) ← log console + AI mode + copy/export + spinner
    ├── CorrectionPanel.jsx     (~100 líneas) ← panel derecho: preview zoom + inputs + validar
    ├── HistoryModal.jsx        (~50 líneas)  ← overlay de sesiones guardadas
    └── ConfirmModal.jsx        (~55 líneas)  ← modal genérico confirm/alert/multi-button
```

### Cómo se conectan

```
App.jsx
 ├── useState (pdfs, issues, metrics, globalProg, status, ...)
 ├── useWebSocket(setters)         → devuelve ws ref
 ├── useApi(ws, setters)           → devuelve { handleStart, handlePause, ... }
 │
 └── return JSX:
      ├── <HeaderBar onAddFolder, onNewSession, onSave, onHistory, controls={...} />
      ├── <Sidebar pdfs, fileProg, metrics, selectedPdfFilter, onSelect, onOpen />
      ├── <ProgressBar globalProg, fileProg, status />
      ├── <IssueInbox issues, selectedIssue, selectedPdfFilter, onSelect />
      ├── <Terminal logs, aiLogs, scanLine, spinFrame, aiLogMode, ... />
      ├── {selectedIssue && <CorrectionPanel issue, onCorrect, onExclude, onNavigate, onClose />}
      ├── {showHistory && <HistoryModal sessions, onDelete, onClose />}
      └── <ConfirmModal config={confirmModal} onClose />
```

**Principio de corte:** cada componente recibe props primitivas (strings, numbers, arrays, callbacks). Ninguno necesita Context ni state management externo. Los setters viven en App; los componentes son presentacionales con callbacks hacia arriba.

---

## Tier 4 — UX polish (baja urgencia)

| # | Mejora | Detalle |
|---|--------|---------|
| 4.1 | Label de filtro activo | "Filtrando: informe.pdf" + botón ✕ sobre la bandeja |
| 4.2 | Hint de keyboard nav | Tooltip discreto en el panel: "← → para navegar" |
| 4.3 | Bandeja vacía contextual | Si hay filtro: "Sin problemas para este archivo" vs el mensaje genérico |
| 4.4 | Double-click affordance | `cursor-pointer` diferenciado + tooltip en sidebar |

---

## Orden de ejecución recomendado

1. **Tier 1** — arreglos de una línea, riesgo cero
2. **Tier 2** — bugs con impacto visible en UX
3. **Tier 3** — modularización (más segura después de que el código esté limpio)
4. **Tier 4** — polish final

## Notas adicionales

- `App.css` no tiene ningún import → eliminar sin riesgo
- `index.css` sí está importado en `main.jsx` → solo limpiar, no eliminar
- `localhost:8000` aparece hardcoded 19 veces → `lib/constants.js` lo centraliza en Tier 3
- El estilo visual (Catppuccin, gradiente radial, terminal) está logrado y no necesita cambios
- Tier 3 NO requiere cambios de comportamiento — es refactor puro de estructura de archivos
