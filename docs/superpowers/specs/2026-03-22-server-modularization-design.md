# Server Modularization Design Spec
**Fecha:** 2026-03-22
**Objetivo:** Desfragmentar `server.py` (~850 líneas) en un módulo cohesivo `api/` manteniendo el estado en memoria y los websockets funcionales sin afectar a la interfaz.

## 1. El Problema Actual
`server.py` es un archivo monolítico que abarca:
- Inicialización de FastAPI y montaje estático.
- Objeto de estado global `ServerState` (incluyendo candados de `threading` y eventos).
- Gestor de WebSockets (`ConnectionManager`) y enrutador.
- 15+ Endpoints (agrupados lógicamente pero mezclados en el script).
- Un Worker Thread gigange (`_process_pdfs`) atado a las variables globales.

Al escalar el motor de inferencia, agregar nuevos endpoints (como reportes en Excel, o configuraciones del sistema) hará que `server.py` colapse rápidamente.

## 2. Nueva Arquitectura Propuesta

Se creará un nuevo subpaquete `api/` a nivel raíz, aliviando la carga del archivo principal.

```text
a:/PROJECTS/PDFoverseer/
├── api/
│   ├── __init__.py           (Exporta el state, router principal)
│   ├── state.py              (Clase ServerState y el singleton `state`)
│   ├── websocket.py          (ConnectionManager, función `_emit` y el endpoint WS)
│   ├── worker.py             (Lógica del thread secundario `_process_pdfs` y `_recalculate_metrics`)
│   └── routes/               (Controladores FastAPI, incluyen al router)
│       ├── __init__.py
│       ├── files.py          (add_folder, add_files, remove_pdf, open_pdf)
│       ├── sessions.py       (get_state, reset, save, list, delete session)
│       └── pipeline.py       (start, pause, resume, stop, skip, correct, exclude)
├── core/                     (Intacto)
├── frontend/                 (Intacto)
└── server.py                 (Punto de entrada ultra-ligero que une api/ con uvicorn)
```

## 3. Prevención de Circular Dependencies
1. **El Estado es el Rey:** `api.state` será hoja del árbol de dependencias. Solo importará typing/threading nativo. Todo lo demás leerá desde `api.state` importando `global_state`.
2. **WebSockets ciegos:** `api.websocket` no necesita conocer de rutas. Exportará `manager` y `_emit()`. Para inyectar asincronía (el `state.loop`), `server.py` asignará el loop principal en su lifespan.
3. **El Worker lee hacia arriba:** `api.worker` importará `api.state` y `api.websocket._emit`.
4. **Los Routes son orquestadores:** Importarán de `api.state`, `api.websocket`, y `api.worker`, despachando los endpoints a las lógicas exactas. `server.py` importará los `APIRouter` y los conectará a la instancia general de `FastAPI`.

## 4. Retrocompatibilidad Continua
- Los endpoints mantendrán su nomenclatura exacta (`/api/pause`, `/api/correct`).
- El WebSocket emitirá exactamente las mismas estructuras (sin cambios al middleware de Vite).
- `ServerState` preservará sus atributos al 100%. Mismo `lock`, `Events` y `confidences`.
