# Conteo asistido de trabajadores — Documento de diseño

**Fecha:** 2026-05-16
**Rama:** `po_overhaul`
**Predecesor:** FASE 5 (slice UX — drill-in histórico, cancelación a nivel de página, auto-retry OCR)
**Estado:** diseño validado en brainstorming; pendiente del plan de implementación

> Mockups validados durante el brainstorming:
> `docs/research/2026-05-16-mockup-visor-conteo.html` (pantalla del visor) y
> `docs/research/2026-05-16-mockup-burbuja-microfono.html` (estados de la burbuja
> y del micrófono).

---

## 1. Contexto y problema

PDFoverseer cuenta documentos internos por celda (hospital × sigla) para la grilla
de 72 casillas del Excel mensual. Pero el Excel tiene, además, dos cifras por
hospital que hoy nadie llena de forma asistida: la **cantidad de trabajadores** que
firmaron en las charlas (`charla`) y en la charla integral (`chintegral`). Esas
cifras alimentan las columnas de **HH de capacitación** mediante fórmulas ya
embebidas en el template.

Contar trabajadores firmantes es un problema distinto al de contar documentos:

- Cada PDF de charla es una o varias planillas de asistencia con una tabla de firmas.
- Un mismo PDF tiene varias páginas, y una tabla de firmas puede continuar de una
  página a la siguiente.
- La cantidad de firmas por página es variable y la calidad del escaneo, irregular.

**La automatización ya se intentó y no resultó.** El proyecto CWcounter y los
intentos con visión por IA no alcanzaron certeza suficiente: las tablas de firma
son demasiado heterogéneas. La conclusión es deliberada: este feature **no
automatiza el conteo — lo asiste.** Una persona pasa las páginas y declara el
número; la herramienta hace que ese trabajo sea rápido, ordenado y que el resultado
caiga solo en el Excel.

## 2. Objetivos y no-objetivos

**Objetivos**

- Un visor donde el usuario recorre todos los PDFs de una celda charla/chintegral
  como una sola sesión continua y registra, por página, cuántos trabajadores firmaron.
- Entrada por **voz** (dictar el número) como vía rápida, y por **teclado** como vía
  sólida de respaldo.
- El conteo se **conserva**: se puede pausar y retomar; nada se pierde.
- El total por celda **cae en cascada** al Excel mensual, a los rangos de
  trabajadores que ya existen en el template, y de ahí a las columnas de HH.
- Corregir dos fórmulas erradas del template que hacen que el HH de charla integral
  se calcule mal.

**No-objetivos**

- No se detecta ni cuenta nada automáticamente. El número siempre lo declara la persona.
- No se hace OCR de las tablas de firma.
- No se toca el conteo de documentos de la grilla de 72 — el conteo de trabajadores
  es una cifra **paralela e independiente** sobre la misma celda.
- El marcado visual de "primera página de documento" (feature 2) queda fuera; se
  diseñará por separado.

## 3. Panorama de la arquitectura

```
HospitalDetail
  └─ celda charla / chintegral  ──[ "Contar trabajadores" ]──┐
                                                              ▼
                                          Visor pdf.js · modo count_workers
                                          (todos los PDFs de la celda como
                                           una sola sesión continua de PgDn)
                                                              │
                            paginado + burbuja + voz/teclado  │
                                                              ▼
                                      marcas (archivo, página, número)
                                      en Zustand → autosave con debounce
                                                              │
                              PATCH /sessions/{id}/cells/.../worker-count
                                                              ▼
                                  blob de sesión · cells[hosp][sigla]
                                  (worker_marks, worker_status, worker_cursor)
                                                              │
                                    POST /sessions/{id}/output │
                                                              ▼
                       emite {HOSP}_workers_chgen / _chintegral
                       → generate_resumen rellena los rangos con nombre
                       → las fórmulas de HH se autocalculan
```

El conteo de trabajadores reutiliza tres mecanismos que ya existen: el blob de
sesión, el autosave con debounce (FASE 3) y el escritor genérico de Excel. Lo
genuinamente nuevo es el visor pdf.js y la interacción de conteo.

## 4. El visor de conteo

### 4.1 pdf.js reemplaza el iframe

El visor actual (`frontend/src/components/PDFLightbox.jsx`) es un `<iframe>` que
delega en el visor del navegador. Es opaco: no se puede dibujar nada encima — ni la
burbuja, ni el HUD. Se reemplaza por un visor basado en **`pdfjs-dist`**, que
renderiza cada página a un `<canvas>` que sí controlamos. `react-zoom-pan-pinch`
(ya es dependencia) envuelve el canvas para el desplazamiento y el zoom.

El visor sigue sirviendo el uso actual de "inspección" (clic en un archivo de
`FileList`) — eso pasa a ser el modo `inspect`.

### 4.2 Modos del visor

El estado `lightbox` de Zustand gana un campo `mode`:

- **`inspect`** — comportamiento actual: un PDF, desplazamiento y zoom, solo lectura.
- **`count_workers`** — este feature.
- **`boundaries`** — reservado para el feature 2; no se construye ahora.

### 4.3 Sesión continua multi-PDF

En `count_workers`, el visor carga **todos** los PDFs de la celda (ordenados como en
`cell.per_file`) y los trata como un solo flujo de PgDn: al pasar la última página
del archivo K se avanza a la página 1 del archivo K+1. De ahí salen los indicadores
"archivo 3 / 7" y "página 5 / 12" del HUD. Cada PDF se obtiene con el endpoint que
ya existe: `GET /sessions/{id}/cells/{hosp}/{sigla}/pdf?index=N`.

### 4.4 Punto de entrada y estado de la celda

En `HospitalDetail`, las celdas `charla` y `chintegral` (y solo esas) ganan una
acción **"Contar trabajadores"**. Al iniciarse, la celda muestra además el total de
trabajadores y un chip de estado:

- Sin iniciar → botón "Contar trabajadores".
- `en_progreso` → total parcial + chip ámbar "en progreso" + botón "Continuar conteo".
- `terminado` → total + chip jade "terminado" + botón "Revisar".

El chip de estado reutiliza el primitive `Badge` con los tonos ya definidos
(`amber` / `jade`), coherente con el resto de la UI.

## 5. La interacción de conteo

El layout completo del visor está en el mockup `2026-05-16-mockup-visor-conteo.html`;
los estados de la burbuja y del micrófono, en `2026-05-16-mockup-burbuja-microfono.html`.

### 5.1 Marcas y la burbuja

Una **marca** es la terna `(archivo, página, número)`. La **burbuja** flota en el
borde derecho-medio de la página y tiene tres estados:

- **Vacía** — la página no tiene marca; anillo punteado gris.
- **Pendiente** — se dictó/tecleó un número que aún no se guarda; anillo punteado
  índigo con el número. Se puede corregir.
- **Fijada** — la marca quedó guardada; círculo sólido índigo.

`PgDn` confirma la marca pendiente (pendiente → fijada) y avanza. La metáfora
punteado → sólido (borrador → confirmado) evita gastar un tercer color y no se
confunde con el ámbar que el proyecto ya usa para "sospechoso".

`PgDn` **sin** número dictado simplemente avanza: no deja marca y no dibuja burbuja.
La ausencia de marca **equivale a 0** en la suma; no se guarda un cero explícito.

La burbuja se puede arrastrar si tapa contenido de la página. Esa posición **no se
persiste** — vuelve a su lugar por defecto en cada sesión; es una comodidad, no un dato.

**Tablas que cruzan páginas.** §1 anota que una tabla de firmas puede continuar de
una página a la siguiente. Para el conteo no hace falta tratamiento especial: cada
página recibe la cantidad de firmas que la persona ve en ella, y la suma de las
marcas da el total correcto sin importar cuántas páginas abarque la tabla. Si una
misma fila de firma queda partida por el corte de página, la persona cuenta a ese
trabajador una sola vez, en la página que decida — es un juicio humano que la
herramienta no asiste.

### 5.2 Entrada por voz

Se usa el **Web Speech API** (`SpeechRecognition`) en modo continuo, con locale
español. Mientras el modo de conteo está activo y el micrófono no está en pausa, el
visor escucha. Al reconocer un número, ese número entra en la burbuja como
**pendiente**. Volver a dictar reemplaza lo pendiente.

Un **parser de números en español** (`frontend/src/lib/spanish-numbers.js`) convierte
la transcripción ("veintitrés", "cuarenta y uno", "ciento cinco") en un entero.

El micrófono es **always-on** mientras se cuenta — sin push-to-talk — porque
mantener una tecla apretada por página es justo la fricción que este feature existe
para eliminar. Se puede **pausar** (clic en el chip del micrófono, o tecla `M`); en
pausa el reconocedor se detiene de verdad, no solo se ignora, así que conversar con
alguien no genera marcas falsas.

> **Riesgo principal.** El Web Speech API depende de un endpoint en la nube y algunos
> navegadores (Brave entre ellos) lo deshabilitan por defecto. Se valida temprano —
> ver §12. El teclado es la vía de respaldo y funciona sin red.

### 5.3 Entrada por teclado

Teclear un número hace exactamente lo mismo que dictarlo: la burbuja queda pendiente
y `PgDn` la fija. `E` entra a una edición explícita de la página actual. Esta vía no
tiene ninguna dependencia externa: es el respaldo sólido.

### 5.4 Atajos de teclado

| Tecla | Acción |
|-------|--------|
| `PgDn` | Fija la marca pendiente y avanza |
| `PgUp` | Retrocede |
| `Supr` | Borra la marca de la página actual |
| `E` | Edita el número a mano |
| `M` | Pausa / reanuda el micrófono |

## 6. Modelo de datos

### 6.1 Marcas en el blob de sesión

La sesión es **un único blob JSON** (`sessions.state_json`), con la forma
`cells[hospital][sigla]`. No hay tabla por celda. Por eso los datos de conteo son
**campos nuevos en el objeto de celda**, presentes solo en `charla` y `chintegral`:

```jsonc
// cells["HLL"]["charla"]
{
  // ... campos existentes: filename_count, ocr_count, user_override, per_file, ...
  "worker_marks": {
    "charla_01.pdf": [{ "page": 2, "count": 18 }, { "page": 4, "count": 20 }],
    "charla_03.pdf": [{ "page": 3, "count": 16 }, { "page": 5, "count": 11 }]
  },
  "worker_status": "en_progreso",        // "en_progreso" | "terminado" | ausente
  "worker_cursor": { "file": 2, "page": 5 }  // última posición, para retomar
}
```

`worker_marks` está indexado por nombre de archivo, igual que el `per_file` que ya
existe. El total de trabajadores de la celda **es derivado** (suma de todos los
`count`) — no se almacena, así no hay riesgo de desincronización.

### 6.2 Persistencia

Reutiliza el mecanismo existente. Se agrega un endpoint
`PATCH /sessions/{id}/cells/{hosp}/{sigla}/worker-count` que mezcla
`{ worker_marks?, worker_status?, worker_cursor? }` en el objeto de celda —
en espejo de `apply_user_override` (`api/state.py`). El frontend mantiene las marcas
en Zustand y las **autosalva con debounce**, igual que el patrón de autosave de FASE 3.

### 6.3 Totales derivados

- **Subtotal de archivo** = suma de los `count` de las marcas de ese archivo.
- **Total de celda** = suma de los subtotales de los archivos **presentes hoy en la
  lista de la celda**.

Se calculan en el frontend para el HUD y la UI de celda, y en el backend al momento
de exportar. La lógica es una suma trivial; no amerita un fixture espejado.

`worker_marks` está indexado por nombre de archivo. Si un PDF se renombra o se quita
entre sesiones, sus marcas quedan huérfanas; el total **solo suma los archivos que
hoy están en la celda** (intersección con `per_file`), así que una marca huérfana no
infla el resultado. El plan puede además podar las huérfanas al cargar la sesión.

## 7. Ciclo de vida del conteo

### 7.1 Suma en vivo y autosave

El total se actualiza a medida que se marca. Las marcas se autosalvan con debounce;
aplica el indicador visible de autosave de FASE 3 (guardando / guardado / error).

### 7.2 Pausar y retomar

El visor se puede cerrar a mitad del conteo. `worker_marks`, `worker_status` y
`worker_cursor` quedan persistidos. Volver a entrar por "Continuar conteo" reabre el
visor en `worker_cursor` — exactamente donde se dejó.

### 7.3 "Terminé" y aviso al exportar

El visor tiene una acción **"Terminé esta categoría"** que fija
`worker_status = "terminado"`. Una celda terminada se puede reabrir y editar después.

Al exportar (`POST /output`), si alguna celda `charla`/`chintegral` está
`en_progreso` o sin iniciar, la respuesta incluye un campo **nuevo**,
`worker_warnings`, que lista esas celdas. Es **distinto** del campo `warnings` que la
respuesta ya devuelve hoy (`output.py:115`, diagnósticos del escritor de Excel —
p. ej. un rango con nombre no encontrado): no se mezclan. `warnings` es diagnóstico
interno del escritor; `worker_warnings` es un aviso de completitud para el usuario.
La exportación **igual procede** — el aviso es informativo. El frontend lo muestra
como toast/diálogo.

## 8. Cascada al Excel

### 8.1 Emisión de los rangos de trabajadores

Hoy `_build_cell_values` (`api/routes/output.py`) emite `{hosp}_{sigla}_count` para
la grilla de 72. Se agrega la emisión de trabajadores: para cada hospital y para
`sigla ∈ {charla, chintegral}`, si la celda tiene datos de conteo, se emite la clave
`{HOSP}_workers_{purpose}` con el total, donde:

```
purpose = "chgen"      si sigla == "charla"
purpose = "chintegral" si sigla == "chintegral"
```

El mapeo `charla → chgen` es **obligatorio**: los rangos de trabajadores del Excel
usan `chgen` ("charlas generales diarias"), no `charla`. Es una divergencia conocida
de nomenclatura entre la sigla del sistema y la clave del rango del template.

`generate_resumen` (`core/excel/writer.py`) ya resuelve cualquier clave → defined
name → celda. Los 8 rangos `{HOSP}_workers_{purpose}` ya existen en el template y
resuelven a las columnas de HH, filas 29 (`chgen`) y 30 (`chintegral`) — p. ej.
`HLL_workers_chgen → H29`, `HPV_workers_chintegral → N30` (verificado con openpyxl).
Emitir la clave rellena la celda sin tocar el escritor. **No se modifica el escritor
de Excel** — solo se agrega la emisión.

Si una celda de trabajadores nunca se contó, no se emite su clave: el template (ya
limpio — ver §8.2) conserva su celda en blanco, y el `worker_warnings` de §7.3 lo
señala. Una celda con algún PDF que no se pudo abrir (§10) también queda incompleta:
se incluye en `worker_warnings` aunque su estado sea `terminado`.

### 8.2 Corrección de la fórmula del template

El template `data/templates/RESUMEN_template_v1.xlsx` se construye con el script
`data/templates/build_template_v1.py`, que **copia** la planilla base
`data/output_sample/RESUMEN_ABRIL_2026.xlsx` (`shutil.copy`) y luego le agrega los
rangos con nombre y vacía las celdas de cantidad. **El script no genera las fórmulas
de HH** — las hereda tal cual de la planilla copiada. Por eso cualquier corrección de
fórmula debe ser un **paso nuevo y explícito** dentro de `build()`, posterior a la copia.

Las filas de HH de charla y charla integral (columnas de HH: H, J, L, N):

- Fila 29 = trabajadores `chgen`; fila 30 = trabajadores `chintegral`.
- Fila 13 = HH de chgen = `trabajadores_chgen (fila 29) × 0.25`.
- Fila 14 = HH de chintegral = `trabajadores_chintegral (fila 30) × 0.5`.

**Una sola fórmula está errada**, verificado con openpyxl sobre el template actual:

| Celda | Fórmula actual | Debe ser | Problema |
|-------|----------------|----------|----------|
| `H14` | `=H29*0.5` | `=H30*0.5` | Apunta a la fila de chgen (29), no a la de chintegral (30) |

`J14` (`=J30*0.5`), `L14` (`=L30*0.5`) y `N14` (`=N30*0.5`) **ya están correctas** —
solo `H14` cambia.

Aparte, las 8 celdas de trabajadores (columnas H/J/L/N, filas 29 y 30) arrastran
**valores obsoletos de ABRIL** pegados en la planilla base: `J29=479`, `L29=5255`,
`N29=4851`, `J30=123`, `L30=373`, `N30=784` (`H29` y `H30` ya están en blanco). El
script **no las limpia hoy**: `build()` solo vacía las columnas de cantidad
(G/I/K/M) y `verify()` solo comprueba esas. Un template limpio debe traer esas 8
celdas en blanco.

El cambio en `build_template_v1.py` es entonces un paso nuevo en `build()` que
(1) reescribe `H14` a `=H30*0.5` y (2) vacía las 8 celdas de trabajadores. Se
extiende `verify()` para afirmar ambas cosas. Luego se regenera el template y se
hace un **diff de verificación**: respecto del template actual, solo deben cambiar
`H14` y los 6 valores obsoletos que se vacían.

> *Deuda aparte, fuera de alcance:* existe otro bug de fórmula, `L12 = =K11*0.25`
> (debería ser `=K12*0.25` — columna correcta, fila equivocada). `L12` es el HH de la
> fila `odi` (fila 12), no de charla. No afecta el conteo de trabajadores y se revisa
> por separado.

## 9. Cambios por capa

**Backend**

| Archivo | Cambio |
|---------|--------|
| `core/db/sessions_repo.py` | Sin cambios de schema — los campos nuevos viven en el blob |
| `api/state.py` | `apply_worker_count()`, en espejo de `apply_user_override` |
| `api/routes/sessions.py` | Endpoint `PATCH .../worker-count` |
| `api/routes/output.py` | Emisión de `{HOSP}_workers_{purpose}`; campo `warnings` en la respuesta |
| `core/excel/writer.py`, `core/excel/template.py` | Sin cambios — las claves nuevas fluyen por `generate_resumen` |
| `data/templates/build_template_v1.py` | Paso nuevo en `build()`: reescribir `H14` a `=H30*0.5`, vaciar las 8 celdas de trabajadores (filas 29/30); extender `verify()`; regenerar |

**Frontend**

| Archivo | Cambio |
|---------|--------|
| `frontend/package.json` | Agregar `pdfjs-dist` |
| `frontend/src/components/PDFLightbox.jsx` | Reemplazar el `<iframe>` por el render de pdf.js; soportar `mode` |
| *(nuevos)* componentes del visor de conteo | HUD, burbuja, lista de marcas (decomposición exacta = nivel de plan) |
| *(nuevo)* `frontend/src/lib/spanish-numbers.js` | Parser de números dictados en español |
| *(nuevo)* hook de voz | Envuelve `SpeechRecognition`; aísla la dependencia de voz |
| `frontend/src/store/session.js` | `mode` en `lightbox`; estado y acciones de marcas; `openWorkerCount(hosp, sigla)` |
| `frontend/src/lib/api.js` | Llamada al nuevo `PATCH worker-count` |
| `HospitalDetail` / componente de celda | CTA "Contar trabajadores" + total + chip de estado en celdas charla/chintegral |

## 10. Manejo de errores

- **Web Speech API no disponible o sin permiso de micrófono** → el visor sigue
  funcionando solo con teclado; se avisa una vez, no se bloquea el conteo.
- **Reconocimiento sin número** (ruido, palabra no numérica) → se ignora; la burbuja
  no cambia.
- **PDF que no carga en pdf.js** → mensaje claro; el archivo se puede saltar y se
  refleja en el HUD; la celda queda incompleta y aparece en `worker_warnings` (§7.3).
- **Autosave que falla** (red) → indicador de error de FASE 3; las marcas quedan en
  memoria y se reintenta.

## 11. Estrategia de pruebas

Siguiendo las convenciones del proyecto: fixtures reales, sin mockear la base de datos.

- **Parser de números en español** — pruebas unitarias exhaustivas: dígitos sueltos,
  decenas ("veintitrés"), centenas ("ciento cinco"), conjunciones ("cuarenta y uno"),
  límites (0, 999) y entradas no numéricas → resultado nulo.
- **Persistencia de `worker_marks`** — agregar y borrar marcas, retomar desde el
  cursor, el total derivado.
- **Cascada** — un fixture de sesión con conteos de trabajadores → `POST /output` →
  verificar que `{HOSP}_workers_{purpose}` cae en el rango con nombre correcto y que
  las fórmulas de HH dan el resultado esperado.
- **Fórmulas del template** — una prueba que verifica que `H14/J14/L14/N14` apuntan a
  la fila 30, que la fila 13 apunta a la 29, y que las 8 celdas de trabajadores
  (H/J/L/N × filas 29/30) quedan en blanco tras regenerar.
- **El visor** — smoke vía chrome-devtools: paginado continuo, burbuja
  pendiente → fijada, `Supr`, `M`, pausar y retomar.

La voz en sí no es testeable por unidad (es una API del navegador); su parte
testeable es el parser.

## 12. Riesgos y validaciones tempranas

- **Web Speech API en el navegador objetivo — riesgo principal.** Brave puede tener
  deshabilitado el endpoint de voz de Google. **Validación temprana:** un spike corto
  — ¿`SpeechRecognition` reconoce números dictados en Brave? Si no: (a) contar en
  Chrome, o (b) usar una STT en la nube por API. La arquitectura aísla la voz detrás
  de un hook, así que cambiar el motor es un cambio contenido. El teclado funciona
  pase lo que pase. Conviene hacer este spike **antes** de construir la capa de voz.
- **Regenerar el template** — riesgo de perder contenido si el template se editó a
  mano después de generarse. Mitigación: el diff de verificación de §8.2 — solo
  `H14`/`N14` (y los valores ABRIL que se limpian) deben cambiar.
- **Tamaño del blob de sesión** — cientos de marcas engordan el JSON. Para un solo
  usuario y un blob de pocos KB es irrelevante; el autosave con debounce evita una
  escritura por tecla.

## 13. Fuera de alcance

- Feature 2 (badges de "primera página de documento" en el visor) — diseño aparte.
- Cualquier detección automática de tablas de firma o de conteo.
- El bug `L12` del template (HH de la fila `odi` —fila 12— con `=K11*0.25` en vez de
  `=K12*0.25`) — anotado como deuda; no afecta a los trabajadores.

## 14. Secuencia de construcción

El plan detalla las tareas; este es el orden grueso:

1. **Backend — modelo de datos de trabajadores**: campos en la celda, endpoint
   `PATCH worker-count`, persistencia.
2. **Backend — cascada y template**: emisión de `{HOSP}_workers_{purpose}`,
   corrección de `H14` + limpieza de las 8 celdas de trabajadores + regeneración del
   template, aviso de exportación.
3. **Spike de voz**: validar el Web Speech API en el navegador objetivo (§12).
4. **Frontend — visor pdf.js**: reemplazar el iframe, con paridad del modo `inspect`.
5. **Frontend — modo `count_workers`**: paginado continuo, burbuja, marcas, teclado,
   atajos.
6. **Frontend — voz**: hook de `SpeechRecognition` + parser de números en español.
7. **Frontend — punto de entrada y UI de celda**: CTA, total, chip de estado, "Terminé".
8. **Integración + smoke.**
