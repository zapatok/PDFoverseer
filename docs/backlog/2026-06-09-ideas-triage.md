# PDFoverseer — Triage de ideas (backlog de trabajo)

**Fecha:** 2026-06-09
**Estado:** BORRADOR para revisión — ninguna idea está aprobada ni implementada.
**Origen:** dos volcados de notas crudas de Daniel (ventana de prueba EN VIVO con MAYO).
**Propósito:** pulir, deduplicar y clasificar las ideas antes de discutirlas y llevarlas a algo real.
**Importante:** los ítems marcados *(verificar)* son reportes que hay que reproducir contra
el código actual antes de tratarlos como bug confirmado.

**Leyenda**
- Prioridad: 🔴 ahora (muerde con MAYO en vivo) · 🟡 pronto · 🟢 después · ⚪ algún día
- Complejidad: **S** trivial · **M** media · **L** grande
- Capa: BE backend · FE frontend · ambas

---

## Hallazgos transversales (leer primero)

Tres ideas-fuerza de las que cuelgan muchas notas. Conviene decidirlas como modelo, no caso por caso.

1. **Máquina de estados de la celda + procedencia del número.** ¿Cuándo una celda está
   "lista" (punto verde)? ¿Qué procedencia tiene cada número (R1 / OCR / manual / mezcla)?
   ¿Quién puede pisar a quién? De esto cuelgan los grupos **A** (integridad), **C** (overrides
   celda↔archivos) y **L** (gate / multiusuario). Definirlo una vez resuelve ~10 notas.

2. **Eje doc-counting vs worker-counting.** Algunas siglas cuentan **documentos**; otras
   (`maquinaria`, y el caso especial de `dif_pts`/HH-capacitación) cuentan **trabajadores**.
   El visor del contador de trabajadores (Feature 1) deja de ser exclusivo de firmantes y se
   vuelve herramienta general (grupo **F**). Esto amplía el modelo "dos regímenes"
   (trivial vs compilación) con un tercer tipo de celda.

3. **Ratio páginas/documento por sigla.** El tratamiento "R1 = páginas = documentos" asume
   ratio 1:1. Pero `charla` = 2 hojas/doc, y `andamios`/`maquinaria` no calzaron. El concepto
   R1 necesita un **ratio configurable por sigla**, no un 1:1 fijo (grupo **B** + ítem N2).

---

## A · Integridad del conteo — semántica de "listo" y reglas "no pisar" 🔴
> El núcleo. Correctness pura; es la familia del incidente de clobber del 2026-06-05.

| ID | Idea pulida | Prio | Compl | Capa |
|----|-------------|:----:|:-----:|:----:|
| A1 | No marcar la celda como "lista" automáticamente si tiene documentos pendientes/por revisar — salvo que se haya editado el número a mano en el detalle. | 🔴 | M | ambas |
| A2 | Escanear una celda con OCR **no enciende el punto verde** en la lista de categorías. Solo encienden: todo-R1, todo-manual, o mezcla R1+manual (por la incertidumbre del OCR). | 🔴 | M | ambas |
| A3 | OCR **no pisa** conteos manuales, ni R1, ni OCR anteriores. *(verificar — debería estar cubierto por el guard `_cell_has_work`; si "ocr pisa a R1" sigue pasando, hay un camino sin tapar)* | 🔴 | M | ambas |
| A4 | Impedir/avisar conteo de documentos **mayor que las páginas** del PDF; bloquear negativos; confirmar el 0 explícito. | 🔴 | S | ambas |

**Relación:** guard `_cell_has_work` (shipeado), incidente clobber 2026-06-05, gate del grupo **L**.

---

## B · Calibración OCR / clasificación de régimen (datos de MAYO) 🔴
> Hallazgos de la prueba en vivo. Alimentan "refinar OCR per-sigla" del roadmap.

| ID | Hallazgo pulido | Prio | Compl | Capa |
|----|-----------------|:----:|:-----:|:----:|
| B1 | `charla` HRB MAYO (`2026-06-05_charla_crs.pdf`, 324 págs): **2 hojas por documento** → real 162, OCR dio 110. El ratio 2:1 es el dato clave. | 🔴 | M | BE |
| B2 | `chintegral`: el escáner pierde documentos de **buena calidad** en HPV abril. | 🔴 | M | BE |
| B3 | `dif_pts`: OCR no detecta cantidad en **ninguna pasada**. (Usa el motor de **anclas de banda**, no V4 — ver pregunta Q3.) | 🔴 | M | BE |
| B4 | `andamios` HRB: **dos tipos mezclados** en la celda → corroborar las anclas. | 🟡 | M | BE |
| B5 | `odi` HRB: **perfecto** ✓ — fijar como baseline de regresión, no tocar. | — | — | — |
| B6 | `andamios` (y `maquinaria`): el tratamiento R1 "páginas = documentos" no se aplicó (quedó 1 pág = 1 doc). *(Ojo: `maquinaria` en realidad es worker-counting — ver B7/F3. `andamios` sí necesita ratio.)* | 🟡 | M | BE |
| B7 | **Reclasificación (corregida 2026-06-09):** `maquinaria` NO cuenta documentos — cuenta **chequeos = columnas de fecha marcadas** (un formulario trae ~5 columnas FECHA con SI/NO/NA; se cuentan las llenas). NO es worker-counting; es su propio tipo (check-counting) y es el conteo PRINCIPAL de la celda → puede superar las páginas. Candidato ideal para el contador por teclado (grupo F/K). | 🔴 | M | ambas |

**Relación:** follow-ups de `ocr_per_sigla_shipped` (V4 errors, scans degradados), hallazgo transversal #3 (ratio), grupo **F** (worker-counting).

---

## C · Modelo de overrides: celda ↔ archivos 🔴/🟡
> La tensión central de "¿quién manda, el número de la celda o la suma de los archivos?".

| ID | Idea pulida | Prio | Compl | Capa |
|----|-------------|:----:|:-----:|:----:|
| C1 | **BUG:** ajustar un archivo (o varios) a mano en el visor / lista no se refleja en el "ajuste manual" del detalle (sigue diciendo "ajuste manual 1"). *(verificar)* | 🔴 | M | ambas |
| C2 | Hoy, ajustar el conteo de la celda en el detalle **tapa** el conteo de los archivos (manual/OCR/R1/mezcla) sin forma de volver. Propuesta de Daniel: al modificar el conteo de un archivo, la app avisa que la celda está en modo manual y pregunta si quiere **volver a contar los archivos** (sí → trae el conteo de la columna archivos; no → mantiene el manual). *(abierto a ideas)* | 🔴 | M | ambas |
| C3 | El ajuste manual **prevalece** sobre el conteo por badge, pero con opción de volver al badge. *(enlaza con Feature 2, grupo K)* | 🟢 | M | ambas |

**Relación:** unificación en `computeCellCount` (ya shipeada), hallazgo transversal #1.

---

## D · Ajuste manual — UX de entrada 🟡 (FE)

| ID | Idea pulida | Prio | Compl |
|----|-------------|:----:|:-----:|
| D1 | Click en el número del ajuste manual lo deja **seleccionado al instante** para sobrescribir. | 🟡 | S |
| D2 | Flechas +/- para subir/bajar el conteo **en vivo**, separadas de los números, siempre visibles y bien presentadas. | 🟡 | S |
| D3 | Estando en el visor de un archivo, **tipear el número directo + Enter** (sin mover el mouse al ajuste manual cada vez). | 🟡 | M |
| D4 | Si se arregla la celda completa a mano, mostrar los chips de archivo en un "manual" de **otro color**. *(tentativo)* | 🟢 | S |

**Relación:** D3 + grupo F (contador por teclado), hallazgo transversal #2.

---

## E · Lista de archivos (columna archivos) — UX 🟡 (FE)

| ID | Idea pulida | Prio | Compl |
|----|-------------|:----:|:-----:|
| E1 | **BUG:** ajustar desde la columna archivos te regresa al inicio de la lista; debe **mantener la posición** en el archivo donde ajustaste. *(verificar)* | 🟡 | S |
| E2 | **Filtrar por chip** en la lista de archivos; agregar una barra entre el buscador y la lista. | 🟡 | M |
| E3 | Color que indique cuándo el nº de documentos de un archivo **difiere** del nº de páginas o es **igual**, en la columna archivos. | 🟡 | S |

**Relación:** E3 se apoya en la misma data que A4 (docs vs páginas) y el concepto R1.

---

## F · Conteo de trabajadores (Feature 1) — bugs y extensión 🔴/🟡
> El visor de trabajadores pasa de "firmantes" a herramienta general de worker-counting.

| ID | Idea pulida | Prio | Compl | Capa |
|----|-------------|:----:|:-----:|:----:|
| F1 | **BUG:** reabrir un conteo terminado, marcar "en progreso", recontar y guardar **no refresca** el detalle ni el Excel (ej. `charla` HPV mayo 6034→6070: el visor guarda 6070, pero el detalle y el Excel quedan en 6034). | 🔴 | M | ambas |
| F2 | Agregar visor de conteo de trabajadores a `dif_pts`. Caso especial: la celda **N15** del output (HH capacitación) solo en **Puerto Varas** toma el total de trabajadores de las difusiones; en otras obras, dejarlo habilitado por si acaso. | 🟡 | M | ambas |
| F3 | Extender el contador de trabajadores (**sin** sistema de voz) a `maquinaria` y demás celdas de worker-counting: moverse entre páginas, tipear el número, guardar rápido. | 🟡 | L | ambas |
| F4 | Destacar en la lista de MARCAS la línea de la página actual; mostrar siempre la última página. | 🟡 | S | FE |
| F5 | ~~Columna de **subtotales** del conteo de trabajadores en `charla` y `chintegral`.~~ **DESCARTADA 2026-06-09** — bajo valor; hay cosas más útiles en la UI antes que esto. | ⚪ | M | — |

**Relación:** `project_feature1_shipped`, hallazgo transversal #2, B7 (maquinaria).

---

## G · Flujo "flavor nuevo" 🟡
> Es el item del roadmap "marcar como nuevo flavor" (hoy solo copia un stub), expandido.

| ID | Idea pulida | Prio | Compl | Capa |
|----|-------------|:----:|:-----:|:----:|
| G1 | Auto-crear flavor: el escáner busca las anclas → te las muestra → tú refinas → aceptas → se agrega al registro enseguida. | 🟡 | L | ambas |
| G2 | Visor "ver portada": listar anclas a la izquierda (**verde** las que encontró, **rojo** las que no), título con el sabor, y un módulo para crear/editar/modificar un sabor. | 🟡 | L | ambas |
| G3 | El escaneo **individual** de un archivo no muestra la sospecha de sabor nuevo (sí aparece al escanear la celda completa). | 🟡 | S | ambas |

---

## H · Control de escaneo 🔴/🟡

| ID | Idea pulida | Prio | Compl | Capa |
|----|-------------|:----:|:-----:|:----:|
| H1 | **BUG:** al cancelar un escaneo, conservar lo ya escaneado. Hoy, aunque alcanzó a procesar varios archivos, cancelar **no pasa** esos resultados a los archivos. | 🔴 | M | ambas |
| H2 | Si ya se escaneó un archivo individual, el OCR de la celda debe **saltarlo**. | 🟡 | S | BE |
| H3 | Botón **"saltar al siguiente archivo"** durante el escaneo. | 🟡 | S | ambas |

**Relación:** guard `_cell_has_work`, eventos de progreso de escaneo.

---

## I · Visor de archivos — navegación / UX 🟡/🟢 (FE)

| ID | Idea pulida | Prio | Compl |
|----|-------------|:----:|:-----:|
| I1 | +20% al tamaño de la lista de páginas (columna izquierda). | 🟡 | S |
| I2 | La lista de miniaturas mantiene la actual **centrada** (autoscroll) para ver las que vienen. | 🟡 | S |
| I3 | Pre-renderizar 2-3 páginas en el visor mismo (no en la columna de previews). | 🟡 | M |
| I4 | Shift+PageDown avanza **10 páginas**. | 🟡 | S |
| I5 | "Ir a página: xx" para PDFs grandes. | 🟡 | S |
| I6 | Botón "siguiente" en el visor de **casi-matches** (como el next/prev que ya tiene el visor normal). | 🟡 | S |
| I7 | Girar el PDF temporalmente (se aplica hasta cambiar o resetear). | 🟢 | M |
| I8 | Calculadora básica colapsable en la columna derecha del visor. | ⚪ | S |

---

## J · Reorganización de archivos / páginas 🔴 PROMOVIDA (antes de multiplayer, para el próximo mes — ver addendum 2026-06-15)

| ID | Idea pulida | Prio | Compl | Capa |
|----|-------------|:----:|:-----:|:----:|
| J1 | Mover o separar una **hoja individual**, un **rango de páginas X–Y**, o el **archivo completo** a otra celda — o dividir dentro de la misma celda — llevando su conteo (y su conteo de trabajadores si tiene, restándolo del total de origen). El **rango de páginas es clave**: hay **documentos de más de una página colados en medio de un compilado** que hay que poder extraer. UI propuesta: sección "Reorganizar" en el panel derecho, con selector archivo-completo / páginas X-Y y un desplegable de celda destino (incluye la actual para solo dividir). Al dividir, **auto-renombrar** conservando fecha y nombres, cambiando solo sigla y empresa. | 🔴 | L | ambas |

**Relación:** corrige misclasificación de origen (PDF en sigla equivocada / compilación), grupo C (conteos), F (trabajadores).

---

## K · Conteo por teclado + badges (Feature 2, futuro) 🟢/⚪

| ID | Idea pulida | Prio | Compl |
|----|-------------|:----:|:-----:|
| K1 | Al marcar páginas con el botón, el badge muestra el **número de documento** contado al que corresponde. | 🟢 | M |
| K2 | El badge también visible en las miniaturas de la columna izquierda. | 🟢 | S |
| K3 | (Futuro) el OCR **aplica los badges**; tú agregas/quitas en cualquier página y se recalculan todos los badges + la suma de documentos en vivo. | ⚪ | L |

**Relación:** `project_feature2_boundary_badges` (parqueada), C3 (manual prevalece sobre badge).

---

## L · Multiusuario + gate de "listo" 🟢/⚪ (grande)

| ID | Idea pulida | Prio | Compl | Capa |
|----|-------------|:----:|:-----:|:----:|
| L1 | Compartir la app en LAN para trabajar en conjunto + **presencia** (ver si hay alguien ya editando una celda). | 🟢 | L | ambas |
| L2 | El botón "marcar listas" también **desmarca** (verde→amarillo pendiente). Diálogo de confirmación por acción (dar por listo + deshabilitar edición / reabrir edición). Un gate simple, posible base del bloqueo multiusuario. | 🟡 | M | ambas |

**Relación:** los tres son la misma máquina de estados a distinta granularidad — **L2 = lock por celda**, **L1 = presencia**, y el *lock per-hospital "terminado"* (idea diferida del incidente) = lock por hospital. Conecta con grupo **A**.

---

## M · Home / vista de mes 🔴/🟡 (FE)

| ID | Idea pulida | Prio | Compl |
|----|-------------|:----:|:-----:|
| M1 | **BUG:** los meses en el home van en **orden cronológico** (marzo, abril, mayo…). | 🔴 | S |
| M2 | Indicador en la card del hospital: trabajadores **pendientes / en proceso / listos**. | 🟡 | M |

---

## N · Cabos sueltos / preguntas

| ID | Idea pulida | Prio | Compl |
|----|-------------|:----:|:-----:|
| N1 | ¿Dónde quedan las **notas del detalle**? Si no están visibles, agregar un "ver notas". *(verificar en código)* | 🟡 | S |
| N2 | Botón "**aplicar R1**" (páginas = nº de documentos, con el ratio por sigla) a **todos** los archivos de una celda, de una. | 🟡 | S |
| N3 | *(cross-project)* ¿La hoja "Cump. Programa Prevención" alimenta algún dato de estadísticas CRS/OG en el proyecto *estadística mensual*? | — | — |

---

## Preguntas abiertas para Daniel

- **Q1 (F5):** los subtotales de `charla`/`chintegral`, ¿en la **UI del visor** o como **columna del Excel**?
- **Q2 (N3):** ¿investigo ahora el cruce con *estadística mensual* o lo dejo anotado para esa otra sesión?
- **Q3 (B3):** confirmado de memoria que `dif_pts` usa anclas de banda (no V4 = el viejo motor de 5 fases, hoy solo en `insgral`/`altura`). A verificar en código al arreglarlo.
- **Q4 (C2):** ¿la solución del "volver a contar los archivos" te cuadra como pregunta-al-vuelo, o prefieres un toggle explícito "celda manual ⇄ suma de archivos"?

---

## Prioridad sugerida para la ventana MAYO en vivo (🔴)

Lo que muerde **ahora** mientras cuentas MAYO a mano:

- **A (integridad):** A1, A2, A3, A4 — que el OCR no pise y que el verde no mienta.
- **C1 + C2 (overrides):** que el ajuste por archivo se refleje y poder volver al conteo de archivos.
- **B (calibración):** B1 (charla 2:1), B2 (chintegral), B3 (dif_pts), B7 (maquinaria = trabajadores).
- **F1 (worker bug):** el conteo de trabajadores recontado no llega al Excel — riesgo de número equivocado en el entregable.
- **H1 (cancelar conserva):** no perder trabajo de escaneo a medio camino.
- **M1 (orden de meses):** trivial, molesto.

Todo lo demás (UX del visor, reorganización, badges, multiusuario, flavor) puede esperar a que cierre el mes.

---

## Bitácora de decisiones
*(se llena a medida que discutimos cada grupo: aprobado / descartado / re-scoped / pendiente)*

### Núcleo A + C — en discusión 2026-06-09

- **Decisión 1 — qué enciende el punto verde (A1 + A2): ✅ RESUELTA.**
  El verde ("listo") se enciende SOLO si: la celda está `confirmed`, **o** tiene override
  manual de celda, **o** *todos* los archivos son **R1 o Manual** (incluida la mezcla
  R1+Manual). Cualquier archivo OCR / Pendiente / Error → ámbar hasta confirmar. Se deja de
  confiar en `confidence === "high"` del scanner; la procedencia por archivo manda.

- **Decisión 2 — OCR no pisa + saltar ya-escaneados (A3 / H2 / S3): ✅ RESUELTA.**
  El OCR de celda pasa de "reemplazar todo el mapa `per_file`" a **"fusionar y saltar"**:
  salta los archivos ya confiables (R1 / manual / OCR previo), solo escanea los pendientes,
  y escribe SOLO esas entradas (no toca las demás). Cubre A3 + H2 + S3 de una. Re-escaneo
  puntual queda disponible vía el botón OCR por-archivo existente.

- **Decisión 3 — modelo override celda ↔ archivos (C1 + C2): ✅ RESUELTA (Variante C, mockup aprobado).**
  **Toggle segmentado** bajo el número grande, dos modos de **una palabra**: `Archivo` ·
  `Manual`. Al lado, el conteo por archivos en muted (`archivos: 1.187`). Interacción:
  - Modo **Archivo** → el total = suma por archivos; el campo de "Ajuste manual" se
    desactiva/aclara. Cambiar a este modo **limpia** el `user_override` (backend ya soporta
    `value=None`).
  - Modo **Manual** → enfoca el campo de ajuste; el total = override de celda (anula archivos).
  **Modal de aviso DESCARTADO** (saldría en cada edición de archivo) → en su lugar, **hint
  inline ámbar persistente** cuando editas un archivo con override de celda activo. Disuelve
  C1. Mockup: `mockups/override-revert.png` (variante C).

- **Decisión 4 — validación del número (A4): ✅ RESUELTA (categorización corregida por Daniel).**
  Bloquear negativos siempre; 0 explícito válido. El tope **`conteo ≤ páginas` aplica SOLO al
  conteo de documentos**. Tres tipos de celda (corrige el binario doc/trabajador):
  - **Doc-counting** (mayoría): el número son documentos → tope `≤ páginas` aplica.
  - **Worker-counting SEPARADO** (`charla`, `chintegral`, `dif_pts`): tienen su conteo de
    documentos *y* un conteo de **trabajadores** en campo aparte (`worker_marks`). El de
    trabajadores puede superar las páginas → sin tope.
  - **Check-counting como conteo PRINCIPAL** (`maquinaria`): NO cuenta documentos; el número
    que va al Excel son **chequeos = columnas de fecha marcadas** (un formulario trae ~5
    columnas → supera las páginas por diseño) → sin tope.

  Requiere marcar formalmente el tipo de cada celda (se cierra al llegar al grupo F).

> Nota: el selector de la **Decisión 3** se queda en **dos modos** (`Archivo · Manual`). RN
> NO es un tercer modo — es una acción en bloque dentro del modo Archivo (ver B-b corregida).

### Grupo B — calibración OCR — en discusión 2026-06-09

- **Decisión B-a — `maquinaria` deja de auto-contar: ✅ RESUELTA.**
  El scanner de anclas cuenta formularios, pero maquinaria cuenta **chequeos (columnas de
  fecha marcadas)** — algo que el OCR de encabezado no puede leer. Se reclasifica como
  **celda de conteo manual** (contador por teclado, grupo F3). El resultado del scanner de
  anclas es irrelevante para esta sigla.

- **Decisión B-b — tratamiento "ratio páginas/documento" = RN, como método por archivo aplicado en bloque: ✅ RESUELTA (corregida).**
  R1 (1 pág = 1 doc) queda **intacto y automático** — es certeza, no juicio. Aparte, **RN** =
  el operador afirma "N páginas por documento". **NO es un tercer modo del selector** (eso no
  componía con correcciones puntuales). Es una **acción en bloque dentro del modo Archivo**:
  un botón "Tratar como N págs/doc" que pone a *cada archivo pendiente* el método ratio
  (`páginas_del_archivo ÷ N`). Como `Σ(páginas_i ÷ N) == (Σ páginas) ÷ N`, el total es el
  mismo, pero al vivir por archivo **compone** con las correcciones: luego puedes override
  manual / OCR de archivos sueltos y solo ésos cambian; el resto conserva RN; total = suma.
  - **No pisa lo ya resuelto** (Daniel 2026-06-09): la acción RN cae **solo sobre archivos
    pendientes** — nunca toca R1 (1 pág = 1 doc), ni manual, ni OCR previo. Es el MISMO
    invariante de la Decisión 2 ("tratamientos en bloque saltan lo resuelto").
  - **Regla viva:** recalcula si cambian las páginas (a diferencia de un override congelado).
  - Determinístico (páginas vía PyMuPDF) → confiable, **enciende verde** (Decisión 1); set
    confiable = {R1, Manual, RN}.
  - Los tratamientos en bloque del modo Archivo quedan agrupados: `OCR la celda · Aplicar R1
    · Aplicar ratio N…`. Caveat: redondeo por archivo (3 págs ÷ 2) → se corrige la excepción
    a mano. Se mockea junto con la Decisión 3 antes de fijar.

- **Decisión B-c — refinamiento OCR = pase DATA-FIRST con enrutamiento por sigla: ✅ RESUELTA (orientación estratégica acordada).**
  Reorienta TODO el "refinar OCR per-sigla" del roadmap. Problema de fondo (Daniel, 2026-06-09):
  las anclas se eligieron leyendo los formularios *como humanos* (top-down), pero Tesseract no
  rescata lo mismo → anclas que existen en papel pero no bajo OCR (charla/chintegral/dif_pts
  rinden mal). OCR es hoy la parte más débil; **V4 (paginación) es lo más confiable** donde
  se aplica. Propuesta:
  1. **Data-first:** muestrear por (sigla, template) con PDF reales de MAYO, OCR-ear las
     bandas, ver qué tokens rescata **de forma estable**, y derivar anclas desde ahí.
  2. **Discriminancia:** una ancla válida es estable bajo OCR **Y** rara entre siglas (cruzar
     contra las otras para evitar falsos positivos por tokens genéricos). Se mide, no se adivina.
  3. **Enrutamiento por sigla:** medir OCR-anclas vs V4 vs manual/RN por sigla y mandar cada
     una a su **mejor método con datos reales** — algunas siglas quizás NO deberían usar
     OCR-anclas.
  4. **Spec sigue siendo la fuente de verdad:** re-derivar es legítimo (la regla "nunca
     derivar empíricamente" era de *fidelidad de implementación* — el postmortem de
     anchor-truncation —, no prohibición de revisar el spec con datos); el resultado pasa a
     ser el nuevo spec, no un parche a ojo en `patterns.py`.
  Los empíricos B2 (chintegral HPV buena calidad), B3 (dif_pts=0 — chequear primero el
  `filename_glob`) y B4 (andamios HRB dos tipos) caen dentro de este pase. Acoplado con el
  flujo "flavor nuevo" (grupo G).

- **B5 — `odi` queda como baseline de regresión** (f_crs_odi_03, perfecto en HRB). No tocar.

### Grupo F — conteo de trabajadores + contador por teclado — en discusión 2026-06-09

- **F (concepto rector) — el contador por teclado es la herramienta GENERAL de conteo manual:
  ✅ RESUELTA.** Mismo visor paginado + teclado + suma en vivo; cambia solo *la unidad*
  que se talla por página: trabajadores (charla/chintegral/dif_pts), chequeos (maquinaria),
  documentos (compilados largos / grupo K). Un solo componente parametrizado, no cuatro.
- **F — etiqueta de "tipo de conteo" por sigla: ✅ RESUELTA.** Best practice confirmada para
  este caso (conjunto cerrado de 18 siglas + varios consumidores comparten la clasificación +
  el proyecto ya usa el patrón en `patterns.py` y ya fue mordido por divergencia → `cell_count.py`).
  Mantener **mínimo**: un campo simple de 3 valores, no jerarquía de clases. Formalizar por
  sigla qué cuenta y si es el número principal o uno secundario:
  - **cuenta-documentos** (mayoría): el número de la celda son documentos.
  - **cuenta-documentos-y-trabajadores** (`charla`, `chintegral`, `dif_pts`): documentos a una
    columna del Excel + trabajadores (contador por teclado) a otra (HH).
  - **cuenta-chequeos** (`maquinaria`): el único número son chequeos = columnas de fecha.
  Es la misma clasificación pendiente de la Decisión 4. La etiqueta le dice al contador qué
  tallar y al Excel de dónde sacar cada número.
- **F5 (subtotales por documento en charla/chintegral): ❌ DESCARTADA 2026-06-09** — bajo valor.
  Cierra la pregunta Q1.
- **F1 (bug 🔴) — el conteo de trabajadores recontado no propaga al detalle ni al Excel**
  (charla HPV 6034→6070 quedó en 6034 fuera del visor). A investigar la ruta de propagación
  al implementar. (MAYO ya cerró, pero afecta meses futuros.)
- **dif_pts / caso N15:** la celda N15 del Excel (HH capacitación) toma el total de
  trabajadores de las difusiones **solo en Puerto Varas**; en otras obras el visor queda
  habilitado por si acaso. Detalle de mapeo al Excel, se cierra al mapear.

### Grupos D · E · I · M — UX — 2026-06-09

**Aprobadas sin discusión (just-do-it):** meses del home en orden cronológico (bug); miniaturas
+20%; Shift+AvPág = 10 págs; "ir a página X"; miniatura actual centrada (autoscroll); botón
"siguiente" en el visor de casi-matches; click en el número del ajuste manual lo selecciona;
arreglar que ajustar desde la lista de archivos te tire al inicio (mantener posición).

- **Rendimiento del visor (era "pre-render 2-3 págs"): ✅ RESUELTA — reencuadrada.**
  Hoy el visor (`PdfPage.jsx`) renderiza **solo la página actual, en frío, y libera la anterior
  en cada cambio** — sin look-ahead ni caché → por eso el scroll rápido laguea. NO está en su
  techo. Combo correcto: **ventana de pre-render (actual ±1-2) + caché acotado (~5 páginas) +
  placeholder instantáneo desde la miniatura ya renderizada**. El cancelar-render-al-cambiar ya
  existe. Costo: unas pocas páginas más en memoria (acotado), aceptable.
- **Flechas +/− en vivo en el conteo por archivo: ✅ RESUELTA.** Capa fina sobre el guardado de
  override por-archivo que ya existe (mismo path que teclear). No es cambio profundo.
- **Tipear número en el visor + Enter: ❌ DESCARTADA.** Cubierto por el contador por teclado
  (tallar) + el campo de override por-archivo (fijar directo). Un tercer camino = conflicto de
  teclas + clutter.
- **Filtrar lista de archivos por chip: ✅ RESUELTA.** Barra compacta combinable con el buscador
  (R1/OCR/Manual/Pendiente/Revisar como toggles).
- **Color cuando documentos ≠ páginas de un archivo: ✅ RESUELTA — versión sutil / baja prioridad.**
  Resalte leve del número cuando difieren (no fondo pesado); o lograrlo como opción del filtro
  ("mostrar solo donde difieren"). Ayuda a cazar al vuelo en la lista gris.
- **Calculadora en el visor: ✅ RESUELTA.** Barra colapsable en el panel derecho, minimalista
  (+ − × ÷), manejable por teclado. Conflicto de teclas con el conteo se evita por **foco**: los
  atajos del conteo se ignoran cuando el foco está en un input (calc/buscador/ajuste manual) —
  buena práctica que el conteo debe respetar igual.
- **Indicador de trabajadores en la card del hospital: ✅ RESUELTA — Variante B** (mockup
  `mockups/hospital-card-workers.png`). Línea secundaria bajo el número: ícono + "Trabajadores
  · [estado]". Estado = **agregado del hospital** sobre sus celdas de conteo manual: pendiente
  (ámbar) si ninguna empezó · en proceso (azul) si alguna empezó · listo (verde) si todas
  terminaron. (Detalle de build: centrar el texto/punto de la pill en el eje Y.)
- **Rotar el PDF: ✅ RESUELTA — camino (a), rotación no destructiva.** Daniel confirmó el
  principio de no modificar archivos de otros procesos (`A:\informe mensual` solo-lectura, lo
  posee el paso 1). La rotación se guarda **como dato de PDFoverseer** (por archivo y por
  página), se aplica **solo al mostrar**, persiste entre sesiones, no toca el original ni se
  propaga al resto del pipeline. **Bonus parqueado:** la orientación guardada podría más adelante
  alimentar al OCR (una página torcida también le cuesta al escáner) — conecta con B-c, futuro.
  **Actualización 2026-06-09:** la rotación *permanente* (escribir en el archivo) tiene ahora un
  camino limpio vía el **manifiesto al paso 1** (ver J abajo) — no la hace PDFoverseer.

### Grupo G — flujo de "flavor nuevo" — en discusión 2026-06-09

- **Estado actual:** "Marcar como nuevo flavor" solo copia un **stub de código** (`flavorStub.js`)
  al portapapeles → un dev lo pega en `patterns.py`. **Bucle NO cerrado.** Además el stub reusa
  las **anclas del spec** (form-first), no lo que el OCR realmente leyó.
- **Pieza 1 — ¿dónde viven los flavors?: ✅ RESUELTA — modelo de dos capas.** Decidido desde
  perspectiva de arquitecto (forces: quién cambia / frecuencia / latencia / radio de daño /
  auditoría / fuente única se reparten → estratificar). Base = **código** (`patterns.py`, 22
  verbatim, autoritativa, testeada). Capa de operador = **runtime, persistida, editable desde la
  UI, ADITIVA** (agrega templates nuevos; nunca pisa la base → sin doble fuente de verdad).
  Camino de **promoción** runtime→spec diferido. No choca con "spec verbatim" (agrega, no trunca).
  **Des-arriesgada por la Decisión 1** (OCR nunca enciende verde solo → un flavor malo no marca
  "listo" a escondidas). Costos: maquinaria de persistencia/validación; test que vigile la regla
  aditiva; export/backup de la capa runtime (DB frágil). Principio para reusar: *código para
  conocimiento estable/compartido/alto-riesgo; datos/runtime para volátil/local/cambiado por el
  usuario; si ambos pesan, estratificar + promoción.*
- **Pieza 2 — ¿de dónde salen las anclas?: 🔵 data-first (acordado).** Mostrar lo que el OCR
  extrajo de la banda + el operador elige los tokens + chequeo de **discriminancia** (no dispara
  en otras siglas). Materializa B-c en la UI.
- **G2 — visor de anclas + autoría: ✅ RESUELTA (v1 mínima).** Es el **diagnóstico de banda OCR
  traído a la UI** + autoría. v1: **(diagnóstico)** portada al lado + lo que el OCR extrajo de la
  banda (tokens crudos) + anclas de los flavors existentes en verde (coincidió) / rojo (faltó);
  **(autoría)** elegir tokens del OCR como anclas (data-first, no reescribir del formulario) +
  `min_match` + nombre + **chequeo de discriminancia** (avisa si un token también aparece en otra
  sigla) + guardar a la capa runtime. **Diferido a v2:** editar / forkear flavors existentes y
  promover a spec (spec read-only en la UI; se valida que sirva antes de hacerlo full). Reusa el
  endpoint `scan-info`. Mockup: `mockups/flavor-anchor-viewer.png`.
  - **Decisiones de diseño afinadas (Daniel, 2026-06-09, mockup aprobado):**
    - **Este visor REEMPLAZA al visor de casi-matches actual** ("Ver portada") — es su superconjunto.
      Por eso lleva **navegación anterior/siguiente** + indicador "N de M" entre casi-matches.
    - El módulo de autoría va como **sección secundaria, no intrusiva** (permite el vistazo rápido).
    - Microcopy: encabezado **"Comparado con `<flavor>` · X de Y anclas"** (sin "(lo más cercano)");
      sección de tokens **"Seleccionar anclas encontradas"**; preview **"Match: X de Y"**; botón **"Guardar"**.
    - Panel de autoría: **Nombre / Anclas / min_match alineados en grilla** (label + contenido), no ragged.
- **G3 — el escaneo individual no muestra casi-matches: ✅ RESUELTA — arreglo de consistencia.**
  El camino por-archivo debe calcular/pasar los casi-matches igual que el de celda completa (la
  plomería de `apply_per_file_ocr_result` ya los acepta). Importa porque el escaneo individual es
  el contexto natural para crear un flavor → se hace junto con G2.

### Grupo L — multiplayer / colaboración — PARQUEADO para sesión dedicada (2026-06-09)

Familia coherente (*ciclo de vida de celda/hospital + colaboración*) — **enmarcada, no detallada**.
Se discute en su propia sesión, **después** del refinamiento OCR + el conteo. Alcance:
1. **Desmarcar / volver una celda a ámbar** + confirmación + gate de edición (botón marcar/desmarcar lista).
2. **Bloqueos:** lock de celda (edición exclusiva) + lock por hospital **"terminado"** (declarativo,
   reversible — del incidente de pisado de MAYO, ver `project_rescan_clobber_incident`).
3. **Presencia:** quién está conectado y en qué celda/hospital (chips; el espacio ya está reservado).
4. **Claude como tercer usuario** (detalle abajo).

La **nota-con-estado** (grupo N) es el primer anticipo del gate de celda.

- **Claude como tercer usuario (idea de Daniel):** factible; son **3 capacidades distintas**.
  **(1) Observar** (telemetría/logs/estado) — la más valiosa, ya existe a medias (bloques
  `[AI:]`/`[DS:]` + SQLite); falta exponerla consumible; **ya requerida por B-c**. **(2) Actuar**
  vía la API HTTP como cliente headless (mismo contrato que el React; ya ocurre parcial vía
  chrome-devtools; **mismo radio de daño → mismas guardas ya construidas**). **(3) Presencia**
  (chip "quién trabaja dónde"); matiz: Claude es **episódico** → aparece mientras trabaja
  activamente, no siempre-online. Principio unificador: **API-first + telemetría estructurada +
  multi-cliente** → los 3 caen solos, y es buena arquitectura igual. **No construir ahora**;
  diseñar teniéndolo en mente. Se detalla al llegar al grupo L (multiplayer).

### Grupo H — control de escaneo — 2026-06-09

- **H1 — cancelar pierde lo ya escaneado: ✅ RESUELTA (cae de la Decisión 2).** Hoy el OCR de
  celda escribe los resultados todo junto al final → cancelar a mitad descarta lo procesado. Con
  la Decisión 2 (fusionar por archivo) + escritura **incremental** (persistir cada archivo apenas
  termina, como ya hace el OCR de un solo archivo), cancelar = parar sin perder lo hecho;
  no-empezados quedan pendientes, el en-curso se descarta. H2/H3 (saltar ya-escaneados / saltar al
  siguiente archivo) ya estaban dentro de la Decisión 2.

### Grupo J — reorganización (mover / separar / reclasificar) — ✅ RESUELTA (arquitectura) 2026-06-09

- **Modelo "decidir vs ejecutar" (plan/apply) vía manifiesto al paso 1.** Toca el mismo límite
  solo-lectura que la rotación, y más fuerte (crear/renombrar/mover archivos = los posee el paso 1).
  Solución (idea de Daniel, validada como patrón sólido): el paso 1 corre en **dos tandas**
  (organiza/normaliza por nombre → **pausa para contar en PDFoverseer** → comparación/fusión/
  entrega). PDFoverseer —único que ve el **contenido**— **marca** rotaciones/separaciones/
  movimientos/reclasificaciones y **exporta un manifiesto declarativo**; el paso 1 —dueño de los
  archivos y de la convención de nombres— lo **ejecuta** en su 2ª tanda. El conteo en PDFoverseer
  no se altera (ya contó virtual; los archivos calzan al aplicarse).
  - **Manifiesto = solo operaciones de archivo** (rotar / separar págs X-Y / mover / reclasificar);
    los conteos se quedan en PDFoverseer.
  - **Lleva intención semántica** (sigla=X, empresa=Y, conserva fecha, rotar N°), **NO el nombre
    literal** → el paso 1 aplica SU convención de nombres (single-source).
  - **Riesgo nuevo: contrato cross-proyecto** → esquema explícito + versionado, coordinado con los
    scripts del paso 1 (`A:\informe mensual\.serena\memories\`). Idempotente, con orden de
    operaciones; la reasignación virtual persiste hasta aplicarse. Bucle de verificación opcional.
  - **Resuelve también la rotación permanente** (mismo canal). Trabajo grande y **coordinado con
    el paso 1** → territorio de transformaciones grandes, no inmediato. Arquitectura ya decidida.
  - **Principio para reusar:** info de un lado, autoridad del otro → pasar un **encargo declarativo**
    por la frontera (decidir vs ejecutar), no dar permiso de cruzarla.
  - **El manifiesto puede llevar un prompt para el agente que opera el paso 1** (Daniel 2026-06-09):
    además de las operaciones declarativas, instrucciones en lenguaje natural para la instancia de
    Claude que ejecuta la 2ª tanda → encargo legible para humano *y* para agente. Cruza con "Claude
    como usuario" (grupo L).

- **Actualización 2026-06-15 (Daniel) — PROMOCIÓN + alcance afinado:**
  - **Prioridad: PROMOVIDA a near-term, ANTES de multiplayer, objetivo el próximo mes.** Razón:
    **ordenar adecuadamente los documentos y contar los que corresponden a cada celda es uno de los
    problemas que MÁS afectan las observaciones de la inspección fiscal.** Deja de ser "parqueado /
    algún día"; es de los próximos focos tras los increments de conteo. (Multiplayer queda después.)
  - **Mover debe incluir RANGO de páginas X–Y, no solo hoja individual o archivo completo:** hay
    **documentos de más de una página colados en medio de un compilado** que hay que poder extraer a
    su celda correcta. El selector de la UI "Reorganizar" ya contempla páginas X-Y; lo clave es que
    la operación MOVER (no solo dividir) lo soporte.
  - **El manifiesto DEBE llevar las rotaciones** (reafirmado): rotación por página/archivo viaja como
    operación declarativa al paso 1 (ya estaba en "rotar / separar págs X-Y / mover / reclasificar",
    se explicita aquí para que no se pierda).
  - Implicación de secuencia: re-evaluar el orden de increments — J podría adelantarse para estar
    lista en el ciclo del próximo mes. Sigue siendo trabajo **L** y **cross-proyecto** (contrato +
    coordinación con el paso 1), así que su tamaño no cambia, solo su prioridad.

### Grupo K — badges / contador de inicios de documento (Feature 2) — ✅ RESUELTA 2026-06-09

- **Parte manual: absorbida por el contador por teclado generalizado** (unidad = "inicios de
  documento"). No es capacidad nueva — es el mismo visor con otra unidad (grupo F).
- **Parte aditiva: badges SEMBRADOS por OCR + corregibles en la página.** El OCR propone los
  inicios; el operador inserta/quita uno en cualquier página y los demás **se renumeran en vivo**
  (badge = ordinal, total = tamaño del set). Ejemplo: {1,3,7}=docs 1-3 → insertar 5 → {1,3,5,7}=docs 1-4.
  - **Modelo de datos = reusa el del contador de trabajadores.** `worker_marks` es
    `{archivo:[{página,cantidad}]}`; badges es `{archivo:[pág,…]}` (solo la página de inicio). Mismo
    visor, misma persistencia, mismos estados en-progreso/terminado.
  - **Método por archivo nuevo "badges (OCR-sembrado, corregido)"** — NO usa el ajuste manual (no
    pone `user_override`); es OCR refinado por el operador, compone con el modelo por-archivo.
  - **Verde (Decisión 1):** "terminado" = el operador revisó cada inicio = verificación humana →
    enciende verde (como confirmar); OCR sembrado sin revisar → ámbar.
  - **Dependencia honesta:** los límites se calculan internamente en inferencia
    (`Document.start_pdf_page`) pero se descartan antes de la API → sembrar requiere cablearlos
    (scanner→estado→API; verificar al implementar). La calidad de la siembra depende del OCR (B-c).
    **El modo badges manual funciona ya**; la siembra-OCR rinde tras afinar el OCR → construir en
    dos tiempos.

### Grupo N — cabos sueltos — 2026-06-09

- **N1 — notas del detalle CON ESTADO: ✅ RESUELTA (ampliada por Daniel).** Hoy la nota está
  pegada al ajuste manual (una nota sin override se descarta). Se **desacopla** → nota por celda
  independiente, con **estado** `por resolver` / `resuelto`. Reglas: una nota **`por resolver`
  bloquea marcar la celda como lista** y la fuerza a ámbar aunque la procedencia diera verde (otra
  condición del verde → extiende la Decisión 1); **`resuelto`** deja el campo de texto
  **read-only**; **reversible** (volver a `por resolver` reabre la edición y re-bloquea). Sin más
  complejidad. Es la primera pieza concreta del tema "ciclo de vida / gate de celda" (grupo L).
- **N2 — "aplicar R1" a toda la celda: ✅ cubierto.** Es la acción en bloque `Aplicar R1`
  (= ratio N=1) del modo Archivo. Sin trabajo nuevo.
- **N3 — pregunta cruzada (¿Cump. Programa Prevención alimenta estadísticas CRS/OG?): ❌ DESCARTADA.**
  No es de PDFoverseer (es del paso 3, estadística mensual).

---

## Orden de implementación (borrador 2026-06-09)

**Principio:** dependencia > valor/urgencia > riesgo, en cortes finos e **independientemente
entregables**, uno a la vez con el proceso completo (spec → plan → review ×2 → TDD → smoke
conducido → commit atómico + tag de milestone; barra de calidad de primer intento).

**Incremento 1 — Fundación: conteo honesto + modelo de estado de celda** (la espina; casi todo
cuelga de acá; arregla los bugs de correctness). Partido en dos:
- **1A — Backend: conteo robusto + sin pisar.** OCR de celda = **fusionar-y-saltar + escritura
  incremental** (arregla "OCR pisa R1/A3", "cancelar pierde lo hecho/H1", "saltar ya-escaneados/H2");
  **etiqueta de tipo de conteo por sigla**; completar la procedencia `per_file_method` en todos los
  caminos. Entrega valor solo (no clobber, cancelar conserva). **Pieza delicada:** toca el bucle de
  orquestación del OCR (recorrido de PDFs, eventos WS, cancelación) → mapearlo antes del spec.
- **1B — Frontend: honestidad + controles.** Verde por procedencia (no `confidence`); toggle
  Archivo·Manual reversible + hint inline; validación (negativos, tope ≤páginas solo en doc-cells).
  Cuelga de 1A.

**Incremento 2 — RN + tratamientos en bloque** (depende de 1). RN como acción en bloque que respeta
R1; cluster OCR/R1/ratio.

**Incremento 3 — Contador por teclado general + maquinaria + bug de trabajadores** (depende de la
etiqueta de tipo). Generalizar el contador (unidad param); maquinaria=chequeos; difusión PTS + N15;
**bug del conteo de trabajadores que no llega al Excel**; indicador en card del hospital. Gate de
notas-con-estado acá o en 1B.

**Track paralelo A — Refinamiento OCR data-first + telemetría** (independiente de 1-3; el más
riesgoso/iterativo). Prototipar en `eval/` (hookify eval-before-core); exponer telemetría de banda
OCR (sirve también para "Claude observa"); medir OCR-anclas vs V4 vs manual por sigla → enrutar.
Subir version-tag antes de tocar `core/`.

**Incremento 4 — Autoría de flavors** (depende de la telemetría de banda del Track A). Capa runtime
aditiva + visor de anclas/autoría (reemplaza el de casi-matches) + escaneo individual muestra
casi-matches (G3).

**Track paralelo B — Pulido UX** (bajo riesgo, casi todo independiente; buen relleno). Perf del
visor (pre-render + caché + placeholder), miniaturas +20%, Shift+AvPág, ir-a-página, actual-centrada,
next en casi-matches, calculadora, rotación-vista, filtro por chip, color docs≠págs, click-seleccionar,
flechas.

**Incremento J — Reorganización vía manifiesto al paso 1** (PROMOVIDO 2026-06-15, ver Grupo J): mover
hoja / **rango de páginas X–Y** / archivo completo entre celdas llevando el conteo, + rotaciones, todo
exportado como **manifiesto declarativo** que ejecuta el paso 1 en su 2ª tanda. **Objetivo: el próximo
mes; antes de multiplayer.** Razón: el ordenamiento correcto de documentos por celda es de los mayores
drivers de observaciones de la inspección fiscal. Trabajo **L** + cross-proyecto (contrato versionado
coordinado con el paso 1). Ubicación exacta en la secuencia: a re-evaluar (puede ir tras Incr 2/3 o
adelantarse según el calendario del próximo mes).

**Parqueado (después / coordinado):** multiplayer/colaboración (grupo L), badges sembrados por OCR
(dependen del Track A + cablear los límites de documento).

**Empezamos por:** Incremento **1A** (spec ← mapear primero la orquestación del OCR). [1A ✅ 2026-06-11,
1B ✅ 2026-06-15. En curso: Incremento 2 — RN + tope ≤páginas.]
