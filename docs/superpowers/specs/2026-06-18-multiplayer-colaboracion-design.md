# Multiplayer / colaboración multiusuario — diseño

**Fecha:** 2026-06-18
**Estado:** diseño aprobado (brainstorm), pendiente de plan de implementación
**Alcance:** PDFoverseer (paso 2). Colaboración en vivo entre 2 humanos (Daniel, Carla) +
1 agente (Claude) sobre la misma sesión-mes, en LAN, con un solo proceso backend.

---

## 1. Propósito

Hoy PDFoverseer es de un solo operador: una persona abre un mes y cuenta. La meta es
que **dos personas (y Claude) trabajen el mismo mes a la vez**, viendo lo que hace el
otro en vivo, sin pisarse y sin riesgo para los datos.

Escenario real (confirmado con el usuario):
- Trabajan **en paralelo, sin repartir hospitales**. Cualquiera puede estar en cualquier
  celda en cualquier momento.
- Cuando alguien está editando una celda, esa celda queda **ocupada**: los demás la ven
  en **solo-lectura** (pueden mirar conteo/archivos/notas, pero los controles de edición
  están deshabilitados y marcados con el badge del dueño). Al moverse el dueño a otra
  celda, la anterior se libera.
- **Claude es un participante más:** aparece con su propio badge cuando se le manda a
  trabajar, y la celda que toca queda bloqueada igual que la de cualquier perfil.

## 2. No-objetivos (YAGNI)

- **No** co-edición concurrente de la misma celda (CRDT/OT tipo Google Docs). Los datos son
  enteros estructurados por celda, no texto libre; el lock duro elimina el problema de raíz.
- **No** autenticación con contraseñas. Es una LAN de confianza con 2 personas + Claude.
- **No** escalado multiproceso (`--workers N`). Ver §11.
- **No** persistir presencia/locks. Son efímeros (ver §9).
- **No** base de datos en tiempo real externa (Firebase/Convex/Yjs). Sobreingeniería para
  este contexto; la app ya tiene las primitivas necesarias (ver §3).

## 3. Por qué la arquitectura actual ya sirve

Tres piezas existen y calzan sin reescritura:

1. **Canal pub/sub por sesión.** `api/routes/ws.py` tiene
   `_CONNECTIONS: dict[session_id → set[WebSocket]]` y `broadcast(session_id, event)`.
   Hoy solo lleva progreso de escaneo (servidor→cliente). Es el tubo que multiplayer
   necesita.
2. **Merge de eventos en el frontend.** `frontend/src/store/session.js` (`_handleWSEvent`,
   caso `cell_done` ~L649) ya aplica un cambio de celda empujado por el servidor al estado
   local de Zustand. **Ojo (precisión):** ese merge es **parcial** — copia solo 6 campos
   (`ocr_count`, `method`, `confidence`, `duration_ms_ocr`, `near_matches`, `per_file`), NO
   reemplaza la celda entera. `cell_updated` (§4) NO puede usar ese patrón parcial: un cambio
   remoto puede tocar cualquier campo (`note`, `user_override`, `per_file_overrides`,
   `confirmed`, `worker_marks`, `reorg_doc_delta`, …) y un merge de 6 campos los descartaría en
   silencio. Por eso `cell_updated` lleva el **snapshot completo** y el frontend **reemplaza la
   celda entera** (§4). `frontend/src/lib/ws.js` ya tiene cliente WS con reconexión + backoff.
3. **Escrituras serializadas y seguras entre clientes.** `api/state.py` (`_synchronized` +
   `RLock`): cada setter hace *load → modifica solo su celda → reescribe el blob*. Dos
   escrituras a **celdas distintas** ya son seguras hoy. El único riesgo es pisar la misma
   celda — y eso lo elimina el lock duro (§6).

## 4. Modelo de sincronización (server-autoritativo, broadcast-on-write)

El servidor sigue siendo la única fuente de verdad (blob en SQLite). Tras **cada escritura
commiteada** de una celda, el servidor difunde `cell_updated` con el **snapshot completo** de
esa celda; el frontend **reemplaza la celda entera** en su estado local (no un merge por
campos — ver §3 ítem 2).

- **Evento (contrato).**
  ```json
  {"type": "cell_updated",
   "hospital": "HRB", "sigla": "odi",
   "actor": "<participant_id>",
   "cell": { /* snapshot COMPLETO de la celda, mismo shape que cada celda en GET /sessions/{id} */ }}
  ```
  El frontend hace `cells[hospital][sigla] = event.cell` (reemplazo completo). `actor` permite
  al cliente distinguir su propio cambio (ya aplicado localmente) de uno remoto, y evitar
  parpadeos (puede ignorar el evento cuyo `actor` es su propio `participant_id`).
- **Punto único de choque.** El broadcast NO se rocía por los ~12 setters de `state.py`. Se
  centraliza para que ningún setter pueda "olvidar" difundir. Dos enfoques candidatos que el
  plan de M1 debe elegir (no es trabajo de arquitectura abierto — están acotados aquí):
  - (a) **Decorador/wrapper alrededor del commit** (`update_session_state` o `_synchronized`):
    cada setter, al persistir, encola el `cell_updated` de su celda. Pro: imposible olvidarlo.
    Contra: el setter debe saber qué (hospital, sigla) tocó.
  - (b) **Capa de servicio por encima de las rutas:** las rutas de edición, tras llamar al
    setter, difunden. Pro: la ruta ya conoce (hospital, sigla) y el `actor`. Contra: hay que
    cubrir cada ruta de escritura.
  Se recomienda (b) por el `actor` (lo conoce la ruta, no el setter) y porque mantiene
  `state.py` ajeno al transporte.
- **Puente async-desde-sync (restricción real).** `broadcast` es `async`. Las rutas de
  edición HTTP son handlers `async` → pueden `await broadcast(...)` directo. Pero el escaneo
  corre en **hilos de fondo** y ya difunde vía el patrón existente
  `asyncio.run_coroutine_threadsafe(broadcast(session_id, event), app.state.loop)`
  (`api/routes/sessions.py` `_safe_broadcast`, ~L560-567, con guarda `loop.is_closed()`).
  Cualquier `cell_updated` emitido desde un hilo (p.ej. el escaneo) DEBE reusar ese mismo
  puente, no `await` directo (no hay loop en el hilo).
- **Auto-sanación (red de seguridad).** El modo de falla de broadcast-on-write es "se perdió
  un evento → pantalla vieja". Se cubre con: (a) el cliente ya re-fetchea la sesión completa
  al **reconectar** el WS; (b) se agrega re-fetch al **recuperar foco de pestaña**
  (`visibilitychange`). Aunque se caiga un evento, la pantalla se corrige sola.

## 5. El WS se queda como tubo de bajada (sin protocolo de 2 vías)

Decisión clave (revisada durante el brainstorm): **claim/release/heartbeat van por HTTP, no
por WS.** El WS solo **baja** eventos (`cell_updated`, diffs de presencia/lock, y el progreso
de escaneo que ya existe). Por qué:

1. **Claude y humanos usan la misma mecánica.** Claude habla HTTP, no WS. Con locks por HTTP,
   no hay rama "agente".
2. **`ws.py` casi no cambia** → menos riesgo para el progreso de escaneo que ya funciona. El
   handler del socket sigue ignorando los mensajes entrantes (solo keepalive); solo se agregan
   nuevos *tipos* de evento de bajada (llamadas a `broadcast()`).
3. **Sobrevive a reconexiones.** El cliente WS reconecta con backoff (`ws.js`). Atar el lock al
   *socket* haría perder la celda en cada parpadeo. Atándolo al `participant_id` + lease, la
   reconexión es transparente.

## 6. Presencia + locks: un registro único en memoria, basado en *lease*

### 6.1 Estructura

Un registro por participante, en memoria del proceso (efímero, §9):

```
participants[session_id][participant_id] = {
    "participant_id": str,
    "name": str,
    "color": str,             # color del badge
    "kind": "human" | "agent",
    "focused_cell": "HRB|odi" | None,   # la celda abierta en su UI; None en vista mes/hospital
    "mode": "editor" | "viewer",        # si tiene el lock de edición de focused_cell, o solo mira
    "expires_at": float,      # epoch; vencido = se purga (presencia + su lock)
}
```

- **El lock se deriva:** el editor de una celda es el participante con
  `focused_cell == cell and mode == "editor"`. Se garantiza **a lo más uno** en el momento
  del claim (atómico bajo `RLock`).
- **Un lease por participante.** Vencerlo cascada: se elimina de presencia **y** se libera su
  lock. Sin casos especiales por tipo de borde (caída, suspensión, tarea de Claude cortada).
- **Sincronización:** el registro de participantes comparte el **mismo `RLock`** de
  `SessionManager` (no se introduce un segundo primitivo). Las operaciones de presencia/claim
  se serializan con las escrituras de celda, lo que además da el claim atómico de §6.4 gratis.
  Para 2-3 participantes el bloqueo breve es irrelevante.

### 6.2 Endpoints HTTP

- `POST /api/sessions/{id}/presence/heartbeat` — body `{participant_id, name, color}`.
  Renueva el lease (lo crea si es nuevo = "join"). Periódico (~15 s) desde el navegador.
  **Devuelve en el body HTTP el snapshot de presencia actual** — así un cliente que se conecta
  cuando los demás están quietos conoce el estado al instante, sin esperar un cambio ajeno.
- `POST /api/sessions/{id}/presence/focus` — body `{participant_id, cell: "H|sigla" | null}`.
  **Focus = claim.** Suelta la celda anterior del participante; si `cell` no es null, intenta
  tomarla como editor (atómico bajo `RLock`): devuelve `{mode: "editor"}` si quedó libre, o
  `{mode: "viewer", lock_holder: {participant_id, name, color, kind}}` si estaba ocupada. El
  frontend DEBE actuar sobre `mode`: en `"viewer"`, además de deshabilitar los controles,
  **muestra un aviso inline visible** ("Carla está editando esta celda") — nunca degradar a
  solo-lectura en silencio. `cell=null` = volver a vista mes/hospital (suelta sin tomar nada).
- `POST /api/sessions/{id}/presence/leave` — body `{participant_id}`. Quita al participante
  (best-effort al cerrar pestaña vía `navigator.sendBeacon`; el vencimiento del lease es el
  respaldo).

**Cuándo se difunde `presence` (§7):** ante **cualquier cambio** del mapa de participantes
(join, focus, leave, expiración) — **no** en cada heartbeat. El heartbeat sin cambios solo
renueva el lease y responde el snapshot por HTTP; no genera tráfico WS. Así se evita ruido
periódico con 2-3 participantes.

### 6.3 Liveness

- **Humano:** el navegador manda `heartbeat` cada ~15 s. Vencimiento ~45 s. Al cerrar limpio
  → `leave` inmediato; si el equipo se cae/suspende → vence en ≤45 s.
- **Claude:** NO manda heartbeat. Cada llamada HTTP suya que escribe una celda renueva su
  lease y fija su `focused_cell` a esa celda (presencia "por-celda-activa" automática). Deja
  de trabajar → su lease vence. Sin navegador, sin WS, sin lock pegado.

### 6.4 Enforcement (M3)

Los endpoints que **escriben** una celda reciben `participant_id`. Hay **dos caminos
distintos**, y ambos resuelven el chequeo de lock **dentro de la misma adquisición del
`RLock`** que la escritura (sin ventana TOCTOU entre "verifico lock" y "escribo"):
- **Humano (claim explícito y previo):** el navegador hizo `focus`(claim) **antes** de editar
  → ya es editor. El endpoint de escritura solo **verifica** que `participant_id` siga siendo
  el editor de esa celda: lo es → escribe; no lo es (la perdió / es de otro) → **409** (la UI
  ya estaba en solo-lectura).
- **Claude (claim implícito, atómico):** su llamada incluye `participant_id="claude"` y NO
  pasa por `focus` previo. El endpoint hace **claim-y-escritura como una sola operación
  atómica** bajo el `RLock`: si la celda está libre la toma, fija su `focused_cell`, renueva su
  lease, escribe y difunde su badge; si está ocupada por otro → **409** sin escribir, y Claude
  lo reporta ("esa celda la tiene Carla, no la toqué"). El claim y la escritura comparten el
  lock → no hay forma de que otro se cuele entre medio.

En M1/M2 las escrituras **no** chequean lock (sin enforcement todavía); el `participant_id` y
el chequeo/claim atómico entran en M3.

## 7. Eventos de bajada de presencia/lock

```json
{"type": "presence", "session_id": "2026-04",
 "participants": [ {participant_id, name, color, kind, focused_cell, mode}, ... ]}
```

Se difunde el snapshot completo de presencia de la sesión ante cualquier cambio (join, focus,
leave, expiración). Para 2-3 participantes el snapshot completo es trivial y elimina el
problema de aplicar diffs incrementales fuera de orden. El frontend reemplaza su mapa de
presencia con el snapshot.

## 8. Claude como participante

- Identidad fija: `participant_id="claude"`, `name="Claude"`, color propio distinto del de los
  humanos, `kind="agent"`.
- **Por-celda-activa:** el badge aparece/bloquea solo la celda que Claude está tocando, y salta
  a medida que trabaja. El escaneo ya tiene esa forma (`cell_scanning`→`cell_done`); se
  formaliza atando la presencia de Claude a sus escrituras.
- **Respeta los locks como cualquiera.** Si la celda objetivo está tomada por otro, Claude
  recibe 409 y lo reporta; no piso a nadie.
- **Borde fino — el usuario tiene abierta la celda que le manda a Claude.** Default acordado:
  Claude avisa ("la tienes abierta, ciérrala o muévete y la ajusto"), el usuario la suelta,
  Claude la toma. Se prefiere la regla única (nadie pisa a nadie) sobre la comodidad de
  "prestar el lock", que metería una excepción al modelo. **Nota de implementación:** este
  borde se resuelve en el comportamiento conversacional de Claude (recibe el 409 y avisa), NO
  en la API. **No existe ni debe construirse un endpoint "ceder/prestar lock"** — por diseño.
  No es testeable mecánicamente; el test solo cubre que la escritura de Claude a una celda
  ocupada devuelve 409 sin escribir.

## 9. Frontera: estado efímero vs estado de documento

- **Documento** (conteos, notas, reorg, etc.) → SQLite (`state_json`). Como hoy.
- **Colaboración** (presencia, locks, leases) → **solo en memoria del proceso. Nunca** se
  escribe al blob.
- Un reinicio del backend borra los locks (todos reconectan) y deja los datos intactos. Esto
  mantiene `state_json` limpio y evita persistir un lock fantasma.

## 10. Escaneo masivo vs locks

- El escáner toma el lock **por celda, solo mientras la escanea** (el badge salta con él,
  `participant_id="claude"`). En el pase de nombres es un parpadeo de ~4 s en todo el mes; en
  el pase OCR cada celda queda tomada mientras dura su escaneo.
- **Dónde se chequea el lock (contrato):** el bucle del escaneo, **justo antes de mutar cada
  celda** (no al encolar), bajo el `RLock`: si esa celda está en `mode="editor"` por **otro**
  participante, el escáner **no la toca** y emite un evento de salto; si está libre, la toma
  (claim a nombre de `claude`), escribe y la suelta. Esto es adicional al clobber-guard
  `_cell_has_work` que ya existe (ese protege contra pisar OCR/ediciones; este protege contra
  pisar una **edición en vivo**).
- **Evento de salto (contrato):** por cada celda omitida, el escáner emite por WS
  `{"type": "cell_skipped", "hospital": ..., "sigla": ..., "reason": "locked",
  "lock_holder": {participant_id, name}}`. Al terminar, `scan_complete` incluye
  `"skipped": [{hospital, sigla}, ...]` para que la UI muestre el resumen ("N celdas omitidas
  porque estaban en edición") y permita re-escanearlas luego.
- El parpadeo del badge en el pase de nombres es cosmético; se puede atenuar con un debounce.

## 11. Despliegue y restricción de un-solo-proceso

- Un solo proceso uvicorn con `HOST=0.0.0.0` para exponer en LAN. **Cuidado (no basta):** el
  frontend hoy **hardcodea `127.0.0.1`** en tres lugares — `frontend/src/lib/ws.js` (L17,
  `ws://127.0.0.1:8000`), `frontend/src/lib/api.js` (L1, `http://127.0.0.1:8000/api`) y
  `frontend/src/lib/constants.js` (L1-2, `API_BASE`/`WS_BASE`). El navegador de Carla
  apuntaría a *su propio* localhost, no al servidor de Daniel. M1 DEBE derivar el host de
  `window.location.hostname` (o una env de build) y consolidar esas tres fuentes en una. Sin
  esto, `HOST=0.0.0.0` por sí solo no conecta a nadie en LAN. Ver §12 (M1).
- El `RLock`, el registro de participantes y el mapa `_CONNECTIONS` del WS viven en **ese**
  proceso. **Restricción dura: nunca `--workers N`** — con N procesos habría N copias aisladas
  (un claim del worker 1 es invisible para el worker 2; un WS del worker 3 no recibe el
  broadcast del worker 1) y multiplayer se rompería en silencio.
- No es una limitación que cueste algo real: es una herramienta interna/batch en LAN, sin el
  volumen que justificaría varios núcleos sirviendo HTTP. El trabajo pesado (OCR) ya se reparte
  a 6 subprocesos de Tesseract, mecanismo independiente.

## 12. Etapas de implementación

Estilo de la serie Incr: cada etapa entrega valor sola y de-riesga la siguiente. Un solo spec
(este); implementación por etapas, cada una con su plan. Se empieza por M1.

- **M1 — Fundación de sincronización.** Broadcast-on-write con snapshot completo (§4) + merge
  en vivo generalizado (reemplazo de celda entera, §3 ítem 2) + auto-sanación (re-fetch al
  reconectar/recuperar foco) + **exposición LAN real**: `HOST=0.0.0.0` **y** consolidar las
  tres fuentes de host hardcodeadas del frontend (`ws.js`/`api.js`/`constants.js`) para que
  deriven de `window.location.hostname` (§11). Sin presencia ni locks. Dos navegadores en
  **máquinas distintas de la LAN** ya ven en vivo lo que edita el otro. Aditivo, bajo riesgo,
  cimiento. Incluye el punto único de choque del broadcast (§4).
- **M2 — Presencia.** Identidad (nombre + color al entrar, `participant_id` en localStorage),
  registro de participantes + heartbeat + `focus`/`leave`, evento `presence`. UI: badge en la
  fila de categoría (espacio reservado en G4) mostrando quién está en cada celda + roster de
  conectados. Sin bloquear: se **ve** a Carla, pero nada frena. El badge de Claude cae casi
  gratis (el escaneo ya emite eventos).
- **M3 — Locks duros + enforcement + Claude.** `focus`=claim atómico bajo `RLock`,
  solo-lectura en celda ocupada (controles deshabilitados + badge del dueño), `participant_id`
  + chequeo de lock en los endpoints de escritura (409 si no se tiene), el escáner salta celdas
  en edición, auto-claim por-celda-activa de Claude. Capa con más bordes, ahora sobre una base
  probada.

## 13. Pruebas

- **Backend (sin mockear DB, fixtures reales):**
  - Registro de locks: grant/deny, vencimiento de lease, **claim atómico** (test de
    concurrencia: dos claims simultáneos a la misma celda → exactamente un grant).
  - Registro de presencia: join/focus/leave, cascada de expiración (vencer lease libera lock).
  - Punto único de broadcast: toda escritura de celda difunde `cell_updated`.
  - Escáner salta celdas bloqueadas por otro: emite `cell_skipped` (§10), NO muta la celda, y
    la incluye en `scan_complete.skipped`. Celda libre → la toma/escribe/suelta normal.
  - Lease con **reloj inyectable** para probar expiración determinísticamente.
- **Integración de 2 participantes sin navegador:** test que simula dos `participant_id`
  golpeando la API (heartbeat/focus/edit/release) + verifica los broadcasts y los 409. Cubre
  la lógica real de multiplayer sin depender del navegador.
- **Frontend (vitest):** merge de `cell_updated` y de `presence` en `_handleWSEvent`; gating de
  solo-lectura (celda ocupada deshabilita controles); heartbeat; identidad/localStorage.
- **Smoke visual de 2 navegadores: manual.** El MCP de chrome-devtools no alcanza a Brave
  (mismatch IPv6, ver memoria del proyecto); se cubre con lo de arriba + verificación en vivo
  con dos pestañas/equipos en LAN.

## 14. Riesgos

1. **Broadcast perdido → pantalla vieja.** → punto único de choque + auto-sanación al
   reconectar/recuperar foco (§4).
2. **Un-solo-proceso (no `--workers N`).** → documentado (§11), no cuesta nada real.
3. **Regresión del camino solo-usuario.** Criterio de aceptación duro: con un participante
   conectado, todo se comporta idéntico a hoy. M1/M2/M3 son aditivas; escaneo/edición/Excel/
   reorg/conteo intactos.
4. **Lock pegado.** → vencimiento de lease. Borde raro: un dueño que parpadeó vuelve a una
   celda ya re-tomada → su `focus` devuelve `{mode: "viewer", lock_holder}` (§6.2) y la UI
   muestra el aviso visible "perdiste la edición de esta celda" (no degrada en silencio).
5. **Parpadeo del badge en el escaneo rápido de nombres.** → cosmético; debounce opcional.

## 15. Registro de decisiones (del brainstorm)

- Modelo de trabajo: paralelo, sin repartir hospitales.
- Celda ocupada: **solo-lectura** para los demás (no bloqueo total de selección).
- Lock: **duro por celda**, atado al participante vía lease (no al socket del WS).
- claim/release/heartbeat: **HTTP** (no WS de 2 vías). WS solo de bajada.
- Claude: participante de primera clase, **por-celda-activa**, respeta todos los locks.
- Borde fino (el usuario tiene la celda que le manda a Claude): Claude avisa, el usuario suelta.
- Presencia/locks: **efímeros**, nunca persistidos.
- Despliegue: un solo proceso, `HOST=0.0.0.0`, nunca `--workers N`.
- Entrega: un spec, implementación por etapas M1→M2→M3.
