# Server Modularization Plan

**Contexto:** Descuartizamiento estructurado del monolito `server.py` (~850 líneas de backend).
**Meta:** Llegar a `< 100` líneas en `server.py` moviendo la lógica al paquete `api/` bajo un patrón router-controller-state, **sin interrumpir** la funcionalidad en vivo conectada al frontend.

## FASE 1: Foundations (Estado y WS)
- [ ] Crear el directorio `api/`.
- [ ] Mover la clase `ServerState` y su instanciador `state` a `api/state.py`.
- [ ] Mover `ConnectionManager`, su instancia `manager` y el enviador global `_emit` a `api/websocket.py`. Incluir también el endpoint websocket en su propio `router = APIRouter()`.
- [ ] *(Prueba inter-pase)* Verificar importaciones básicas.

## FASE 2: Worker Thread 
- [ ] Crear `api/worker.py`. 
- [ ] Extraer el grueso de `_process_pdfs` hacia allí.
- [ ] Extraer la extensa métrica `_recalculate_metrics` hacia este archivo. Asegurar que las importaciones a `core.analyzer` o lo que use sea válido.
- [ ] Mapear llamadas de estado al singleton `from api.state import global_state as state`.
- [ ] Mapear logs al broadcaster `from api.websocket import _emit`.

## FASE 3: Enrutadores (Endpoints API REST)
- [ ] Crear directorio `api/routes/`.
- [ ] **Files Route (`api/routes/files.py`):** Aislar endpoints de manipulación de archivos que tocan OS y Tkinter (`/add_folder`, `/add_files`, `/remove_pdf`, `/open_pdf`, `/debug_add`). Instanciar su `APIRouter`.
- [ ] **Sessions Route (`api/routes/sessions.py`):** Aislar persistencia de historial puro JSON y recover state (`/state`, `/reset`, `/save_session`, `/sessions`, `/delete_session`).
- [ ] **Pipeline Route (`api/routes/pipeline.py`):** Centralizar la botonería que dispara eventos de control de `threading` del engine de PDFs (`/start`, `/pause`, `/resume`, `/stop`, `/skip`, `/correct`, `/exclude`). 

## FASE 4: Orchestrator (Nuevo `server.py`)
- [ ] En `server.py`, borrar el viejo código y reescribirlo totalmente para que importe `FastAPI`, configure la instancia CORS, sirva los archivos estáticos de `/frontend/dist/` e inserte los `router` desde `api/`.
- [ ] Mantener el `uvicorn.run()` global.
- [ ] *(Run)*: `python server.py`. Lanzar backend y ver que levante limpio. Confirmar que el navegador con Vite puede abrir una carpeta con PDFs y que el motor inicie asincronamente.
