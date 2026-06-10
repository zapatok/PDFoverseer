# Refinamiento de scanners OCR por categoría — design doc

**Fecha:** 2026-05-18
**Rama:** `po_overhaul`
**Estado:** 🚧 Brainstorm en curso — recorriendo las 18 categorías una a una.
Documento vivo; se acumula una entrada por categoría a medida que se acuerda.
Será la base del plan de implementación.

---

## Propósito

Refinar el conteo de documentos por categoría. El problema raíz: `filename_glob`
(R1) deja una celda en verde con confianza "Alta" cuando en realidad solo contó
nombres de archivo — un **falso verde**. Por cada categoría preguntamos:

> ¿Cuándo *miente* `filename_glob` para esta categoría, y cuál es el chequeo más
> barato y fiable que lo caza?

No es "meter OCR a las 18". Para varias siglas la conclusión válida será
"`filename_glob` es confiable aquí, déjala" (YAGNI).

## Arquitectura — dos capas

1. **Capa de scanners** (`core/scanners/`): el dispatch por sigla. Registry +
   Protocol `Scanner` + `ScanResult`. Hoy: 4 especializados (art/odi/irl/charla)
   + 14 vía `SimpleFilenameScanner`. **Esta es la capa que se refina.**
2. **Pipeline V4** (`core/pipeline.py`): motor de paginación "Página N de M" +
   inferencia de 5 fases + Dempster-Shafer. **Estrategia de pase 2
   alternativa** (ver A6): se usa selectivamente para categorías con plantillas
   demasiado heterogéneas para A2 — caso `insgral` (categoría 8), donde hay
   ≥ 4 templates CRS distintos + formatos no-CRS de subcontratistas. Para las
   categorías con formularios CRS estandarizados (irl, odi, charla, chintegral,
   dif_pts, art), A2 sigue siendo más rápido y específico. Su cascada de
   preproceso de imagen y su normalización de dígitos OCR también se reusan
   dentro de A2.

Técnicas disponibles en `core/scanners/utils/`: `filename_glob`, `header_detect`
(códigos `F-CRS-XXX/NN`), `corner_count` (numeración en esquina),
`page_count_pure` (metadata PyMuPDF), `page_count_heuristic`
(`flag_compilation_suspect`).

**Principio de reuso:** scanner por sigla = wrapper delgado + técnica compartida
en `utils/`. ODI e IRL ya comparten `HeaderDetectScanner`. Cada vez que una sigla
pueda reusar la técnica de otra, se anota explícitamente — cada categoría tiene
su scanner, pero no se duplica código.

## Decisiones de diseño (transversales)

Estas decisiones surgen del análisis de `irl` (categoría 2) pero aplican al
refinamiento como conjunto. Las categorías posteriores las dan por sentadas.

### A1 — Registro central de patrones (`core/scanners/patterns.py`)

Hoy los regex y anclas viven dispersos: `_build_pattern` en
`utils/header_detect.py`, `_FILENAME_REMAINDER_RE` en `utils/filename_glob.py`,
`_PAGE_PATTERNS` en `core/pipeline.py`. Se consolidan en un **registro por
tipo de documento**, con la misma estructura por entrada:

```python
# Anclas reusables compartidas entre siglas que usan el mismo formulario.
CRS_RCH_ANCHORS = [
    "Nombre de la Charla", "Obra", "Relator", "Cargo Relator",
    "Hora de inicio", "Hora de Término", "Tiempo duración charla",
    "Tipología de Charla/Reunión",
    # ...
]

PATTERNS: dict[str, SiglaPattern] = {
    "irl": {
        "filename_glob": r"^.*irl.*\.pdf$",       # ver A10
        "scan_strategy": "anchors",
        "cover_flavors": [
            {
                "name": "f_irl_01",               # ver A9
                "anchors": [
                    "ANTECEDENTES GENERALES",
                    "FECHA DE REALIZACIÓN",
                    "TIPO DE INDUCCIÓN",
                    "IDENTIFICACIÓN DEL TRABAJADOR",
                    "Página 1 de",
                    # ...
                ],
                "min_match": 3,
            },
        ],
    },
    "chintegral": {
        "filename_glob": r"^.*chintegral.*\.pdf$",
        "scan_strategy": "anchors",
        "cover_flavors": [
            {"name": "f_rch",      "anchors": CRS_RCH_ANCHORS, "min_match": 3},
            {"name": "f_japa",     "anchors": [...],            "min_match": 3},
            {"name": "f_previene", "anchors": [...],            "min_match": 3},
        ],
    },
    # una entrada por sigla; las mono-formato tienen un solo flavor
}
```

Cambiar un formato (variantes, nuevas revisiones, distintos prevencionistas,
o un nuevo contratista que emita su propio template) = editar una entrada o
agregar un flavor. Sin tocar la lógica de los scanners. Ver **A11** para el
tipo canónico, **A9** para la convención de naming, **A10** para
`filename_glob`.

### A2 — Técnica compartida: portada por anclas en una banda superior

`core/scanners/utils/header_band_anchors.py` (nuevo) — OCR de la **banda
superior** de cada página (configurable, default 25 %), normaliza el texto
(sin acentos, lowercase, espacios y slashes colapsados), cuenta páginas con
≥ N matches del set de anclas del tipo. Devuelve el conteo de **portadas**
(= conteo de documentos).

Es la pieza reusable que Daniel anticipó: varios tipos del CRS comparten el
patrón "portada con encabezado de campos + páginas interiores tabulares" — la
misma función sirve cambiando solo la lista de anclas en `patterns.py`.

**Banda configurable por sigla.** Cada entrada de `patterns.py` puede declarar
`top_fraction: float` (default 0.25). Las siglas con formularios cover-only
más densos en la mitad superior — caso `dif_pts` (categoría 6) — suben a 1/3
sin tocar lógica del scanner.

Reuso del pipeline V4 (selectivo):
- ✅ Cascada de preproceso de imagen (deskew → quita color → canal rojo →
  inpaint → unsharp). Aplicable a cualquier OCR.
- ✅ Patrón "Página N de M" — se incluye como uno de los anclas (caza la
  forma "Página 1 de…" que marca portada).

V4 NO se reusa para portadas (overkill para esta tarea):
- ❌ Motor de inferencia 5 fases + Dempster-Shafer.
- ❌ 6 workers paralelos (las compilaciones son raras, no justifican
  paralelismo).

### A3 — Granularidad del disparador OCR

Hoy: el usuario marca categorías y aplica OCR a la categoría completa. **Se
mantiene.** Se agrega: **OCR por PDF individual** — un click sobre un archivo
en la `FileList` → "escanear este PDF con OCR". El resultado vive en el
campo `per_file` (modelo de datos ya existente desde FASE 4). El total de la
celda = suma de los `per_file` (`filename_glob` para los normales + OCR para
el sospechoso).

El disparador automático `flag_compilation_suspect` se mantiene como detector
preventivo, pero el usuario tiene la palabra final por PDF. Esto resuelve el
hueco actual de `len(pdfs)==1`, que solo detecta compilación cuando TODA la
carpeta es un único PDF — el caso "1 compilación escondida entre 49
individuales" hoy no se caza.

### A4 — Multi-flavor por tipo de documento

Descubierto al analizar `chintegral` (categoría 5): algunas siglas reciben
PDFs en formatos **completamente distintos** según el origen. La misma carga
semántica ("charla integral") puede venir como el formulario CRS interno,
como el formato JAPA "Registro Capacitación", o como una lista de asistencia
del programa PREVIENE del gobierno. Las anclas de cada formato son disjuntas.

**Estructura en `patterns.py`:** cada sigla tiene un `cover_flavors: list`,
donde cada flavor tiene su propio set de anclas y umbral `min_match`. La
detección de portada considera una página cover si **algún flavor** alcanza
su umbral. Las siglas mono-formato (reunion sin anclas; irl, odi, charla con
un solo formato por ahora) tienen una lista con un único elemento.

**Por qué no un solo set unión:** mezclar anclas de distintos flavors en una
sola lista con umbral global **diluye la redundancia** que valida cada formato
internamente. Una página podría matchear 1 ancla de flavor A + 2 de flavor B
= 3 matches sin ser realmente cover de ningún formato real. La regla "≥ N
matches dentro de un mismo flavor" preserva la redundancia interna.

**Reuso entre siglas:** cuando dos siglas comparten un formulario (caso
`charla` y `chintegral`, ambas usan F-CRS-RCH-01), sus anclas viven en una
constante reusable en `patterns.py` (ej. `CRS_RCH_ANCHORS`); cada sigla
referencia la constante en su flavor correspondiente.

### A5 — Anti-anchors por flavor (rechazo de shadow covers)

Algunos formatos generan **shadow covers**: páginas posteriores a la portada
que reproducen el mismo header del formulario (mismos campos, misma
estructura) pero NO son portada — son tests, evaluaciones u otra hoja
estructuralmente paralela a la cover. Caso real: `dif_pts` de HLL
(categoría 6) — cada difusión consta de una cover ("REGISTRO DE CHARLA")
seguida de una página de test ("TEST DE COMPRENSIÓN" / "TEST TRABAJO EN
…") que **repite todos los campos de identificación** (Nombre de la
Capacitación, Obra, Relator, Cargo Relator, Fecha, Tiempo duración charla).
El conteo de anchors sin más, contaría doble.

Para distinguir cover real de shadow cover, cada flavor puede declarar
opcionalmente `anti_anchors: list[str]`. La regla de detección queda:

> Una página es cover del flavor si matchea **≥ `min_match`** anchors
> **Y** matchea **< `anti_min_match`** anti-anchors (default 1, i.e.
> cualquier match en la lista de anti-anchors descalifica la página).

Sin `anti_anchors` declarada, el comportamiento es idéntico al anterior
(sin rechazo). Las anti-anchors deben caer dentro de la `top_fraction`
configurada para la sigla — si no, no las verá el OCR de la banda.

Ejemplo (flavor B de `dif_pts`, ver categoría 6 para el detalle):

```python
{
    "name": "f_ch_crs_01",
    "anchors": [
        "REGISTRO DE CHARLA",
        "Nombre de la Capacitación",
        "Cargo Relator",
        "Tiempo duración charla",
    ],
    "min_match": 3,
    "anti_anchors": [
        "TEST DE COMPRENSIÓN",
        "TEST TRABAJO EN",     # cubre "...EN ALTURA", "...EN CALIENTE", etc.
        "ALTERNATIVA CORRECTA",
        "F-PETS-CRS",          # prefijo del código del test (cover es F-CH-CRS-01)
    ],
}
```

Anti-anchors no es solo para test pages: es el patrón "este formato tiene
shadow pages que comparten estructura con la cover; necesito palabras-llave
en la shadow page que NO estén en la cover". Probablemente lo reusen
categorías futuras donde se descubra el mismo patrón.

### A6 — Estrategia de pase 2 por sigla: A2 vs pagination vs none

Cada sigla declara explícitamente en `patterns.py` cómo cuenta cuando
`filename_glob` no basta. El dispatcher del scanner elige:

- **`scan_strategy: "anchors"`** (default cuando hay `cover_flavors`): usa
  A2 (`header_band_anchors`) sobre los flavors declarados. Apropiado para
  formularios CRS con header fijo y campos cover-only identificables.
  Categorías: irl, odi, charla, chintegral, dif_pts, art.
- **`scan_strategy: "pagination"`**: cuenta documentos vía detección de
  transiciones "Página N de M" en la esquina superior derecha. Implementado
  por `PaginationScanner` que reusa `corner_count.count_paginations` —
  motor mínimo (OCR + regex + normalización de dígitos), sin Dempster-Shafer,
  sin workers paralelos. Apropiado para categorías donde los formularios son
  heterogéneos pero la paginación es confiable y universal. Categorías:
  insgral (categoría 8), altura (categoría 14).

  > **Nota histórica**: en versiones tempranas del spec esta estrategia se
  > llamó `"v4"` (porque hubo un plan de delegar al pipeline V4 completo,
  > `core/pipeline.py`). En el plan de implementación se decidió no traer
  > V4 entero — sólo la pieza mínima de paginación — y se renombró a
  > `"pagination"`. **El nombre canónico es `"pagination"`**. V4 queda como
  > código legacy en `core/pipeline.py`, desconectado del scanner registry.
- **`scan_strategy: "none"`**: solo `filename_glob`, sin pase 2. Categorías:
  reunion (categoría 1).

La elección la determina la **variabilidad de plantillas**:
- ≤ 3 plantillas con campos cover-only redundantes → A2 (más rápido, anclas
  específicas, menos OCR).
- ≥ 4 plantillas con poco overlap pero paginación común → pagination (motor
  genérico basado en la única señal compartida).
- 1 PDF = 1 documento sin posibilidad de compilación → none.

### A7 — Regla de R1: PDFs de 1 página cuentan como 1 documento (locked)

Un PDF de exactamente 1 página **no puede ser una compilación** —
físicamente no hay dónde meter una segunda portada. Esta certeza se
incorpora a **R1** (el primer pase, al abrir la carpeta), no al
dispatcher de pase 2:

- **R1 cuenta = 1** trivialmente para esos PDFs, sin llamar a OCR.
- **Estado "locked"**: el PDF queda fuera del flujo de pase 2. La UI
  NO ofrece el botón "escanear este PDF" (A3) sobre archivos de 1 pág
  — ya están contados, OCR no aporta información.
- **Confianza "Alta — trivial"** automática (no requiere verificación
  manual, no entra en el flujo "Baja" de S2).

La regla es **previa a A6**: si aplica, no se evalúa la `scan_strategy`.
Es parte de la decisión de R1 al enumerar la carpeta, no del dispatcher
de pase 2.

Implicación UX: en el `FileList`, un PDF de 1 pág muestra el chip
`Npp = 1 · Ndocs = 1 · Origin = trivial`; sin botón de re-scan
individual. En PDFs multi-página, el flujo normal de A3 (OCR per-PDF)
sigue disponible.

Caso canónico (cat 9): HRB `bodega_respel.pdf` y `bodega_suspel.pdf`
son 1 pág c/u → R1 los cuenta como 1 chequeo cada uno y los bloquea.
Caso negativo (también cat 9): HPV `chequeos_suspel_y_respel.pdf` es 4
págs → R1 NO aplica A7; el archivo queda disponible para A2.

### A8 — Carpeta de sigla inexistente → 0 docs (sin error)

Descubierto en cat 17 (`andamios`, HLU sin carpeta en abril) y
confirmado en cat 18 (`chps`, HRB/HLU/HLL sin carpeta). El
dispatcher del scanner **debe tolerar `FileNotFoundError`** sobre la
carpeta de sigla y devolver un `ScanResult` con `count=0`,
`confidence="HIGH"` (es una certeza, no una duda) y
`method="empty_folder"`. Aplicable a las 18 siglas.

Es trivial pero crítico: hoy el wrapper podría lanzar excepción y
romper el conteo del hospital entero por una sola sigla vacía.

**No usar `confidence="LOW"` para este caso** — vacío no es "no sé"
sino "0 con certeza".

### A9 — Naming unificado de flavors

Convención: **`f_<código_canónico>[_<origen>]`** donde:

- `<código_canónico>` es el prefijo del código del formulario sin
  el prefijo `F-` redundante. Ejemplos: `lch_05` (de `F-CRS-LCH-05`),
  `ar_01` (de `F-CRS-AR-01`), `rch` (de `F-CRS-RCH-01`).
- `<origen>` (opcional) cuando el flavor identifica un origen no-CRS:
  `titan`, `reali`, `ribeiro`, `previene`, `japa`, `hll_17`,
  `aguasan`.

Reglas:
- **No** repetir la sigla en el nombre — el flavor ya vive bajo
  `PATTERNS["<sigla>"]`. ❌ `f_crs_lch_05_andamios` → ✅ `f_lch_05`.
- Lower-case + snake_case.
- Múltiples códigos en una familia → `f_lch_xx` (sufijo `_xx`
  indica "varios").

### A10 — `filename_glob` unificado (patrón laxo)

Patrón canónico para todas las siglas:

```python
r"^.*<sigla>.*\.pdf$"
```

Razón: el folder ya filtra por sigla (las 18 carpetas están
separadas en disco). El glob es defensa secundaria contra archivos
sueltos mal nombrados. El **patrón estricto previo**
(`r"^\d{4}-\d{2}-\d{2}_<sigla>_.+\.pdf$"`) rechazaba mega-compilados
HLL con nombres como `2026-04_<sigla>.pdf` (sin día) — falsos
negativos sistemáticos.

El glob es **case-insensitive** (la flag `re.IGNORECASE` se aplica
en la implementación), porque algunos nombres llegan con tipografía
mixta.

### A11 — Tipo canónico del registro (TypedDict)

Reemplaza la descripción informal de A1. La estructura es
inequívoca:

```python
from typing import Literal, NotRequired, TypedDict

class Flavor(TypedDict):
    name: str                                    # ver A9
    anchors: list[str]                            # min 3 recomendado
    min_match: int                                # default 3
    anti_anchors: NotRequired[list[str]]          # ver A5
    anti_min_match: NotRequired[int]              # default 1

class SiglaPattern(TypedDict):
    filename_glob: str                            # ver A10
    scan_strategy: Literal["anchors", "pagination", "none"]  # ver A6
    cover_flavors: NotRequired[list[Flavor]]      # requerido si strategy="anchors"
    top_fraction: NotRequired[float]              # default 0.25
    recursive_glob: NotRequired[bool]             # default False, ver Patrón P6

PATTERNS: dict[str, SiglaPattern] = {
    # 18 entradas, una por sigla
}
```

Los defaults documentados aquí son **fuente de verdad**; las
entradas individuales solo declaran lo que difiere del default.

### A12 — Anclas estructurales antes que códigos numéricos

Cuando una sigla usa una **familia de códigos** (`F-CRS-LCH-XX` con
XX variable: -04, -05, -10, -14, -29, -33, -39, ...), el ancla
debe ser el **prefijo de familia** (`F-CRS-LCH`), no el código
completo. El código específico puede coexistir como ancla extra,
pero la **detección** debe sostenerse sobre anclas estructurales:

- Títulos del formulario (`"LISTA DE CHEQUEO DE ANDAMIOS"`).
- Headers de sección (`"DATOS DEL ANDAMIO"`,
  `"SUPERFICIE DE APOYO"`).
- Field-labels específicos (`"Tipo andamio"`, `"Contratista"`).
- Identidad del emisor (`"CONSTRUCTORA REGIÓN SUR"`, `"TITAN"`,
  `"RIBEIRO SPA"`).
- Marcadores de paginación (`"Página 1 de"`).

Razón: cuando CRS emite una **revisión** del formulario o
**reasigna el sufijo numérico** a una herramienta nueva dentro de la
misma familia, la estructura visual no cambia — solo el código.
Anclar a código completo es frágil; anclar a prefijo + estructura es
robusto.

Aplica retroactivamente a las entradas que hoy usan códigos
completos. La auditoría se hizo al cerrar el recorrido — ver lista
de cambios al final del spec.

### A13 — Protocolo de mantenimiento "PDF inesperado"

Un PDF que **no alcanza `min_match` en ningún flavor** queda sin
contar como cover; la celda termina con conteo bajo y/o confianza
"Baja". Esto es **señal**, no falla — significa que apareció una
variante no registrada.

**Protocolo operativo** (documentado en
`tests/fixtures/scanners/README.md` y en el `DetailPanel` de la
celda afectada):

1. **Renderizar p1 del sospechoso** — botón "Ver portada" en el
   `DetailPanel` que reusa el visor pdf.js de Feature 1.
2. **Clasificar**:
   - **Variante de flavor existente** (mismo template, distinto
     código/revisión) → ampliar `anchors` del flavor.
   - **Template nuevo** (otro origen, otro contratista, otro
     hospital) → agregar nueva entrada a `cover_flavors`.
3. **Snapshot** del PDF a
   `tests/fixtures/scanners/<sigla>/<flavor>_p1_<descripción>.pdf`
   con ground truth en `ground_truth.json`
   (`{"covers_expected": N}`).
4. **Re-correr smoke** contra todos los fixtures (ver A15).
5. **Commit** con mensaje `fix(scanners/<sigla>): add <flavor>
   variant` que referencie el PDF observado.

Este protocolo **convierte sorpresa en mantenimiento previsible**.
Sin él, una variante nueva se traduce en un mes con celda en "Baja"
sin diagnóstico claro.

### A14 — Telemetría de "casi-match"

Para evitar que variantes nuevas pasen como **falso negativo
silencioso**, el scanner registra páginas que matchean
**`min_match - 1`** anchors en algún flavor como **candidatos a
flavor nuevo**.

Forma concreta:

```python
@dataclass
class ScanTelemetry:
    near_match_pages: list[NearMatch]   # min_match - 1 anchors

@dataclass
class NearMatch:
    pdf_path: str
    page_index: int           # 0-based
    flavor_name: str          # el más cercano
    matched_anchors: list[str]
    missing_anchors: list[str]  # los del flavor que no estaban
```

`ScanResult` lleva `telemetry: ScanTelemetry` (opcional, vacío si
no hay near-matches). La UI muestra un aviso en `DetailPanel`:

> "1 página parece una variante no registrada de `<flavor>`. Revisa:
> [botón Ver portada] [botón Marcar como nuevo flavor]"

El botón "Marcar como nuevo flavor" abre un diálogo que muestra los
anchors faltantes y permite copy-paste de un nuevo flavor stub para
`patterns.py`.

Sin A14, A13 es reactivo (solo se dispara cuando la celda baja a
"Baja"); con A14, A13 es proactivo (se dispara apenas asoma una
variante, incluso si el conteo sigue alto).

### A15 — Fixtures cumulativos por flavor

Cada vez que A13 agrega un flavor (o amplía anchors), se snapshotea
el sample real:

```
tests/fixtures/scanners/
├── README.md                              # documenta A13 + cómo agregar
├── <sigla>/
│   ├── ground_truth.json                  # {"flavor_name": covers_expected}
│   ├── f_lch_05_p1_aguasan.pdf            # 1 página, 1 cover esperada
│   ├── f_lch_05_p1_titan_chequeo.pdf
│   ├── f_ribeiro_p1.pdf
│   └── ...
└── ...
```

El smoke (`pytest tests/test_scanners.py`) recorre todos los
fixtures y verifica que el scanner cuente `covers_expected`. Si una
revisión futura del registro rompe un fixture, el test cae
inmediatamente apuntando al flavor culpable.

Beneficios:
- **Regresión protegida**: si Daniel agrega un anchor que era ruidoso
  y rompe un flavor ya cubierto, el smoke lo caza.
- **Auditoría visual**: cada PDF en `fixtures/` es un sample real
  observado; abrir la carpeta es ver el "universo conocido" del
  scanner.
- **Onboarding**: un colaborador entiende qué tipos de documento
  existen leyendo los fixtures.

## Patrones de anchor (cómo se construye un flavor)

Cinco patrones recurrentes detectados en el recorrido. Cada entrada
de categoría declara qué patrón(es) usa, sin re-justificar:

### P1 — Anchors específicos del template

Anclas tomadas del título + headers de sección + field-labels +
emisor del formulario. La estructura visual del template **es** la
señal. Aplica cuando la familia es estable y conocida.

Categorías: 2 irl, 3 odi, 4 charla, 5 chintegral, 6 dif_pts, 7 art,
9 bodega, 15 caliente, 17 andamios, 18 chps.

### P2 — Anchors por intersección estable entre templates

Cuando una sigla tiene **varios templates conocidos** (LCH-18 +
LCH-37 en cat 11 ext, LCH-31 + LCH-034 en cat 13 exc) y los
templates **comparten field-labels** específicos, el flavor usa esa
**intersección** como anchors. Tolera plantillas futuras que sigan
el mismo patrón estructural sin necesidad de agregar un flavor.

Categorías: 10 maquinaria, 11 ext, 13 exc.

### P3 — `pagination` fallback (cuenta "Página N de M" transitions)

Cuando el universo de templates es **demasiado heterogéneo** para
A2 pero **todos los templates declaran `"Página N de M"`**
correctamente, el scanner invoca `PaginationScanner` (reusa
`corner_count.count_paginations` — OCR esquina sup. der. + regex +
normalización de dígitos). No requiere mantener un registro de
flavors. Históricamente llamado `"v4"` — ver A6 para nota.

Categorías: 8 insgral, 14 altura.

### P4 — Edge cases out-of-scope manual

Cuando una sigla incluye documentos que NO son del template
canónico (UEO-01 y PSR-RG en cat 11 ext), se documentan como
**fuera del scope automático**: el operador los cuenta a mano vía
override. No se intenta cubrirlos con flavor — más caro de
mantener que valor que aporta.

Categorías: 11 ext.

### P5 — Full-page scan (`top_fraction=1.0`)

Cuando una sigla tiene **volumen mínimo** y **orientaciones mixtas**
no normalizables por la banda superior (cat 12 senal), el scanner
escanea la página completa. Costo alto pero volumen bajo lo
amortiza.

Categorías: 12 senal.

### P6 — Glob recursivo por subcarpetas

Cuando un hospital usa **subcarpetas por contratista** (HPV es el
caso típico), el glob debe ser recursivo
(`<categoria>/**/*.pdf`). Patrón consolidado en 9 categorías.

Categorías: 7 art, 8 insgral, 10 maquinaria, 11 ext, 12 senal,
14 altura, 15 caliente, 16 herramientas_elec, 17 andamios.

Declarado en `patterns.py` con `recursive_glob: True`.

## Metodología obligatoria — antes de fijar anclas

**Leer las primeras páginas (2-4) de un sample real**, no solo la página 1.
El encabezado del formulario (logo + título + "Constructora Región Sur SPA"
+ cuadro de código) **suele repetirse en las páginas interiores** de los
formatos CRS y NO sirve como ancla. Solo los **campos del formulario** son
cover-only — **pero verificar página a página**, porque hay formatos donde
las páginas interiores reproducen también los campos (caso `dif_pts` HLL,
ver A5 + categoría 6) y se necesitan anti-anchors.

En compilaciones multi-documento, las páginas interiores pueden ser:
- **otra portada** (caso normal de compilación) — la cuentan los anchors,
- **una página de test o evaluación con título distinto y mismos campos**
  (caso `dif_pts` HLL) — la descartan los anti-anchors (A5),
- **una hoja de firmas o tabla cruda sin header de formulario** (caso
  `charla` continuation) — no matchea los anchors, queda fuera sin trabajo
  extra.

Si después de los anchors propuestos quedan dudas sobre algún tipo de
página interior, **rendi­zar las páginas 1-4 del sample como PNG y leerlas**
antes de cerrar la entrada en este spec.

**Nota sobre calidad de PDF en samples vs producción.** Los PDFs en
`A:\informe mensual\ABRIL` están **comprimidos** para probar el flujo del
proyecto upstream; los PDFs originales (al momento del escaneo OCR
real) son de mayor calidad. Esto significa: si una lista de anclas
funciona bien sobre los samples comprimidos, funciona con margen en
producción. NO afinar las anclas para sobrevivir a OCR degradado más
allá de lo razonable — la verificación contra samples reales y los
totales mensuales es suficiente.

**Nota sobre orientación de PDFs (delegada upstream).** Varios samples
de HLL (cat 8 insgral, cat 9 bodega, cat 11 ext) vienen rotados 270°,
y `senal` (cat 12) tiene orientaciones mixtas (portrait, landscape,
"portrait ajustado de landscape"). **PDFoverseer NO implementa
normalización de rotación cardinal** — esa tarea está delegada a un
proyecto upstream separado que solo se ocupa de la normalización antes
de que los PDFs lleguen al pipeline de conteo. **Supuesto de
implementación**: los PDFs entran al scanner ya bien orientados. La
verificación contra los samples actuales de `A:\informe mensual\ABRIL`
puede fallar sobre los archivos rotados hasta que el upstream esté en
producción; los conteos esperados en este spec asumen orientación
correcta. Si un sample concreto requiere rotación, anotarlo como
limitación del entorno de test (no como bug del scanner).

## Plantilla por categoría

Cada entrada lleva: carpeta · volumen típico · modelo de conteo · scanner actual
· modos de falla observados (falsos verdes) · veredicto/enfoque · código
(compartido vs nuevo) · señal de validación.

Validación general: contra los **totales mensuales por (hospital, sigla)** que
contaron Daniel/Carla — NO hay ground truth per-PDF.

## Recorrido — orden de carpetas (1-18)

| #  | Carpeta                          | Sigla              | Estado                        |
|----|----------------------------------|--------------------|-------------------------------|
| 1  | Reunion Prevencion               | `reunion`          | ✅ decidido — sin refinamiento |
| 2  | Induccion IRL                    | `irl`              | ✅ decidido — anclas + "Página 1" |
| 3  | ODI Visitas                      | `odi`              | ✅ decidido — anclas (mismo enfoque que irl, anclas distintas) |
| 4  | Charlas                          | `charla`           | ✅ decidido — anclas (sin "Página 1 de" — template buggy) |
| 5  | Charla Integral                  | `chintegral`       | ✅ decidido — multi-flavor (CRS RCH + JAPA + PREVIENE) |
| 6  | Difusion PTS                     | `dif_pts`          | ✅ decidido — multi-flavor (CRS RCH + F-CH-CRS-01 + Aguasan), anti-anchors, top 1/3 |
| 7  | ART                              | `art`              | ✅ decidido — mono-flavor, defaults (1/4, sin anti-anchors); enumeración recursiva por subcarpetas HRB |
| 8  | Inspecciones Generales           | `insgral`          | ✅ decidido — pagination fallback (no A2), `scan_strategy: "pagination"` — generó A6 |
| 9  | Inspeccion Bodega                | `bodega`           | ✅ decidido — A2 mono-flavor + A7 (R1 lock para 1-pág) — generó A7 |
| 10 | Inspeccion de Maquinaria         | `maquinaria`       | ✅ decidido — A2 mono-flavor por intersección de field-labels (≥5 templates observados) — universo abierto |
| 11 | Extintores                       | `ext`              | ✅ decidido — A2 mono-flavor por intersección (LCH-18 + LCH-37); UEO-01 y PSR-RG fuera (manual) |
| 12 | Senaleticas                      | `senal`            | ✅ decidido — A2 mono-flavor F-CRS-LCH-22, `top_fraction=1.0` (full-page) por orientaciones mixtas + volumen mínimo |
| 13 | Excavaciones y Vanos             | `exc`              | ✅ decidido — A2 mono-flavor por intersección (LCH-31 + LCH-034) |
| 14 | Trabajos en Altura               | `altura`           | ✅ decidido — pagination fallback (universo de templates abierto); A7 absorbe ~80 PDFs 1-pág en R1 |
| 15 | Inspeccion Trabajos en Caliente  | `caliente`         | ✅ decidido — A2 mono-flavor uniforme F-LCH-CRS-3X; A7 absorbe ~38 1-pág |
| 16 | Inspeccion Herramientas Electricas | `herramientas_elec` | ✅ decidido — A2 multi-flavor (4 sabores: CRS estándar + TITAN + REALI + REG-SSO-HLL) + anti-anchor EPP; A7 absorbe los muchos 1-pág |
| 17 | Andamios                         | `andamios`         | ✅ decidido — A2 multi-flavor (2 sabores: F-CRS-LCH-05 + RIBEIRO 1cl-1890) + anti-anchor ART (TITAN_armado); A7 absorbe 1-pág; HLU = 0 docs (carpeta inexistente) |
| 18 | CHPS                             | `chps`             | ✅ decidido — A2 mono-flavor F-CRS-AR-01 ACTA DE REUNIÓN (mismo template que cat 1 `reunion`, distinguido por filename); anclas que diferencian p1 portada de p2/p3 continuación; volumen ínfimo (1/mes por hospital por DS-54) |

## Puntos separados del plan — S1-S3 (no son del conteo per-sigla)

### S1 — Overrides stale

Un `user_override` puede quedar más viejo que los archivos de su celda.
Detectado 2026-05-18 en `HLL/reunion`: estado guardado `user_override: 12`,
`manual_entry: true`, `override_note: null` — entrado por el flujo manual de
FASE 4 cuando HLL todavía no tenía carpeta de documentos. Ahora la carpeta real
`HLL/1.-Reunion Prevencion/` tiene 1 PDF y el 12 ficticio sigue ganando la
cascada de conteo. Un re-scan refresca `filename_count` pero **no** limpia el
override (es dato del usuario).

Mejora candidata: el scanner / la UI avisa cuando un override es más viejo que
los archivos de la celda — un "override stale" es otra forma de falso verde.
Alcance aparte del conteo per-sigla; se decide en el plan.

### S2 — Bajar la confianza "Baja" una vez verificado

Detectado 2026-05-19 en `irl` con ABRIL: R1 cuenta bien pero la celda mantiene
el tag "Baja" (probablemente por el flag `ocr_failed` heredado de un intento
de pase 2). No hay forma de decir "esto está OK, sácamelo de Baja". Mejora
candidata: un toggle "Marcar como verificado" en el `DetailPanel` que sube la
confianza a `HIGH` con audit `method="verified"`; un OCR exitoso después
también debería subirla automáticamente. Alcance aparte del conteo per-sigla.

### S3 — Alineación de la `FileList` con nombres largos

Detectado 2026-05-19: en la columna ARCHIVOS, cuando un nombre de PDF es muy
largo, empuja `Npp + Ndocs + OriginChip` y la fila se ve desordenada (Daniel
adjuntó screenshot en la conversación). Lo deseado: datos a la derecha
alineados y siempre visibles; solo el nombre se trunca/scrollea
horizontalmente dentro de su celda. Fix de CSS — probablemente `min-width:
0` + `overflow-x: auto` en el contenedor del nombre del archivo. UI pura,
sin relación con el conteo.

---

## Categorías

### 1 · `reunion` — Reunión de prevención

- **Carpeta:** `1.-Reunion Prevencion`
- **Volumen típico:** 0-2 por hospital/mes; rara vez a nunca más de un par.
- **Modelo de conteo:** 1 PDF = 1 reunión.
- **Scanner actual:** `SimpleFilenameScanner` (`filename_glob`).
- **Modos de falla:** ninguno propio del scanner. (El 12 de `HLL/reunion` era un
  override stale → ver S1; no es un fallo del conteo.)
- **Veredicto:** ✅ **SIN refinamiento.** `filename_glob` ya hace exactamente "1
  PDF = 1 reunión". El caso raro "varias reuniones en un solo PDF" se corrige a
  mano — trivial, no justifica OCR.
- **Código:** ninguno nuevo.
- **Validación:** nº de PDFs en la carpeta de la categoría = total.

### 2 · `irl` — Información de Riesgos Laborales

> **Nota nominal:** IRL se usa en el proyecto tanto para "Información de
> Riesgos Laborales" (el título impreso en la portada del documento) como
> para "Inspecciones de Riesgo Laboral" (la docstring actual del scanner).
> Daniel y la documentación reconocen ambas; **de aquí en adelante se usa
> "Información"**. La docstring se corregirá cuando se toque el scanner.

- **Carpeta:** `2.-Induccion IRL`
- **Volumen típico:** alto y variable — HPV 141, HRB 92, HLL 89, HLU 25.
- **Modelo de conteo:** **1 PDF = 1 inducción** (validado por Daniel en
  abril 2026: R1 cuenta bien). Caso compilación: varias inducciones en un
  mismo PDF — raro, pero ha ocurrido en el pasado; hay que cazarlo como red
  de seguridad.
- **Scanner actual:** `IrlScanner` extiende `HeaderDetectScanner` con
  `sigla_code="IRL"`. Pase 1 = `filename_glob` (funciona). Pase 2 (OCR) =
  busca `F-CRS-IRL/NN` en el 35 % superior cuando hay 1 PDF + flag
  `compilation_suspect`.
- **Bugs detectados en el path de compilación (todos cazados con muestras de
  HPV y HLU):**
  1. **El código de formulario real es `F-CRS-ODI-01`**, NO `F-CRS-IRL`. La
     IRL ("Información de Riesgos Laborales") usa la numeración interna
     "ODI" del CRS. `IrlScanner` arma el patrón `F-CRS-IRL-NN` → nunca
     matchea → siempre cae a `filename_glob` con flag `ocr_failed`.
  2. **El encabezado se repite en todas las páginas**: `F-CRS-ODI-01 /
     Rev.02 / Página X de N` aparece como header corrido en las ~31 páginas
     de cada inducción. `count_form_codes` cuenta páginas-con-código → para
     una inducción de 31 páginas devolvería 31, no 1. `header_detect` no
     aplica a este tipo de documento.
  3. **Disparador insuficiente**: `len(pdfs)==1` solo caza compilación
     cuando TODA la carpeta es un único PDF; el caso mixto (49 individuales
     + 1 compilación escondida) no se detecta. → Resuelto por A3.
- **Veredicto:** pase 1 (`filename_glob`) se queda — R1 funciona impecable
  para el caso normal. **Pase 2 se rediseña** con la técnica A2 (anclas en
  la banda superior). Regla: contar portadas = contar inducciones.
- **Anclas candidatas (banda superior, default 1/4), entran en `patterns.py`:**

  **Verificado leyendo página 2 de un sample real (corrige una mala
  suposición previa):** el encabezado completo se repite en TODAS las
  páginas. Por eso **NO sirven como anclas de portada**:
  - título `"INFORMACIÓN DE RIESGOS LABORALES"`
  - `"CONSTRUCTORA REGIÓN SUR SPA"`
  - cuadro de código de formulario (`F-CRS-ODI-01 / Rev / Fecha`)
  - banner `"DECRETO SUPREMO N° 44 Art. 15"`
  - encabezados de tabla `"ACTIVIDAD"` / `"PELIGRO / RIESGOS ASOCIADOS"` /
    `"MEDIDAS DE CONTROL"` / `"MÉTODOS O PROCEDIMIENTOS DE TRABAJO CORRECTO"`
    (en IRL repiten en página 2; en ODI Visita NO repiten — distinto por
    tipo, ver categoría 3)

  **Cover-only reales** (campos del formulario que solo aparecen en portada):
  - `"ANTECEDENTES GENERALES"`
  - `"FECHA DE REALIZACIÓN"`
  - `"TIEMPO DE DURACIÓN"`
  - `"HORARIO DE INICIO"` / `"HORARIO DE TÉRMINO"`
  - `"OBRA"` / `"TIPO DE INDUCCIÓN"`
  - `"IDENTIFICACIÓN DEL TRABAJADOR"` / `"IDENTIFICACIÓN DEL RELATOR"`
  - `"PERSONA TRABAJADORA NUEVA"` (uno de los 4 textos de las casillas en
    "TIPO DE INDUCCIÓN")
  - `"CON AUSENCIA PROLONGADA"`
  - `"REUBICADA/CON NUEVO CARGO"`
  - `"POR NUEVO PROCESO PRODUCTIVO"`
  - `"Página 1 de"` — el literal "1" solo matchea la portada; reusa el patrón
    "Página N de M" del V4 como un ancla más

  Regla de detección: una página es portada si tiene **≥ 3** de estos textos
  (tras normalización: sin acentos, lowercase, espacios y slashes
  colapsados). Redundancia alta → tolera OCR sucio mucho mejor que un único
  código.
- **Código:**
  - `IrlScanner` se reescribe usando A2; el `sigla_code="IRL"` desaparece
    (era para el `header_detect` descartado).
  - Las anclas y el patrón de filename viven en `patterns.py` (A1).
  - La técnica `header_band_anchors` (A2) la consumen los scanners que
    sigan este patrón de portada (probablemente la mayoría — confirmamos
    categoría por categoría).
- **Validación:** total de PDFs en la carpeta = total de inducciones (caso
  normal); en compilación, total de portadas detectadas = total de
  inducciones. Sanity-check contra los totales mensuales por
  (hospital, irl).

### 3 · `odi` — ODI Visitas (Obligación de Informar Visita)

- **Carpeta:** `3.-ODI Visitas`
- **Volumen típico:** medio-bajo. HPV 90 en abril; HLL marcada con "0" en
  el nombre de carpeta (sin visitas ese mes — el sufijo es convencional).
- **Modelo de conteo:** **1 PDF = 1 visita**. Cada PDF son 2 páginas
  (portada con datos + tabla de actividades; página 2 continúa la tabla más
  el bloque de EPP, OBSERVACIÓN, DECLARACIÓN y firmas). Caso compilación:
  varias visitas en un mismo PDF — mismo escenario que IRL, hay que cazarlo.
- **Scanner actual:** `OdiScanner` extiende `HeaderDetectScanner` con
  `sigla_code="ODI"`. Pase 1 = `filename_glob`. Pase 2 = busca
  `F-CRS-ODI-NN` cuando hay 1 PDF + flag compilación.
- **Bugs detectados en el path de compilación:**
  1. A diferencia de IRL, **el código sí matchea** — el formulario es
     `F-CRS-ODI-03` y el patrón `OdiScanner` con `sigla_code="ODI"` lo
     captura (`[\s\-_/]+` acepta el guion). No hay desajuste de nombre.
  2. **PERO el cuadro de código se repite en cada página** (en una visita
     de 2 páginas, aparece en p.1 con "Página 1 de 2" y en p.2 con "Página
     2 de 2"). `count_form_codes` cuenta páginas-con-código → para 1
     visita devolvería 2; para una compilación de 5 visitas devolvería 10.
     `header_detect` tampoco aplica aquí.
  3. Disparador `len(pdfs)==1` — mismo hueco que IRL (resuelto por A3).
- **Veredicto:** mismo enfoque que IRL — pase 1 (`filename_glob`) se queda;
  pase 2 se rediseña con la técnica A2. **Las anclas son distintas** porque
  es otro formulario.
- **Anclas candidatas (verificado leyendo página 2 de un sample):**

  **Repite en página 2 (NO sirve como ancla):** título `"OBLIGACIÓN DE
  INFORMAR VISITA"`, `"CONSTRUCTORA REGIÓN SUR SPA"`, cuadro de código
  `F-CRS-ODI-03 / Rev / Fecha`.

  **Cover-only reales:**
  - `"NOMBRE COMPLETO"` — campo del visitante
  - `"N° TELEFÓNICO"` — distintivo (el formulario de visita pide teléfono)
  - `"C. IDENTIDAD"`
  - `"EMPRESA"`
  - `"ACTIVIDAD"` — encabezado de columna; **en este formato NO se repite
    en página 2** (la tabla continúa sin re-cabecera)
  - `"PELIGRO / INCIDENTE POTENCIAL"` — encabezado de columna, texto muy
    específico de este formulario
  - `"MEDIDAS DE CONTROL"` — encabezado de columna; en ODI cover-only, en
    IRL repite (por eso `patterns.py` por tipo es la decisión correcta)
  - `"Página 1 de"`

  Constelación más distintiva: `NOMBRE COMPLETO + N° TELEFÓNICO + C.
  IDENTIDAD` — casi únicas de la portada de ODI Visita.

  Regla: ≥ 3 matches ⇒ portada (misma regla que IRL).
- **Código:** `OdiScanner` se reescribe usando A2. **Reusa exactamente la
  misma función `header_band_anchors`** que `IrlScanner`; lo único distinto
  es la entrada en `patterns.py`. Esto confirma la apuesta arquitectónica
  de A2 — un solo motor, N configuraciones.
- **Validación:** total de PDFs en la carpeta = total de visitas (normal);
  en compilación, total de portadas = total de visitas. Sanity contra
  totales mensuales por (hospital, odi).

### 4 · `charla` — Registro de Formación e Información (Charlas de Seguridad)

- **Carpeta:** `4.-Charlas`
- **Volumen típico:** **ALTO** — HPV 338, HRB ~89, HLU ~89, HLL ~677 PDFs
  en abril. La categoría más voluminosa del proyecto.
- **Modelo de conteo:** **1 PDF = 1 charla** (caso normal — `filename_glob`
  cuenta bien). Caso compilación: varias charlas en un mismo PDF.
- **Scanner actual:** `CharlaScanner` (NO extiende `HeaderDetectScanner`).
  Pase 1 = `filename_glob`. Pase 2 = `page_count_pure` — conteo de páginas
  vía PyMuPDF asumiendo "1 página = 1 charla".
- **Bugs detectados:**
  1. **La suposición "1 página = 1 charla" es falsa.** Las charlas tienen
     2+ páginas (portada con campos + 1 o más páginas de tabla de
     firmantes — un sample muestra una continuación con 35 filas para
     firmas). Una compilación de 5 charlas (2 pp c/u) son 10 páginas →
     `page_count_pure` devolvería 10, no 5.
  2. **El template está mal autorizado** y `"Página 1 de N"` no es
     confiable: hay páginas de continuación (rejilla de firmas, sin
     campos de cabecera del formulario) que también dicen "Página 1 de 2"
     (verificado con sample de Daniel). V4 con inferencia tampoco fue
     certero acá por esta misma razón. **`charla` es la excepción a la
     regla general** de incluir `"Página 1 de"` entre las anclas.
- **Veredicto:** pase 1 (`filename_glob`) se queda. **Pase 2 se rediseña**
  con la técnica A2 — mismo enfoque que IRL/ODI, distinta lista de anclas,
  sin `"Página 1 de"`. `page_count_pure` se descarta.
- **Anclas (banda superior, default 1/4 — campos del formulario):**

  El formulario tiene variantes: Rev 01 (2024) con `"Tiempo duración
  charla"` + `"Tipología de Charla/Reunión"` con casillas; Rev 03 (2025)
  con `"Hora de inicio"` + `"Hora de Término"` sin tipología. La lista
  cubre ambas; con la regla ≥ 3 matches, cualquier variante pasa.

  **Repite en cada página (NO sirve como ancla):** título `"REGISTRO DE
  FORMACIÓN E INFORMACIÓN"`, `"CONSTRUCTORA REGIÓN SUR SPA"`, cuadro de
  código `F-CRS-RCH-01`. Y crucialmente: `"Página 1 de N"` **NO se incluye**
  en charla por el bug del template (ver arriba).

  **Cover-only:**
  - `"Nombre de la Charla"` — todas las variantes
  - `"Obra"` — todas
  - `"Relator"` — todas
  - `"Cargo Relator"` — todas
  - `"Hora de inicio"` / `"Hora de Término"` — Rev 03+
  - `"Tiempo duración charla"` — Rev 01
  - `"Tipología de Charla/Reunión"` — Rev 01
  - `"Charla de Inducción"` / `"Charla Re-instrucción"` / `"Reunión de
    Coordinación"` / `"Difusión de Documentos"` — etiquetas de las
    casillas de tipología (Rev 01); textos largos y distintivos

  Match típico (cualquier variante): `Nombre de la Charla + Obra + Relator
  + Cargo Relator` ⇒ 4 anclas, supera ≥ 3 con margen.
- **Código:** `CharlaScanner` se reescribe — abandona `page_count_pure` y
  pasa a usar `header_band_anchors` (A2). **Reusa la misma función que
  `IrlScanner` y `OdiScanner`** (las tres siglas comparten motor; solo
  cambia la entrada en `patterns.py`). La entrada de charla omite
  explícitamente `"Página 1 de"` del set de anclas.
- **Validación:** total de PDFs en la carpeta = total de charlas (normal);
  en compilación, total de portadas detectadas = total de charlas. Sanity
  contra totales mensuales por (hospital, charla).
- **Nota — módulo ortogonal:** charla tiene además el conteo de
  TRABAJADORES firmantes (Feature 1, shipped 2026-05-17) que alimenta
  filas distintas del Excel a través del `WorkerCountViewer`. Acá nos
  ocupamos solo del conteo de CHARLAS (documentos), no de los firmantes.

### 5 · `chintegral` — Charla Integral

> **Esta sigla genera A4** (multi-flavor): los PDFs vienen en tres formatos
> completamente distintos. Daniel compartió 7 imágenes de muestra que
> cubren los tres flavors.

- **Carpeta:** `5.-Charla Integral`
- **Volumen típico:** bajo. HPV abril `chintegral · 6`; volúmenes similares
  en otros hospitales.
- **Modelo de conteo:** **1 PDF = 1 charla integral** (caso normal —
  `filename_glob` cuenta bien). Caso compilación: varias charlas integrales
  en un mismo PDF.
- **Scanner actual:** `SimpleFilenameScanner` (chintegral cae en los 14
  genéricos). Sin pase 2 OCR.
- **Veredicto:** pase 1 (`filename_glob`) se queda. **Se introduce un pase 2**
  con la técnica A2, **estructura multi-flavor A4** — 3 flavors.
- **Flavor A — CRS RCH (mismo formulario que `charla` regular):**

  F-CRS-RCH-01, título "REGISTRO DE FORMACIÓN E INFORMACIÓN" (o "REGISTRO
  DE CHARLA" en Rev 00 antigua). El contenido marca "Charla Integral" en
  el "Nombre de la Charla" o en la casilla "Charla Integral" de la
  Tipología. **Las anclas son las mismas que `charla`** — se reusa la
  constante `CRS_RCH_ANCHORS` de `patterns.py`. Sin `"Página 1 de"` (mismo
  template buggy que charla).
- **Flavor B — JAPA "Registro Capacitación":**

  Formulario distinto, emitido por la contratista JAPA. Anclas cover-only:
  - `"REGISTRO CAPACITACION"` — título, distintivo
  - `"Lugar"` — campo
  - `"TEMAS TRATADOS"` — sección
  - `"TIPO CHARLA"` — caja de tipo (texto distintivo)
  - `"CAPACITACION INTERNA"` / `"CAPACITACION EXTERNA"` — casillas
  - `"CHARLA INTEGRAL"` — casilla (literal en mayúsculas)
  - `"REINSTRUCCION"` / `"PROCEDIMIENTO"` / `"CHARLA 5 MINUTOS"` /
    `"PROTOCOLO"` — casillas
  - `"PERSONAL JAPA"` / `"SUBCONTRATO"` — caja al final
  - `"SOCIEDAD DE PROYECTOS DE INGENIERIA"` — pie del logo
- **Flavor C — PREVIENE (lista de asistencia del gobierno):**

  Documento del Plan de Acción Nacional de Drogas. Daniel no había visto
  este flavor; Carla confirma que cuenta como charla integral. Anclas
  cover-only:
  - `"PROGRAMA PREVIENE"` — título, distintivo
  - `"INFANCIA, JUVENTUD Y BIENESTAR"` — subtítulo
  - `"LISTA DE ASISTENCIA"` — sección
  - `"ESTRATEGIA NACIONAL DE DROGAS"` — banner
  - `"Región"`, `"Comuna"`, `"Espacio de Intervención"`, `"Número de
    asistentes"`, `"Componente"`, `"Temática"` — campos
- **Regla de detección:** ≥ 3 matches **dentro de un mismo flavor** ⇒
  portada. Si NINGÚN flavor alcanza ≥ 3, no es portada (aunque sume 5
  matches sueltos entre flavors distintos — ver A4 para el porqué).
- **Código:** sustituir `SimpleFilenameScanner` por un nuevo
  `ChintegralScanner` que reusa `header_band_anchors` (A2) con el
  dispatcher multi-flavor (A4). Al aparecer una nueva contratista con su
  propio template, basta con añadir un flavor a `patterns.py` —
  cero código nuevo en el scanner.
- **Validación:** total de PDFs en la carpeta = total de charlas integrales
  (normal); en compilación, total de portadas de **cualquier** flavor =
  total de charlas integrales. Sanity contra totales mensuales por
  (hospital, chintegral).

### 6 · `dif_pts` — Difusión PTS (Procedimiento Trabajo Seguro)

> **Esta sigla genera A5** (anti-anchors): las compilaciones de HLL tienen
> cover seguida de una página de test que **reproduce los campos del cover**
> (shadow cover), y hay que distinguirlas con anti-anchors. También
> introduce `top_fraction = 1/3` (A2) — los flavors B y C tienen campos
> cover-only más abajo que IRL/ODI.

- **Carpeta:** `6.-Difusion PTS`
- **Volumen típico:** medio. HPV abril `dif_pts · 18`. HLL **~889
  difusiones empacadas en un único PDF de 1779 páginas** (cover + test
  alternados; verificado leyendo páginas 1-4 de
  `A:\informe mensual\ABRIL\HLL\6.-Difusion PTS\2026-04_dif_pts.pdf`).
- **Modelo de conteo:** **1 difusión = 1 portada**. Caso normal (HPV / HRB /
  HLU): 1 PDF = 1 difusión, `filename_glob` cuenta bien. Caso HLL: 1 PDF
  gigante = N difusiones, detectar portadas internas via A2 + A5.
- **Scanner actual:** `SimpleFilenameScanner` (dif_pts cae en los 14
  genéricos). Sin pase 2 OCR.
- **Veredicto:** pase 1 (`filename_glob`) se queda. **Se introduce un pase
  2** con técnica A2, multi-flavor A4, anti-anchors A5, y `top_fraction =
  1/3`.

#### Flavor A — CRS RCH (mismo formulario que `charla` / `chintegral`)

Mayoritario en HPV / HRB / HLU. F-CRS-RCH-01, "REGISTRO DE FORMACIÓN E
INFORMACIÓN"; el campo "Nombre de la Charla" suele decir "DIFUSIÓN DE …" o
"PROCEDIMIENTO TRABAJO SEGURO EN … PTS-CRS-NN", y la casilla "Difusión de
Documentos" (o "Charla de Inducción" en algunos casos) está marcada en la
Tipología.

**Reusa exactamente `CRS_RCH_ANCHORS`** — cero anclas nuevas. Sin `"Página
1 de"` (mismo template buggy que charla). El `filename_glob` ya distingue
dif_pts de charla, así que el OCR de portada solo cuenta, no clasifica.

#### Flavor B — F-CH-CRS-01 "REGISTRO DE CHARLA" (compilaciones HLL)

**Verificado leyendo páginas 1-4 de un sample real (1779 págs).** Patrón
observado:

| PDF page | Tipo | Título | Código |
|----------|------|--------|--------|
| 1, 3, 5, … | cover | REGISTRO DE CHARLA | F-CH-CRS-01 |
| 2, 4, 6, … | test (shadow cover) | TEST TRABAJO EN ALTURA / TEST DE COMPRENSIÓN | F-PETS-CRS-XX-01 |

El test **reproduce todos los campos de identificación de la cover** (Nombre
de la Capacitación, Obra, Relator, Cargo Relator, Fecha, Tiempo duración
charla, tabla de firmas con 1 fila vs 10 en la cover). Diferencias:

- **Título:** "REGISTRO DE CHARLA" (cover) vs "TEST TRABAJO EN …" / "TEST
  DE COMPRENSIÓN" (test).
- **Código:** `F-CH-CRS-01` (cover) vs `F-PETS-CRS-XX-01` (test, donde XX =
  nº de PTS).
- **Cuerpo:** cover tiene "Se realiza difusión de …" + lista numerada
  (1. Objeto, 2. Alcance, …, Matriz de Riesgos); test tiene preguntas
  ("ENCIERRE EN UN CÍRCULO LA ALTERNATIVA CORRECTA", "VERDADERA / FALSA").

**Sin `"Página 1 de"`** — en este flavor el patrón aparece en el **test** (que
es estándar de 1 página), no en el cover (cuyo cuadro de código dice "Página
N de 23" con N variable). Anti-correlacionado; usarlo contaría tests.

```python
{
    "name": "f_ch_crs_01",
    "anchors": [
        "REGISTRO DE CHARLA",
        "Nombre de la Capacitación",
        "Cargo Relator",
        "Tiempo duración charla",
    ],
    "min_match": 3,
    "anti_anchors": [
        "TEST DE COMPRENSIÓN",
        "TEST TRABAJO EN",     # cubre "...EN ALTURA", "...EN CALIENTE", etc.
        "ALTERNATIVA CORRECTA",
        "F-PETS-CRS",          # prefijo del código del test (cover usa F-CH-CRS-01)
    ],
}
```

Geometría con `top_fraction = 1/3`:
- `"REGISTRO DE CHARLA"` y los títulos de test caen en el ~10 % superior.
- Campos de identificación (`Nombre de la Capacitación`, `Cargo Relator`,
  `Tiempo duración charla`) en el 20-30 %.
- `"F-CH-CRS-01"` / `"F-PETS-CRS"` en el cuadro de código (esquina sup.
  derecha, top 10 %).
- `"ALTERNATIVA CORRECTA"` ~30-35 % desde arriba — borde del top 1/3;
  queda como red. Las otras tres anti-anchors ya bastarían.

#### Flavor C — Aguasan

Contratista externa con template propio (código `SGT-06-F2`, título
"REGISTRO DE CHARLA Y CAPACITACIÓN"). 1 PDF = 1 capacitación,
autocontenido. No se han visto shadow pages en este flavor.

```python
{
    "name": "f_aguasan",   # ver A9
    "anchors": [
        "AGUASAN",
        "REGISTRO DE CHARLA Y CAPACITACIÓN",
        "CATEGORIA",
        "CHARLA ESPECÍFICA DIARIA",
        "CHARLA OPERACIONAL",
        "TOTAL PERSONAL ENTRENADO",
        "TEMA TRATADO",
    ],
    "min_match": 3,
}
```

#### Entrada completa en `patterns.py`

```python
"dif_pts": {
    "filename_glob": r"^.*dif_pts.*\.pdf$",   # ver A10
    "scan_strategy": "anchors",
    "top_fraction": 1/3,  # flavors B y C extienden el cover form más abajo
    "cover_flavors": [
        {"name": "f_rch",      "anchors": CRS_RCH_ANCHORS, "min_match": 3},   # ver A9
        {
            "name": "f_ch_crs_01",
            "anchors": [
                "REGISTRO DE CHARLA",
                "Nombre de la Capacitación",
                "Cargo Relator",
                "Tiempo duración charla",
            ],
            "min_match": 3,
            "anti_anchors": [
                "TEST DE COMPRENSIÓN",
                "TEST TRABAJO EN",
                "ALTERNATIVA CORRECTA",
                "F-PETS-CRS",
            ],
        },
        {
            "name": "f_aguasan",
            "anchors": [
                "AGUASAN",
                "REGISTRO DE CHARLA Y CAPACITACIÓN",
                "CATEGORIA",
                "CHARLA ESPECÍFICA DIARIA",
                "CHARLA OPERACIONAL",
                "TOTAL PERSONAL ENTRENADO",
                "TEMA TRATADO",
            ],
            "min_match": 3,
        },
    ],
},
```

- **Código:** scanner nuevo `DifPtsScanner` (sustituye al
  `SimpleFilenameScanner` actual). Internamente reusa `header_band_anchors`
  (A2) con dispatcher multi-flavor (A4) y soporte de anti-anchors (A5).
- **Validación:** total de PDFs en la carpeta = total de difusiones (normal);
  en compilación HLL, total de portadas Flavor B detectadas = total de
  difusiones. Sanity contra totales mensuales por (hospital, dif_pts).

### 7 · `art` — Análisis de Riesgos en el Trabajo (ART)

> **Mono-flavor con defaults** (sin A4, sin A5, `top_fraction=1/4`
> default) — primer caso del recorrido donde el "default path" basta.
> Template **F-CRS-ART-01 uniforme** entre hospitales y entre empresas;
> solo varían colores del logo y los datos rellenados.

- **Carpeta:** `7.-ART`
- **Volumen típico:** muy variable según hospital. Verificado leyendo
  páginas 1-4 de 3 samples reales (HPV CRS, HRB ALTOFEM, HLL
  compilación). La organización del filesystem cambia por hospital
  (ver "Nota de enumeración" abajo) pero el documento en sí es siempre
  el mismo template de 4 páginas.
- **Modelo de conteo:** **1 ART = 4 páginas** (`F-CRS-ART-01 / Rev. 02
  / Fecha 31/12/2025`, con paginación "Página 1 de 4" → "Página 4 de
  4"). 1 portada = 1 documento.
- **Scanner actual:** `SimpleFilenameScanner` (art cae en los 14
  genéricos). Sin pase 2 OCR. **No detecta** las compilaciones de HRB
  ni la mega-compilación de HLL.

#### Estructura del documento (verificado en 3 samples)

| Página | Contenido | Anchors de cover presentes |
|--------|-----------|----------------------------|
| 1 (cover) | Datos del supervisor / Área de Trabajo / Descripción / Hora / N° trabajadores / EPP / TRABAJOS CRÍTICOS / PERMISO DE TRABAJO / MATERIALES, HERRAMIENTAS Y EQUIPOS / PROTECCIONES COLECTIVAS / CONDICIONES DEL ÁREA DE TRABAJO | **sí** |
| 2 | Tabla `ETAPA DEL TRABAJO / PELIGROS Y RIESGOS PRESENTES / MEDIDAS PREVENTIVAS` (3 columnas) | no |
| 3 | Tabla `TOMA DE CONOCIMIENTO` (nombre / RUT / firma / empresa) | no |
| 4 | Tabla `CÓDIGOS DE COLOR` + `ESTÁNDARES, EXTENSIONES Y HERRAMIENTAS ELÉCTRICAS` + firma del supervisor | no |

El header del formulario (título `"ANÁLISIS DE RIESGOS EN EL TRABAJO
(ART)"`, logo, cuadro de código `"F-CRS-ART-01"` con el nº de página)
se repite en las 4 páginas → NO sirve como ancla. Solo los **campos
del formulario cover** son cover-only. Sin shadow cover (A5 no
necesario).

- **Veredicto:** pase 1 (`filename_glob`) se mantiene para HPV/HLU
  (1 PDF = 1 ART, ya cuenta bien). **Pase 2 con A2 + `top_fraction =
  1/4` default + mono-flavor + sin anti-anchors** para HRB
  (compilaciones por empresa) y HLL (compilación mensual). Anclas
  todas en el cuarto superior, con margen.

#### Anclas (banda superior 1/4)

- `"Nombre del Supervisor"` — top ~10 %, cover-only
- `"Área de Trabajo"` — top ~15 %, cover-only
- `"Descripción del trabajo a realizar"` — top ~18 %, cover-only y muy
  distintiva por la cadena larga
- `"Hora de Inicio de los trabajos"` — top ~22 %, cover-only
- `"N° de trabajadores involucrados"` — top ~22 %, cover-only
- `"Página 1 de"` — top ~5 %, cover-only en ART (p2/p3/p4 dicen
  "Página 2/3/4 de 4")

Regla: ≥ 3 matches ⇒ portada. Robustez amplia — si OCR pierde 2-3
anclas (sello sobre el header, manchas, etc.), las restantes pasan.

#### Entrada en `patterns.py`

```python
"art": {
    "filename_glob": r"^.*art.*\.pdf$",   # ver A10
    # top_fraction default 0.25; no override
    "cover_flavors": [
        {
            "name": "f_art_01",   # ver A9
            "anchors": [
                "Nombre del Supervisor",
                "Área de Trabajo",
                "Descripción del trabajo a realizar",
                "Hora de Inicio de los trabajos",
                "N° de trabajadores involucrados",
                "Página 1 de",
            ],
            "min_match": 3,
        },
    ],
},
```

#### Nota de enumeración — varía por hospital

La organización del filesystem para esta sigla NO es uniforme:

- **HPV / HLU**: flat — `7.-ART/2026-04-XX_art_*.pdf`, 1 PDF = 1 ART.
- **HRB**: subcarpetas por empresa —
  `7.-ART/<EMPRESA>/2026-05-XX_art_*.pdf` (ej. ALTOFEM, ALUMINIOS 2000,
  BSM, CPINOCHET, CRS, GENESIS, INSAP, JOGA, METTCO, P SAEZ). Cada
  PDF de subcarpeta es a su vez una mini-compilación de los ARTs de
  esa empresa para el mes (típicamente decenas de págs).
- **HLL**: un único PDF monolítico —
  `7.-ART/2026-04_art.pdf` = **4074 págs ≈ 1018 ARTs** del mes
  empacados.

El scanner necesita **enumerar recursivamente** `7.-ART/**` para incluir
los PDFs de las subcarpetas de HRB. Esto es un cambio en la capa de
enumeración del scanner, ortogonal al detector de portadas (A2 funciona
igual independientemente del layout del filesystem).

- **Código:** scanner nuevo `ArtScanner` que reusa `header_band_anchors`
  (A2) con `cover_flavors=[f_crs_art_01]`. Habilita el caso compilación
  para HRB y HLL. Glob recursivo en `7.-ART/**/*.pdf`.
- **Validación:** total de PDFs en `7.-ART/**` (caso HPV/HLU) = total de
  ARTs; en HRB, suma de portadas detectadas por PDF de subcarpeta =
  total ARTs; en HLL, total de portadas en el PDF gigante = total ARTs
  del mes. Sanity contra totales mensuales por (hospital, art).

### 8 · `insgral` — Inspecciones Generales (check-lists varios)

> **Estrategia de pase 2 = V4** (no A2) — primera sigla del recorrido
> donde los formularios son demasiado heterogéneos para anchors.
> Genera A6 (estrategia explícita por sigla). El denominador común es
> la paginación "Página N de M", exactamente lo que V4 fue diseñado
> para detectar.

- **Carpeta:** `8.-Inspecciones Generales`
- **Volumen típico:** bajo a medio. HPV: mix de flat + subcarpetas por
  empresa (AGUASAN, ALUMINIO 2000, ARAYA, HU, JAPA, JJC, MMG, REALI,
  STI, TITAN — igual estructura que ART). HRB: ~20 PDFs flat. HLU:
  4 PDFs flat. HLL: 1 archivo "monolítico" pero **solo 6 págs** = 1
  inspección larga, no compilación grande (contraste con dif_pts y
  art).
- **Modelo de conteo:** **1 portada = 1 inspección**. Portada =
  cualquier página con `"Página 1 de M"`:
  - PDF de 1 página `"Página 1 de 1"` → 1 inspección.
  - PDF multi-página (1 inspección de M págs) → portada solo p1.
  - **Compilación de N inspecciones de 1 pág** (caso HPV chequeos_epp:
    22 pp = 22 inspecciones, cada una `"Página 1 de 1"`) → cada página
    es portada.
- **Scanner actual:** `SimpleFilenameScanner`. No detecta compilaciones.

#### Variabilidad encontrada (10 samples × 4 hospitales)

| Sample | Template / Título | Págs | Orientación | "Página N de M" |
|--------|-------------------|------|-------------|------------------|
| HPV `chequeos_epp` | F-CRS-LCH-02 EPP | **22 (= 22 insp.)** | portrait | sí, "Página 1 de 1" en cada pág |
| HPV AGUASAN `comedores` | F-CRS-LCH-28 | 1 | portrait | sí |
| HPV HU `orden_y_aseo` | F-CRS-LCH-11 | 1 | portrait | sí |
| HRB `check_list_comedor` | (F-CRS-LCH similar) | 1 | portrait | sí |
| HRB `chequeo_botadero` | "Lista de Chequeo Botadero" (**no-CRS**) | 2 | **landscape** | **no** (usa "Doc N°") |
| HRB `hormigon` | "Lista de Chequeo Faenas Hormigón" (**no-CRS**) | 9 | **landscape** | **no** |
| HLU `chequeo_epp` | LCH-CRS-02 (= HPV) | 16 (= 16 insp.) | portrait | sí |
| HLU `orden_y_aseo` | LCH | 4 | portrait | sí |
| HLU `comedores` | F-CRS-LCH-28 | 1 | portrait | sí |
| HLL `2026-04_insgral.pdf` | F-CRS-LCH-23 Condiciones Generales de Obra | 6 (1 insp.) | **rotado 270°** | sí, "Página 1-6 de 6" |

Observaciones clave:
- **Plantillas dispares**: ≥ 4-5 templates CRS (F-CRS-LCH-02, -11, -23,
  -28) + templates no-CRS de subcontratistas. Anclas A2 requerirían un
  flavor por template = explosión combinatoria frágil.
- **Paginación universal en CRS**: cada inspección expone su propia
  paginación; el reset de M (o un nuevo "Página 1 de") marca inicio de
  inspección.
- **Templates no-CRS** (botadero, hormigon) usan "Doc N°" en lugar de
  "Página N de M" — V4 NO los cuenta. Aceptable según Daniel: son pocos
  y caen al **review manual** vía el override de FASE 2.
- **Orientaciones mixtas**: landscape (HRB botadero/hormigon) y
  rotación 270° (HLL). Landscape lo absorbe Tesseract sin problema;
  la rotación cardinal queda delegada al upstream (ver nota en
  Metodología) — el scanner asume PDFs bien orientados.
- **HLL es pequeño**: 6 págs ≈ 1 inspección, no compilación masiva.
  Volumen total bajo justifica el approach "V4 + review manual de no-CRS".

#### Veredicto: pase 2 = V4, NO A2

- **Pase 1** (`filename_glob`) se queda para HPV/HRB/HLU (1 PDF flat =
  1 inspección — caso común).
- **Pase 2 = pipeline V4** (`core/pipeline.py`): dispara cuando el
  usuario pide OCR explícitamente, o cuando un PDF supera el umbral
  típico (>1 págs → posible compilación). V4 hace OCR del cuarto
  superior, detecta "Página N de M", e infiere conteo de documentos via
  las 5 fases + Dempster-Shafer.
- **A3 (OCR per-PDF)** sigue aplicando — Daniel puede pedir V4 para un
  archivo individual desde la `FileList`.

#### Entrada en `patterns.py`

```python
"insgral": {
    "filename_glob": r"^.*insgral.*\.pdf$",   # ver A10
    "scan_strategy": "pagination",   # ver A6 (canónico; antes "v4")
    # sin cover_flavors — A2 no aplica
},
```

Necesario en el scanner glob: enumerar recursivamente
`8.-Inspecciones Generales/**/*.pdf` (HPV usa subcarpetas por empresa,
igual que ART — confirmando la nota de enumeración de cat 7).

#### Pre-requisitos de implementación

- **Sanity-check ejecutivo**: probar V4 sobre HPV `chequeos_epp.pdf`
  (debería devolver 22) y HLU `chequeo_epp.pdf` (16) antes de
  declarar el scanner listo. (Nota: el sample HLL `2026-04_insgral.pdf`
  está rotado 270° en `A:\informe mensual\ABRIL`; la normalización
  de rotación está delegada al upstream — ver nota en Metodología.
  Si el sample local no se corrige, no es un bug del scanner.)

#### Validación

Total de inspecciones detectadas = total mensual reportado por
Daniel/Carla. Los templates no-CRS (botadero, hormigon) NO se cuentan
automáticamente — quedan para `user_override` manual. Esto es
intencional: el volumen es lo bastante bajo para que el review manual
de los huecos compense la simplicidad del scanner.

### 9 · `bodega` — Inspección de Bodega (SUSPEL/RESPEL)

> **Genera A7** — regla de R1: los PDFs de 1 página se cuentan como 1
> documento y quedan locked (sin pase 2 disponible). Mono-flavor A2
> para los multi-página. La tabla `PLANILLA CONTROL DE RESIDUOS`
> (sample paralelo que mostró Daniel) queda **diferida** — no aparece
> en ABRIL. HLL viene rotado 270° en el sample local (igual que cat 8
> insgral); la normalización está delegada al upstream — ver nota en
> Metodología.

- **Carpeta:** `9.-Inspeccion Bodega`
- **Volumen típico:** **muy bajo**. ABRIL: HPV 1 PDF, HRB 2 PDFs
  (respel + suspel), HLU **no tiene carpeta** (sin inspecciones ese
  mes), HLL 1 PDF. Total mensual del proyecto ≈ 4 PDFs.
- **Modelo de conteo:** template `F-PETS-CRS-07-03 "CHEQUEO BODEGA
  SUSPEL/RESPEL"` **uniforme** entre hospitales; cada chequeo es
  **siempre 1 página** ("Página 1 de 1"). Compilaciones aparecen como
  PDFs multi-página donde **cada página es una portada/chequeo
  distinto** (a diferencia de irl/odi/art donde cada doc era 4+ págs).
  → El conteo correcto es "cuántas páginas matchean el template", no
  "cuántos PDFs hay".
- **Scanner actual:** `SimpleFilenameScanner`. No detecta compilaciones.

#### Patrón observado en samples ABRIL

| Sample | Págs | Orientación | Contenido |
|--------|------|-------------|-----------|
| HPV `chequeos_suspel_y_respel.pdf` | 4 | portrait | 4 chequeos F-PETS-CRS-07-03 compilados |
| HRB `respel.pdf` | **1** | portrait | 1 chequeo (R1 lo cuenta y bloquea — A7) |
| HRB `suspel.pdf` | **1** | portrait | 1 chequeo (R1 lo cuenta y bloquea — A7) |
| HLL `2026-04_bodega.pdf` | 2 | **rotado 270°** | 2 chequeos compilados |

Observaciones:
- Template uniforme entre hospitales (las dos primeras imágenes
  compartidas por Daniel son visualmente idénticas salvo datos
  rellenados).
- **≥ 50 % de los PDFs son 1-pág** → A7 los absorbe en R1 (counted=1
  + locked). Nunca llegan al dispatcher A2.
- **HLL rotado 270°** confirma el patrón observado en cat 8: HLL
  escanea documentos en sideways por defecto. La normalización está
  delegada al upstream — el scanner asume PDFs bien orientados (ver
  Metodología).
- Sin shadow covers, sin continuation pages. Caso A4/A5 N/A.

#### Otro flavor pendiente — PLANILLA CONTROL DE RESIDUOS

Daniel mostró un sample paralelo: logo `S·C·R·S` distinto del CRS
estándar, título `"PLANILLA CONTROL DE RESIDUOS EN BODEGA RESPEL"`,
tabla con columnas `Tipo de residuo / Lugar de Generación / Cantidad /
Lugar de Disposición / Volumen / Fecha`. **NO aparece en los samples de
ABRIL** — entra en algún mes puntual. Decisión diferida: añadir como
flavor adicional solo cuando aparezca regularmente. Por ahora no se
modela.

#### Veredicto

`scan_strategy = "anchors"` con mono-flavor + `top_fraction` default
1/4. A7 absorbe en R1 los 2 PDFs de HRB (1 pág c/u, locked); A2 corre
solo sobre HPV (4 pp) y HLL (2 pp) — 50 % del volumen total del mes.

#### Anclas (banda superior 1/4)

- `"CHEQUEO BODEGA SUSPEL/RESPEL"` — título, top ~5 %
- `"F-PETS-CRS-07-03"` — código de formulario, top ~5 %
- `"OBRA"` — etiqueta de campo, top ~12 %
- `"REALIZADO POR"` — etiqueta de campo, top ~16 %
- `"BODEGA SUSPEL"` — etiqueta de campo, top ~20 %
- `"BODEGA RESPEL"` — etiqueta de campo, top ~20 %

Regla: ≥ 3 matches ⇒ portada (= 1 chequeo). En PDFs multi-página,
**cada** página que cumpla la regla suma al conteo.

#### Entrada en `patterns.py`

```python
"bodega": {
    "filename_glob": r"^.*bodega.*\.pdf$",   # ver A10
    "scan_strategy": "anchors",
    "cover_flavors": [
        {
            "name": "f_pets_07_03",   # ver A9 (no-CRS-prefixed code preserved)
            "anchors": [
                "CHEQUEO BODEGA SUSPEL/RESPEL",
                "F-PETS-CRS-07-03",
                "OBRA",
                "REALIZADO POR",
                "BODEGA SUSPEL",
                "BODEGA RESPEL",
            ],
            "min_match": 3,
        },
    ],
},
```

#### Pre-requisitos de implementación

- A7 implementado en R1 (HRB respel/suspel son los casos de prueba
  canónicos: 1 pág → counted=1 + locked, sin botón de re-scan en la UI).
- Sin pre-requisito de rotación: el sample HLL local viene rotado 270°
  pero la normalización está delegada al upstream (ver Metodología).

#### Validación

Total de portadas detectadas = total de chequeos. ABRIL esperado:

| Hospital | PDFs | Páginas | Chequeos esperados | Cómo se cuenta |
|----------|------|---------|---------------------|----------------|
| HPV | 1 | 4 | 4 | A2 sobre las 4 págs |
| HRB | 2 | 1 + 1 | 2 | R1 trivial + locked en cada uno (A7) |
| HLU | 0 | — | 0 | sin carpeta |
| HLL | 1 | 2 | 2 | A2 (asumiendo PDF normalizado por upstream) |

Total proyecto: **8 chequeos**. Sanity contra totales mensuales por
(hospital, bodega).

### 10 · `maquinaria` — Inspección de Maquinaria (chequeos varios)

> **Primer caso con "universo de templates abierto"** — observamos ≥5
> templates distintos (F-CRS-LCH-08, -16, -26, -40, **LCH-CRS-07** con
> prefijo distinto), pero la **intersección de field-labels** es
> suficiente para anchors. Mono-flavor por intersección. Robustez
> diseñada para absorber templates futuros sin tocar `patterns.py`.

- **Carpeta:** `10.-Inspeccion de Maquinaria`
- **Volumen típico:** medio. HPV mix flat + subcarpetas por empresa
  (ARAYA, KOHLER, PERFORROTE — patrón ya conocido). HRB ~8 PDFs flat.
  HLU 2 PDFs. HLL 1 PDF compilación (14 págs, no rotado esta vez).
- **Modelo de conteo:** **1 portada = 1 chequeo**. Cada PDF puede ser:
  - 1-pág → 1 chequeo (cae en A7 R1 lock).
  - 2-pág form (caso F-CRS-LCH-16 grúa torre): 1 chequeo, p2 es
    continuación del checklist (sin field-labels de identificación).
  - N-pág compilación de 1-pág chequeos (caso HLU `chequeo_excavadora`
    5 pp = 5 chequeos, cada uno "Página 1 de 1").
  - N-pág compilación de 2-pág chequeos (caso HPV `grua_torres` 24 pp
    = 12 chequeos).
  - El counter de anchors absorbe todos los casos sin distinguir
    layout — cuenta páginas con ≥ N matches.
- **Scanner actual:** `SimpleFilenameScanner`. No detecta compilaciones.

#### Variabilidad observada (9 samples × 4 hospitales)

| Sample | Código | Identificación específica del template |
|--------|--------|-----------------------------------------|
| HPV `grua_torres` (24 pp) | F-CRS-LCH-16 GRÚA TORRE | TIPO MAQUINARIA · MARCA · **N° DE GRÚA** · OPERADOR · RUT |
| HPV `chilemaq` (4 pp) | F-CRS-LCH-08 MAQUINARIA GENERAL | TIPO MAQUINARIA · MARCA · **PATENTE** · OPERADOR · RUT |
| HPV ARAYA `excavadora` (1 pp) | F-CRS-LCH-26 EXCAVADORA | PATENTE · MARCA/MODELO · PERMISO · SOAP · REVISIÓN TÉCNICA · EMPRESA · AÑO · OPERADOR · RUT |
| HRB `grua_torre` (2 pp) | F-CRS-LCH-16 | igual a HPV grua_torres |
| HRB `alza` (24 pp) | **LCH-CRS-07** (prefijo distinto) PLATAFORMA ELEVADORA | TIPO MAQUINARIA · MARCA · PATENTE · OPERADOR · RUT |
| HRB `chequeo_general` (9 pp) | F-CRS-LCH-08 | igual a HPV chilemaq |
| HLU `excavadora` (5 pp) | F-CRS-LCH-26 | igual a HPV ARAYA excavadora |
| HLU `retroexcavadora` (5 pp) | (similar) | (similar) |
| HLL `2026-04_maquinaria` (14 pp) | F-CRS-LCH-40 RETROEXCAVADORA + otros | mismos campos vehiculares |

**Universo abierto**: cada empresa contratista puede traer su propia
variante (PERFORROTE, KOHLER, etc. en HPV subfolders sin chequear aún).
La estrategia debe ser robusta a nuevos templates sin updates de spec.

#### Intersección estable de anchors (presente en TODOS los templates)

- `"FECHA ÚLTIMA MANTENCIÓN"` — string largo, muy distintivo, cover-only
- `"NOMBRE OPERADOR"` — distintivo, cover-only
- `"RUT"` — short pero clásico label de campo
- `"MARCA"` — matchea también "MARCA/MODELO" como substring
- `"Página 1 de"` — cover-only universal (verificado en grua p2: la
  continuación dice "Página 2 de 2", no "1 de")

5 anchors, `min_match = 3`. Cualquier template observado matchea ≥ 4;
un template nuevo debería matchear ≥ 3 si mantiene los básicos (fecha
mantención + operador + paginación).

**Cover-only confirmado leyendo p2 de F-CRS-LCH-16 grúa**: la
continuación tiene el header del form (título + código + "Página 2 de
2") y el ITEM/ACTIVIDAD del checklist, **pero NO los field-labels de
identificación** (TIPO MAQUINARIA, FECHA ÚLTIMA MANTENCIÓN, NOMBRE
OPERADOR, RUT, MARCA). Los 5 anchors propuestos son seguros.

#### Veredicto

`scan_strategy = "anchors"` mono-flavor (por intersección, no por
template específico), `top_fraction` default 1/4.

#### Entrada en `patterns.py`

```python
"maquinaria": {
    "filename_glob": r"^.*maquinaria.*\.pdf$",   # ver A10
    "scan_strategy": "anchors",
    "cover_flavors": [
        {
            "name": "f_lch_xx",   # ver A9 — cubre F-CRS-LCH-* y F-LCH-CRS-* por intersección
            "anchors": [
                "FECHA ÚLTIMA MANTENCIÓN",
                "NOMBRE OPERADOR",
                "RUT",
                "MARCA",
                "Página 1 de",
            ],
            "min_match": 3,
        },
    ],
},
```

Glob recursivo `10.-Inspeccion de Maquinaria/**/*.pdf` (HPV
subcarpetas por empresa).

#### Validación

- A7 absorbe los PDFs de 1 pág en R1 (ej. HPV ARAYA `excavadora`,
  HRB `grua_torre.pdf` cuando es 1 pág, etc.).
- A2 corre sobre los multi-pág; cuenta páginas con ≥ 3 anchor matches.
- Total proyecto = suma. Sanity contra totales mensuales por (hospital,
  maquinaria).

**Caso de prueba canónico**: HLU `chequeo_excavadora.pdf` (5 pp, cada
uno "Página 1 de 1") debería devolver **5 chequeos**. Si V4 hubiera
sido la estrategia, este caso lo confunde (las paginaciones son
todas "1 de 1" — no hay reset que infiera boundaries). A2 con anchors
sí lo cuenta correctamente.

### 11 · `ext` — Extintores (chequeos)

> **A2 mono-flavor por intersección** (mismo patrón que cat 10
> maquinaria). Dos templates "CHEQUEO EXTINTORES" funcionalmente
> idénticos (F-CRS-LCH-18 emitido por Constructora; F-CRS-LCH-37
> emitido por Sociedad Concesionaria Región Sur S.A.) — comparten
> los field-labels de identificación. **Edge cases out-of-scope**:
> UEO-01 "ubicación en obra" (master-list) y forms third-party (PSR-RG
> de Sgs SPA) quedan para `user_override` manual.

- **Carpeta:** `11.-Extintores`
- **Volumen típico:** medio a alto en compilaciones, bajo en
  individuales. HPV: 1 PDF principal (15 pp compilado) + subcarpetas
  por empresa (ARAYA, JAPA, MMG, STI). HRB: 5 PDFs — 2 chequeos
  multi-pág + 1 third-party + 1 master-list + 1 individual. HLU: 1
  PDF (2 pp). HLL: 1 PDF (36 pp, rotado 270°).
- **Modelo de conteo:** **1 portada (CHEQUEO EXTINTORES) = 1
  extintor chequeado**. Cada chequeo cabe en 1 página → en una
  compilación de N págs hay N chequeos (cada página es portada).
  Mismo patrón que cat 9 bodega y cat 10 maquinaria.
- **Scanner actual:** `SimpleFilenameScanner`.

#### Variabilidad observada (7 samples × 4 hospitales)

| Sample | Código | Tipo de doc | Págs | Orientación |
|--------|--------|-------------|------|-------------|
| HPV `chequeos.pdf` (15 pp) | F-CRS-LCH-18 | chequeo individual × 15 compilados | 15 | portrait |
| HPV ARAYA + JAPA + MMG + STI | F-CRS-LCH-* | chequeos individuales por empresa | — | — |
| HRB `2026-04-01_check_list.pdf` | **PSR-RG-OO?** (third-party "Sgs SPA") | revisión externa con tabla de N extintores en 1 pág | 1 | portrait |
| HRB `chequeo.pdf` (47 pp) | F-CRS-LCH-18 | 47 chequeos compilados | 47 | portrait |
| HRB `ubicacion.pdf` (2 pp) | **F-CRS-UEO-01** | **master-list de extintores en obra** (no es chequeo per-extintor) | 2 | **landscape** |
| HLU `chequeo.pdf` (2 pp) | F-CRS-LCH-18 | 2 chequeos | 2 | portrait |
| HLL `2026-04_ext.pdf` (36 pp) | F-CRS-LCH-18 | 36 chequeos compilados | 36 | **rotado 270°** |
| Daniel's image | F-CRS-LCH-37 (SCRS) | chequeo individual emitido por Sociedad Concesionaria | 1 | portrait |

#### Observaciones

- **F-CRS-LCH-18 y F-CRS-LCH-37 son funcionalmente idénticos**: mismo
  título "CHEQUEO EXTINTORES", mismos field-labels de identificación
  (Ubicación del Extintor / Número de Serie del Extintor / Fecha de
  Vencimiento del Extintor / Tipo de Extintor). Solo cambia el emisor
  (Constructora vs Sociedad Concesionaria) — irrelevante para conteo.
- **F-CRS-UEO-01** es un **doc TYPE distinto**: tabla maestra con N
  rows (UBICACIÓN / TIPO / PESO / N° / PRÓXIMA MANTENCIÓN /
  OBSERVACIÓN). Cuántos extintores cuenta es ambiguo (1 doc? N
  filas?). **Decisión: fuera de anchors, manual override**.
- **PSR-RG (third-party)** también queda **fuera de anchors** — un
  proveedor externo con su propio template; volumen anecdótico.
- **HLL rotado 270° por tercera vez** (cat 8, 9, 11) en los samples
  locales. La normalización está delegada al upstream — ver
  Metodología. El scanner asume PDFs bien orientados.

#### Veredicto

`scan_strategy = "anchors"` mono-flavor por intersección de LCH-18 +
LCH-37. `top_fraction` default 1/4 (los field-labels de identificación
están en el ~30 % superior, pero la lista tiene redundancia ≥ 4 anclas
en top 1/4).

#### Anclas (banda superior 1/4)

- `"CHEQUEO EXTINTORES"` — título universal LCH-18/LCH-37
- `"Ubicación del Extintor"` — field-label
- `"Número de Serie del Extintor"` — field-label
- `"Fecha de Vencimiento del Extintor"` — field-label
- `"Tipo de Extintor"` — substring que cubre "Tipo de Extintor de
  incendios" (puede caer al borde de 1/4)
- `"Página 1 de"` — cover-only (cada chequeo es "Página 1 de 1")

≥ 3 matches ⇒ portada. Cualquier compilación LCH-18/LCH-37 matchea
4-5 anclas por página → robusto.

#### Entrada en `patterns.py`

```python
"ext": {
    "filename_glob": r"^.*ext.*\.pdf$",   # ver A10
    "scan_strategy": "anchors",
    "cover_flavors": [
        {
            "name": "f_lch_xx",   # ver A9 — cubre LCH-18 + LCH-37 por intersección
            "anchors": [
                "CHEQUEO EXTINTORES",
                "Ubicación del Extintor",
                "Número de Serie del Extintor",
                "Fecha de Vencimiento del Extintor",
                "Tipo de Extintor",
                "Página 1 de",
            ],
            "min_match": 3,
        },
    ],
},
```

Glob recursivo `11.-Extintores/**/*.pdf` (HPV subcarpetas por empresa,
patrón ya conocido).

#### Edge cases (out-of-scope para A2 — manual)

- **F-CRS-UEO-01 "ubicación en obra"** (HRB `ubicacion.pdf`): un
  master-list-table; no cae en los anchors → A2 retorna 0 sobre ese
  PDF → Daniel ajusta con `user_override`. Daniel: "no son tantos".
- **PSR-RG third-party** (HRB `2026-04-01_check_list.pdf` u otros):
  template externo, A2 retorna 0 → manual override.
- **A7 R1 lock** absorbe los 1-pág triviales (incluido el PSR-RG si
  llega como 1 pág — counted=1, locked, sin necesidad de OCR; si la
  cuenta real era distinta, Daniel ajusta con override).

#### Validación

Total = anchors-matches sobre todos los PDFs (excluyendo los
out-of-scope). Sanity contra totales mensuales por (hospital, ext).
Daniel ajusta con override para los pocos casos UEO-01 y third-party.
El sample HLL local viene rotado 270° (delegado al upstream — ver
Metodología); el scanner asume PDFs ya normalizados.

### 12 · `senal` — Señaléticas (lista de chequeo de seguridad)

> **Primer caso con `top_fraction = 1.0`** (full-page scan) — volumen
> mínimo (4 PDFs en todo ABRIL) y orientaciones mixtas (portrait,
> landscape, "portrait ajustado de landscape") justifican OCR'ear toda
> la página por simplicidad. Template **F-CRS-LCH-22** uniforme entre
> samples.

- **Carpeta:** `12.-Senaleticas` (algunos hospitales con suffix `0` en
  el nombre indican "sin inspecciones ese mes").
- **Volumen típico:** **muy bajo**. ABRIL: HPV 1 PDF + 2 subcarpetas
  (MMG, REALI), HRB **sin carpeta** (`Senaleticas 0`), HLU **sin
  carpeta** (`Senaleticas 0`), HLL 1 PDF. **Total proyecto: 4 PDFs**.
- **Modelo de conteo:** **1 portada (LISTA DE CHEQUEO DE SEÑALÉTICA)
  = 1 inspección**. Cada chequeo cabe en 1 página → en compilación,
  cada página es portada.
- **Scanner actual:** `SimpleFilenameScanner`.

#### Patrón observado (4 samples = todo el universo de ABRIL)

| Sample | Págs | Orientación | Template |
|--------|------|-------------|----------|
| HPV `chequeos.pdf` | 6 | portrait (1275×1650) | F-CRS-LCH-22 |
| HPV MMG `senal_mmg.pdf` | 1 | **landscape** (1755×1240) | F-CRS-LCH-22 |
| HPV REALI `senal_chequeo_de_seguridad.pdf` | 4 | p1-2 "portrait ajustado de landscape" (1275×1008); p3 portrait | F-CRS-LCH-22 |
| HLL `2026-04_senal.pdf` | 31 | **landscape** (1650×1275) | F-CRS-LCH-22 |

**Template uniforme**: todos los samples usan F-CRS-LCH-22 "LISTA DE
CHEQUEO DE SEÑALÉTICA DE SEGURIDAD" de Constructora Región Sur SpA.
Mono-flavor con margen.

**Orientaciones mixtas**: portrait, landscape, "portrait ajustado de
landscape" (el form fue maquetado horizontal pero el PDF se exportó en
portrait con el contenido ocupando solo la parte media superior). Esto
hace que el cuarto superior (`top_fraction = 0.25`) pueda cortar
field-labels en algunas orientaciones.

#### Veredicto

`scan_strategy = "anchors"` mono-flavor con **`top_fraction = 1.0`
(full-page)**. Justificación:
- Volumen mínimo (4 PDFs, máx 31 págs en HLL) → costo OCR adicional
  despreciable.
- Orientaciones mixtas → escanear toda la página garantiza que los
  field-labels caen siempre dentro del área OCR'ada.
- Simplicidad: sin tunear `top_fraction` por subcaso de orientación.

#### Anclas (full page)

- `"LISTA DE CHEQUEO DE SEÑALÉTICA"` — título distintivo (subset de
  "DE SEGURIDAD")
- `"Zona/Área"` — field label
- `"Persona(s) que realiza la inspección"` — label largo distintivo
- `"Código de Registro PGS"` — label distintivo
- `"CUMPLE"` — encabezado columna de la tabla
- `"FOTOGRAFÍA"` — encabezado columna
- `"Inspección realizada por"` — etiqueta de firma (bottom)
- `"Página 1 de"` — cover-only (cada chequeo es 1 pág)

8 anchors, `min_match = 3`. Robusto con margen.

#### Entrada en `patterns.py`

```python
"senal": {
    "filename_glob": r"^.*senal.*\.pdf$",   # ver A10
    "scan_strategy": "anchors",
    "top_fraction": 1.0,  # full-page por orientaciones mixtas + volumen mínimo
    "cover_flavors": [
        {
            "name": "f_lch_22",   # ver A9
            "anchors": [
                "LISTA DE CHEQUEO DE SEÑALÉTICA",
                "Zona/Área",
                "Persona(s) que realiza la inspección",
                "Código de Registro PGS",
                "CUMPLE",
                "FOTOGRAFÍA",
                "Inspección realizada por",
                "Página 1 de",
            ],
            "min_match": 3,
        },
    ],
},
```

Glob recursivo `12.-Senaleticas/**/*.pdf` (HPV usa subcarpetas).

#### Validación

Total = anchors-matches por página sobre los 4 PDFs. Sanity contra
totales mensuales por (hospital, senal). HRB y HLU = 0 (sin carpeta).

### 13 · `exc` — Excavaciones y Vanos

> **A2 mono-flavor por intersección** (mismo patrón que cat 10
> maquinaria + cat 11 ext). Dos templates `F-CRS-LCH-31` "CHEQUEO
> EXCAVACIONES Y VANOS" (HPV, HRB, HLU) y `F-CRS-LCH-034` "CHEQUEO
> PROCEDIMIENTO DE EXCAVACIONES" (HLL) comparten field-labels
> esenciales y el keyword `"EXCAVACIONES"` en el título.

- **Carpeta:** `13.-Excavaciones y Vanos`
- **Volumen típico:** bajo. ABRIL: HPV 1 PDF (23 pp compilado), HRB
  1 PDF (2 pp), HLU 1 PDF (5 pp), HLL 1 PDF (21 pp). Total: 4 PDFs.
- **Modelo de conteo:** **1 portada = 1 chequeo**. Cada chequeo
  cabe en 1 página ("Página 1 de 1") → en compilación, cada página
  es portada (mismo patrón que cat 9 bodega, cat 10 maquinaria, cat
  11 ext).
- **Scanner actual:** `SimpleFilenameScanner`.

#### Variabilidad observada (4 samples = todo ABRIL)

| Sample | Código | Título | Fields de identificación |
|--------|--------|--------|--------------------------|
| HPV `chequeos.pdf` (23 pp) | F-CRS-LCH-31 | "CHEQUEO EXCAVACIONES Y VANOS" | OBRA · SECTOR INSPECCIONADO · FECHA · NOMBRE QUIEN HACE LA INSPECCIÓN · CARGO |
| HRB `chequeo.pdf` (2 pp) | F-CRS-LCH-31 | (igual) | (igual) |
| HLU `chequeo.pdf` (5 pp) | F-CRS-LCH-31 | (igual) | (igual) |
| HLL `2026-04_exc.pdf` (21 pp, rotado 270°) | F-CRS-LCH-034 | "CHEQUEO PROCEDIMIENTO DE EXCAVACIONES" | SECTOR INSPECCIONADO · OBRA · INSPECCIÓN REALIZADA POR · FECHA · FIRMA · CARGO |

**Intersección estable**:
- `"EXCAVACIONES"` — keyword en ambos títulos, muy distintivo de esta
  sigla.
- `"SECTOR INSPECCIONADO"` — field-label largo, distintivo.
- `"OBRA"` / `"FECHA"` / `"CARGO"` — etiquetas cortas pero estándar.
- `"Página 1 de"` — universal cover-only.

**Variable** (no usar como anchor):
- `"NOMBRE QUIEN HACE LA INSPECCIÓN"` (solo LCH-31) vs
  `"INSPECCIÓN REALIZADA POR"` (solo LCH-034).

#### Veredicto

`scan_strategy = "anchors"` mono-flavor por intersección, `top_fraction`
default 1/4. Los field-labels caen todos en el cuarto superior.

#### Anclas (banda superior 1/4)

- `"EXCAVACIONES"` — keyword del título, alta especificidad
- `"SECTOR INSPECCIONADO"` — field-label largo distintivo
- `"OBRA"` — etiqueta de campo
- `"FECHA"` — etiqueta de campo
- `"CARGO"` — etiqueta de campo
- `"Constructora Región Sur SpA"` — subtítulo (todos los chequeos son
  1-pág → sin riesgo de match en continuation)
- `"DESCRIPCIÓN"` — encabezado de columna de la tabla
- `"Página 1 de"` — cover-only

8 anchors, `min_match = 3`. Robusto.

#### Entrada en `patterns.py`

```python
"exc": {
    "filename_glob": r"^.*exc.*\.pdf$",   # ver A10
    "scan_strategy": "anchors",
    "cover_flavors": [
        {
            "name": "f_lch_xx",   # ver A9 — cubre LCH-31 y LCH-034 por intersección
            "anchors": [
                "EXCAVACIONES",
                "SECTOR INSPECCIONADO",
                "OBRA",
                "FECHA",
                "CARGO",
                "Constructora Región Sur SpA",
                "DESCRIPCIÓN",
                "Página 1 de",
            ],
            "min_match": 3,
        },
    ],
},
```

#### Validación

Total = anchors-matches por página. Sanity contra totales mensuales
por (hospital, exc). HLL viene rotado 270° en el sample local —
delegado al upstream (ver Metodología).

### 14 · `altura` — Trabajos en Altura

> **`scan_strategy = "pagination"`** (segunda sigla tras `insgral` cat 8 con
> pagination fallback). El universo de templates es **excepcionalmente
> abierto**: cada empresa contratista trae su propio paquete (CRS,
> SCRS, AGUASAN, TITAN, REALI, JAPA, JJC, ALUMINIO 2000, Ribeiro), y
> dentro de cada paquete hay varios tipos de chequeo (arnés, escala,
> andamios, verificación carrera, línea de vida, ESLINGAS, …). Ni
> siquiera la intersección de field-labels es estable. El
> denominador común es la paginación. **A7 absorbe en R1 los muchos
> PDFs 1-pág** (aprox. 50 % del volumen) sin tocar OCR.

- **Carpeta:** `14.-Trabajos en Altura`
- **Volumen típico:** **el más alto del recorrido**. ABRIL: **170
  PDFs, 1210 págs** repartidos así:
  - HPV ~150 PDFs en 6+ subcarpetas por contratista (AGUASAN 38,
    TITAN 66, REALI 22, JAPA 5, JJC 12, ALUMINIO 2000 1, +2 root).
  - HRB 9 PDFs (4 Ribeiro 1-pág + 5 "CHEQUEO LINEA DE VIDA" 3-pág).
  - HLU **0** (sin carpeta — `14.-Trabajos en Altura 0`).
  - HLL 1 PDF monolítico de **770 pp / 171 MB**, rotado 270°.
- **Modelo de conteo:** **1 chequeo = N páginas** según template (1
  pág para arnés y verificación carrera, 2 pág para escala
  unipersonal, 3 pág para línea de vida, 3-6 pág para chequeos
  internos de contratista, etc.). V4 infiere boundaries por reset
  de paginación "Página N de M".

#### Variabilidad observada — universo MUY abierto

**Templates CRS/SCRS (los "buenos"):**
- F-PETS-CRS-01-01 "LISTA DE CHEQUEO PARA TRABAJOS EN ALTURA" (3 pp,
  emitido por Sociedad Concesionaria).
- F-CRS-LCH-03 "CHEQUEO DE ARNÉS DE SEGURIDAD" (1 pp, emitido por
  Constructora).

**Templates por contratista en HPV (paquetes propios)**, cada
contratista trae varios tipos de chequeo:
- AGUASAN: escala unipersonal (2 pp), arnés (1 pp), esmeril angular
  (1 pp), andamios (1 pp).
- TITAN: arnés (1-2 pp), escalas (1-2 pp), titan-principal (3-6 pp),
  verificación carrera (1-2 pp), andamios.
- REALI: arnés (2-14 pp compilado), reali-principal (3-9 pp).
- JAPA: paquete único (4 pp consistente).
- JJC: arnés (1 pp mayoría).

**Templates Ribeiro (HRB, baja calidad)**:
- "LISTA DE VERIFICACIÓN TRABAJO EN ALTURA" 1CL-1890 (1 pp).
- "LISTA DE VERIFICACIÓN ACCESORIOS DE LEVANTE 'ESLINGAS'" 1CL-1890
  (3 pp, casi idénticas).
- Subcarpeta `CHEQUEO LINEA DE VIDA/` (5 PDFs, 3 pp c/u).

**Decisión transversal**: anchors específicos no escalan (≥ 10
paquetes distintos) y la intersección de field-labels no existe (los
temas son disjuntos: arnés ≠ escala ≠ andamios ≠ ESLINGAS ≠ línea
de vida). Pero **la paginación "Página N de M" es universal** —
exactamente el caso de uso de V4.

- **Scanner actual:** `SimpleFilenameScanner`.
- **Veredicto:** `scan_strategy = "pagination"`. Mismo enfoque que `insgral`
  (cat 8), con la ventaja de que A7 ya absorbe los muchos PDFs de
  1-pág en R1 antes de que V4 sea invocado.

#### Cómo se cuenta el volumen real

| Hospital | PDFs | Cómo se cuenta |
|----------|------|----------------|
| HPV | ~150 | Mitad ~75 PDFs 1-pág (A7 R1 lock); resto ~75 multi-pág → V4 |
| HRB | 9 | 4 Ribeiro 1-pág → A7; 5 LINEA DE VIDA 3-pág → V4 |
| HLU | 0 | sin carpeta |
| HLL | 1 (770 pp) | V4 sobre el PDF gigante; cada inspección dentro se cuenta por reset de paginación |

A7 (R1) absorbe aprox. **80 PDFs** sin tocar OCR. V4 se ejecuta solo
sobre los ~90 multi-pág.

#### Entrada en `patterns.py`

```python
"altura": {
    "filename_glob": r"^.*altura.*\.pdf$",   # ver A10
    "scan_strategy": "pagination",   # universo de templates abierto; pagination cuenta transiciones (canónico; antes "v4")
    # sin cover_flavors — anchors no aplica
},
```

Glob recursivo `14.-Trabajos en Altura/**/*.pdf` (HPV subcarpetas por
contratista + HRB `CHEQUEO LINEA DE VIDA/` subcarpeta).

#### Pre-requisitos de implementación

- **Sanity-check ejecutivo**: probar V4 sobre HPV
  `chequeos_arnes_de_seguridad.pdf` (18 pp, contratista esperado) y
  REALI `2026-04-20_altura_chequeo_arnes_de_seguridad_reali.pdf`
  (12 pp). Si V4 devuelve un conteo razonable contra el total
  mensual, listo.
- **HLL caveat**: el sample local de 770 pp está rotado 270° —
  normalización delegada al upstream (ver Metodología). En producción
  V4 debería contar bien.

#### Validación

Total = A7 (1-pág) + V4 (multi-pág). Sanity contra totales mensuales
por (hospital, altura). El volumen es el mayor del recorrido, por lo
que cualquier error sistémico se notará en el override manual rápido.
Si V4 subcuenta en los Ribeiro de mala calidad o en contratistas con
templates raros, Daniel ajusta con override (acotado al subconjunto
problemático, no al universo entero).

### 15 · `caliente` — Inspección Trabajos en Caliente

> **A2 mono-flavor uniforme** — la sigla "más regular" del recorrido:
> template `F-LCH-CRS-3X` "CHEQUEO TRABAJOS EN CALIENTE" idéntico
> entre los 4 hospitales **Y** entre los contratistas (AGUASAN,
> TITAN, JAPA, STI, HU). Cada chequeo es 1 página ("Página 1 de 1").
> Anchors estándar en cuarto superior. A7 absorbe en R1 los muchos
> 1-pág.

- **Carpeta:** `15.-Inspeccion Trabajos en Caliente`
- **Volumen típico:** alto. ABRIL: HPV ~50 PDFs (root + 5 subcarpetas
  por contratista), HRB 4 PDFs (con compilaciones grandes 21+21+10+2),
  HLU 1 PDF (2 pp), HLL 1 PDF de **298 pp rotado 270°**. Total
  estimado ~430 chequeos.
- **Modelo de conteo:** **1 portada = 1 chequeo = 1 página**.
  Compilaciones tienen N páginas = N chequeos (cada uno "Página 1 de
  1"). Mismo patrón que cat 9 bodega, cat 10 maquinaria, cat 11 ext,
  cat 13 exc.
- **Scanner actual:** `SimpleFilenameScanner`.

#### Patrón observado (samples × 4 hospitales)

| Sample | Págs | Template |
|--------|------|----------|
| HPV `chequeos.pdf` | 19 | F-LCH-CRS-32 compilados |
| HPV TITAN (varios) | 1-2 | F-LCH-CRS-32 (varias revisiones) |
| HPV STI `chequeo_sti.pdf` | 6 | F-LCH-CRS-32 compilados |
| HPV AGUASAN (17 PDFs) | 1 c/u | F-LCH-CRS-32 — todos 1-pág → A7 absorbe |
| HPV JAPA (5 PDFs) | 1 c/u | F-LCH-CRS-32 → A7 absorbe |
| HRB `chequeo_soldadora.pdf` | 21 | F-LCH-CRS-32 compilados |
| HRB `trab.pdf` | 21 | F-LCH-CRS-32 compilados |
| HLU `chequeos.pdf` | 2 | F-LCH-CRS-32 |
| HLL `2026-04_caliente.pdf` | **298** | F-LCH-CRS-36 (rev distinta) compilados (rotado 270°) |

**Observaciones**:
- Template universal: todos los samples usan `F-LCH-CRS-3X` (sufijo
  varía entre revisiones: -32 más común, -36 en HLL).
- **Sin field-labels de identificación en el header** (a diferencia
  de las otras siglas tipo chequeo). El cuarto superior contiene
  solo título + código + table headers (ITEM/ACTIVIDAD/CUMPLE) +
  posiblemente el primer item. Los datos de obra/firma/fecha están
  al pie.
- HLL rotado 270° (sexta sigla con este patrón) — delegado upstream
  (ver Metodología).

#### Veredicto

`scan_strategy = "anchors"` mono-flavor, `top_fraction` default 1/4.
A7 absorbe los muchos PDFs 1-pág (estimado ~38 entre AGUASAN, JAPA,
HU, TITAN-1pp). A2 corre solo sobre las compilaciones.

#### Anclas (banda superior 1/4)

- `"CHEQUEO TRABAJOS EN CALIENTE"` — título universal y distintivo
- `"CONSTRUCTORA REGIÓN SUR SPA"` — subtítulo (sin riesgo de
  continuation: 1-pág por chequeo)
- `"F-LCH-CRS"` — prefijo de código (cubre -32 y -36)
- `"ITEM"` — encabezado de tabla
- `"ACTIVIDAD"` — encabezado de tabla
- `"CUMPLE"` — encabezado de columna
- `"esmeril angular"` — texto del item 1 (universal — verificado en
  HPV, HRB, HLL)
- `"Página 1 de"` — cover-only universal

8 anchors, `min_match = 3`. Robusto con margen.

#### Entrada en `patterns.py`

```python
"caliente": {
    "filename_glob": r"^.*caliente.*\.pdf$",   # ver A10
    "scan_strategy": "anchors",
    "cover_flavors": [
        {
            "name": "f_lch_3x",   # ver A9 — cubre F-LCH-CRS-32 + -36
            "anchors": [
                "CHEQUEO TRABAJOS EN CALIENTE",
                "CONSTRUCTORA REGIÓN SUR SPA",
                "F-LCH-CRS",
                "ITEM",
                "ACTIVIDAD",
                "CUMPLE",
                "esmeril angular",
                "Página 1 de",
            ],
            "min_match": 3,
        },
    ],
},
```

Glob recursivo `15.-Inspeccion Trabajos en Caliente/**/*.pdf` (HPV
subcarpetas por contratista — patrón ya conocido).

#### Validación

Total = A7 (1-pág) + A2 anchor-matches (multi-pág). Sanity contra
totales mensuales por (hospital, caliente). HLL viene rotado 270° —
delegado upstream.

---

### 16 · `herramientas_elec` — Inspección Herramientas Eléctricas

> **A2 multi-flavor (4 sabores) con anti-anchor EPP** — la sigla con
> mayor heterogeneidad de templates del recorrido. La familia CRS
> estándar absorbe ~90% del corpus con anclas estructurales
> invariantes (header `CONSTRUCTORA REGIÓN SUR` + tabla
> `ITEM/ACTIVIDAD/CUMPLE`); los 3 sabores restantes cubren minorías
> bien delimitadas (TITAN-only en HPV, REALI-only en HRB, HLL-only en
> mega). A7 absorbe los muchos 1-pág de HPV/contratistas.

- **Carpeta:** `16.-Inspeccion Herramientas Electricas`
- **Volumen típico:** alto y heterogéneo. ABRIL: HPV 3 sueltos
  compilados (23 + 20 + 53 pp) + 9 subcarpetas por contratista
  (AGUASAN, ALUMINIO 2000, HU, JAPA, JJC, KOHLER, MMG, REALI, TITAN),
  HRB 9 sueltos compilados (3-31 pp con sufijos `_a/b/c/d`), HLU 3
  sueltos pequeños (3-6 pp), HLL 1 mega-compilado de 111 pp.
- **Modelo de conteo:** **1 portada = 1 documento**. Daniel
  confirmó: "en compilados casi siempre solo vienen primeras páginas,
  a pesar de decir 1 de 2 no viene la segunda". Cada página real ≈
  portada — por eso anchors funciona mejor que V4.
- **Scanner actual:** `SimpleFilenameScanner`.

#### Patrón observado (samples × 4 hospitales × varios contratistas)

| Sample | Págs | Template / Familia |
|--------|------|--------------------|
| HPV `chequeos_extenciones.pdf` (suelto) | 23 | F-CRS-LCH-04 compilado (familia CRS) |
| HPV `chequeos_sierra_circular.pdf` (suelto) | 20 | F-CRS-LCH-39 compilado (familia CRS) |
| HPV `chequeos_tableros_electricos.pdf` (suelto) | 53 | F-LCH-CRS-29 compilado (familia CRS) |
| HPV AGUASAN, JAPA, HU, MMG, REALI, ALUMINIO (varios) | 1 c/u | F-CRS-LCH-XX → A7 absorbe |
| HPV TITAN (varios herramientas) | 1 c/u | TN-SGSSO-RG-{137,191,...} TITAN propio → A7 absorbe |
| HPV KOHLER `esmeril.pdf` | 5 | F-CRS-LCH-14 compilado (familia CRS) |
| HPV JJC `esmeril/extensiones.pdf` | 2 c/u | F-CRS-LCH-XX (familia CRS) |
| HPV ALUMINIO `epp_*.pdf` | 1 | **LCH-CRS-02 EPP** — fuera de scope (anti-anchor) |
| HRB `check_list.pdf` / `check_list_a.pdf` | 3-5 | FORM-PREV-021 REALI landscape |
| HRB `check_list_ext{,_a,_b,_c,_d}.pdf` | 4-13 | F-CRS-LCH-04 compilados (familia CRS) |
| HRB `chequeo_tablero_electrico.pdf` | 31 | F-LCH-CRS-29 compilado (familia CRS) |
| HRB `inspeccion.pdf` | 7 | F-CRS-CRS "NOMINA INSPECCION" — tipo planilla (familia CRS) |
| HLU `chequeo_esmeril/ext/sierra.pdf` | 3-6 | F-CRS-LCH-{14,04,39} compilados |
| HLL `2026-04_herramientas_elec.pdf` | **111** | REG-SSO-HLL-17 landscape (cada pág = doc) |

**Observaciones**:
- **Familia CRS estándar es ~90% del corpus** y cubre múltiples
  códigos (`F-CRS-LCH-XX` con XX ∈ {04, 10, 14, 33, 39, ...},
  `F-LCH-CRS-29`, `F-CRS-CRS-XX`). El **título** varía
  ("CHEQUEO DE EXTENSIONES / ESMERIL / SIERRA / MAQUINA DE SOLDAR /
  TABLEROS / NOMINA INSPECCION DE HERRAMIENTAS") — **no se usa como
  ancla**. El **header común** sí es invariante.
- **TITAN propio (HPV/TITAN)**: cabecera con logo TITAN, "SISTEMA
  DE GESTIÓN DE SEGURIDAD Y SALUD OCUPACIONAL", subtitulo "CHECK
  LIST HERRAMIENTAS ELÉCTRICAS" + herramienta específica. Código
  `TN-SGSSO-RG-XXX` varía por herramienta.
- **REALI propio (HRB)**: `FORM-PREV-021` "LISTA DE CHEQUEO DE
  HERRAMIENTAS" + "PROGRAMA DE GESTIÓN EN SEGURIDAD Y SALUD
  OCUPACIONAL", landscape (rotación delegada upstream).
- **REG-SSO-HLL-17 (HLL)**: "Chequeo de Herramientas para
  Codificación por Mantención de Obra", grilla horizontal por
  trabajador/empresa con calendario al lado. Landscape (rotación
  delegada upstream).
- **EPP fuera de scope**: `LCH-CRS-02 CHEQUEO DE ELEMENTOS DE
  PROTECCIÓN PERSONAL` aparece en HPV/ALUMINIO 2000 — pertenece a
  otra sigla, debe rechazarse por anti-anchor.
- **HPV/contratistas son casi todos 1-pág** (AGUASAN, TITAN, JAPA,
  HU, MMG, REALI, ALUMINIO): A7 absorbe directo sin pasar por OCR.

#### Veredicto

`scan_strategy = "anchors"` multi-flavor (4 sabores), `top_fraction`
default 1/4, anti-anchor EPP en el sabor CRS estándar. Glob
recursivo (subcarpetas por contratista en HPV — séptima sigla con
este patrón).

#### Anclas por sabor (banda superior 1/4)

**`f_crs_estandar` (dominante, ~90%)**
- `"CONSTRUCTORA REGIÓN SUR"` — cubre SPA y SpA (header común)
- `"F-CRS-LCH"`, `"F-LCH-CRS"`, `"F-CRS-CRS"` — variantes de prefijo
  de código
- `"ITEM"`, `"ACTIVIDAD"`, `"CUMPLE"` — encabezados de tabla
- `"SI"`, `"NO"`, `"NA"` — encabezados de columna
- `"Página 1 de"` — cover marker
- `"Inspección Realizada"` — pie de página estable

`min_match = 4`. Anti-anchors: `"ELEMENTOS DE PROTECCIÓN PERSONAL"`,
`"LCH-CRS-02"` (rechaza EPP cross-categoría).

**`f_titan_chequeo` (HPV/TITAN)**
- `"TITAN"`, `"CHECK LIST"`, `"HERRAMIENTAS ELÉCTRICAS"`,
  `"TN-SGSSO-RG"`, `"SISTEMA DE GESTIÓN DE SEGURIDAD Y SALUD OCUPACIONAL"`

`min_match = 3`.

**`f_reali_form_prev` (HRB/check_list*)**
- `"REALI"`, `"FORM-PREV-021"`, `"LISTA DE CHEQUEO DE HERRAMIENTAS"`,
  `"PROGRAMA DE GESTIÓN EN SEGURIDAD"`

`min_match = 3`.

**`f_reg_sso_hll` (HLL mega 111 pp)**
- `"REG-SSO-HLL-17"`, `"Chequeo de Herramientas"`,
  `"Mantención de Obra"`, `"Codificación"`, `"Estado enchufe macho"`
  (header de columna muy específico)

`min_match = 3`.

#### Entrada en `patterns.py`

```python
"herramientas_elec": {
    "filename_glob": r"^.*herramientas_elec.*\.pdf$",
    "scan_strategy": "anchors",
    "cover_flavors": [
        {
            "name": "f_lch_xx",   # ver A9 — cubre F-CRS-LCH-* + F-LCH-CRS-* + F-CRS-CRS-*
            "anchors": [
                "CONSTRUCTORA REGIÓN SUR",
                "F-CRS-LCH",
                "F-LCH-CRS",
                "F-CRS-CRS",
                "ITEM",
                "ACTIVIDAD",
                "CUMPLE",
                "SI",
                "NO",
                "NA",
                "Página 1 de",
                "Inspección Realizada",
            ],
            "min_match": 4,
            "anti_anchors": [
                "ELEMENTOS DE PROTECCIÓN PERSONAL",
                "LCH-CRS-02",
            ],
        },
        {
            "name": "f_titan",   # ver A9
            "anchors": [
                "TITAN",
                "CHECK LIST",
                "HERRAMIENTAS ELÉCTRICAS",
                "TN-SGSSO-RG",
                "SISTEMA DE GESTIÓN DE SEGURIDAD Y SALUD OCUPACIONAL",
            ],
            "min_match": 3,
        },
        {
            "name": "f_reali",   # ver A9
            "anchors": [
                "REALI",
                "FORM-PREV-021",
                "LISTA DE CHEQUEO DE HERRAMIENTAS",
                "PROGRAMA DE GESTIÓN EN SEGURIDAD",
            ],
            "min_match": 3,
        },
        {
            "name": "f_hll_17",   # ver A9 — REG-SSO-HLL-17
            "anchors": [
                "REG-SSO-HLL-17",
                "Chequeo de Herramientas",
                "Mantención de Obra",
                "Codificación",
                "Estado enchufe macho",
            ],
            "min_match": 3,
        },
    ],
    "top_fraction": 0.25,
},
```

Glob recursivo `16.-Inspeccion Herramientas Electricas/**/*.pdf`
(HPV subcarpetas por contratista — séptima sigla con este patrón,
patrón consolidado).

#### Validación

Total = A7 (1-pág) + A2 anchor-matches por sabor (multi-pág).
Sanity contra totales mensuales por (hospital, herramientas_elec).
HLL viene en landscape (REG-SSO-HLL-17) y REALI/HRB en landscape
(FORM-PREV-021) — ambos delegados upstream para de-skew.

---

### 17 · `andamios` — Andamios

> **A2 multi-flavor (2 sabores) con anti-anchor ART** — la familia
> CRS estándar `F-CRS-LCH-05 LISTA DE CHEQUEO DE ANDAMIOS` cubre
> ~95% del corpus, incluyendo HLL (≠ cat 16, aquí HLL viene en
> portrait y formato CRS). Un sabor minoritario para RIBEIRO
> `1cl-1890` que apareció en 1 archivo de HRB. Anti-anchor rechaza
> los ARTs cross-categoría que TITAN clasificó como
> `*_armado_titan.pdf`. **HLU = 0 docs este mes** (carpeta inexistente
> — patrón nuevo a manejar transversalmente).

- **Carpeta:** `17.-Andamios`
- **Volumen típico:** medio-bajo. ABRIL: HPV 1 suelto (2 pp) + 4
  subcarpetas por contratista (AGUASAN, JAPA, JJC, TITAN), HRB 7
  sueltos (1-9 pp con sufijos `_a/b/c/d`), HLU **sin carpeta** (0
  docs), HLL 1 mega-compilado de 29 pp.
- **Modelo de conteo:** **1 portada = 1 chequeo**. HPV/contratistas
  mayormente 1-pág (A7 absorbe). Compilados con paginación real.
- **Scanner actual:** `SimpleFilenameScanner`.

#### Patrón observado (samples × hospitales × contratistas)

| Sample | Págs | Template / Familia |
|--------|------|--------------------|
| HPV `check_list.pdf` (suelto) | 2 | F-CRS-LCH-05 estándar |
| HPV AGUASAN, JJC, TITAN `chequeo_*.pdf` | 1 c/u | F-CRS-LCH-05 → A7 absorbe |
| HPV JAPA `chequeo_japa.pdf` | 3 | F-CRS-LCH-05 estándar |
| HPV TITAN `chequeo_titan.pdf` | 1 | F-CRS-LCH-05 → A7 absorbe |
| HPV TITAN `armado_titan.pdf` | 3 | **F-CRS-ART-01 ART** — fuera de scope (anti-anchor) |
| HRB `check_list.pdf` (abril) | 1 | **RIBEIRO 1cl-1890** propio (sabor secundario) |
| HRB `check_list.pdf`/`_a/_b/_c/_d/chequeo` (mayo) | 1-9 c/u | F-CRS-LCH-05 estándar |
| HLL `2026-04_andamios.pdf` | **29** | F-CRS-LCH-05 estándar (portrait, no landscape) |

**Observaciones**:
- **Template dominante `F-CRS-LCH-05`** con secciones bien
  definidas: DATOS DEL ANDAMIO / SUPERFICIE DE APOYO / ESTRUCTURA
  DEL ANDAMIO / PLATAFORMAS DE TRABAJO / ACCESOS / ACOPIOS /
  CAPACITACIÓN Y EXPERIENCIA. Header con FECHA, OBRA, Contratista,
  Subcontratista, Tipo andamio (FACHADA / MULTIDIRECCIONAL),
  Proveedor, Ubicación.
- **TITAN sí usa CRS estándar aquí** (≠ cat 16 donde TITAN tenía
  formato propio TN-SGSSO-RG).
- **Cross-categoría fuera de scope**: HPV/TITAN `*_armado_*.pdf`
  son **F-CRS-ART-01 ANÁLISIS DE RIESGOS EN EL TRABAJO** (sigla 7,
  no sigla 17). TITAN los clasifica acá porque el ART precede al
  montaje del andamio, pero no son chequeos de andamio.
- **HLU sin carpeta de andamios este mes** — no es un bug. El
  scanner debe devolver 0 sin lanzar excepción. Patrón nuevo que
  vale documentar como caveat transversal (cualquier sigla puede
  estar vacía en meses sin actividad).
- **HLL mega 29 pp = 29 chequeos individuales**, todos portrait y
  formato CRS estándar (≠ cat 16 mega landscape REG-SSO-HLL-17).

#### Veredicto

`scan_strategy = "anchors"` multi-flavor (2 sabores), `top_fraction`
default 1/4, anti-anchor ART en el sabor CRS estándar. Glob
recursivo (HPV subcarpetas — octava sigla con este patrón).

**Caveat aplicado**: ver **A8** (descubierto al cerrar esta sigla).

#### Anclas por sabor (banda superior 1/4)

**`f_crs_lch_05_andamios` (dominante, ~95%)**
- `"LISTA DE CHEQUEO DE ANDAMIOS"` — título universal
- `"CONSTRUCTORA REGIÓN SUR"` — subtítulo header
- `"F-CRS-LCH-05"` — código (sin variantes observadas, distinto a
  herramientas_elec donde el sufijo numérico cambiaba)
- `"Tipo andamio"` — field-label específico
- `"DATOS DEL ANDAMIO"`, `"SUPERFICIE DE APOYO"`,
  `"ESTRUCTURA DEL ANDAMIO"`, `"PLATAFORMAS DE TRABAJO"` —
  encabezados de secciones (suficientes en 1/4 sup si la tabla
  empieza arriba; redundancia útil)
- `"Página 1 de"` — cover marker

`min_match = 4`. Anti-anchors: `"ANÁLISIS DE RIESGOS EN EL TRABAJO"`,
`"F-CRS-ART-01"` (rechaza ARTs cross-categoría).

**`f_ribeiro_verificacion` (HRB, minoría)**
- `"RIBEIRO SPA"`, `"LISTA DE VERIFICACIÓN ANDAMIOS"`, `"1cl-1890"`,
  `"INSPECCIÓN DE ANDAMIOS"`, `"Centro de Trabajo"`,
  `"Línea de Negocio"`

`min_match = 3`.

#### Entrada en `patterns.py`

```python
"andamios": {
    "filename_glob": r"^.*andamios.*\.pdf$",
    "scan_strategy": "anchors",
    "cover_flavors": [
        {
            "name": "f_lch_05",   # ver A9
            "anchors": [
                "LISTA DE CHEQUEO DE ANDAMIOS",
                "CONSTRUCTORA REGIÓN SUR",
                "F-CRS-LCH-05",
                "Tipo andamio",
                "DATOS DEL ANDAMIO",
                "SUPERFICIE DE APOYO",
                "ESTRUCTURA DEL ANDAMIO",
                "PLATAFORMAS DE TRABAJO",
                "Página 1 de",
            ],
            "min_match": 4,
            "anti_anchors": [
                "ANÁLISIS DE RIESGOS EN EL TRABAJO",
                "F-CRS-ART-01",
            ],
        },
        {
            "name": "f_ribeiro",   # ver A9
            "anchors": [
                "RIBEIRO SPA",
                "LISTA DE VERIFICACIÓN ANDAMIOS",
                "1cl-1890",
                "INSPECCIÓN DE ANDAMIOS",
                "Centro de Trabajo",
                "Línea de Negocio",
            ],
            "min_match": 3,
        },
    ],
    "top_fraction": 0.25,
},
```

Glob recursivo `17.-Andamios/**/*.pdf` (HPV subcarpetas por
contratista — octava sigla con este patrón).

#### Validación

Total = A7 (1-pág) + A2 anchor-matches por sabor (multi-pág).
Sanity contra totales mensuales por (hospital, andamios). HLU = 0
docs (carpeta inexistente, sin actividad — ver A8).

---

### 18 · `chps` — Comité Paritario de Higiene y Seguridad

> **A2 mono-flavor sobre F-CRS-AR-01 `ACTA DE REUNIÓN`** — el mismo
> template que cat 1 `reunion` (la distinción CHPS vs reunión
> general vive en el filename + en el campo "Lugar de la reunión").
> Las anclas elegidas (`LISTA DE CONVOCADOS`, `DESARROLLO DE LA
> REUNIÓN`) aparecen **solo en p1**, no en p2/p3 — Daniel lo
> identificó al revisar el sample completo. Robusto a compilados
> multi-acta si llegaran (improbable, pero el costo es ínfimo).

- **Carpeta:** `18.-CHPS`
- **Volumen típico:** **ínfimo**. ABRIL: solo HPV con 1 archivo de
  3 páginas (1 acta CPHS). HRB, HLU, HLL **sin carpeta** (0 docs).
  Por DS-54 el CPHS sesiona ~1 vez al mes por obra, así que el
  techo natural es 4 PDFs/mes (1 por hospital) cuando todas las
  obras tienen actividad.
- **Modelo de conteo:** **1 acta = 1 documento** (independiente del
  número de páginas). Una reunión multi-página NO se cuenta varias
  veces — se cuenta como 1 portada.
- **Scanner actual:** `SimpleFilenameScanner`.

#### Patrón observado (sample HPV abril)

| Sample | Págs | Template / Estructura |
|--------|------|-----------------------|
| HPV `chps_acta_reunion.pdf` | 3 | F-CRS-AR-01 ACTA DE REUNIÓN |

**Estructura por página**:
- **p1 (portada)**: header `ACTA DE REUNIÓN` + código `F-CRS-AR-01` +
  OBRA `HOSPITAL DE PUERTO VARAS` + Lugar `SALA DE REUNIONES CPHS` +
  Fecha + **`LISTA DE CONVOCADOS`** (tabla NOMBRE/EMPRESA/FIRMAS) +
  **`DESARROLLO DE LA REUNIÓN`** (asuntos 1-2). "Página 1 de 3".
- **p2 (continuación)**: mismo header pero **sin LISTA DE
  CONVOCADOS ni DESARROLLO** — solo asuntos 2-7 con tabla `ASUNTO /
  ACUERDOS ADOPTADOS / RESPONSABLE / PLAZO / ESTADO`. "Página 2 de 3".
- **p3 (cierre)**: continuación de asuntos + `ASUNTOS PENDIENTES DE
  REUNIONES ANTERIORES` + `CONVOCATORIA PRÓXIMA REUNIÓN`. "Página 3
  de 3".

**Observaciones**:
- **Mismo template que cat 1 `reunion`**. La distinción vive en el
  filename (`chps_*.pdf` vs `reunion_*.pdf`) y en el campo "Lugar
  de la reunión" (CPHS lo dice explícitamente). Por claridad
  auditiva, mantener entradas separadas en `patterns.py` (DRY no
  vale el costo de confusión).
- **Diferencia p1 vs p2/p3 es la señal natural**: `LISTA DE
  CONVOCADOS` y `DESARROLLO DE LA REUNIÓN` solo aparecen en p1, así
  que son anclas ideales para detección de portada.
- **No hay cross-categoría detectada** — no se requieren
  anti-anchors. Las actas de reunión general (sigla 1) están en
  otra carpeta (`1.-...`), no en `18.-CHPS`.
- **HRB, HLU, HLL sin carpeta este mes** — ver A8.

#### Veredicto

`scan_strategy = "anchors"` mono-flavor, `top_fraction` default 1/4.
Anclas que cubren tanto el código común con `reunion` como las
secciones únicas de p1. **Sin anti-anchors** (no hay cross-categoría
que rechazar). A7 absorbe 1-pág si llegara (improbable; una reunión
real raramente cabe en 1 página).

#### Anclas (banda superior 1/4)

- `"ACTA DE REUNIÓN"` — título universal
- `"F-CRS-AR-01"` — código (común con sigla 1 `reunion`)
- `"LISTA DE CONVOCADOS"` — **solo en p1** (señal de portada)
- `"DESARROLLO DE LA REUNIÓN"` — **solo en p1** (señal de portada)
- `"HOSPITAL DE"` — OBRA (común a todos los hospitales)
- `"Lugar de la reunión"` — field-label
- `"Página 1 de"` — cover marker

7 anclas, `min_match = 3`. Robusto con margen.

#### Entrada en `patterns.py`

```python
"chps": {
    "filename_glob": r"^.*chps.*\.pdf$",
    "scan_strategy": "anchors",
    "cover_flavors": [
        {
            "name": "f_ar_01",   # ver A9
            "anchors": [
                "ACTA DE REUNIÓN",
                "F-CRS-AR-01",
                "LISTA DE CONVOCADOS",
                "DESARROLLO DE LA REUNIÓN",
                "HOSPITAL DE",
                "Lugar de la reunión",
                "Página 1 de",
            ],
            "min_match": 3,
        },
    ],
    "top_fraction": 0.25,
},
```

#### Validación

Total = A2 anchor-matches sobre p1 (modelo: 1 acta = 1 documento).
Sanity contra totales mensuales por (hospital, chps); techo natural
4/mes (1 por obra por DS-54). HRB/HLU/HLL = 0 docs en abril (sin
actividad — ver A8).
