# Frontend Components (Tier 3 Modularization)

Este directorio contiene la arquitectura fragmentada del frontend de PDFoverseer (anteriormente encapsulada en un único archivo de ~1140 líneas `App.jsx`).

La aplicación sigue un enfoque de React Funcional donde todo el estado global reside en `App.jsx` y fluye unidireccionalmente hacia abajo mediante _props_ (sin usar Context API externo o Redux para no complejizar), garantizando renderizados ultra-rápidos e independientes.

## Árbol de Componentes

*   **HeaderBar.jsx**: Barra superior de controles de aplicación. Dispara las peticiones iniciales (abrir, guardar, iniciar motor).
*   **Sidebar.jsx**: Panel lateral izquierdo. Muestra la lista reactiva de los PDF cargados y un pequeño medidor de confiabilidad.
*   **ProgressBar.jsx**: Componente ultra-ligero central. Solo re-renderiza cuando cambian los ticks de cálculo del backend o de inferencia de GPUs.
*   **IssueInbox.jsx**: La bandeja central de problemas reportados (las "issues" detectadas por el motor Dempster-Shafer y OCR).
*   **CorrectionPanel.jsx**: Panel lateral derecho condicional. Se abre al seleccionar un issue, permitiendo el zoom pan-pinch al buffer base64 nativo de la página infractora y validación humana de correcciones manuales.
*   **Terminal.jsx**: Consola escurridiza conectada directamente por WebSocket al backend `python`. Permite descargar los historiales AI y AI_INF para debuggear modelos Claude externamente.
*   **ConfirmModal.jsx / HistoryModal.jsx**: Componentes de Overlay Z-Index 50+ puramente visuales.

Todas las lógicas asíncronas viven fuera de estos archivos (en `src/hooks/useApi.js` y `src/hooks/useWebSocket.js`).
