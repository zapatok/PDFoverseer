# Plan de Implementación — PDFoverseer Frontend

> **Objetivo:** Documento autosuficiente para que otra IA ejecute cada tarea sin contexto previo.
> Cada tarea tiene: archivos, código ANTES/DESPUÉS completo, y verificación.
> **Restricción zero-break:** Cada tarea es independiente y no rompe nada. Se ejecutan en orden pero cada una deja la app funcional.

---

## FASE 1 — Errores reales

### TAREA 1.1: Error Boundary global

**Problema:** Si cualquier componente crashea en render, toda la app queda en pantalla blanca sin forma de recuperarse.

**Archivos a crear/modificar:**
- `[NEW]` `frontend/src/components/ErrorBoundary.jsx`
- `[MODIFY]` [frontend/src/App.jsx](file:///A:/PROJECTS/PDFoverseer/frontend/src/App.jsx)

#### Paso 1: Crear `frontend/src/components/ErrorBoundary.jsx`

```jsx
import { Component } from 'react';

export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('[ErrorBoundary]', error, errorInfo);
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="h-screen w-screen bg-[#1e1e2e] flex items-center justify-center">
          <div className="bg-[#313244] border border-white/10 rounded-2xl p-8 max-w-md w-full text-center shadow-2xl">
            <div className="text-4xl mb-4">💥</div>
            <h2 className="text-xl font-bold text-gray-200 mb-2">Error inesperado</h2>
            <p className="text-gray-400 text-sm mb-4">
              {this.state.error?.message || 'Ocurrió un error en la interfaz.'}
            </p>
            <pre className="bg-black/40 text-red-400 text-xs p-3 rounded-lg mb-6 max-h-32 overflow-auto text-left">
              {this.state.error?.stack?.split('\n').slice(0, 5).join('\n')}
            </pre>
            <button
              onClick={this.handleReload}
              className="px-6 py-2 bg-[#89b4fa] text-[#1e1e2e] font-bold rounded-lg hover:opacity-90 transition-opacity"
            >
              Recargar aplicación
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
```

#### Paso 2: Modificar [frontend/src/App.jsx](file:///A:/PROJECTS/PDFoverseer/frontend/src/App.jsx)

**ANTES** (líneas 1-12):
```jsx
import { useEffect, useRef } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import { useApi } from './hooks/useApi';
import { useStore } from './store/useStore';
import { HeaderBar } from './components/HeaderBar';
import { Sidebar } from './components/Sidebar';
import { ProgressBar } from './components/ProgressBar';
import { IssueInbox } from './components/IssueInbox';
import { Terminal } from './components/Terminal';
import { CorrectionPanel } from './components/CorrectionPanel';
import { HistoryModal } from './components/HistoryModal';
import { ConfirmModal } from './components/ConfirmModal';
```

**DESPUÉS:**
```jsx
import { useEffect, useRef } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import { useApi } from './hooks/useApi';
import { useStore } from './store/useStore';
import { ErrorBoundary } from './components/ErrorBoundary';
import { HeaderBar } from './components/HeaderBar';
import { Sidebar } from './components/Sidebar';
import { ProgressBar } from './components/ProgressBar';
import { IssueInbox } from './components/IssueInbox';
import { Terminal } from './components/Terminal';
import { CorrectionPanel } from './components/CorrectionPanel';
import { HistoryModal } from './components/HistoryModal';
import { ConfirmModal } from './components/ConfirmModal';
```

**ANTES** (líneas 41-76):
```jsx
  return (
    <div className="h-screen w-screen bg-base text-gray-200 flex flex-col font-sans overflow-hidden relative">
      <div className="absolute inset-0 opacity-20 pointer-events-none" style={{ background: 'radial-gradient(circle at 15% 50%, rgba(137, 180, 250, 0.4), transparent 30%), radial-gradient(circle at 85% 30%, rgba(243, 139, 168, 0.3), transparent 30%)' }}></div>

      <HeaderBar api={api} />
      ...
      <HistoryModal api={api} />
      <ConfirmModal />
    </div>
  );
```

**DESPUÉS:** Envolver todo el contenido del `return` con `<ErrorBoundary>`:
```jsx
  return (
    <ErrorBoundary>
      <div className="h-screen w-screen bg-base text-gray-200 flex flex-col font-sans overflow-hidden relative">
        <div className="absolute inset-0 opacity-20 pointer-events-none" style={{ background: 'radial-gradient(circle at 15% 50%, rgba(137, 180, 250, 0.4), transparent 30%), radial-gradient(circle at 85% 30%, rgba(243, 139, 168, 0.3), transparent 30%)' }}></div>

        <HeaderBar api={api} />

        {/* Metrics Summary Bar */}
        <div className="h-10 bg-panel/60 backdrop-blur-md px-6 flex items-center shadow-lg space-x-8 text-sm border-b border-white/5 z-10 relative">
          <div className="font-bold text-white tracking-wide">RESUMEN GLOBAL:</div>
          <div className="flex items-center"><span className="w-2.5 h-2.5 rounded-full bg-accent mr-2 shadow-[0_0_10px_rgba(137,180,250,0.8)]"></span>Documentos: <span className="ml-1 font-mono font-bold">{metrics.docs || 0}</span></div>
          <div className="flex items-center"><span className="w-2.5 h-2.5 rounded-full bg-success mr-2 shadow-[0_0_10px_rgba(166,227,161,0.8)]"></span>Completos: <span className="ml-1 font-mono font-bold">{metrics.complete || 0}</span></div>
          <div className="flex items-center"><span className="w-2.5 h-2.5 rounded-full bg-error mr-2 shadow-[0_0_10px_rgba(243,139,168,0.8)]"></span>Incompletos: <span className="ml-1 font-mono font-bold">{metrics.incomplete || 0}</span></div>
          <div className="flex items-center"><span className="w-2.5 h-2.5 rounded-full bg-warning mr-2 shadow-[0_0_10px_rgba(250,179,135,0.8)]"></span>Pág. Inferidas: <span className="ml-1 font-mono font-bold">{metrics.inferred || 0}</span></div>
        </div>

        <div className="flex-1 flex flex-row overflow-hidden z-10">
          <Sidebar api={api} />

          <div className="flex-1 flex flex-col min-w-0">
            <ProgressBar />

            <div className="flex-1 flex flex-row overflow-hidden relative">
              <div className="flex-1 flex flex-col bg-transparent overflow-hidden relative min-w-0">
                <IssueInbox />
                <Terminal />
              </div>

              <CorrectionPanel api={api} />
            </div>
          </div>
        </div>

        <HistoryModal api={api} />
        <ConfirmModal />
      </div>
    </ErrorBoundary>
  );
```

**Verificación:** Abrir la app en el navegador. Debe verse exactamente igual. Para forzar el error boundary, agregar temporalmente `throw new Error('test')` en cualquier componente hijo → debe mostrar la pantalla de error con botón "Recargar" en lugar de pantalla blanca.

---

### TAREA 1.2: Accesibilidad de modales (Escape, aria, focus)

**Problema:** Los modales no se cierran con Escape, no tienen atributos ARIA, y no atrapan el foco.

**Archivos a modificar:**
- [frontend/src/components/ConfirmModal.jsx](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/ConfirmModal.jsx)
- [frontend/src/components/HistoryModal.jsx](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/HistoryModal.jsx)

#### ConfirmModal.jsx — Reemplazo completo

**ANTES:** 67 líneas sin accesibilidad.

**DESPUÉS:**
```jsx
import { useEffect, useRef } from 'react';
import { useStore } from '../store/useStore';

export const ConfirmModal = () => {
  const config = useStore(s => s.confirmModal);
  const setConfirmModal = useStore(s => s.setConfirmModal);
  const overlayRef = useRef(null);
  const primaryBtnRef = useRef(null);

  const onClose = () => {
    setConfirmModal({ ...config, isOpen: false });
  };

  // Escape para cerrar + auto-focus en botón primario
  useEffect(() => {
    if (!config.isOpen) return;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    // Auto-focus en el botón primario
    setTimeout(() => primaryBtnRef.current?.focus(), 50);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [config.isOpen]);

  // Click en overlay cierra (solo si no es alerta)
  const handleOverlayClick = (e) => {
    if (e.target === overlayRef.current && !config.isAlert) onClose();
  };

  if (!config.isOpen) return null;
  
  return (
    <div
      ref={overlayRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-modal-title"
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={handleOverlayClick}
    >
      <div className="bg-[#1e1e2e] border border-[#313244] rounded-2xl p-6 shadow-2xl max-w-sm w-full mx-4 relative overflow-hidden">
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-accent to-success"></div>
        <h3 id="confirm-modal-title" className="text-xl font-bold text-gray-200 mb-3">{config.title}</h3>
        <p className="text-gray-400 text-sm mb-6 leading-relaxed">{config.message}</p>
        <div className="flex justify-end space-x-3">
          {config.buttons ? (
            <>
              <button
                onClick={onClose}
                className="px-4 py-2 rounded-lg bg-surface hover:bg-white/5 text-gray-300 transition-colors text-sm font-medium border border-white/5"
              >
                Cancelar
              </button>
              {config.buttons.map((btn, idx) => (
                <button
                  key={idx}
                  ref={idx === config.buttons.length - 1 ? primaryBtnRef : null}
                  onClick={() => {
                    if (btn.onClick) btn.onClick();
                    onClose();
                  }}
                  className={btn.className}
                >
                  {btn.label}
                </button>
              ))}
            </>
          ) : (
            <>
              {!config.isAlert && (
                <button
                  onClick={onClose}
                  className="px-4 py-2 rounded-lg bg-surface hover:bg-white/5 text-gray-300 transition-colors text-sm font-medium border border-white/5"
                >
                  Cancelar
                </button>
              )}
              <button
                ref={primaryBtnRef}
                onClick={() => {
                  if (config.onConfirm) config.onConfirm();
                  onClose();
                }}
                className="px-4 py-2 rounded-lg bg-accent text-base hover:opacity-90 font-bold transition-shadow shadow-[0_0_15px_rgba(137,180,250,0.3)] text-sm"
              >
                {config.isAlert ? 'Aceptar' : 'Confirmar'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
```

**Cambios clave vs original:**
1. Importa `useEffect, useRef`
2. Agrega `overlayRef` y `primaryBtnRef`
3. `useEffect` escucha `Escape` y auto-focus en botón primario
4. `handleOverlayClick` cierra al clicar fuera (excepto alertas)
5. El `<div>` overlay tiene `role="dialog"`, `aria-modal="true"`, `aria-labelledby`
6. El `<h3>` tiene `id="confirm-modal-title"` para el labelledby
7. `ref={primaryBtnRef}` en el botón de acción principal

#### HistoryModal.jsx — Agregar Escape y ARIA

**ANTES** (líneas 1-3):
```jsx
import { formatTime } from '../lib/constants';
import { useStore } from '../store/useStore';

export const HistoryModal = ({ api }) => {
```

**DESPUÉS:**
```jsx
import { useEffect, useRef } from 'react';
import { formatTime } from '../lib/constants';
import { useStore } from '../store/useStore';

export const HistoryModal = ({ api }) => {
```

**ANTES** (línea 11-13, primer `if` y apertura del overlay):
```jsx
  if (!show) return null;
  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-md z-50 flex items-center justify-center">
      <div className="bg-surface border border-white/10 rounded-2xl shadow-2xl w-[800px] h-[600px] flex flex-col">
```

**DESPUÉS:** Agregar `useEffect` para Escape, ref para overlay, y atributos ARIA. Insertar **después** de la línea `const { handleDeleteSession } = api;` y **antes** del `if (!show)`:

```jsx
  const overlayRef = useRef(null);

  useEffect(() => {
    if (!show) return;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') setShowHistory(false);
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [show]);

  const handleOverlayClick = (e) => {
    if (e.target === overlayRef.current) setShowHistory(false);
  };

  if (!show) return null;
  return (
    <div
      ref={overlayRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="history-modal-title"
      className="fixed inset-0 bg-black/80 backdrop-blur-md z-50 flex items-center justify-center"
      onClick={handleOverlayClick}
    >
      <div className="bg-surface border border-white/10 rounded-2xl shadow-2xl w-[800px] h-[600px] flex flex-col">
```

Y agregar `id="history-modal-title"` al `<h2>`:
```jsx
          <h2 id="history-modal-title" className="text-2xl font-bold text-gray-100">Historial de Sesiones Guardadas</h2>
```

**Verificación:**
1. Abrir la app, disparar cualquier modal (ej: HistoryModal via el botón de historial en HeaderBar)
2. Presionar `Escape` → el modal debe cerrarse
3. Clicar fuera del panel blanco del modal → debe cerrarse
4. Con el modal abierto, el foco debe estar en el botón primario

---

### TAREA 1.3: WebSocket — Agregar `sessionId` a las dependencias del useEffect

**Problema:** El `useEffect` que crea el WebSocket tiene `[]` como deps pero lee `sessionId`. Si el backend asigna un nuevo `sessionId` tras reset, el WS no se reconecta.

**Archivo:** [frontend/src/hooks/useWebSocket.js](file:///A:/PROJECTS/PDFoverseer/frontend/src/hooks/useWebSocket.js)

**ANTES** (línea 99):
```js
  }, []);
```

**DESPUÉS:**
```js
  }, [sessionId]);
```

**Eso es todo.** El cleanup de la línea 92-98 ya cierra el WS viejo y anula handlers. El `if (!sessionId) return;` de la línea 10 ya previene conexión sin sesión.

**Verificación:** 
1. Abrir la app, verificar que el WS se conecta (ver logs en Terminal)
2. Usar el botón de "Nueva Sesión" o resetear → verificar que la Terminal sigue recibiendo logs del nuevo proceso (el WS debe haberse reconectado automáticamente con el nuevo sessionId)

---

## FASE 2 — Mejoras de calidad

### TAREA 2.1: Consolidar lógica de sort duplicada

**Problema:** El mismo algoritmo de sorting por impact priority aparece duplicado en [IssueInbox.jsx](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/IssueInbox.jsx) (líneas 20-24) y [useApi.js](file:///A:/PROJECTS/PDFoverseer/frontend/src/hooks/useApi.js) (líneas 250-254), con valores mágicos hardcodeados en vez de usar `IMPACT_PRIORITY` de [constants.js](file:///A:/PROJECTS/PDFoverseer/frontend/src/lib/constants.js).

**Archivos a modificar:**
- [frontend/src/lib/constants.js](file:///A:/PROJECTS/PDFoverseer/frontend/src/lib/constants.js) — agregar función helper
- [frontend/src/components/IssueInbox.jsx](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/IssueInbox.jsx) — reemplazar sort inline
- [frontend/src/hooks/useApi.js](file:///A:/PROJECTS/PDFoverseer/frontend/src/hooks/useApi.js) — reemplazar sort inline

#### Paso 1: Agregar a [constants.js](file:///A:/PROJECTS/PDFoverseer/frontend/src/lib/constants.js)

**ANTES** (línea 30-31, final del archivo):
```js
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
};
```

**DESPUÉS** (agregar al final):
```js
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
};

/** Ordena issues por prioridad de impacto (ph5b=1 → internal=6). Retorna nuevo array. */
export const sortByImpactPriority = (issues) => {
  return [...issues].sort((a, b) => {
    const p1 = IMPACT_PRIORITY[a.impact] ?? 99;
    const p2 = IMPACT_PRIORITY[b.impact] ?? 99;
    return p1 - p2;
  });
};
```

#### Paso 2: Reemplazar en [IssueInbox.jsx](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/IssueInbox.jsx)

**ANTES** (línea 1):
```jsx
import { IMPACT_LABELS } from '../lib/constants';
```
**DESPUÉS:**
```jsx
import { IMPACT_LABELS, sortByImpactPriority } from '../lib/constants';
```

**ANTES** (líneas 18-24):
```jsx
  const filteredIssuesList = (selectedPdfPath ? issues.filter(i => i.pdf_path === selectedPdfPath) : issues)
    .filter(i => showAllIssues || (i.impact || 'internal') !== 'internal')
    .sort((a, b) => {
      const p1 = a.impact === 'ph5b' ? 1 : a.impact === 'ph5-merge' ? 2 : a.impact === 'boundary' ? 3 : a.impact === 'sequence' ? 4 : a.impact === 'orphan' ? 5 : 6;
      const p2 = b.impact === 'ph5b' ? 1 : b.impact === 'ph5-merge' ? 2 : b.impact === 'boundary' ? 3 : b.impact === 'sequence' ? 4 : b.impact === 'orphan' ? 5 : 6;
      return p1 - p2;
    });
```
**DESPUÉS:**
```jsx
  const filteredIssuesList = sortByImpactPriority(
    (selectedPdfPath ? issues.filter(i => i.pdf_path === selectedPdfPath) : issues)
      .filter(i => showAllIssues || (i.impact || 'internal') !== 'internal')
  );
```

#### Paso 3: Reemplazar en [useApi.js](file:///A:/PROJECTS/PDFoverseer/frontend/src/hooks/useApi.js)

**ANTES** (líneas 247-255):
```js
  const _getFilteredIssues = (store) => {
    return (store.selectedPdfPath ? store.issues.filter(i => i.pdf_path === store.selectedPdfPath) : store.issues)
      .filter(i => store.showAllIssues || (i.impact || 'internal') !== 'internal')
      .sort((a, b) => {
        const p1 = a.impact === 'ph5b' ? 1 : a.impact === 'ph5-merge' ? 2 : a.impact === 'boundary' ? 3 : a.impact === 'sequence' ? 4 : a.impact === 'orphan' ? 5 : 6;
        const p2 = b.impact === 'ph5b' ? 1 : b.impact === 'ph5-merge' ? 2 : b.impact === 'boundary' ? 3 : b.impact === 'sequence' ? 4 : b.impact === 'orphan' ? 5 : 6;
        return p1 - p2;
      });
  };
```
**DESPUÉS:**
```js
  const _getFilteredIssues = (store) => {
    return sortByImpactPriority(
      (store.selectedPdfPath ? store.issues.filter(i => i.pdf_path === store.selectedPdfPath) : store.issues)
        .filter(i => store.showAllIssues || (i.impact || 'internal') !== 'internal')
    );
  };
```

Y agregar al import de [useApi.js](file:///A:/PROJECTS/PDFoverseer/frontend/src/hooks/useApi.js):
```js
// ANTES:
import { API_BASE, IMPACT_PRIORITY } from '../lib/constants';
// DESPUÉS:
import { API_BASE, IMPACT_PRIORITY, sortByImpactPriority } from '../lib/constants';
```

> **Nota:** Si [useApi.js](file:///A:/PROJECTS/PDFoverseer/frontend/src/hooks/useApi.js) no importa `IMPACT_PRIORITY` actualmente, verificar el import existente. El import actual en línea 1 es `import { API_BASE } from '../lib/constants';`. Ajustar a:
> ```js
> import { API_BASE, sortByImpactPriority } from '../lib/constants';
> ```

**Verificación:** Abrir la app con issues existentes. El orden de issues en la Bandeja debe ser idéntico al de antes (ph5b primero, luego ph5-merge, boundary, sequence, orphan, internal al final). Navegar con flechas izquierda/derecha también debe seguir el mismo orden.

---

### TAREA 2.2: Mover el interval de `spinFrame` de App a Terminal

**Problema:** El `setInterval` de 80ms vive en [App.jsx](file:///A:/PROJECTS/PDFoverseer/frontend/src/App.jsx) pero `spinFrame` solo se consume en [Terminal.jsx](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/Terminal.jsx) y [IssueInbox.jsx](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/IssueInbox.jsx). Moverlo al consumer principal reduce acoplamiento.

**Archivos a modificar:**
- [frontend/src/App.jsx](file:///A:/PROJECTS/PDFoverseer/frontend/src/App.jsx) — eliminar interval y selector
- [frontend/src/components/Terminal.jsx](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/Terminal.jsx) — agregar interval

#### En [App.jsx](file:///A:/PROJECTS/PDFoverseer/frontend/src/App.jsx):

**ANTES** (líneas 21-22):
```jsx
  const setSpinFrame = useStore(s => s.setSpinFrame);
  const metrics = useStore(s => s.metrics);
```
**DESPUÉS:**
```jsx
  const metrics = useStore(s => s.metrics);
```

**ANTES** (líneas 36-39):
```jsx
  useEffect(() => {
    const id = setInterval(() => setSpinFrame(f => (f + 1) % 4), 80);
    return () => clearInterval(id);
  }, [setSpinFrame]);
```
**DESPUÉS:** Eliminar estas 4 líneas por completo.

#### En [Terminal.jsx](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/Terminal.jsx):

**ANTES** (líneas 1-3):
```jsx
import { useRef, useEffect } from 'react';
import { SPINNER } from '../lib/constants';
import { useStore } from '../store/useStore';
```
**DESPUÉS** (sin cambio — ya importa `useEffect`).

**ANTES** (líneas 16-17, después de `const setAiLogMode`):
```jsx
  const logsEndRef = useRef(null);
```
**DESPUÉS:** Insertar el interval justo antes:
```jsx
  const setSpinFrame = useStore(s => s.setSpinFrame);

  useEffect(() => {
    const id = setInterval(() => setSpinFrame(f => (f + 1) % 4), 80);
    return () => clearInterval(id);
  }, [setSpinFrame]);

  const logsEndRef = useRef(null);
```

**Verificación:** Abrir la app, activar la Terminal, iniciar un proceso. El spinner animado (`/ - \ |`) en la línea de scan debe seguir girando exactamente igual que antes.

---

### TAREA 2.3: URLs desde variables de entorno

**Problema:** Las URLs de la API y WebSocket están hardcodeadas. Moverlas a env vars permite configurar sin tocar código.

**Archivo:** [frontend/src/lib/constants.js](file:///A:/PROJECTS/PDFoverseer/frontend/src/lib/constants.js)

**ANTES** (líneas 1-2):
```js
export const API_BASE = 'http://127.0.0.1:8000/api';
export const WS_BASE = 'ws://127.0.0.1:8000/ws';
```
**DESPUÉS:**
```js
export const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000/api';
export const WS_BASE = import.meta.env.VITE_WS_BASE || 'ws://127.0.0.1:8000/ws';
```

El fallback `||` garantiza que sin `.env` el comportamiento sea idéntico al actual.

**Verificación:** La app debe funcionar exactamente igual sin crear ningún `.env`. Las URLs siguen siendo `127.0.0.1:8000`.

---

## FASE 3 — Nice-to-haves (SOLO SI HAY TIEMPO)

No se incluye código propuesto porque estos no son defectos. Solo se listan como referencia:

| # | Mejora | Esfuerzo | Detalle |
|---|--------|----------|---------|
| 3.1 | Virtualizar Terminal con `react-window` | Medio | Instalar `react-window`, reemplazar el `.map()` en Terminal por `<FixedSizeList>`. 200 items no es bottleneck real. |
| 3.2 | Drag-and-drop de archivos en Sidebar | Medio | Agregar `onDragOver`/`onDrop` handlers al contenedor de Sidebar que invoquen `api.handleAddFiles`. |
| 3.3 | Filtro de texto en Sidebar | Bajo | Agregar un `<input>` encima de la lista de PDFs que filtre por `pdf.name.includes(query)`. |
| 3.4 | Reconnection automática de WebSocket | Medio | Agregar lógica de retry con backoff exponencial en [useWebSocket](file:///A:/PROJECTS/PDFoverseer/frontend/src/hooks/useWebSocket.js#5-103) [onclose](file:///A:/PROJECTS/PDFoverseer/frontend/src/hooks/useWebSocket.js#77-87). |
| 3.5 | Indicador de keyboard shortcuts | Bajo | Toast sutil en IssueInbox que diga "← → para navegar issues". |

---

## RESUMEN DE EJECUCIÓN

```
Fase 1 (errores reales):
  1.1  ErrorBoundary.jsx [NEW] + App.jsx [MODIFY]
  1.2  ConfirmModal.jsx [MODIFY] + HistoryModal.jsx [MODIFY]
  1.3  useWebSocket.js [MODIFY] — 1 línea

Fase 2 (calidad):
  2.1  constants.js [MODIFY] + IssueInbox.jsx [MODIFY] + useApi.js [MODIFY]
  2.2  App.jsx [MODIFY] + Terminal.jsx [MODIFY]
  2.3  constants.js [MODIFY] — 2 líneas

Fase 3 (opcional):
  Solo si hay tiempo. No incluye código propuesto.
```

Cada tarea se commitea independientemente. Verificar después de cada una que la app abre y funciona normalmente.
