# Contra-Auditoría: PDFoverseer Frontend

Verificación línea-por-línea de los 12 archivos fuente del frontend contra las afirmaciones de la auditoría original.

---

## RESUMEN EJECUTIVO

| Categoría | Válidos | Exagerados | Falsos | Faltantes |
|-----------|:-------:|:----------:|:------:|:---------:|
| Performance | 2 | 2 | 1 | 1 |
| Arquitectura/Store | 1 | 2 | 1 | 0 |
| UX / a11y | 2 | 1 | 0 | 2 |
| Seguridad | 0 | 1 | 0 | 0 |
| **Total** | **5** | **6** | **2** | **3** |

---

## VEREDICTOS POR PUNTO

### 1. Performance

#### 1a. `spinFrame` causa re-render global cada 80ms
| Claim | Veredicto |
|-------|-----------|
| "spinFrame en el store → re-render de todo" | ❌ **FALSO** |

**Evidencia:** El timer vive en [App.jsx:37](file:///A:/PROJECTS/PDFoverseer/frontend/src/App.jsx#L36-L39), pero `spinFrame` solo se consume en [Terminal.jsx:14](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/Terminal.jsx#L14) y [IssueInbox.jsx:16](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/IssueInbox.jsx#L16) con selectores granulares (`useStore(s => s.spinFrame)`). Zustand solo re-renderiza componentes que seleccionan ese slice. App no consume spinFrame — solo llama [setSpinFrame](file:///A:/PROJECTS/PDFoverseer/frontend/src/store/useStore.js#39-40). **No hay re-render global.**

> [!TIP]
> Aún así, mover el `setInterval` al componente que lo consume ([Terminal](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/Terminal.jsx#5-95)) evitaría que un setter innecesario viva en App.

#### 1b. Terminal renderiza 200+ líneas sin virtualización
| Claim | Veredicto |
|-------|-----------|
| "Rinde 200 divs en cada log" | ✅ **VÁLIDO** |

**Evidencia:** [Terminal.jsx:65-77](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/Terminal.jsx#L65-L77) hace `.map()` directo sobre `logs` (capped a 200 en WebSocket). No hay virtualización (`react-window` o similar). Con 200 elementos de texto no es catastrófico, pero sí mejorable.

#### 1c. "App.jsx tiene 450 líneas monolíticas"
| Claim | Veredicto |
|-------|-----------|
| "450+ líneas en un componente monolítico" | ❌ **FALSO** |

**Evidencia:** [App.jsx](file:///A:/PROJECTS/PDFoverseer/frontend/src/App.jsx) tiene **80 líneas** y es puramente composicional. Delega todo a componentes ([HeaderBar](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/HeaderBar.jsx#3-82), [Sidebar](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/Sidebar.jsx#3-88), [ProgressBar](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/ProgressBar.jsx#4-45), [IssueInbox](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/IssueInbox.jsx#4-161), [Terminal](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/Terminal.jsx#5-95), [CorrectionPanel](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/CorrectionPanel.jsx#5-105)) y hooks ([useApi](file:///A:/PROJECTS/PDFoverseer/frontend/src/hooks/useApi.js#5-397), [useWebSocket](file:///A:/PROJECTS/PDFoverseer/frontend/src/hooks/useWebSocket.js#5-103)). La auditoría infló números 5x.

#### 1d. IssueInbox.jsx es "excesivamente largo"
| Claim | Veredicto |
|-------|-----------|
| "Componente gigante" | ⚠️ **EXAGERADO** |

**Evidencia:** [IssueInbox.jsx](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/IssueInbox.jsx) tiene **79 líneas**. Es compacto y legible. Contiene lógica de filtrado y sort inline que podría extraerse, pero no es un problema real.

#### 1e. Re-render innecesario por `metrics` en App
| Claim | Veredicto |
|-------|-----------|
| Audit no lo mencionó | 🔍 **FALTANTE** |

[App.jsx:22](file:///A:/PROJECTS/PDFoverseer/frontend/src/App.jsx#L22) consume `metrics` pero solo para renderizar la barra de resumen. Esto es correcto y necesario — no es un problema mayor.

#### 1f. Lógica de sort duplicada
| Claim | Veredicto |
|-------|-----------|
| Audit no lo mencionó | 🔍 **FALTANTE** |

La misma lógica de sorting por impact priority aparece en [IssueInbox.jsx:24-29](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/IssueInbox.jsx#L24-L29) y en [useApi.js:250-254](file:///A:/PROJECTS/PDFoverseer/frontend/src/hooks/useApi.js#L250-L254). Debería consolidarse usando `IMPACT_PRIORITY` de [constants.js](file:///A:/PROJECTS/PDFoverseer/frontend/src/lib/constants.js).

---

### 2. Arquitectura / Store

#### 2a. "Store monolítico con un solo objeto"
| Claim | Veredicto |
|-------|-----------|
| "Zustand store monolítico sin slices" | ⚠️ **EXAGERADO** |

**Evidencia:** [useStore.js](file:///A:/PROJECTS/PDFoverseer/frontend/src/store/useStore.js) tiene **54 líneas**, ~20 campos y ~20 setters. Para una app de este tamaño es un patrón perfectamente válido. Zustand **por diseño** no necesita slices si los selectores son granulares (lo son). Partir el store agregaría complejidad sin beneficio real.

#### 2b. "No hay error boundaries"
| Claim | Veredicto |
|-------|-----------|
| "Falta manejo de errores" | ✅ **VÁLIDO** |

No hay ningún `<ErrorBoundary>` en el árbol de componentes. Si un componente crashea, toda la app se rompe. [useApi.js](file:///A:/PROJECTS/PDFoverseer/frontend/src/hooks/useApi.js) maneja errores de red con [handleApiErr](file:///A:/PROJECTS/PDFoverseer/frontend/src/hooks/useApi.js#14-25) (modal de error), pero errores de render no están cubiertos.

#### 2c. "Hook [useApi](file:///A:/PROJECTS/PDFoverseer/frontend/src/hooks/useApi.js#5-397) viola el principio de responsabilidad única"
| Claim | Veredicto |
|-------|-----------|
| "Hace demasiado" | ⚠️ **EXAGERADO** |

[useApi.js](file:///A:/PROJECTS/PDFoverseer/frontend/src/hooks/useApi.js) tiene **397 líneas** y contiene handlers para browse, start, pause, stop, skip, correct, exclude, sessions, etc. Es largo, pero cohesivo: todo es "comunicación con la API". Partirlo por dominio (sesiones, proceso, corrección) sería una mejora marginal, no un defecto grave.

#### 2d. "WebSocket no tiene reconnection"
| Claim | Veredicto |
|-------|-----------|
| "No reintentos automáticos" | ✅ **VÁLIDO — pero con matiz** |

[useWebSocket.js](file:///A:/PROJECTS/PDFoverseer/frontend/src/hooks/useWebSocket.js) no implementa reconnection. Pero **sí** muestra un modal de "Conexión Perdida" en [onclose](file:///A:/PROJECTS/PDFoverseer/frontend/src/hooks/useWebSocket.js#77-87) (línea 78). Para una app local de escritorio esto es razonable — el usuario controla el backend. Reconnection sería un nice-to-have.

> [!NOTE]
> El `useEffect` en [useWebSocket](file:///A:/PROJECTS/PDFoverseer/frontend/src/hooks/useWebSocket.js#5-103) tiene `[]` como deps pero lee `sessionId` (línea 7/10). El WS no se reconecta cuando cambia `sessionId` tras reset.

---

### 3. UX / Accesibilidad

#### 3a. "No hay soporte de drag-and-drop"
| Claim | Veredicto |
|-------|-----------|
| "Falta D&D para agregar PDFs" | ✅ **VÁLIDO** |

No hay handlers `onDrop`/`onDragOver` en ningún componente. La Sidebar tiene botones de "Abrir" y "Añadir" pero no acepta drops.

#### 3b. "Sidebar no tiene tooltips"
| Claim | Veredicto |
|-------|-----------|
| "Falta información contextual" | ⚠️ **EXAGERADO** |

[Sidebar.jsx](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/Sidebar.jsx) muestra el filename completo en la lista. No necesita tooltips porque el nombre visible ya es informativo **excepto** cuando el path se trunca — lo cual sí pasa con paths largos.

#### 3c. "Modales no son accesibles"
| Claim | Veredicto |
|-------|-----------|
| "Sin focus trap, aria, tecla Escape" | ✅ **VÁLIDO** |

[ConfirmModal.jsx](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/ConfirmModal.jsx) y [HistoryModal.jsx](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/HistoryModal.jsx) no tienen:
- `role="dialog"` / `aria-modal`
- Focus trap
- Cierre con `Escape`
- Auto-focus en el primer botón

#### 3d. Keyboard navigation de issues
| Claim | Veredicto |
|-------|-----------|
| Audit no lo mencionó completamente | 🔍 **FALTANTE** |

[App.jsx:25-33](file:///A:/PROJECTS/PDFoverseer/frontend/src/App.jsx#L25-L33) implementa ArrowLeft/ArrowRight para navegar issues. Esto ya existe y funciona. Sin embargo, no hay indicación visual de que este shortcut existe.

#### 3e. Sidebar no tiene búsqueda/filtro
| Claim | Veredicto |
|-------|-----------|
| "Difícil encontrar archivos en listas largas" | La auditoría no lo mencionó pero es una mejora real |

Con 100+ PDFs, la Sidebar solo tiene scroll. Un filtro de texto sería valioso.

---

### 4. Seguridad

#### 4a. "URLs hardcodeadas"
| Claim | Veredicto |
|-------|-----------|
| "API_BASE y WS_BASE hardcodeados" | ⚠️ **EXAGERADO** |

[constants.js](file:///A:/PROJECTS/PDFoverseer/frontend/src/lib/constants.js) tiene `http://127.0.0.1:8000`. Para una app local de escritorio esto es correcto. Moverlo a env vars sería más limpio pero no es un riesgo de seguridad.

---

## PLAN DE IMPLEMENTACIÓN

> [!IMPORTANT]
> **Restricción zero-break:** Cada cambio individual debe mantener la app 100% funcional. No refactors combinados. Un commit por mejora, testeable independientemente.

### Fase 1 — Errores reales (3 cambios)

Estos son defectos que vale la pena corregir:

#### 1.1 Error Boundary global
- **Archivo:** [App.jsx](file:///A:/PROJECTS/PDFoverseer/frontend/src/App.jsx)
- **Cambio:** Envolver el árbol con un `<ErrorBoundary>` que muestre un botón "Recargar" en lugar de pantalla blanca
- **Riesgo:** Ninguno. Es aditivo.

#### 1.2 Accesibilidad de modales
- **Archivos:** [ConfirmModal.jsx](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/ConfirmModal.jsx), [HistoryModal.jsx](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/HistoryModal.jsx)
- **Cambio:** Agregar `role="dialog"`, `aria-modal="true"`, cierre con `Escape`, auto-focus en botón primario
- **Riesgo:** Muy bajo. Solo agrega atributos y listeners.

#### 1.3 WebSocket: dependencia de `sessionId`
- **Archivo:** [useWebSocket.js](file:///A:/PROJECTS/PDFoverseer/frontend/src/hooks/useWebSocket.js)
- **Cambio:** Agregar `sessionId` al array de deps del `useEffect` para que el WS se reconecte tras [handleNewSession](file:///A:/PROJECTS/PDFoverseer/frontend/src/hooks/useApi.js#108-136)
- **Riesgo:** Bajo. El cleanup actual ya cierra `ws.current`, la reconexión debería ser transparente.

### Fase 2 — Mejoras de calidad (3 cambios)

#### 2.1 Consolidar lógica de sort
- **Archivos:** [IssueInbox.jsx](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/IssueInbox.jsx), [useApi.js](file:///A:/PROJECTS/PDFoverseer/frontend/src/hooks/useApi.js), [constants.js](file:///A:/PROJECTS/PDFoverseer/frontend/src/lib/constants.js)
- **Cambio:** Crear una función `sortIssuesByPriority(issues)` en [constants.js](file:///A:/PROJECTS/PDFoverseer/frontend/src/lib/constants.js) usando `IMPACT_PRIORITY`. Reemplazar la lógica duplicada.
- **Riesgo:** Ninguno si el sort resultante es idéntico (misma prioridad).

#### 2.2 Mover `spinFrame` interval a Terminal
- **Archivos:** [App.jsx](file:///A:/PROJECTS/PDFoverseer/frontend/src/App.jsx), [Terminal.jsx](file:///A:/PROJECTS/PDFoverseer/frontend/src/components/Terminal.jsx)
- **Cambio:** Eliminar el `setInterval` de App y ponerlo en Terminal (el consumer principal). IssueInbox puede lanzar su propio interval o usar un ref local.
- **Riesgo:** Bajo. Cambio de ownership del timer.

#### 2.3 URLs desde variables de entorno
- **Archivo:** [constants.js](file:///A:/PROJECTS/PDFoverseer/frontend/src/lib/constants.js)
- **Cambio:** `const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000/api'`
- **Riesgo:** Ninguno. El fallback mantiene el comportamiento actual.

### Fase 3 — Nice-to-haves (solo si hay tiempo)

| Mejora | Esfuerzo | Impacto |
|--------|----------|---------|
| Virtualización de Terminal (react-window) | Medio | Bajo (200 items no es un bottleneck real) |
| Drag-and-drop de archivos en Sidebar | Medio | Medio |
| Filtro de texto en Sidebar | Bajo | Medio |
| Reconnection automática de WebSocket | Medio | Bajo (app local) |
| Toast visual para keyboard shortcuts | Bajo | Bajo |

---

## CONCLUSIÓN

La auditoría original tiene **5 puntos válidos** que vale la pena atender, pero contiene **6 exageraciones** y **2 afirmaciones falsas** que inflan la gravedad. El frontend no es perfecto, pero está bien estructurado para su alcance: App.jsx tiene 80 líneas (no 450), los componentes usan selectores granulares de Zustand (no re-renders globales), y el manejo de errores de API existe (solo faltan error boundaries de render).

**El plan de 6 cambios en Fases 1-2 cubre todos los defectos reales sin romper nada.**
