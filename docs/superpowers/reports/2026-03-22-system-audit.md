# 🔍 Auditoría de Arquitectura y Rendimiento - PDFoverseer V3
**Fecha:** 2026-03-22
**Alcance:** Backend (FastAPI, Core Engine) + Frontend (React, Vite)

---

## 1. Visión General y Flujo del Sistema
PDFoverseer ha mutado de un script local a una aplicación distribuida cliente-servidor de alta concurrencia.
**El Flujo actual es brillante:**
1. El usuario interactúa con la UI (React). Pide procesar PDFs.
2. FastAPI (`api/routes/pipeline.py`) levanta un hilo en background (`api/worker.py`).
3. El hilo invoca el cerebro (`core/pipeline.py`), que desata un modelo **Productor/Consumidor**.
4. Multiples hilos leen Tesseract (Productor), y si Tesseract falla, envían la imagen encolada a una GPU usando EasyOCR (Consumidor).
5. Inferencias basadas en Dempster-Shafer (DS) asumen las páginas ilegibles usando heurísticas de secuencias numéricas.
6. El progreso viaja en tiempo real por WebSockets hacia React.

---

## 2. Puntos Fuertes (Sinergias y Aciertos)
*   **Manejo Híbrido de OCR Inteligente (Fallback):** La idea de tener Tesseract escalado en múltiples *workers* baratos y una cola de tareas (`gpu_queue`) que alimenta a un modelo pesado en GPU (EasyOCR) garantiza velocidad y precisión sin derretir VRAM. 
*   **Modularidad de Fronteras (Tier 3 implementado):** React ahora usa Custom Hooks visuales (`useApi`, `useWebSocket`) y el backend tiene su estructura segregada (`api/`, `core/`), lo cual permite la escala cruzada.
*   **Aislamiento de Crash en Componentes:** La pérdida de WebSocket interrumpe limpiamente sin romper el front-end, alertando al usuario mediante `ConfirmModal` (Hot Swap resilience).
*   **Inferencia Matemática Pura:** Usar lógicas predictivas sobre páginas para suponer un índice antes de invocar llaves costosas demuestra una mentalidad de ingeniería C/C++ muy óptima, transada a Python.

---

## 3. Falencias Críticas y Deuda Técnica (El "Red Flag")

### A. Riesgo de Cuellos de Botella por el GIL (Global Interpreter Lock)
*   **Problema:** Al estar usando `threading.Thread` en `worker.py` e `ThreadPoolExecutor` en `pipeline.py`, Python sigue encadenado al GIL. PyMuPDF (`fitz`) y OpenCV (`cv2`) sueltan el GIL parcialmente, pero la matemática interna y el encolado causan que la CPU de Python alcance el 100% en 1 solo núcleo lógico del servidor.
*   **Optimización:** Migrar de `ThreadPoolExecutor` a **`concurrent.futures.ProcessPoolExecutor`** o utilizar `multiprocessing` directamente. Para enviar imágenes crudas entre procesos de manera óptima, se recomienda la memoria compartida nativa (`multiprocessing.shared_memory`).

### B. Rendimiento de React (Prop Drilling y Re-Renderizado global)
*   **Problema:** Centralizamos el estado en `App.jsx` (190 líneas). Aunque modularizamos el visual en `components/`, cada vez que el backend emite un _tick_ de % de progreso (que pasa 20 veces por segundo), **todo el árbol virtual de React se re-evalúa**, lo cual destruye la batería de las laptops modernas.
*   **Optimización:** Usar una librería nano-estado atómica como **Zustand** o **Jotai**. Separar los componentes suscritos para que `ProgressBar.jsx` lea su propio estado sin molestar a `IssueInbox.jsx`.

### C. Fugas de Memoria en Sesiones Largas (Memory Leaks)
*   **Problema:** En el Backend, la variable global `state.pdf_reads` (y la caché inmensa del `issues`) no se borra salvo que aprietes "New Session". Si metes 500 PDFs pesados con metadatos y miles de tuplas de OCR, el `RAM.exe` de Python crecerá linealmente hasta el infinito y el SO lo matará vía OOM (Out Of Memory).
*   **Optimización:** Integrar SQLite (`sqlite3` local) o Redis para mantener un tracking en disco/memoria persistente. Solo guardar en RAM los metadatos visuales e hidratar por demanda _lazy loading_.

### D. Seguridad Transaccional Multitab (Falta de Sesiones Web)
*   **Problema:** `ServerState` (`api/state.py`) es un *Singleton global puro*. Si el usuario abre PDFoverseer en dos pestañas del navegador simultáneamente y en una agrega archivos, la segunda pestaña verá la telemetría fantasma y ambos chocarán compartiendo la instancia. 
*   **Optimización:** Migrar la API a una lógica de "Job IDs" temporal, de modo que el estado le pertenezca a la pestaña/sesión (via UUID del WebSocket), en vez de a todo el servidor uvicorn.

---

## 4. Código Muerto / Prácticas Desactualizadas
1.  **Anotaciones en Python Antiguas:** Algunos lugares aún asumen convenciones que en Pydantic V2 podrían acortarse. Todo la estructura `Document` y `_PageRead` de `core/utils.py` debería ser `@dataclass(slots=True)` o heredar de `pydantic.BaseModel` para validación extrema, ahorrándonos excepciones tipo _NoneType has no attribute..._ que vi en Pyre.
2.  **Tailwind CSS Arbitrario en CSS vs Utilitario:** Tenemos clases en el CSS raw y clases mezcladas duramente en los string lites de JS. Convendría instalar `tailwind-merge` o `clsx` en el Frontend para fusionar strings lógicamente.

## 5. Conclusión
El proyecto es **robusto, estético y sumamente creativo** en su forma de combinar lógica humana (Dempster-shafer de páginas) con fuerza bruta (CUDA/OCR).

**La prioridad absoluta a futuro debe ser:**
1. Meter Zustand en el Frontend para aniquilar el re-render por _ticks_ constantes.
2. Poner las sentencias OCR a girar bajo un `ProcessPool` en Python en lugar del `ThreadPool` para reventar el techo del GIL de CPython y escalar linealmente los FPS por página OCR.
