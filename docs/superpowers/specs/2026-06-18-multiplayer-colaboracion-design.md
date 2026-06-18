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
   caso `cell_done` ~L649) ya aplica el snapshot de una celda empujado por el servidor al
   estado local de Zustand. `frontend/src/lib/ws.js` ya tiene cliente WS con reconexión +
   backoff. Se **generaliza** ese merge a cualquier celda.
3. **Escrituras serializadas y seguras entre clientes.** `api/state.py` (`_synchronized` +
   `RLock`): cada setter hace *load → modifica solo su celda → reescribe el blob*. Dos
   escrituras a **celdas distintas** ya son seguras hoy. El único riesgo es pisar la misma
   celda — y eso lo elimina el lock duro (§6).

## 4. Modelo de sincronización (server-autoritativo, broadcast-on-write)

El servidor sigue siendo la única fuente de verdad (blob en SQLite). Tras **cada escritura
commiteada** de una celda, el servidor difunde `cell_updated` con el snapshot de esa celda;
el frontend lo mergea al estado local.

- **Punto único de choque.** El broadcast NO se rocía por los ~12 setters de `state.py`. Se
  centraliza (un wrapper/capa fina alrededor del commit de estado, o en una capa de servicio
  por encima de las rutas) para que ningún setter pueda "olvidar" difundir. Decisión de plan:
  el punto exacto se fija en M1.
- **Evento (contrato).**
  ```json
  {"type": "cell_updated",
   "hospital": "HRB", "sigla": "odi",
   "actor": "<participant_id>",
   "cell": { /* snapshot de la celda, mismo shape que GET /sessions/{id} */ }}
  ```
  `actor` permite al cliente distinguir su propio cambio (ya aplicado localmente) de uno
  remoto, y evitar parpadeos.
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

### 6.2 Endpoints HTTP

- `POST /api/sessions/{id}/presence/heartbeat` — body `{participant_id, name, color}`.
  Renueva el lease (lo crea si es nuevo = "join"). Periódico (~15 s) desde el navegador.
  Devuelve el snapshot de presencia actual.
- `POST /api/sessions/{id}/presence/focus` — body `{participant_id, cell: "H|sigla" | null}`.
  **Focus = claim.** Suelta la celda anterior del participante; si `cell` no es null, intenta
  tomarla como editor (atómico): devuelve `{mode: "editor"}` si quedó libre, o
  `{mode: "viewer", lock_holder: {participant_id, name, color, kind}}` si estaba ocupada.
  `cell=null` = volver a vista mes/hospital (suelta sin tomar nada).
- `POST /api/sessions/{id}/presence/leave` — body `{participant_id}`. Quita al participante
  (best-effort al cerrar pestaña vía `navigator.sendBeacon`; el vencimiento del lease es el
  respaldo).

### 6.3 Liveness

- **Humano:** el navegador manda `heartbeat` cada ~15 s. Vencimiento ~45 s. Al cerrar limpio
  → `leave` inmediato; si el equipo se cae/suspende → vence en ≤45 s.
- **Claude:** NO manda heartbeat. Cada llamada HTTP suya que escribe una celda renueva su
  lease y fija su `focused_cell` a esa celda (presencia "por-celda-activa" automática). Deja
  de trabajar → su lease vence. Sin navegador, sin WS, sin lock pegado.

### 6.4 Enforcement (M3)

Los endpoints que **escriben** una celda reciben `participant_id` y verifican el lock:
- Humano: el navegador hizo `focus`(claim) antes de editar → tiene el lock → escritura
  permitida. Si no lo tiene (celda de otro) → **409** y la UI ya estaba en solo-lectura.
- Claude: su llamada incluye `participant_id="claude"`. El endpoint intenta el claim a su
  nombre: libre → toma + escribe + difunde su badge; ocupada por otro → **409** y Claude lo
  reporta al usuario ("esa celda la tiene Carla, no la toqué").

En M1/M2 las escrituras **no** chequean lock (sin enforcement todavía).

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
  "prestar el lock", que metería una excepción al modelo.

## 9. Frontera: estado efímero vs estado de documento

- **Documento** (conteos, notas, reorg, etc.) → SQLite (`state_json`). Como hoy.
- **Colaboración** (presencia, locks, leases) → **solo en memoria del proceso. Nunca** se
  escribe al blob.
- Un reinicio del backend borra los locks (todos reconectan) y deja los datos intactos. Esto
  mantiene `state_json` limpio y evita persistir un lock fantasma.

## 10. Escaneo masivo vs locks

- El escáner toma el lock **por celda, solo mientras la escanea** (el badge salta con él). En
  el pase de nombres es un parpadeo de ~4 s en todo el mes; en el pase OCR cada celda queda
  tomada mientras dura su escaneo.
- Si el escáner llega a una celda que **otro tiene en edición**, la **salta** y lo reporta
  ("N celdas omitidas porque estaban en edición"), en vez de pisarla. Esto es adicional al
  clobber-guard `_cell_has_work` que ya existe.
- El parpadeo del badge en el pase de nombres es cosmético; se puede atenuar con un debounce.

## 11. Despliegue y restricción de un-solo-proceso

- Un solo proceso uvicorn con `HOST=0.0.0.0` para exponer en LAN.
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

- **M1 — Fundación de sincronización.** Broadcast-on-write + merge en vivo generalizado +
  auto-sanación (re-fetch al reconectar/recuperar foco) + `HOST=0.0.0.0`. Sin presencia ni
  locks. Dos navegadores ya ven en vivo lo que edita el otro. Aditivo, bajo riesgo, cimiento.
  Incluye el punto único de choque del broadcast.
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
  - Escáner salta celdas bloqueadas por otro.
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
   celda ya re-tomada → cae a solo-lectura con aviso "perdiste la edición de esta celda".
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
